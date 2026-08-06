# Solana DEX Trader Intelligence Platform

A production-grade AI-powered trading intelligence platform for Solana DEX markets.
Monitors markets 24/7, detects opportunities, analyzes risks, and tracks smart money
using a multi-agent AI system.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                   │
│  Overview │ Tokens │ Wallets │ Whales │ AI Analysis │ Alerts │
└─────────────────────────┬───────────────────────────────────┘
                          │ REST + WebSocket
┌─────────────────────────▼───────────────────────────────────┐
│                     FastAPI Backend                          │
│  /api/v1/tokens  /wallets  /events  /analysis  /alerts      │
└────────────┬──────────────────────────────────┬─────────────┘
             │                                  │
┌────────────▼───────────┐     ┌───────────────▼─────────────┐
│     Celery Workers      │     │       PostgreSQL             │
│  collectors / monitors  │     │  tokens, wallets, events,   │
│  analyzers / ai_agents  │     │  analyses, alerts           │
│  alerts                 │     └─────────────────────────────┘
└────────────┬────────────┘
             │ pub/sub
┌────────────▼────────────┐
│         Redis            │
│  cache / queues / events │
└─────────────────────────┘
```

### Data Pipeline

```
Solana RPC / Helius / DexScreener / Birdeye
        ↓
  Data Collectors (Celery beat tasks)
        ↓
  Market Monitor (event detection)
        ↓
  AI Orchestrator → 5 agents in parallel
    ├── Market Agent    (price/volume/momentum)
    ├── Security Agent  (rug pull analysis)
    ├── Whale Agent     (large wallet moves)
    ├── Wallet Agent    (smart money conviction)
    └── Social Agent    (community credibility)
        ↓
  Trader Agent (GPT-4o synthesis → decision)
        ↓
  Scoring Engine → AIAnalysis persisted
        ↓
  Alert Processor → Telegram + WebSocket + DB
```

---

## Quick Start

### Prerequisites

- Docker Desktop
- API keys: Helius, Birdeye, OpenAI, Telegram Bot

### 1. Clone and configure

```bash
git clone <repo>
cd solana-dex-trader
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start with Docker Compose

```bash
# Development (with pgAdmin + Redis Commander)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Production
docker compose up -d
```

### 3. Run database migrations

```bash
docker compose exec backend alembic upgrade head
```

### 4. Verify everything is running

```bash
# Health check
curl http://localhost:8000/health

# API docs (dev only)
open http://localhost:8000/docs

# Frontend
open http://localhost:3000

# Celery monitor
open http://localhost:5555    # user: admin / pw: flowerpassword

# pgAdmin (dev)
open http://localhost:5050    # admin@dex.local / pgadminpassword
```

---

## Services

| Service       | Port  | Description                          |
|---------------|-------|--------------------------------------|
| Frontend      | 3000  | Next.js dashboard                    |
| Backend API   | 8000  | FastAPI + WebSocket                  |
| PostgreSQL    | 5432  | Primary database                     |
| Redis         | 6379  | Cache + message broker               |
| Flower        | 5555  | Celery task monitor                  |
| pgAdmin       | 5050  | Database GUI (dev only)              |
| Redis Cmd     | 8081  | Redis browser (dev only)             |

---

## API Endpoints

| Method | Path                              | Description                     |
|--------|-----------------------------------|---------------------------------|
| GET    | /api/v1/tokens                    | List tokens (paginated)         |
| GET    | /api/v1/tokens/new                | New token launches              |
| GET    | /api/v1/tokens/top                | Top by AI score                 |
| GET    | /api/v1/tokens/{mint}             | Token detail                    |
| GET    | /api/v1/tokens/{mint}/price-history | OHLCV candles                |
| GET    | /api/v1/wallets/smart-money       | Smart money wallets             |
| GET    | /api/v1/wallets/whales            | Whale wallets                   |
| GET    | /api/v1/events                    | Market events feed              |
| POST   | /api/v1/analysis/trigger          | Trigger AI analysis             |
| GET    | /api/v1/analysis/{mint}/latest    | Latest analysis for token       |
| GET    | /api/v1/analysis/summaries/top    | Top AI picks                    |
| GET    | /api/v1/alerts                    | Alert history                   |
| WS     | /ws/market                        | Live price updates              |
| WS     | /ws/events                        | Live market events              |
| WS     | /ws/alerts                        | Live alert notifications        |
| WS     | /ws/token/{mint}                  | Token-specific updates          |

---

## AI Scoring

### Score Weights

| Component     | Weight | Source                          |
|---------------|--------|---------------------------------|
| Security      | 25%    | SecurityAnalyzer + SecurityAgent|
| Smart Money   | 25%    | WalletAnalyzer + WalletAgent    |
| Volume        | 20%    | PriceCollector + MarketAgent    |
| Liquidity     | 15%    | DexScreener data                |
| Social        | 15%    | SocialAgent                     |

### AI Decisions

| Decision     | Score Range | Meaning                              |
|--------------|-------------|--------------------------------------|
| STRONG_BUY   | 85-100      | High conviction — all signals green  |
| BUY          | 70-84       | Good opportunity, manageable risk    |
| WATCH        | 50-69       | Interesting, awaiting confirmation   |
| AVOID        | 30-49       | Risk outweighs potential             |
| DANGER       | 0-29        | Active red flags, possible rug       |

---

## Project Structure

```
solana-dex-trader/
├── backend/
│   ├── app/
│   │   ├── core/          # Config, logging, redis, celery, security
│   │   ├── database/      # Models, repositories, migrations
│   │   ├── collectors/    # Solana RPC, Helius, DexScreener, Birdeye clients
│   │   ├── monitors/      # Market event detection, whale monitoring
│   │   ├── analyzers/     # Wallet intelligence, security engine
│   │   ├── ai_agents/     # 6 agents + orchestrator + scoring engine
│   │   ├── alerts/        # Telegram bot + alert processor
│   │   └── api/           # FastAPI routers, schemas, WebSocket
│   ├── alembic/           # Database migrations
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/           # Next.js 14 app router pages
│       ├── components/    # Reusable UI components
│       ├── hooks/         # WebSocket hook
│       ├── lib/           # API client, utilities
│       └── types/         # TypeScript definitions
├── nginx/                 # Reverse proxy config
├── docker-compose.yml
├── docker-compose.dev.yml
└── .env.example
```

---

## Development

### Running backend locally (without Docker)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt -r requirements-dev.txt

# Start services first (Docker)
docker compose up postgres redis -d

# Run FastAPI
uvicorn app.main:app --reload --port 8000

# Run Celery worker
celery -A app.core.celery_app worker --loglevel=debug -Q collectors,monitors,analyzers,alerts

# Run Celery beat
celery -A app.core.celery_app beat --loglevel=debug
```

### Running frontend locally

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

### Database migrations

```bash
# Generate a new migration after model changes
cd backend
alembic revision --autogenerate -m "describe your change"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

---

## Required API Keys

| Service    | Purpose                          | Get at                          |
|------------|----------------------------------|---------------------------------|
| Helius     | Enriched Solana data, parsed TXs | https://www.helius.dev/         |
| Birdeye    | Token analytics, OHLCV, holders  | https://birdeye.so/             |
| OpenAI     | Multi-agent AI analysis          | https://platform.openai.com/    |
| Telegram   | Alert notifications              | @BotFather on Telegram          |

DexScreener and Jupiter Price API require no keys for public endpoints.

---

## VPS Deployment

```bash
# 1. Provision a VPS (min: 4 vCPU, 8GB RAM, 50GB SSD)
# 2. Install Docker + Docker Compose
# 3. Clone repo and configure .env
# 4. Generate self-signed SSL (or use Let's Encrypt)
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem -out nginx/ssl/cert.pem

# 5. Set APP_ENV=production in .env
# 6. Start services
docker compose up -d --build

# 7. Run migrations
docker compose exec backend alembic upgrade head
```

---

## Monitoring

- **Celery tasks**: http://localhost:5555 (Flower)
- **Application logs**: `docker compose logs -f backend`
- **Database**: pgAdmin at http://localhost:5050
- **Health check**: `curl http://localhost:8000/health`

---

## License

MIT — use freely, modify as needed.
