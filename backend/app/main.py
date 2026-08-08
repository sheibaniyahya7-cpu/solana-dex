"""
FastAPI application factory.
Creates and configures the ASGI app with all routers, middleware,
exception handlers, lifespan events, and WebSocket support.
"""

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.exceptions import DexBaseException
from app.core.redis import init_redis, close_redis
from app.core.http_client import close_all_clients
from app.database.base import init_db, close_db

# Routers
from app.api.v1.router import api_router
from app.api.websocket import (
    ws_router,
    start_pubsub_forwarders,
    stop_pubsub_forwarders,
)
from app.alerts.alert_processor import (
    start_alert_listener_task,
    stop_alert_listener_task,
)

logger = get_logger(__name__)


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Startup and shutdown lifecycle management.
    All I/O-bound resources are initialized here, not at module level.
    """
    # ── Startup ──────────────────────────────────────────────────────────────
    setup_logging()
    logger.info(
        "Starting DEX Trader Intelligence Platform",
        version=settings.APP_VERSION,
        env=settings.APP_ENV,
    )

    # Initialize database connection pool
    await init_db()
    logger.info("Database initialized")

    # Initialize Redis connection pool
    await init_redis()
    logger.info("Redis initialized")

    # Bridge Redis pub/sub (written by Celery workers) to WebSocket clients
    await start_pubsub_forwarders()

    # Buffer alerts published on dex:alert_queue so the Celery alert task can
    # deliver them. Without a subscriber the queue is a dead end.
    await start_alert_listener_task()

    logger.info("All services ready — platform is online")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Shutting down platform...")
    await stop_alert_listener_task()
    await stop_pubsub_forwarders()
    await close_db()
    await close_redis()
    await close_all_clients()
    logger.info("Shutdown complete")


# ─── App Factory ──────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Professional AI-powered Solana DEX trading intelligence platform. "
            "Real-time market monitoring, multi-agent AI analysis, smart money tracking."
        ),
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    _register_middleware(app)

    # ── Exception Handlers ────────────────────────────────────────────────────
    _register_exception_handlers(app)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    app.include_router(ws_router, prefix="/ws")

    # ── Health & Root ─────────────────────────────────────────────────────────
    _register_system_routes(app)

    return app


# ─── Middleware Registration ───────────────────────────────────────────────────

def _register_middleware(app: FastAPI) -> None:
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Gzip compression for responses > 1KB
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Request timing middleware
    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
        response.headers["X-API-Version"] = settings.APP_VERSION
        return response

    # Request ID middleware for tracing
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        import uuid
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ─── Exception Handlers ───────────────────────────────────────────────────────

def _register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(DexBaseException)
    async def dex_exception_handler(request: Request, exc: DexBaseException):
        logger.warning(
            "Domain exception",
            error_code=exc.error_code,
            message=exc.message,
            path=str(request.url),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning(
            "Request validation failed",
            path=str(request.url),
            errors=exc.errors(),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error_code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled exception",
            path=str(request.url),
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error_code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred.",
            },
        )


# ─── System Routes ────────────────────────────────────────────────────────────

def _register_system_routes(app: FastAPI) -> None:

    @app.get("/health", tags=["system"], summary="Health check")
    async def health_check():
        """
        Returns platform health status.
        Used by Docker health checks and load balancers.
        """
        from app.core.redis import get_redis
        from app.database.base import get_engine
        from sqlalchemy import text

        checks = {"status": "ok", "version": settings.APP_VERSION, "services": {}}

        # Database check
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["services"]["database"] = "ok"
        except Exception as e:
            checks["services"]["database"] = f"error: {str(e)[:50]}"
            checks["status"] = "degraded"

        # Redis check
        try:
            redis = get_redis()
            await redis.ping()
            checks["services"]["redis"] = "ok"
        except Exception as e:
            checks["services"]["redis"] = f"error: {str(e)[:50]}"
            checks["status"] = "degraded"

        status_code = 200 if checks["status"] == "ok" else 503
        return JSONResponse(content=checks, status_code=status_code)

    @app.get("/", tags=["system"], include_in_schema=False)
    async def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "health": "/health",
        }


# ─── Module-level app instance ────────────────────────────────────────────────
app = create_app()
