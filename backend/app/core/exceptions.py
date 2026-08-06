"""
Custom application exceptions.
All domain-specific errors inherit from DexBaseException.
FastAPI exception handlers are registered in app/main.py.
"""

from typing import Any, Optional


class DexBaseException(Exception):
    """Base exception for the DEX Trader platform."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: Optional[str] = None,
        details: Optional[Any] = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.details = details
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


# ─── HTTP 4xx ─────────────────────────────────────────────────────────────────

class NotFoundException(DexBaseException):
    status_code = 404
    error_code = "NOT_FOUND"
    message = "Resource not found."


class ValidationException(DexBaseException):
    status_code = 422
    error_code = "VALIDATION_ERROR"
    message = "Validation failed."


class RateLimitException(DexBaseException):
    status_code = 429
    error_code = "RATE_LIMITED"
    message = "Rate limit exceeded. Please slow down."


class UnauthorizedException(DexBaseException):
    status_code = 401
    error_code = "UNAUTHORIZED"
    message = "Authentication required."


class ForbiddenException(DexBaseException):
    status_code = 403
    error_code = "FORBIDDEN"
    message = "Access denied."


# ─── Data Collection Errors ───────────────────────────────────────────────────

class CollectorException(DexBaseException):
    status_code = 502
    error_code = "COLLECTOR_ERROR"
    message = "Failed to collect data from external source."


class SolanaRPCException(CollectorException):
    error_code = "SOLANA_RPC_ERROR"
    message = "Solana RPC request failed."


class HeliusAPIException(CollectorException):
    error_code = "HELIUS_API_ERROR"
    message = "Helius API request failed."


class DexScreenerAPIException(CollectorException):
    error_code = "DEXSCREENER_API_ERROR"
    message = "DexScreener API request failed."


class BirdeyeAPIException(CollectorException):
    error_code = "BIRDEYE_API_ERROR"
    message = "Birdeye API request failed."


# ─── Analysis Errors ──────────────────────────────────────────────────────────

class AnalysisException(DexBaseException):
    status_code = 500
    error_code = "ANALYSIS_ERROR"
    message = "Analysis failed."


class AIAgentException(AnalysisException):
    error_code = "AI_AGENT_ERROR"
    message = "AI agent analysis failed."


class InsufficientDataException(AnalysisException):
    status_code = 422
    error_code = "INSUFFICIENT_DATA"
    message = "Not enough data to perform analysis."


# ─── Alert Errors ─────────────────────────────────────────────────────────────

class AlertException(DexBaseException):
    status_code = 500
    error_code = "ALERT_ERROR"
    message = "Failed to send alert."


class TelegramException(AlertException):
    error_code = "TELEGRAM_ERROR"
    message = "Telegram notification failed."
