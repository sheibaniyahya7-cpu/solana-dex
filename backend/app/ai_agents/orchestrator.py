"""
AI Analysis Orchestrator.
Coordinates all agents, collects results, and persists the final AIAnalysis record.

Pipeline for each token:
  1. Build context (token data + security analysis + wallet data + whale events)
  2. Run Market, Security, Whale, Wallet, Social agents in parallel
  3. ScoringEngine computes weighted composite score
  4. Trader Agent synthesizes all reports → final decision
  5. Persist AIAnalysis record
  6. Update Token record with AI fields
  7. Publish result to Redis for WebSocket + alert dispatch
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from celery import shared_task
from sqlalchemy import select, desc

from app.ai_agents.base_agent import BaseAgent
from app.ai_agents.market_agent import MarketAgent
from app.ai_agents.security_agent import SecurityAgent
from app.ai_agents.whale_agent import WhaleAgent
from app.ai_agents.wallet_agent import WalletAgent
from app.ai_agents.social_agent import SocialAgent
from app.ai_agents.trader_agent import TraderAgent
from app.ai_agents.scoring_engine import scoring_engine
from app.analyzers.security_analyzer import SecurityAnalyzer
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis, RedisCache
from app.core.task_runtime import run_async
from app.database.base import get_session_factory
from app.database.models.analysis import AIAnalysis
from app.database.models.market_event import MarketEvent
from app.database.models.token import Token
from app.database.models.wallet import Wallet, WalletTrade, WalletHolding
from app.database.repositories.token_repository import TokenRepository
from app.database.repositories.wallet_repository import WalletRepository

logger = get_logger(__name__)

ANALYSIS_COOLDOWN_MINUTES = 15  # Don't re-analyze same token more often than this


class AnalysisOrchestrator:
    """
    Full multi-agent analysis pipeline for a single token.
    Designed to be called per-token, either on-demand or via Celery beat.
    """

    def __init__(self) -> None:
        self.session_factory = get_session_factory()
        self.market_agent = MarketAgent()
        self.security_agent = SecurityAgent()
        self.whale_agent = WhaleAgent()
        self.wallet_agent = WalletAgent()
        self.social_agent = SocialAgent()
        self.trader_agent = TraderAgent()
        self.security_analyzer = SecurityAnalyzer()

    async def analyze_token(
        self,
        mint_address: str,
        force_refresh: bool = False,
    ) -> Optional[Dict]:
        """
        Full AI analysis pipeline for one token.
        Returns the analysis result dict or None if skipped.
        """
        start_ms = time.perf_counter() * 1000

        # ── Load token ────────────────────────────────────────────────────────
        async with self.session_factory() as session:
            token_repo = TokenRepository(session)
            token = await token_repo.get_by_mint(mint_address)

        if not token:
            logger.warning("Token not found for analysis", mint=mint_address[:8])
            return None

        # ── Check cooldown ─────────────────────────────────────────────────
        if not force_refresh and token.ai_analyzed_at:
            elapsed = (datetime.now(timezone.utc) - token.ai_analyzed_at).total_seconds() / 60
            if elapsed < ANALYSIS_COOLDOWN_MINUTES:
                logger.debug(
                    "Analysis skipped — too recent",
                    mint=mint_address[:8],
                    minutes_ago=round(elapsed, 1),
                )
                return None

        logger.info("Starting AI analysis", mint=mint_address[:8], symbol=token.symbol)

        # ── Build token age ───────────────────────────────────────────────────
        if token.first_seen_at:
            age_hours = (datetime.now(timezone.utc) - token.first_seen_at).total_seconds() / 3600
        else:
            age_hours = None

        token_dict = self._token_to_dict(token)

        # ── Parallel data fetch ───────────────────────────────────────────────
        security_data, smart_wallets, recent_trades, whale_events = await asyncio.gather(
            self._fetch_security_data(mint_address, token_dict),
            self._fetch_smart_wallet_data(mint_address),
            self._fetch_recent_smart_trades(mint_address),
            self._fetch_whale_events(mint_address),
            return_exceptions=True,
        )

        # Safety defaults for exceptions
        if isinstance(security_data, Exception):
            security_data = {}
        if isinstance(smart_wallets, Exception):
            smart_wallets = []
        if isinstance(recent_trades, Exception):
            recent_trades = []
        if isinstance(whale_events, Exception):
            whale_events = []

        # ── Build per-agent context ───────────────────────────────────────────
        base_context = {"token": token_dict, "token_age_hours": round(age_hours, 1) if age_hours else "N/A"}

        market_ctx = {**base_context}
        security_ctx = {**base_context, "security_analysis": security_data}
        whale_ctx = {**base_context, "whale_events": whale_events}
        wallet_ctx = self._build_wallet_context(base_context, smart_wallets, recent_trades)
        social_ctx = {**base_context}

        # ── Run specialist agents in parallel ─────────────────────────────────
        logger.debug("Running specialist agents in parallel", token=token.symbol)
        results = await asyncio.gather(
            self.market_agent.analyze(market_ctx),
            self.security_agent.analyze(security_ctx),
            self.whale_agent.analyze(whale_ctx),
            self.wallet_agent.analyze(wallet_ctx),
            self.social_agent.analyze(social_ctx),
            return_exceptions=True,
        )

        market_r, security_r, whale_r, wallet_r, social_r = [
            r if not isinstance(r, Exception) else {} for r in results
        ]

        # ── Compute composite score ───────────────────────────────────────────
        sec_score = security_r.get("score") or scoring_engine.derive_security_score_fast(token_dict)
        sm_score = wallet_r.get("score") or (
            len(smart_wallets) * 15 if smart_wallets else 50
        )
        vol_score = market_r.get("score") or scoring_engine.derive_volume_score(token_dict)
        liq_score = scoring_engine.derive_liquidity_score(token_dict)
        soc_score = social_r.get("score") or 40

        composite_score, score_breakdown = scoring_engine.compute_composite_score(
            security_score=sec_score,
            smart_money_score=min(100, sm_score),
            volume_score=vol_score,
            liquidity_score=liq_score,
            social_score=soc_score,
        )

        # ── Trader Agent final synthesis ──────────────────────────────────────
        logger.debug("Running Trader Agent synthesis", token=token.symbol)
        trader_context = {
            **base_context,
            "agent_reports": {
                "market": market_r,
                "security": security_r,
                "whale": whale_r,
                "wallet": wallet_r,
                "social": social_r,
            },
            "composite_score": composite_score,
        }
        trader_result = await self.trader_agent.analyze(trader_context)

        final_score = float(trader_result.get("final_score") or composite_score)
        decision = trader_result.get("decision") or scoring_engine.decision_from_score(
            final_score, float(security_data.get("rug_probability", 0))
        )

        # ── Count tokens used ─────────────────────────────────────────────────
        total_tokens = sum(
            (r.get("tokens_used", 0) or 0)
            for r in [market_r, security_r, whale_r, wallet_r, social_r, trader_result]
        )
        duration_ms = int(time.perf_counter() * 1000 - start_ms)

        # ── Persist AIAnalysis record ─────────────────────────────────────────
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            analysis = AIAnalysis(
                token_id=token.id,
                token_mint=mint_address,
                token_symbol=token.symbol,
                analyzed_at=now,
                # Agent outputs
                market_agent_output=market_r,
                security_agent_output=security_r,
                whale_agent_output=whale_r,
                wallet_agent_output=wallet_r,
                social_agent_output=social_r,
                # Component scores
                security_score=sec_score,
                smart_money_score=min(100, sm_score),
                volume_score=vol_score,
                liquidity_score=liq_score,
                social_score=soc_score,
                # Trader Agent output
                final_score=final_score,
                decision=decision,
                confidence=trader_result.get("confidence"),
                summary=trader_result.get("summary"),
                reasons=trader_result.get("reasons"),
                risks=trader_result.get("risks"),
                catalysts=trader_result.get("catalysts"),
                raw_trader_output=str(trader_result),
                model_used=settings.OPENAI_MODEL_ADVANCED,
                tokens_used=total_tokens,
                analysis_duration_ms=duration_ms,
            )
            session.add(analysis)

            # Update token AI fields
            token_repo = TokenRepository(session)
            await token_repo.update(token, {
                "ai_score": final_score,
                "smart_money_score": min(100, sm_score),
                "volume_score": vol_score,
                "liquidity_score": liq_score,
                "social_score": soc_score,
                "security_score": sec_score,
                "ai_decision": decision,
                "ai_analysis_text": trader_result.get("summary"),
                "ai_analyzed_at": now,
            })

            await session.commit()
            analysis_id = analysis.id

        # ── Publish result ────────────────────────────────────────────────────
        cache = RedisCache(get_redis(), "dex")
        await cache.publish(f"token:{mint_address}", {
            "type": "analysis_complete",
            "token_mint": mint_address,
            "token_symbol": token.symbol,
            "final_score": final_score,
            "decision": decision,
            "confidence": trader_result.get("confidence"),
            "summary": trader_result.get("summary"),
            "reasons": trader_result.get("reasons", []),
            "analyzed_at": now.isoformat(),
        })

        # Dispatch alert for high-score tokens
        if final_score >= 75 and decision in ("STRONG_BUY", "BUY"):
            await cache.publish("alert_queue", {
                "type": "AI_ANALYSIS",
                "token_mint": mint_address,
                "token_symbol": token.symbol,
                "final_score": final_score,
                "decision": decision,
                "summary": trader_result.get("summary", ""),
                "reasons": trader_result.get("reasons", []),
                "detected_at": now.isoformat(),
            })

        logger.info(
            "AI analysis complete",
            token=token.symbol,
            score=round(final_score, 1),
            decision=decision,
            tokens_used=total_tokens,
            duration_ms=duration_ms,
        )

        return {
            "analysis_id": str(analysis_id),
            "token_mint": mint_address,
            "final_score": final_score,
            "decision": decision,
            "confidence": trader_result.get("confidence"),
            "duration_ms": duration_ms,
            "tokens_used": total_tokens,
        }

    # ─── Context Builders ─────────────────────────────────────────────────────

    def _token_to_dict(self, token: Token) -> Dict:
        """Convert Token ORM object to plain dict for agent context."""
        return {
            "mint_address": token.mint_address,
            "symbol": token.symbol,
            "name": token.name,
            "price_usd": str(token.price_usd) if token.price_usd else None,
            "market_cap_usd": str(token.market_cap_usd) if token.market_cap_usd else None,
            "volume_5m_usd": str(token.volume_5m_usd) if token.volume_5m_usd else None,
            "volume_1h_usd": str(token.volume_1h_usd) if token.volume_1h_usd else None,
            "volume_24h_usd": str(token.volume_24h_usd) if token.volume_24h_usd else None,
            "liquidity_usd": str(token.liquidity_usd) if token.liquidity_usd else None,
            "price_change_5m": token.price_change_5m,
            "price_change_1h": token.price_change_1h,
            "price_change_6h": token.price_change_6h,
            "price_change_24h": token.price_change_24h,
            "buys_5m": token.buys_5m,
            "sells_5m": token.sells_5m,
            "buys_1h": token.buys_1h,
            "sells_1h": token.sells_1h,
            "tx_count_24h": token.tx_count_24h,
            "holder_count": token.holder_count,
            "top_10_holder_pct": token.top_10_holder_pct,
            "dev_wallet_pct": token.dev_wallet_pct,
            "has_mint_authority": token.has_mint_authority,
            "has_freeze_authority": token.has_freeze_authority,
            "is_mutable": token.is_mutable,
            "security_score": token.security_score,
            "rug_probability": token.rug_probability,
            "website": token.website,
            "twitter": token.twitter,
            "telegram": token.telegram,
            "discord": token.discord,
            "description": None,
            "is_verified": token.is_verified,
        }

    async def _fetch_security_data(self, mint: str, token_dict: Dict) -> Dict:
        """Get fresh security data or use cached token fields."""
        if token_dict.get("security_score") is not None:
            return token_dict  # Already have recent security data
        result = await self.security_analyzer.analyze(mint)
        return result

    async def _fetch_smart_wallet_data(self, mint: str) -> List[Dict]:
        """Get smart money wallets currently holding this token."""
        async with self.session_factory() as session:
            wallet_repo = WalletRepository(session)
            wallets = await wallet_repo.get_wallets_holding_token(mint)
            return [
                {
                    "address": w.address,
                    "score": w.score,
                    "win_rate": w.win_rate,
                    "total_pnl_usd": str(w.total_pnl_usd) if w.total_pnl_usd else None,
                    "wallet_type": w.wallet_type,
                }
                for w in wallets
            ]

    async def _fetch_recent_smart_trades(self, mint: str) -> List[Dict]:
        """Get recent trades for this token from smart money wallets."""
        async with self.session_factory() as session:
            from sqlalchemy import select, desc, and_
            stmt = (
                select(WalletTrade, Wallet)
                .join(Wallet, Wallet.id == WalletTrade.wallet_id)
                .where(
                    and_(
                        WalletTrade.token_mint == mint,
                        Wallet.is_smart_money == True,
                    )
                )
                .order_by(desc(WalletTrade.trade_timestamp))
                .limit(20)
            )
            result = await session.execute(stmt)
            rows = result.all()
            return [
                {
                    "wallet": row.Wallet.address,
                    "trade_type": row.WalletTrade.trade_type,
                    "amount_usd": str(row.WalletTrade.amount_usd) if row.WalletTrade.amount_usd else None,
                    "is_smart": row.Wallet.is_smart_money,
                    "is_whale": row.Wallet.is_whale,
                    "timestamp": row.WalletTrade.trade_timestamp.isoformat(),
                }
                for row in rows
            ]

    async def _fetch_whale_events(self, mint: str) -> List[Dict]:
        """Get recent whale events for this token from the DB."""
        async with self.session_factory() as session:
            from sqlalchemy import select, desc, and_
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            stmt = (
                select(MarketEvent)
                .where(
                    and_(
                        MarketEvent.token_mint == mint,
                        MarketEvent.event_type.in_(["WHALE_BUY", "WHALE_SELL"]),
                        MarketEvent.detected_at >= cutoff,
                    )
                )
                .order_by(desc(MarketEvent.detected_at))
                .limit(10)
            )
            result = await session.execute(stmt)
            events = result.scalars().all()
            return [
                {
                    "wallet": e.whale_wallet_address,
                    "trade_type": "buy" if e.event_type == "WHALE_BUY" else "sell",
                    "amount_usd": float(e.whale_amount_usd) if e.whale_amount_usd else 0,
                    "is_whale": True,
                }
                for e in events
            ]

    def _build_wallet_context(
        self,
        base_context: Dict,
        smart_wallets: List[Dict],
        recent_trades: List[Dict],
    ) -> Dict:
        enters = sum(1 for t in recent_trades if t.get("trade_type") == "buy")
        exits = sum(1 for t in recent_trades if t.get("trade_type") == "sell")
        scores = [float(w.get("score") or 0) for w in smart_wallets if w.get("score")]
        avg_score = sum(scores) / len(scores) if scores else 0

        return {
            **base_context,
            "smart_wallets": smart_wallets,
            "recent_smart_trades": recent_trades,
            "sm_entered_count": enters,
            "sm_exited_count": exits,
            "avg_wallet_score": round(avg_score, 1) if avg_score else "N/A",
        }


# ─── Batch runner ─────────────────────────────────────────────────────────────

class BatchAnalysisRunner:
    """Runs AI analysis for the top tokens that need it."""

    def __init__(self) -> None:
        self.orchestrator = AnalysisOrchestrator()
        self.session_factory = get_session_factory()

    async def run(self) -> dict:
        analyzed = 0
        skipped = 0
        errors = 0

        async with self.session_factory() as session:
            token_repo = TokenRepository(session)
            # Prioritize: high liquidity + not recently analyzed
            tokens = await token_repo.get_active_tokens(
                limit=20,
                min_liquidity=settings.MIN_LIQUIDITY_USD,
            )

        for token in tokens:
            try:
                result = await self.orchestrator.analyze_token(token.mint_address)
                if result:
                    analyzed += 1
                else:
                    skipped += 1
                # Small delay between analyses to avoid API rate limits
                await asyncio.sleep(2)
            except Exception as e:
                errors += 1
                logger.error("Batch analysis failed", mint=token.mint_address[:8], error=str(e))

        return {"analyzed": analyzed, "skipped": skipped, "errors": errors}


# ─── Celery tasks ─────────────────────────────────────────────────────────────

@shared_task(name="app.ai_agents.orchestrator.run_analysis_cycle", bind=True)
def run_analysis_cycle(self) -> dict:
    """Celery beat task: analyze top tokens every 5 minutes."""
    return run_async(BatchAnalysisRunner().run())


@shared_task(name="app.ai_agents.orchestrator.run_token_analysis", bind=True)
def run_token_analysis(self, mint_address: str, force_refresh: bool = False) -> Optional[Dict]:
    """Celery task: analyze a single token on demand."""
    return run_async(
        AnalysisOrchestrator().analyze_token(mint_address, force_refresh=force_refresh)
    )
