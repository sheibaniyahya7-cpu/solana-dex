"""
WebSocket endpoints for real-time data streaming to the frontend.
Channels:
  /ws/market      — live token price/volume updates
  /ws/events      — real-time market event feed
  /ws/alerts      — live alert notifications
  /ws/token/{mint} — token-specific updates
"""

import asyncio
import json
from typing import Dict, List, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis

ws_router = APIRouter(tags=["websocket"])
logger = get_logger(__name__)

PING_INTERVAL = 30.0  # seconds between keepalive pings
SEND_TIMEOUT = 5.0    # per-connection budget for a broadcast frame


# ─── Connection Manager ───────────────────────────────────────────────────────

class ConnectionManager:
    """
    Manages active WebSocket connections grouped by channel.
    Broadcasts messages to all subscribers of a channel.
    """

    def __init__(self) -> None:
        # channel_name → set of active websocket connections
        self._channels: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        await websocket.accept()
        if channel not in self._channels:
            self._channels[channel] = set()
        self._channels[channel].add(websocket)
        logger.info("WebSocket connected", channel=channel, total=len(self._channels[channel]))

    def disconnect(self, websocket: WebSocket, channel: str) -> None:
        if channel in self._channels:
            self._channels[channel].discard(websocket)
        logger.info("WebSocket disconnected", channel=channel)

    async def broadcast(self, channel: str, message: dict) -> None:
        """Send a message to all connections on a channel."""
        connections = list(self._channels.get(channel, ()))
        if not connections:
            return
        payload = json.dumps(message, default=str)

        async def send(ws: WebSocket) -> bool:
            if ws.client_state != WebSocketState.CONNECTED:
                return False
            try:
                await asyncio.wait_for(ws.send_text(payload), timeout=SEND_TIMEOUT)
                return True
            except Exception:
                return False

        # Concurrent so that one unresponsive client cannot stall delivery to
        # the rest of the channel.
        delivered = await asyncio.gather(*(send(ws) for ws in connections))

        for ws, ok in zip(connections, delivered):
            if not ok:
                self._channels.get(channel, set()).discard(ws)

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        await websocket.send_text(json.dumps(message, default=str))

    def subscriber_count(self, channel: str) -> int:
        return len(self._channels.get(channel, set()))


manager = ConnectionManager()


# ─── Redis Pub/Sub Forwarder ──────────────────────────────────────────────────

# Celery workers run in separate processes, so they hand updates to the API via
# Redis pub/sub. These routes map a published channel (without the "dex:"
# namespace) onto the WebSocket channel that serves it.
PUBSUB_ROUTES: Dict[str, str] = {
    "price_updates": "market",
    "volume_spikes": "market",
    "events": "events",
    "whale_transactions": "events",
    "alerts": "alerts",
}

# Per-token channels are created on demand, so they are matched by pattern and
# forwarded to the WebSocket channel of the same name.
TOKEN_CHANNEL_PATTERN = "token:*"

_forwarder_tasks: List[asyncio.Task] = []


def _decode(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


async def redis_pubsub_forwarder(channel_pattern: str, ws_channel: str) -> None:
    """
    Subscribes to a Redis pub/sub channel and broadcasts messages
    to all WebSocket subscribers. Runs as a background task.
    """
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"dex:{channel_pattern}")
    logger.info("Redis pubsub listener started", channel=channel_pattern)

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await manager.broadcast(ws_channel, data)
                except Exception as e:
                    logger.warning("PubSub message parse error", error=str(e))
    except asyncio.CancelledError:
        logger.info("Redis pubsub listener stopped", channel=channel_pattern)
        raise
    finally:
        # Release the pooled connection; the supervisor may restart this task.
        await pubsub.aclose()


async def redis_pattern_forwarder(pattern: str) -> None:
    """
    Subscribes to a Redis pub/sub pattern and broadcasts each message to the
    WebSocket channel named after the Redis channel it arrived on.
    """
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.psubscribe(f"dex:{pattern}")
    logger.info("Redis pubsub pattern listener started", pattern=pattern)

    try:
        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                try:
                    ws_channel = _decode(message["channel"]).split(":", 1)[1]
                    data = json.loads(message["data"])
                    await manager.broadcast(ws_channel, data)
                except Exception as e:
                    logger.warning("PubSub message parse error", error=str(e))
    except asyncio.CancelledError:
        logger.info("Redis pubsub pattern listener stopped", pattern=pattern)
        raise
    finally:
        await pubsub.aclose()


async def _supervise(name: str, factory) -> None:
    """Restart a forwarder if its Redis connection drops, with backoff."""
    delay = 1.0
    while True:
        try:
            await factory()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("PubSub forwarder crashed — restarting",
                         forwarder=name, error=str(e), retry_in=delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


async def start_pubsub_forwarders() -> None:
    """
    Launch one background task per pub/sub route. Called at application
    startup; without these, nothing published by the workers ever reaches a
    connected WebSocket client.
    """
    if _forwarder_tasks:
        return

    for redis_channel, ws_channel in PUBSUB_ROUTES.items():
        _forwarder_tasks.append(asyncio.create_task(
            _supervise(
                redis_channel,
                lambda c=redis_channel, w=ws_channel: redis_pubsub_forwarder(c, w),
            ),
            name=f"pubsub-forwarder:{redis_channel}",
        ))

    _forwarder_tasks.append(asyncio.create_task(
        _supervise(
            TOKEN_CHANNEL_PATTERN,
            lambda: redis_pattern_forwarder(TOKEN_CHANNEL_PATTERN),
        ),
        name="pubsub-forwarder:token",
    ))

    logger.info("Pub/sub forwarders started", count=len(_forwarder_tasks))


async def stop_pubsub_forwarders() -> None:
    """Cancel all forwarder tasks and wait for them to unwind."""
    if not _forwarder_tasks:
        return
    for task in _forwarder_tasks:
        task.cancel()
    await asyncio.gather(*_forwarder_tasks, return_exceptions=True)
    _forwarder_tasks.clear()
    logger.info("Pub/sub forwarders stopped")


# ─── WebSocket Endpoints ──────────────────────────────────────────────────────

async def _serve_until_disconnect(websocket: WebSocket) -> None:
    """
    Hold a connection open, sending a keepalive ping when the client is idle.

    Reads from the socket instead of sleeping blindly: with no pending receive,
    a client that goes away is not noticed until the next send fails, so its
    entry lingers in the registry and swallows broadcasts meant for it. Inbound
    frames carry no meaning in this protocol and are discarded.
    """
    while True:
        try:
            await asyncio.wait_for(websocket.receive_text(), timeout=PING_INTERVAL)
        except asyncio.TimeoutError:
            await manager.send_personal(websocket, {"type": "ping"})


@ws_router.websocket("/market")
async def ws_market_feed(websocket: WebSocket):
    """
    Real-time token price and volume updates.
    Clients receive a JSON message every time a token's market data is refreshed.
    Format: { "type": "price_update", "data": { token fields } }
    """
    await manager.connect(websocket, "market")
    await manager.send_personal(websocket, {
        "type": "connected",
        "channel": "market",
        "message": "Connected to live market feed",
    })
    try:
        # Real data arrives via the Redis pub/sub forwarders, not from here.
        await _serve_until_disconnect(websocket)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        manager.disconnect(websocket, "market")


@ws_router.websocket("/events")
async def ws_events_feed(websocket: WebSocket):
    """
    Real-time market event stream — volume spikes, whale entries, momentum signals.
    Format: { "type": "market_event", "data": { event fields } }
    """
    await manager.connect(websocket, "events")
    await manager.send_personal(websocket, {
        "type": "connected",
        "channel": "events",
        "message": "Connected to live event feed",
    })
    try:
        await _serve_until_disconnect(websocket)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        manager.disconnect(websocket, "events")


@ws_router.websocket("/alerts")
async def ws_alerts_feed(websocket: WebSocket):
    """
    Real-time alert notifications — Telegram + in-app.
    Format: { "type": "alert", "data": { alert fields } }
    """
    await manager.connect(websocket, "alerts")
    await manager.send_personal(websocket, {
        "type": "connected",
        "channel": "alerts",
        "message": "Connected to live alert feed",
    })
    try:
        await _serve_until_disconnect(websocket)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        manager.disconnect(websocket, "alerts")


@ws_router.websocket("/token/{mint_address}")
async def ws_token_feed(websocket: WebSocket, mint_address: str):
    """
    Token-specific WebSocket — subscribes to all updates for one token.
    Format: { "type": "token_update|event|analysis", "data": {...} }
    """
    channel = f"token:{mint_address}"
    await manager.connect(websocket, channel)
    await manager.send_personal(websocket, {
        "type": "connected",
        "channel": channel,
        "token": mint_address,
        "message": f"Subscribed to updates for {mint_address[:8]}...",
    })
    try:
        await _serve_until_disconnect(websocket)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        manager.disconnect(websocket, channel)


# ─── Public broadcaster helper (called by monitors/analyzers) ─────────────────

async def broadcast_event(channel: str, message: dict) -> None:
    """Called by background workers to push updates to WebSocket clients."""
    await manager.broadcast(channel, message)
