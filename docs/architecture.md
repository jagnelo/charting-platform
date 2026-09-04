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
issuer (legal entity; CIK/LEI and provenance)
instrument_identity_quarantine (unresolved/ambiguous provider candidates)
market_series (venue/feed/session/timeframe/adjustment scope)
exchange_session_rule / exchange_calendar_exception (versioned calendars)
data_source (provider-backed, extensible)
  └── supported_capabilities (price_history, instrument_metadata, option_chain, ...)
provider_policy / provider_health_state / provider_request_log
provider_quota_window / provider_workload_lease / provider_routing_decision
instrument_profile_snapshot / market_bar_observation / instrument_dataset_state
market_event / fundamental_fact / short_interest_observation
market_universe_reconciliation_run / market_universe_lifecycle_observation
market_coverage_snapshot / provider_shadow_observation / market_data_anomaly
option_chain_snapshot / option_quote_point

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
  ├── radar_run / radar_detection (engine-owned market discovery artefacts)
  ├── watchlist
  │     └── watchlist_item
  └── screener
        ├── screener_condition
        └── screener_result
```

### Key design decisions

**Single `ohlcv_bar` table with a timeframe enum** — avoids the common mistake of splitting daily and intraday into separate tables. Queries simply filter on `timeframe = 'D1'`.

**`instrument` is universal** — options and futures are instruments with a detail row, not separate tables. This means a screener condition can target any instrument type with the same code path.

**`instrument_listing` separates instrument from exchange** — AAPL on NASDAQ and AAPL on XETR are the same `instrument` but different `instrument_listing` rows. Price data is fetched via the listing's ticker symbol on its exchange. `instrument.domain_key` (FIGI namespace where possible) is the stable cross-provider identity; ticker/provider-symbol rows are effective-dated evidence.

**`market_series` separates a security from a feed** — A regular-session SIP series, an IEX overlay, a provider-native daily series, and a split-adjusted canonical series are distinct rows. Rollups are created only from acquired finer bars; missing sessions are never fabricated.

**`chart_drawing.timeframe` is nullable + `pin_to_all`** — a drawing with `pin_to_all=True` appears on all timeframes for that instrument. `timeframe=None` with `pin_to_all=False` is invalid by convention.

**Provider capabilities are split, not monolithic** — the registry resolves price history, latest price, metadata, discovery, identifier, event, and option-chain capabilities independently. One provider may implement several capabilities, but the app no longer assumes that every provider does everything.

**Field provenance is persisted with mastered metadata** — canonical instrument/detail/stat rows keep JSON provenance per field so the app can explain which provider last supplied a value and when it was refreshed.

**Raw observations and canonical read models are separate** — provider snapshots and observations are stored first (`instrument_profile_snapshot`, `market_bar_observation`, `option_chain_snapshot`, `option_quote_point`), then reconciled into canonical rows such as `instrument`, `instrument_stats`, `ohlcv_bar`, and `instrument_event`.

**Provider routing is DB-controlled at runtime** — env vars seed the initial provider chain, rate limits, and freshness windows, but day-to-day ordering, pinning, and auto-weighting live in `provider_policy` and `provider_health_state`.

**Quota-aware routing is durable and explainable** — workers reserve units in `provider_quota_window`, receive a short-lived `provider_workload_lease`, and write a `provider_routing_decision` explaining accepted/rejected candidates. Coverage snapshots, shadow comparisons, and anomaly records are also durable; shadow rows default to `routing_enabled=false`. Optional provider descriptors are visible to administrators but remain disabled until reviewed.

**Universe lifecycle is observation-based** — complete discovery pages are
retained as provider snapshots and summarized in
`market_universe_reconciliation_run`. Per-symbol/venue presence is tracked in
`market_universe_lifecycle_observation`; a failed or empty provider response
never counts as a complete absence, and listing/instrument retirement requires
repeated missing confirmations. SEC CIK values are retained on the issuer and
never used alone to merge a new security; a security-level key or review is
required. Core D1 coverage is recorded after successful reconciliation with
exchange holiday exceptions applied.

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
    Return from DB         Fetch gaps via provider executor
                                         │
                          Persist provider observations first
                                         │
                           Reconcile/update canonical bars
                                         │
                               Return merged dataset
```

The caching key is `(instrument_id, timeframe, ts, is_adjusted)`. The unique constraint on `ohlcv_bar` prevents duplicates even if two requests race.

---

## Alert Engine

The alert engine runs as an APScheduler job inside the FastAPI process (configurable interval, default 60s). On each tick:

1. Load all `ACTIVE` price alerts from DB, grouped by instrument
2. For each instrument, resolve the active latest-price provider chain and fetch through the provider executor
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
| `run_radar_scan_task` | API request / future schedule | Persist a market-wide technical radar scan |
| `check_all_alerts` | APScheduler | Alert evaluation (also runs in main process as fallback) |

---

## Technical Radar

The radar is a separate backend subsystem from screeners. Screeners answer “does this instrument match a user-authored ruleset right now?” while radar answers “what technically interesting setups does the system currently see across the universe, and why?”

Current implementation characteristics:

- engine-owned persisted runs and detections
- persisted setup threads that link related detections across runs
- persisted detection/thread state fields for evolving setup status
- timeframe-aware manual scanning and filtering
- non-editable chart overlays generated from persisted evidence payloads
- chart-side instrument radar panel with per-detection toggles
- focus-aware chart overlay dimming when multiple detections are enabled
- explicit action-level fields (`entry_price`, `invalidation_price`, `target_price`)
- normalized scoring with stored factor breakdowns
- direct radar alert/watchlist workflow actions
- per-instrument history browsing plus aggregate outcome summaries

Current structure sources:

- clustered swing-based support/resistance zones
- anchored VWAP from recent/contextual anchors
- EMA context
- 52-week high/low context
- all-time / YTD / rolling-window context
- diagonal trendlines
- gap zones
- simple channel / wedge / triangle context when both sides of a structure can be inferred

Current event families now include:

- approachings
- breakouts / breakdowns
- reclaims / rejections
- breakout retests / breakdown retests
- fakeouts / fakedowns
- failed reclaim / failed breakdown recovery
- compression support / compression resistance

The radar currently favors transparency over sophistication: evidence is stored in a format directly consumable by the UI so the chart can show the same structures used by the scorer.

The newer thread layer sits between raw detections and the UI:

- scan runs persist one or more detections
- detections are matched into `radar_setup_thread` records by instrument, role, and nearby level
- threads now also retain a current state and state-change timestamp
- detail/chart consumers can then render a sequence of related events instead of a flat list with no memory

Chart behavior is intentionally split into two modes:

- opening a symbol directly in `/chart/:symbol` loads the instrument’s current detections into the radar panel but leaves them disabled by default
- opening a symbol from `/radar` carries an internal preferred detection handoff so the target symbol opens with that one detection enabled

This keeps radar evidence discoverable on the chart without turning the chart route into a fragile public URL contract for individual detection ids.

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
