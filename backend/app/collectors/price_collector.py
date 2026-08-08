"""
Price collector — refreshes token prices and stores OHLCV candles.
Runs every 15 seconds via Celery beat.
Sources: DexScreener (primary), Birdeye (fallback), Jupiter Price API.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from celery import shared_task

from app.collectors.base_collector import BaseCollector
from app.collectors.dexscreener_client import dexscreener_client
from app.collectors.birdeye_client import birdeye_client
from app.core.config import settings
from app.core.http_client import get_http_client, safe_get
from app.core.logging import get_logger
from app.core.task_runtime import run_async
from app.database.models.token import Token, TokenPriceHistory
from app.database.repositories.token_repository import TokenRepository

logger = get_logger(__name__)

JUPITER_PRICE_URL = "https://price.jup.ag/v4"


class PriceCollector(BaseCollector):
    """
    Refreshes current prices for all active tokens.
    Stores 5-minute OHLCV candles in the price_history table.
    Publishes price updates to Redis pub/sub for WebSocket streaming.
    """
    name = "price_collector"

    def __init__(self) -> None:
        super().__init__()
        self.jupiter_client = get_http_client(base_url=JUPITER_PRICE_URL, timeout=10)

    async def collect(self) -> dict:
        collected = 0
        errors = 0
        cache = self.get_cache("prices")

        # ── Step 1: Load active token mints from DB ─────────────────────────
        async with await self.get_db_session() as session:
            repo = TokenRepository(session)
            tokens = await repo.get_active_tokens(limit=500, min_liquidity=settings.MIN_LIQUIDITY_USD)
            mints = [t.mint_address for t in tokens]
            token_map: Dict[str, Token] = {t.mint_address: t for t in tokens}

        if not mints:
            return {"collected": 0, "errors": 0}

        self.logger.debug(f"Refreshing prices for {len(mints)} tokens")

        # ── Step 2: Batch fetch prices from Jupiter ─────────────────────────
        jupiter_prices = await self._fetch_jupiter_prices(mints)

        # ── Step 3: Fetch DexScreener data for top 50 tokens ────────────────
        dex_prices = await self._fetch_dexscreener_prices(
            list(token_map.keys())[:50]
        )

        # ── Step 4: Persist price updates ───────────────────────────────────
        async with await self.get_db_session() as session:
            repo = TokenRepository(session)
            now = datetime.now(timezone.utc)

            for mint, token in token_map.items():
                try:
                    # Resolve best price (DexScreener > Jupiter > existing)
                    dex_data = dex_prices.get(mint, {})
                    jup_price = jupiter_prices.get(mint)

                    price_usd = (
                        dex_data.get("price_usd")
                        or jup_price
                        or float(token.price_usd or 0)
                    )

                    update_data = {
                        "price_usd": Decimal(str(price_usd)) if price_usd else token.price_usd,
                        "last_updated_at": now,
                    }

                    # Include DexScreener market data if available
                    if dex_data:
                        update_data.update({
                            "volume_24h_usd": dex_data.get("volume_24h_usd"),
                            "volume_1h_usd": dex_data.get("volume_1h_usd"),
                            "volume_5m_usd": dex_data.get("volume_5m_usd"),
                            "liquidity_usd": dex_data.get("liquidity_usd"),
                            "price_change_5m": dex_data.get("price_change_5m"),
                            "price_change_1h": dex_data.get("price_change_1h"),
                            "price_change_24h": dex_data.get("price_change_24h"),
                            "buys_5m": dex_data.get("buys_5m"),
                            "sells_5m": dex_data.get("sells_5m"),
                            "buys_1h": dex_data.get("buys_1h"),
                            "sells_1h": dex_data.get("sells_1h"),
                        })

                    await repo.update(token, {k: v for k, v in update_data.items() if v is not None})

                    # Store 5m candle if we have price data
                    if price_usd and price_usd > 0:
                        candle = TokenPriceHistory(
                            token_id=token.id,
                            timestamp=now,
                            interval="5m",
                            open=token.price_usd or Decimal(str(price_usd)),
                            high=Decimal(str(price_usd)),
                            low=Decimal(str(price_usd)),
                            close=Decimal(str(price_usd)),
                            volume_usd=dex_data.get("volume_5m_usd"),
                            buys=dex_data.get("buys_5m"),
                            sells=dex_data.get("sells_5m"),
                        )
                        await repo.add_price_candle(candle)

                    collected += 1

                    # Publish to Redis for WebSocket streaming
                    await cache.publish("price_updates", {
                        "type": "price_update",
                        "mint": mint,
                        "symbol": token.symbol,
                        "price_usd": price_usd,
                        "price_change_5m": dex_data.get("price_change_5m"),
                        "price_change_1h": dex_data.get("price_change_1h"),
                        "volume_5m_usd": dex_data.get("volume_5m_usd"),
                        "timestamp": now.isoformat(),
                    })

                except Exception as e:
                    errors += 1
                    self.logger.warning("Price update failed", mint=mint[:8], error=str(e))

            await session.commit()

        return {"collected": collected, "errors": errors}

    async def _fetch_jupiter_prices(self, mints: List[str]) -> Dict[str, float]:
        """
        Batch fetch SOL-denominated prices from Jupiter Price API v4.
        Returns { mint_address: price_usd }
        Jupiter supports up to ~100 mints per request.
        """
        prices: Dict[str, float] = {}
        try:
            for i in range(0, len(mints), 100):
                batch = mints[i : i + 100]
                ids_param = ",".join(batch)
                data = await safe_get(
                    self.jupiter_client,
                    "/price",
                    params={"ids": ids_param, "vsToken": "USDC"},
                )
                if data and "data" in data:
                    for mint, price_data in data["data"].items():
                        if price_data and "price" in price_data:
                            prices[mint] = float(price_data["price"])
        except Exception as e:
            self.logger.warning("Jupiter price fetch failed", error=str(e))
        return prices

    async def _fetch_dexscreener_prices(
        self, mints: List[str]
    ) -> Dict[str, dict]:
        """
        Fetch market data for tokens from DexScreener.
        Returns { mint_address: normalized_pair_data }
        """
        result: Dict[str, dict] = {}
        try:
            for mint in mints[:50]:  # Limit to avoid rate limits
                pairs = await dexscreener_client.get_pairs_by_token(mint)
                if pairs:
                    # Use the most liquid pair
                    best = max(
                        pairs,
                        key=lambda p: float((p.get("liquidity") or {}).get("usd", 0) or 0),
                        default=None,
                    )
                    if best:
                        result[mint] = dexscreener_client.normalize_pair(best)
        except Exception as e:
            self.logger.warning("DexScreener price batch failed", error=str(e))
        return result


@shared_task(name="app.collectors.price_collector.collect_prices", bind=True)
def collect_prices(self) -> dict:
    """Celery task: refresh token prices."""
    return run_async(PriceCollector().run())
