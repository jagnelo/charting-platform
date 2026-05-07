# API Reference

Base URL: `http://your-host:8000/api/v1`

All endpoints except `/auth/register` and `/auth/login` require a valid JWT access token:

```
Authorization: Bearer <access_token>
```

---

## Authentication

### POST /auth/register
Create a new user account. Also creates a default watchlist for the user.

**Request**
```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "SecurePass123!"
}
```

**Response** `201 Created`
```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "is_active": true,
  "is_admin": false,
  "last_login": null
}
```

**Errors** `400` username or email already registered

---

### POST /auth/login
Exchange credentials for JWT tokens.

**Request**
```json
{
  "username": "alice",
  "password": "SecurePass123!"
}
```

**Response** `200 OK`
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

**Errors** `401` invalid credentials

---

### POST /auth/refresh
Exchange a refresh token for a new access token. Pass the refresh token as a query parameter.

```
POST /auth/refresh?refresh_token=eyJ...
```

**Response** `200 OK`
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

**Errors** `401` token expired, invalid, or wrong type (access token passed instead of refresh)

---

### GET /auth/me
Get the currently authenticated user.

**Response** `200 OK`
```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "is_active": true,
  "is_admin": false,
  "last_login": "2024-03-01T09:00:00Z"
}
```

---

### POST /auth/change-password
```
POST /auth/change-password?old_password=OldPass123!&new_password=NewPass456!
```

**Response** `204 No Content`

**Errors** `400` old password incorrect

---

## Instruments

### GET /instruments/{symbol}
Retrieve an instrument by ticker symbol. If not in the database, the backend attempts to fetch metadata through the active provider chain and register it automatically.

**Response** `200 OK`
```json
{
  "id": 42,
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "currency": "USD",
  "is_active": true,
  "instrument_type": "Stock",
  "asset_class": "Equity",
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "market_cap": 3000000000000
}
```

**Errors** `404` symbol not found by any enabled metadata provider

---

### GET /instruments/{symbol}/provenance
Return field-level provenance, listings, identifiers, and recent provider snapshots for a canonical instrument.

---

## OHLCV Bars

### GET /ohlcv/{symbol}/{timeframe}
Fetch OHLCV bars for a symbol and timeframe. Bars are served from the database cache; gaps are filled automatically through the active market-data provider chain.

**Timeframes:** `M1` `M5` `M15` `M30` `H1` `H2` `H4` `H12` `D1` `W1` `MN`

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `start` | ISO 8601 datetime | Yes | Range start (UTC) |
| `end` | ISO 8601 datetime | Yes | Range end (UTC) |
| `adjusted` | bool | No (default `true`) | Use split/dividend-adjusted prices |

**Example**
```
GET /ohlcv/AAPL/D1?start=2024-01-01T00:00:00Z&end=2024-12-31T23:59:59Z
```

**Response** `200 OK`
```json
[
  {
    "ts": "2024-01-02T00:00:00Z",
    "open": "185.2000",
    "high": "188.4400",
    "low": "183.0600",
    "close": "185.8500",
    "volume": "68213100",
    "is_adjusted": true
  }
]
```

---

## Providers

### GET /providers
List registered providers plus their supported capabilities.

### GET /providers/policies
List runtime provider policy rows, including current scores, rate limits, freshness windows, and health metrics.

### GET /providers/health
List provider health telemetry per capability.

### PATCH /providers/policies/{provider_name}/{capability}
Update a provider policy row, for example enabling/disabling, pinning, or changing token limits.

---

## Options

### GET /instruments/{symbol}/options/expirations
Return stored option expirations for an underlying. If needed, the backend refreshes from the active option-chain provider chain first.

### GET /instruments/{symbol}/options/chain
Return a persisted option-chain snapshot for an underlying and expiration, including bid/ask/mark/last/volume/open interest/implied vol and greeks.

### GET /options/contracts/{instrument_id}
Return canonical metadata for a stored option contract.

### GET /options/contracts/{instrument_id}/quote-history
Return persisted option quote points for a contract. If a quote-history provider exists and the requested coverage is stale or missing, the backend can ingest before returning rows.

---

## Indicators

### GET /indicators
List all available indicators from the registry. No authentication required.

**Response** `200 OK`
```json
[
  {
    "name": "rsi",
    "display_name": "Relative Strength Index",
    "description": "Momentum oscillator measuring speed and magnitude of price changes.",
    "params_schema": {
      "period": { "type": "int", "default": 14, "min": 2, "max": 200 }
    },
    "output_columns": ["rsi"],
    "pane": "separate"
  }
]
```

---

### GET /indicators/compute/{symbol}/{timeframe}
Compute an indicator over cached OHLCV data and return the values aligned to timestamps. Useful for the frontend when local computation is unavailable or as a second source for verification.

**Query parameters**

| Parameter | Type | Description |
|---|---|---|
| `indicator` | string | Indicator name from the registry (e.g. `rsi`) |
| `params` | JSON string | Indicator parameters (e.g. `{"period": 14}`) |

**Response** `200 OK`
```json
{
  "timestamps": [1704067200, 1704153600, "..."],
  "values": {
    "rsi": [null, null, "...", 54.32, 61.17]
  }
}
```

If the indicator name is unknown:
```json
{ "error": "Unknown indicator: xyz" }
```

---

## Technical Radar

### GET /radar/runs
Return recent radar scan executions.

**Query parameters**

| Parameter | Type | Description |
|---|---|---|
| `limit` | int | Max number of recent runs to return (default `5`) |
| `timeframe` | string | Optional timeframe filter |

---

### POST /radar/run
Trigger a synchronous radar scan over the current active instrument universe.

**Request body**
```json
{
  "timeframe": "H4"
}
```

**Response** `200 OK`
```json
{
  "id": 12,
  "timeframe": "D1",
  "universe_type": "all",
  "status": "completed",
  "started_at": "2026-05-04T10:00:00Z",
  "completed_at": "2026-05-04T10:00:04Z",
  "evaluated_count": 842,
  "detection_count": 37,
  "error_summary": null
}
```

---

### GET /radar/detections
Return the latest completed radar detections with optional filtering.

Each summary row now also includes:

- `signal_at`
- `context_at`
- `state`
- `state_reason`
- `thread_id`
- `thread_event_index`
- `entry_price`
- `invalidation_price`
- `target_price`
- `outcome_status`
- `outcome_last_evaluated_at`
- `bars_since_signal`
- `max_favorable_excursion_pct`
- `max_adverse_excursion_pct`
- `target_hit_at`
- `invalidated_at`

Current setup values include `approaching_support`, `approaching_resistance`, `breakout`, `breakout_retest`, `breakdown`, `breakdown_retest`, `fakeout`, `fakedown`, `failed_reclaim`, `failed_breakdown_recovery`, `compression_support`, `compression_resistance`, `reclaim`, and `rejection`.

**Query parameters**

| Parameter | Type | Description |
|---|---|---|
| `timeframe` | string | Optional timeframe filter |
| `setup_type` | string | Optional setup filter |
| `state` | string | Optional state filter (`developing`, `confirmed`, `invalidated`, `expired`) |
| `min_score` | float | Minimum normalized score (0-1) |
| `symbol` | string | Case-insensitive symbol substring filter |
| `limit` | int | Max rows to return |
| `fresh_only` | bool | Exclude expired detections |

---

### GET /radar/detections/{detection_id}
Return one radar detection with its full evidence payload:

- chart overlays
- evidence metrics
- extracted structure metadata
- action-plan fields (`entry_price`, `invalidation_price`, `target_price`)
- current setup-thread summary
- ordered thread history for that setup storyline

The evidence payload can now include AVWAP anchor provenance, all-time / YTD / rolling-window context, and gap / trendline / simple pattern metadata.

---

### GET /radar/instruments/{instrument_id}/overlays
Return the active radar detections for one instrument, optionally narrowed to a single detection.

This is the endpoint used by the chart page to:

- populate the chart-side radar sub-panel for the loaded instrument
- render non-editable radar evidence overlays separate from saved drawings
- restore a preferred detection when navigation originated from `/radar`
- support focus-aware overlay rendering when multiple detections are enabled on the same symbol

**Query parameters**

| Parameter | Type | Description |
|---|---|---|
| `timeframe` | string | Optional timeframe filter |
| `detection_id` | int | Optional preferred detection id |
| `fresh_only` | bool | Exclude expired detections |

---

### GET /radar/instruments/{instrument_id}/history
Return prior radar detections for one instrument, ordered by signal time.

**Query parameters**

| Parameter | Type | Description |
|---|---|---|
| `timeframe` | string | Optional timeframe filter |
| `limit` | int | Max rows to return (default `150`) |

---

### GET /radar/outcomes/summary
Return grouped forward-outcome summaries by timeframe and setup type.

Each row includes:

- `timeframe`
- `setup_type`
- `total`
- `open_count`
- `target_hit_count`
- `invalidated_count`
- `expired_count`
- `target_hit_rate`
- `invalidated_rate`
- `avg_mfe_pct`
- `avg_mae_pct`

---

### POST /radar/detections/{detection_id}/actions/add-to-watchlist
Add the detection’s instrument to a target watchlist, or to the default radar watchlist when none is specified.

**Request body**
```json
{
  "watchlist_id": 9
}
```

---

### POST /radar/detections/{detection_id}/actions/create-price-alert
Create a price alert around the detection’s actionable level using the setup’s directional bias.

---

## Price Alerts

### GET /alerts/
List all price alerts for the current user.

**Query parameters**

| Parameter | Type | Description |
|---|---|---|
| `status` | `active` \| `triggered` \| `disabled` | Filter by status |
| `instrument_id` | int | Filter by instrument |

**Response** `200 OK` — array of alert objects (see create response below)

---

### POST /alerts/
Create a price alert.

**Request**
```json
{
  "instrument_id": 42,
  "condition": "crosses_above",
  "threshold_price": "200.00",
  "repeat": false,
  "notes": "Key resistance level"
}
```

**Conditions:** `crosses_above` `crosses_below` `touches` `percent_change_up` `percent_change_down`

**Response** `201 Created`
```json
{
  "id": 7,
  "instrument_id": 42,
  "user_id": 1,
  "condition": "crosses_above",
  "threshold_price": "200.00000000",
  "status": "active",
  "repeat": false,
  "notes": "Key resistance level",
  "last_known_price": null,
  "trigger_count": 0,
  "triggered_at": null,
  "last_notification_id": null,
  "created_at": "2024-03-01T10:00:00Z"
}
```

---

### DELETE /alerts/{id}
Delete an alert. Returns `404` if the alert belongs to another user.

**Response** `204 No Content`

---

### POST /alerts/{id}/rearm
Re-activate a triggered alert so it can fire again.

**Response** `200 OK` — updated alert object with `status: "active"`

---

### WebSocket /alerts/ws
Real-time alert trigger notifications. Connect to receive a message whenever any of your alerts fires.

**Connection:** `ws://your-host:8000/api/v1/alerts/ws`

**Keepalive:** Send `ping` text frame every 30 seconds; server responds with `{"type": "pong"}`.

**Alert trigger message**
```json
{
  "type": "alert_triggered",
  "alert_id": 7,
  "user_id": 1,
  "symbol": "AAPL",
  "condition": "crosses_above",
  "threshold": 200.0,
  "current_price": 201.5,
  "triggered_at": "2024-03-01T14:32:00Z"
}
```

---

## Indicator Alerts

### GET /indicator-alerts/
List all indicator alerts for the current user.

---

### POST /indicator-alerts/
Create an indicator alert. Two modes:

**Mode 1 — indicator vs fixed value** (e.g. RSI crosses below 30)
```json
{
  "instrument_id": 42,
  "timeframe": "D1",
  "indicator_type": "rsi",
  "indicator_params": { "period": 14 },
  "condition": "crosses_below",
  "threshold_value": "30",
  "repeat": true
}
```

**Mode 2 — indicator vs indicator** (e.g. EMA50 crosses above EMA200 — golden cross)
```json
{
  "instrument_id": 42,
  "timeframe": "D1",
  "indicator_type": "ema",
  "indicator_params": { "period": 50 },
  "condition": "crosses_above",
  "compare_indicator_type": "ema",
  "compare_indicator_params": { "period": 200 }
}
```

**Response** `201 Created` — indicator alert object with `status: "active"`

---

### DELETE /indicator-alerts/{id}
**Response** `204 No Content`

---

### POST /indicator-alerts/{id}/rearm
**Response** `200 OK`

---

## Drawings

### GET /drawings/
List drawings for an instrument/timeframe. Always includes `pin_to_all` drawings regardless of timeframe filter.

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `instrument_id` | int | Yes | Instrument to fetch drawings for |
| `timeframe` | string | No | Filter by timeframe; omit for all timeframes |

---

### POST /drawings/
Create a drawing.

**Request**
```json
{
  "instrument_id": 42,
  "timeframe": "D1",
  "drawing_type": "trendline",
  "data": {
    "points": [
      { "time": 1700000000, "price": 180.0 },
      { "time": 1701000000, "price": 195.0 }
    ]
  },
  "style": { "color": "#64b5f6", "lineWidth": 1.5, "lineDash": [] },
  "is_visible": true,
  "is_locked": false,
  "pin_to_all": false
}
```

**Drawing types:** `trendline` `horizontal_line` `vertical_line` `ray` `rectangle` `circle` `arrow` `text_box` `fibonacci_retracement` `fibonacci_extension`

**Response** `201 Created`

---

### PATCH /drawings/{id}
Update a drawing's data, style, or lock state. Only the fields provided are updated.

**Request** (all fields optional)
```json
{
  "data": { "points": ["..."] },
  "style": { "color": "#ff0000", "lineWidth": 2 },
  "is_visible": true,
  "is_locked": true
}
```

**Response** `200 OK`

---

### DELETE /drawings/{id}
**Response** `204 No Content`

---

## Indicator Presets

Presets are named collections of indicators (e.g. "Day Trading Setup" = EMA9 + EMA21 + RSI14).

### GET /presets/
List all presets for the current user.

### POST /presets/
```json
{
  "name": "Swing Trading",
  "indicators": [
    { "type": "ema", "params": { "period": 20 }, "style": { "color": "#26a69a" } },
    { "type": "ema", "params": { "period": 50 }, "style": { "color": "#ef5350" } },
    { "type": "rsi", "params": { "period": 14 }, "style": { "color": "#ba68c8" } }
  ],
  "is_default": true
}
```

Setting `is_default: true` automatically unsets any existing default preset for this user.

**Response** `201 Created`

### DELETE /presets/{id}
**Response** `204 No Content`

---

## Watchlists

### GET /watchlists/
List all watchlists for the current user.

**Response** `200 OK`
```json
[
  {
    "id": 1,
    "name": "Default",
    "is_default": true,
    "items": [
      { "id": 1, "instrument_id": 42, "symbol": "AAPL", "name": "Apple Inc.", "position": 0 }
    ]
  }
]
```

### POST /watchlists/
```json
{ "name": "Tech Stocks", "is_default": false }
```

### POST /watchlists/{id}/items
Add an instrument to a watchlist.
```json
{ "instrument_id": 42 }
```

### DELETE /watchlists/{id}/items/{instrument_id}
Remove an instrument from a watchlist.

---

## Screeners

### GET /screeners/
List all screeners for the current user.

### POST /screeners/
Create a screener with conditions.

```json
{
  "name": "Oversold Stocks",
  "description": "RSI below 30 on daily timeframe",
  "logic": "and",
  "watchlist_id": null,
  "schedule_cron": null,
  "conditions": [
    {
      "position": 0,
      "subject": "indicator",
      "timeframe": "D1",
      "operator": "lt",
      "indicator_type": "rsi",
      "indicator_params": { "period": 14 },
      "threshold_value": "30"
    }
  ]
}
```

**logic:** `and` | `or`

**subject:** `price` | `indicator` | `indicator_cross`

**operators:** `gt` `lt` `gte` `lte` `eq` `crosses_above` `crosses_below` `percent_above` `percent_below`

**Response** `201 Created` — screener object with conditions

---

### GET /screeners/{id}
Get a screener and its conditions. Returns `404` if it belongs to another user.

### DELETE /screeners/{id}
**Response** `204 No Content`

---

### POST /screeners/{id}/run
Run the screener immediately against all active instruments (or the watchlist if `watchlist_id` is set). The result is stored and returned.

**Response** `200 OK`
```json
{
  "id": 3,
  "screener_id": 1,
  "run_at": "2024-03-01T14:00:00Z",
  "matched_instrument_ids": [42, 57, 103],
  "total_scanned": 487,
  "duration_ms": 1842
}
```

---

### GET /screeners/{id}/results
List historical run results for a screener.

**Query parameters:** `limit` (default 20, max 100)

**Response** `200 OK` — array of result objects

---

## Error Format

All errors return a consistent JSON body:

```json
{ "detail": "Human-readable description of what went wrong" }
```

Common HTTP status codes:

| Code | Meaning |
|---|---|
| `400` | Bad request — validation error or business rule violation |
| `401` | Unauthenticated or token expired |
| `403` | No Authorization header provided |
| `404` | Resource not found or belongs to another user |
| `422` | Request body failed Pydantic schema validation |
| `500` | Unexpected server error (check backend logs) |
