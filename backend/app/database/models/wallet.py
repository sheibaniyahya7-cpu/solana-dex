"""
Wallet model — tracks Solana wallet performance, classification, and PnL.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey,
    Index, Integer, Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDMixin


class Wallet(Base, UUIDMixin, TimestampMixin):
    """
    Solana wallet tracked for smart money / whale analysis.
    Performance metrics are recalculated periodically by the wallet analyzer.
    """
    __tablename__ = "wallets"
    __table_args__ = (
        Index("ix_wallets_address", "address", unique=True),
        Index("ix_wallets_wallet_type", "wallet_type"),
        Index("ix_wallets_score", "score"),
        Index("ix_wallets_win_rate", "win_rate"),
        {"schema": "dex"},
    )

    # ─── Identity ─────────────────────────────────────────────────────────────
    address: Mapped[str] = mapped_column(String(44), nullable=False, unique=True)
    label: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # e.g. "Alameda", "Jump"

    # ─── Classification ───────────────────────────────────────────────────────
    wallet_type: Mapped[str] = mapped_column(
        String(20), default="unknown"
    )  # smart_money | whale | insider | retail | unknown
    is_smart_money: Mapped[bool] = mapped_column(Boolean, default=False)
    is_whale: Mapped[bool] = mapped_column(Boolean, default=False)
    is_insider: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=True)

    # ─── Performance Metrics ──────────────────────────────────────────────────
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    total_pnl_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2), nullable=True)
    total_pnl_sol: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    realized_pnl_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2), nullable=True)
    unrealized_pnl_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2), nullable=True)
    roi_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    avg_profit_per_trade_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)
    avg_loss_per_trade_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)
    best_trade_pnl_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)
    worst_trade_pnl_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)

    # ─── Trading Behavior ─────────────────────────────────────────────────────
    avg_holding_time_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_entry_timing_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-100
    avg_exit_timing_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 0-100
    preferred_trade_size_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)

    # ─── Portfolio ────────────────────────────────────────────────────────────
    sol_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6), nullable=True)
    portfolio_value_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 2), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    # ─── Scoring ──────────────────────────────────────────────────────────────
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-100
    score_breakdown: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # ─── Activity ─────────────────────────────────────────────────────────────
    first_trade_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_trade_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ─── Extra ────────────────────────────────────────────────────────────────
    tags: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)  # ["degen", "early_buyer"]
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # ─── Relationships ────────────────────────────────────────────────────────
    trades: Mapped[List["WalletTrade"]] = relationship(
        back_populates="wallet", cascade="all, delete-orphan", lazy="dynamic"
    )
    holdings: Mapped[List["WalletHolding"]] = relationship(
        back_populates="wallet", cascade="all, delete-orphan", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<Wallet {self.address[:8]}... type={self.wallet_type} score={self.score}>"


class WalletTrade(Base, UUIDMixin, TimestampMixin):
    """Individual trade record linked to a wallet and a token."""
    __tablename__ = "wallet_trades"
    __table_args__ = (
        Index("ix_wallet_trades_wallet_id", "wallet_id"),
        Index("ix_wallet_trades_token_mint", "token_mint"),
        Index("ix_wallet_trades_timestamp", "trade_timestamp"),
        {"schema": "dex"},
    )

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dex.wallets.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_mint: Mapped[str] = mapped_column(String(44), nullable=False)
    token_symbol: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    trade_type: Mapped[str] = mapped_column(String(10), nullable=False)  # buy | sell
    trade_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signature: Mapped[str] = mapped_column(String(88), nullable=False)  # Solana tx signature

    amount_token: Mapped[Optional[Decimal]] = mapped_column(Numeric(38, 9), nullable=True)
    amount_sol: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 9), nullable=True)
    amount_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)
    price_per_token_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 12), nullable=True)

    pnl_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    holding_time_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    is_profitable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    dex_program: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # raydium, orca, etc.

    wallet: Mapped["Wallet"] = relationship(back_populates="trades")


class WalletHolding(Base, UUIDMixin, TimestampMixin):
    """Current token holdings for a tracked wallet."""
    __tablename__ = "wallet_holdings"
    __table_args__ = (
        Index("ix_wallet_holdings_wallet_id", "wallet_id"),
        Index("ix_wallet_holdings_token_mint", "token_mint"),
        {"schema": "dex"},
    )

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dex.wallets.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_mint: Mapped[str] = mapped_column(String(44), nullable=False)
    token_symbol: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    balance: Mapped[Decimal] = mapped_column(Numeric(38, 9), nullable=False)
    value_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)
    avg_buy_price_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 12), nullable=True)
    unrealized_pnl_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)
    unrealized_pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    first_buy_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    wallet: Mapped["Wallet"] = relationship(back_populates="holdings")
