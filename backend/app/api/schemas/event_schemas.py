"""Pydantic schemas for MarketEvent and Alert API endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MarketEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    token_id: UUID
    token_mint: str
    token_symbol: Optional[str] = None
    event_type: str
    severity: str
    title: str
    description: str

    price_usd_at_event: Optional[Decimal] = None
    volume_usd_at_event: Optional[Decimal] = None
    liquidity_usd_at_event: Optional[Decimal] = None
    volume_change_pct: Optional[float] = None
    price_change_pct: Optional[float] = None

    smart_wallets_count: int = 0
    whale_wallet_address: Optional[str] = None
    whale_amount_usd: Optional[Decimal] = None

    ai_score: Optional[float] = None
    ai_decision: Optional[str] = None
    ai_summary: Optional[str] = None

    detected_at: datetime
    is_processed: bool
    is_alerted: bool


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    token_id: Optional[UUID] = None
    event_id: Optional[UUID] = None
    alert_type: str
    severity: str
    title: str
    message: str
    ai_score: Optional[float] = None
    channel: str
    is_sent: bool
    sent_at: Optional[datetime] = None
    created_at: datetime


class EventListResponse(BaseModel):
    events: List[MarketEventResponse]
    total: int
    page: int
    page_size: int


class AlertListResponse(BaseModel):
    alerts: List[AlertResponse]
    total: int
    page: int
    page_size: int
