"""
Whale Agent — analyzes large wallet movements and their implications.
"""

from typing import Any, Dict, List

from app.ai_agents.base_agent import BaseAgent


WHALE_AGENT_SYSTEM = """You are a whale tracking expert for Solana DeFi.
You interpret large wallet movements and their potential market impact.
You understand accumulation vs distribution patterns, market manipulation,
and the difference between smart whale moves and coordinated pumps.
Only return valid JSON — no extra text."""

WHALE_AGENT_PROMPT = """Analyze the following whale wallet activity for a Solana token and return a JSON assessment.

Token: {symbol} ({mint_address})
Current Price: ${price_usd}
Liquidity: ${liquidity_usd}

Recent Whale/Large Wallet Activity:
{whale_activity}

Market Context:
- Volume (1h): ${volume_1h}
- Price Change (1h): {price_change_1h}%
- Buy/Sell Ratio: {buy_sell_ratio}

Return ONLY this JSON:
{{
  "score": <0-100, whale activity quality score>,
  "activity_type": "<accumulation|distribution|manipulation|neutral>",
  "whale_sentiment": "<bullish|bearish|mixed|neutral>",
  "impact_assessment": "<high|medium|low>",
  "signals": [<list of significant observations, max 5>],
  "risks": [<list of risks from whale behavior>],
  "summary": "<2-3 sentence professional assessment>",
  "watch_level": "<price or metric to monitor>"
}}"""


class WhaleAgent(BaseAgent):
    name = "whale_agent"
    system_prompt = WHALE_AGENT_SYSTEM

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        token = context.get("token", {})
        whale_events = context.get("whale_events", [])
        symbol = token.get("symbol") or token.get("mint_address", "")[:8]

        # Format whale activity
        if whale_events:
            activity_lines = []
            for evt in whale_events[:10]:
                line = (
                    f"- Wallet {str(evt.get('wallet', ''))[:8]}... "
                    f"{evt.get('trade_type', 'buy').upper()} "
                    f"${float(evt.get('amount_usd', 0)):,.0f}"
                    f"{' (smart money)' if evt.get('is_smart') else ''}"
                    f"{' (known whale)' if evt.get('is_whale') else ''}"
                )
                activity_lines.append(line)
            whale_activity = "\n".join(activity_lines)
        else:
            whale_activity = "No significant whale activity detected in recent window."

        buys = token.get("buys_1h", 0) or 0
        sells = token.get("sells_1h", 0) or 0
        buy_sell_ratio = round(buys / sells, 2) if sells > 0 else 0

        prompt = WHALE_AGENT_PROMPT.format(
            symbol=symbol,
            mint_address=token.get("mint_address", ""),
            price_usd=f"{float(token.get('price_usd', 0) or 0):.8f}",
            liquidity_usd=f"{float(token.get('liquidity_usd', 0) or 0):,.0f}",
            whale_activity=whale_activity,
            volume_1h=f"{float(token.get('volume_1h_usd', 0) or 0):,.0f}",
            price_change_1h=f"{token.get('price_change_1h', 0) or 0:.1f}",
            buy_sell_ratio=buy_sell_ratio,
        )

        response, tokens_used = await self._call_llm(
            prompt,
            response_format={"type": "json_object"},
        )
        parsed = self._parse_json_response(response)

        if not parsed:
            return {
                "score": 50, "activity_type": "neutral", "whale_sentiment": "neutral",
                "impact_assessment": "low", "signals": [], "risks": [],
                "summary": "Whale analysis unavailable.",
                "tokens_used": tokens_used,
            }

        parsed["tokens_used"] = tokens_used
        return parsed
