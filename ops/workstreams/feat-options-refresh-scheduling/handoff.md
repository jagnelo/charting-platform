# Handoff: options refresh scheduling

## Findings (production, read-only, 2026-11-26)
- `option_detail`, `option_chain_snapshot`, `option_quote_point`, option dataset states and OPTION
  provider symbols: 0 rows. Options are only ever fetched on demand by `/instruments/.../options/*`
  (`options_data.py`); no cron or `market_refresh_job` (queue only has price_history and
  instrument_metadata) touched them.
- Latent bug: `ensure_option_contract` creates active `Instrument` rows; the background planner in
  `enqueue_workstation_maintenance` selects every active non-synthetic instrument for D1 history, so
  contracts would have been queued as stock OHLCV work. Now excluded.
- Providers: only `marketdata_app` is enabled for OPTION_CHAIN / OPTION_QUOTE_HISTORY / OPTIONS_CURRENT
  (tradier and yfinance policies disabled; yfinance also lacks archive authority). MarketData.app free:
  100 credits/day, resets 09:30 ET, data >=24h delayed. Expirations 1 credit; chain billed per returned
  contract and fail-closed until `MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS>=2`; quote history 1 credit
  per 1,000 quotes. Greeks/IV/OI come with chains and quote history; missing greeks are estimated locally.
  Provider usage so far: 11 `fetch_account_usage` calls only.

## Design
`app/services/options_refresh.py`, cron `scheduled_options_refresh` (14:45 UTC, after the MarketData.app
reset and far from the 22:00 core equity planner; separate provider pool from Alpaca core D1 so core
work is never starved). Disabled by default (`OPTIONS_REFRESH_ENABLED`).
- Expired contracts are deactivated first; selection uses expiry >= today and <= today +
  `OPTION_CHAIN_REFRESH_HORIZON_DAYS` (45).
- Phase 1: up to `OPTIONS_REFRESH_MAX_UNDERLYINGS` (3) stalest Stock/ETF underlyings (core workstation,
  saved-watchlist, or with persisted contracts), `list_option_expirations(refresh=True)` then nearest
  `OPTIONS_REFRESH_EXPIRATIONS_PER_UNDERLYING` (1) active chain(s).
- Phase 2: up to `OPTIONS_REFRESH_MAX_CONTRACTS` (10) stalest active contracts, quote history over
  `OPTIONS_REFRESH_QUOTE_LOOKBACK_DAYS` (7).
- Credit worst case per day: 3 expirations + chain bound x3 + 10 quote calls; the ledger still admits.
- Idempotency: caps are per UTC day, remaining = cap - distinct instruments already fetched today
  (dataset_state.fetched_at); rerun is a no-op. RateLimit/QuotaUnknown stops run; 3 consecutive failures
  stop; wall budget `OPTIONS_REFRESH_TIME_BUDGET_SECONDS` (420).

## Evidence
`pytest tests/unit/services/test_options_refresh.py tests/unit/services/test_options_data.py
tests/unit/workers tests/unit/test_provider_secret_wiring.py tests/unit/tasks`: 245 passed; ruff clean.

## Gaps
Chains need the operator to set MAX_SYMBOLS; no intraday option data on free tiers; index/futures
options and underlyings outside Stock/ETF not covered; no dedicated queue priority (separate pool +
schedule used instead); not deployed or enabled.

## Orchestrator review (2026-11-26)

- Switched on by default (`OPTIONS_REFRESH_ENABLED=true`) under the standing direction to run the real
  free-provider configuration rather than blanket disables.
- `OPTIONS_REFRESH_MAX_UNDERLYINGS` is lowered to 2. Production sets
  `MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS=20`, so each chain costs up to 20 credits. The daily worst case
  is 2 + 40 + 10 = 52 of the 100 free credits, which leaves headroom for on-demand option requests.
