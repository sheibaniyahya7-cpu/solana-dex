"""
Base collector class.
All data collectors extend this to get shared retry logic,
rate limiting, session management, and metrics.
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import settings
from app.core.http_client import get_http_client
from app.core.logging import get_logger
from app.core.redis import get_redis, RedisCache, RateLimiter
from app.database.base import get_session_factory


class BaseCollector(ABC):
    """
    Abstract base for all data collectors.
    Subclasses implement `collect()` with the actual data-fetching logic.
    """

    name: str = "base_collector"

    def __init__(self) -> None:
        self.logger = get_logger(f"collector.{self.name}")
        self._session_factory = get_session_factory()

    # ─── Session helpers ──────────────────────────────────────────────────────

    async def get_db_session(self):
        """Returns an async DB session context manager."""
        return self._session_factory()

    def get_cache(self, namespace: str = "collectors") -> RedisCache:
        return RedisCache(get_redis(), namespace=namespace)

    def get_rate_limiter(self, key: str, limit: int, window: int = 60) -> RateLimiter:
        return RateLimiter(get_redis(), key=key, limit=limit, window=window)

    # ─── Abstract interface ───────────────────────────────────────────────────

    @abstractmethod
    async def collect(self) -> dict:
        """
        Main collection method. Must return a dict with at minimum:
        { "collected": int, "errors": int, "duration_ms": float }
        """
        ...

    # ─── Lifecycle helpers ────────────────────────────────────────────────────

    async def run(self) -> dict:
        """
        Wraps collect() with timing, error handling, and metrics reporting.
        Called by Celery tasks.
        """
        start = datetime.now(timezone.utc)
        self.logger.info(f"Collector starting", collector=self.name)
        try:
            result = await self.collect()
            duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            result["duration_ms"] = duration_ms
            result["collector"] = self.name
            result["ran_at"] = start.isoformat()
            self.logger.info(
                "Collector finished",
                collector=self.name,
                collected=result.get("collected", 0),
                errors=result.get("errors", 0),
                duration_ms=round(duration_ms, 2),
            )
            return result
        except Exception as e:
            duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            self.logger.error(
                "Collector failed",
                collector=self.name,
                error=str(e),
                duration_ms=round(duration_ms, 2),
                exc_info=True,
            )
            return {
                "collector": self.name,
                "collected": 0,
                "errors": 1,
                "error_message": str(e),
                "duration_ms": duration_ms,
            }
