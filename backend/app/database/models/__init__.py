"""
Centralized model imports.
Import all models here so Alembic can discover them for autogenerate.
"""

from app.database.models.token import Token, TokenPriceHistory
from app.database.models.wallet import Wallet, WalletTrade, WalletHolding
from app.database.models.market_event import MarketEvent
from app.database.models.alert import Alert
from app.database.models.analysis import AIAnalysis

__all__ = [
    "Token",
    "TokenPriceHistory",
    "Wallet",
    "WalletTrade",
    "WalletHolding",
    "MarketEvent",
    "Alert",
    "AIAnalysis",
]
