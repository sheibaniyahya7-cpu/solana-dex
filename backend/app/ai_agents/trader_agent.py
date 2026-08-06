"""
Trader Agent — the senior trader that synthesizes all agent reports
into a final trading decision with full rationale.

This is the most expensive agent and uses the advanced model (GPT-4o).
It receives all other agents' outputs and produces the final AI Score,
decision, and reasoning.
"""

import json
from typing import Any, Dict, List, Optional

from app.ai_agents.base_agent import BaseAgent
from app.core.config import settings


TRADER_AGENT_SYSTEM = """You are a veteran Solana DEX trader with 5+ years of experience.
You have analyzed thousands of tokens and have a proven track record of identifying
early opportunities while avoiding rugs and pump-and-dumps.

You are presented with reports from specialized AI agents. Your job is to synthesize
all reports into ONE final trading decision with clear reasoning.

Decisions:
- STRONG_BUY: High conviction opportunity — strong fundamentals + smart money + security ✓
- BUY: Good opportunity — most signals positive, manageable risk
- WATCH: Interesting but waiting for confirmation — monitor closely
- AVOID: Risk outweighs potential — not worth trading at current conditions
- DANGER: Active red flags — rug risk, manipulation, or exit scam indicators

Be a professional trader, not a hype machine. Your reputation depends on accuracy.
Only return valid JSON — no extra text."""

TRADER_AGENT_PROMPT = """You are the lead trader reviewing agent reports for this Solana token.
Make a final trading decision based on all available intelligence.

═══ TOKEN OVERVIEW ═══
Symbol: {symbol}
Mint: {mint_address}
Price: ${price_usd}
Age: {token_age_hours} hours

═══ MARKET AGENT REPORT ═══
Score: {market_score}/100 | Trend: {market_trend} | Momentum: {market_momentum}
Volume Quality: {volume_quality}
Key Signals: {market_signals}
Key Risks: {market_risks}
Summary: {market_summary}

═══ SECURITY AGENT REPORT ═══
Score: {security_score}/100 | Risk Level: {risk_level} | Verdict: {security_verdict}
Rug Probability: {rug_prob}
Critical Risks: {critical_risks}
Positives: {security_positives}
Summary: {security_summary}

═══ WHALE AGENT REPORT ═══
Score: {whale_score}/100 | Activity: {whale_activity} | Sentiment: {whale_sentiment}
Signals: {whale_signals}
Summary: {whale_summary}

═══ SMART MONEY AGENT REPORT ═══
Score: {wallet_score}/100 | Conviction: {sm_conviction} | Flow: {sm_flow}
Smart Wallets: {sm_count} | Avg Entry Quality: {entry_quality}
Signals: {wallet_signals}
Summary: {wallet_summary}

═══ SOCIAL AGENT REPORT ═══
Score: {social_score}/100 | Community: {community} | Credibility: {credibility}
Summary: {social_summary}

═══ PRE-CALCULATED COMPOSITE SCORE ═══
Weighted Score: {composite_score}/100

Return ONLY this JSON:
{{
  "final_score": <0-100 your independent final score>,
  "decision": "<STRONG_BUY|BUY|WATCH|AVOID|DANGER>",
  "confidence": <0.0-1.0>,
  "summary": "<3-4 sentence professional trading assessment>",
  "reasons": [<top 3-5 positive reasons for your decision>],
  "risks": [<top 2-4 risks to monitor>],
  "catalysts": [<what events would move this to a stronger buy signal>],
  "entry_advice": "<specific advice on position sizing and timing>",
  "exit_conditions": "<what would make you exit/change thesis>"
}}"""


class TraderAgent(BaseAgent):
    """
    Senior Trader Agent — final synthesis and decision maker.
    Uses the advanced model for maximum reasoning capability.
    """

    name = "trader_agent"
    system_prompt = TRADER_AGENT_SYSTEM
    model = ""  # Will be set to OPENAI_MODEL_ADVANCED in __init__

    def __init__(self) -> None:
        super().__init__()
        self.model = settings.OPENAI_MODEL_ADVANCED  # gpt-4o

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        token = context.get("token", {})
        reports = context.get("agent_reports", {})
        composite_score = context.get("composite_score", 50)
        symbol = token.get("symbol") or token.get("mint_address", "")[:8]

        market = reports.get("market", {})
        security = reports.get("security", {})
        whale = reports.get("whale", {})
        wallet = reports.get("wallet", {})
        social = reports.get("social", {})

        prompt = TRADER_AGENT_PROMPT.format(
            symbol=symbol,
            mint_address=token.get("mint_address", ""),
            price_usd=f"{float(token.get('price_usd', 0) or 0):.8f}",
            token_age_hours=context.get("token_age_hours", "N/A"),

            # Market
            market_score=market.get("score", "N/A"),
            market_trend=market.get("trend", "N/A"),
            market_momentum=market.get("momentum", "N/A"),
            volume_quality=market.get("volume_quality", "N/A"),
            market_signals=", ".join(market.get("signals", [])) or "None",
            market_risks=", ".join(market.get("risks", [])) or "None",
            market_summary=market.get("summary", "N/A"),

            # Security
            security_score=security.get("score", "N/A"),
            risk_level=security.get("risk_level", "N/A"),
            security_verdict=security.get("verdict", "N/A"),
            rug_prob=security.get("rug_probability", "N/A"),
            critical_risks=", ".join(security.get("critical_risks", [])) or "None",
            security_positives=", ".join(security.get("positives", [])) or "None",
            security_summary=security.get("summary", "N/A"),

            # Whale
            whale_score=whale.get("score", "N/A"),
            whale_activity=whale.get("activity_type", "N/A"),
            whale_sentiment=whale.get("whale_sentiment", "N/A"),
            whale_signals=", ".join(whale.get("signals", [])) or "None",
            whale_summary=whale.get("summary", "N/A"),

            # Smart Money
            wallet_score=wallet.get("score", "N/A"),
            sm_conviction=wallet.get("conviction", "N/A"),
            sm_flow=wallet.get("flow_direction", "N/A"),
            sm_count=wallet.get("smart_wallet_count", 0),
            entry_quality=wallet.get("avg_entry_quality", "N/A"),
            wallet_signals=", ".join(wallet.get("signals", [])) or "None",
            wallet_summary=wallet.get("summary", "N/A"),

            # Social
            social_score=social.get("score", "N/A"),
            community=social.get("community_strength", "N/A"),
            credibility=social.get("credibility", "N/A"),
            social_summary=social.get("summary", "N/A"),

            composite_score=round(composite_score, 1),
        )

        response, tokens_used = await self._call_llm(
            prompt,
            response_format={"type": "json_object"},
            temperature=0.15,  # Very low — we want consistent, analytical output
            max_tokens=1500,
        )
        parsed = self._parse_json_response(response)

        if not parsed:
            return {
                "final_score": composite_score,
                "decision": "WATCH",
                "confidence": 0.5,
                "summary": "Final analysis unavailable — using composite score.",
                "reasons": [],
                "risks": [],
                "catalysts": [],
                "entry_advice": "Await full AI analysis.",
                "exit_conditions": "Monitor for rug indicators.",
                "tokens_used": tokens_used,
            }

        parsed["tokens_used"] = tokens_used
        return parsed
