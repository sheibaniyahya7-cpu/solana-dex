"""
Redis connection pool and helper utilities.
Provides async Redis client with connection pooling, serialization helpers,
and a simple cache decorator.
"""

import json
import functools
from typing import Any, Callable, Optional, TypeVar, cast
from datetime import timedelta

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_pool: Optional[ConnectionPool] = None
_client: Optional[Redis] = None

# ─── Pool Management ──────────────────────────────────────────────────────────

async def init_redis() -> Redis:
    """Initialize the Redis connection pool. Call once at app startup."""
    global _pool, _client
    _pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_POOL_SIZE,
        decode_responses=settings.REDIS_DECODE_RESPONSES,
        socket_timeout=5,
        socket_connect_timeout=5,
        retry_on_timeout=True,
    )
    _client = Redis(connection_pool=_pool)
    # Verify connection
    await _client.ping()
    logger.info("Redis connection pool initialized", pool_size=settings.REDIS_POOL_SIZE)
    return _client


async def close_redis() -> None:
    """Gracefully close the Redis connection pool."""
    global _pool, _client
    if _client:
        await _client.aclose()
    if _pool:
        await _pool.aclose()
    logger.info("Redis connection pool closed")


def get_redis() -> Redis:
    """
    FastAPI dependency — returns active Redis client.
    Raises RuntimeError if not yet initialized.
    """
    if _client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _client


# ─── Serialization Helpers ────────────────────────────────────────────────────

class RedisCache:
    """
    High-level cache wrapper with JSON serialization.
    Supports TTL, namespaced keys, and bulk operations.
    """

    def __init__(self, client: Redis, namespace: str = "dex") -> None:
        self.client = client
        self.namespace = namespace

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        raw = await self.client.get(self._key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        serialized = json.dumps(value, default=str)
        if ttl:
            await self.client.setex(self._key(key), ttl, serialized)
        else:
            await self.client.set(self._key(key), serialized)

    async def delete(self, key: str) -> None:
        await self.client.delete(self._key(key))

    async def exists(self, key: str) -> bool:
        return bool(await self.client.exists(self._key(key)))

    async def get_or_set(
        self,
        key: str,
        factory: Callable,
        ttl: int = settings.CACHE_TTL_MEDIUM,
    ) -> Any:
        """Return cached value or call factory() to populate it."""
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await factory()
        await self.set(key, value, ttl=ttl)
        return value

    async def increment(self, key: str, amount: int = 1) -> int:
        return await self.client.incrby(self._key(key), amount)

    async def lpush_trim(self, key: str, value: Any, max_len: int = 1000) -> None:
        """Push to a list and trim to max_len (useful for event queues)."""
        pipe = self.client.pipeline()
        pipe.lpush(self._key(key), json.dumps(value, default=str))
        pipe.ltrim(self._key(key), 0, max_len - 1)
        await pipe.execute()

    async def lrange(self, key: str, start: int = 0, end: int = -1) -> list:
        raw_list = await self.client.lrange(self._key(key), start, end)
        return [json.loads(item) for item in raw_list]

    async def sadd(self, key: str, *members: str) -> None:
        await self.client.sadd(self._key(key), *members)

    async def smembers(self, key: str) -> set:
        return await self.client.smembers(self._key(key))

    async def hset(self, key: str, mapping: dict) -> None:
        serialized = {k: json.dumps(v, default=str) for k, v in mapping.items()}
        await self.client.hset(self._key(key), mapping=serialized)

    async def hgetall(self, key: str) -> dict:
        raw = await self.client.hgetall(self._key(key))
        return {k: json.loads(v) for k, v in raw.items()}

    async def publish(self, channel: str, message: Any) -> None:
        """Publish a message to a Redis pub/sub channel."""
        await self.client.publish(
            f"{self.namespace}:{channel}",
            json.dumps(message, default=str),
        )


# ─── Rate Limiter ─────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Sliding-window rate limiter backed by Redis.
    Used to throttle external API calls (Helius, Birdeye, etc.)
    """

    def __init__(self, client: Redis, key: str, limit: int, window: int) -> None:
        self.client = client
        self.key = f"ratelimit:{key}"
        self.limit = limit
        self.window = window  # seconds

    async def is_allowed(self) -> bool:
        pipe = self.client.pipeline()
        import time
        now = int(time.time() * 1000)
        window_start = now - (self.window * 1000)

        pipe.zremrangebyscore(self.key, 0, window_start)
        pipe.zcard(self.key)
        pipe.zadd(self.key, {str(now): now})
        pipe.expire(self.key, self.window)

        results = await pipe.execute()
        count = results[1]
        return count < self.limit

    async def wait_if_needed(self) -> None:
        import asyncio
        while not await self.is_allowed():
            await asyncio.sleep(0.1)
