"""
Birdeye API client.
Birdeye specializes in Solana token analytics: OHLCV, holder data,
token security checks, and wallet analytics.

Docs: https://docs.birdeye.so/
"""

from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.http_client import get_http_client, safe_get
from app.core.logging import get_logger

logger = get_logger(__name__)


class BirdeyeClient:
    """
    Birdeye REST API client.
    Requires a valid API key set via BIRDEYE_API_KEY env var.
    Rate limit: 100 req/min on starter plan.
    """

    def __init__(self) -> None:
        if not settings.BIRDEYE_API_KEY:
            logger.warning("Birdeye API key not configured")

        self.api_key = settings.BIRDEYE_API_KEY
        self.client = get_http_client(
            base_url=settings.BIRDEYE_BASE_URL,
            timeout=20,
            headers={
                "X-API-KEY": self.api_key,
                "x-chain": "solana",
            },
        )

    def _headers(self) -> Dict[str, str]:
        return {"X-API-KEY": self.api_key, "x-chain": "solana"}

    # ─── Token Data ───────────────────────────────────────────────────────────

    async def get_token_overview(self, token_address: str) -> Optional[Dict]:
        """
        Comprehensive token overview: price, volume, liquidity,
        market cap, price changes across all timeframes.
        """
        if not self.api_key:
            return None
        data = await safe_get(
            self.client,
            "/defi/token_overview",
            params={"address": token_address},
            headers=self._headers(),
        )
        return data.get("data") if data and data.get("success") else None

    async def get_token_security(self, token_address: str) -> Optional[Dict]:
        """
        Token security analysis: mint authority, freeze authority,
        holder concentration, top holder data.
        Critical for rug pull detection.
        """
        if not self.api_key:
            return None
        data = await safe_get(
            self.client,
            "/defi/token_security",
            params={"address": token_address},
            headers=self._headers(),
        )
        return data.get("data") if data and data.get("success") else None

    async def get_token_creation_info(self, token_address: str) -> Optional[Dict]:
        """Returns token creation timestamp and deployer wallet."""
        if not self.api_key:
            return None
        data = await safe_get(
            self.client,
            "/defi/token_creation_info",
            params={"address": token_address},
            headers=self._headers(),
        )
        return data.get("data") if data and data.get("success") else None

    # ─── OHLCV ────────────────────────────────────────────────────────────────

    async def get_ohlcv(
        self,
        token_address: str,
        resolution: str = "5m",
        time_from: Optional[int] = None,
        time_to: Optional[int] = None,
        limit: int = 200,
    ) -> List[Dict]:
        """
        OHLCV candlestick data for a token.
        resolution: 1m | 3m | 5m | 15m | 30m | 1H | 2H | 4H | 6H | 8H | 12H | 1D | 3D | 1W | 1M
        """
        if not self.api_key:
            return []
        import time as _time
        params: Dict[str, Any] = {
            "address": token_address,
            "type": resolution,
        }
        if time_from:
            params["time_from"] = time_from
        else:
            params["time_from"] = int(_time.time()) - (limit * _interval_seconds(resolution))
        if time_to:
            params["time_to"] = time_to
        else:
            params["time_to"] = int(_time.time())

        data = await safe_get(
            self.client,
            "/defi/ohlcv",
            params=params,
            headers=self._headers(),
        )
        if data and data.get("success"):
            return data.get("data", {}).get("items", [])
        return []

    # ─── Holders ──────────────────────────────────────────────────────────────

    async def get_token_holders(
        self,
        token_address: str,
        offset: int = 0,
        limit: int = 20,
    ) -> Optional[Dict]:
        """
        Returns top token holders with their addresses and percentages.
        Key for detecting holder concentration risk.
        """
        if not self.api_key:
            return None
        data = await safe_get(
            self.client,
            "/defi/v3/token/holder",
            params={"address": token_address, "offset": offset, "limit": limit},
            headers=self._headers(),
        )
        return data.get("data") if data and data.get("success") else None

    # ─── Trades ───────────────────────────────────────────────────────────────

    async def get_token_trades(
        self,
        token_address: str,
        limit: int = 50,
        tx_type: str = "swap",
    ) -> List[Dict]:
        """Recent trades for a token — used for buy/sell pressure analysis."""
        if not self.api_key:
            return []
        data = await safe_get(
            self.client,
            "/defi/txs/token",
            params={"address": token_address, "limit": limit, "tx_type": tx_type},
            headers=self._headers(),
        )
        if data and data.get("success"):
            return data.get("data", {}).get("items", [])
        return []

    # ─── Wallet Analytics ─────────────────────────────────────────────────────

    async def get_wallet_portfolio(self, wallet_address: str) -> Optional[Dict]:
        """Returns wallet's current token portfolio with values."""
        if not self.api_key:
            return None
        data = await safe_get(
            self.client,
            "/v1/wallet/token_list",
            params={"wallet": wallet_address},
            headers=self._headers(),
        )
        return data.get("data") if data and data.get("success") else None

    async def get_wallet_trades(
        self,
        wallet_address: str,
        limit: int = 100,
        tx_type: str = "swap",
    ) -> List[Dict]:
        """Returns recent swap transactions for a wallet."""
        if not self.api_key:
            return []
        data = await safe_get(
            self.client,
            "/defi/txs/wallet",
            params={"wallet": wallet_address, "limit": limit, "tx_type": tx_type},
            headers=self._headers(),
        )
        if data and data.get("success"):
            return data.get("data", {}).get("items", [])
        return []

    # ─── Token List ───────────────────────────────────────────────────────────

    async def get_token_list(
        self,
        sort_by: str = "v24hUSD",
        sort_type: str = "desc",
        offset: int = 0,
        limit: int = 50,
        min_liquidity: float = 1000,
    ) -> List[Dict]:
        """
        Returns a ranked list of tokens on Solana.
        sort_by: v24hUSD (volume) | mc (market cap) | v24hChangePercent
        """
        if not self.api_key:
            return []
        data = await safe_get(
            self.client,
            "/defi/tokenlist",
            params={
                "sort_by": sort_by,
                "sort_type": sort_type,
                "offset": offset,
                "limit": limit,
                "min_liquidity": min_liquidity,
            },
            headers=self._headers(),
        )
        if data and data.get("success"):
            return data.get("data", {}).get("tokens", [])
        return []

    async def get_new_listings(self, limit: int = 50) -> List[Dict]:
        """Returns the most recently listed tokens on Solana DEXes."""
        if not self.api_key:
            return []
        data = await safe_get(
            self.client,
            "/defi/v2/tokens/new_listing",
            params={"limit": limit, "time_to": int(__import__("time").time())},
            headers=self._headers(),
        )
        if data and data.get("success"):
            return data.get("data", {}).get("items", [])
        return []


def _interval_seconds(resolution: str) -> int:
    """Convert Birdeye resolution string to seconds."""
    mapping = {
        "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
        "1H": 3600, "2H": 7200, "4H": 14400, "6H": 21600,
        "8H": 28800, "12H": 43200, "1D": 86400,
    }
    return mapping.get(resolution, 300)


# Module-level singleton
birdeye_client = BirdeyeClient()
