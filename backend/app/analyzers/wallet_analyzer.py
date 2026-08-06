"""
Wallet Intelligence System.
Analyzes on-chain trading history to classify wallets and compute performance metrics.

Runs every 5 minutes via Celery beat.
Called on-demand when new wallets are discovered via transaction collector.

Classifications:
  smart_money  — high win rate (>65%), early entry timing, consistent profits
  whale        — large portfolio value (>$100K) or large individual trades (>500 SOL)
  insider      — enters tokens hours before public pumps (suspicious timing)
  retail       — typical retail trader patterns
"""

import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from celery import shared_task

from app.core.config import settings
from app.core.logging import get_logger
from app.collectors.birdeye_client import birdeye_client
from app.collectors.helius_client import helius_client
from app.collectors.solana_rpc_client import solana_client
from app.database.base import get_session_factory
from app.database.models.wallet import Wallet, WalletTrade, WalletHolding
from app.database.repositories.wallet_repository import WalletRepository
from app.database.repositories.token_repository import TokenRepository

logger = get_logger(__name__)

# Insider detection: if wallet buys < N hours before a pump, flag as potential insider
INSIDER_LEAD_HOURS = 2
# Min portfolio value to be considered a whale
WHALE_PORTFOLIO_THRESHOLD_USD = 100_000
# Min individual trade to be considered whale behavior
WHALE_TRADE_THRESHOLD_USD = 50_000


class WalletAnalyzer:
    """
    Full wallet intelligence pipeline:
    1. Fetch wallet's recent trade history (Helius + Birdeye)
    2. Calculate PnL, win rate, timing scores
    3. Classify wallet type
    4. Compute wallet score (0-100)
    5. Update database record
    """

    def __init__(self) -> None:
        self.session_factory = get_session_factory()

    async def run(self) -> dict:
        """Analyze all tracked wallets that haven't been updated in 6+ hours."""
        analyzed = 0
        errors = 0

        async with self.session_factory() as session:
            repo = WalletRepository(session)
            wallets = await repo.get_stale_wallets(hours=6)

        for wallet in wallets:
            try:
                await self.analyze_wallet(wallet.address)
                analyzed += 1
            except Exception as e:
                errors += 1
                logger.error("Wallet analysis failed", address=wallet.address[:8], error=str(e))

        return {"analyzed": analyzed, "errors": errors}

    async def analyze_wallet(self, address: str) -> Optional[Dict]:
        """
        Full analysis for a single wallet address.
        Returns the computed metrics dict.
        """
        logger.debug("Analyzing wallet", address=address[:8])

        # ── Fetch trade history ────────────────────────────────────────────
        trades_data = await self._fetch_trade_history(address)
        if not trades_data:
            logger.debug("No trade data for wallet", address=address[:8])
            return None

        # ── Calculate performance metrics ──────────────────────────────────
        metrics = self._calculate_metrics(trades_data)

        # ── Fetch portfolio ────────────────────────────────────────────────
        portfolio = await self._fetch_portfolio(address)
        sol_balance = await solana_client.get_sol_balance(address)

        # ── Estimate portfolio value ───────────────────────────────────────
        portfolio_value = portfolio.get("total_usd", 0)
        sol_price = 200.0  # TODO: pull from price cache
        sol_value = sol_balance * sol_price
        total_portfolio = portfolio_value + sol_value

        # ── Classify wallet ────────────────────────────────────────────────
        classification = self._classify_wallet(metrics, total_portfolio)

        # ── Compute score ──────────────────────────────────────────────────
        score, breakdown = self._compute_score(metrics, total_portfolio)

        # ── Persist ────────────────────────────────────────────────────────
        async with self.session_factory() as session:
            repo = WalletRepository(session)
            wallet, _ = await repo.get_or_create(address)

            update_data = {
                "wallet_type": classification["wallet_type"],
                "is_smart_money": classification["is_smart_money"],
                "is_whale": classification["is_whale"],
                "is_insider": classification["is_insider"],
                "total_trades": metrics["total_trades"],
                "winning_trades": metrics["winning_trades"],
                "losing_trades": metrics["losing_trades"],
                "win_rate": metrics["win_rate"],
                "total_pnl_usd": Decimal(str(metrics["total_pnl_usd"])),
                "realized_pnl_usd": Decimal(str(metrics["realized_pnl_usd"])),
                "roi_pct": metrics["roi_pct"],
                "avg_profit_per_trade_usd": Decimal(str(metrics.get("avg_profit", 0))),
                "avg_loss_per_trade_usd": Decimal(str(metrics.get("avg_loss", 0))),
                "best_trade_pnl_usd": Decimal(str(metrics.get("best_trade", 0))),
                "worst_trade_pnl_usd": Decimal(str(metrics.get("worst_trade", 0))),
                "avg_holding_time_hours": metrics.get("avg_holding_hours"),
                "avg_entry_timing_score": metrics.get("entry_timing_score"),
                "avg_exit_timing_score": metrics.get("exit_timing_score"),
                "sol_balance": Decimal(str(sol_balance)),
                "portfolio_value_usd": Decimal(str(total_portfolio)),
                "score": score,
                "score_breakdown": breakdown,
                "last_analyzed_at": datetime.now(timezone.utc),
            }

            await repo.update(wallet, update_data)

            # Persist current holdings
            await self._update_holdings(repo, wallet, portfolio.get("holdings", []))
            await session.commit()

        result = {
            "address": address,
            "wallet_type": classification["wallet_type"],
            "score": score,
            "win_rate": metrics["win_rate"],
            "total_pnl_usd": metrics["total_pnl_usd"],
        }
        logger.info(
            "Wallet analyzed",
            address=address[:8],
            type=classification["wallet_type"],
            score=round(score, 1),
            win_rate=round(metrics["win_rate"] * 100, 1) if metrics["win_rate"] else 0,
        )
        return result

    # ─── Data Fetching ────────────────────────────────────────────────────────

    async def _fetch_trade_history(self, address: str) -> List[Dict]:
        """Fetch swap history from Helius (best) or Birdeye (fallback)."""
        # Try Helius enhanced transactions
        if helius_client.api_key:
            txs = await helius_client.get_parsed_transactions(
                address=address,
                tx_type="SWAP",
                limit=100,
            )
            if txs:
                return self._normalize_helius_trades(txs, address)

        # Birdeye fallback
        if birdeye_client.api_key:
            txs = await birdeye_client.get_wallet_trades(address, limit=100)
            if txs:
                return self._normalize_birdeye_trades(txs)

        return []

    async def _fetch_portfolio(self, address: str) -> Dict:
        """Fetch current token holdings and their USD values."""
        if birdeye_client.api_key:
            portfolio_data = await birdeye_client.get_wallet_portfolio(address)
            if portfolio_data:
                return self._normalize_portfolio(portfolio_data)

        if helius_client.api_key:
            assets = await helius_client.search_assets(
                owner_address=address,
                token_type="fungible",
                limit=100,
            )
            if assets:
                return self._normalize_helius_portfolio(assets)

        return {"total_usd": 0, "holdings": []}

    # ─── Normalizers ──────────────────────────────────────────────────────────

    def _normalize_helius_trades(self, txs: List[Dict], address: str) -> List[Dict]:
        """Parse Helius enhanced swap transactions into a standard trade format."""
        trades = []
        for tx in txs:
            try:
                if tx.get("type") != "SWAP":
                    continue
                events = tx.get("events", {})
                swap = events.get("swap", {})
                if not swap:
                    continue

                ts = datetime.fromtimestamp(tx.get("timestamp", 0), tz=timezone.utc)
                token_outputs = swap.get("tokenOutputs", [])
                token_inputs = swap.get("tokenInputs", [])

                for output in token_outputs:
                    mint = output.get("mint", "")
                    if mint and mint != "So11111111111111111111111111111111111111112":
                        trades.append({
                            "trade_type": "buy",
                            "token_mint": mint,
                            "amount_usd": float(output.get("rawTokenAmount", {}).get("tokenAmount", 0)) / 1e6,
                            "timestamp": ts,
                            "signature": tx.get("signature", ""),
                            "dex": tx.get("source", "unknown"),
                        })

            except Exception:
                continue
        return trades

    def _normalize_birdeye_trades(self, txs: List[Dict]) -> List[Dict]:
        """Parse Birdeye trade items into standard format."""
        trades = []
        for tx in txs:
            try:
                side = tx.get("side", "").lower()
                trades.append({
                    "trade_type": "buy" if side == "buy" else "sell",
                    "token_mint": tx.get("token", {}).get("address", ""),
                    "amount_usd": float(tx.get("volume", 0) or 0),
                    "timestamp": datetime.fromtimestamp(
                        tx.get("blockUnixTime", 0), tz=timezone.utc
                    ),
                    "signature": tx.get("txHash", ""),
                    "dex": tx.get("source", "unknown"),
                })
            except Exception:
                continue
        return trades

    def _normalize_portfolio(self, data: Dict) -> Dict:
        """Normalize Birdeye portfolio response."""
        items = data.get("items", [])
        holdings = []
        total_usd = 0.0
        for item in items:
            value = float(item.get("valueUsd", 0) or 0)
            total_usd += value
            holdings.append({
                "token_mint": item.get("address", ""),
                "token_symbol": item.get("symbol"),
                "balance": float(item.get("uiAmount", 0) or 0),
                "value_usd": value,
                "price_usd": float(item.get("priceUsd", 0) or 0),
            })
        return {"total_usd": total_usd, "holdings": holdings}

    def _normalize_helius_portfolio(self, assets: List[Dict]) -> Dict:
        """Normalize Helius DAS portfolio response."""
        holdings = []
        total_usd = 0.0
        for asset in assets:
            try:
                token_info = asset.get("token_info", {})
                value = float(token_info.get("price_info", {}).get("total_price", 0) or 0)
                total_usd += value
                holdings.append({
                    "token_mint": asset.get("id", ""),
                    "token_symbol": asset.get("content", {}).get("metadata", {}).get("symbol"),
                    "balance": float(token_info.get("balance", 0) or 0),
                    "value_usd": value,
                })
            except Exception:
                continue
        return {"total_usd": total_usd, "holdings": holdings}

    # ─── Calculations ─────────────────────────────────────────────────────────

    def _calculate_metrics(self, trades: List[Dict]) -> Dict:
        """
        Compute performance metrics from normalized trade history.
        Pairs buys and sells of the same token to calculate PnL per round-trip.
        """
        if not trades:
            return self._empty_metrics()

        # Group trades by token mint
        token_trades: Dict[str, List[Dict]] = {}
        for trade in trades:
            mint = trade["token_mint"]
            if mint not in token_trades:
                token_trades[mint] = []
            token_trades[mint].append(trade)

        winning_trades = 0
        losing_trades = 0
        total_pnl = 0.0
        pnl_per_trade = []
        holding_times = []
        entry_timings = []

        for mint, token_tx in token_trades.items():
            sorted_txs = sorted(token_tx, key=lambda t: t["timestamp"])
            buys = [t for t in sorted_txs if t["trade_type"] == "buy"]
            sells = [t for t in sorted_txs if t["trade_type"] == "sell"]

            for buy, sell in zip(buys, sells):
                buy_amt = float(buy.get("amount_usd", 0))
                sell_amt = float(sell.get("amount_usd", 0))
                pnl = sell_amt - buy_amt
                total_pnl += pnl
                pnl_per_trade.append(pnl)

                if pnl > 0:
                    winning_trades += 1
                else:
                    losing_trades += 1

                # Holding time
                hold_hours = (sell["timestamp"] - buy["timestamp"]).total_seconds() / 3600
                holding_times.append(hold_hours)

        total_trades = len(pnl_per_trade)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        profits = [p for p in pnl_per_trade if p > 0]
        losses = [p for p in pnl_per_trade if p < 0]

        # Entry timing score: reward early entries relative to pump timing
        # Simplified: score based on win rate + holding discipline
        entry_timing = min(100.0, win_rate * 100 * 1.2)

        total_invested = sum(
            float(t.get("amount_usd", 0))
            for t in trades
            if t["trade_type"] == "buy"
        )
        roi_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 4),
            "total_pnl_usd": round(total_pnl, 2),
            "realized_pnl_usd": round(total_pnl, 2),
            "roi_pct": round(roi_pct, 2),
            "avg_profit": round(sum(profits) / len(profits), 2) if profits else 0,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
            "best_trade": max(pnl_per_trade, default=0),
            "worst_trade": min(pnl_per_trade, default=0),
            "avg_holding_hours": round(sum(holding_times) / len(holding_times), 2) if holding_times else 0,
            "entry_timing_score": round(entry_timing, 1),
            "exit_timing_score": round(min(100.0, win_rate * 110), 1),
        }

    def _classify_wallet(self, metrics: Dict, portfolio_usd: float) -> Dict:
        """Classify wallet based on computed metrics."""
        win_rate = metrics.get("win_rate", 0)
        total_trades = metrics.get("total_trades", 0)
        total_pnl = metrics.get("total_pnl_usd", 0)

        is_smart_money = (
            win_rate >= settings.SMART_MONEY_MIN_WIN_RATE
            and total_trades >= settings.SMART_MONEY_MIN_TRADES
            and total_pnl > 0
        )
        is_whale = portfolio_usd >= WHALE_PORTFOLIO_THRESHOLD_USD

        # Insider: very high win rate + small trade count (statistically suspicious)
        is_insider = (
            win_rate >= 0.85
            and total_trades >= 5
            and total_trades <= 30
            and total_pnl > 10_000
        )

        if is_insider:
            wallet_type = "insider"
        elif is_smart_money:
            wallet_type = "smart_money"
        elif is_whale:
            wallet_type = "whale"
        elif total_trades > 0:
            wallet_type = "retail"
        else:
            wallet_type = "unknown"

        return {
            "wallet_type": wallet_type,
            "is_smart_money": is_smart_money,
            "is_whale": is_whale,
            "is_insider": is_insider,
        }

    def _compute_score(self, metrics: Dict, portfolio_usd: float) -> Tuple[float, Dict]:
        """
        Calculate wallet intelligence score (0-100).
        Components:
          Win Rate        40%
          ROI             25%
          Trade Count     15%  (experience)
          Entry Timing    10%
          Portfolio Size  10%
        """
        win_rate_score = min(100.0, metrics.get("win_rate", 0) * 100 * 1.3)
        roi = metrics.get("roi_pct", 0)
        roi_score = min(100.0, max(0, (roi / 200) * 100))  # 200% ROI = 100 score
        trade_count = metrics.get("total_trades", 0)
        experience_score = min(100.0, (trade_count / 100) * 100)
        entry_score = metrics.get("entry_timing_score", 0)
        portfolio_score = min(100.0, (portfolio_usd / 500_000) * 100)

        final = (
            win_rate_score * 0.40
            + roi_score * 0.25
            + experience_score * 0.15
            + entry_score * 0.10
            + portfolio_score * 0.10
        )
        breakdown = {
            "win_rate_score": round(win_rate_score, 1),
            "roi_score": round(roi_score, 1),
            "experience_score": round(experience_score, 1),
            "entry_timing_score": round(entry_score, 1),
            "portfolio_score": round(portfolio_score, 1),
            "final": round(final, 1),
        }
        return round(final, 1), breakdown

    def _empty_metrics(self) -> Dict:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0,
            "total_pnl_usd": 0,
            "realized_pnl_usd": 0,
            "roi_pct": 0,
            "avg_profit": 0,
            "avg_loss": 0,
            "best_trade": 0,
            "worst_trade": 0,
            "avg_holding_hours": 0,
            "entry_timing_score": 0,
            "exit_timing_score": 0,
        }

    async def _update_holdings(
        self,
        repo: WalletRepository,
        wallet: Wallet,
        holdings: List[Dict],
    ) -> None:
        """Replace wallet's current holdings with fresh data."""
        from sqlalchemy import delete
        from app.database.models.wallet import WalletHolding

        # Delete old holdings
        await repo.session.execute(
            delete(WalletHolding).where(WalletHolding.wallet_id == wallet.id)
        )
        # Insert new holdings
        for h in holdings:
            if not h.get("token_mint"):
                continue
            holding = WalletHolding(
                wallet_id=wallet.id,
                token_mint=h["token_mint"],
                token_symbol=h.get("token_symbol"),
                balance=Decimal(str(h.get("balance", 0))),
                value_usd=Decimal(str(h.get("value_usd", 0))),
                avg_buy_price_usd=None,
            )
            repo.session.add(holding)


# ─── Celery task ──────────────────────────────────────────────────────────────

@shared_task(name="app.analyzers.wallet_analyzer.analyze_active_wallets", bind=True)
def analyze_active_wallets(self) -> dict:
    """Celery task: analyze all stale tracked wallets."""
    return asyncio.run(WalletAnalyzer().run())


@shared_task(name="app.analyzers.wallet_analyzer.analyze_single_wallet", bind=True)
def analyze_single_wallet(self, address: str) -> Optional[Dict]:
    """Celery task: analyze a single wallet on-demand."""
    return asyncio.run(WalletAnalyzer().analyze_wallet(address))
