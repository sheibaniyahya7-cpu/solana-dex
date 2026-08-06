"""
Holder collector — fetches token holder distribution data.
Used by the security engine to detect concentration risk.
Runs as part of the token security analysis flow.
"""

import asyncio
from typing import Dict, List, Optional

from app.collectors.birdeye_client import birdeye_client
from app.collectors.helius_client import helius_client
from app.collectors.solana_rpc_client import solana_client, TOKEN_PROGRAM_ID
from app.core.logging import get_logger

logger = get_logger(__name__)


class HolderCollector:
    """
    Fetches token holder data from Birdeye and Helius.
    Returns structured holder info for security analysis.
    """

    async def get_holder_data(self, mint_address: str) -> Dict:
        """
        Returns holder concentration data for a token.
        Tries Birdeye first (best data), then Helius.
        """
        # ── Birdeye ──────────────────────────────────────────────────────────
        birdeye_holders = await birdeye_client.get_token_holders(
            mint_address, limit=20
        )
        if birdeye_holders and isinstance(birdeye_holders, dict):
            return self._parse_birdeye_holders(birdeye_holders)

        # ── Helius fallback ───────────────────────────────────────────────────
        helius_holders = await helius_client.get_token_holders(mint_address, limit=20)
        if helius_holders:
            return self._parse_helius_holders(helius_holders)

        return {
            "holder_count": 0,
            "top_10_holder_pct": None,
            "top_holder_pct": None,
            "dev_wallet_pct": None,
            "holders": [],
        }

    def _parse_birdeye_holders(self, data: Dict) -> Dict:
        """Parse Birdeye holder response."""
        items = data.get("items", [])
        total_supply = float(data.get("total", 1) or 1)

        holders = []
        for item in items[:20]:
            amount = float(item.get("uiAmount", 0) or 0)
            pct = (amount / total_supply * 100) if total_supply > 0 else 0
            holders.append({
                "address": item.get("owner", ""),
                "amount": amount,
                "percentage": round(pct, 4),
            })

        top_10_pct = sum(h["percentage"] for h in holders[:10])
        top_holder_pct = holders[0]["percentage"] if holders else 0

        return {
            "holder_count": data.get("total", 0),
            "top_10_holder_pct": round(top_10_pct, 2),
            "top_holder_pct": round(top_holder_pct, 2),
            "dev_wallet_pct": None,  # Requires additional lookup
            "holders": holders,
        }

    def _parse_helius_holders(self, data: List) -> Dict:
        """Parse Helius holder response."""
        holders = []
        for item in data[:20]:
            holders.append({
                "address": item.get("owner", ""),
                "amount": float(item.get("amount", 0) or 0),
                "percentage": float(item.get("percentage", 0) or 0),
            })

        top_10_pct = sum(h["percentage"] for h in holders[:10])
        top_holder_pct = holders[0]["percentage"] if holders else 0

        return {
            "holder_count": len(holders),
            "top_10_holder_pct": round(top_10_pct, 2),
            "top_holder_pct": round(top_holder_pct, 2),
            "dev_wallet_pct": None,
            "holders": holders,
        }

    async def get_mint_authority_info(self, mint_address: str) -> Dict:
        """
        Checks whether mint authority and freeze authority are still active.
        Active mint authority = token can be inflated = security risk.
        """
        account_info = await solana_client.get_account_info(mint_address)
        if not account_info:
            return {
                "has_mint_authority": True,  # Assume worst case if can't fetch
                "has_freeze_authority": True,
                "is_mutable": True,
            }

        parsed = account_info.get("data", {}).get("parsed", {})
        info = parsed.get("info", {})

        mint_authority = info.get("mintAuthority")
        freeze_authority = info.get("freezeAuthority")

        return {
            "has_mint_authority": mint_authority is not None,
            "has_freeze_authority": freeze_authority is not None,
            "mint_authority_address": mint_authority,
            "freeze_authority_address": freeze_authority,
            "is_mutable": mint_authority is not None or freeze_authority is not None,
            "supply": info.get("supply"),
            "decimals": info.get("decimals"),
        }


# Module-level singleton
holder_collector = HolderCollector()
