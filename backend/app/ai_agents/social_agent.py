"""
Social Agent — evaluates social presence and narrative strength.
Analyzes website, Twitter, Telegram, community signals,
and token description quality.
"""

from typing import Any, Dict

from app.ai_agents.base_agent import BaseAgent


SOCIAL_AGENT_SYSTEM = """You are a crypto social analyst specializing in community assessment.
You evaluate the credibility and strength of a token's social presence.
You can identify organic communities vs artificial hype vs copy-paste scams.
Only return valid JSON — no extra text."""

SOCIAL_AGENT_PROMPT = """Analyze the following Solana token's social presence and return a JSON assessment.

Token: {symbol} ({mint_address})

Social Links:
- Website: {website}
- Twitter: {twitter}
- Telegram: {telegram}
- Discord: {discord}

Token Information:
- Name: {name}
- Description: {description}
- Token Age: {age_hours} hours

Market Legitimacy Signals:
- Liquidity: ${liquidity_usd}
- Holder Count: {holder_count}
- Is Verified: {is_verified}

Return ONLY this JSON:
{{
  "score": <0-100, social/community score>,
  "community_strength": "<strong|moderate|weak|none>",
  "credibility": "<high|medium|low|suspicious>",
  "presence": {{
    "has_website": <true/false>,
    "has_twitter": <true/false>,
    "has_telegram": <true/false>,
    "has_discord": <true/false>
  }},
  "signals": [<positive social observations, max 4>],
  "risks": [<social red flags, max 3>],
  "summary": "<2 sentence social assessment>",
  "narrative_quality": "<strong|generic|copied|none>"
}}"""


class SocialAgent(BaseAgent):
    name = "social_agent"
    system_prompt = SOCIAL_AGENT_SYSTEM

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        token = context.get("token", {})
        symbol = token.get("symbol") or token.get("mint_address", "")[:8]

        prompt = SOCIAL_AGENT_PROMPT.format(
            symbol=symbol,
            mint_address=token.get("mint_address", ""),
            website=token.get("website") or "Not provided",
            twitter=token.get("twitter") or "Not provided",
            telegram=token.get("telegram") or "Not provided",
            discord=token.get("discord") or "Not provided",
            name=token.get("name") or "Unknown",
            description=token.get("description") or "Not provided",
            age_hours=context.get("token_age_hours", "N/A"),
            liquidity_usd=f"{float(token.get('liquidity_usd', 0) or 0):,.0f}",
            holder_count=token.get("holder_count", "N/A"),
            is_verified=token.get("is_verified", False),
        )

        response, tokens_used = await self._call_llm(
            prompt,
            response_format={"type": "json_object"},
        )
        parsed = self._parse_json_response(response)

        if not parsed:
            # Derive basic score from available data
            has_website = bool(token.get("website"))
            has_twitter = bool(token.get("twitter"))
            has_telegram = bool(token.get("telegram"))
            links_score = (has_website + has_twitter + has_telegram) * 15
            return {
                "score": links_score,
                "community_strength": "weak",
                "credibility": "low",
                "presence": {
                    "has_website": has_website,
                    "has_twitter": has_twitter,
                    "has_telegram": has_telegram,
                    "has_discord": bool(token.get("discord")),
                },
                "signals": [], "risks": [],
                "summary": "Social analysis unavailable.",
                "narrative_quality": "none",
                "tokens_used": tokens_used,
            }

        parsed["tokens_used"] = tokens_used
        return parsed
