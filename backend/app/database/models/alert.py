"""
Alert model — records sent notifications (Telegram, webhook, etc.)
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey,
    Index, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class Alert(Base, UUIDMixin, TimestampMixin):
    """Tracks every alert dispatched by the platform."""
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_token_id", "token_id"),
        Index("ix_alerts_event_id", "event_id"),
        Index("ix_alerts_alert_type", "alert_type"),
        Index("ix_alerts_sent_at", "sent_at"),
        {"schema": "dex"},
    )

    # ─── Context ──────────────────────────────────────────────────────────────
    token_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dex.tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dex.market_events.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ─── Alert Details ────────────────────────────────────────────────────────
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # SMART_MONEY | WHALE | VOLUME_SPIKE | NEW_TOKEN | SECURITY | AI_ANALYSIS | RUG_RISK
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    ai_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ─── Delivery ─────────────────────────────────────────────────────────────
    channel: Mapped[str] = mapped_column(String(32), nullable=False)  # telegram | webhook | email
    channel_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # chat_id or URL
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # ─── Relationships ────────────────────────────────────────────────────────
    token: Mapped[Optional["Token"]] = relationship(back_populates="alerts")
    event: Mapped[Optional["MarketEvent"]] = relationship(back_populates="alerts")

    def __repr__(self) -> str:
        return f"<Alert {self.alert_type} sent={self.is_sent}>"
