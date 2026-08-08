"""
Core application configuration.
All settings are loaded from environment variables with sane defaults.
Uses Pydantic Settings for validation and type safety.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "Solana DEX Trader Intelligence Platform"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = Field(default="development", pattern="^(development|staging|production)$")
    DEBUG: bool = False
    SECRET_KEY: str = Field(min_length=32)
    API_V1_PREFIX: str = "/api/v1"

    # Key required by write endpoints in production. Generate one with
    # app.core.security.generate_api_key(); requests present it as X-API-Key.
    API_KEY: str = ""

    # CORS — comma-separated list of allowed origins
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # ─── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str  # async: postgresql+asyncpg://...
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_ECHO: bool = False  # Set True to log all SQL

    # ─── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str  # redis://:password@host:port/db
    REDIS_POOL_SIZE: int = 20
    REDIS_DECODE_RESPONSES: bool = True

    # Cache TTLs (seconds)
    CACHE_TTL_SHORT: int = 30       # 30 seconds — live prices
    CACHE_TTL_MEDIUM: int = 300     # 5 minutes  — token metadata
    CACHE_TTL_LONG: int = 3600      # 1 hour     — wallet scores
    CACHE_TTL_VERY_LONG: int = 86400 # 24 hours  — static data

    # ─── Celery ───────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = ""      # Defaults to REDIS_URL if empty
    CELERY_RESULT_BACKEND: str = ""  # Defaults to REDIS_URL if empty
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: List[str] = ["json"]
    CELERY_TIMEZONE: str = "UTC"
    CELERY_TASK_TRACK_STARTED: bool = True
    CELERY_TASK_SOFT_TIME_LIMIT: int = 300   # 5 min soft limit
    CELERY_TASK_TIME_LIMIT: int = 600        # 10 min hard limit

    # ─── Solana RPC ───────────────────────────────────────────────────────────
    SOLANA_RPC_URL: str = "https://api.mainnet-beta.solana.com"
    SOLANA_RPC_WS_URL: str = "wss://api.mainnet-beta.solana.com"
    SOLANA_RPC_TIMEOUT: int = 30
    SOLANA_MAX_RETRIES: int = 3

    # ─── Helius API ───────────────────────────────────────────────────────────
    HELIUS_API_KEY: str = ""
    HELIUS_BASE_URL: str = "https://api.helius.xyz/v0"
    HELIUS_RPC_URL: str = ""  # Populated in validator below

    # ─── DexScreener API ──────────────────────────────────────────────────────
    DEXSCREENER_BASE_URL: str = "https://api.dexscreener.com/latest"
    DEXSCREENER_RATE_LIMIT: int = 300  # requests per minute (free tier)

    # ─── Birdeye API ──────────────────────────────────────────────────────────
    BIRDEYE_API_KEY: str = ""
    BIRDEYE_BASE_URL: str = "https://public-api.birdeye.so"
    BIRDEYE_RATE_LIMIT: int = 100  # requests per minute

    # ─── Jupiter API ──────────────────────────────────────────────────────────
    JUPITER_BASE_URL: str = "https://price.jup.ag/v4"

    # ─── AI / OpenAI ──────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"         # Default model for agents
    OPENAI_MODEL_ADVANCED: str = "gpt-4o"     # For Trader Agent (final synthesis)
    OPENAI_MAX_TOKENS: int = 2000
    OPENAI_TEMPERATURE: float = 0.2            # Low temp for consistent analysis
    OPENAI_REQUEST_TIMEOUT: int = 60

    # ─── Telegram Bot ─────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""                # Default channel for alerts
    TELEGRAM_ALERT_CHAT_ID: str = ""          # High-priority alerts channel
    TELEGRAM_RATE_LIMIT: int = 30             # messages per second

    # ─── Data Collection Intervals (seconds) ─────────────────────────────────
    COLLECT_NEW_TOKENS_INTERVAL: int = 60       # Check for new tokens every 1 min
    COLLECT_PRICES_INTERVAL: int = 15           # Update prices every 15 sec
    COLLECT_VOLUMES_INTERVAL: int = 60          # Update volumes every 1 min
    COLLECT_TRANSACTIONS_INTERVAL: int = 30     # Fetch transactions every 30 sec
    COLLECT_WALLETS_INTERVAL: int = 300         # Analyze wallets every 5 min
    MONITOR_EVENTS_INTERVAL: int = 30           # Check for market events every 30 sec

    # ─── Market Monitoring Thresholds ─────────────────────────────────────────
    VOLUME_SPIKE_THRESHOLD: float = 200.0       # % increase to trigger volume spike
    PRICE_SPIKE_THRESHOLD: float = 20.0         # % increase to trigger price spike
    LIQUIDITY_SPIKE_THRESHOLD: float = 50.0     # % increase in liquidity
    WHALE_TX_THRESHOLD_SOL: float = 500.0       # SOL value to classify as whale tx
    SMART_MONEY_MIN_WIN_RATE: float = 0.65      # Min win rate to be "smart money"
    SMART_MONEY_MIN_TRADES: int = 20            # Min trades to qualify

    # ─── Token Security Thresholds ─────────────────────────────────────────────
    MAX_HOLDER_CONCENTRATION: float = 0.30      # Max % for top holder (rug flag)
    MAX_DEV_WALLET_HOLD: float = 0.15           # Max % dev wallet can hold
    MIN_LIQUIDITY_USD: float = 10000.0          # Min liquidity to consider a token
    MIN_TOKEN_AGE_HOURS: int = 1                # Min age before analysis

    # ─── Scoring Weights ──────────────────────────────────────────────────────
    SCORE_WEIGHT_SECURITY: float = 0.25
    SCORE_WEIGHT_SMART_MONEY: float = 0.25
    SCORE_WEIGHT_VOLUME: float = 0.20
    SCORE_WEIGHT_LIQUIDITY: float = 0.15
    SCORE_WEIGHT_SOCIAL: float = 0.15

    # ─── Pagination ───────────────────────────────────────────────────────────
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # ─── Logging ──────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"   # "json" | "text"
    LOG_FILE: str = "logs/app.log"
    LOG_ROTATION: str = "1 day"
    LOG_RETENTION: str = "30 days"

    # ─── Validators ───────────────────────────────────────────────────────────
    @model_validator(mode="after")
    def populate_derived_urls(self) -> "Settings":
        """Auto-populate derived URLs from base keys."""
        if self.HELIUS_API_KEY and not self.HELIUS_RPC_URL:
            self.HELIUS_RPC_URL = (
                f"https://mainnet.helius-rpc.com/?api-key={self.HELIUS_API_KEY}"
            )
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = self.REDIS_URL
        return self

    @field_validator("SCORE_WEIGHT_SECURITY", "SCORE_WEIGHT_SMART_MONEY",
                     "SCORE_WEIGHT_VOLUME", "SCORE_WEIGHT_LIQUIDITY",
                     "SCORE_WEIGHT_SOCIAL", mode="before")
    @classmethod
    def validate_weights(cls, v: float) -> float:
        if not 0.0 <= float(v) <= 1.0:
            raise ValueError("Score weights must be between 0.0 and 1.0")
        return float(v)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def effective_rpc_url(self) -> str:
        """Return Helius RPC if key is set, otherwise fallback to public RPC."""
        return self.HELIUS_RPC_URL if self.HELIUS_RPC_URL else self.SOLANA_RPC_URL


@lru_cache
def get_settings() -> Settings:
    """
    Returns cached Settings instance.
    Use as a FastAPI dependency: settings = Depends(get_settings)
    """
    return Settings()


# Module-level singleton for non-DI usage
settings = get_settings()
