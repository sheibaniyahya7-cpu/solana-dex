"""
MarketEvent model — records detected market events such as volume spikes,
whale entries, smart money accumulation, etc.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey,
    Index, Integer, Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class MarketEvent(Base, UUIDMixin, TimestampMixin):
    """
    A significant market event detected by the monitoring engine.
    Events are the primary trigger for AI analysis and alerts.
    """
    __tablename__ = "market_events"
    __table_args__ = (
        Index("ix_market_events_token_id", "token_id"),
        Index("ix_market_events_event_type", "event_type"),
        Index("ix_market_events_severity", "severity"),
        Index("ix_market_events_detected_at", "detected_at"),
        Index("ix_market_events_is_processed", "is_processed"),
        {"schema": "dex"},
    )

    # ─── Event Identity ───────────────────────────────────────────────────────
    token_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dex.tokens.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_mint: Mapped[str] = mapped_column(String(44), nullable=False)
    token_symbol: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # ─── Event Classification ─────────────────────────────────────────────────
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Types:
    #   VOLUME_SPIKE       — volume increased by threshold%
    #   PRICE_SPIKE        — price jumped by threshold%
    #   LIQUIDITY_ADD      — significant liquidity added
    #   LIQUIDITY_REMOVE   — significant liquidity removed (rug risk)
    #   WHALE_BUY          — whale wallet purchased
    #   WHALE_SELL         — whale wallet sold
    #   SMART_MONEY_ENTRY  — smart money wallet(s) entered
    #   SMART_MONEY_EXIT   — smart money wallet(s) exited
    #   NEW_TOKEN          — new token just launched
    #   MOMENTUM           — combined positive signals
    #   RUG_RISK           — security red flags detected

    severity: Mapped[str] = mapped_column(String(10), default="medium")
    # low | medium | high | critical

    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Text] = mapped_column(Text, nullable=False)

    # ─── Metrics at Event Time ────────────────────────────────────────────────
    price_usd_at_event: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 12), nullable=True)
    volume_usd_at_event: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2), nullable=True)
    liquidity_usd_at_event: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2), nullable=True)
    volume_change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    liquidity_change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ─── Smart Money Context ──────────────────────────────────────────────────
    smart_wallets_count: Mapped[int] = mapped_column(Integer, default=0)
    smart_wallets_addresses: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    whale_wallet_address: Mapped[Optional[str]] = mapped_column(String(44), nullable=True)
    whale_amount_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)

    # ─── AI Analysis (populated after analysis) ───────────────────────────────
    ai_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_decision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ─── Status ───────────────────────────────────────────────────────────────
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_alerted: Mapped[bool] = mapped_column(Boolean, default=False)
    alerted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # ─── Relationships ────────────────────────────────────────────────────────
    token: Mapped["Token"] = relationship(back_populates="events")
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<MarketEvent {self.event_type} {self.token_symbol} severity={self.severity}>"
