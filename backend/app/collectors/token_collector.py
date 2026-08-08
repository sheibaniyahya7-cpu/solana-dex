"""
Token collector — discovers and updates Solana tokens.
Sources: DexScreener new pairs, Birdeye new listings, Helius token metadata.

Celery task: collect_new_tokens (runs every 60 seconds)
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional

from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base_collector import BaseCollector
from app.collectors.dexscreener_client import dexscreener_client
from app.collectors.birdeye_client import birdeye_client
from app.collectors.helius_client import helius_client
from app.core.config import settings
from app.core.logging import get_logger
from app.core.task_runtime import run_async
from app.database.models.token import Token
from app.database.repositories.token_repository import TokenRepository

logger = get_logger(__name__)


class TokenCollector(BaseCollector):
    """
    Discovers new Solana tokens from multiple sources and stores them.
    Updates market data for tokens already in the database.
    """
    name = "token_collector"

    async def collect(self) -> dict:
        collected = 0
        updated = 0
        errors = 0

        # ── Step 1: Discover new tokens ─────────────────────────────────────
        new_pairs = await self._fetch_new_pairs()
        birdeye_new = await self._fetch_birdeye_new_listings()

        # Merge sources — deduplicate by mint address
        all_mints: Dict[str, dict] = {}
        for pair_data in new_pairs:
            mint = pair_data.get("mint_address")
            if mint:
                all_mints[mint] = pair_data

        for token_data in birdeye_new:
            mint = token_data.get("address")
            if mint and mint not in all_mints:
                all_mints[mint] = {"mint_address": mint, **token_data}

        self.logger.info(f"Found {len(all_mints)} tokens to process")

        # ── Step 2: Persist to database ──────────────────────────────────────
        async with await self.get_db_session() as session:
            repo = TokenRepository(session)
            for mint, data in all_mints.items():
                try:
                    token, created = await repo.get_or_create(
                        mint_address=mint,
                        defaults=self._build_token_defaults(data),
                    )
                    if created:
                        token.first_seen_at = datetime.now(timezone.utc)
                        collected += 1
                        self.logger.info("New token discovered", mint=mint[:8], symbol=token.symbol)
                    else:
                        # Update market data for existing token
                        await self._update_market_data(repo, token, data)
                        updated += 1
                except Exception as e:
                    errors += 1
                    self.logger.error("Token persist failed", mint=mint[:8], error=str(e))

            await session.commit()

        return {"collected": collected, "updated": updated, "errors": errors}

    async def _fetch_new_pairs(self) -> List[Dict]:
        """Fetch new token pairs from DexScreener."""
        try:
            pairs = await dexscreener_client.get_new_pairs("solana")
            normalized = []
            for pair in pairs:
                norm = dexscreener_client.normalize_pair(pair)
                # Only accept tokens with at least some liquidity
                if norm.get("liquidity_usd", 0) >= settings.MIN_LIQUIDITY_USD:
                    normalized.append(norm)
            self.logger.debug("DexScreener new pairs fetched", count=len(normalized))
            return normalized
        except Exception as e:
            self.logger.error("DexScreener fetch failed", error=str(e))
            return []

    async def _fetch_birdeye_new_listings(self) -> List[Dict]:
        """Fetch new token listings from Birdeye."""
        try:
            listings = await birdeye_client.get_new_listings(limit=50)
            self.logger.debug("Birdeye new listings fetched", count=len(listings))
            return listings
        except Exception as e:
            self.logger.error("Birdeye new listings fetch failed", error=str(e))
            return []

    def _build_token_defaults(self, data: dict) -> dict:
        """Map collected data to Token model fields."""
        return {
            "symbol": data.get("symbol"),
            "name": data.get("name"),
            "logo_uri": data.get("logoURI") or data.get("logo_uri"),
            "price_usd": data.get("price_usd") or data.get("price"),
            "volume_24h_usd": data.get("volume_24h_usd") or data.get("v24hUSD"),
            "volume_1h_usd": data.get("volume_1h_usd"),
            "volume_5m_usd": data.get("volume_5m_usd"),
            "liquidity_usd": data.get("liquidity_usd") or data.get("liquidity"),
            "price_change_5m": data.get("price_change_5m"),
            "price_change_1h": data.get("price_change_1h"),
            "price_change_6h": data.get("price_change_6h"),
            "price_change_24h": data.get("price_change_24h"),
            "buys_5m": data.get("buys_5m"),
            "sells_5m": data.get("sells_5m"),
            "buys_1h": data.get("buys_1h"),
            "sells_1h": data.get("sells_1h"),
            "tx_count_24h": data.get("tx_count_24h"),
            "pair_address": data.get("pair_address"),
            "dex_id": data.get("dex_id"),
            "quote_token_address": data.get("quote_token_address"),
            "website": data.get("website"),
            "is_active": True,
            "last_updated_at": datetime.now(timezone.utc),
        }

    async def _update_market_data(
        self,
        repo: TokenRepository,
        token: Token,
        data: dict,
    ) -> None:
        """Update price/volume/liquidity for an existing token."""
        update_fields = {
            "price_usd": data.get("price_usd") or data.get("price") or token.price_usd,
            "volume_24h_usd": data.get("volume_24h_usd") or token.volume_24h_usd,
            "volume_1h_usd": data.get("volume_1h_usd") or token.volume_1h_usd,
            "volume_5m_usd": data.get("volume_5m_usd") or token.volume_5m_usd,
            "liquidity_usd": data.get("liquidity_usd") or token.liquidity_usd,
            "price_change_5m": data.get("price_change_5m", token.price_change_5m),
            "price_change_1h": data.get("price_change_1h", token.price_change_1h),
            "price_change_6h": data.get("price_change_6h", token.price_change_6h),
            "price_change_24h": data.get("price_change_24h", token.price_change_24h),
            "buys_5m": data.get("buys_5m", token.buys_5m),
            "sells_5m": data.get("sells_5m", token.sells_5m),
            "buys_1h": data.get("buys_1h", token.buys_1h),
            "sells_1h": data.get("sells_1h", token.sells_1h),
            "last_updated_at": datetime.now(timezone.utc),
        }
        await repo.update(token, update_fields)


# ─── Celery task wrappers ─────────────────────────────────────────────────────

@shared_task(name="app.collectors.token_collector.collect_new_tokens", bind=True)
def collect_new_tokens(self) -> dict:
    """Celery task: discover and update tokens from all sources."""
    return run_async(TokenCollector().run())
