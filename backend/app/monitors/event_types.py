"""
Market event type definitions, severity levels, and helper factories.
Single source of truth for all event classifications.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


# ─── Event Type Constants ─────────────────────────────────────────────────────

class EventType:
    VOLUME_SPIKE       = "VOLUME_SPIKE"
    PRICE_SPIKE        = "PRICE_SPIKE"
    PRICE_DROP         = "PRICE_DROP"
    LIQUIDITY_ADD      = "LIQUIDITY_ADD"
    LIQUIDITY_REMOVE   = "LIQUIDITY_REMOVE"
    WHALE_BUY          = "WHALE_BUY"
    WHALE_SELL         = "WHALE_SELL"
    SMART_MONEY_ENTRY  = "SMART_MONEY_ENTRY"
    SMART_MONEY_EXIT   = "SMART_MONEY_EXIT"
    NEW_TOKEN          = "NEW_TOKEN"
    MOMENTUM           = "MOMENTUM"       # Multiple positive signals combined
    RUG_RISK           = "RUG_RISK"       # Security red flags detected
    BUY_PRESSURE       = "BUY_PRESSURE"   # High buy/sell ratio
    TX_ACCELERATION    = "TX_ACCELERATION" # Transaction count spike


class Severity:
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


# ─── Event Data Container ─────────────────────────────────────────────────────

@dataclass
class DetectedEvent:
    """
    Intermediate event object produced by detectors.
    Converted to a MarketEvent DB record by the monitor.
    """
    token_id: str          # UUID as string
    token_mint: str
    token_symbol: Optional[str]
    event_type: str
    severity: str
    title: str
    description: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Market context at time of event
    price_usd: Optional[float] = None
    volume_usd: Optional[float] = None
    liquidity_usd: Optional[float] = None
    volume_change_pct: Optional[float] = None
    price_change_pct: Optional[float] = None
    liquidity_change_pct: Optional[float] = None

    # Smart money context
    smart_wallets_count: int = 0
    smart_wallets_addresses: Optional[List[str]] = None
    whale_wallet_address: Optional[str] = None
    whale_amount_usd: Optional[float] = None

    extra_data: Optional[dict] = None


# ─── Event Factories ──────────────────────────────────────────────────────────

def make_volume_spike_event(
    token_id: str,
    token_mint: str,
    token_symbol: Optional[str],
    prev_vol: float,
    current_vol: float,
    change_pct: float,
    price_usd: Optional[float] = None,
    liquidity_usd: Optional[float] = None,
) -> DetectedEvent:
    severity = (
        Severity.CRITICAL if change_pct >= 1000
        else Severity.HIGH if change_pct >= 500
        else Severity.MEDIUM if change_pct >= 200
        else Severity.LOW
    )
    return DetectedEvent(
        token_id=token_id,
        token_mint=token_mint,
        token_symbol=token_symbol,
        event_type=EventType.VOLUME_SPIKE,
        severity=severity,
        title=f"🔥 Volume Spike: {token_symbol or token_mint[:8]}",
        description=(
            f"Volume surged +{change_pct:.0f}% from "
            f"${prev_vol:,.0f} to ${current_vol:,.0f} in the last window."
        ),
        price_usd=price_usd,
        volume_usd=current_vol,
        liquidity_usd=liquidity_usd,
        volume_change_pct=change_pct,
    )


def make_price_spike_event(
    token_id: str,
    token_mint: str,
    token_symbol: Optional[str],
    change_pct: float,
    price_usd: float,
    timeframe: str = "5m",
) -> DetectedEvent:
    severity = (
        Severity.CRITICAL if change_pct >= 100
        else Severity.HIGH if change_pct >= 50
        else Severity.MEDIUM if change_pct >= 20
        else Severity.LOW
    )
    return DetectedEvent(
        token_id=token_id,
        token_mint=token_mint,
        token_symbol=token_symbol,
        event_type=EventType.PRICE_SPIKE,
        severity=severity,
        title=f"🚀 Price Spike: {token_symbol or token_mint[:8]}",
        description=f"Price jumped +{change_pct:.1f}% in the last {timeframe}.",
        price_usd=price_usd,
        price_change_pct=change_pct,
    )


def make_whale_event(
    token_id: str,
    token_mint: str,
    token_symbol: Optional[str],
    wallet_address: str,
    amount_usd: float,
    trade_type: str,  # "buy" | "sell"
    price_usd: Optional[float] = None,
) -> DetectedEvent:
    is_buy = trade_type.lower() == "buy"
    event_type = EventType.WHALE_BUY if is_buy else EventType.WHALE_SELL
    emoji = "🐋" if is_buy else "⚠️"
    direction = "bought" if is_buy else "sold"
    severity = Severity.HIGH if amount_usd >= 100_000 else Severity.MEDIUM

    return DetectedEvent(
        token_id=token_id,
        token_mint=token_mint,
        token_symbol=token_symbol,
        event_type=event_type,
        severity=severity,
        title=f"{emoji} Whale {direction.title()}: {token_symbol or token_mint[:8]}",
        description=(
            f"Whale wallet {wallet_address[:8]}... {direction} "
            f"${amount_usd:,.0f} worth of {token_symbol or 'tokens'}."
        ),
        price_usd=price_usd,
        whale_wallet_address=wallet_address,
        whale_amount_usd=amount_usd,
    )


def make_smart_money_event(
    token_id: str,
    token_mint: str,
    token_symbol: Optional[str],
    wallet_addresses: List[str],
    trade_type: str,
    price_usd: Optional[float] = None,
    volume_usd: Optional[float] = None,
) -> DetectedEvent:
    is_entry = trade_type.lower() == "buy"
    event_type = EventType.SMART_MONEY_ENTRY if is_entry else EventType.SMART_MONEY_EXIT
    count = len(wallet_addresses)
    direction = "entered" if is_entry else "exited"
    severity = Severity.HIGH if count >= 3 else Severity.MEDIUM

    return DetectedEvent(
        token_id=token_id,
        token_mint=token_mint,
        token_symbol=token_symbol,
        event_type=event_type,
        severity=severity,
        title=f"🧠 Smart Money {direction.title()}: {token_symbol or token_mint[:8]}",
        description=(
            f"{count} smart money wallet{'s' if count > 1 else ''} "
            f"{direction} position in {token_symbol or 'this token'}."
        ),
        price_usd=price_usd,
        volume_usd=volume_usd,
        smart_wallets_count=count,
        smart_wallets_addresses=wallet_addresses,
    )


def make_momentum_event(
    token_id: str,
    token_mint: str,
    token_symbol: Optional[str],
    signals: List[str],
    price_usd: Optional[float] = None,
    volume_usd: Optional[float] = None,
    liquidity_usd: Optional[float] = None,
    smart_wallet_count: int = 0,
) -> DetectedEvent:
    signal_count = len(signals)
    severity = (
        Severity.CRITICAL if signal_count >= 4
        else Severity.HIGH if signal_count >= 3
        else Severity.MEDIUM
    )
    return DetectedEvent(
        token_id=token_id,
        token_mint=token_mint,
        token_symbol=token_symbol,
        event_type=EventType.MOMENTUM,
        severity=severity,
        title=f"⚡ Momentum Signal: {token_symbol or token_mint[:8]}",
        description=f"Multiple bullish signals detected: {', '.join(signals)}.",
        price_usd=price_usd,
        volume_usd=volume_usd,
        liquidity_usd=liquidity_usd,
        smart_wallets_count=smart_wallet_count,
        extra_data={"signals": signals},
    )


def make_rug_risk_event(
    token_id: str,
    token_mint: str,
    token_symbol: Optional[str],
    risk_factors: List[str],
    rug_probability: float,
) -> DetectedEvent:
    severity = (
        Severity.CRITICAL if rug_probability >= 0.8
        else Severity.HIGH if rug_probability >= 0.6
        else Severity.MEDIUM
    )
    return DetectedEvent(
        token_id=token_id,
        token_mint=token_mint,
        token_symbol=token_symbol,
        event_type=EventType.RUG_RISK,
        severity=severity,
        title=f"🚨 Rug Risk Alert: {token_symbol or token_mint[:8]}",
        description=(
            f"Security scan detected {len(risk_factors)} risk factor(s). "
            f"Rug probability: {rug_probability:.0%}. Risks: {', '.join(risk_factors[:3])}."
        ),
        extra_data={"risk_factors": risk_factors, "rug_probability": rug_probability},
    )


def make_new_token_event(
    token_id: str,
    token_mint: str,
    token_symbol: Optional[str],
    liquidity_usd: float,
    dex_id: Optional[str] = None,
) -> DetectedEvent:
    severity = Severity.MEDIUM if liquidity_usd >= 50_000 else Severity.LOW
    return DetectedEvent(
        token_id=token_id,
        token_mint=token_mint,
        token_symbol=token_symbol,
        event_type=EventType.NEW_TOKEN,
        severity=severity,
        title=f"🆕 New Token: {token_symbol or token_mint[:8]}",
        description=(
            f"New token launched on {dex_id or 'Solana DEX'} "
            f"with ${liquidity_usd:,.0f} initial liquidity."
        ),
        liquidity_usd=liquidity_usd,
    )
