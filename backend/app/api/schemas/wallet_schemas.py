"""Pydantic schemas for Wallet API endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    address: str
    label: Optional[str] = None
    wallet_type: str
    is_smart_money: bool
    is_whale: bool
    is_insider: bool

    # Performance
    total_trades: int
    winning_trades: int
    win_rate: Optional[float] = None
    total_pnl_usd: Optional[Decimal] = None
    roi_pct: Optional[float] = None
    avg_profit_per_trade_usd: Optional[Decimal] = None

    # Behavior
    avg_holding_time_hours: Optional[float] = None
    avg_entry_timing_score: Optional[float] = None
    avg_exit_timing_score: Optional[float] = None

    # Portfolio
    sol_balance: Optional[Decimal] = None
    portfolio_value_usd: Optional[Decimal] = None
    token_count: int

    # Score
    score: Optional[float] = None
    score_breakdown: Optional[dict] = None

    # Activity
    last_trade_at: Optional[datetime] = None
    last_analyzed_at: Optional[datetime] = None
    tags: Optional[list] = None


class WalletListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    address: str
    label: Optional[str] = None
    wallet_type: str
    is_smart_money: bool
    is_whale: bool
    win_rate: Optional[float] = None
    total_pnl_usd: Optional[Decimal] = None
    roi_pct: Optional[float] = None
    total_trades: int
    score: Optional[float] = None
    last_trade_at: Optional[datetime] = None


class WalletTradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    token_mint: str
    token_symbol: Optional[str] = None
    trade_type: str
    trade_timestamp: datetime
    signature: str
    amount_usd: Optional[Decimal] = None
    price_per_token_usd: Optional[Decimal] = None
    pnl_usd: Optional[Decimal] = None
    pnl_pct: Optional[float] = None
    holding_time_hours: Optional[float] = None
    is_profitable: Optional[bool] = None
    dex_program: Optional[str] = None


class WalletHoldingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    token_mint: str
    token_symbol: Optional[str] = None
    balance: Decimal
    value_usd: Optional[Decimal] = None
    avg_buy_price_usd: Optional[Decimal] = None
    unrealized_pnl_usd: Optional[Decimal] = None
    unrealized_pnl_pct: Optional[float] = None
    first_buy_at: Optional[datetime] = None


class WalletSearchResponse(BaseModel):
    wallets: List[WalletListItem]
    total: int
    page: int
    page_size: int
