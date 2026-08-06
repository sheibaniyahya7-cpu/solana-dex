"""
Alert processor — subscribes to the Redis alert queue and dispatches
alerts via Telegram and other channels.
Also persists all alerts to the DB for the dashboard.

Architecture:
  Redis pub/sub "dex:alert_queue" → AlertProcessor → TelegramBot + DB
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Optional

from celery import shared_task

from app.alerts.telegram_bot import telegram_bot
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis, RedisCache
from app.database.base import get_session_factory
from app.database.models.alert import Alert
from app.database.repositories.event_repository import AlertRepository
from app.database.repositories.token_repository import TokenRepository

logger = get_logger(__name__)


class AlertProcessor:
    """
    Processes the alert queue from Redis and delivers notifications.
    Runs as a long-lived async task or via Celery.
    """

    def __init__(self) -> None:
        self.session_factory = get_session_factory()

    async def process_pending_alerts(self) -> dict:
        """
        Pull pending alerts from the Redis queue and deliver them.
        Called every 30 seconds by Celery beat (or as needed).
        """
        redis = get_redis()
        cache = RedisCache(redis, "dex")
        sent = 0
        failed = 0

        # Pull up to 50 alerts from the queue at once
        alerts = await cache.lrange("alert_queue_buffer", 0, 49)
        if alerts:
            await redis.delete("dex:alert_queue_buffer")

        for alert_data in alerts:
            try:
                await self._process_single_alert(alert_data)
                sent += 1
                # Rate limit — Telegram allows ~30 msg/sec
                await asyncio.sleep(0.1)
            except Exception as e:
                failed += 1
                logger.error("Alert processing failed", error=str(e), data=str(alert_data)[:100])

        # Also process any unsent DB alerts (retry failed ones)
        await self._retry_failed_db_alerts()

        return {"sent": sent, "failed": failed}

    async def _process_single_alert(self, alert_data: Dict) -> None:
        """Process one alert: deliver via Telegram + persist to DB."""
        event_type = alert_data.get("event_type") or alert_data.get("type", "")
        token_mint = alert_data.get("token_mint")
        ai_score = alert_data.get("final_score") or alert_data.get("ai_score")

        # Severity mapping
        severity = self._determine_severity(event_type, ai_score, alert_data)

        # ── Telegram dispatch ─────────────────────────────────────────────
        telegram_sent = False
        if telegram_bot.is_configured():
            telegram_sent = await telegram_bot.dispatch_alert(alert_data)

        # ── Persist to DB ─────────────────────────────────────────────────
        async with self.session_factory() as session:
            alert_repo = AlertRepository(session)
            token_repo = TokenRepository(session)

            # Look up token ID
            token_id = None
            if token_mint:
                token = await token_repo.get_by_mint(token_mint)
                if token:
                    token_id = token.id

            # Build alert message summary
            title = alert_data.get("title", f"{event_type} Alert")
            message = alert_data.get("description") or alert_data.get("summary", "")

            db_alert = Alert(
                token_id=token_id,
                alert_type=event_type or "UNKNOWN",
                severity=severity,
                title=title[:256],
                message=message[:4000] if message else "",
                ai_score=float(ai_score) if ai_score else None,
                channel="telegram",
                channel_id=settings.TELEGRAM_ALERT_CHAT_ID or settings.TELEGRAM_CHAT_ID,
                is_sent=telegram_sent,
                sent_at=datetime.now(timezone.utc) if telegram_sent else None,
                error_message=None if telegram_sent else "Telegram delivery failed",
                extra_data=alert_data,
            )
            await alert_repo.create(db_alert)
            await session.commit()

        # ── WebSocket broadcast ───────────────────────────────────────────
        ws_cache = RedisCache(get_redis(), "dex")
        await ws_cache.publish("alerts", {
            "type": "alert",
            "event_type": event_type,
            "severity": severity,
            "title": title,
            "token_mint": token_mint,
            "ai_score": ai_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def _retry_failed_db_alerts(self) -> None:
        """Retry delivery for alerts that failed on first attempt."""
        async with self.session_factory() as session:
            alert_repo = AlertRepository(session)
            unsent = await alert_repo.get_unsent(limit=20)

            for alert in unsent:
                if alert.retry_count >= 3:
                    continue
                try:
                    if alert.extra_data and telegram_bot.is_configured():
                        success = await telegram_bot.dispatch_alert(alert.extra_data)
                        if success:
                            alert.is_sent = True
                            alert.sent_at = datetime.now(timezone.utc)
                        alert.retry_count += 1
                except Exception as e:
                    alert.retry_count += 1
                    alert.error_message = str(e)[:500]

            await session.commit()

    def _determine_severity(
        self,
        event_type: str,
        ai_score: Optional[float],
        data: Dict,
    ) -> str:
        """Map event type and score to severity level."""
        if event_type in ("RUG_RISK", "DANGER"):
            return "critical"
        if event_type in ("WHALE_BUY", "WHALE_SELL") and float(data.get("whale_amount_usd", 0) or 0) >= 100_000:
            return "high"
        if event_type == "SMART_MONEY_ENTRY" and int(data.get("smart_wallets_count", 0) or 0) >= 3:
            return "high"
        if event_type == "AI_ANALYSIS" and ai_score and float(ai_score) >= 80:
            return "high"
        if event_type in ("VOLUME_SPIKE", "MOMENTUM"):
            return "medium"
        return "medium"


# ─── Redis Pub/Sub listener for real-time alert ingestion ──────────────────────

async def start_alert_listener() -> None:
    """
    Long-running async task that listens to the Redis alert_queue pub/sub channel
    and buffers incoming alerts for processing.
    Called once at application startup in production environments.
    """
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe("dex:alert_queue")
    logger.info("Alert listener started — subscribed to dex:alert_queue")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    # Buffer into a Redis list for batch processing
                    cache = RedisCache(redis, "dex")
                    await cache.lpush_trim("alert_queue_buffer", data, max_len=500)
                except Exception as e:
                    logger.warning("Alert buffer error", error=str(e))
    except asyncio.CancelledError:
        await pubsub.unsubscribe()
        logger.info("Alert listener stopped")


# ─── Celery task ──────────────────────────────────────────────────────────────

@shared_task(name="app.alerts.alert_processor.process_alerts", bind=True)
def process_alerts(self) -> dict:
    """Celery task: deliver pending alerts from queue."""
    return asyncio.run(AlertProcessor().process_pending_alerts())
