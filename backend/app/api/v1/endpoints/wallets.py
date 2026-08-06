"""
Wallet intelligence endpoints — smart money, whales, trade history.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.wallet_schemas import (
    WalletResponse, WalletListItem, WalletTradeResponse,
    WalletHoldingResponse, WalletSearchResponse,
)
from app.core.config import settings
from app.core.exceptions import NotFoundException
from app.core.redis import get_redis, RedisCache
from app.database.base import get_db
from app.database.repositories.wallet_repository import WalletRepository
from app.core.logging import get_logger

router = APIRouter(prefix="/wallets", tags=["wallets"])
logger = get_logger(__name__)


def get_wallet_repo(db: AsyncSession = Depends(get_db)) -> WalletRepository:
    return WalletRepository(db)


def get_cache(redis=Depends(get_redis)) -> RedisCache:
    return RedisCache(redis, namespace="wallets")


@router.get("", response_model=WalletSearchResponse, summary="List tracked wallets")
async def list_wallets(
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    wallet_type: Optional[str] = Query(None, description="smart_money | whale | insider | retail"),
    repo: WalletRepository = Depends(get_wallet_repo),
):
    offset = (page - 1) * page_size
    wallets = await repo.get_all(limit=page_size, offset=offset)
    total = await repo.count()
    items = [WalletListItem.model_validate(w) for w in wallets]
    return WalletSearchResponse(wallets=items, total=total, page=page, page_size=page_size)


@router.get("/smart-money", response_model=list[WalletListItem], summary="Smart money wallets")
async def get_smart_money(
    limit: int = Query(50, ge=1, le=200),
    repo: WalletRepository = Depends(get_wallet_repo),
    cache: RedisCache = Depends(get_cache),
):
    """
    Returns wallets classified as smart money — high win rate, consistent profits,
    early entry timing. These wallets are tracked for entry signal generation.
    """
    cached = await cache.get(f"smart_money:{limit}")
    if cached:
        return cached
    wallets = await repo.get_smart_money_wallets(limit=limit)
    items = [WalletListItem.model_validate(w) for w in wallets]
    await cache.set(f"smart_money:{limit}", [i.model_dump(mode="json") for i in items], ttl=120)
    return items


@router.get("/whales", response_model=list[WalletListItem], summary="Whale wallets")
async def get_whales(
    limit: int = Query(50, ge=1, le=100),
    repo: WalletRepository = Depends(get_wallet_repo),
    cache: RedisCache = Depends(get_cache),
):
    """Wallets with large portfolio value — sorted by portfolio size."""
    cached = await cache.get(f"whales:{limit}")
    if cached:
        return cached
    wallets = await repo.get_whale_wallets(limit=limit)
    items = [WalletListItem.model_validate(w) for w in wallets]
    await cache.set(f"whales:{limit}", [i.model_dump(mode="json") for i in items], ttl=120)
    return items


@router.get("/top-performers", response_model=list[WalletListItem], summary="Top performing wallets")
async def get_top_performers(
    limit: int = Query(50, ge=1, le=100),
    min_trades: int = Query(10, ge=5),
    repo: WalletRepository = Depends(get_wallet_repo),
):
    wallets = await repo.get_top_performers(limit=limit, min_trades=min_trades)
    return [WalletListItem.model_validate(w) for w in wallets]


@router.get("/{address}", response_model=WalletResponse, summary="Wallet detail")
async def get_wallet(
    address: str,
    repo: WalletRepository = Depends(get_wallet_repo),
    cache: RedisCache = Depends(get_cache),
):
    """Full wallet intelligence profile — PnL, win rate, holdings, behavior."""
    cached = await cache.get(f"detail:{address}")
    if cached:
        return cached

    wallet = await repo.get_by_address(address)
    if not wallet:
        raise NotFoundException(f"Wallet '{address}' not found.")

    result = WalletResponse.model_validate(wallet)
    await cache.set(f"detail:{address}", result.model_dump(mode="json"), ttl=300)
    return result


@router.get("/{address}/trades", response_model=list[WalletTradeResponse], summary="Wallet trade history")
async def get_wallet_trades(
    address: str,
    limit: int = Query(100, ge=1, le=500),
    token_mint: Optional[str] = Query(None),
    repo: WalletRepository = Depends(get_wallet_repo),
):
    wallet = await repo.get_by_address(address)
    if not wallet:
        raise NotFoundException(f"Wallet '{address}' not found.")
    trades = await repo.get_wallet_trades(wallet.id, limit=limit, token_mint=token_mint)
    return [WalletTradeResponse.model_validate(t) for t in trades]


@router.get("/{address}/holdings", response_model=list[WalletHoldingResponse], summary="Current holdings")
async def get_wallet_holdings(
    address: str,
    repo: WalletRepository = Depends(get_wallet_repo),
):
    wallet = await repo.get_by_address(address)
    if not wallet:
        raise NotFoundException(f"Wallet '{address}' not found.")

    from sqlalchemy import select
    from app.database.models.wallet import WalletHolding
    from app.database.base import get_session_factory
    # Holdings accessed via wallet relationship
    holdings = wallet.holdings
    # Eagerly load if needed via separate query
    from sqlalchemy import select
    from app.database.models.wallet import WalletHolding
    stmt = select(WalletHolding).where(WalletHolding.wallet_id == wallet.id)
    result = await repo.session.execute(stmt)
    holdings = result.scalars().all()
    return [WalletHoldingResponse.model_validate(h) for h in holdings]
