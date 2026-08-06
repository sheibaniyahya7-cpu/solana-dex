"""
Shared FastAPI dependencies used across multiple endpoints.
"""

from typing import Optional
from fastapi import Header, HTTPException, status, Depends
from app.core.config import settings
from app.core.security import decode_access_token
from app.core.logging import get_logger

logger = get_logger(__name__)


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    """
    Optional API key verification.
    In production, require a valid key for write operations.
    Read endpoints are public in this MVP.
    """
    if not settings.is_production:
        return "dev"  # Skip auth in development

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header is required",
        )
    # Validate against stored keys (extend this with DB lookup for multi-key support)
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
