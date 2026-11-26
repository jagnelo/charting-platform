# fix/provider-negative-memo

Created from `staging` at `24b62e7e09b3e0e568818951b8e26a3fbee66952`.

## Human authorization

- Recorded at: 2026-11-26T16:15:18.490595+00:00
- Request: do ALL of these
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: draft; the implementation agent must complete scope, acceptance criteria, tests, and local validation profile before creating a goal.

Update this handoff at each coherent boundary.

## Implementation notes (provider negative memo)

Cause: the worker wasted free-tier provider requests on answers that never change.
- xstocks logged about 150/h `all providers exhausted for tokenized_assets/get_tokenized_price - HTTP 404` (1468 in 6h): tokens xstocks does not list, re-requested every refresh cycle.
- The no-data history slice memo lived only in process memory, so each worker restart re-asked Alpaca for every slice (about 4.6k no-data/h).
- Finnhub/FMP profile lookups were retried for symbols the free plans do not serve.

Fix:
- `backend/app/services/negative_memo.py`: best-effort Redis memo (existing `REDIS_URL`, keys `charting:negmemo:*`, 0.5s socket timeouts, 30s cool-down after a failure; never raises).
- `market_data.py`: no-data slices are mirrored to Redis with the same 12h TTL and 2-day minimum slice age (only slices remembered locally are persisted); on read, pending slices are checked locally, then with one Redis MGET, and warm the dict.
- `provider_runtime.py`: per-(provider, capability, operation, symbol) memo for `get_tokenized_price` and `get_instrument_profile`. HTTP 404 is remembered 7d, HTTP 402/403 3d, a definitive "returned no usable data" 2d; 429, 5xx, timeouts and quota denials are never remembered. `execute_provider_call` drops remembered providers from the chain; if none remain it raises `ProviderNoDataError`.
- `tokenized_assets.refresh_tokenized_prices`: skips remembered tokens before any provider call (result gains `skipped_not_listed`), so there is no request and no ERROR log.
- `tests/unit/conftest.py`: autouse fixture keeps unit tests off a real Redis and clears the identity memo.

Evidence (production, 7 days of provider_request_log, SELECT only):
- Finnhub get_instrument_profile 403: 1182 requests, 100% on tickers shaped like US mutual funds (four letters plus X, e.g. NICHX, LTCFX; 259 symbols, 0 successes), plus 7 on preferred/punctuated symbols. Free Finnhub does not serve fund profiles; 403 is symbol-class specific, not a key fault (5302 other profile calls succeeded).
- Finnhub profile no-data: 13636 requests across about 1.6k symbols (ETFs, warrants, expired/derivative ids such as 2200963D, crypto pairs like 00-USD); symbol-specific and stable.
- FMP profile: 75 HTTP 402 Payment Required, all dot-class symbols (MOG.A, BF.B, ADC.PRA), 0 dot successes; free plan excludes them. FMP no-data 876 vs 438 successes: mostly mutual funds, crypto pairs and non-covered symbols.
- Decision: a per-symbol negative memo (not a blanket capability gate) because both providers still serve many symbols in each broad class; the memo stops the repeat requests while keeping the fallback chain.
