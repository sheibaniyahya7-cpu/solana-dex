"""
AIAnalysis model — stores the full multi-agent analysis result for a token.
One record per analysis run (tokens can be analyzed multiple times).
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime, Float, ForeignKey,
    Index, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class AIAnalysis(Base, UUIDMixin, TimestampMixin):
    """
    Full AI analysis result produced by the multi-agent orchestrator.
    Each agent's output is stored alongside the Trader Agent's final synthesis.
    """
    __tablename__ = "ai_analyses"
    __table_args__ = (
        Index("ix_ai_analyses_token_id", "token_id"),
        Index("ix_ai_analyses_analyzed_at", "analyzed_at"),
        Index("ix_ai_analyses_final_score", "final_score"),
        Index("ix_ai_analyses_decision", "decision"),
        {"schema": "dex"},
    )

    token_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dex.tokens.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_mint: Mapped[str] = mapped_column(String(44), nullable=False)
    token_symbol: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # ─── Per-Agent Outputs ────────────────────────────────────────────────────
    market_agent_output: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    security_agent_output: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    whale_agent_output: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    wallet_agent_output: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    social_agent_output: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # ─── Component Scores ─────────────────────────────────────────────────────
    security_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    smart_money_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    liquidity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    social_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ─── Trader Agent Final Output ────────────────────────────────────────────
    final_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-100
    decision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # STRONG_BUY | BUY | WATCH | AVOID | DANGER
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-1
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reasons: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)  # list of str
    risks: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)    # list of str
    catalysts: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True) # list of str
    raw_trader_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ─── Metadata ─────────────────────────────────────────────────────────────
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_used: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(nullable=True)
    analysis_duration_ms: Mapped[Optional[int]] = mapped_column(nullable=True)

    # ─── Relationships ────────────────────────────────────────────────────────
    token: Mapped["Token"] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<AIAnalysis {self.token_symbol} "
            f"score={self.final_score} decision={self.decision}>"
        )
