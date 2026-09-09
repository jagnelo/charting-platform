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
It also prints a routing-safety preflight for FINRA's asynchronous result-byte
bound and the operation-level Tiingo/FMP byte-bound maps. A direct adapter read
can therefore be green while its provider remains non-routable: missing,
invalid, partial, or non-positive safety controls are reported explicitly and
never guessed.
The same preflight reports whether the non-secret
`MARKETSTACK_DISCOVERY_EXCHANGE` venue scope is configured; history can still
be probed with only the key, but discovery remains non-routable without it.
Before invoking pytest, the wrapper acquires an exclusive local lock at
`~/.config/charting-platform/provider-live.lock` (override with
`PROVIDER_LIVE_LOCK_FILE`). A second worktree on the same host therefore exits
with code `3` without making provider calls. This coordinates local worktrees
only; GitHub and deployed environments still need separate provider accounts,
environment concurrency controls, or an operator-approved shared-key window.
Each live pytest process also appends measured per-provider operation, HTTP
request, and response-byte totals to the external
`~/.config/charting-platform/provider-live-usage.jsonl` ledger (override with
`PROVIDER_LIVE_USAGE_LEDGER`). This supplements, rather than replaces, the
application database's durable runtime quota windows; it makes direct live-test
consumption visible across local sessions without storing credentials or
payloads.
Local secrets belong in the owner-only
`~/.config/charting-platform/app.env`. Worktree runtime setup links the ignored
`.env` and `backend/.env.dev` paths to that external source. Set
`CHARTING_PLATFORM_SHARED_ENV_FILE` to use another source. The exact variable
names are in `.env.example` and the provider ledger; never put values in Git.

GitHub uses the separate manually dispatched
`Credentialed Provider Live Validation` workflow. Configure its
`provider-live-validation` environment with same-named environment secrets and
with `EDGAR_USER_AGENT` and `FINRA_OTC_SYMBOL_DIRECTORY_URL` environment
variables. Put the reviewed non-secret safety settings
`FINRA_ASYNC_MAX_RESULT_BYTES`, `TIINGO_OPERATION_BYTE_BOUNDS`, and
`FMP_OPERATION_BYTE_BOUNDS` in the same environment's configuration variables;
the workflow passes them through without inventing defaults. Keep required
reviewers enabled. Ordinary push/PR CI deliberately
receives no provider secrets and makes no external provider calls, so a forked
PR cannot spend quotas or exfiltrate keys.

Provider usage is account- and/or IP-scoped by the vendor, not branch-scoped.
The durable request log and quota windows preserve usage across application
restarts and workers that share the same database, but a separate worktree,
CI database, deployment, or unrelated client using the same credential is not
visible to that local ledger unless the provider exposes a cumulative usage
header that the adapter safely reconciles. Credentialed live probes therefore
consume the same external allowance as the application and any parallel
development branch. Do not run the live matrix concurrently against a shared
key; use separate provider accounts/keys per environment when account-wide
isolation is required.

Deployments use a target-owned secret store, never the developer-machine file.
The RPi deployment already requires `/opt/charting-platform/shared/app.env`
with mode `0600`; the release Compose contract passes its provider variables
only to `backend` and `worker`. This includes the non-secret FINRA async result
bound and Tiingo/FMP operation-byte maps that control whether their bandwidth
dimensions can be admitted. The network-disabled `research-runner` receives
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

Additional bounded checks on 2026-09-09 covered the provider-specific surfaces
that the original one-read matrix did not exercise: Finnhub profile,
historical earnings, and forward earnings-calendar normalization passed in one
case (`3` requests, `170,868` response bytes); EODHD daily/weekly/monthly
history plus the free-plan Fundamentals entitlement check and FMP history plus
profile passed (`3/3` cases, successful ledger totals EODHD `4` requests/
`2,522` bytes and FMP `2` requests/`3,857` bytes). The EODHD free key's
Fundamentals `403` is retained as explicit non-entitlement evidence, not
treated as an empty profile or a successful capability. Alpha Vantage's IPO
calendar now has a dedicated live case: the current key returned a valid
68-byte CSV header with no currently published rows, so the adapter proved
transport/schema handling without fabricating an event; a positive IPO row
remains unobserved. Optional-provider HTTP failures now redact credentials
from direct/live tracebacks while retaining typed 429/reset evidence.

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
- latest combined unit + Docker-backed coverage gate: `1807 passed`, `80.22%`
  line coverage, above the repository `75%` threshold
- focused capacity/quota/runtime/provider-support tests: `17 passed`; capacity-admin plus provider API integration: `8 passed`
- migration compatibility: passed against the previous release head

429/418/quota responses now create durable `provider_capacity_event` records
with provider scope, status, filtered reset headers, retry time, and the
originating request-log link. The backend-only
`/api/v1/market-data/capacity-events` endpoint exposes this evidence to
administrators.

Provider error text is centrally redacted before it reaches durable request
logs, health state, capacity events, or live-probe failure output. The redactor
removes configured secret values and credential-bearing URL/header values, and
the persistence regression covers transport URLs that include an API key.

The remaining credentialed blockers are Alpaca, Tradier, and MarketData.app.
The authoritative rerun supplied a temporary non-secret SEC EDGAR User-Agent
and passed the EDGAR cases; every deployment and CI environment must still
provide its own operator contact value. A provider may have a green live probe
and remain non-routable when any external constraint cannot yet be accounted
safely. Every registered synchronous adapter now reports
observed HTTP request counts, response bytes, and selected provider headers
into the runtime context; that telemetry is durable in
`provider_request_log`, and the provider usage endpoint exposes the latest
filtered header snapshot plus active durable quota-window reservations for
operator inspection, including the durable distinct-identity count for
identity-metered dimensions. Twelve Data's cumulative
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
bandwidth reset are represented in the durable calendar-window engine. Tiingo's
500-symbol monthly pool is enforced by the durable `provider_quota_identity`
ledger, which claims each normalized provider symbol once per window and does
not approximate repeated calls as new symbols. FINRA's synchronous short-interest and OTC Daily List
calls reserve the documented 3 MB maximum response against the 10 GB monthly
credential budget and settle to measured bytes; its asynchronous
submit/poll/presigned-download path is implemented as a documentation-faithful
direct adapter. A positive `FINRA_ASYNC_MAX_RESULT_BYTES` promotes the signed
download operation into the durable monthly byte reservation; the default `0`
remains non-routable because provider results are otherwise unbounded. FRED v1
records the official 120-requests/minute threshold but remains non-routable
until the deployment supplies the explicit reviewed controls
`FRED_REVIEWED_LIMIT_SCOPE`, `FRED_REVIEWED_REQUESTS_PER_MINUTE` (1..120), and
`FRED_SERIES_TERMS_REVIEWED=true`; these controls make the operator's
conservative decision observable without pretending the provider's adjustable
scope is fixed. Nasdaq Trader's polling allowance remains unpublished. IBKR remains a
descriptor without an authenticated account adapter.

The public tokenized matrix is maintained separately in
`tests/live/test_tokenized_providers_live.py`. It covers xStocks, Robinhood
Chain Stock Tokens, Bybit xStocks, Gate TradFi stock endpoints, and Kraken's
current xStocks catalogue. The latest bounded run passed all five probes, and
the quote assertions observed at least two upstream requests for every
successful quote operation (metadata resolution plus quote/order-book read).
The Kraken result was an empty provider catalogue (no current xStocks pair),
and Robinhood returned one transient `local_rate_limited` response before the
test's single provider-specific retry succeeded; neither result is treated as
permission to guess a ticker or a quota.

The CoinGecko credentialed probes also cover the compound metadata operation:
the provider resolves a ticker through ranked `/search` results and then reads
the canonical `/coins/{id}` profile. The bounded live probe verified
`BTC-USD` resolves to Bitcoin and observed at least two upstream requests;
runtime accounting reserves both calls. This avoids selecting the first
ambiguous row from `/coins/list`.

The complete manifest-driven matrix also wraps every available non-tokenized
provider read in transport telemetry and requires at least one observed HTTP
request and positive response bytes. SEC and Nasdaq directory pagination is
cache-aware: the cache-populating read must produce transport evidence, while
subsequent locally served pages are validated for completeness without being
misreported as new network calls.

The still-missing variables are `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`,
`TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`. `EDGAR_USER_AGENT` was
supplied as a temporary non-secret override for the latest local run, but
remains an explicit per-environment configuration requirement. Until the three
credential domains are supplied and their cases pass, the complete manifest
matrix remains an open acceptance gate.

Marketstack history and discovery are intentionally separate gates: a key is
enough for the bounded EOD history probe, while venue discovery also requires
the non-secret `MARKETSTACK_DISCOVERY_EXCHANGE` MIC/exchange setting. The
adapter no longer defaults discovery to `XNYS`, so a single-venue read cannot
be mistaken for complete US listing coverage.

The latest network-enabled rerun at `2026-09-09T18:59:06Z`, using the existing
external keys plus a temporary non-secret SEC User-Agent and explicit
`MARKETSTACK_DISCOVERY_EXCHANGE=XNAS`, collected 32 cases: 29 passed with
positive transport observations across the available keyless and credentialed
adapters, including all five tokenized providers, OpenFIGI after its prior
cooldown, and the header-only Alpha Vantage IPO-calendar response. Three failed
exact credential preflight for `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`,
`TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`. The wrapper returned exit code
2 and made no acceptance claim. FRED now reports its three explicit missing
review controls (`FRED_REVIEWED_LIMIT_SCOPE`,
`FRED_REVIEWED_REQUESTS_PER_MINUTE`, and `FRED_SERIES_TERMS_REVIEWED`) rather
than an opaque generic blocker. FINRA asynchronous result bytes, Nasdaq polling,
xStocks quota/legal eligibility, Bybit endpoint/UID state, and Tiingo/FMP
operation byte maps remain non-routable because their reviewed controls are not
configured.

The wrapper also reports the remaining provider-specific admission gates
explicitly: FRED's v1 limit scope/adjustable-limit/series-terms review,
Nasdaq Trader's unpublished polling allowance, xStocks' unpublished public
quota plus its official US-person/jurisdiction/redistribution restriction,
and Bybit's endpoint/UID header state. A positive live read for any of these
providers is therefore not treated as routing admission.

The MarketData.app adapter was also checked against the current official API
root during this checkpoint: versioned resources are under
`https://api.marketdata.app/v1` (not `/api/v1`). The checked-in contract records
the documented 100-credit daily free window, its 09:30 America/New_York reset,
and the 50-request concurrent ceiling; the adapter path, Bearer-auth shape, and
durable release-only in-flight reservation are covered by fixture/unit tests.
A credentialed live read is still required before this provider can be accepted
for routing.
