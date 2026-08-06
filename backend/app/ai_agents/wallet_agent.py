"""
Wallet Agent — analyzes smart money behavior in a specific token.
"""

from typing import Any, Dict, List

from app.ai_agents.base_agent import BaseAgent


WALLET_AGENT_SYSTEM = """You are a smart money analyst for Solana DEX trading.
You specialize in identifying which wallets are making intelligent, profitable trades
versus which are retail noise or wash trading.
Only return valid JSON — no extra text."""

WALLET_AGENT_PROMPT = """Analyze the following smart money wallet activity for a Solana token.

Token: {symbol} ({mint_address})
Current Price: ${price_usd}

Smart Money Wallets Currently Holding This Token:
{smart_wallet_data}

Recent Smart Money Trades:
{smart_trades}

Aggregate Metrics:
- Smart Wallets Entered (recent): {sm_entered}
- Smart Wallets Exited (recent): {sm_exited}
- Average Smart Wallet Score: {avg_wallet_score}
- Net Smart Money Flow: {net_flow}

Return ONLY this JSON:
{{
  "score": <0-100, smart money conviction score>,
  "conviction": "<strong|moderate|weak|mixed>",
  "flow_direction": "<accumulating|distributing|mixed|neutral>",
  "smart_wallet_count": {sm_entered},
  "avg_entry_quality": "<early|on-time|late>",
  "signals": [<list of significant smart money observations, max 5>],
  "risks": [<potential risks from smart money behavior, max 3>],
  "summary": "<2-3 sentence smart money assessment>",
  "confidence": <0.0-1.0>
}}"""


class WalletAgent(BaseAgent):
    name = "wallet_agent"
    system_prompt = WALLET_AGENT_SYSTEM

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        token = context.get("token", {})
        smart_wallets = context.get("smart_wallets", [])
        recent_smart_trades = context.get("recent_smart_trades", [])
        symbol = token.get("symbol") or token.get("mint_address", "")[:8]

        # Format smart wallet holders
        if smart_wallets:
            holder_lines = []
            for w in smart_wallets[:8]:
                holder_lines.append(
                    f"- {str(w.get('address', ''))[:8]}... "
                    f"Score={w.get('score', 'N/A')}, "
                    f"WinRate={w.get('win_rate', 0):.0%}, "
                    f"PnL=${float(w.get('total_pnl_usd', 0) or 0):,.0f}"
                )
            smart_wallet_data = "\n".join(holder_lines)
        else:
            smart_wallet_data = "No tracked smart wallets currently holding."

        # Format recent smart trades
        if recent_smart_trades:
            trade_lines = []
            for t in recent_smart_trades[:8]:
                trade_lines.append(
                    f"- {t.get('trade_type', '?').upper()} "
                    f"${float(t.get('amount_usd', 0) or 0):,.0f} "
                    f"by {str(t.get('wallet', ''))[:8]}..."
                )
            smart_trades = "\n".join(trade_lines)
        else:
            smart_trades = "No recent smart money trades."

        entered = context.get("sm_entered_count", 0)
        exited = context.get("sm_exited_count", 0)
        net_flow = "positive" if entered > exited else "negative" if exited > entered else "neutral"

        prompt = WALLET_AGENT_PROMPT.format(
            symbol=symbol,
            mint_address=token.get("mint_address", ""),
            price_usd=f"{float(token.get('price_usd', 0) or 0):.8f}",
            smart_wallet_data=smart_wallet_data,
            smart_trades=smart_trades,
            sm_entered=entered,
            sm_exited=exited,
            avg_wallet_score=context.get("avg_wallet_score", "N/A"),
            net_flow=net_flow,
        )

        response, tokens_used = await self._call_llm(
            prompt,
            response_format={"type": "json_object"},
        )
        parsed = self._parse_json_response(response)

        if not parsed:
            return {
                "score": 50, "conviction": "neutral", "flow_direction": "neutral",
                "smart_wallet_count": entered, "avg_entry_quality": "unknown",
                "signals": [], "risks": [], "summary": "Smart money analysis unavailable.",
                "confidence": 0.5, "tokens_used": tokens_used,
            }

        parsed["tokens_used"] = tokens_used
        return parsed
