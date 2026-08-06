"""
Token model — represents a Solana SPL token tracked by the platform.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class Token(Base, UUIDMixin, TimestampMixin):
    """
    Solana SPL token tracked by the platform.
    Stores metadata, current market state, and security analysis.
    """
    __tablename__ = "tokens"
    __table_args__ = (
        UniqueConstraint("mint_address", name="uq_tokens_mint_address"),
        Index("ix_tokens_symbol", "symbol"),
        Index("ix_tokens_created_at", "created_at"),
        Index("ix_tokens_ai_score", "ai_score"),
        Index("ix_tokens_is_active", "is_active"),
        {"schema": "dex"},
    )

    # ─── Identity ─────────────────────────────────────────────────────────────
    mint_address: Mapped[str] = mapped_column(String(44), nullable=False, index=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    decimals: Mapped[int] = mapped_column(Integer, default=9)
    logo_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ─── Market Data ──────────────────────────────────────────────────────────
    price_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 12), nullable=True)
    price_sol: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 12), nullable=True)
    market_cap_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2), nullable=True)
    fully_diluted_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2), nullable=True)
    total_supply: Mapped[Optional[Decimal]] = mapped_column(Numeric(38, 0), nullable=True)
    circulating_supply: Mapped[Optional[Decimal]] = mapped_column(Numeric(38, 0), nullable=True)

    # ─── Volume & Liquidity ───────────────────────────────────────────────────
    volume_24h_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2), nullable=True)
    volume_1h_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2), nullable=True)
    volume_5m_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2), nullable=True)
    liquidity_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2), nullable=True)

    # ─── Price Changes ────────────────────────────────────────────────────────
    price_change_5m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_change_1h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_change_6h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_change_24h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ─── Transaction Counts ───────────────────────────────────────────────────
    tx_count_5m: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tx_count_1h: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tx_count_24h: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    buys_5m: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sells_5m: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    buys_1h: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sells_1h: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ─── Holder Information ───────────────────────────────────────────────────
    holder_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    top_10_holder_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dev_wallet_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ─── Security ─────────────────────────────────────────────────────────────
    has_mint_authority: Mapped[bool] = mapped_column(Boolean, default=True)
    has_freeze_authority: Mapped[bool] = mapped_column(Boolean, default=True)
    is_mutable: Mapped[bool] = mapped_column(Boolean, default=True)
    security_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rug_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ─── AI Scores ────────────────────────────────────────────────────────────
    ai_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    smart_money_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    liquidity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    social_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_decision: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # STRONG_BUY | BUY | WATCH | AVOID | DANGER
    ai_analysis_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_analyzed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ─── DEX Info ─────────────────────────────────────────────────────────────
    dex_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    pair_address: Mapped[Optional[str]] = mapped_column(String(44), nullable=True)
    base_token_address: Mapped[Optional[str]] = mapped_column(String(44), nullable=True)
    quote_token_address: Mapped[Optional[str]] = mapped_column(String(44), nullable=True)

    # ─── Social ───────────────────────────────────────────────────────────────
    website: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    twitter: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    telegram: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    discord: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ─── Status ───────────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ─── Extra Metadata ───────────────────────────────────────────────────────
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # ─── Relationships ────────────────────────────────────────────────────────
    price_history: Mapped[List["TokenPriceHistory"]] = relationship(
        back_populates="token", cascade="all, delete-orphan", lazy="dynamic"
    )
    events: Mapped[List["MarketEvent"]] = relationship(
        back_populates="token", cascade="all, delete-orphan", lazy="dynamic"
    )
    alerts: Mapped[List["Alert"]] = relationship(
        back_populates="token", cascade="all, delete-orphan", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<Token {self.symbol} ({self.mint_address[:8]}...)>"


class TokenPriceHistory(Base, UUIDMixin):
    """OHLCV price history for a token, bucketed by interval."""
    __tablename__ = "token_price_history"
    __table_args__ = (
        Index("ix_price_history_token_ts", "token_id", "timestamp"),
        Index("ix_price_history_timestamp", "timestamp"),
        {"schema": "dex"},
    )

    token_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dex.tokens.id", ondelete="CASCADE"),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False)  # 1m, 5m, 1h, 4h, 1d

    open: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 12), nullable=True)
    high: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 12), nullable=True)
    low: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 12), nullable=True)
    close: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 12), nullable=True)
    volume_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2), nullable=True)
    tx_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    buys: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sells: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    token: Mapped["Token"] = relationship(back_populates="price_history")
