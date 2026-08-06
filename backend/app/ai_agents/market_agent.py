"""
Market Agent — analyzes current market conditions for a token.
Evaluates price action, volume trends, buy/sell pressure,
and overall market momentum.
"""

from typing import Any, Dict, Optional

from app.ai_agents.base_agent import BaseAgent


MARKET_AGENT_SYSTEM = """You are a professional Solana DEX market analyst with expertise in:
- Price action and momentum analysis
- Volume profile interpretation
- Buy/sell pressure dynamics
- Market microstructure on DEX platforms

Your job: analyze raw market data for a token and return a structured JSON assessment.
Be concise, precise, and evidence-based. Avoid speculation without data support.
Only return valid JSON — no extra text."""

MARKET_AGENT_PROMPT = """Analyze the following Solana token market data and return a JSON assessment.

Token: {symbol} ({mint_address})

Market Data:
- Current Price: ${price_usd}
- Price Change (5m): {price_change_5m}%
- Price Change (1h): {price_change_1h}%
- Price Change (6h): {price_change_6h}%
- Price Change (24h): {price_change_24h}%
- Volume (5m): ${volume_5m}
- Volume (1h): ${volume_1h}
- Volume (24h): ${volume_24h}
- Liquidity: ${liquidity}
- Buys (1h): {buys_1h}
- Sells (1h): {sells_1h}
- Buy/Sell Ratio (1h): {buy_sell_ratio}
- Market Cap: ${market_cap}
- Token Age: {token_age_hours} hours

Return ONLY this JSON:
{{
  "score": <0-100 market health score>,
  "trend": "<bullish|neutral|bearish>",
  "momentum": "<strong|moderate|weak|negative>",
  "volume_quality": "<organic|suspicious|low>",
  "signals": [<list of observed positive signals, max 5>],
  "risks": [<list of observed risks, max 3>],
  "summary": "<2-3 sentence professional summary>",
  "key_level": "<price level to watch>"
}}"""


class MarketAgent(BaseAgent):
    """
    Analyzes price action, volume, and market momentum.
    Returns a market health score and trend assessment.
    """

    name = "market_agent"
    system_prompt = MARKET_AGENT_SYSTEM

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        token = context.get("token", {})
        symbol = token.get("symbol") or token.get("mint_address", "")[:8]

        # Calculate derived metrics
        buys = token.get("buys_1h", 0) or 0
        sells = token.get("sells_1h", 0) or 0
        buy_sell_ratio = round(buys / sells, 2) if sells > 0 else (buys if buys > 0 else 0)

        prompt = MARKET_AGENT_PROMPT.format(
            symbol=symbol,
            mint_address=token.get("mint_address", ""),
            price_usd=f"{float(token.get('price_usd', 0) or 0):.8f}",
            price_change_5m=f"{token.get('price_change_5m', 0) or 0:.1f}",
            price_change_1h=f"{token.get('price_change_1h', 0) or 0:.1f}",
            price_change_6h=f"{token.get('price_change_6h', 0) or 0:.1f}",
            price_change_24h=f"{token.get('price_change_24h', 0) or 0:.1f}",
            volume_5m=f"{float(token.get('volume_5m_usd', 0) or 0):,.0f}",
            volume_1h=f"{float(token.get('volume_1h_usd', 0) or 0):,.0f}",
            volume_24h=f"{float(token.get('volume_24h_usd', 0) or 0):,.0f}",
            liquidity=f"{float(token.get('liquidity_usd', 0) or 0):,.0f}",
            buys_1h=buys,
            sells_1h=sells,
            buy_sell_ratio=buy_sell_ratio,
            market_cap=f"{float(token.get('market_cap_usd', 0) or 0):,.0f}",
            token_age_hours=context.get("token_age_hours", "unknown"),
        )

        response, tokens_used = await self._call_llm(
            prompt,
            response_format={"type": "json_object"},
        )
        parsed = self._parse_json_response(response)

        if not parsed:
            return {
                "score": 50, "trend": "neutral", "momentum": "weak",
                "volume_quality": "unknown", "signals": [], "risks": [],
                "summary": "Market analysis unavailable.",
                "tokens_used": tokens_used,
            }

        parsed["tokens_used"] = tokens_used
        return parsed
