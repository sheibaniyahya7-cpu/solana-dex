# Recovery Report

Repair of the seven critical integration failures identified in the audit. Scope was
limited to making the existing design work: no features were added and no component was
redesigned except where a confirmed bug required it.

**Result: 36/36 integration checks pass, all 7 services healthy, all 6 frontend pages
render, frontend builds clean.**

Reproduce with:

```bash
docker compose up -d --build postgres redis backend celery_worker celery_beat flower frontend
docker compose exec backend alembic upgrade head
docker compose exec backend python scripts/integration_check.py
```

---

## 1. Celery task registration

**Root cause.** `celery_app.py` called `app.autodiscover_tasks()`, which imports a
`tasks.py` submodule from each listed package. Tasks in this project live in
domain-named modules (`token_collector.py`, `market_monitor.py`, `orchestrator.py`, …),
so no task module was ever imported. Beat dispatched jobs that no worker could execute.

**Fix.** Replaced autodiscovery with an explicit `app.conf.imports` tuple naming all ten
task modules.

**Second defect found while verifying.** `cleanup-old-data` is scheduled onto the
`default` queue, but the worker's `-Q` list was
`collectors,monitors,analyzers,alerts` — no consumer. The daily cleanup would have
accumulated in Redis forever. Added `default` to the queue list in both compose files
and the README.

**Verified.** Beat dispatches and the worker executes every scheduled task. The
integration check asserts that each of the 10 beat entries is registered *and* targets a
queue the worker actually consumes.

Files: `backend/app/core/celery_app.py`, `docker-compose.yml`,
`docker-compose.dev.yml`, `README.md`

---

## 2. Redis initialization in Celery workers

**Root cause.** Two compounding problems. Redis is initialized in the FastAPI lifespan,
which Celery workers never execute, so `get_redis()` raised
`RuntimeError("Redis not initialized")`. And every task wrapped its coroutine in
`asyncio.run()`, which creates and destroys a fresh event loop per task — so even after
initializing, the cached Redis client and the module-level `httpx` clients were bound to
a loop that no longer existed.

**Fix.** Added `backend/app/core/task_runtime.py`, which keeps one event loop per worker
process, initializes Redis inside it on first use, and releases both on
`worker_process_shutdown`. All ten task entrypoints now call `run_async(...)` instead of
`asyncio.run(...)`. Also fixed `close_redis()` to reset its module globals so
re-initialization works.

**Verified.** The worker executes all scheduled tasks with no RuntimeError.

Files: `backend/app/core/task_runtime.py` (new), `backend/app/core/redis.py`, and the
ten task modules under `collectors/`, `monitors/`, `analyzers/`, `ai_agents/`,
`alerts/`, `database/`

---

## 3. Frontend compilation errors

**Root cause.** Two independent problems, the first non-obvious:

- `.gitignore` carried the unanchored Python pattern `lib/`, which matches at *any*
  depth — including `frontend/src/lib/`. The frontend's own source directory was
  silently excluded from version control, which is why `@/lib/api` and `@/lib/utils`
  were missing from a fresh clone.
- `package.json` depended on `@radix-ui/react-badge`, which does not exist on npm.
  `npm install` failed with E404 before compilation could even begin. Nothing in the
  source imported it.

**Fix.** Anchored the Python artifact patterns in `.gitignore` (and added
`*.tsbuildinfo`); recreated `src/lib/utils.ts` (formatting, colors, `timeAgo`,
`truncateAddress`) and `src/lib/api.ts` (typed axios clients covering every endpoint the
pages call); removed the non-existent dependency; committed `package-lock.json`; fixed a
`TooltipItem<"line">` typing error in `PriceChart.tsx`; added `frontend/public/.gitkeep`
because the Dockerfile copies that directory.

**Verified.** `npm install`, `npx tsc --noEmit`, and `npm run build` all succeed.
`git check-ignore` no longer matches `frontend/src/lib/`. All six routes return 200 from
the running container.

Files: `.gitignore`, `frontend/package.json`, `frontend/package-lock.json`,
`frontend/src/lib/api.ts`, `frontend/src/lib/utils.ts`,
`frontend/src/components/charts/PriceChart.tsx`, `frontend/public/.gitkeep`

---

## 4. Docker Compose services

Six distinct defects.

1. **Beat could not persist its schedule.** `celerybeat_data:/app/celerybeat-schedule`
   mounted a *directory* at the path where `PersistentScheduler` needs to create a
   shelve *file*. Now mounts `celerybeat_data:/app/celerybeat` with `--schedule` and
   `--pidfile` pointing inside it.
2. **Production ran host source as a non-root user.** `./backend:/app` shadowed the
   image contents and left `/app` owned by the host user while the container runs as
   `appuser`. Removed from the production services; added to the dev override, whose
   image stage runs as root, so development hot-reload is unchanged.
3. **Log directory was unwritable.** `./logs:/app/logs` is created root-owned on Linux,
   so `appuser` could not write to it. Switched to a named `backend_logs` volume, which
   inherits ownership from the image, and moved `mkdir -p /app/logs /app/celerybeat`
   before `chown` in the Dockerfile so that ownership is `appuser`.
4. **Worker, beat, and flower were permanently unhealthy.** All three inherited the API
   image's `HEALTHCHECK` (`curl localhost:8000/health`), which they can never satisfy.
   The worker now uses `celery inspect ping`, flower probes `:5555/healthcheck`, and
   beat's is disabled since it exposes no endpoint.
5. **The frontend image could not build, and its healthcheck was wrong.** The builder
   ran `npm ci --only=production` under `NODE_ENV=production`, omitting the
   typescript/tailwind/postcss that `next build` needs — now `npm ci --include=dev`. The
   healthcheck probed a non-existent `/api/health`; it also had to move from `localhost`
   to `127.0.0.1`, because `localhost` resolves to `::1` first while the Next server
   binds IPv4 only, and busybox `wget` does not retry the next address.
6. **Flower was missing `DATABASE_URL`** even though it imports the settings module.
   Added for parity. Also removed the obsolete `version:` key from both compose files.

**Verified.** All seven services report healthy. `celerybeat-schedule` is present on the
named volume owned by `appuser`, and `/app/logs` is writable by the non-root user.

Files: `docker-compose.yml`, `docker-compose.dev.yml`, `backend/Dockerfile`,
`frontend/Dockerfile`

---

## 5. WebSocket

**Root cause.** `redis_pubsub_forwarder()` was defined but never called. Collectors and
monitors run in separate Celery processes and hand updates to the API by publishing to
`dex:price_updates`, `dex:volume_spikes`, `dex:events`, `dex:whale_transactions`,
`dex:alerts`, and `dex:token:<mint>`. With no subscriber relaying any of it, clients only
ever received the `connected` frame and a ping every 30 seconds.

**Second defect found while verifying.** The endpoints held connections open with a
blind `asyncio.sleep(30)` and never read from the socket, so a client that disappeared
was not noticed until the next send failed up to 30 seconds later. Stale entries
lingered in the channel registry and absorbed broadcasts, which made delivery to a
reconnected client fail intermittently — this is why the `events` channel passed on one
run and failed on the next.

**Fix.**

- `PUBSUB_ROUTES` maps each published channel onto the WebSocket channel that serves it,
  plus a pattern forwarder for the dynamic `dex:token:*` channels.
- `start_pubsub_forwarders()` / `stop_pubsub_forwarders()` run from the application
  lifespan. Each forwarder is supervised with exponential backoff so a dropped Redis
  connection self-heals instead of silently ending real-time delivery.
- Endpoints now await `receive_text()` with a timeout, so disconnects are detected
  immediately, and always deregister in a `finally` block.
- `broadcast()` fans out concurrently with a per-connection send timeout, so one
  unresponsive client cannot stall an entire channel.

**Verified.** Synthetic publishes reach connected clients on all four channel shapes
(`/market`, `/events`, `/alerts`, `/token/<mint>`), and again on a second pass after
reconnecting — which is the check that would catch a regression of the stale-connection
bug.

Files: `backend/app/api/websocket.py`, `backend/app/main.py`

---

## 6. Telegram alerts

**Root cause.** `start_alert_listener()` was never called, so `dex:alert_queue` — where
`market_monitor`, `whale_monitor`, `security_analyzer`, and the AI orchestrator all
publish — had no subscriber. `alert_queue_buffer` stayed empty and the `process_alerts`
task ran every 30 seconds returning `{'sent': 0}` indefinitely. The Telegram client
itself was complete and correct; only the ingestion hop was missing.

**Fix.** Started the listener from the application lifespan. Because the API is served
by four uvicorn worker processes, a Redis lock (`dex:alert_listener:lock`, 30s TTL,
renewed while subscribed) keeps exactly one process subscribed — otherwise every alert
would be buffered, persisted, and delivered to Telegram once per worker. The loop now
uses `get_message(timeout=1.0)` so the lock renews between messages, and it re-contends
for the lock if it ever loses it.

**Verified.** Exactly one listener holds the lock across four workers. A synthetic alert
was buffered, drained by the Celery task (`{'sent': 1, 'failed': 0}`), persisted to
Postgres as `VOLUME_SPIKE`/`medium`, and rebroadcast on `dex:alerts` to WebSocket
clients.

**Remaining configuration step.** Telegram delivery itself is unconfigured in this
environment, so alerts are stored with `is_sent=false`. Set `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID` to complete the final hop; the retry path in
`_retry_failed_db_alerts` will pick up the stored alerts.

Files: `backend/app/alerts/alert_processor.py`, `backend/app/main.py`

---

## 7. Authentication

**Root cause.** `app/api/dependencies.py::verify_api_key` returned whatever `X-API-Key`
value it was given without comparing it against anything, so in production any non-empty
string authenticated successfully. It was also not attached to any endpoint, and its name
collided with the unrelated constant-time hash comparison helper of the same name in
`app/core/security.py`.

**Fix.** Renamed the dependency to `require_api_key`, added an `API_KEY` setting, and
validated the header using the existing constant-time
`verify_api_key(plain, hash_api_key(configured))`. It fails closed with 503 when
production is missing its key, rather than leaving the endpoint open; 401 for a missing
header and 403 for an incorrect one. Attached it to `POST /api/v1/analysis/trigger`, the
only write endpoint and the one that spends OpenAI credits. Read endpoints remain public
as documented. `API_KEY` is documented in `.env.example` alongside the command to
generate one.

**Verified.** Six checks: the dependency is attached to the route, development bypasses
the check, and production covers all four branches (unconfigured → 503, missing → 401,
wrong → 403, correct → accepted).

Files: `backend/app/api/dependencies.py`, `backend/app/core/config.py`,
`backend/app/api/v1/endpoints/analysis.py`, `.env.example`

---

## Additional blocker fixed along the way

**Alembic could not run migrations.** `alembic/env.py` rewrote the database URL to the
synchronous `psycopg2` driver before handing it to `async_engine_from_config`, so
`alembic upgrade head` failed with *"The asyncio extension requires an async driver to be
used."* Online mode now keeps `asyncpg` and only offline mode renders through the sync
URL. `alembic current` inside the container reports `0001_initial (head)`.

Files: `backend/alembic/env.py`, `backend/alembic.ini`

---

## Integration test

`backend/scripts/integration_check.py` (new) exercises the paths that cross service
boundaries and therefore cannot be unit tested. Run it against a live stack:

```bash
docker compose exec backend python scripts/integration_check.py
```

| Group | Checks | What it proves |
| --- | --- | --- |
| HTTP API | 16 | Health reports database and Redis ok, and every route the frontend client calls returns 200 |
| Celery | 3 | All 10 beat entries are registered, target a consumed queue, and a worker answers ping |
| WebSocket bridge | 7 | Redis publishes from another process reach clients on all four channel shapes, including after a reconnect |
| Alert pipeline | 4 | A published alert is buffered, drained by the Celery task, persisted to Postgres, and rebroadcast |
| Authentication | 6 | The dependency is wired to the write endpoint and enforces every production branch |

The HTTP group deliberately probes the exact route list used by
`frontend/src/lib/api.ts`, so a routing regression surfaces here rather than as an empty
dashboard.

---

## Known limitations, not in scope

- **nginx is excluded from the verified set.** It requires TLS certificates at
  `nginx/ssl/`, which README step 4 tells you to generate and `.gitignore` excludes.
  Without them nginx crash-loops on `docker compose up`. This is documented behaviour and
  was left unchanged, but generate the certificates before bringing up the full stack.
- **Collectors return zero rows here.** `HELIUS_API_KEY` and `BIRDEYE_API_KEY` are unset,
  and DexScreener responds 404 to `/latest/dex/tokens/new/solana` — that endpoint does
  not exist in their public API. The task plumbing is proven end to end; the
  DexScreener URL is a data-source bug outside the seven-issue scope and worth a separate
  look.
- **OpenAI and Telegram are unconfigured**, so the AI analysis and notification hops are
  structurally verified but not exercised against the live providers.
- **Host port conflicts.** On the verification machine, host ports 5432 and 5555 were
  occupied or reserved, so testing used a temporary compose override that republished
  them. It has been removed; the committed configuration uses the documented ports.
