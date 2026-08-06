"""
Market events endpoints — detected opportunities and anomalies.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.event_schemas import (
    MarketEventResponse, EventListResponse,
)
from app.core.config import settings
from app.core.exceptions import NotFoundException
from app.core.redis import get_redis, RedisCache
from app.database.base import get_db
from app.database.repositories.event_repository import MarketEventRepository
from app.core.logging import get_logger

router = APIRouter(prefix="/events", tags=["events"])
logger = get_logger(__name__)


def get_event_repo(db: AsyncSession = Depends(get_db)) -> MarketEventRepository:
    return MarketEventRepository(db)


def get_cache(redis=Depends(get_redis)) -> RedisCache:
    return RedisCache(redis, namespace="events")


@router.get("", response_model=EventListResponse, summary="List market events")
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    event_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None, pattern="^(low|medium|high|critical)$"),
    hours: int = Query(24, ge=1, le=168),
    repo: MarketEventRepository = Depends(get_event_repo),
    cache: RedisCache = Depends(get_cache),
):
    """
    Returns recent market events ordered by detection time — newest first.
    Filter by event type (VOLUME_SPIKE, WHALE_BUY, SMART_MONEY_ENTRY, etc.)
    or severity level.
    """
    cache_key = f"list:{page}:{page_size}:{event_type}:{severity}:{hours}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    events = await repo.get_recent_events(
        hours=hours, event_type=event_type, severity=severity,
        limit=page_size * 10  # Fetch more for pagination
    )
    offset = (page - 1) * page_size
    page_events = events[offset: offset + page_size]
    items = [MarketEventResponse.model_validate(e) for e in page_events]
    result = EventListResponse(
        events=items, total=len(events), page=page, page_size=page_size
    )
    await cache.set(cache_key, result.model_dump(mode="json"), ttl=15)
    return result


@router.get("/unprocessed", response_model=list[MarketEventResponse], summary="Unprocessed events")
async def get_unprocessed_events(
    limit: int = Query(50, ge=1, le=200),
    repo: MarketEventRepository = Depends(get_event_repo),
):
    """Events that have not yet been analyzed by the AI agents."""
    events = await repo.get_unprocessed(limit=limit)
    return [MarketEventResponse.model_validate(e) for e in events]


@router.get("/{event_id}", response_model=MarketEventResponse, summary="Event detail")
async def get_event(
    event_id: str,
    repo: MarketEventRepository = Depends(get_event_repo),
):
    from uuid import UUID
    try:
        uid = UUID(event_id)
    except ValueError:
        raise NotFoundException("Invalid event ID format.")
    event = await repo.get_by_id(uid)
    if not event:
        raise NotFoundException(f"Event '{event_id}' not found.")
    return MarketEventResponse.model_validate(event)
