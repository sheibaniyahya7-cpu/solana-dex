"""
DexScreener API client.
Provides real-time DEX pair data: prices, volume, liquidity, OHLCV.
No API key required for public endpoints.

Docs: https://docs.dexscreener.com/api/reference
"""

from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.http_client import get_http_client, safe_get
from app.core.logging import get_logger

logger = get_logger(__name__)

DEXSCREENER_BASE = "https://api.dexscreener.com/latest"


class DexScreenerClient:
    """
    DexScreener REST API client — no authentication required.
    Rate limit: ~300 requests/minute on the free tier.
    """

    def __init__(self) -> None:
        self.client = get_http_client(
            base_url=DEXSCREENER_BASE,
            timeout=15,
        )

    # ─── Token / Pair Lookups ─────────────────────────────────────────────────

    async def get_pairs_by_token(self, token_address: str) -> List[Dict]:
        """
        Returns all DEX pairs for a given token address on Solana.
        Includes price, volume, liquidity, and 24h stats.
        """
        data = await safe_get(
            self.client,
            f"/dex/tokens/{token_address}",
        )
        if data:
            return data.get("pairs", [])
        return []

    async def get_pair(self, pair_address: str) -> Optional[Dict]:
        """Returns data for a specific pair address."""
        data = await safe_get(
            self.client,
            f"/dex/pairs/solana/{pair_address}",
        )
        if data:
            pairs = data.get("pairs", [])
            return pairs[0] if pairs else None
        return None

    async def get_pairs_bulk(self, pair_addresses: List[str]) -> List[Dict]:
        """
        Batch fetch up to 30 pairs in one request.
        Splits into chunks if more than 30 addresses are provided.
        """
        results = []
        for i in range(0, len(pair_addresses), 30):
            batch = pair_addresses[i : i + 30]
            addresses_str = ",".join(batch)
            data = await safe_get(
                self.client,
                f"/dex/pairs/solana/{addresses_str}",
            )
            if data:
                results.extend(data.get("pairs", []))
        return results

    async def search_pairs(self, query: str) -> List[Dict]:
        """Search DEX pairs by token name, symbol, or address."""
        data = await safe_get(
            self.client,
            f"/dex/search",
            params={"q": query},
        )
        if data:
            return data.get("pairs", [])
        return []

    async def get_new_pairs(self, chain: str = "solana") -> List[Dict]:
        """
        Returns recently created pairs on a chain.
        This endpoint gives us newly launched tokens.
        """
        data = await safe_get(
            self.client,
            f"/dex/tokens/new/{chain}",
        )
        if data:
            return data.get("pairs", [])
        return []

    # ─── Data Normalization ───────────────────────────────────────────────────

    @staticmethod
    def normalize_pair(pair: Dict) -> Dict:
        """
        Normalize a DexScreener pair response into our internal format.
        Maps DexScreener field names to our token model fields.
        """
        base_token = pair.get("baseToken", {})
        quote_token = pair.get("quoteToken", {})
        price_change = pair.get("priceChange", {})
        volume = pair.get("volume", {})
        txns = pair.get("txns", {})

        return {
            "mint_address": base_token.get("address", ""),
            "symbol": base_token.get("symbol"),
            "name": base_token.get("name"),
            "pair_address": pair.get("pairAddress"),
            "dex_id": pair.get("dexId"),
            "quote_token_address": quote_token.get("address"),
            # Prices
            "price_usd": float(pair.get("priceUsd", 0) or 0),
            "price_native": float(pair.get("priceNative", 0) or 0),
            # Market
            "market_cap_usd": float((pair.get("marketCap") or pair.get("fdv") or 0)),
            "fully_diluted_value": float(pair.get("fdv") or 0),
            # Liquidity
            "liquidity_usd": float((pair.get("liquidity") or {}).get("usd", 0) or 0),
            # Volume (24h, 1h, 5m)
            "volume_24h_usd": float(volume.get("h24", 0) or 0),
            "volume_1h_usd": float(volume.get("h1", 0) or 0),
            "volume_5m_usd": float(volume.get("m5", 0) or 0),
            # Price changes
            "price_change_5m": float(price_change.get("m5", 0) or 0),
            "price_change_1h": float(price_change.get("h1", 0) or 0),
            "price_change_6h": float(price_change.get("h6", 0) or 0),
            "price_change_24h": float(price_change.get("h24", 0) or 0),
            # Transactions
            "buys_5m": int((txns.get("m5") or {}).get("buys", 0) or 0),
            "sells_5m": int((txns.get("m5") or {}).get("sells", 0) or 0),
            "buys_1h": int((txns.get("h1") or {}).get("buys", 0) or 0),
            "sells_1h": int((txns.get("h1") or {}).get("sells", 0) or 0),
            "tx_count_24h": int(
                (txns.get("h24") or {}).get("buys", 0) or 0
            ) + int((txns.get("h24") or {}).get("sells", 0) or 0),
            # URLs
            "website": (pair.get("info") or {}).get("websites", [None])[0]
            if (pair.get("info") or {}).get("websites") else None,
            # Pair creation time
            "pair_created_at": pair.get("pairCreatedAt"),
        }


# Module-level singleton
dexscreener_client = DexScreenerClient()
