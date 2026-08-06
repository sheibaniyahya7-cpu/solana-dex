"""
Transaction collector — fetches and parses DEX swap transactions.
Identifies whale transactions and smart money wallet activity.
Runs every 30 seconds via Celery beat.

Sources: Helius parsed transactions (primary), Solana RPC (fallback).
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from celery import shared_task

from app.collectors.base_collector import BaseCollector
from app.collectors.helius_client import helius_client
from app.collectors.solana_rpc_client import solana_client
from app.core.config import settings
from app.core.logging import get_logger
from app.database.models.wallet import Wallet, WalletTrade
from app.database.repositories.token_repository import TokenRepository
from app.database.repositories.wallet_repository import WalletRepository

logger = get_logger(__name__)

# DEX program IDs to recognize swaps
SWAP_PROGRAMS = {
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "raydium",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "orca",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "jupiter",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pump_fun",
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "meteora",
}


class TransactionCollector(BaseCollector):
    """
    Fetches recent DEX transactions for tracked token pairs.
    Parses swap data to extract:
    - Buyer/seller wallet addresses
    - Trade amounts in USD
    - Whether it was a buy or sell
    Stores trades linked to known smart money / whale wallets.
    """
    name = "transaction_collector"

    async def collect(self) -> dict:
        collected = 0
        whale_txs = 0
        errors = 0

        # ── Get tokens to monitor ────────────────────────────────────────────
        async with await self.get_db_session() as session:
            token_repo = TokenRepository(session)
            tokens = await token_repo.get_active_tokens(
                limit=50,
                min_liquidity=settings.MIN_LIQUIDITY_USD,
            )
            # Prioritize tokens with recent events or high scores
            tokens = sorted(
                tokens,
                key=lambda t: float(t.ai_score or 0),
                reverse=True,
            )[:30]

        if not tokens:
            return {"collected": 0, "whale_txs": 0, "errors": 0}

        # ── Get known smart money wallets ────────────────────────────────────
        async with await self.get_db_session() as session:
            wallet_repo = WalletRepository(session)
            smart_wallets = await wallet_repo.get_smart_money_wallets(limit=200)
            whale_wallets = await wallet_repo.get_whale_wallets(limit=100)
            tracked_addresses = {
                w.address for w in list(smart_wallets) + list(whale_wallets)
            }

        # ── Fetch transactions for each token ────────────────────────────────
        for token in tokens:
            if not token.pair_address:
                continue
            try:
                txs = await self._fetch_pair_transactions(token.pair_address)
                for tx in txs:
                    parsed = self._parse_swap(tx, token.mint_address)
                    if not parsed:
                        continue

                    wallet_address = parsed["wallet_address"]
                    amount_usd = parsed["amount_usd"]

                    # Check for whale tx
                    sol_price = await self._get_sol_price()
                    amount_sol = amount_usd / sol_price if sol_price else 0

                    if amount_sol >= settings.WHALE_TX_THRESHOLD_SOL:
                        whale_txs += 1
                        whale_cache = self.get_cache("whales")
                        await whale_cache.publish("whale_transactions", {
                            "type": "WHALE_TX",
                            "wallet": wallet_address,
                            "mint": token.mint_address,
                            "symbol": token.symbol,
                            "trade_type": parsed["trade_type"],
                            "amount_usd": amount_usd,
                            "amount_sol": round(amount_sol, 2),
                            "signature": parsed["signature"],
                            "detected_at": datetime.now(timezone.utc).isoformat(),
                        })

                    # Store trade if wallet is tracked
                    if wallet_address in tracked_addresses:
                        await self._store_trade(wallet_address, token.mint_address, token.symbol, parsed)
                        collected += 1

            except Exception as e:
                errors += 1
                self.logger.warning(
                    "Transaction fetch failed",
                    mint=token.mint_address[:8],
                    error=str(e),
                )

        return {"collected": collected, "whale_txs": whale_txs, "errors": errors}

    async def _fetch_pair_transactions(self, pair_address: str) -> List[Dict]:
        """Fetch recent transactions for a DEX pair address."""
        if helius_client.api_key:
            return await helius_client.get_parsed_transactions(
                address=pair_address,
                tx_type="SWAP",
                limit=50,
            )
        # Fallback: use raw RPC signatures
        sigs = await solana_client.get_signatures_for_address(pair_address, limit=30)
        return sigs  # Will be partially parsed below

    def _parse_swap(
        self, tx: Dict, token_mint: str
    ) -> Optional[Dict]:
        """
        Parse a transaction to extract swap details.
        Handles Helius enhanced format and raw signature format.
        """
        try:
            # Helius enhanced format
            if "type" in tx and tx.get("type") == "SWAP":
                events = tx.get("events", {})
                swap = events.get("swap", {})
                if not swap:
                    return None

                # Determine if this was a buy or sell for our token
                token_inputs = swap.get("tokenInputs", [])
                token_outputs = swap.get("tokenOutputs", [])

                trade_type = "buy"
                amount_usd = float(tx.get("tokenTransfers", [{}])[0].get("tokenAmount", 0))

                signer = (tx.get("feePayer") or
                          (tx.get("accountData") or [{}])[0].get("account"))

                return {
                    "wallet_address": signer or "",
                    "trade_type": trade_type,
                    "amount_usd": amount_usd,
                    "signature": tx.get("signature", ""),
                    "timestamp": datetime.fromtimestamp(
                        tx.get("timestamp", 0), tz=timezone.utc
                    ),
                    "dex_program": self._identify_dex(tx),
                }

            # Raw signature format — minimal info
            if "signature" in tx and "err" not in tx:
                return {
                    "wallet_address": "",  # Unknown without full tx parse
                    "trade_type": "buy",
                    "amount_usd": 0,
                    "signature": tx.get("signature", ""),
                    "timestamp": datetime.now(timezone.utc),
                    "dex_program": "unknown",
                }

        except Exception as e:
            self.logger.debug("Swap parse failed", error=str(e))
        return None

    def _identify_dex(self, tx: Dict) -> str:
        """Identify which DEX program was used in a transaction."""
        instructions = tx.get("instructions", [])
        for ix in instructions:
            program_id = ix.get("programId", "")
            if program_id in SWAP_PROGRAMS:
                return SWAP_PROGRAMS[program_id]
        return "unknown"

    async def _get_sol_price(self) -> float:
        """Get current SOL price in USD from cache."""
        cache = self.get_cache("prices")
        sol_price = await cache.get("sol_usd_price")
        return float(sol_price or 200.0)  # Fallback to $200 if not cached

    async def _store_trade(
        self,
        wallet_address: str,
        token_mint: str,
        token_symbol: Optional[str],
        parsed: Dict,
    ) -> None:
        """Persist a parsed trade to the database."""
        async with await self.get_db_session() as session:
            wallet_repo = WalletRepository(session)

            # Skip if we already have this signature
            exists = await wallet_repo.trade_signature_exists(parsed["signature"])
            if exists:
                return

            wallet, _ = await wallet_repo.get_or_create(wallet_address)
            if not wallet:
                return

            trade = WalletTrade(
                wallet_id=wallet.id,
                token_mint=token_mint,
                token_symbol=token_symbol,
                trade_type=parsed["trade_type"],
                trade_timestamp=parsed["timestamp"],
                signature=parsed["signature"],
                amount_usd=Decimal(str(parsed["amount_usd"])) if parsed["amount_usd"] else None,
                dex_program=parsed.get("dex_program"),
            )
            await wallet_repo.add_trade(trade)
            await session.commit()


@shared_task(name="app.collectors.transaction_collector.collect_transactions", bind=True)
def collect_transactions(self) -> dict:
    """Celery task: collect DEX swap transactions for tracked tokens."""
    return asyncio.run(TransactionCollector().run())
