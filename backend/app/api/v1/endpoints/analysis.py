"""
AI Analysis endpoints — trigger analysis, fetch results, decision summaries.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.api.schemas.analysis_schemas import (
    AIAnalysisResponse, AnalysisRequestSchema, AnalysisSummaryResponse,
)
from app.core.config import settings
from app.core.exceptions import NotFoundException, InsufficientDataException
from app.core.redis import get_redis, RedisCache
from app.database.base import get_db
from app.database.models.analysis import AIAnalysis
from app.database.repositories.token_repository import TokenRepository
from app.core.logging import get_logger

router = APIRouter(prefix="/analysis", tags=["analysis"])
logger = get_logger(__name__)


def get_token_repo(db: AsyncSession = Depends(get_db)) -> TokenRepository:
    return TokenRepository(db)


def get_cache(redis=Depends(get_redis)) -> RedisCache:
    return RedisCache(redis, namespace="analysis")


@router.post("/trigger", status_code=status.HTTP_202_ACCEPTED, summary="Trigger AI analysis")
async def trigger_analysis(
    request: AnalysisRequestSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    repo: TokenRepository = Depends(get_token_repo),
):
    """
    Queues an AI analysis job for the specified token.
    Returns immediately — analysis runs asynchronously in Celery.
    Poll GET /analysis/{mint_address}/latest for results.
    """
    token = await repo.get_by_mint(request.mint_address)
    if not token:
        raise NotFoundException(f"Token '{request.mint_address}' not found.")

    # Dispatch Celery task
    from app.ai_agents.orchestrator import run_token_analysis
    task = run_token_analysis.apply_async(
        args=[request.mint_address],
        kwargs={"force_refresh": request.force_refresh},
        queue="analyzers",
    )

    return {
        "status": "queued",
        "task_id": task.id,
        "token_mint": request.mint_address,
        "message": "Analysis queued. Check /analysis/{mint}/latest for results.",
    }


@router.get("/{mint_address}/latest", response_model=AIAnalysisResponse, summary="Latest analysis")
async def get_latest_analysis(
    mint_address: str,
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
):
    """Returns the most recent AI analysis for a token."""
    cache_key = f"latest:{mint_address}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    stmt = (
        select(AIAnalysis)
        .where(AIAnalysis.token_mint == mint_address)
        .order_by(desc(AIAnalysis.analyzed_at))
        .limit(1)
    )
    result = await db.execute(stmt)
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise NotFoundException(f"No analysis found for token '{mint_address}'.")

    resp = AIAnalysisResponse.model_validate(analysis)
    await cache.set(cache_key, resp.model_dump(mode="json"), ttl=300)
    return resp


@router.get("/{mint_address}/history", response_model=List[AIAnalysisResponse], summary="Analysis history")
async def get_analysis_history(
    mint_address: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Returns all past AI analyses for a token, newest first."""
    stmt = (
        select(AIAnalysis)
        .where(AIAnalysis.token_mint == mint_address)
        .order_by(desc(AIAnalysis.analyzed_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    analyses = result.scalars().all()
    return [AIAnalysisResponse.model_validate(a) for a in analyses]


@router.get("/summaries/top", response_model=List[AnalysisSummaryResponse], summary="Top AI picks")
async def get_top_ai_picks(
    limit: int = 20,
    decision: str = None,
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
):
    """
    Returns the top AI picks — tokens with the highest scores from the latest analysis.
    Optionally filter by decision (BUY, WATCH, etc.)
    """
    cache_key = f"top_picks:{limit}:{decision}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    from sqlalchemy import func
    # Get latest analysis per token
    subq = (
        select(
            AIAnalysis.token_mint,
            func.max(AIAnalysis.analyzed_at).label("latest_at")
        )
        .group_by(AIAnalysis.token_mint)
        .subquery()
    )
    stmt = (
        select(AIAnalysis)
        .join(subq, (AIAnalysis.token_mint == subq.c.token_mint) &
              (AIAnalysis.analyzed_at == subq.c.latest_at))
        .order_by(desc(AIAnalysis.final_score))
        .limit(limit)
    )
    if decision:
        stmt = stmt.where(AIAnalysis.decision == decision.upper())

    result = await db.execute(stmt)
    analyses = result.scalars().all()

    summaries = [
        AnalysisSummaryResponse(
            token_mint=a.token_mint,
            token_symbol=a.token_symbol,
            final_score=a.final_score,
            decision=a.decision,
            confidence=a.confidence,
            top_reason=a.reasons[0] if a.reasons else None,
            top_risk=a.risks[0] if a.risks else None,
            analyzed_at=a.analyzed_at,
        )
        for a in analyses
    ]
    await cache.set(cache_key, [s.model_dump(mode="json") for s in summaries], ttl=120)
    return summaries
