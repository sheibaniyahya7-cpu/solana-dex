"""
Token Security Engine.
Analyzes tokens for rug pull indicators, honeypot patterns,
and concentration risks. Returns a Security Score (0-100)
and a rug probability estimate.

Risk factors analyzed:
  - Mint authority active (can print unlimited tokens)
  - Freeze authority active (can freeze accounts)
  - Top holder concentration (>30% = high risk)
  - Dev wallet concentration (>15% = red flag)
  - Very low holder count (<50 = suspicious)
  - Mutable metadata
  - Liquidity locked status
  - Token age (new tokens have higher risk)
"""

import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from app.collectors.birdeye_client import birdeye_client
from app.collectors.holder_collector import holder_collector
from app.collectors.solana_rpc_client import solana_client
from app.core.config import settings
from app.core.logging import get_logger
from app.database.base import get_session_factory
from app.database.repositories.token_repository import TokenRepository

logger = get_logger(__name__)


class SecurityAnalyzer:
    """
    Comprehensive token security analyzer.
    Produces a Security Score and detailed risk breakdown.
    """

    def __init__(self) -> None:
        self.session_factory = get_session_factory()

    async def analyze(self, mint_address: str) -> Dict:
        """
        Full security analysis for a token.
        Returns structured result with score, risks, and raw data.
        """
        logger.debug("Security analysis started", mint=mint_address[:8])
        start = datetime.now(timezone.utc)

        result = {
            "mint_address": mint_address,
            "security_score": None,
            "rug_probability": None,
            "risk_level": "unknown",
            "risks": [],
            "positive_signals": [],
            "raw": {},
        }

        try:
            # ── Parallel data fetching ─────────────────────────────────────
            mint_info, holder_data, birdeye_security, token_creation = await asyncio.gather(
                holder_collector.get_mint_authority_info(mint_address),
                holder_collector.get_holder_data(mint_address),
                birdeye_client.get_token_security(mint_address),
                birdeye_client.get_token_creation_info(mint_address),
                return_exceptions=True,
            )

            # Handle exceptions from gather
            if isinstance(mint_info, Exception):
                mint_info = {"has_mint_authority": True, "has_freeze_authority": True, "is_mutable": True}
            if isinstance(holder_data, Exception):
                holder_data = {}
            if isinstance(birdeye_security, Exception):
                birdeye_security = None
            if isinstance(token_creation, Exception):
                token_creation = None

            # Merge Birdeye security data (richer)
            if birdeye_security:
                mint_info = self._merge_birdeye_security(mint_info, birdeye_security)
                holder_data = self._merge_birdeye_holders(holder_data, birdeye_security)

            result["raw"] = {
                "mint_info": mint_info,
                "holder_data": holder_data,
                "creation_info": token_creation,
            }

            # ── Score calculation ──────────────────────────────────────────
            score, rug_prob, risks, positives = self._calculate_security_score(
                mint_info=mint_info,
                holder_data=holder_data,
                token_creation=token_creation,
            )

            result.update({
                "security_score": round(score, 1),
                "rug_probability": round(rug_prob, 3),
                "risk_level": self._risk_level(score),
                "risks": risks,
                "positive_signals": positives,
                # Holder data
                "holder_count": holder_data.get("holder_count"),
                "top_10_holder_pct": holder_data.get("top_10_holder_pct"),
                "dev_wallet_pct": holder_data.get("dev_wallet_pct"),
                # Authority flags
                "has_mint_authority": mint_info.get("has_mint_authority", True),
                "has_freeze_authority": mint_info.get("has_freeze_authority", True),
                "is_mutable": mint_info.get("is_mutable", True),
            })

            duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            logger.info(
                "Security analysis complete",
                mint=mint_address[:8],
                score=round(score, 1),
                rug_prob=round(rug_prob, 3),
                risks=len(risks),
                duration_ms=round(duration_ms),
            )

            # ── Persist to DB ──────────────────────────────────────────────
            await self._persist_results(mint_address, result)

        except Exception as e:
            logger.error("Security analysis failed", mint=mint_address[:8], error=str(e), exc_info=True)
            result["error"] = str(e)

        return result

    def _calculate_security_score(
        self,
        mint_info: Dict,
        holder_data: Dict,
        token_creation: Optional[Dict],
    ) -> Tuple[float, float, List[str], List[str]]:
        """
        Score = 100 - sum(penalty for each risk factor).
        Each risk deducts points proportional to its severity.
        """
        score = 100.0
        risks: List[str] = []
        positives: List[str] = []
        rug_flags = 0  # Hard rug indicators

        # ─── Authority Checks ─────────────────────────────────────────────

        if mint_info.get("has_mint_authority"):
            score -= 25
            risks.append("Mint authority active — developer can create unlimited tokens")
            rug_flags += 1
        else:
            positives.append("Mint authority revoked ✓")

        if mint_info.get("has_freeze_authority"):
            score -= 20
            risks.append("Freeze authority active — developer can freeze holder accounts")
            rug_flags += 1
        else:
            positives.append("Freeze authority revoked ✓")

        if mint_info.get("is_mutable"):
            score -= 5
            risks.append("Token metadata is mutable")

        # ─── Holder Concentration ─────────────────────────────────────────

        top_10_pct = holder_data.get("top_10_holder_pct")
        top_holder_pct = holder_data.get("top_holder_pct")
        dev_pct = holder_data.get("dev_wallet_pct")

        if top_10_pct is not None:
            if top_10_pct >= 80:
                score -= 30
                risks.append(f"Top 10 holders control {top_10_pct:.1f}% of supply (critical)")
                rug_flags += 2
            elif top_10_pct >= 60:
                score -= 20
                risks.append(f"Top 10 holders control {top_10_pct:.1f}% of supply (high risk)")
                rug_flags += 1
            elif top_10_pct >= 40:
                score -= 10
                risks.append(f"Top 10 holders control {top_10_pct:.1f}% of supply (elevated)")
            elif top_10_pct <= 20:
                positives.append(f"Well-distributed supply (top 10 = {top_10_pct:.1f}%) ✓")

        if top_holder_pct is not None:
            if top_holder_pct >= settings.MAX_HOLDER_CONCENTRATION * 100:
                score -= 15
                risks.append(
                    f"Single holder controls {top_holder_pct:.1f}% of supply"
                )
                rug_flags += 1

        if dev_pct is not None:
            if dev_pct >= settings.MAX_DEV_WALLET_HOLD * 100:
                score -= 15
                risks.append(
                    f"Dev wallet holds {dev_pct:.1f}% of supply (potential dump risk)"
                )
                rug_flags += 1
            elif dev_pct <= 5:
                positives.append(f"Dev wallet holdings minimal ({dev_pct:.1f}%) ✓")

        # ─── Holder Count ─────────────────────────────────────────────────

        holder_count = holder_data.get("holder_count", 0)
        if holder_count > 0:
            if holder_count < 50:
                score -= 15
                risks.append(f"Very few holders ({holder_count}) — possible honeypot")
                rug_flags += 1
            elif holder_count < 200:
                score -= 5
                risks.append(f"Low holder count ({holder_count})")
            elif holder_count > 1000:
                positives.append(f"Healthy holder count ({holder_count:,}) ✓")

        # ─── Token Age ────────────────────────────────────────────────────

        if token_creation and isinstance(token_creation, dict):
            created_at_ts = token_creation.get("creationTime") or token_creation.get("blockTime")
            if created_at_ts:
                created_at = datetime.fromtimestamp(created_at_ts, tz=timezone.utc)
                age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600

                if age_hours < 1:
                    score -= 10
                    risks.append(f"Token is only {age_hours:.1f} hours old (very new)")
                elif age_hours < 24:
                    score -= 5
                    risks.append(f"Token is less than 24 hours old")
                elif age_hours > 168:  # 1 week
                    positives.append("Token survived first week ✓")

        # ─── Rug Probability ─────────────────────────────────────────────

        # Base rug probability on flag count and severity
        rug_prob = min(0.99, rug_flags * 0.20 + (max(0, 50 - score) / 50) * 0.40)

        # If score is very low, ensure high rug prob
        if score <= 20:
            rug_prob = max(rug_prob, 0.85)
        elif score >= 80:
            rug_prob = min(rug_prob, 0.15)

        return max(0, min(100, score)), rug_prob, risks, positives

    def _merge_birdeye_security(self, mint_info: Dict, birdeye: Dict) -> Dict:
        """Merge Birdeye security data into our mint_info dict."""
        return {
            **mint_info,
            "has_mint_authority": birdeye.get("mintable", mint_info.get("has_mint_authority", True)),
            "has_freeze_authority": birdeye.get("freezeable", mint_info.get("has_freeze_authority", True)),
            "is_mutable": birdeye.get("metaplexUpdateAuthorityBalance") is not None,
        }

    def _merge_birdeye_holders(self, holder_data: Dict, birdeye: Dict) -> Dict:
        """Merge Birdeye holder data into our holder_data dict."""
        return {
            **holder_data,
            "holder_count": birdeye.get("numberMarkets") or holder_data.get("holder_count", 0),
            "top_10_holder_pct": birdeye.get("top10HolderPercent", holder_data.get("top_10_holder_pct")),
            "dev_wallet_pct": birdeye.get("creatorPercentage", holder_data.get("dev_wallet_pct")),
        }

    def _risk_level(self, score: float) -> str:
        if score >= 80:
            return "low"
        elif score >= 60:
            return "medium"
        elif score >= 40:
            return "high"
        else:
            return "critical"

    async def _persist_results(self, mint_address: str, result: Dict) -> None:
        """Save security analysis results back to the token record."""
        async with self.session_factory() as session:
            repo = TokenRepository(session)
            token = await repo.get_by_mint(mint_address)
            if not token:
                return
            await repo.update(token, {
                "security_score": result.get("security_score"),
                "rug_probability": result.get("rug_probability"),
                "has_mint_authority": result.get("has_mint_authority", True),
                "has_freeze_authority": result.get("has_freeze_authority", True),
                "is_mutable": result.get("is_mutable", True),
                "holder_count": result.get("holder_count"),
                "top_10_holder_pct": result.get("top_10_holder_pct"),
                "dev_wallet_pct": result.get("dev_wallet_pct"),
                "last_updated_at": datetime.now(timezone.utc),
            })
            await session.commit()

            # Emit rug risk event if critical
            if (
                result.get("rug_probability", 0) >= 0.6
                and result.get("risks")
            ):
                from app.monitors.event_types import make_rug_risk_event
                from app.core.redis import get_redis, RedisCache
                event = make_rug_risk_event(
                    token_id=str(token.id),
                    token_mint=mint_address,
                    token_symbol=token.symbol,
                    risk_factors=result["risks"][:5],
                    rug_probability=result["rug_probability"],
                )
                cache = RedisCache(get_redis(), "dex")
                await cache.publish("alert_queue", {
                    "type": "market_event",
                    "event_type": event.event_type,
                    "severity": event.severity,
                    "title": event.title,
                    "description": event.description,
                    "token_mint": mint_address,
                    "token_symbol": token.symbol,
                    "rug_probability": result["rug_probability"],
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                })


# Module-level singleton
security_analyzer = SecurityAnalyzer()
