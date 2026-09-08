# Provider live-validation matrix

The live matrix is intentionally separate from normal unit/integration runs:

```sh
RUN_LIVE_PROVIDER_TESTS=1 rtk uv run --project backend python scripts/run-live-provider-probes.py
```

The command performs a preflight, prints every missing environment variable,
runs one bounded read per provider (including the public tokenized-security
matrix), and returns non-zero when a credentialed
probe is blocked. A missing credential is never reported as a passing skip.
The wrapper returns exit code `2` for an incomplete credential preflight.
Local secrets belong in the owner-only
`~/.config/charting-platform/app.env`. Worktree runtime setup links the ignored
`.env` and `backend/.env.dev` paths to that external source. Set
`CHARTING_PLATFORM_SHARED_ENV_FILE` to use another source. The exact variable
names are in `.env.example` and the provider ledger; never put values in Git.

GitHub uses the separate manually dispatched
`Credentialed Provider Live Validation` workflow. Configure its
`provider-live-validation` environment with same-named environment secrets and
with `EDGAR_USER_AGENT` and `FINRA_OTC_SYMBOL_DIRECTORY_URL` environment
variables. Keep required reviewers enabled. Ordinary push/PR CI deliberately
receives no provider secrets and makes no external provider calls, so a forked
PR cannot spend quotas or exfiltrate keys.

Deployments use a target-owned secret store, never the developer-machine file.
The RPi deployment already requires `/opt/charting-platform/shared/app.env`
with mode `0600`; the release Compose contract passes its provider variables
only to `backend` and `worker`. The network-disabled `research-runner` receives
none. Other targets must provide an equivalent runtime secret manager or
permission-restricted env file.

## Evidence captured in this worktree

On 2026-09-07, the 13 probes covered by operator-supplied credentials passed
after enforcing non-empty provider-native results: Massive, Alpha Vantage,
CoinGecko, FRED, FINRA short interest, FINRA OTC Daily List, FINRA OTC Security
Master, Tiingo, Twelve Data, Finnhub company profile, Marketstack, EODHD, and
FMP. The run used one bounded read per case (`13 passed, 11 deselected`). It
also exposed and corrected entitlement/API mismatches: Alpha Vantage's free
key supports the compact latest-100 daily response rather than full history,
Finnhub's free key rejected stock candles but supports company profiles, and
FMP history now uses its current `/stable` API instead of `/api/v3`.

On 2026-09-05, with network access, a temporary non-secret SEC User-Agent, and
the official FINRA OTC Security Master URL, the public/keyless matrix passed
`9/9`, including full SEC ticker/exchange-directory pagination, full Nasdaq
directory pagination for both equities and ETFs, and full FINRA OTC DAPI
pagination:

```sh
RUN_LIVE_PROVIDER_TESTS=1 EDGAR_USER_AGENT='charting-platform live-validation ops@example.invalid' \
  FINRA_OTC_SYMBOL_DIRECTORY_URL='https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster' \
  rtk uv run --project backend pytest tests/live/test_market_data_providers_live.py \
  -m live -k 'openfigi or sec_edgar or nasdaq or binance or coinbase or kraken or finra_otc_directory' \
  --no-header -q --no-cov
# 9 passed, 15 deselected
```

A later bounded rerun passed the other six keyless probes but received an honest
OpenFIGI HTTP 429 after additional anonymous traffic. After the documented
anonymous window reset, the bounded keyless matrix passed again; the
intermediate 429 remains recorded as rate-limit evidence, not hidden.

The standalone venue-disambiguated OpenFIGI probe also passed `1/1`:

```sh
RUN_LIVE_PROVIDER_TESTS=1 rtk uv run --project backend pytest \
  tests/live/test_openfigi_live.py -m live --no-header -q --no-cov
# 1 passed
```

The backend deterministic gates pass on the current corrective revision:

- unit suite: `1384 passed`
- Docker-backed integration suite: `371 passed` on the current branch; the
  isolated testcontainer resources were cleaned after the run
- combined unit + Docker-backed coverage gate: `1756 passed`, `80.11%` line
  coverage, above the repository `75%` threshold
- focused capacity/quota/runtime/provider-support tests: `17 passed`; capacity-admin plus provider API integration: `8 passed`
- migration compatibility: passed against the previous release head

429/418/quota responses now create durable `provider_capacity_event` records
with provider scope, status, filtered reset headers, retry time, and the
originating request-log link. The backend-only
`/api/v1/market-data/capacity-events` endpoint exposes this evidence to
administrators.

The remaining credentialed blockers are Alpaca, Tradier, and MarketData.app;
SEC EDGAR also needs an operator contact User-Agent. A provider may have a
green live probe and remain non-routable when any external constraint cannot
yet be accounted safely. Every registered synchronous adapter now reports
observed HTTP request counts, response bytes, and selected provider headers
into the runtime context; that telemetry is durable in
`provider_request_log`, and the provider usage endpoint exposes the latest
filtered header snapshot plus active durable quota-window reservations for
operator inspection. Twelve Data's cumulative
`api-credits-used`/`api-credits-left` headers, Tradier's
allowed/used/available token-window headers, and Binance's one-minute used
weight are reconciled only when each observation proves its matching reviewed
contract limit; stale or mismatched observations cannot reduce local
consumption. Other byte ceilings and dynamic response-header/account budgets
are not implicitly guessed. Tiingo and FMP remain non-routable unless the
deployment supplies a positive, provider-reviewed maximum response size for
every exposed operation through `TIINGO_OPERATION_BYTE_BOUNDS` and
`FMP_OPERATION_BYTE_BOUNDS` JSON maps. When complete maps are present, the
runtime reserves the documented bandwidth pool before execution and settles it
to measured response bytes; incomplete or invalid maps remain fail-closed.
Tiingo's first-of-month Eastern bandwidth reset and FMP's rolling 30-day
bandwidth reset are represented in the durable calendar-window engine. FINRA's synchronous short-interest and OTC Daily List
calls reserve the documented 3 MB maximum response against the 10 GB monthly
credential budget and settle to measured bytes; its asynchronous
submit/poll/presigned-download path is implemented as a documentation-faithful
direct adapter but remains non-routable until the unbounded async-result byte
budget is safely reserved. FRED v1 and Nasdaq Trader remain non-routable because
their official documentation publishes throttling behavior without a numeric
ceiling. IBKR remains a descriptor without an authenticated account adapter.

The public tokenized matrix is maintained separately in
`tests/live/test_tokenized_providers_live.py`. It covers xStocks, Robinhood
Chain Stock Tokens, Bybit xStocks, Gate TradFi stock endpoints, and Kraken's
current xStocks catalogue. The latest bounded run passed all five probes. The
Kraken result was an empty provider catalogue (no current xStocks pair), and
Robinhood returned one transient `local_rate_limited` response before the
test's single provider-specific retry succeeded; neither result is treated as
permission to guess a ticker or a quota.

The still-missing variables are `EDGAR_USER_AGENT`, `ALPACA_API_KEY`,
`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`. Until
those are supplied and their cases pass, the complete 29-case matrix remains
an open acceptance gate.

The MarketData.app adapter was also checked against the current official API
root during this checkpoint: versioned resources are under
`https://api.marketdata.app/v1` (not `/api/v1`). The checked-in contract records
the documented 100-credit daily free window, its 09:30 America/New_York reset,
and the 50-request concurrent ceiling; the adapter path and Bearer-auth shape
are covered by a fixture test. A credentialed live read is still required before
this provider can be accepted for routing.
