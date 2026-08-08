"""
Market monitoring engine — detects trading opportunities and anomalies.
Runs every 30 seconds via Celery beat.

Detection pipeline:
1. Load active tokens + recent snapshots from Redis
2. Run all detectors in parallel
3. Deduplicate events (avoid re-alerting the same event twice in 5 min)
4. Persist DetectedEvents to MarketEvent DB records
5. Publish events to Redis pub/sub for WebSocket + alert system
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession

from app.monitors.event_types import (
    DetectedEvent, EventType, Severity,
    make_volume_spike_event, make_price_spike_event,
    make_smart_money_event, make_momentum_event, make_new_token_event,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis, RedisCache
from app.core.task_runtime import run_async
from app.database.base import get_session_factory
from app.database.models.market_event import MarketEvent
from app.database.models.token import Token
from app.database.repositories.event_repository import MarketEventRepository
from app.database.repositories.token_repository import TokenRepository
from app.database.repositories.wallet_repository import WalletRepository

logger = get_logger(__name__)

# Dedup window — don't re-emit same event type for same token within this many seconds
EVENT_DEDUP_TTL = 300  # 5 minutes


class MarketMonitor:
    """
    Core market monitoring engine.
    Pulls from multiple data streams and synthesizes market events.
    """

    def __init__(self) -> None:
        self.session_factory = get_session_factory()

    async def run(self) -> dict:
        events_detected = 0
        events_persisted = 0
        errors = 0

        try:
            async with self.session_factory() as session:
                token_repo = TokenRepository(session)
                wallet_repo = WalletRepository(session)

                # Load active tokens with sufficient data
                tokens = await token_repo.get_active_tokens(
                    limit=200,
                    min_liquidity=settings.MIN_LIQUIDITY_USD,
                )
                smart_wallets = await wallet_repo.get_smart_money_wallets(limit=500)
                smart_wallet_set = {w.address for w in smart_wallets}

            if not tokens:
                return {"events_detected": 0, "events_persisted": 0, "errors": 0}

            # Run all detectors concurrently
            all_events: List[DetectedEvent] = []
            results = await asyncio.gather(
                self._detect_volume_spikes(tokens),
                self._detect_price_spikes(tokens),
                self._detect_smart_money_entries(tokens, smart_wallet_set),
                self._detect_momentum_signals(tokens, smart_wallet_set),
                self._detect_new_tokens(tokens),
                return_exceptions=True,
            )

            for r in results:
                if isinstance(r, Exception):
                    errors += 1
                    logger.error("Detector failed", error=str(r))
                else:
                    all_events.extend(r)

            events_detected = len(all_events)

            # Persist and publish
            async with self.session_factory() as session:
                event_repo = MarketEventRepository(session)
                for event in all_events:
                    try:
                        if await self._is_duplicate(event):
                            continue
                        db_event = await self._persist_event(event_repo, event)
                        await self._publish_event(event, db_event)
                        await self._mark_dedup(event)
                        events_persisted += 1
                    except Exception as e:
                        errors += 1
                        logger.error("Event persist failed", error=str(e))
                await session.commit()

        except Exception as e:
            errors += 1
            logger.error("Market monitor run failed", error=str(e), exc_info=True)

        logger.info(
            "Market monitor cycle complete",
            detected=events_detected,
            persisted=events_persisted,
            errors=errors,
        )
        return {
            "events_detected": events_detected,
            "events_persisted": events_persisted,
            "errors": errors,
        }

    # ─── Detectors ────────────────────────────────────────────────────────────

    async def _detect_volume_spikes(
        self, tokens: List[Token]
    ) -> List[DetectedEvent]:
        """Detect tokens with sudden volume increases."""
        events = []
        cache = RedisCache(get_redis(), "volumes")

        for token in tokens:
            try:
                current_vol = float(token.volume_1h_usd or 0)
                if current_vol <= 0:
                    continue

                # Load previous 1h volume snapshot
                prev_key = f"prev_vol_1h:{token.mint_address}"
                prev_vol = await cache.get(prev_key)

                if prev_vol is not None:
                    prev_vol = float(prev_vol)
                    if prev_vol > 100:  # Avoid division by tiny numbers
                        change_pct = ((current_vol - prev_vol) / prev_vol) * 100
                        if change_pct >= settings.VOLUME_SPIKE_THRESHOLD:
                            events.append(make_volume_spike_event(
                                token_id=str(token.id),
                                token_mint=token.mint_address,
                                token_symbol=token.symbol,
                                prev_vol=prev_vol,
                                current_vol=current_vol,
                                change_pct=change_pct,
                                price_usd=float(token.price_usd or 0),
                                liquidity_usd=float(token.liquidity_usd or 0),
                            ))

                # Update snapshot
                await cache.set(prev_key, current_vol, ttl=3600)

            except Exception as e:
                logger.debug("Volume spike detection error", mint=token.mint_address[:8], error=str(e))

        return events

    async def _detect_price_spikes(
        self, tokens: List[Token]
    ) -> List[DetectedEvent]:
        """Detect significant price movements in short timeframes."""
        events = []

        for token in tokens:
            try:
                # 5-minute spike
                if (
                    token.price_change_5m
                    and token.price_change_5m >= settings.PRICE_SPIKE_THRESHOLD
                    and float(token.price_usd or 0) > 0
                ):
                    events.append(make_price_spike_event(
                        token_id=str(token.id),
                        token_mint=token.mint_address,
                        token_symbol=token.symbol,
                        change_pct=token.price_change_5m,
                        price_usd=float(token.price_usd),
                        timeframe="5m",
                    ))

                # 1-hour spike (different threshold)
                elif (
                    token.price_change_1h
                    and token.price_change_1h >= settings.PRICE_SPIKE_THRESHOLD * 2
                    and float(token.price_usd or 0) > 0
                ):
                    events.append(make_price_spike_event(
                        token_id=str(token.id),
                        token_mint=token.mint_address,
                        token_symbol=token.symbol,
                        change_pct=token.price_change_1h,
                        price_usd=float(token.price_usd),
                        timeframe="1h",
                    ))
            except Exception:
                pass

        return events

    async def _detect_smart_money_entries(
        self,
        tokens: List[Token],
        smart_wallet_set: set,
    ) -> List[DetectedEvent]:
        """
        Detect when multiple smart money wallets enter a token.
        Checks Redis for recently published smart money activity.
        """
        events = []
        cache = RedisCache(get_redis(), "wallets")

        for token in tokens:
            try:
                # Check Redis for smart money entries published by transaction collector
                key = f"sm_entries:{token.mint_address}"
                entries = await cache.lrange(key, 0, 49)

                if len(entries) >= 2:  # At least 2 smart wallets
                    wallet_addresses = [e.get("wallet") for e in entries if e.get("wallet")]
                    events.append(make_smart_money_event(
                        token_id=str(token.id),
                        token_mint=token.mint_address,
                        token_symbol=token.symbol,
                        wallet_addresses=wallet_addresses[:10],
                        trade_type="buy",
                        price_usd=float(token.price_usd or 0),
                        volume_usd=float(token.volume_1h_usd or 0),
                    ))
                    # Clear entries after processing
                    await cache.delete(key)
            except Exception:
                pass

        return events

    async def _detect_momentum_signals(
        self,
        tokens: List[Token],
        smart_wallet_set: set,
    ) -> List[DetectedEvent]:
        """
        Detect momentum by combining multiple positive signals:
        - Volume increasing + price increasing
        - Smart money present
        - Healthy buy/sell ratio
        - Improving liquidity
        """
        events = []

        for token in tokens:
            try:
                signals = []

                # Volume signal
                if token.price_change_1h and token.price_change_1h >= 10:
                    signals.append(f"Price +{token.price_change_1h:.0f}% (1h)")

                if token.volume_1h_usd and token.volume_24h_usd:
                    vol_1h = float(token.volume_1h_usd)
                    vol_24h_avg = float(token.volume_24h_usd) / 24
                    if vol_1h > vol_24h_avg * 2 and vol_24h_avg > 0:
                        signals.append("Volume 2x above average")

                # Buy pressure
                if token.buys_1h and token.sells_1h and token.sells_1h > 0:
                    ratio = token.buys_1h / token.sells_1h
                    if ratio >= 2.0:
                        signals.append(f"Buy/Sell ratio {ratio:.1f}x")

                # Minimum liquidity threshold
                if float(token.liquidity_usd or 0) >= 50_000:
                    signals.append(f"Liquidity ${float(token.liquidity_usd):,.0f}")

                # Security baseline
                if not token.has_mint_authority and not token.has_freeze_authority:
                    signals.append("No mint/freeze authority")

                # Only emit momentum if 3+ independent signals
                if len(signals) >= 3:
                    events.append(make_momentum_event(
                        token_id=str(token.id),
                        token_mint=token.mint_address,
                        token_symbol=token.symbol,
                        signals=signals,
                        price_usd=float(token.price_usd or 0),
                        volume_usd=float(token.volume_1h_usd or 0),
                        liquidity_usd=float(token.liquidity_usd or 0),
                    ))

            except Exception:
                pass

        return events

    async def _detect_new_tokens(
        self, tokens: List[Token]
    ) -> List[DetectedEvent]:
        """Emit events for tokens first seen in the last 10 minutes."""
        events = []
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)

        for token in tokens:
            try:
                if token.first_seen_at and token.first_seen_at >= cutoff:
                    liq = float(token.liquidity_usd or 0)
                    if liq >= settings.MIN_LIQUIDITY_USD:
                        events.append(make_new_token_event(
                            token_id=str(token.id),
                            token_mint=token.mint_address,
                            token_symbol=token.symbol,
                            liquidity_usd=liq,
                            dex_id=token.dex_id,
                        ))
            except Exception:
                pass

        return events

    # ─── Helpers ──────────────────────────────────────────────────────────────

    async def _is_duplicate(self, event: DetectedEvent) -> bool:
        """Check Redis dedup key to avoid re-emitting same event within 5 min."""
        redis = get_redis()
        key = f"event_dedup:{event.event_type}:{event.token_mint}"
        exists = await redis.exists(key)
        return bool(exists)

    async def _mark_dedup(self, event: DetectedEvent) -> None:
        """Set Redis dedup key so this event won't be re-emitted for 5 min."""
        redis = get_redis()
        key = f"event_dedup:{event.event_type}:{event.token_mint}"
        await redis.setex(key, EVENT_DEDUP_TTL, "1")

    async def _persist_event(
        self,
        repo: MarketEventRepository,
        event: DetectedEvent,
    ) -> MarketEvent:
        """Save a DetectedEvent to the database."""
        db_event = MarketEvent(
            token_id=UUID(event.token_id),
            token_mint=event.token_mint,
            token_symbol=event.token_symbol,
            event_type=event.event_type,
            severity=event.severity,
            title=event.title,
            description=event.description,
            detected_at=event.detected_at,
            price_usd_at_event=event.price_usd,
            volume_usd_at_event=event.volume_usd,
            liquidity_usd_at_event=event.liquidity_usd,
            volume_change_pct=event.volume_change_pct,
            price_change_pct=event.price_change_pct,
            smart_wallets_count=event.smart_wallets_count,
            smart_wallets_addresses=event.smart_wallets_addresses,
            whale_wallet_address=event.whale_wallet_address,
            whale_amount_usd=event.whale_amount_usd,
            extra_data=event.extra_data,
        )
        return await repo.create(db_event)

    async def _publish_event(
        self,
        event: DetectedEvent,
        db_event: MarketEvent,
    ) -> None:
        """Publish event to Redis pub/sub for WebSocket broadcast and alert dispatch."""
        cache = RedisCache(get_redis(), "dex")
        payload = {
            "type": "market_event",
            "event_id": str(db_event.id),
            "event_type": event.event_type,
            "severity": event.severity,
            "title": event.title,
            "description": event.description,
            "token_mint": event.token_mint,
            "token_symbol": event.token_symbol,
            "price_usd": event.price_usd,
            "volume_change_pct": event.volume_change_pct,
            "price_change_pct": event.price_change_pct,
            "smart_wallets_count": event.smart_wallets_count,
            "detected_at": event.detected_at.isoformat(),
        }
        # Broadcast to event feed WebSocket channel
        await cache.publish("events", payload)
        # Queue for alert processing
        await cache.publish("alert_queue", payload)

        logger.info(
            "Market event emitted",
            event_type=event.event_type,
            token=event.token_symbol,
            severity=event.severity,
        )


# ─── Celery task ──────────────────────────────────────────────────────────────

@shared_task(name="app.monitors.market_monitor.detect_market_events", bind=True)
def detect_market_events(self) -> dict:
    """Celery task: run one full monitoring cycle."""
    return run_async(MarketMonitor().run())
