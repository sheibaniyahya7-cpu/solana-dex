"""
Solana RPC client wrapper.
Handles JSON-RPC requests to Solana mainnet (or Helius).
All methods are async and retry on transient failures.
"""

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.http_client import get_http_client, safe_post
from app.core.logging import get_logger

logger = get_logger(__name__)

# Known DEX program IDs on Solana mainnet
RAYDIUM_AMM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
ORCA_WHIRLPOOL_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
METEORA_PROGRAM = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
JUPITER_PROGRAM = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"

# Token program addresses
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


class SolanaRPCClient:
    """
    Async Solana JSON-RPC client.
    Uses the Helius RPC endpoint when a key is configured,
    falls back to the public Solana mainnet RPC.
    """

    def __init__(self) -> None:
        self.rpc_url = settings.effective_rpc_url
        self.client = get_http_client(
            base_url=self.rpc_url,
            timeout=settings.SOLANA_RPC_TIMEOUT,
        )
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _rpc(
        self,
        method: str,
        params: Optional[List[Any]] = None,
    ) -> Optional[Any]:
        """Send a JSON-RPC request and return the result field."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or [],
        }
        try:
            response = await self.client.post("", json=payload)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                logger.warning(
                    "Solana RPC error",
                    method=method,
                    error=data["error"],
                )
                return None
            return data.get("result")
        except httpx.HTTPStatusError as e:
            logger.error("Solana RPC HTTP error", method=method, status=e.response.status_code)
            return None
        except Exception as e:
            logger.error("Solana RPC request failed", method=method, error=str(e))
            return None

    # ─── Account / Token Methods ──────────────────────────────────────────────

    async def get_token_supply(self, mint_address: str) -> Optional[Dict]:
        """Returns token supply info for a mint address."""
        result = await self._rpc("getTokenSupply", [mint_address])
        if result:
            return result.get("value")
        return None

    async def get_account_info(
        self, address: str, encoding: str = "jsonParsed"
    ) -> Optional[Dict]:
        result = await self._rpc(
            "getAccountInfo",
            [address, {"encoding": encoding, "commitment": "confirmed"}],
        )
        if result:
            return result.get("value")
        return None

    async def get_token_accounts_by_owner(
        self, owner_address: str, limit: int = 100
    ) -> List[Dict]:
        """Returns all SPL token accounts owned by a wallet."""
        result = await self._rpc(
            "getTokenAccountsByOwner",
            [
                owner_address,
                {"programId": TOKEN_PROGRAM_ID},
                {
                    "encoding": "jsonParsed",
                    "commitment": "confirmed",
                    "dataSlice": {"offset": 0, "length": 0},
                },
            ],
        )
        if result:
            return result.get("value", [])
        return []

    async def get_sol_balance(self, address: str) -> float:
        """Returns SOL balance in lamports, converted to SOL."""
        result = await self._rpc(
            "getBalance",
            [address, {"commitment": "confirmed"}],
        )
        if result is not None:
            lamports = result.get("value", 0)
            return lamports / 1_000_000_000  # Convert lamports to SOL
        return 0.0

    async def get_signatures_for_address(
        self,
        address: str,
        limit: int = 100,
        before: Optional[str] = None,
        until: Optional[str] = None,
    ) -> List[Dict]:
        """Returns transaction signatures for an address."""
        params: Dict[str, Any] = {
            "limit": min(limit, 1000),
            "commitment": "confirmed",
        }
        if before:
            params["before"] = before
        if until:
            params["until"] = until

        result = await self._rpc("getSignaturesForAddress", [address, params])
        return result or []

    async def get_transaction(
        self, signature: str, max_supported_version: int = 0
    ) -> Optional[Dict]:
        """Returns a parsed transaction by signature."""
        result = await self._rpc(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "commitment": "confirmed",
                    "maxSupportedTransactionVersion": max_supported_version,
                },
            ],
        )
        return result

    async def get_multiple_accounts(self, addresses: List[str]) -> List[Optional[Dict]]:
        """Batch fetch up to 100 account infos in one RPC call."""
        if not addresses:
            return []
        result = await self._rpc(
            "getMultipleAccounts",
            [addresses, {"encoding": "jsonParsed", "commitment": "confirmed"}],
        )
        if result:
            return result.get("value", [])
        return []

    async def get_program_accounts(
        self,
        program_id: str,
        filters: Optional[List[Dict]] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Returns all accounts owned by a program (e.g., all Raydium pools)."""
        params: Dict[str, Any] = {
            "encoding": "jsonParsed",
            "commitment": "confirmed",
            "dataSlice": {"offset": 0, "length": 0},
        }
        if filters:
            params["filters"] = filters

        result = await self._rpc("getProgramAccounts", [program_id, params])
        return result or []

    async def get_latest_blockhash(self) -> Optional[str]:
        result = await self._rpc("getLatestBlockhash", [{"commitment": "confirmed"}])
        if result:
            return result.get("value", {}).get("blockhash")
        return None

    async def get_slot(self) -> Optional[int]:
        return await self._rpc("getSlot", [{"commitment": "confirmed"}])


# Module-level singleton
solana_client = SolanaRPCClient()
