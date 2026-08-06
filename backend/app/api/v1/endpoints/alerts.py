"""
Alerts endpoints — view and manage sent notifications.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.event_schemas import AlertResponse, AlertListResponse
from app.core.config import settings
from app.core.redis import get_redis, RedisCache
from app.database.base import get_db
from app.database.repositories.event_repository import AlertRepository

router = APIRouter(prefix="/alerts", tags=["alerts"])


def get_alert_repo(db: AsyncSession = Depends(get_db)) -> AlertRepository:
    return AlertRepository(db)


def get_cache(redis=Depends(get_redis)) -> RedisCache:
    return RedisCache(redis, namespace="alerts")


@router.get("", response_model=AlertListResponse, summary="List alerts")
async def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    hours: int = Query(24, ge=1, le=168),
    alert_type: Optional[str] = Query(None),
    repo: AlertRepository = Depends(get_alert_repo),
    cache: RedisCache = Depends(get_cache),
):
    """Recent alerts sent by the platform, newest first."""
    cache_key = f"list:{page}:{page_size}:{hours}:{alert_type}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    alerts = await repo.get_recent_alerts(hours=hours, limit=page_size * 5)
    offset = (page - 1) * page_size
    page_alerts = alerts[offset: offset + page_size]
    items = [AlertResponse.model_validate(a) for a in page_alerts]
    result = AlertListResponse(
        alerts=items, total=len(alerts), page=page, page_size=page_size
    )
    await cache.set(cache_key, result.model_dump(mode="json"), ttl=30)
    return result


@router.get("/unsent", response_model=list[AlertResponse], summary="Unsent alerts")
async def get_unsent_alerts(
    repo: AlertRepository = Depends(get_alert_repo),
):
    """Alerts queued but not yet delivered. Useful for monitoring alert delivery."""
    alerts = await repo.get_unsent(limit=100)
    return [AlertResponse.model_validate(a) for a in alerts]
