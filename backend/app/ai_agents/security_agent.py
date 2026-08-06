"""
Security Agent — assesses token safety and rug pull risk.
Interprets the raw security scores from the SecurityAnalyzer
and provides a human-readable risk assessment.
"""

from typing import Any, Dict

from app.ai_agents.base_agent import BaseAgent


SECURITY_AGENT_SYSTEM = """You are a blockchain security expert specializing in Solana token analysis.
You identify rug pulls, honeypots, and scam tokens with high precision.
Be direct about risks. Do not soften warnings about dangerous tokens.
Only return valid JSON — no extra text."""

SECURITY_AGENT_PROMPT = """Analyze the following Solana token security data and return a JSON risk assessment.

Token: {symbol} ({mint_address})

Security Data:
- Mint Authority Active: {has_mint_authority} (can create unlimited tokens = critical risk)
- Freeze Authority Active: {has_freeze_authority} (can lock holder wallets = critical risk)
- Metadata Mutable: {is_mutable}
- Top 10 Holders: {top_10_pct}% of supply
- Largest Single Holder: {top_holder_pct}% of supply
- Dev Wallet Holdings: {dev_wallet_pct}% of supply
- Total Holders: {holder_count}
- Token Age: {age_hours} hours
- Pre-calculated Security Score: {security_score}/100
- Pre-calculated Rug Probability: {rug_probability}

Identified Risk Factors:
{risk_factors}

Positive Signals:
{positive_signals}

Return ONLY this JSON:
{{
  "score": <0-100, independent security assessment>,
  "risk_level": "<low|medium|high|critical>",
  "rug_probability": <0.0-1.0>,
  "verdict": "<SAFE|CAUTION|RISKY|DANGER>",
  "critical_risks": [<list of deal-breaker risks, if any>],
  "warnings": [<list of yellow-flag warnings>],
  "positives": [<list of green flags>],
  "summary": "<2-3 sentence professional security assessment>",
  "recommendation": "<one-line action recommendation>"
}}"""


class SecurityAgent(BaseAgent):
    name = "security_agent"
    system_prompt = SECURITY_AGENT_SYSTEM

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        token = context.get("token", {})
        security = context.get("security_analysis", {})
        symbol = token.get("symbol") or token.get("mint_address", "")[:8]

        risk_factors = security.get("risks", [])
        positive_signals = security.get("positive_signals", [])

        prompt = SECURITY_AGENT_PROMPT.format(
            symbol=symbol,
            mint_address=token.get("mint_address", ""),
            has_mint_authority=security.get("has_mint_authority", token.get("has_mint_authority", True)),
            has_freeze_authority=security.get("has_freeze_authority", token.get("has_freeze_authority", True)),
            is_mutable=security.get("is_mutable", token.get("is_mutable", True)),
            top_10_pct=security.get("top_10_holder_pct") or token.get("top_10_holder_pct", "N/A"),
            top_holder_pct=security.get("top_holder_pct", "N/A"),
            dev_wallet_pct=security.get("dev_wallet_pct") or token.get("dev_wallet_pct", "N/A"),
            holder_count=security.get("holder_count") or token.get("holder_count", "N/A"),
            age_hours=context.get("token_age_hours", "N/A"),
            security_score=security.get("security_score") or token.get("security_score", "N/A"),
            rug_probability=security.get("rug_probability") or token.get("rug_probability", "N/A"),
            risk_factors="\n".join(f"- {r}" for r in risk_factors) or "None identified",
            positive_signals="\n".join(f"- {p}" for p in positive_signals) or "None identified",
        )

        response, tokens_used = await self._call_llm(
            prompt,
            response_format={"type": "json_object"},
        )
        parsed = self._parse_json_response(response)

        if not parsed:
            return {
                "score": 50, "risk_level": "unknown", "rug_probability": 0.5,
                "verdict": "CAUTION", "critical_risks": [], "warnings": [],
                "positives": [], "summary": "Security assessment unavailable.",
                "recommendation": "Conduct manual security review.",
                "tokens_used": tokens_used,
            }

        parsed["tokens_used"] = tokens_used
        return parsed
