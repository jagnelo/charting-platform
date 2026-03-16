# Architecture

## Design Goals

1. **Single-user first, multi-user ready** — one Postgres DB, per-user row-level isolation on all data tables. No shared global state.
2. **Local data ownership** — all OHLCV data is cached in Postgres. Once fetched, the app works offline.
3. **Extensible indicators** — adding an indicator requires one class. No router, schema, or migration changes.
4. **Alerts that work when the browser is closed** — alert evaluation runs in the backend process on a timer, not in the browser.

---

## Data Model

```
asset_class (Equity, Fixed Income, Crypto, ...)
  └── instrument_type (Stock, ETF, Future, Option, ...)
        └── instrument  ←─── universal entity (AAPL, BTC-USD, ...)
              ├── equity_detail
              ├── future_detail
              ├── option_detail (with greeks)
              └── forex_detail

exchange (MIC code, timezone, market hours)
instrument_listing  (ticker per exchange — AAPL on NASDAQ vs XETR)
data_source (yfinance, extensible)

ohlcv_bar
  ├── instrument_id  (FK → instrument)
  ├── timeframe      (enum: M1 M5 M15 M30 H1 H2 H4 H12 D1 W1 MN)
  ├── ts             (timestamp with timezone)
  ├── open/high/low/close/volume
  └── is_adjusted    (unique constraint: instrument+timeframe+ts+is_adjusted)

user
  ├── chart_drawing   (per user, per instrument, per timeframe or pin_to_all)
  ├── indicator_preset (named reusable indicator sets)
  ├── price_alert     (raw price conditions)
  ├── indicator_alert (indicator value conditions)
  ├── watchlist
  │     └── watchlist_item
  └── screener
        ├── screener_condition
        └── screener_result
```

### Key design decisions

**Single `ohlcv_bar` table with a timeframe enum** — avoids the common mistake of splitting daily and intraday into separate tables. Queries simply filter on `timeframe = 'D1'`.

**`instrument` is universal** — options and futures are instruments with a detail row, not separate tables. This means a screener condition can target any instrument type with the same code path.

**`instrument_listing` separates instrument from exchange** — AAPL on NASDAQ and AAPL on XETR are the same `instrument` but different `instrument_listing` rows. Price data is fetched via the listing's ticker symbol on its exchange.

**`chart_drawing.timeframe` is nullable + `pin_to_all`** — a drawing with `pin_to_all=True` appears on all timeframes for that instrument. `timeframe=None` with `pin_to_all=False` is invalid by convention.

---

## OHLCV Caching Flow

```
Frontend: GET /ohlcv/AAPL/D1?start=2024-01-01&end=2024-12-31
                        │
Backend: check DB for bars in range
                        │
           ┌────────────┴────────────────┐
           │ All bars present            │ Gaps or stale (>20 min)
           │ and fresh                   │
           ▼                             ▼
    Return from DB             Fetch gaps from yfinance
                                         │
                               Store new bars (upsert)
                                         │
                               Return merged dataset
```

The caching key is `(instrument_id, timeframe, ts, is_adjusted)`. The unique constraint on `ohlcv_bar` prevents duplicates even if two requests race.

---

## Alert Engine

The alert engine runs as an APScheduler job inside the FastAPI process (configurable interval, default 60s). On each tick:

1. Load all `ACTIVE` price alerts from DB, grouped by instrument
2. For each instrument, fetch current price from yfinance via `fast_info.last_price` (single ticker info call)
3. Evaluate each alert's condition using `last_known_price` for crossing detection
4. On trigger: update DB, send OneSignal push notification, broadcast WebSocket message
5. Update `last_known_price` for all alerts (even those that didn't trigger)

Indicator alerts follow the same flow but additionally:
1. Load recent OHLCV bars from DB (no network call needed if data is fresh)
2. Compute the indicator(s) using the backend indicator engine
3. Evaluate the condition against the latest value and the previous value (for crossing detection)

---

## Background Tasks (ARQ)

Long-running jobs that should not block the API run as ARQ tasks in a separate `worker` container:

| Task | Trigger | Description |
|---|---|---|
| `fetch_instrument_history` | New instrument registered | Pull all available history across all timeframes |
| `fetch_all_instruments_history` | Nightly cron | Refresh recent data for all instruments |
| `run_screener_task` | API request | Run a specific screener against the DB |
| `run_all_scheduled_screeners` | Every minute | Check cron schedules and run due screeners |
| `check_all_alerts` | APScheduler | Alert evaluation (also runs in main process as fallback) |

---

## Authentication

JWT-based with two tokens:

| Token | Lifetime | Stored in | Purpose |
|---|---|---|---|
| Access token | 60 minutes | `localStorage` | API requests (`Authorization: Bearer <token>`) |
| Refresh token | 30 days | `localStorage` | Obtaining new access tokens silently |

The API client (`src/lib/api.ts`) intercepts 401 responses, automatically refreshes the access token using the refresh token, and retries the original request — all transparently to the calling code.

All routes except `/auth/register` and `/auth/login` require a valid access token. The FastAPI `get_current_user` dependency validates the token and injects the `User` object; row-level queries always filter by `user_id = current_user.id`.

---

## WebSocket Architecture

A single WebSocket endpoint (`/api/v1/alerts/ws`) is used for real-time alert notifications.

- The `WebSocketManager` class maintains a list of active connections
- Alert triggers (from the alert engine) call `ws_manager.broadcast(message)`
- All connected clients receive every triggered alert message; the frontend filters by `user_id` to show only relevant notifications
- The frontend auto-reconnects with 5s backoff if the connection drops
- A ping/pong keepalive runs every 30 seconds from the client

In a future multi-server deployment, the WebSocket manager would need to be backed by Redis pub/sub so broadcasts reach all backend instances. This is a known limitation of the current in-process manager.
