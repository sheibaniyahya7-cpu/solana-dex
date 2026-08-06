"""
Whale activity endpoints — large wallet movements and transaction tracking.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_

from app.api.schemas.event_schemas import MarketEventResponse
from app.api.schemas.wallet_schemas import WalletListItem, WalletTradeResponse
from app.core.redis import get_redis, RedisCache
from app.database.base import get_db
from app.database.models.market_event import MarketEvent
from app.database.models.wallet import Wallet, WalletTrade
from app.database.repositories.wallet_repository import WalletRepository

router = APIRouter(prefix="/whales", tags=["whales"])


def get_wallet_repo(db: AsyncSession = Depends(get_db)) -> WalletRepository:
    return WalletRepository(db)


def get_cache(redis=Depends(get_redis)) -> RedisCache:
    return RedisCache(redis, namespace="whales")


@router.get("/activity", response_model=list[MarketEventResponse], summary="Recent whale activity")
async def get_whale_activity(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
):
    """
    Returns recent whale buy/sell events ordered by detection time.
    Whale events are triggered when a tracked large wallet makes a significant move.
    """
    from datetime import datetime, timezone, timedelta
    cache_key = f"activity:{hours}:{limit}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(MarketEvent)
        .where(
            and_(
                MarketEvent.event_type.in_(["WHALE_BUY", "WHALE_SELL"]),
                MarketEvent.detected_at >= cutoff,
            )
        )
        .order_by(desc(MarketEvent.detected_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()
    items = [MarketEventResponse.model_validate(e) for e in events]
    await cache.set(cache_key, [i.model_dump(mode="json") for i in items], ttl=30)
    return items


@router.get("/wallets", response_model=list[WalletListItem], summary="Whale wallets")
async def get_whale_wallets(
    limit: int = Query(50, ge=1, le=200),
    repo: WalletRepository = Depends(get_wallet_repo),
    cache: RedisCache = Depends(get_cache),
):
    """Wallets classified as whales, sorted by portfolio value."""
    cached = await cache.get(f"wallets:{limit}")
    if cached:
        return cached
    wallets = await repo.get_whale_wallets(limit=limit)
    items = [WalletListItem.model_validate(w) for w in wallets]
    await cache.set(f"wallets:{limit}", [i.model_dump(mode="json") for i in items], ttl=120)
    return items


@router.get("/recent-trades", response_model=list[WalletTradeResponse], summary="Recent whale trades")
async def get_recent_whale_trades(
    hours: int = Query(24, ge=1, le=72),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Most recent trades from whale wallets."""
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(WalletTrade)
        .join(Wallet, Wallet.id == WalletTrade.wallet_id)
        .where(
            and_(
                Wallet.is_whale == True,
                WalletTrade.trade_timestamp >= cutoff,
            )
        )
        .order_by(desc(WalletTrade.trade_timestamp))
        .limit(limit)
    )
    result = await db.execute(stmt)
    trades = result.scalars().all()
    return [WalletTradeResponse.model_validate(t) for t in trades]
