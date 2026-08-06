"""Pydantic schemas for AI Analysis API endpoints."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AgentOutputSchema(BaseModel):
    """Generic agent output wrapper."""
    score: Optional[float] = None
    summary: Optional[str] = None
    signals: Optional[List[str]] = None
    risks: Optional[List[str]] = None
    raw: Optional[dict] = None


class AIAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    token_id: UUID
    token_mint: str
    token_symbol: Optional[str] = None

    # Component scores
    security_score: Optional[float] = None
    smart_money_score: Optional[float] = None
    volume_score: Optional[float] = None
    liquidity_score: Optional[float] = None
    social_score: Optional[float] = None

    # Final Trader Agent output
    final_score: Optional[float] = None
    decision: Optional[str] = None       # STRONG_BUY | BUY | WATCH | AVOID | DANGER
    confidence: Optional[float] = None
    summary: Optional[str] = None
    reasons: Optional[List[str]] = None
    risks: Optional[List[str]] = None
    catalysts: Optional[List[str]] = None

    analyzed_at: datetime
    model_used: Optional[str] = None
    analysis_duration_ms: Optional[int] = None


class AnalysisRequestSchema(BaseModel):
    """Request body to trigger on-demand analysis for a token."""
    mint_address: str
    force_refresh: bool = False  # Re-analyze even if recent analysis exists


class AnalysisSummaryResponse(BaseModel):
    """Quick summary for dashboard cards."""
    token_mint: str
    token_symbol: Optional[str] = None
    final_score: Optional[float] = None
    decision: Optional[str] = None
    confidence: Optional[float] = None
    top_reason: Optional[str] = None  # Most impactful positive signal
    top_risk: Optional[str] = None    # Most impactful risk
    analyzed_at: Optional[datetime] = None
