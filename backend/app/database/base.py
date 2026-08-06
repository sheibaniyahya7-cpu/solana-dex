"""
SQLAlchemy async engine, session factory, and declarative base.
All models import Base from here.
"""

from typing import AsyncGenerator

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ─── Naming Convention ────────────────────────────────────────────────────────
# Ensures Alembic can auto-generate constraint names consistently
NAMING_CONVENTION: dict = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION, schema="dex")


class Base(DeclarativeBase):
    metadata = metadata


# ─── Engine ───────────────────────────────────────────────────────────────────
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_timeout=settings.DATABASE_POOL_TIMEOUT,
            pool_pre_ping=True,          # Validate connections before use
            pool_recycle=3600,           # Recycle connections every hour
            echo=settings.DATABASE_ECHO,
        )
    return _engine


def get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,      # Don't expire objects after commit
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


async def init_db() -> None:
    """Verify DB connectivity at startup."""
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("Database connection verified")


async def close_db() -> None:
    """Dispose the connection pool on shutdown."""
    global _engine
    if _engine:
        await _engine.dispose()
        logger.info("Database connection pool closed")


# ─── FastAPI Dependency ───────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields an async database session.
    Usage: db: AsyncSession = Depends(get_db)
    Automatically commits on success, rolls back on exception.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
