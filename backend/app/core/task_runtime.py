"""
Async runtime for Celery tasks.

Celery workers are synchronous processes, so every task body has to drive an
event loop itself. Using ``asyncio.run()`` per task is not viable here: the
Redis connection pool and the shared ``httpx.AsyncClient`` singletons bind to
the loop that first used them, and a fresh loop per task would invalidate them
after the first execution.

Instead each worker process keeps one long-lived event loop. Redis is
initialized once inside that loop the first time a task runs, which is also
what makes ``get_redis()`` usable from task code — the FastAPI lifespan that
normally calls ``init_redis()`` never executes in a worker.
"""

import asyncio
from typing import Any, Awaitable, TypeVar

from celery.signals import worker_process_shutdown

from app.core.logging import get_logger
from app.core.redis import close_redis, init_redis

logger = get_logger(__name__)

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None


def get_task_loop() -> asyncio.AbstractEventLoop:
    """Return this worker process's event loop, creating it on first use."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _loop.run_until_complete(init_redis())
        logger.info("Celery task event loop started with Redis initialized")
    return _loop


def run_async(coro: Awaitable[T]) -> T:
    """Run a task coroutine to completion on the worker's event loop."""
    return get_task_loop().run_until_complete(coro)


@worker_process_shutdown.connect
def _shutdown_task_loop(**_kwargs: Any) -> None:
    """Release the Redis pool and event loop when a worker process exits."""
    global _loop
    if _loop is None or _loop.is_closed():
        return
    try:
        _loop.run_until_complete(close_redis())
    except Exception as exc:
        logger.warning("Redis shutdown failed", error=str(exc))
    finally:
        _loop.close()
        _loop = None
