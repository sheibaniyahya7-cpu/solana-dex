"""
Helius API client.
Helius provides enriched Solana data: parsed transactions, token metadata,
NFT data, webhook subscriptions, and enhanced RPC.

Docs: https://docs.helius.dev/
"""

from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.http_client import get_http_client, safe_get, safe_post
from app.core.logging import get_logger

logger = get_logger(__name__)


class HeliusClient:
    """
    Async Helius REST API client.
    Rate-limited to Helius plan limits (varies by tier).
    """

    def __init__(self) -> None:
        if not settings.HELIUS_API_KEY:
            logger.warning("Helius API key not configured — using limited public RPC")

        self.api_key = settings.HELIUS_API_KEY
        self.base_url = settings.HELIUS_BASE_URL

        self.client = get_http_client(
            base_url=self.base_url,
            timeout=30,
            headers={"Content-Type": "application/json"},
        )

    def _params(self, extra: Optional[Dict] = None) -> Dict:
        """Inject API key into query params."""
        params = {"api-key": self.api_key}
        if extra:
            params.update(extra)
        return params

    # ─── Token Metadata ───────────────────────────────────────────────────────

    async def get_token_metadata(self, mint_address: str) -> Optional[Dict]:
        """
        Fetch rich token metadata including name, symbol, logo, social links.
        Uses the Helius DAS (Digital Asset Standard) API.
        """
        if not self.api_key:
            return None
        result = await safe_post(
            self.client,
            f"/token-metadata",
            json_body={"mintAccounts": [mint_address], "includeOffChain": True},
            headers={"api-key": self.api_key},
        )
        if result and len(result) > 0:
            return result[0]
        return None

    async def get_tokens_metadata_batch(
        self, mint_addresses: List[str]
    ) -> List[Dict]:
        """Batch fetch metadata for up to 100 mints."""
        if not self.api_key or not mint_addresses:
            return []
        # Helius supports batches of up to 100
        results = []
        for i in range(0, len(mint_addresses), 100):
            batch = mint_addresses[i : i + 100]
            data = await safe_post(
                self.client,
                "/token-metadata",
                json_body={"mintAccounts": batch, "includeOffChain": True},
                headers={"api-key": self.api_key},
            )
            if data:
                results.extend(data)
        return results

    # ─── Parsed Transactions ──────────────────────────────────────────────────

    async def get_parsed_transactions(
        self,
        address: str,
        tx_type: str = "SWAP",
        limit: int = 100,
        before: Optional[str] = None,
    ) -> List[Dict]:
        """
        Returns enriched/parsed transaction history for an address.
        tx_type: SWAP | TRANSFER | NFT_SALE | etc.
        """
        if not self.api_key:
            return []
        params: Dict[str, Any] = {"limit": min(limit, 100), "type": tx_type}
        if before:
            params["before"] = before

        data = await safe_get(
            self.client,
            f"/addresses/{address}/transactions",
            params=self._params(params),
        )
        return data or []

    async def get_transaction_history(
        self,
        address: str,
        limit: int = 100,
        before: Optional[str] = None,
    ) -> List[Dict]:
        """Full transaction history — all types."""
        if not self.api_key:
            return []
        params: Dict[str, Any] = {"limit": min(limit, 100)}
        if before:
            params["before"] = before

        data = await safe_get(
            self.client,
            f"/addresses/{address}/transactions",
            params=self._params(params),
        )
        return data or []

    # ─── Holders ──────────────────────────────────────────────────────────────

    async def get_token_holders(
        self, mint_address: str, limit: int = 20
    ) -> List[Dict]:
        """
        Returns top token holders.
        Note: Full holder list requires Helius Advanced plan.
        """
        if not self.api_key:
            return []
        data = await safe_get(
            self.client,
            f"/token/{mint_address}/holders",
            params=self._params({"limit": limit}),
        )
        return data or []

    # ─── DAS (Digital Asset Standard) API ────────────────────────────────────

    async def get_asset(self, asset_id: str) -> Optional[Dict]:
        """Get asset (token/NFT) via DAS API."""
        if not self.api_key:
            return None
        data = await safe_post(
            self.client,
            "/das/getAsset",
            json_body={"id": asset_id},
            headers={"api-key": self.api_key},
        )
        return data

    async def search_assets(
        self,
        owner_address: Optional[str] = None,
        token_type: str = "fungible",
        limit: int = 100,
    ) -> List[Dict]:
        """Search assets — useful for finding all tokens held by a wallet."""
        if not self.api_key:
            return []
        body: Dict[str, Any] = {
            "tokenType": token_type,
            "limit": limit,
            "displayOptions": {
                "showFungible": True,
                "showNativeBalance": True,
            },
        }
        if owner_address:
            body["ownerAddress"] = owner_address

        data = await safe_post(
            self.client,
            "/das/searchAssets",
            json_body=body,
            headers={"api-key": self.api_key},
        )
        if data:
            return data.get("items", [])
        return []

    # ─── Webhook Management ───────────────────────────────────────────────────

    async def create_webhook(
        self,
        webhook_url: str,
        addresses: List[str],
        transaction_types: List[str] = ["SWAP"],
    ) -> Optional[Dict]:
        """Register a Helius webhook to receive real-time transaction events."""
        if not self.api_key:
            return None
        data = await safe_post(
            self.client,
            "/webhooks",
            json_body={
                "webhookURL": webhook_url,
                "transactionTypes": transaction_types,
                "accountAddresses": addresses,
                "webhookType": "enhanced",
            },
            headers={"api-key": self.api_key},
        )
        return data


# Module-level singleton
helius_client = HeliusClient()
