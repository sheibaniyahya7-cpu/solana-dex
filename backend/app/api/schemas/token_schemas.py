"""
Pydantic schemas for Token API endpoints.
Separates API contracts from DB models.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TokenBase(BaseModel):
    mint_address: str
    symbol: Optional[str] = None
    name: Optional[str] = None
    decimals: int = 9
    logo_uri: Optional[str] = None


class TokenMarketData(BaseModel):
    price_usd: Optional[Decimal] = None
    price_sol: Optional[Decimal] = None
    market_cap_usd: Optional[Decimal] = None
    volume_24h_usd: Optional[Decimal] = None
    volume_1h_usd: Optional[Decimal] = None
    volume_5m_usd: Optional[Decimal] = None
    liquidity_usd: Optional[Decimal] = None
    price_change_5m: Optional[float] = None
    price_change_1h: Optional[float] = None
    price_change_6h: Optional[float] = None
    price_change_24h: Optional[float] = None
    buys_5m: Optional[int] = None
    sells_5m: Optional[int] = None
    buys_1h: Optional[int] = None
    sells_1h: Optional[int] = None
    tx_count_24h: Optional[int] = None

    @property
    def buy_sell_ratio(self) -> Optional[float]:
        if self.buys_1h and self.sells_1h and self.sells_1h > 0:
            return round(self.buys_1h / self.sells_1h, 2)
        return None


class TokenSecurityData(BaseModel):
    has_mint_authority: bool = True
    has_freeze_authority: bool = True
    is_mutable: bool = True
    holder_count: Optional[int] = None
    top_10_holder_pct: Optional[float] = None
    dev_wallet_pct: Optional[float] = None
    security_score: Optional[float] = None
    rug_probability: Optional[float] = None


class TokenAIData(BaseModel):
    ai_score: Optional[float] = None
    smart_money_score: Optional[float] = None
    volume_score: Optional[float] = None
    liquidity_score: Optional[float] = None
    social_score: Optional[float] = None
    ai_decision: Optional[str] = None
    ai_analysis_text: Optional[str] = None
    ai_analyzed_at: Optional[datetime] = None


class TokenResponse(TokenBase, TokenMarketData, TokenSecurityData, TokenAIData):
    """Full token response — used for token detail page."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    is_verified: bool
    first_seen_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    pair_address: Optional[str] = None
    dex_id: Optional[str] = None
    website: Optional[str] = None
    twitter: Optional[str] = None
    telegram: Optional[str] = None
    created_at: datetime


class TokenListItem(BaseModel):
    """Compact token representation for list views."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mint_address: str
    symbol: Optional[str] = None
    name: Optional[str] = None
    logo_uri: Optional[str] = None
    price_usd: Optional[Decimal] = None
    price_change_1h: Optional[float] = None
    price_change_24h: Optional[float] = None
    volume_24h_usd: Optional[Decimal] = None
    liquidity_usd: Optional[Decimal] = None
    ai_score: Optional[float] = None
    ai_decision: Optional[str] = None
    security_score: Optional[float] = None
    first_seen_at: Optional[datetime] = None
    is_verified: bool = False


class TokenPriceHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    interval: str
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    close: Optional[Decimal] = None
    volume_usd: Optional[Decimal] = None
    tx_count: Optional[int] = None
    buys: Optional[int] = None
    sells: Optional[int] = None


class TokenSearchResponse(BaseModel):
    tokens: List[TokenListItem]
    total: int
    page: int
    page_size: int


class TokenStatsResponse(BaseModel):
    """Aggregated market statistics for the overview dashboard."""
    total_tokens: int
    active_tokens: int
    new_tokens_24h: int
    total_volume_24h_usd: Optional[Decimal] = None
    total_liquidity_usd: Optional[Decimal] = None
    avg_ai_score: Optional[float] = None
    top_movers: List[TokenListItem] = []
    top_by_volume: List[TokenListItem] = []
    top_by_score: List[TokenListItem] = []
