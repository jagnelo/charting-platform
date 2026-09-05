# Charting Platform

A self-hosted personal trading chart platform — OHLCV data, technical indicators, persistent drawings, price and indicator alerts, and a screener — all running on your own hardware with your own data.

[![CI](https://github.com/your-org/charting-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/charting-platform/actions/workflows/ci.yml)

---

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Features](#features)
- [Configuration](#configuration)
- [Running Tests](#running-tests)
- [Documentation](#documentation)

---

## Quick Start

**Prerequisites:** Docker and Docker Compose.

```bash
# 1. Clone and configure
git clone https://github.com/your-org/charting-platform
cd charting-platform
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY:
#   echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env

# 2. Allocate isolated resources for this worktree and start the stack
RUNTIME_ENV="$(python3 scripts/worktree-runtime.py env-file)"
set -a; . "$RUNTIME_ENV"; set +a
COMPOSE_PROJECT_NAME="$STACK_COMPOSE_PROJECT" docker compose up -d

# 3. Apply DB migrations
COMPOSE_PROJECT_NAME="$(./scripts/dev-stack.sh project-name stack)" docker compose exec backend alembic upgrade head

# 4. Open in browser
open http://localhost
```

Register an account and start searching for symbols. Market data comes from the active provider policy chain for each capability and is persisted locally before it is served back to the UI.

Every local stack started from this repository is worktree-scoped by default.
The resolved worktree path contributes a stable suffix to Compose projects and
the allocator also assigns distinct host ports, URLs, databases, queues,
volumes, and networks. No local command stops another worktree.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser  (Vue 3 + TypeScript + uPlot)                          │
│  Chart | Screener | Alerts | Settings | Login                   │
└──────────────────────┬────────────────────────┬─────────────────┘
                       │ REST  (JWT Bearer)      │ WebSocket
┌──────────────────────▼────────────────────────▼─────────────────┐
│  FastAPI  (Python 3.12)                                         │
│  ┌─────────────┐  ┌────────────────────┐  ┌──────────────────┐ │
│  │  REST API   │  │  Alert Engine      │  │  Indicator       │ │
│  │  /api/v1    │  │  (APScheduler 60s) │  │  Engine          │ │
│  └─────────────┘  └────────────────────┘  └──────────────────┘ │
└───────────────────────────┬──────────────────────────────────────┘
                            │
               ┌────────────┴───────────────┐
               │                           │
       ┌───────▼──────┐           ┌────────▼─────┐
       │  PostgreSQL  │           │    Redis     │
       │  (data +     │           │  (ARQ task   │
       │   schema)    │           │   queue)     │
       └──────────────┘           └──────────────┘
```

| Container | Port | Purpose |
|---|---|---|
| `postgres` | 5432 | Primary database — persisted in named volume |
| `redis` | 6379 | ARQ background task broker |
| `backend` | 8000 | FastAPI REST + WebSocket |
| `worker` | — | ARQ worker for bulk fetches and scheduled screener runs |
| `frontend` | 80 | Vue 3 SPA served by nginx |

---

## Features

### Chart
- Candlestick rendering with volume bars (uPlot canvas — very fast)
- Pan/zoom across all timeframes M1 → Monthly
- OHLCV tooltip on cursor hover
- RSI, MACD and other oscillators rendered in separate sub-panes below the main chart

### Indicators

14 built-in indicators, registry-based — adding a new one requires exactly one class and one decorator (see [Adding Indicators](docs/adding-indicators.md)):

| Category | Indicators |
|---|---|
| Trend | SMA, EMA, WMA, Bollinger Bands |
| Momentum | RSI, MACD, Stochastic, CCI, ROC |
| Volume | VWAP, Anchored VWAP, OBV, Volume SMA |
| Volatility | ATR, ATR % |

All indicators are computed **server-side** in Python (authoritative) and mirrored in TypeScript on the frontend for rendering speed.

### Drawings
Trendline, horizontal/vertical line, ray, Fibonacci retracement/extension, rectangle, circle, arrow, text box. Click-to-select with hit detection. Per-timeframe scoping or pin-to-all. Persistent per user.

### Alerts

**Price alerts** — crosses above/below, touches, percent change target  
**Indicator alerts** — any indicator vs a fixed threshold, or indicator vs indicator (e.g. EMA 50 crosses above EMA 200)

- Evaluated server-side every 60 seconds (never misses even when browser is closed)
- Push notifications via OneSignal (free tier — unlimited devices and notifications)
- Real-time in-app toast notifications via WebSocket

### Screener
Saved screens with AND/OR logic, combining price conditions and indicator conditions across any timeframe. Run on demand or on a cron schedule. Historical runs are stored so you can track what matched over time.

### User Accounts
Full JWT auth — access tokens (60 min) + refresh tokens (30 days) with silent auto-refresh. All data is strictly isolated per user.

### Data Pipeline
- OHLCV bars cached in Postgres — the configured provider is only called for missing date ranges or stale data
- Raw provider observations are persisted alongside canonical read models so alternate provider copies are not lost
- Bulk historical fetch triggered automatically when a new instrument is first registered (ARQ background task)
- Nightly refresh job keeps all instruments current
- Identifier enrichment is opportunistic — instruments missing an external ID are backfilled naturally on profile/event access and scheduled maintenance
- Option contracts are canonical instruments with persisted chain snapshots and quote points (bid/ask/OI/IV/greeks as timeseries)

---

## Configuration

Copy and edit `.env.example`:

```env
# Required — generate with: openssl rand -hex 32
SECRET_KEY=your-64-char-hex-string

# Optional — push notifications (free at onesignal.com)
ONESIGNAL_APP_ID=your-onesignal-app-id
ONESIGNAL_REST_API_KEY=your-onesignal-rest-api-key

# CORS — add your NAS IP/hostname
CORS_ORIGINS=["http://localhost","http://your-nas-ip"]

# Alert engine poll interval in seconds
ALERT_POLL_INTERVAL=60

# Provider routing
DEFAULT_MARKET_DATA_PROVIDER=yfinance
DEFAULT_METADATA_PROVIDER=yfinance
DEFAULT_EVENT_PROVIDER=yfinance
DEFAULT_DISCOVERY_PROVIDER=yfinance
DEFAULT_OPTIONS_PROVIDER=yfinance
IDENTIFIER_PROVIDER_PRIORITY=["yfinance","openfigi"]
OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY=[]
PROVIDER_CHAIN_SEEDS={}
PROVIDER_RATE_LIMIT_SEEDS={}
PROVIDER_FRESHNESS_SEEDS={}
OPTION_CHAIN_REFRESH_HORIZON_DAYS=45

# Provider credentials / tuning
OPENFIGI_API_KEY=
OPENFIGI_TIMEOUT_SECONDS=10
MARKETDATA_API_KEY=
FMP_API_KEY=
```

The database and Redis URLs are pre-configured for the Docker Compose network and do not need to be changed for local/NAS deployment.

Provider responsibilities are capability-based. A single source can handle price history, metadata, events, discovery, and options, or those capabilities can be split across different providers. The `DEFAULT_*` variables are only seed values used to initialize DB-backed provider policies on first boot; after that, runtime routing and fallback are controlled from the database and the Settings UI.

Useful provider envs:

- `IDENTIFIER_PROVIDER_PRIORITY`: seed order for identifier enrichment.
- `OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY`: seed order for option quote-history providers.
- `PROVIDER_CHAIN_SEEDS`: JSON object overriding seed chains per capability, for example `{"instrument_metadata":["openfigi","yfinance"]}`.
- `PROVIDER_RATE_LIMIT_SEEDS`: JSON object keyed by provider. Values must be
  copied from the provider's current published contract and include a complete
  quota contract; there is no safe generic example or fallback.
- `PROVIDER_FRESHNESS_SEEDS`: JSON object keyed by capability, for example `{"price_history":300,"instrument_events":86400}`.
- `OPTION_CHAIN_REFRESH_HORIZON_DAYS`: refresh horizon for tracked-interest options maintenance.

Provider provenance is persisted alongside mastered instrument/detail/stat fields so it remains clear where key metadata came from, when it was observed, and why a given provider won field selection.

---

## Development

For active development you don't want to rebuild Docker containers after every code change. The dev setup runs only Postgres and Redis in Docker; the backend and frontend run directly on your machine with full hot-reload.

**Prerequisites:** Docker, Node.js 20+. `uv` is installed automatically.

```bash
# 1. One-time: install all dependencies
make dev-install

# 2. Start Postgres + Redis, apply migrations
make dev-infra

# 3. Start everything with hot-reload
make dev
```

After `make dev`:

| Service | URL | Reload |
|---|---|---|
| Frontend | http://localhost:5173 | Vite HMR — instant on `.vue`/`.ts` save |
| Backend | http://localhost:8000 | uvicorn `--reload` — restarts on `.py` save |
| API docs | http://localhost:8000/docs | Swagger UI |
| Worker | — | watchfiles restart on `.py` save |

**Python tooling — `uv`:** combines Python version management (like pyenv) and dependency management (like pip + venv) in one fast tool. The Python version is pinned in `backend/.python-version` (3.12.4). `make dev-install` handles everything automatically.

Prefer pyenv + venv? That works too:
```bash
pyenv install 3.12.4 && pyenv local 3.12.4
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
```

See [`docs/development.md`](docs/development.md) for VS Code setup, debugging, and Postgres access.

---

## Running Tests

```bash
# Fast unit tests — no containers required
make test-unit

# Integration tests — starts Postgres + Redis via testcontainers automatically
make test-int

# Frontend unit tests (Vitest)
make test-fe

# Everything (unit + integration + frontend)
make test

# E2E browser tests via Playwright — use the branch-scoped full stack
make test-stack-up
make test-e2e
# Optional cleanup when you're done
make test-stack-down
```

See [`docs/testing.md`](docs/testing.md) for full details including coverage targets and how to add tests.

---

## Documentation

| Document | What it covers |
|---|---|
| [Architecture](docs/architecture.md) | Design decisions, data model, service interactions |
| [API Reference](docs/api.md) | All REST endpoints with request/response examples |
| [Adding Indicators](docs/adding-indicators.md) | Step-by-step guide to adding a new indicator |
| [Testing Guide](docs/testing.md) | Test strategy, coverage targets, writing new tests |
| [Deployment](docs/deployment.md) | NAS setup, HTTPS with a reverse proxy, backup |
| [Development](docs/development.md) | Local dev setup, VS Code config, debugging |
