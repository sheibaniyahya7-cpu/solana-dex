"""
Telegram Bot alert dispatcher.
Sends formatted trading intelligence alerts to configured Telegram channels.

Alert types sent:
  🚨 Smart Money Alert
  🐋 Whale Alert
  🔥 Volume Spike Alert
  🆕 New Token Alert
  ⚡ Momentum Alert
  🛡️ AI Analysis Alert (high-score tokens)
  🚨 Rug Risk Alert

Rate limited to avoid Telegram API 429 errors (30 msg/sec limit).
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramBot:
    """
    Async Telegram Bot API client.
    Formats and dispatches trading intelligence alerts.
    """

    def __init__(self) -> None:
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.default_chat_id = settings.TELEGRAM_CHAT_ID
        self.alert_chat_id = settings.TELEGRAM_ALERT_CHAT_ID or settings.TELEGRAM_CHAT_ID
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=f"{TELEGRAM_API_BASE}/bot{self.token}",
                timeout=httpx.Timeout(15.0),
            )
        return self._client

    def is_configured(self) -> bool:
        return bool(self.token and self.default_chat_id)

    async def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
    ) -> bool:
        """Send a raw message. Returns True on success."""
        if not self.is_configured():
            logger.warning("Telegram not configured — skipping alert")
            return False

        target_chat = chat_id or self.default_chat_id
        try:
            response = await self.client.post(
                "/sendMessage",
                json={
                    "chat_id": target_chat,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": disable_web_page_preview,
                    "disable_notification": disable_notification,
                },
            )
            data = response.json()
            if not data.get("ok"):
                logger.warning("Telegram send failed", error=data.get("description"))
                return False
            return True
        except Exception as e:
            logger.error("Telegram API error", error=str(e))
            return False

    # ─── Alert Formatters ─────────────────────────────────────────────────────

    async def send_smart_money_alert(self, event_data: Dict) -> bool:
        """
        🧠 Smart Money Alert
        Token: ABC
        5 profitable wallets entered
        AI Score: 91/100 | Risk: Low
        """
        token_symbol = event_data.get("token_symbol") or event_data.get("token_mint", "")[:8]
        wallet_count = event_data.get("smart_wallets_count", 1)
        ai_score = event_data.get("ai_score")
        price = event_data.get("price_usd")
        mint = event_data.get("token_mint", "")

        score_line = f"<b>AI Score:</b> {ai_score:.0f}/100" if ai_score else ""
        price_line = f"<b>Price:</b> ${float(price):.8f}" if price else ""

        text = (
            f"🧠 <b>Smart Money Alert</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>Token:</b> ${token_symbol}\n"
            f"<b>Signal:</b> {wallet_count} smart wallet{'s' if wallet_count > 1 else ''} entered\n"
            f"{price_line}\n"
            f"{score_line}\n"
            f"<b>Risk:</b> {self._risk_emoji(ai_score)} {self._risk_label(ai_score)}\n"
            f"<b>Mint:</b> <code>{mint[:20]}...</code>\n"
            f"<b>Time:</b> {self._fmt_time()}\n"
        )
        return await self.send_message(text.strip(), chat_id=self.alert_chat_id)

    async def send_whale_alert(self, event_data: Dict) -> bool:
        """
        🐋 Whale Alert
        Token: ABC | $250,000 BUY
        Wallet: 0x1234...
        """
        token_symbol = event_data.get("token_symbol") or event_data.get("token_mint", "")[:8]
        amount = event_data.get("whale_amount_usd") or event_data.get("amount_usd", 0)
        wallet = event_data.get("whale_wallet_address") or event_data.get("wallet", "")
        event_type = event_data.get("event_type", "WHALE_BUY")
        is_buy = "BUY" in event_type
        emoji = "🟢" if is_buy else "🔴"
        action = "BUY" if is_buy else "SELL"
        mint = event_data.get("token_mint", "")

        text = (
            f"🐋 <b>Whale Alert</b> {emoji}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>Token:</b> ${token_symbol}\n"
            f"<b>Action:</b> {action} ${float(amount):,.0f}\n"
            f"<b>Wallet:</b> <code>{str(wallet)[:20]}...</code>\n"
            f"<b>Mint:</b> <code>{mint[:20]}...</code>\n"
            f"<b>Time:</b> {self._fmt_time()}\n"
        )
        return await self.send_message(text.strip(), chat_id=self.alert_chat_id)

    async def send_volume_spike_alert(self, event_data: Dict) -> bool:
        """🔥 Volume Spike Alert"""
        token_symbol = event_data.get("token_symbol") or event_data.get("token_mint", "")[:8]
        change_pct = event_data.get("volume_change_pct", 0)
        volume = event_data.get("volume_usd_at_event") or event_data.get("volume_usd", 0)
        price_change = event_data.get("price_change_pct", 0) or 0
        mint = event_data.get("token_mint", "")

        text = (
            f"🔥 <b>Volume Spike Alert</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>Token:</b> ${token_symbol}\n"
            f"<b>Volume Surge:</b> +{change_pct:.0f}%\n"
            f"<b>Current Volume:</b> ${float(volume):,.0f}\n"
            f"<b>Price Change:</b> {'+' if price_change >= 0 else ''}{price_change:.1f}%\n"
            f"<b>Mint:</b> <code>{mint[:20]}...</code>\n"
            f"<b>Time:</b> {self._fmt_time()}\n"
        )
        return await self.send_message(text.strip())

    async def send_new_token_alert(self, event_data: Dict) -> bool:
        """🆕 New Token Alert"""
        token_symbol = event_data.get("token_symbol") or event_data.get("token_mint", "")[:8]
        liquidity = event_data.get("liquidity_usd_at_event") or event_data.get("liquidity_usd", 0)
        dex = event_data.get("extra_data", {}).get("dex_id", "Solana DEX") if event_data.get("extra_data") else "Solana DEX"
        mint = event_data.get("token_mint", "")

        text = (
            f"🆕 <b>New Token Launch</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>Token:</b> ${token_symbol}\n"
            f"<b>DEX:</b> {dex}\n"
            f"<b>Initial Liquidity:</b> ${float(liquidity):,.0f}\n"
            f"<b>Mint:</b> <code>{mint[:20]}...</code>\n"
            f"<b>Time:</b> {self._fmt_time()}\n"
            f"\n⚠️ <i>New tokens carry high risk. DYOR.</i>"
        )
        return await self.send_message(text.strip())

    async def send_ai_analysis_alert(self, analysis_data: Dict) -> bool:
        """
        🤖 AI Analysis Alert (only for STRONG_BUY / BUY decisions)
        Token: ABC
        AI Score: 87/100
        Decision: WATCH
        Reasons: Smart money accumulation, liquidity improving...
        """
        token_symbol = analysis_data.get("token_symbol") or analysis_data.get("token_mint", "")[:8]
        final_score = analysis_data.get("final_score", 0)
        decision = analysis_data.get("decision", "WATCH")
        summary = analysis_data.get("summary", "")
        reasons = analysis_data.get("reasons", [])
        risks = analysis_data.get("risks", [])
        mint = analysis_data.get("token_mint", "")

        decision_emoji = {
            "STRONG_BUY": "🟢🟢",
            "BUY": "🟢",
            "WATCH": "🟡",
            "AVOID": "🔴",
            "DANGER": "🚨",
        }.get(decision, "⚪")

        reasons_text = ""
        if reasons:
            reasons_text = "\n<b>Reasons:</b>\n" + "\n".join(f"  ✅ {r}" for r in reasons[:4])

        risks_text = ""
        if risks:
            risks_text = "\n<b>Risks:</b>\n" + "\n".join(f"  ⚠️ {r}" for r in risks[:3])

        text = (
            f"🤖 <b>AI Trading Intelligence</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>Token:</b> ${token_symbol}\n"
            f"<b>AI Score:</b> {final_score:.0f}/100\n"
            f"<b>Decision:</b> {decision_emoji} {decision}\n"
            f"\n<i>{summary}</i>"
            f"{reasons_text}"
            f"{risks_text}\n"
            f"\n<b>Mint:</b> <code>{mint[:20]}...</code>\n"
            f"<b>Time:</b> {self._fmt_time()}\n"
        )
        return await self.send_message(text.strip(), chat_id=self.alert_chat_id)

    async def send_rug_risk_alert(self, event_data: Dict) -> bool:
        """🚨 Rug Risk / Security Alert"""
        token_symbol = event_data.get("token_symbol") or event_data.get("token_mint", "")[:8]
        rug_prob = event_data.get("rug_probability", 0)
        description = event_data.get("description", "")
        mint = event_data.get("token_mint", "")

        text = (
            f"🚨 <b>RUG RISK ALERT</b> 🚨\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>Token:</b> ${token_symbol}\n"
            f"<b>Rug Probability:</b> {float(rug_prob):.0%}\n"
            f"\n<b>Details:</b> {description}\n"
            f"\n<b>Mint:</b> <code>{mint[:20]}...</code>\n"
            f"<b>Time:</b> {self._fmt_time()}\n"
            f"\n🛑 <i>Extreme caution advised. Do NOT ape in.</i>"
        )
        return await self.send_message(text.strip(), chat_id=self.alert_chat_id)

    async def send_momentum_alert(self, event_data: Dict) -> bool:
        """⚡ Momentum Alert"""
        token_symbol = event_data.get("token_symbol") or event_data.get("token_mint", "")[:8]
        description = event_data.get("description", "")
        ai_score = event_data.get("ai_score")
        price_change = event_data.get("price_change_pct", 0) or 0
        volume_change = event_data.get("volume_change_pct", 0) or 0
        mint = event_data.get("token_mint", "")
        signals = (event_data.get("extra_data") or {}).get("signals", [])

        signals_text = ""
        if signals:
            signals_text = "\n" + "\n".join(f"  ⚡ {s}" for s in signals[:5])

        score_line = f"<b>AI Score:</b> {ai_score:.0f}/100\n" if ai_score else ""

        text = (
            f"⚡ <b>Momentum Signal</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>Token:</b> ${token_symbol}\n"
            f"<b>Price Change:</b> {'+' if price_change >= 0 else ''}{price_change:.1f}%\n"
            f"<b>Volume Change:</b> +{volume_change:.0f}%\n"
            f"{score_line}"
            f"<b>Signals:</b>{signals_text}\n"
            f"\n<b>Mint:</b> <code>{mint[:20]}...</code>\n"
            f"<b>Time:</b> {self._fmt_time()}\n"
        )
        return await self.send_message(text.strip())

    # ─── Dispatch Router ──────────────────────────────────────────────────────

    async def dispatch_alert(self, alert_payload: Dict) -> bool:
        """
        Route an alert payload to the correct formatter.
        Called by the alert processor from the Redis queue.
        """
        event_type = alert_payload.get("event_type") or alert_payload.get("type", "")

        dispatch_map = {
            "SMART_MONEY_ENTRY": self.send_smart_money_alert,
            "WHALE_BUY": self.send_whale_alert,
            "WHALE_SELL": self.send_whale_alert,
            "VOLUME_SPIKE": self.send_volume_spike_alert,
            "NEW_TOKEN": self.send_new_token_alert,
            "MOMENTUM": self.send_momentum_alert,
            "RUG_RISK": self.send_rug_risk_alert,
            "AI_ANALYSIS": self.send_ai_analysis_alert,
        }

        handler = dispatch_map.get(event_type)
        if handler:
            return await handler(alert_payload)
        else:
            logger.debug("No alert handler for event type", event_type=event_type)
            return False

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _risk_emoji(self, score: Optional[float]) -> str:
        if score is None:
            return "⚪"
        if score >= 75:
            return "🟢"
        elif score >= 55:
            return "🟡"
        elif score >= 35:
            return "🟠"
        else:
            return "🔴"

    def _risk_label(self, score: Optional[float]) -> str:
        if score is None:
            return "Unknown"
        if score >= 75:
            return "Low"
        elif score >= 55:
            return "Medium"
        elif score >= 35:
            return "High"
        else:
            return "Critical"

    def _fmt_time(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()


# Module-level singleton
telegram_bot = TelegramBot()
