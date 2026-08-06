"""
Scoring Engine — computes the composite AI score from all agent outputs.

Weights (configurable via settings):
  Security Score:     25%
  Smart Money Score:  25%
  Volume Score:       20%
  Liquidity Score:    15%
  Social Score:       15%

Each component is normalized to 0-100 before weighting.
The Trader Agent may override this composite score in its final output.
"""

from typing import Dict, Optional, Tuple

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ScoringEngine:
    """
    Calculates the weighted composite AI score for a token.
    Also derives individual component scores from raw token data
    when agent results are not yet available (fast-path scoring).
    """

    def compute_composite_score(
        self,
        security_score: Optional[float],
        smart_money_score: Optional[float],
        volume_score: Optional[float],
        liquidity_score: Optional[float],
        social_score: Optional[float],
    ) -> Tuple[float, Dict]:
        """
        Compute weighted composite score.
        Returns (final_score, component_breakdown).
        """
        weights = {
            "security": settings.SCORE_WEIGHT_SECURITY,
            "smart_money": settings.SCORE_WEIGHT_SMART_MONEY,
            "volume": settings.SCORE_WEIGHT_VOLUME,
            "liquidity": settings.SCORE_WEIGHT_LIQUIDITY,
            "social": settings.SCORE_WEIGHT_SOCIAL,
        }
        scores = {
            "security": security_score,
            "smart_money": smart_money_score,
            "volume": volume_score,
            "liquidity": liquidity_score,
            "social": social_score,
        }

        # Use 50 as neutral default for missing components
        available_weight = 0.0
        weighted_sum = 0.0

        for component, weight in weights.items():
            score = scores[component]
            if score is not None:
                weighted_sum += score * weight
                available_weight += weight
            else:
                # Use neutral 50 for missing, but scale weight down
                weighted_sum += 50 * weight * 0.5
                available_weight += weight * 0.5

        if available_weight > 0:
            final = weighted_sum / available_weight
        else:
            final = 50.0

        breakdown = {
            "security": round(security_score or 50, 1),
            "smart_money": round(smart_money_score or 50, 1),
            "volume": round(volume_score or 50, 1),
            "liquidity": round(liquidity_score or 50, 1),
            "social": round(social_score or 50, 1),
            "weights": weights,
            "final": round(final, 1),
        }

        return round(final, 1), breakdown

    def derive_volume_score(self, token: Dict) -> float:
        """
        Derive volume score from raw token market data.
        Used for fast-path scoring before AI agents run.
        """
        score = 50.0  # Neutral baseline

        # Volume trend (1h vs 24h average)
        vol_1h = float(token.get("volume_1h_usd") or 0)
        vol_24h = float(token.get("volume_24h_usd") or 0)
        if vol_24h > 0 and vol_1h > 0:
            hourly_avg = vol_24h / 24
            if hourly_avg > 0:
                ratio = vol_1h / hourly_avg
                if ratio >= 3:
                    score += 30
                elif ratio >= 2:
                    score += 20
                elif ratio >= 1.5:
                    score += 10
                elif ratio < 0.5:
                    score -= 15

        # Price momentum boost
        price_change_1h = float(token.get("price_change_1h") or 0)
        if price_change_1h > 20:
            score += 15
        elif price_change_1h > 10:
            score += 8
        elif price_change_1h < -20:
            score -= 15

        # Buy/sell pressure
        buys = int(token.get("buys_1h") or 0)
        sells = int(token.get("sells_1h") or 0)
        if buys + sells > 0:
            ratio = buys / (buys + sells)
            if ratio >= 0.70:
                score += 15
            elif ratio >= 0.60:
                score += 8
            elif ratio <= 0.30:
                score -= 15

        return max(0.0, min(100.0, score))

    def derive_liquidity_score(self, token: Dict) -> float:
        """Derive liquidity score from raw token data."""
        liquidity = float(token.get("liquidity_usd") or 0)

        if liquidity >= 1_000_000:
            return 95.0
        elif liquidity >= 500_000:
            return 85.0
        elif liquidity >= 100_000:
            return 70.0
        elif liquidity >= 50_000:
            return 55.0
        elif liquidity >= 10_000:
            return 40.0
        elif liquidity >= 1_000:
            return 25.0
        else:
            return 10.0

    def derive_security_score_fast(self, token: Dict) -> float:
        """
        Fast security score from cached token fields.
        Full security score comes from SecurityAnalyzer.
        """
        if token.get("security_score") is not None:
            return float(token["security_score"])

        score = 100.0

        if token.get("has_mint_authority"):
            score -= 25
        if token.get("has_freeze_authority"):
            score -= 20
        if token.get("is_mutable"):
            score -= 5

        top_10 = float(token.get("top_10_holder_pct") or 0)
        if top_10 >= 80:
            score -= 30
        elif top_10 >= 60:
            score -= 20
        elif top_10 >= 40:
            score -= 10

        rug_prob = float(token.get("rug_probability") or 0)
        score -= rug_prob * 30

        return max(0.0, min(100.0, score))

    def decision_from_score(self, score: float, rug_probability: float = 0) -> str:
        """Convert composite score to a decision label."""
        if rug_probability >= 0.8:
            return "DANGER"
        if score >= 85:
            return "STRONG_BUY"
        elif score >= 70:
            return "BUY"
        elif score >= 50:
            return "WATCH"
        elif score >= 30:
            return "AVOID"
        else:
            return "DANGER"


# Module-level singleton
scoring_engine = ScoringEngine()
