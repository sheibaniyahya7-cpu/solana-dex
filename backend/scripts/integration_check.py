"""
End-to-end integration check for the running stack.

Exercises the paths that cross service boundaries and therefore cannot be
covered by unit tests: HTTP API, database, Redis, Celery dispatch, the
Redis-pub/sub-to-WebSocket bridge, and the alert pipeline.

Run from inside a container that shares the compose network:

    docker compose exec -T -e PYTHONPATH=/app backend python scripts/integration_check.py
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

import httpx
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

API = os.getenv("CHECK_API_URL", "http://localhost:8000")
WS = os.getenv("CHECK_WS_URL", "ws://localhost:8000")

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


# ─── HTTP API ─────────────────────────────────────────────────────────────────

# Every route the frontend API client calls, so a routing regression surfaces
# here rather than as an empty dashboard.
FRONTEND_ROUTES = [
    "/tokens/stats",
    "/tokens/top?limit=5",
    "/tokens/new?hours=24&limit=5",
    "/tokens/search?q=sol&limit=5",
    "/events?page_size=5",
    "/events/unprocessed?limit=5",
    "/wallets/smart-money?limit=5",
    "/wallets/whales?limit=5",
    "/wallets/top-performers?limit=5",
    "/whales/activity?hours=24&limit=5",
    "/whales/wallets?limit=5",
    "/whales/recent-trades?hours=24&limit=5",
    "/analysis/summaries/top?limit=5",
    "/alerts?page_size=5",
    "/alerts/unsent",
]


async def check_http() -> None:
    async with httpx.AsyncClient(base_url=API, timeout=20) as client:
        r = await client.get("/health")
        body = r.json()
        record(
            "health endpoint reports all services ok",
            r.status_code == 200 and body.get("status") == "ok",
            json.dumps(body.get("services", {})),
        )

        for path in FRONTEND_ROUTES:
            r = await client.get(f"/api/v1{path}")
            record(f"GET /api/v1{path}", r.status_code == 200, f"HTTP {r.status_code}")


# ─── Redis pub/sub → WebSocket bridge ─────────────────────────────────────────

async def check_websocket_bridge() -> None:
    from app.core.redis import RedisCache, close_redis, init_redis

    redis = await init_redis()
    cache = RedisCache(redis, "dex")
    marker = uuid.uuid4().hex

    cases = [
        ("events", "events", {"type": "market_event", "marker": marker}),
        ("alerts", "alerts", {"type": "alert", "marker": marker}),
        ("market", "price_updates", {"type": "price_update", "marker": marker}),
    ]

    try:
        # Each case runs twice. The second pass would fail if closed
        # connections were left behind in the channel registry.
        for attempt in (1, 2):
            suffix = "" if attempt == 1 else " (after reconnect)"
            for ws_path, redis_channel, payload in cases:
                async with websockets.connect(f"{WS}/ws/{ws_path}") as ws:
                    hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                    if hello.get("type") != "connected":
                        record(f"ws /{ws_path} handshake{suffix}", False, str(hello))
                        continue

                    # The forwarder subscribes at startup, but give the broadcast
                    # a moment to reach the connection registry.
                    await asyncio.sleep(0.3)
                    await cache.publish(redis_channel, payload)

                    try:
                        received = json.loads(
                            await asyncio.wait_for(ws.recv(), timeout=10))
                    except asyncio.TimeoutError:
                        record(f"dex:{redis_channel} -> ws /{ws_path}{suffix}",
                               False, "no message received")
                        continue

                    record(
                        f"dex:{redis_channel} -> ws /{ws_path}{suffix}",
                        received.get("marker") == marker,
                        f"type={received.get('type')}",
                    )

        # Per-token channels are pattern-matched.
        mint = f"TESTMINT{marker[:8]}"
        async with websockets.connect(f"{WS}/ws/token/{mint}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=10)
            await asyncio.sleep(0.3)
            await cache.publish(f"token:{mint}", {"type": "analysis", "marker": marker})
            try:
                received = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                record("dex:token:<mint> -> ws /token/<mint>",
                       received.get("marker") == marker, f"type={received.get('type')}")
            except asyncio.TimeoutError:
                record("dex:token:<mint> -> ws /token/<mint>", False, "no message received")
    finally:
        await close_redis()


# ─── Alert pipeline ───────────────────────────────────────────────────────────

async def check_alert_pipeline() -> None:
    """
    Publish a synthetic alert and follow it through the whole pipeline:
    pub/sub -> listener buffer -> Celery processor -> Postgres + WebSocket.
    """
    from sqlalchemy import text

    from app.core.celery_app import celery_app
    from app.core.redis import RedisCache, close_redis, init_redis
    from app.database.base import close_db, get_engine, init_db

    redis = await init_redis()
    await init_db()
    cache = RedisCache(redis, "dex")
    marker = uuid.uuid4().hex
    title = f"integration-check {marker}"

    # Watch the outbound broadcast the processor emits after delivery.
    broadcast = redis.pubsub()
    await broadcast.subscribe("dex:alerts")

    try:
        await cache.publish("alert_queue", {
            "type": "market_event",
            "event_type": "VOLUME_SPIKE",
            "title": title,
            "description": "synthetic alert emitted by integration_check.py",
            "token_mint": None,
            "volume_change_pct": 250,
            "marker": marker,
        })

        # The listener buffers asynchronously.
        buffered = False
        for _ in range(20):
            await asyncio.sleep(0.5)
            items = await cache.lrange("alert_queue_buffer", 0, -1)
            if any(item.get("marker") == marker for item in items):
                buffered = True
                break
        record("dex:alert_queue -> alert_queue_buffer (listener is subscribed)", buffered)
        if not buffered:
            return

        result = celery_app.send_task("app.alerts.alert_processor.process_alerts",
                                      queue="alerts")
        try:
            payload = await asyncio.to_thread(result.get, 60)
            record("process_alerts task drains the buffer", payload.get("sent", 0) >= 1,
                   str(payload))
        except Exception as e:
            record("process_alerts task drains the buffer", False, str(e)[:120])

        engine = get_engine()
        persisted = False
        for _ in range(20):
            async with engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT alert_type, severity FROM alerts WHERE title = :t"),
                    {"t": title})
                found = row.first()
            if found:
                persisted = True
                record("alert persisted to Postgres", True,
                       f"type={found[0]} severity={found[1]}")
                break
            await asyncio.sleep(0.5)
        if not persisted:
            record("alert persisted to Postgres", False, "no row found")

        rebroadcast = False
        deadline = asyncio.get_running_loop().time() + 15
        while asyncio.get_running_loop().time() < deadline:
            message = await broadcast.get_message(
                ignore_subscribe_messages=True, timeout=1.0)
            if message and json.loads(message["data"]).get("title") == title:
                rebroadcast = True
                break
        record("processed alert rebroadcast on dex:alerts", rebroadcast)
    finally:
        await broadcast.unsubscribe()
        await broadcast.aclose()
        await close_db()
        await close_redis()


# ─── Celery ───────────────────────────────────────────────────────────────────

def check_celery() -> None:
    from app.core.celery_app import celery_app

    # Reproduce what a worker does at boot: pull in every module listed in
    # conf.imports. Plain `import celery_app` does not register any task.
    celery_app.loader.import_default_modules()

    registered = set(celery_app.tasks)
    scheduled = {e["task"] for e in celery_app.conf.beat_schedule.values()}

    unregistered = sorted(scheduled - registered)
    record("every beat-scheduled task is registered", not unregistered,
           f"unregistered: {unregistered}" if unregistered
           else f"{len(scheduled)} scheduled tasks")

    ping = celery_app.control.ping(timeout=10)
    record("celery worker responds to ping", bool(ping), f"{len(ping)} worker(s)")

    # A task scheduled onto a queue no worker consumes is silently never run.
    active = celery_app.control.inspect(timeout=10).active_queues() or {}
    consumed = {q["name"] for queues in active.values() for q in queues}

    def target_queue(entry: dict) -> str:
        if entry.get("options", {}).get("queue"):
            return entry["options"]["queue"]
        for route, dest in (celery_app.conf.task_routes or {}).items():
            if route.endswith("*") and entry["task"].startswith(route[:-1]):
                return dest["queue"]
        return celery_app.conf.task_default_queue

    orphaned = sorted(
        f"{name} -> {target_queue(entry)}"
        for name, entry in celery_app.conf.beat_schedule.items()
        if target_queue(entry) not in consumed
    )
    record("every beat-scheduled task targets a consumed queue", not orphaned,
           f"orphaned: {orphaned}" if orphaned else f"consumed: {sorted(consumed)}")


# ─── Authentication ───────────────────────────────────────────────────────────

async def check_auth() -> None:
    from fastapi import HTTPException

    from app.api.dependencies import require_api_key
    from app.api.v1.endpoints.analysis import router as analysis_router
    from app.core.config import settings

    trigger = [r for r in analysis_router.routes
               if getattr(getattr(r, "endpoint", None), "__name__", "") == "trigger_analysis"]
    record(
        "POST /analysis/trigger has the API key dependency attached",
        bool(trigger) and any(d.call is require_api_key
                              for d in trigger[0].dependant.dependencies),
        "route not found" if not trigger else "",
    )

    async def call(header: Optional[str]):
        try:
            return await require_api_key(header)
        except HTTPException as e:
            return e.status_code

    original_env, original_key = settings.APP_ENV, settings.API_KEY
    try:
        settings.APP_ENV = "development"
        record("development skips the API key check", await call(None) == "dev")

        settings.APP_ENV = "production"
        settings.API_KEY = ""
        record("production without a configured key fails closed",
               await call("anything") == 503)

        settings.API_KEY = "dex_integration_check_key"
        record("production rejects a missing key", await call(None) == 401)
        record("production rejects an incorrect key", await call("wrong") == 403)
        record("production accepts the configured key",
               await call(settings.API_KEY) == settings.API_KEY)
    finally:
        settings.APP_ENV, settings.API_KEY = original_env, original_key


# ─── Runner ───────────────────────────────────────────────────────────────────

async def main() -> int:
    print("── HTTP API ──")
    await check_http()
    print("\n── Celery ──")
    check_celery()
    print("\n── WebSocket bridge ──")
    await check_websocket_bridge()
    print("\n── Alert pipeline ──")
    await check_alert_pipeline()
    print("\n── Authentication ──")
    await check_auth()

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("Failed: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
