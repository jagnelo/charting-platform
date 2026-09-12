# Provider live-validation matrix

The live matrix is intentionally separate from normal unit/integration runs:

```sh
PROVIDER_LIVE_USAGE_SCOPE=local-dev RUN_LIVE_PROVIDER_TESTS=1 \
  rtk uv run --project backend python scripts/run-live-provider-probes.py
```

The command performs a preflight, prints every missing environment variable,
runs one bounded read per provider (including the public tokenized-security
matrix), and returns non-zero when a credential or usage-attribution preflight
is blocked. A missing credential is never reported as a passing skip. The
wrapper returns exit code `2` for an incomplete credential/usage preflight.
It also prints a routing-safety preflight for Alpaca's paginated corporate-actions
page bound, FINRA's asynchronous result-byte
bound, FINRA OTC's reviewed operation-cost/terms/completeness/redistribution/
poll controls, the MarketData.app reviewed account-plan/credit pair and
operation-specific option-chain symbol bound, and the operation-level
Tiingo/FMP byte-bound maps. A direct adapter read can therefore be green while
its provider remains non-routable:
missing, invalid, partial, or non-positive safety controls are reported
explicitly and never guessed.
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
When `RUN_LIVE_PROVIDER_TESTS=1`, the live pytest session first opens the
configured ledger for a zero-byte append and exits with code `2` before any
provider test runs if that path is not writable. This prevents a filesystem
permission failure at teardown from spending provider quota without a receipt.
The same startup check requires a bounded, printable
`PROVIDER_LIVE_USAGE_SCOPE`; direct pytest invocations cannot silently create
new unattributed `unspecified` receipts.
The ledger is opened and permission-hardened to owner-only mode (`0600`) during
that preflight, and each flushed batch is `fsync`'d before the lock is released.
This protects cross-session usage evidence against a permissive pre-existing
file mode and ordinary process/host crashes; it remains observational evidence,
not a provider-account reservation.
Set the non-secret `PROVIDER_LIVE_USAGE_SCOPE` label separately for each local
environment, GitHub environment, and deployment account. The scope is written
into each receipt and is part of merger deduplication, so identical run IDs
from different environments cannot be silently collapsed. Legacy receipts with
an omitted scope are normalized to `unspecified`; the live runner now fails its
preflight when a scope is absent so new quota-consuming runs cannot create
unattributed usage. Receipts also retain only provider-native capacity headers
observed by the transport (remaining credits, reset times, `Retry-After`, FINRA
record bounds, or Binance/Bybit weight state); auth and payload headers are
rejected. This snapshot is observational evidence, never a substitute for
provider-account reconciliation or runtime quota reservations.
Each provider row distinguishes `exit_status` (whether an operation for that
provider failed), `failed_operations`, and `process_exit_status` (the overall
pytest/matrix result). This prevents an unrelated expected credential or quota
failure from falsely marking every successful provider row as failed. Older
receipts without the new fields remain readable with zero failed operations and
the legacy `exit_status` used as the process status.
When an operator mounts that redacted ledger into a backend deployment and sets
the same `PROVIDER_LIVE_USAGE_LEDGER` path, the authenticated
`/api/v1/providers/usage` response exposes a separate `live_test_usage` object
per provider plus ledger status/row counts. It never merges direct-test usage
into runtime quota reservations, exposes the ledger path, or makes routing
depend on the file; an absent or unreadable ledger is reported as unavailable.
The per-provider live object includes all-time totals plus rolling 24-hour,
7-day, and 30-day request/operation/byte totals. The 30-day view is useful for
rolling bandwidth pools (for example FMP); calendar-reset allowances still
require provider-native reset evidence or operator reconciliation and are not
inferred from these rolling counters.
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
`ALPACA_CORPORATE_ACTIONS_MAX_PAGES`, `FINRA_ASYNC_MAX_RESULT_BYTES`, `FINRA_OTC_OPERATION_COSTS`,
`FINRA_OTC_TERMS_REVIEWED`, `FINRA_OTC_COMPLETENESS_REVIEWED`,
`FINRA_OTC_REDISTRIBUTION_REVIEWED`, `FINRA_OTC_POLL_INTERVAL_SECONDS`,
`TIINGO_OPERATION_BYTE_BOUNDS`, `FMP_OPERATION_BYTE_BOUNDS`,
`MARKETDATA_APP_REVIEWED_PLAN`, `MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT`,
and `MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS` in the same environment's
configuration variables; the workflow passes them through without inventing
entitlements. Leave the MarketData.app pair blank/zero and the option bound at
zero until the account plan, response-priced exposure, and redistribution
terms have been reviewed. Keep required reviewers enabled. Ordinary
push/PR CI deliberately
receives no provider secrets and makes no external provider calls, so a forked
PR cannot spend quotas or exfiltrate keys.
The workflow labels receipts with a GitHub repository/environment usage scope;
the scope is non-secret and does not grant provider access.

The manual GitHub workflow sets `PROVIDER_LIVE_USAGE_LEDGER` to a runner
temporary path and uploads the aggregate-only JSONL receipt with
`actions/upload-artifact` for 90 days, even when probes fail. The artifact has
no credentials, response payloads, or secret-bearing URLs; it is retained for
operator reconciliation and is not automatically merged into runtime quota
reservations. Downloaded receipts may be merged into an operator-owned ledger
only after checking provider/account scope and avoiding duplicate runs.

Use the checked-in sanitizer/merger for downloaded GitHub receipts:

```sh
backend/.venv/bin/python scripts/merge-provider-live-usage.py \
  --destination ~/.config/charting-platform/provider-live-usage.jsonl \
  ./provider-live-usage-<run-id>/provider-live-usage.jsonl
```

It takes an exclusive lock, writes only the allow-listed aggregate fields,
deduplicates rows by `run_id`, usage scope, and provider (or by a canonical row fingerprint
when no run ID exists), tightens the destination to owner-only mode where the
filesystem permits, and returns exit code `2` if any source rows were rejected.

The workflow/artifact contract is covered by the provider secret-wiring tests;
the focused wiring and usage suite passed `13/13`, and the authoritative gate
after this change passed `1860` tests with `80.38%` coverage and 89 warnings in
`393.90s`. Testcontainer session
`ed0b76f0-f94e-4dfe-b994-d9a24c67250c` was cleaned without host-wide pruning.

The receipt merger is covered by focused live-usage tests and the full backend
gate. It is intentionally an operator reconciliation tool: it does not infer
provider limits, change routing, or treat CI artifact counts as provider-native
cumulative usage.

Provider usage is account- and/or IP-scoped by the vendor, not branch-scoped.
Receipt scopes are operator labels for reconciliation, not provider-native
identity proofs; they must be assigned consistently with the actual account or
IP boundary.
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

On 2026-09-10, the configured FMP key also passed the bounded stable
`earnings-calendar` probe alongside profile/history (`3` upstream requests,
`9,444` response bytes). The adapter returned non-empty normalized earnings
events with inclusive date bounds; the raw EPS/revenue estimate fields remain
preserved in event provenance. This is positive transport/shape evidence for
the configured account, not a promotion of FMP routing: the rolling 30-day
bandwidth pool still requires a complete operator-reviewed
`FMP_OPERATION_BYTE_BOUNDS` map, and analyst-estimate/price-target endpoints
remain outside this adapter until their plan entitlements are separately
validated.

The same day, the configured Massive key passed the bounded reference, IPO
calendar, and market-holiday live case. Search, one `reference/ipos` page, and
one `marketstatus/upcoming` response all produced valid transport/schema
evidence; the normalized results preserved IPO status/date and holiday
exchange/status/open/close fields and applied the requested windows. The
assertion intentionally allows a valid empty calendar window, so this proves
the integration contract without fabricating an IPO or holiday row; non-empty
rows are useful additional evidence but are not required for transport
correctness.

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

The latest backend deterministic gate on the current corrective revision is:

- authoritative combined unit + PostgreSQL/Redis Docker-backed coverage gate:
  `1855 passed`, `80.37%` line coverage, 89 warnings, above the repository
  `75%` threshold; the isolated testcontainer resources were cleaned after
  the run
- dedicated tokenized corporate-action capability, availability, registry,
  and service suite: `47 passed`
- migration compatibility and the broader focused provider/quota/runtime
  suites are included in the authoritative combined gate

429/418/quota responses now create durable `provider_capacity_event` records
with provider scope, status, filtered reset headers, retry time, and the
originating request-log link. The backend-only
`/api/v1/market-data/capacity-events` endpoint exposes this evidence to
administrators.

Provider error text is centrally redacted before it reaches durable request
logs, health state, capacity events, or live-probe failure output. The redactor
removes configured secret values and credential-bearing URL/header values, and
the persistence regression covers transport URLs that include an API key.

Current local validation (2026-09-12) has passing EDGAR, Alpaca, MarketData.app,
and Dinari Sandbox probes. MarketData.app required its provider-mandated
trailing slash. Dinari initially returned typed HTTP 401 because the
operator-only endpoint was still the live host; after switching to the
documented Sandbox host, the replacement Sandbox pair passed the full bounded
stock metadata, quote/history/news, dividend, and split case. Tradier, Ondo,
and IBKR are intentionally deferred. Every deployment and CI
environment must still provide its own operator contact value.

The complete 37-case manifest rerun at 2026-09-11T17:43:45Z passed 33 cases.
The four honest outcomes were Alpha Vantage's documented 25-requests/day
capacity response for IPO-calendar and exact credential preflights for the
intentionally deferred Tradier, IBKR, and Ondo providers. Aggregate request and
response-byte telemetry was written outside Git; no credential or payload was
persisted.

Provider refreshes now create/reuse a deterministic `MarketSeries` and attach
its ID to canonical bars and provider observations. OHLCV conflict identity is
series/session-aware through `scope_key`, with `legacy:<session>` retained for
older rows; migration `9f0a1b2c3d4e` backfills the key. Focused
series/migration coverage passed `19/19` and the complete backend unit suite
passed `1,799/1,799`; this is persistence/schema evidence, not additional
provider transport evidence, and PostgreSQL migration validation remains
Docker-gated.

The shared optional REST parser and Alpha Vantage raw-history adapter now add
the provider name to each bar's provenance envelope. This metadata-only change
was covered by focused provider tests (`272/272`) and the complete backend unit
suite (`1,797/1,797`); no additional external calls were needed because the
transport contracts were unchanged.

The 2026-09-12 focused core refresh passed 4/4 checks: EDGAR profile and complete
directory pagination, Alpaca paper-account history, and MarketData.app daily
candles. A separate Dinari Sandbox refresh passed 1/1, covering its metadata,
quote/history, news, dividend, and split case. Both refreshes used the
operator-owned environment and retained only aggregate transport telemetry
outside Git.

The same credentialed refresh also passed the bounded Alpaca latest-price probe
and the MarketData.app options surface probe (expirations, a current chain, and
historical single-contract quotes), 2/2 focused cases. The options adapter
validates the provider's parallel-array response shape and preserves contract
fields/Greeks and quote-history observations. MarketData.app documents
response-dependent credit charging for chain/quote reads, so the implementation
deliberately leaves those operations outside routing until a reviewed maximum
reservation bound is supplied; a green transport probe is not quota admission.

After adding the explicit paper/live Alpaca trading-host setting and replacing
the deprecated corporate-actions route, the focused credentialed suite passed
3/3: Alpaca paper assets plus v1 corporate actions, SEC EDGAR filing events
plus Company Facts, and the Dinari Sandbox metadata/quote/history/news/
dividend/split case. The run used only the operator-owned key store and wrote
aggregate request/byte telemetry outside Git.

The subsequent complete matrix rerun at 2026-09-12 collected 39 cases and passed
35 with positive transport observations. The four honest outcomes were
Alpha Vantage's documented 25-requests/day capacity response for IPO-calendar
and exact credential preflights for intentionally deferred Tradier, IBKR, and
Ondo. The xStocks quote endpoint returned an explicit null quote while the
selected token reported `currentPeriod=closed`; the live test records that
provider state and does not fabricate a price. The wrapper made no acceptance
claim because the deferred credential and provider-governance gates remain open.

The superseding complete matrix after the Alpaca endpoint correction collected
41 cases and passed 37/41. The four honest outcomes were the configured Alpha
Vantage key's documented 25-requests/day capacity response and exact missing
credential preflights for intentionally deferred Tradier, IBKR, and Ondo. The
new Alpaca assets/corporate-actions and SEC/Dinari surface cases passed; no
credentials or response payloads were persisted.

A provider may
have a green live probe and remain non-routable when any external constraint
cannot yet be accounted safely. Every registered synchronous adapter now reports
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
The usage summary derives `window_ends_at` from each policy's explicit calendar
reset (including Eastern-time month/day and 09:30 ET boundaries), rather than
adding a nominal 31-day duration. Fixed and rolling windows retain their
duration semantics, so active-window diagnostics expire at the same boundary
used by admission across short months and daylight-saving transitions.
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
scope is fixed. Nasdaq Trader's polling allowance remains unpublished. IBKR
now has a concrete read-only Client Portal Gateway adapter for security search,
raw historical bars, and latest-price snapshots. The gateway login remains
interactive and session-bound; no options/futures capability is claimed, and
raw bars are never labeled as adjusted. Live evidence still requires an
operator-owned `IBKR_READ_ONLY_URL` and `IBKR_READ_ONLY_SESSION_COOKIE`.

The public and credentialed tokenized matrix is maintained separately in
`tests/live/test_tokenized_providers_live.py`. It covers xStocks, Robinhood
Chain Stock Tokens, Bybit xStocks, Gate TradFi stock endpoints, Kraken's
current xStocks catalogue, Dinari dShares, and Ondo Global Markets. Public
cases can run keylessly; Dinari and Ondo require their exact credentials and
fail explicitly during preflight when absent. The latest bounded public run at
`2026-09-10T02:50:33Z` passed all seven public probes,
including xStocks and Robinhood corporate-action reads, and
the quote assertions observed at least two upstream requests for every
successful quote operation (metadata resolution plus quote/order-book read).
The Kraken result was an empty provider catalogue (no current xStocks pair),
and Robinhood returned one transient `local_rate_limited` response before the
test's single provider-specific retry succeeded; neither result is treated as
permission to guess a ticker or a quota.

Tokenized transport failures are typed at the shared adapter boundary: network
errors become redacted `ProviderResponseError` instances, HTTP 418/429
responses become `ProviderRateLimitError` instances with only an allow-listed
set of provider rate headers and parsed `Retry-After` metadata, and other HTTP
or JSON failures remain redacted response errors. The bounded Robinhood retry
handles only that typed 429 and remains finite. Unit regression coverage and
the seven-case live suite both pass after this change; no raw request URL,
credential, or arbitrary response header is persisted.

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

The current operator environment has Alpaca and MarketData.app credentials and
an EDGAR contact, and their bounded probes pass. The intentionally deferred
credential domains are `TRADIER_API_KEY`, `IBKR_READ_ONLY_URL` plus
`IBKR_READ_ONLY_SESSION_COOKIE`, and `ONDO_GLOBAL_MARKETS_API_KEY`; their live
cases remain explicit preflight outcomes rather than skips. Every deployment,
CI environment, and isolated worktree still needs its own approved secret
distribution and EDGAR contact configuration.

Marketstack history and discovery are intentionally separate gates: a key is
enough for the bounded EOD history probe, while venue discovery also requires
the non-secret `MARKETSTACK_DISCOVERY_EXCHANGE` MIC/exchange setting. The
adapter no longer defaults discovery to `XNYS`, so a single-venue read cannot
be mistaken for complete US listing coverage.

The latest network-enabled rerun at `2026-09-10T03:16:52Z`, using the existing
external keys plus a temporary non-secret SEC User-Agent and explicit
`MARKETSTACK_DISCOVERY_EXCHANGE=XNAS`, collected 34 cases: 31 passed with
positive transport observations across the available keyless and credentialed
adapters, including all seven tokenized probes across five tokenized providers,
OpenFIGI after its prior cooldown, and the header-only Alpha Vantage IPO-calendar
response. Three failed
exact credential preflight for `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`,
`TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`. The wrapper returned exit code
2 and made no acceptance claim. The newly implemented Tradier expiration and
current-chain live reads remained unexecuted because `TRADIER_API_KEY` is still
absent; this is an explicit credential failure, not a live skip. FRED now reports its three explicit missing
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
A credentialed live read passed on 2026-09-11, but the provider remains subject
to the documented quota/terms review before routing admission.

After the FMP live-preflight correction, the complete manifest was rerun at
`2026-09-10T03:36Z` with the existing operator-owned keys plus temporary
non-secret `EDGAR_USER_AGENT` and `MARKETSTACK_DISCOVERY_EXCHANGE=XNAS`
overrides. It again collected 34 cases: 31 passed with positive transport
observations, while only the exact Alpaca, Tradier, and MarketData.app
credential domains failed preflight. The wrapper returned exit code `2` and
made no acceptance claim. The live runner now regression-checks its Tiingo/FMP
byte-bound operation set against the runtime quota policy, including FMP's
`fetch_market_events`; the Docker-backed combined gate passed `1858/1858` with
`80.36%` coverage. No provider-specific safety gate was relaxed.

The continuation rerun at `2026-09-10T03:59Z` used the same existing keys and
temporary non-secret overrides. It reproduced the exact result: all 34 cases
were collected, 31 passed, and the three failures were explicit credential
preflight for `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and
`MARKETDATA_APP_API_KEY`. The pytest summary was `3 failed, 31 passed in
36.12s`; the wrapper returned exit code `2`, appended only redacted external
usage telemetry, and made no acceptance claim. The provider-specific routing
safety controls remain fail-closed.

The authoritative backend gate was rerun in a session-aware invocation at
`2026-09-10T04:17Z`. It passed `1858` tests with `89` warnings and `80.36%`
line coverage in `384.90s`, above the 75% threshold. Testcontainer session
`abb23a71-625c-402e-baa2-3efccac456ec` was cleaned successfully without a
host-wide prune. This validates the current code unchanged; it does not relax
the live credential or provider-governance gates.

After adding the optional read-only live-ledger summary to the backend usage
endpoint, the authoritative gate was rerun at `2026-09-10T04:33Z`. It passed
`1860` tests with `89` warnings and `80.37%` line coverage in `544.22s`, above
the 75% threshold. Testcontainer session
`247cc1c4-05aa-4571-adac-9709ad237562` was cleaned without host-wide pruning.

The authenticated `/api/v1/providers/usage` test now writes a temporary
redacted ledger row and asserts that the endpoint exposes the separate
`live_usage_ledger` status and `live_test_usage` counters. The focused
service/router/secret-wiring suite remained green, and the authoritative
session-aware gate was rerun at `2026-09-10T04:53Z`: `1860 passed`, `89`
warnings, `80.37%` line coverage in `399.55s`, above the 75% threshold.
Testcontainer session `0e80e4ff-024f-4ca1-b8ab-f5c876922c95` was cleaned
without host-wide pruning. This remains observability only: direct live-test
usage is not merged into runtime quota reservations and cannot change routing.

The continuation complete matrix was rerun at `2026-09-10T04:57Z` with the
existing operator environment. It collected 34 cases: `31 passed` in
`38.13s`, while exactly three cases failed credential preflight for
`ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and
`MARKETDATA_APP_API_KEY`. The wrapper returned exit code `2` and made no
acceptance claim. FINRA async/OTC, FRED, Nasdaq, xStocks, Bybit, and
Tiingo/FMP controls remain explicitly fail-closed; only redacted telemetry was
written to the external usage ledger.

The usage-summary regression now proves that a temporary live-ledger row is
visible as separate `live_test_usage` while runtime request totals and durable
quota-window availability remain unchanged. Focused usage/router/live-ledger
tests passed `13/13`; the authoritative gate completed at
`2026-09-10T05:13Z` with `1860 passed`, `89` warnings, and `80.38%` line
coverage in `388.17s`. Testcontainer session
`1cf565df-7b9d-468f-acf8-bcb1349dc51b` was cleaned without host-wide pruning.

The live-ledger reader and receipt merger now reject booleans, fractional JSON
numbers, negative values, and other non-integral usage fields instead of
coercing them with `int()`. Digit strings remain accepted for redacted receipt
compatibility. The strict parser regression suite passed `7/7`; the
authoritative gate completed at `2026-09-10T05:48Z` with `1862 passed`, `89`
warnings, and `80.38%` line coverage in `394.96s`. Testcontainer session
`8ed2d4ef-04a8-47d2-8129-b228e18885a6` was cleaned without host-wide pruning.

Transport failures are also typed for the first-party Alpaca, FRED, and SEC
EDGAR adapters. Network errors no longer become empty history, empty event
lists, or a synthetic SEC profile; legitimate unsupported symbols and valid
empty provider responses remain unchanged. The focused provider suite passed
`106/106`; the authoritative gate completed at `2026-09-10T06:02Z` with
`1865 passed`, `89` warnings, and `80.39%` line coverage in `365.39s`.
Testcontainer session `9aad314f-c0a9-4fd9-b902-83afd574e391` was cleaned
without host-wide pruning.

The optional candle adapters now validate provider-specific parallel-array
contracts: Finnhub and MarketData.app reject missing/unknown status, non-array
fields, and mismatched array lengths instead of truncating with `zip()` or
returning an empty series. The focused optional-provider suite passed `30/30`;
the authoritative gate completed at `2026-09-10T07:38Z` with `1890 passed`,
`89` warnings, and `80.36%` line coverage in `395.31s`. Testcontainer session
`3b3c3a4b-042f-4161-b40c-5df689a8ee6d` was cleaned without host-wide pruning.

The same adapters now validate response shape and malformed JSON explicitly:
Alpaca bars/latest, corporate-actions, and assets responses, SEC EDGAR
submissions/facts/directories, and FRED observations all reject invalid
payloads with typed provider-response failures. The focused provider suite
passed `109/109`; the authoritative gate completed at `2026-09-10T06:14Z`
with `1868 passed`, `89` warnings, and `80.35%` line coverage in `544.34s`.
Testcontainer session `5050159c-29bd-4cba-8846-54785ab4b75a` was cleaned
without host-wide pruning.

Coinbase, Kraken, and OpenFIGI now also preserve typed failure semantics:
network errors and malformed JSON are provider-response failures, and invalid
exchange payload shapes are not normalized into empty market data or identity
results. The focused crypto/OpenFIGI/provider-transport suite passed `116/116`;
the authoritative gate completed at `2026-09-10T06:25Z` with `1872 passed`,
`89` warnings, and `80.35%` line coverage in `407.49s`. Testcontainer session
`02888682-f032-4f0a-8669-efc552fa9fd2` was cleaned without host-wide pruning.

Alpha Vantage and CoinGecko shared HTTP helpers now convert transport and
malformed-JSON failures into typed provider-response errors, including
CoinGecko's ranked symbol-resolution request. The focused provider/transport
suite passed `115/115`; the authoritative gate completed at
`2026-09-10T06:35Z` with `1876 passed`, `89` warnings, and `80.36%` line
coverage in `389.90s`. Testcontainer session
`795d0dc3-df37-451b-af3c-62eb6ad3d0ce` was cleaned without host-wide pruning.

Binance, Nasdaq Trader, FINRA Query API, and the FINRA OTC directory now also
fail closed on transport errors, malformed JSON, invalid response shapes, and
incomplete directory payloads. Binance rejects malformed candle rows instead
of silently dropping them; Nasdaq accepts the official `ACT Symbol` header and
approved `Symbol` mirror variation while retaining identity-header validation;
FINRA OAuth, short-interest, Daily List, async status, and OTC DAPI paths all
preserve typed redacted provider failures. The focused provider/directory/
instrumentation suite passed `138/138`; the corrected authoritative gate
completed at `2026-09-10T06:59Z` with `1885 passed`, `89` warnings, and
`80.37%` line coverage in `369.50s`. Testcontainer session
`43c93bbd-d914-4259-ad39-21197ad67ed7` was cleaned without host-wide pruning.

The post-change complete manifest matrix reran at `2026-09-10T07:03:12Z` and
again collected 34 cases: `31 passed` in `40.75s`, with exactly the three
credential preflight failures for `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`,
`TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`. Binance, Nasdaq, FINRA, and
the seven tokenized probes therefore have current end-to-end evidence under
the existing environment. The wrapper returned exit code `2` and made no
acceptance claim; FINRA async/OTC, FRED, Nasdaq polling, xStocks, Bybit, and
Tiingo/FMP controls remained fail-closed.

FINRA's bounded asynchronous presigned-result download now also converts
stream setup and iteration transport failures into typed redacted provider
errors; the positive byte-bound and credential-free signed-download behavior
is unchanged. The focused FINRA suite passed `9/9`; the authoritative gate
completed at `2026-09-10T07:15Z` with `1886 passed`, `89` warnings, and
`80.36%` line coverage in `416.19s`. Testcontainer session
`0f4c9b7f-f9a2-43e6-a9a6-9a1cfa2fb7bd` was cleaned without host-wide pruning.

The shared optional-provider REST layer now converts malformed JSON from
Twelve Data, Finnhub, FMP, Tiingo, EODHD, Marketstack, Tradier, and
MarketData.app into typed redacted failures instead of leaking parser errors or
allowing false empty-data results. The focused optional-provider suite passed
`27/27`; the authoritative gate completed at `2026-09-10T07:27Z` with
`1887 passed`, `89` warnings, and `80.36%` line coverage in `522.57s`.
Testcontainer session `a9124505-09fa-42a8-825b-60047d50b4af` was cleaned
without host-wide pruning.

Tradier nested history and quote wrappers now reject scalar or malformed row
containers while preserving valid empty wrappers. Marketstack EOD pagination
now rejects missing, malformed, non-progressing, or contradictory metadata
instead of truncating history. The focused optional-provider suite passed
`32/32`; the authoritative gate completed at `2026-09-10T07:51Z` with
`1892 passed`, `89` warnings, and `80.36%` line coverage in `404.68s`.
Testcontainer session `294f910c-3bf6-4c72-8cf3-7d5c66d132da` was cleaned
without host-wide pruning.

All concrete optional-provider documented row-list endpoints now fail closed on
missing, scalar, or mixed row containers instead of normalizing malformed
responses to empty data; Tradier option-expiration parsing also rejects
malformed dates and wrapper shapes. The focused optional-provider suite passed
`35/35`; the authoritative gate completed at `2026-09-10T08:07Z` with
`1895 passed`, `89` warnings, and `80.36%` line coverage in `390.66s`.
Testcontainer session `3a0e72c2-6f1c-444d-9bc0-71059e0b4ed6` was cleaned
without host-wide pruning.

Tokenized xStocks, Robinhood, Bybit, Gate, and Kraken list, quote, instrument,
and corporate-action paths now reject missing, scalar, or mixed response
containers instead of filtering malformed rows or creating synthetic records.
The focused tokenized suite passed `23/23`; the authoritative gate completed at
`2026-09-10T08:19Z` with `1900 passed`, `89` warnings, and `80.35%` line
coverage in `403.85s`. Testcontainer session
`8190d6b2-84ee-48fa-a119-cd53f0e10fda` was cleaned without host-wide pruning.

Coinbase and Kraken crypto candle, ticker, and directory adapters now reject
malformed row containers and non-numeric fields instead of skipping
observations or returning empty/synthetic results. Focused new-provider tests
passed `121/121`; the authoritative gate completed at `2026-09-10T08:32Z`
with `1904 passed`, `89` warnings, and `80.35%` line coverage in `444.39s`.
Testcontainer session `291324c7-d107-4007-97ad-496ee703ce08` was cleaned
without host-wide pruning.

OpenFIGI mapping now rejects malformed outer envelopes, missing or mixed
mapping rows, response-count mismatches, and non-2xx/429 transport failures
with typed provider errors. Focused OpenFIGI tests passed `8/8`; the
authoritative gate completed at `2026-09-10T08:42Z` with `1907 passed`,
`89` warnings, and `80.35%` line coverage in `410.96s`. Testcontainer session
`fddece92-aebf-488b-a824-68f4068db334` was cleaned without host-wide pruning.

Alpaca OHLCV and latest-price paths now reject malformed or mixed bar rows,
missing required OHLC fields, non-finite numeric values, and invalid pagination
tokens instead of skipping observations or leaking generic exceptions. The
focused Alpaca suite passed `30/30`; Ruff and diff checks passed. A follow-up
authoritative gate was attempted at `2026-09-10T08:53:03Z`, but Docker Desktop
returned HTTP 500 from its local API during the preflight before tests started;
therefore this change has no new full-gate acceptance claim until the isolated
Docker validation can run.

FINRA short-interest and OTC Daily List adapters now reject mixed or scalar
rows, invalid short-interest settlement dates, and malformed or non-finite
numeric fields instead of silently dropping records or creating partial
observations. The focused FINRA suite passed `13/13`; Ruff and diff checks
passed. The authoritative gate remains unverified because Docker preflight is
currently unavailable.

SEC EDGAR ticker and exchange directories, filing arrays, and Company Facts
nested observations now reject malformed rows, table-width mismatches,
misaligned arrays, and invalid nested containers instead of truncating or
filtering provider data. The focused EDGAR suite passed `21/21`; Ruff and diff
checks passed. The authoritative gate remains unverified because Docker
preflight is currently unavailable.

Massive ticker search/discovery, IPO-calendar, and market-holiday adapters now
reject invalid result containers, mixed or scalar rows, missing identities or
dates, and invalid pagination metadata instead of silently filtering or
returning partial reference evidence. The focused Massive suite passed `13/13`;
Ruff and diff checks passed. The authoritative gate remains unverified because
Docker preflight is currently unavailable.

Nasdaq Trader directory parsing now rejects inconsistent CSV row widths, missing
symbol/name values, and malformed official or approved mirror rows while
preserving intentional test-issue exclusion and ACT Symbol/Symbol compatibility.
The focused Nasdaq suite passed `11/11`; Ruff and diff checks passed. The
authoritative gate remains unverified because Docker preflight is currently
unavailable.

CoinGecko HTTP, search, ranked symbol resolution, profile, and market-discovery
paths now reject invalid containers, malformed or mixed rows, incomplete
identities, malformed nested metadata, and non-rate-limit HTTP failures while
preserving typed capacity errors. The focused CoinGecko suite passed `17/17`;
Ruff and diff checks passed. The authoritative gate remains unverified because
Docker preflight is currently unavailable.

Binance OHLCV, ticker, and exchange-info paths now reject malformed row
containers, short or non-finite numeric rows, non-increasing pagination,
malformed symbol metadata, and non-rate-limit HTTP failures. Binance 429/418
responses are typed capacity errors retaining provider headers. The focused
Binance suite passed `26/26`; Ruff and diff checks passed. The authoritative
gate recorded at `2026-09-10T09:45Z` passed `1959/1959`, with `89` warnings
and `80.45%` coverage, using isolated PostgreSQL/Redis testcontainer session
`160eaf86-b011-484f-b3cc-a5259f212c26`, cleaned without host-wide pruning.

The bounded keyless Binance live probe then passed `1/1` in `1.46s` against
the public `/klines` endpoint and recorded positive transport telemetry. This
is additive live evidence only; the authoritative Docker-backed gate is now
also recorded above.

Alpha Vantage JSON and CSV adapters now reject invalid containers, malformed
search/history rows, incomplete listing or IPO rows, invalid dates/numbers, and
non-rate-limit HTTP failures while preserving documented rate-limit/error
handling. The focused Alpha Vantage suite passed `16/16`; Ruff and diff checks
passed. The authoritative gate remains unverified because Docker preflight is
currently unavailable.

FRED history and latest-price paths now preserve typed non-rate-limit HTTP
failures and reject invalid observation containers, mixed rows, invalid dates,
and non-finite values while retaining the documented `.` missing-data marker.
The focused FRED suite passed `31/31`; Ruff and diff checks passed. The
authoritative gate remains unverified because Docker preflight is currently
unavailable.

## Latest live and full-gate evidence

The complete manifest matrix was rerun at `2026-09-10T09:58:46Z` with the
existing operator-owned environment file, a temporary non-secret
`EDGAR_USER_AGENT`, and `MARKETSTACK_DISCOVERY_EXCHANGE=XNAS`. It collected 34
cases: `29 passed` and `5 failed` in `36.15s`. The five failures are explicit
credential/capacity blockers, not live skips: missing
`ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, missing `TRADIER_API_KEY`, missing
`MARKETDATA_APP_API_KEY`, and Alpha Vantage's documented 25-requests/day
capacity response for both daily history and IPO-calendar reads. The direct
pytest matrix returned exit code `1`, so this is not an acceptance claim.

Alpha Vantage's observed CSV `Information` response is now classified as a
typed `ProviderRateLimitError` before CSV row parsing; it is never interpreted
as an IPO event or malformed date. The Gate public TradFi order-book probe
passed `1/1` after the adapter accepted the documented `null` empty-book shape,
validated object rows and finite decimal prices, and rejected scalar/malformed
rows. All seven tokenized probes remained green.

The tokenized live suite now also contains credentialed Dinari and Ondo
probes. Dinari's case exercises provider UUID discovery, fair price, bid/ask
quote, DAY aggregate history, and bounded news; Ondo's case exercises metadata,
latest indicative price, and a bounded primary-market OHLC read. Both cases
require their exact environment variables (`DINARI_API_KEY_ID` plus
`DINARI_API_SECRET_KEY`, or `ONDO_GLOBAL_MARKETS_API_KEY`) and fail explicitly
when absent; they are never skipped as evidence. Their adapters also have
fixture coverage for malformed identity, timestamp, numeric, and OHLC shapes.

The latest authoritative `make test-backend-coverage` gate passed
`1963/1963`, with `89` warnings and `80.48%` coverage in `458.04s`, using
isolated PostgreSQL/Redis testcontainer session
`e6ae1ca0-d42b-473d-a83a-90751305ae08`. The testcontainer was cleaned without
host-wide pruning. No credentials or provider payloads were persisted, and no
frontend or ETF-constituent files were changed.

The Alpha Vantage quota handling was then tightened without changing its
routing entitlement: explicit daily-capacity messages, including the observed
CSV `Information` shape, now carry a provider-specific rolling 24-hour retry
timestamp. Other informational responses do not receive an invented delay.
Focused Alpha Vantage coverage passed `18/18`; the authoritative gate passed
`1964/1964`, with `89` warnings and `80.49%` coverage in `421.20s`, using
isolated PostgreSQL/Redis testcontainer session
`26146598-40dc-4c1a-b5cc-100ad6ed6d3b`, cleaned without host-wide pruning.

The follow-up Alpha Vantage refinement also preserves response headers on
body-level capacity errors, allowing the runtime to retain any allow-listed
provider-native remaining/reset evidence. Focused coverage remained `18/18`;
the follow-up authoritative gate passed `1964/1964`, with `89` warnings and
`80.49%` coverage in `396.81s`, using isolated PostgreSQL/Redis testcontainer
session `343bdfb7-6f4d-41e8-99a0-d1a9802f5db2`, cleaned without host-wide
pruning.

The shared provider error-envelope path now retains provider-declared reset
headers and retry timestamps for JSON quota/error envelopes across all
registered adapters. Only allow-listed capacity headers are retained, and
lightweight/malformed response-header objects fail safely without hiding the
typed provider error. The focused provider/error suite passed `247/247`; Ruff,
compilation, and diff checks passed. The authoritative backend gate then
passed `1966/1966`, with `89` warnings and `80.50%` coverage in `406.22s`,
using isolated PostgreSQL/Redis testcontainer session
`8219560c-3015-42a7-9b59-eeae4342330a`, cleaned without host-wide pruning.

The post-change complete live matrix at `2026-09-10T11:15Z` collected 34
cases: `27 passed` in `38.20s`. Seven failures were explicit preflight or
provider-capacity outcomes: missing `EDGAR_USER_AGENT`,
`ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and
`MARKETDATA_APP_API_KEY`, plus Alpha Vantage's documented 25-requests/day
capacity response for daily history and IPO-calendar reads. The wrapper made
no acceptance claim; all seven tokenized probes remained green and aggregate
usage was recorded outside Git without credentials or payloads.

After the final safe response-header extraction fix, the focused provider,
runtime, and error suite passed `327/327` in `5.85s`, with Ruff and diff checks
clean. The final authoritative `make test-backend-coverage` gate passed
`1966/1966`, with `89` warnings and `80.52%` coverage in `412.11s`, using
isolated PostgreSQL/Redis testcontainer session
`bc90810e-baba-4963-84c1-ef58081f42ce`, cleaned without host-wide pruning.
This does not change the live-matrix blockers or constitute provider acceptance.

The next complete matrix rerun at `2026-09-10T11:24Z` supplied a temporary
descriptive SEC User-Agent and the reviewed `XNAS` Marketstack discovery scope.
It collected 34 cases and passed `29/34`; the five failures were explicit
missing `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and
`MARKETDATA_APP_API_KEY` credential preflights plus typed Alpha Vantage
25-requests/day capacity responses for daily history and IPO-calendar reads.
All tokenized probes remained green. A separate Finnhub credentialed profile,
historical-earnings, and forward-calendar isolation passed `1/1` with the
operator-owned env. The temporary SEC value is not a deployment configuration;
each trusted environment must supply its own non-secret contact value.

The live credential preflight now rejects the checked-in placeholder SEC contact
value before any external call, and the live-test helper applies the same rule.
Focused secret-wiring coverage passed `10/10` with Ruff and diff checks clean.
The follow-up authoritative `make test-backend-coverage` gate passed
`1967/1967`, with `89` warnings and `80.52%` coverage in `437.64s`, using
isolated PostgreSQL/Redis testcontainer session
`aca39e7f-8836-4d71-b130-9d92033cafee`, cleaned without host-wide pruning.

The SEC contact validation is now shared and rejects empty values,
`contact@example.com`, `your.email@example.com`, and any `example.com`
placeholder in the EDGAR adapter, registry, live preflight, and live-test
helper. Focused SEC/secret-wiring coverage passed `32/32`; Ruff and diff checks
were clean. The authoritative `make test-backend-coverage` gate passed
`1968/1968`, with `89` warnings and `80.51%` coverage in `421.39s`, using
isolated PostgreSQL/Redis testcontainer session
`59baf5db-b0e7-42fe-8ef9-221e13084cec`, cleaned without host-wide pruning.
This hardens preflight only; each trusted environment still needs its own
non-placeholder SEC User-Agent.

The checked-in root/backend environment examples now leave `EDGAR_USER_AGENT`
blank and explicitly state that the setting is fail-closed until an operator
supplies a real contact. The provider guide uses an angle-bracket documentation
example and explains that it is rejected. Shared validation also rejects
`myemail@` and angle-bracket placeholders. Focused SEC/secret-wiring coverage
remained `32/32`; the authoritative gate passed `1968/1968`, with `89`
warnings and `80.52%` coverage in `412.46s`, using isolated PostgreSQL/Redis
testcontainer session `4ac59081-aebf-41f3-b579-a0784fcaf418`, cleaned without
host-wide pruning.

The backend shadow-report contract now aggregates core-session D1 coverage and
returns `pass`, `fail`, or `insufficient_evidence` against the explicit 99%
threshold, alongside quota-capacity event totals and open-anomaly severity
counts. Focused monitoring tests passed `5/5`; the authoritative
`make test-backend-coverage` gate passed `1969/1969`, with `89` warnings and
`80.53%` coverage in `388.46s`, using isolated PostgreSQL/Redis testcontainer
session `2f99f994-7fc5-4944-b43c-6b3308512d79`, cleaned without host-wide
pruning. This remains observational and does not enable routing.

Direct live receipts now include the non-secret `PROVIDER_LIVE_USAGE_SCOPE`
label. Scope is surfaced in per-provider `/api/v1/providers/usage` aggregates,
passed through local/GitHub/Compose wiring, and included in merger
deduplication; a same-named run/provider from another scope is retained rather
than collapsed. Legacy receipts without the field are normalized to
`unspecified`. Focused ledger/usage/router/wiring tests passed `26/26`; the
authoritative backend gate passed `1970/1970`, with `89` warnings and `80.53%`
coverage in `501.31s`, using isolated PostgreSQL/Redis testcontainer session
`ce2882bf-eb46-4cc4-82b7-947dc03324b6`, cleaned without host-wide pruning.

The Dinari/Ondo implementation follow-up added two credentialed tokenized live
cases to the manifest. A post-change attempt at `2026-09-10T14:29Z` collected
37 tests; the exact Dinari and Ondo credential preflights failed because
`DINARI_API_KEY_ID`/`DINARI_API_SECRET_KEY` and
`ONDO_GLOBAL_MARKETS_API_KEY` are not present in this environment, so neither
provider made an upstream call. The run recorded 23 available-provider
aggregate telemetry rows (57 requests and 11,625,293 response bytes) only in
an operator-owned ledger outside Git. The existing Alpaca, Tradier,
MarketData.app, and IBKR credential gates and Alpha Vantage daily-capacity
responses remain open; no live acceptance claim is made.

Focused Dinari/Ondo and surrounding registry/quota/secret coverage passed
`122/122`, Ruff and diff checks passed, and the authoritative Docker-backed
combined gate passed `1994/1994` with `89` warnings and `80.50%` coverage in
`521.76s` (isolated PostgreSQL/Redis session
`3f19adca-0e0a-4f86-97b3-04e03a7c45d3`, cleaned without host-wide pruning).

The fresh complete matrix at `2026-09-12T09:36:37Z` collected all 41 cases and
passed `37/41` using the existing configured keys. Alpha Vantage returned its
documented 25-requests/day capacity response; Tradier, IBKR, and Ondo failed
only their exact intentionally deferred credential preflights. The owner
ledger recorded 26 aggregate provider rows (`64` operations, `86` HTTP
requests, `22,749,358` response bytes) under a unique run identity. The
wrapper returned exit code `2` and made no acceptance claim; no credentials or
payloads entered Git.

The live pytest session now checks both ledger writability and the non-secret
`PROVIDER_LIVE_USAGE_SCOPE` before invoking any provider. An unwritable ledger
or missing/invalid scope exits with code `2` before collection/provider calls,
so direct invocations cannot spend quota without a durable, attributable
receipt.

After the prior Alpha Vantage capacity response, the newly added bounded
credentialed earnings case was rerun at 2026-09-12T09:58Z under run
`alpha-earnings-20260912` and passed `1/1`. The `EARNINGS` response produced
annual/quarterly rows that passed strict fiscal/reported-date and EPS/surprise
normalization; the aggregate usage receipt remains outside Git. This is
endpoint-specific evidence and does not change the existing 25-requests/day
quota or the still-open full-matrix/terms gates.

The follow-up complete matrix at 2026-09-12T10:00Z collected 42 cases and
passed `37/42`. The two Alpha Vantage non-passes were provider-native
25-requests/day capacity responses for IPO-calendar and earnings after the
shared key was exercised; the other three were the exact intentional
credential preflights for Tradier, IBKR, and Ondo. The wrapper returned exit
code `2` and made no acceptance claim. This confirms the provider-specific
quota guard under fan-out; it does not invalidate the separate successful
standalone Alpha earnings normalization probe.

The Alpha Vantage adapter was then tightened to reject adjusted daily-history
requests before transport: the free `TIME_SERIES_DAILY` response is raw, while
the adjusted daily surface is premium. Raw history is now requested explicitly
for the latest-price helper and carries `raw`/`provider-native` adjustment
provenance. Focused Alpha coverage passed `25/25`, and the complete backend unit
suite passed `1,781/1,781` with the existing 37 warnings; no provider call was
needed for this correctness regression.

The same raw-versus-adjusted contract is now enforced at the adapter boundary,
not only in resolver admission. Optional REST adapters and the Binance,
Coinbase, and Kraken exchange feeds reject adjusted-history calls before any
HTTP request; raw exchange bars carry explicit `raw`/`provider-native`
provenance. Focused provider coverage passed `284/284`, the complete backend
unit suite passed `1,794/1,794` with the known 37 warnings, and the bounded
keyless Binance/Coinbase/Kraken history probes passed `3/3` under run
`51b1b146-7d5b-47ac-86be-5b545bad3b6d`. Aggregate usage remains in the
owner-managed ledger outside Git; this evidence does not promote any separate
quota, terms, or deployment gate.

Canonical OHLCV persistence now retains the market-series identity, trading
session, adjustment basis/version, and provider provenance in both
`ohlcv_bar` and `market_bar_observation`; provider observations gained an
additive `session` column in migration `8e9f0a1b2c3d`. This is a local
serialization/migration correctness change, not new provider transport
evidence. Focused persistence/provider tests passed `212/212`, and the
complete backend unit suite passed `1,797/1,797`; Docker-backed migration and
full-stack validation remains unverified while Docker is unavailable.

The post-change bounded live regression for the provenance-bearing adapters
passed `4/4` (`alpaca_credentialed_history` plus the Binance, Coinbase, and
Kraken keyless history probes) under run
`canonical-persistence-provenance-20260912`. Aggregate usage was written to
the owner-managed ledger outside Git; no credentials or payloads were
persisted.

Compatibility reads now use the durable `market_series_default` mapping. The
first admitted canonical series is stable, regular sessions supersede an
extended-only default, and inactive mappings fall back to an active canonical
series without mixing alternate feeds or legacy rows. Migration
`a0b1c2d3e4f5` plus service/read regressions passed `21/21`; the complete
backend unit suite passed `1,802/1,802`. This is persistence/query evidence,
not additional provider transport evidence; PostgreSQL/full-stack validation
remains Docker-gated.

The follow-up persistence audit also routes cold/latest provider fetches through
the same `MarketSeries` attachment as historical repairs. Focused
market-data/default-mapping coverage passed `21/21`, and the complete backend
unit suite passed `1,804/1,804`; this adds no provider transport evidence and
does not change the external usage ledger.

Bulk historical refreshes and the risk-free-rate history path now apply the
same series attachment before persistence. Focused bulk/risk-free/market-data
coverage passed `27/27`, and the complete backend unit suite passed
`1,805/1,805`; no provider calls were needed for this correction.

Synthetic OHLCV recomputation readback now applies the compatibility selector
as well, so derived chart results cannot leak alternate or legacy rows. The
complete backend unit suite remained green at `1,805/1,805`; this was a local
query-boundary correction with no provider calls.

The compatibility selector now requires matching canonical bars before it
suppresses legacy rows. A pre-created or emptied canonical series therefore
cannot hide readable legacy history. Focused selector coverage passed `22/22`,
and the complete backend unit suite passed `1,806/1,806`; no provider calls
were made.

Provider batches with mixed session/feed/adjustment metadata are now split into
separate deterministic series before persistence. Focused market-data coverage
passed `29/29`, and the complete backend unit suite passed `1,807/1,807`; this
was a local normalization correction with no provider calls.

On 2026-09-12, the newly supplied operator credentials were revalidated in
bounded provider-specific runs after the Dinari transport was updated for its
current cursor-paginated v2 catalogue contract. SEC EDGAR profile, filing/facts,
and complete ticker/exchange-directory cases passed `3/3` (5 operations, 6
requests); Alpaca paper daily/intraday/latest/assets/events passed `4/4` (5
operations, 5 requests); MarketData.app options and five-minute history passed
`2/2` (4 operations, 4 requests); and Dinari Sandbox metadata, fair price,
quote, all four documented history windows, news, dividends, and splits passed
`1/1` (10 operations, 19 requests). Redacted receipts were merged into the
owner-managed cross-session ledger with `accepted=4`, `duplicates=0`, and
`rejected=0`; no credentials or response payloads were persisted. Dinari stock
and split reads now send `limit`/`order` and validate `pagination_metadata.next`,
while explicitly retaining a legacy list-response fallback and requiring
explicit in-order continuation for any advertised next cursor. This is
transport/schema evidence only: Dinari partner
quota, US SIP/NBBO fees, redistribution approval, and MarketData.app reviewed
plan/option bounds remain independent routing gates.

On 2026-09-12, the Dinari adapter's ticker lookup was changed to use the
provider-documented `symbols[]` filter instead of assuming the first catalogue
page contains every symbol. The existing rotated-Sandbox compound live case
passed `1/1` after the change (20 HTTP requests, 11 measured operations), and
two secret-free aggregate receipts were merged into the owner-managed ledger
(`accepted=2`, `duplicates=0`, `rejected=0`). UUID lookups retain the
unfiltered compatibility path; provider quota, commercial terms, and routing
admission remain independent fail-closed gates.

On 2026-09-12, Dinari's direct dividend/split adapters were also exposed through
the generic `tokenized_corporate_actions` capability. The changed rotated-Sandbox
case passed `1/1` with 23 HTTP requests and 12 measured operations, covering the
provider's cursor-backed metadata lookup, fair price/quote/history/news, direct
dividend/split reads, and the symbol-scoped combined action path. Aggregate-only
telemetry was merged into the owner-managed ledger outside Git. Dinari's
unscoped action path remains split-only (there is no documented global dividend
feed), rejects `upcoming`, and supports only explicit same-instance cursor
continuation; partner
quota, US eligibility, fees, display/cache, redistribution, and commercial
routing gates remain fail-closed.

The shared tokenized event linker was then corrected to recognize Dinari's
provider-native `stock_id` identity field. This is local persistence/linkage
evidence only; it used the existing scheduler fixture and did not consume any
additional provider quota or persist live payloads.

On 2026-09-12, the Dinari split adapter was extended to retain documented
opaque `next` cursors and support explicit same-instance continuation for both
global and per-stock feeds. The credentialed Sandbox compound case passed
`1/1` (12 measured operations, 23 HTTP requests); the live response was already
terminal, so no additional continuation request was needed. Fixture coverage
passed `64/64`, and the complete backend unit suite passed `1,910/1,910`.
This remains transport/schema evidence only; Dinari quota, fees, eligibility,
display/cache, redistribution, and commercial routing gates remain fail-closed.
