"""
MarketEvent and Alert repositories.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.market_event import MarketEvent
from app.database.models.alert import Alert
from app.database.repositories.base_repository import BaseRepository


class MarketEventRepository(BaseRepository[MarketEvent]):
    model = MarketEvent

    async def get_unprocessed(self, limit: int = 50) -> Sequence[MarketEvent]:
        stmt = (
            select(MarketEvent)
            .where(MarketEvent.is_processed == False)
            .order_by(desc(MarketEvent.detected_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_recent_events(
        self,
        hours: int = 24,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> Sequence[MarketEvent]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        conditions = [MarketEvent.detected_at >= cutoff]
        if event_type:
            conditions.append(MarketEvent.event_type == event_type)
        if severity:
            conditions.append(MarketEvent.severity == severity)
        stmt = (
            select(MarketEvent)
            .where(and_(*conditions))
            .order_by(desc(MarketEvent.detected_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_token_events(
        self, token_id: UUID, limit: int = 20
    ) -> Sequence[MarketEvent]:
        stmt = (
            select(MarketEvent)
            .where(MarketEvent.token_id == token_id)
            .order_by(desc(MarketEvent.detected_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def mark_processed(self, event_id: UUID) -> None:
        stmt = (
            update(MarketEvent)
            .where(MarketEvent.id == event_id)
            .values(is_processed=True)
        )
        await self.session.execute(stmt)


class AlertRepository(BaseRepository[Alert]):
    model = Alert

    async def get_unsent(self, limit: int = 100) -> Sequence[Alert]:
        stmt = (
            select(Alert)
            .where(and_(Alert.is_sent == False, Alert.retry_count < 3))
            .order_by(Alert.created_at)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_recent_alerts(
        self, hours: int = 24, limit: int = 50
    ) -> Sequence[Alert]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(Alert)
            .where(Alert.created_at >= cutoff)
            .order_by(desc(Alert.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
