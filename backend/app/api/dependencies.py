"""
Shared FastAPI dependencies used across multiple endpoints.
"""

from typing import Optional
from fastapi import Header, HTTPException, status
from app.core.config import settings
from app.core.security import hash_api_key, verify_api_key
from app.core.logging import get_logger

logger = get_logger(__name__)


async def require_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    """
    API key verification for write operations.
    Read endpoints are public in this MVP; development skips the check entirely.

    Fails closed: if no key is configured in production, protected endpoints are
    refused rather than left open to anyone.
    """
    if not settings.is_production:
        return "dev"  # Skip auth in development

    if not settings.API_KEY:
        logger.error("API_KEY is not configured — refusing authenticated request")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server is missing its API key configuration.",
        )

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header is required",
        )

    if not verify_api_key(x_api_key, hash_api_key(settings.API_KEY)):
        logger.warning("Rejected request with invalid API key")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return x_api_key


def get_pagination(
    page: int = 1,
    page_size: int = settings.DEFAULT_PAGE_SIZE,
) -> dict:
    """Standardized pagination parameters."""
    page = max(1, page)
    page_size = min(max(1, page_size), settings.MAX_PAGE_SIZE)
    return {
        "limit": page_size,
        "offset": (page - 1) * page_size,
        "page": page,
        "page_size": page_size,
    }
