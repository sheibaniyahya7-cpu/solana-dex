"""
Shared async HTTP client factory.
Provides a single, reusable httpx.AsyncClient per service with:
- Automatic retries with exponential backoff
- Timeout configuration
- Rate limiting integration
- Response logging
"""

import asyncio
from typing import Any, Dict, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Global client registry — one client per base URL
_clients: Dict[str, httpx.AsyncClient] = {}


def get_http_client(
    base_url: str,
    timeout: int = 30,
    headers: Optional[Dict[str, str]] = None,
) -> httpx.AsyncClient:
    """
    Return (or create) a shared AsyncClient for a given base URL.
    Call close_all_clients() during app shutdown.
    """
    if base_url not in _clients:
        default_headers = {
            "User-Agent": f"DEXTrader/{settings.APP_VERSION}",
            "Accept": "application/json",
        }
        if headers:
            default_headers.update(headers)

        _clients[base_url] = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers=default_headers,
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=50,
                keepalive_expiry=30,
            ),
            follow_redirects=True,
        )
    return _clients[base_url]


async def close_all_clients() -> None:
    """Close all shared HTTP clients on application shutdown."""
    for url, client in _clients.items():
        await client.aclose()
        logger.debug("HTTP client closed", base_url=url)
    _clients.clear()


# ─── Retry-wrapped request helper ─────────────────────────────────────────────

async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    max_retries: int = 3,
) -> Optional[Dict[str, Any]]:
    """
    Perform a GET request with exponential backoff retries.
    Returns parsed JSON or None on failure.
    """
    for attempt in range(1, max_retries + 1):
        try:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Respect Retry-After header if present
                retry_after = float(e.response.headers.get("Retry-After", 1.0))
                logger.warning(
                    "Rate limited by API",
                    url=url,
                    retry_after=retry_after,
                    attempt=attempt,
                )
                await asyncio.sleep(retry_after)
            elif e.response.status_code >= 500:
                wait = 2 ** attempt
                logger.warning(
                    "Server error, retrying",
                    url=url,
                    status=e.response.status_code,
                    attempt=attempt,
                    wait=wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "HTTP client error",
                    url=url,
                    status=e.response.status_code,
                    body=e.response.text[:200],
                )
                return None
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            wait = 2 ** attempt
            logger.warning(
                "Connection error, retrying",
                url=url,
                error=str(e),
                attempt=attempt,
                wait=wait,
            )
            await asyncio.sleep(wait)
        except Exception as e:
            logger.error("Unexpected HTTP error", url=url, error=str(e))
            return None

    logger.error("All retries exhausted", url=url, max_retries=max_retries)
    return None


async def safe_post(
    client: httpx.AsyncClient,
    url: str,
    json_body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    max_retries: int = 3,
) -> Optional[Dict[str, Any]]:
    """POST with retries. Returns parsed JSON or None on failure."""
    for attempt in range(1, max_retries + 1):
        try:
            response = await client.post(url, json=json_body, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = float(e.response.headers.get("Retry-After", 1.0))
                await asyncio.sleep(retry_after)
            elif e.response.status_code >= 500 and attempt < max_retries:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error(
                    "POST request failed",
                    url=url,
                    status=e.response.status_code,
                )
                return None
        except Exception as e:
            logger.error("POST error", url=url, error=str(e))
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)
            else:
                return None
    return None
