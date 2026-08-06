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
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis

ws_router = APIRouter(tags=["websocket"])
logger = get_logger(__name__)


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
        if channel not in self._channels:
            return
        dead: Set[WebSocket] = set()
        payload = json.dumps(message, default=str)
        for ws in self._channels[channel]:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        # Clean up dead connections
        for ws in dead:
            self._channels[channel].discard(ws)

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        await websocket.send_text(json.dumps(message, default=str))

    def subscriber_count(self, channel: str) -> int:
        return len(self._channels.get(channel, set()))


manager = ConnectionManager()


# ─── Redis Pub/Sub Forwarder ──────────────────────────────────────────────────

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
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning("PubSub message parse error", error=str(e))
    except asyncio.CancelledError:
        await pubsub.unsubscribe()
        logger.info("Redis pubsub listener stopped", channel=channel_pattern)


# ─── WebSocket Endpoints ──────────────────────────────────────────────────────

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
        while True:
            # Keep connection alive — real data comes via Redis pubsub broadcasts
            await asyncio.sleep(30)
            await manager.send_personal(websocket, {"type": "ping"})
    except WebSocketDisconnect:
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
        while True:
            await asyncio.sleep(30)
            await manager.send_personal(websocket, {"type": "ping"})
    except WebSocketDisconnect:
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
        while True:
            await asyncio.sleep(30)
            await manager.send_personal(websocket, {"type": "ping"})
    except WebSocketDisconnect:
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
        while True:
            await asyncio.sleep(30)
            await manager.send_personal(websocket, {"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


# ─── Public broadcaster helper (called by monitors/analyzers) ─────────────────

async def broadcast_event(channel: str, message: dict) -> None:
    """Called by background workers to push updates to WebSocket clients."""
    await manager.broadcast(channel, message)
