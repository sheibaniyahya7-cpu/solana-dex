"""
Celery task: prune old records to keep DB size manageable.
Runs daily at 3 AM UTC (configured in celery_app.py beat schedule).
"""

from datetime import datetime, timezone, timedelta

from celery import shared_task
from sqlalchemy import delete, and_

from app.core.logging import get_logger

logger = get_logger(__name__)


@shared_task(name="app.database.cleanup.cleanup_old_records", bind=True)
def cleanup_old_records(self) -> dict:
    """
    Remove records older than retention thresholds:
    - Price history (1m interval): 7 days
    - Price history (5m interval): 30 days
    - Price history (1h+ interval): 365 days
    - Market events: 60 days
    - Sent alerts: 90 days
    """
    import asyncio
    from app.database.base import get_session_factory
    from app.database.models.token import TokenPriceHistory
    from app.database.models.market_event import MarketEvent
    from app.database.models.alert import Alert

    async def _run():
        factory = get_session_factory()
        deleted_counts = {}
        now = datetime.now(timezone.utc)

        async with factory() as session:
            # 1m candles: keep 7 days
            cutoff_1m = now - timedelta(days=7)
            result = await session.execute(
                delete(TokenPriceHistory).where(
                    and_(
                        TokenPriceHistory.interval == "1m",
                        TokenPriceHistory.timestamp < cutoff_1m,
                    )
                )
            )
            deleted_counts["price_1m"] = result.rowcount

            # 5m candles: keep 30 days
            cutoff_5m = now - timedelta(days=30)
            result = await session.execute(
                delete(TokenPriceHistory).where(
                    and_(
                        TokenPriceHistory.interval == "5m",
                        TokenPriceHistory.timestamp < cutoff_5m,
                    )
                )
            )
            deleted_counts["price_5m"] = result.rowcount

            # Market events: keep 60 days
            cutoff_events = now - timedelta(days=60)
            result = await session.execute(
                delete(MarketEvent).where(
                    and_(
                        MarketEvent.detected_at < cutoff_events,
                        MarketEvent.is_processed == True,
                    )
                )
            )
            deleted_counts["market_events"] = result.rowcount

            # Sent alerts: keep 90 days
            cutoff_alerts = now - timedelta(days=90)
            result = await session.execute(
                delete(Alert).where(
                    and_(
                        Alert.sent_at < cutoff_alerts,
                        Alert.is_sent == True,
                    )
                )
            )
            deleted_counts["alerts"] = result.rowcount

            await session.commit()

        logger.info("Database cleanup complete", counts=deleted_counts)
        return deleted_counts

    return asyncio.run(_run())
