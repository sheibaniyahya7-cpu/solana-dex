"""
Whale monitor — detects large wallet movements on tracked tokens.
Subscribes to whale transaction events published by the transaction collector
and generates MarketEvent records with alert payloads.
Runs every 60 seconds via Celery beat.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from celery import shared_task

from app.monitors.event_types import make_whale_event, make_smart_money_event
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis, RedisCache
from app.core.task_runtime import run_async
from app.database.base import get_session_factory
from app.database.models.market_event import MarketEvent
from app.database.repositories.event_repository import MarketEventRepository
from app.database.repositories.token_repository import TokenRepository
from app.database.repositories.wallet_repository import WalletRepository
from uuid import UUID

logger = get_logger(__name__)


class WhaleMonitor:
    """
    Processes whale transaction events from the Redis queue.
    Cross-references wallet classification to generate appropriate events.
    """

    def __init__(self) -> None:
        self.session_factory = get_session_factory()

    async def run(self) -> dict:
        processed = 0
        errors = 0

        redis = get_redis()
        cache = RedisCache(redis, "whales")

        # Drain the whale transaction queue (up to 100 events per cycle)
        whale_events = await cache.lrange("whale_tx_queue", 0, 99)
        if whale_events:
            # Clear processed items
            await redis.delete("whales:whale_tx_queue")

        for tx_event in whale_events:
            try:
                await self._process_whale_tx(tx_event)
                processed += 1
            except Exception as e:
                errors += 1
                logger.error("Whale tx processing failed", error=str(e))

        # Also check for smart money entries aggregated in Redis
        await self._aggregate_smart_money_entries()

        return {"processed": processed, "errors": errors}

    async def _process_whale_tx(self, tx_data: dict) -> None:
        """
        Convert a whale transaction into a MarketEvent.
        Determines event type based on wallet classification.
        """
        mint = tx_data.get("mint")
        wallet = tx_data.get("wallet")
        amount_usd = float(tx_data.get("amount_usd", 0))
        trade_type = tx_data.get("trade_type", "buy")

        if not mint or not wallet or amount_usd < settings.WHALE_TX_THRESHOLD_SOL * 100:
            return

        # Look up token
        async with self.session_factory() as session:
            token_repo = TokenRepository(session)
            wallet_repo = WalletRepository(session)

            token = await token_repo.get_by_mint(mint)
            if not token:
                return

            # Classify the wallet
            db_wallet = await wallet_repo.get_by_address(wallet)
            is_smart = db_wallet.is_smart_money if db_wallet else False
            is_whale = db_wallet.is_whale if db_wallet else (amount_usd >= 50_000)

            if is_smart:
                # Track as smart money entry
                sm_cache = RedisCache(get_redis(), "wallets")
                await sm_cache.lpush_trim(
                    f"sm_entries:{mint}",
                    {"wallet": wallet, "trade_type": trade_type, "amount_usd": amount_usd},
                    max_len=50,
                )
            elif is_whale or amount_usd >= 50_000:
                event = make_whale_event(
                    token_id=str(token.id),
                    token_mint=mint,
                    token_symbol=token.symbol,
                    wallet_address=wallet,
                    amount_usd=amount_usd,
                    trade_type=trade_type,
                    price_usd=float(token.price_usd or 0),
                )

                event_repo = MarketEventRepository(session)
                db_event = MarketEvent(
                    token_id=token.id,
                    token_mint=event.token_mint,
                    token_symbol=event.token_symbol,
                    event_type=event.event_type,
                    severity=event.severity,
                    title=event.title,
                    description=event.description,
                    detected_at=event.detected_at,
                    price_usd_at_event=event.price_usd,
                    whale_wallet_address=wallet,
                    whale_amount_usd=Decimal(str(amount_usd)),
                )
                await event_repo.create(db_event)
                await session.commit()

                # Publish to alert queue
                alert_cache = RedisCache(get_redis(), "dex")
                await alert_cache.publish("alert_queue", {
                    "type": "market_event",
                    "event_id": str(db_event.id),
                    "event_type": event.event_type,
                    "severity": event.severity,
                    "title": event.title,
                    "description": event.description,
                    "token_mint": mint,
                    "token_symbol": token.symbol,
                    "whale_amount_usd": amount_usd,
                    "detected_at": event.detected_at.isoformat(),
                })

                logger.info(
                    "Whale event created",
                    event_type=event.event_type,
                    token=token.symbol,
                    amount_usd=amount_usd,
                )

    async def _aggregate_smart_money_entries(self) -> None:
        """
        Check if enough smart money wallets have accumulated in any token
        to generate a SMART_MONEY_ENTRY event (triggered at 2+ wallets).
        The market monitor handles this — this is just a failsafe check.
        """
        pass  # Handled by market_monitor._detect_smart_money_entries


@shared_task(name="app.monitors.whale_monitor.detect_whale_activity", bind=True)
def detect_whale_activity(self) -> dict:
    """Celery task: process whale transaction queue and generate events."""
    return run_async(WhaleMonitor().run())
