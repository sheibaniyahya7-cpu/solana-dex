"""
Token endpoints — market data, price history, search, stats.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.token_schemas import (
    TokenResponse, TokenListItem, TokenPriceHistoryItem,
    TokenSearchResponse, TokenStatsResponse,
)
from app.core.config import settings
from app.core.exceptions import NotFoundException
from app.core.redis import get_redis, RedisCache
from app.database.base import get_db
from app.database.repositories.token_repository import TokenRepository
from app.core.logging import get_logger

router = APIRouter(prefix="/tokens", tags=["tokens"])
logger = get_logger(__name__)


# ─── Dependency helpers ───────────────────────────────────────────────────────

def get_token_repo(db: AsyncSession = Depends(get_db)) -> TokenRepository:
    return TokenRepository(db)


def get_cache(redis=Depends(get_redis)) -> RedisCache:
    return RedisCache(redis, namespace="tokens")


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=TokenSearchResponse, summary="List tokens")
async def list_tokens(
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    min_liquidity: float = Query(0, ge=0, description="Minimum liquidity in USD"),
    min_score: float = Query(0, ge=0, le=100, description="Minimum AI score"),
    repo: TokenRepository = Depends(get_token_repo),
    cache: RedisCache = Depends(get_cache),
):
    """
    Returns paginated list of active tokens, ordered by AI score descending.
    Results are cached for 30 seconds.
    """
    cache_key = f"list:{page}:{page_size}:{min_liquidity}:{min_score}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    offset = (page - 1) * page_size
    tokens = await repo.get_active_tokens(
        limit=page_size,
        offset=offset,
        min_liquidity=min_liquidity,
        min_score=min_score,
    )
    total = await repo.count()
    items = [TokenListItem.model_validate(t) for t in tokens]
    result = TokenSearchResponse(
        tokens=items, total=total, page=page, page_size=page_size
    )
    await cache.set(cache_key, result.model_dump(mode="json"), ttl=settings.CACHE_TTL_SHORT)
    return result


@router.get("/new", response_model=list[TokenListItem], summary="New token launches")
async def get_new_tokens(
    hours: int = Query(24, ge=1, le=168, description="Look-back window in hours"),
    limit: int = Query(50, ge=1, le=100),
    repo: TokenRepository = Depends(get_token_repo),
    cache: RedisCache = Depends(get_cache),
):
    """
    Returns tokens first detected within the last N hours.
    Sorted by discovery time — newest first.
    """
    cache_key = f"new:{hours}:{limit}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    tokens = await repo.get_new_tokens(hours=hours, limit=limit)
    items = [TokenListItem.model_validate(t) for t in tokens]
    await cache.set(cache_key, [i.model_dump(mode="json") for i in items], ttl=30)
    return items


@router.get("/search", response_model=list[TokenListItem], summary="Search tokens")
async def search_tokens(
    q: str = Query(..., min_length=1, max_length=100, description="Symbol, name, or mint address"),
    limit: int = Query(20, ge=1, le=50),
    repo: TokenRepository = Depends(get_token_repo),
):
    """Full-text search by symbol, name, or mint address."""
    tokens = await repo.search(q, limit=limit)
    return [TokenListItem.model_validate(t) for t in tokens]


@router.get("/stats", response_model=TokenStatsResponse, summary="Market overview stats")
async def get_market_stats(
    repo: TokenRepository = Depends(get_token_repo),
    cache: RedisCache = Depends(get_cache),
):
    """Aggregated market statistics for the overview dashboard."""
    cached = await cache.get("market_stats")
    if cached:
        return cached

    total = await repo.count()
    new_tokens = await repo.get_new_tokens(hours=24, limit=1000)
    top_by_score = await repo.get_top_by_score(limit=10)
    active = await repo.get_active_tokens(limit=1, min_liquidity=0)

    result = TokenStatsResponse(
        total_tokens=total,
        active_tokens=total,   # Refined by actual filter in production
        new_tokens_24h=len(new_tokens),
        top_by_score=[TokenListItem.model_validate(t) for t in top_by_score],
        top_movers=[],
        top_by_volume=[],
    )
    await cache.set("market_stats", result.model_dump(mode="json"), ttl=60)
    return result


@router.get("/top", response_model=list[TokenListItem], summary="Top tokens by AI score")
async def get_top_tokens(
    limit: int = Query(20, ge=1, le=100),
    repo: TokenRepository = Depends(get_token_repo),
    cache: RedisCache = Depends(get_cache),
):
    """Top N tokens ranked by AI composite score."""
    cache_key = f"top:{limit}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    tokens = await repo.get_top_by_score(limit=limit)
    items = [TokenListItem.model_validate(t) for t in tokens]
    await cache.set(cache_key, [i.model_dump(mode="json") for i in items], ttl=60)
    return items


@router.get("/{mint_address}", response_model=TokenResponse, summary="Token detail")
async def get_token(
    mint_address: str,
    repo: TokenRepository = Depends(get_token_repo),
    cache: RedisCache = Depends(get_cache),
):
    """Full token detail including market data, security analysis, and AI scores."""
    cache_key = f"detail:{mint_address}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    token = await repo.get_by_mint(mint_address)
    if not token:
        raise NotFoundException(f"Token with mint address '{mint_address}' not found.")

    result = TokenResponse.model_validate(token)
    await cache.set(cache_key, result.model_dump(mode="json"), ttl=settings.CACHE_TTL_SHORT)
    return result


@router.get("/{mint_address}/price-history", response_model=list[TokenPriceHistoryItem])
async def get_price_history(
    mint_address: str,
    interval: str = Query("5m", pattern="^(1m|5m|1h|4h|1d)$"),
    limit: int = Query(200, ge=10, le=1000),
    repo: TokenRepository = Depends(get_token_repo),
    cache: RedisCache = Depends(get_cache),
):
    """OHLCV price history for charting. Ordered oldest → newest."""
    token = await repo.get_by_mint(mint_address)
    if not token:
        raise NotFoundException(f"Token '{mint_address}' not found.")

    cache_key = f"price_history:{mint_address}:{interval}:{limit}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    history = await repo.get_price_history(token.id, interval=interval, limit=limit)
    items = [TokenPriceHistoryItem.model_validate(h) for h in reversed(history)]
    await cache.set(cache_key, [i.model_dump(mode="json") for i in items], ttl=30)
    return items
