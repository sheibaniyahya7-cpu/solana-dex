"""
Volume collector — tracks volume changes and detects spikes.
Stores volume snapshots and calculates rolling comparisons.
Runs every 60 seconds via Celery beat.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List

from celery import shared_task

from app.collectors.base_collector import BaseCollector
from app.collectors.birdeye_client import birdeye_client
from app.collectors.dexscreener_client import dexscreener_client
from app.core.config import settings
from app.core.logging import get_logger
from app.core.task_runtime import run_async
from app.database.repositories.token_repository import TokenRepository

logger = get_logger(__name__)

# Redis key for storing previous volume snapshots
VOLUME_SNAPSHOT_KEY = "volume_snapshots"


class VolumeCollector(BaseCollector):
    """
    Periodically fetches volume for tracked tokens.
    Compares against previous snapshot to detect spikes.
    Emits volume spike events via Redis when thresholds are crossed.
    """
    name = "volume_collector"

    async def collect(self) -> dict:
        collected = 0
        spikes_detected = 0
        errors = 0
        cache = self.get_cache("volumes")
        now = datetime.now(timezone.utc)

        # ── Fetch active tokens ──────────────────────────────────────────────
        async with await self.get_db_session() as session:
            repo = TokenRepository(session)
            tokens = await repo.get_active_tokens(
                limit=200,
                min_liquidity=settings.MIN_LIQUIDITY_USD,
            )

        if not tokens:
            return {"collected": 0, "spikes_detected": 0, "errors": 0}

        # ── Load previous volume snapshots from Redis ────────────────────────
        prev_snapshots: Dict[str, float] = {}
        for token in tokens:
            cached = await cache.get(f"vol_snap:{token.mint_address}")
            if cached:
                prev_snapshots[token.mint_address] = float(cached)

        # ── Fetch Birdeye top token list (includes volume data) ──────────────
        try:
            top_tokens = await birdeye_client.get_token_list(
                sort_by="v24hUSD",
                sort_type="desc",
                limit=50,
                min_liquidity=settings.MIN_LIQUIDITY_USD,
            )
            birdeye_vol_map: Dict[str, float] = {
                t.get("address", ""): float(t.get("v24hUSD", 0) or 0)
                for t in top_tokens
            }
        except Exception as e:
            self.logger.warning("Birdeye volume fetch failed", error=str(e))
            birdeye_vol_map = {}

        # ── Compare volumes and detect spikes ────────────────────────────────
        async with await self.get_db_session() as session:
            repo = TokenRepository(session)

            for token in tokens:
                try:
                    current_vol = (
                        birdeye_vol_map.get(token.mint_address)
                        or float(token.volume_24h_usd or 0)
                    )
                    prev_vol = prev_snapshots.get(token.mint_address, current_vol)

                    # Calculate % change
                    if prev_vol > 0:
                        change_pct = ((current_vol - prev_vol) / prev_vol) * 100
                    else:
                        change_pct = 0

                    # Update DB
                    if current_vol > 0:
                        await repo.update(token, {
                            "volume_24h_usd": Decimal(str(current_vol)),
                            "last_updated_at": now,
                        })
                        collected += 1

                    # Store new snapshot
                    await cache.set(
                        f"vol_snap:{token.mint_address}",
                        current_vol,
                        ttl=3600,
                    )

                    # Detect spike
                    if change_pct >= settings.VOLUME_SPIKE_THRESHOLD:
                        spikes_detected += 1
                        self.logger.info(
                            "Volume spike detected",
                            mint=token.mint_address[:8],
                            symbol=token.symbol,
                            prev_vol=prev_vol,
                            current_vol=current_vol,
                            change_pct=round(change_pct, 1),
                        )
                        # Publish spike event for market monitor to pick up
                        await cache.publish("volume_spikes", {
                            "type": "VOLUME_SPIKE",
                            "mint": token.mint_address,
                            "symbol": token.symbol,
                            "prev_volume_usd": prev_vol,
                            "current_volume_usd": current_vol,
                            "change_pct": round(change_pct, 1),
                            "liquidity_usd": float(token.liquidity_usd or 0),
                            "detected_at": now.isoformat(),
                        })

                except Exception as e:
                    errors += 1
                    self.logger.warning(
                        "Volume update failed",
                        mint=token.mint_address[:8],
                        error=str(e),
                    )

            await session.commit()

        return {
            "collected": collected,
            "spikes_detected": spikes_detected,
            "errors": errors,
        }


@shared_task(name="app.collectors.volume_collector.collect_volumes", bind=True)
def collect_volumes(self) -> dict:
    """Celery task: refresh token volumes and detect spikes."""
    return run_async(VolumeCollector().run())
