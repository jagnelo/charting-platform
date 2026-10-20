# Provider live-validation matrix

## Current source/admission snapshot — 2026-10-15 20:38 UTC

This snapshot supersedes the older source/admission section immediately below.
The exact published source is `1ab6f79868a736535143ad8a50a649a3afacd36b`.
A fresh `make provider-live-preflight` completed admission analysis with the
owner-private durable quota ledger accessible; it made zero provider HTTP
requests and admitted 20 of 27 manifests. Seven remain held: Alpha Vantage,
CTA Plan, EODHD, and Nasdaq lack current headroom for their full daily
reservations; Dinari lacks an account-reviewed Sandbox quota/reset/cost map;
Marketstack lacks the monthly headroom for its two-call reservation and has
unresolved discovery cost/MIC; Tiingo lacks current hourly usage baselines.
No held provider was called. This is current admission evidence, not provider
live acceptance. The private ledger was accessed only to read current durable
quota state; no reservation or usage was spent by the preflight.

The same exact source passed GitHub CI run
`38798881420`: backend and frontend unit jobs, branch-declared migration
compatibility, and Playwright E2E. The migration check covered all 50 changed
files, confirmed fresh-install/existing-database provider-quota schema/data
equivalence, and previous-release `/health 200`. Playwright reported 151 passed
and 109 skipped (260 total). Exhaustive Integration Gate was skipped by the
feature-branch workflow condition. Credentialed provider live validation was
not run.

## Current source and provider admission — 2026-10-15 18:45 UTC

The Provider worktree is dirty at branch HEAD
`65a467b43d7830b0875d9c3ad538e47a06d4a6db`; it is not yet a clean pushed
checkpoint. The latest no-transport preflight at `2026-10-15T18:45:55Z`
evaluated all 27 provider manifests, admitted 20, quarantined seven, and sent
zero provider requests. It confirmed the owner-managed durable quota
coordinator is ready with no global blockers; the seven holds below are
provider-specific. The earlier sandbox-only ledger permission failure was
resolved by using the authorized local-ledger path. This is current admission
evidence, not a live-provider pass or exact-source provider receipt.

The seven quarantined manifests and exact admission reasons are:

- Alpha Vantage: its nine-request daily reservation exceeds current shared
  headroom.
- CTA Plan and Nasdaq: each requires two daily directory requests, beyond the
  remaining client-side daily allowance.
- EODHD: its 16-request daily reservation exceeds current shared headroom.
- Dinari Sandbox: account-reviewed quota/reset semantics and the complete
  worst-case operation-cost map are missing; nine normal Sandbox operations
  remain unverified for reset behavior.
- Marketstack: the two-call monthly reservation lacks headroom; directory
  discovery remains non-routable until its venue/MIC, reset, and per-page cost
  are established.
- Tiingo: the active hourly usage baseline is unknown for OHLCV, current price,
  instrument profile, and search. Its last durable dashboard baseline is
  `2026-10-14T18:27Z`; a read-only dashboard attempt redirected to login, and
  no credentials or provider API request were used.

The routing safety preflight separately reports FINRA async result-byte use as
non-routable until the download/accounting path can admit and retain a complete
result safely. A static maximum response size is not a provider-published
payload limit: FINRA documents async responses as having no maximum payload
size, while capping each asynchronous request at 100,000 records. Its signed
result link expires two hours after the completed status response or 24 hours
after result creation, whichever comes first. Thus the present positive bound
is a local stop-before-download guard, not a reason to truncate and accept a
partial dataset. A durable enabling path must retain the original query and
page/filter state, stream results to persistent storage without buffering an
entire result in memory, account observed bytes against the durable monthly
pool, and restart an expired job from its saved query rather than silently
dropping rows. The current fail-closed disposition is covered by focused
routing, adapter, and quota tests (3 passed on 2026-10-15); no FINRA async
result was downloaded during this review. See [FINRA Query API large-dataset
and async documentation](https://developer.finra.org/docs). This operation is
separate from the 27-manifest count. Tradier, IBKR, and Ondo remain explicit
user deferrals. These operation-level states are not silently treated as
provider success. Existing 20/27 live receipts belong to a prior exact
candidate tree and are not promoted to this dirty source. No provider request
was made during the current preflight.

### Provider documentation checks — 2026-10-15

Dinari's official [environment reference](https://docs.dinari.com/reference/environments)
identifies separate Sandbox and Live base URLs. Its [Quickstart](https://docs.dinari.com/docs/quickstart)
says that listing supported stocks is a read-only connectivity check that needs
no Entity, KYC, or funding. The reviewed official pages do not publish a numeric
Sandbox request quota, reset boundary, or operation-cost table; searches of the
official docs for rate-limit and `X-RateLimit` guidance produced no matching
documentation. This cannot establish that no server-side limit exists, so the
account-specific Sandbox profile and normal operations remain quarantined; no
extra request was made to infer limits from headers.

Dinari's [Partner Fees page](https://docs.dinari.com/docs/fees) separately
states that API access is billed monthly and starts at $2,000/month, while
Sandbox access is free during evaluation/build. Thus the current Sandbox
integration can support isolated contract testing only; no production/live
Dinari routing is admitted under this workstream's free-only boundary or
without a separately authorized paid entitlement.

Marketstack's official [pricing page](https://marketstack.com/pricing/) and
[FAQ](https://marketstack.com/faq) publish 100 Free-plan requests per month and
state that each stock ticker looked up consumes one unit (five symbols consume
five). The FAQ does not specify the exact monthly reset anchor. The official
[API Playground documentation](https://docs.apilayer.com/marketstack/docs/playground)
shows `GET /v2/tickers?search=...` and `GET /v2/exchanges`, but the reviewed
public material does not state how an exchange-wide paginated ticker directory
is billed per page or per returned ticker. The existing rolling-30-day safety
window and discovery quarantine therefore remain; no directory request was
made. The provider's monthly allowance is known, while this account's exact
reset anchor and the directory operation's cost are not.

The owner reports the Marketstack account's 100/100 monthly request pool is
fully consumed. Its FAQ confirms per-ticker billing for data lookups, but does
not settle the exchange-wide discovery-page charge. No further Marketstack
request is admissible or was attempted.

### Current exact-candidate and backend evidence

At 15:43Z, the unchanged staged candidate tree
`60b5d49f3799659f82bda2cc04eea6609bfc0cd9` (parent source HEAD
`65a467b43d7830b0875d9c3ad538e47a06d4a6db`) passed 20/27 admitted provider
manifests: 56/56 cases, zero failures, and 129 provider HTTP requests. The
offline verifier matched all 20 receipts to that exact tree; seven manifests
were quarantined before transport. This is partial live acceptance, not a
current clean-source matrix.

The full backend gate before that live candidate passed 3,166 tests (2,771
unit and 395 PostgreSQL/Redis integration) at 82% coverage on candidate tree
`457d8e5dd35cf6c09a2d03b6e92cf4d673bf3b60`. The later candidate differs in
five files; the only implementation/test change is MarketData.app `/user/`
accounting, plus documentation. Its focused regression passed 1/1 (134
deselected) with Ruff clean. The full backend gate still needs to pass on the
final clean exact source. Migration equivalence passed 50 changed files on a
dirty candidate and must be rerun or source-bound after final edits.

Repair CI run `38785967367` ended with its 260-case Playwright job cancelled
at case 94/260; no assertion failure appeared before cancellation, and the
Exhaustive Integration Gate was skipped. Its repair owner has since started a
replacement local full matrix; the log reached 75/260 at 18:58Z. This is still
active and not a pass. Provider has not started an overlapping full gate or
changed frontend files.

## Historical candidate acceptance — 2026-10-13 11:23 UTC (superseded)

The exact staged candidate tree
`3166d70a39c500d63ecc37aeeac9ce50dd66f6ad` passed all manifests admitted by
its provider-specific preflight: 20/20 providers, 56/56 cases, zero failures
or skips, 138 HTTP requests, and 55,488,120 response bytes. All 138 requests
were matched to entries in the private response archive without displaying
response bodies or credentials. The exact-tree receipt verifier remains
incomplete for six safely held providers: Alpha Vantage, Dinari, EODHD,
Marketstack, Nasdaq, and Tiingo. Their individual admission requirements are
recorded below and in the branch handoff; do not retry until preflight admits
them.

The Docker-backed backend coverage gate previously passed 2,746 unit tests,
390 PostgreSQL/Redis integration tests, and 82% coverage. Migration
compatibility has now passed for all three changed migrations, including a
previous-release `/health 200` smoke. `make validate-integration` now passes
dependency and migration stages but stops at backend formatting: five
branch-touched files were formatted, while Ruff still flags many untouched
backend files. No unrelated files were reformatted.

The latest provider-specific zero-transport preflight at 11:23Z admits 20
providers and holds six: Alpha Vantage (9-call daily reservation exceeds current headroom),
Dinari (Sandbox quota/cost contract unreviewed), EODHD (16-call daily
reservation exceeds headroom), Marketstack (monthly baseline and discovery
MIC/page cost unresolved), Nasdaq (today's two-file allowance consumed), and
Tiingo (current request/byte/symbol counters unavailable). It made zero provider
requests. Do not retry held slices until their individual admission
requirements clear.

Workflow tests passed 76/76, changed-file Ruff check and format passed, branch
validation passed all 30 records, and staged/unstaged diff checks passed. The
full `make validate-integration` gate remains incomplete because broad backend
format checking flags many untouched files; the five branch-touched files
reported by that check are individually formatted. No unrelated files were
reformatted.

Universe persistence remains separate from provider-manifest acceptance. The
2026-10-13 Nasdaq Trader files were persisted as `7,487/7,487` equities and
`5,761/5,761` ETFs, with zero quarantines or deactivations. Complete NMS
evidence currently covers two distinct source dates (2026-10-09 and
2026-10-13); it still needs one more distinct completed session date before
absence-based lifecycle decisions can be exercised. Complete FINRA OTC evidence
covers three dates (2026-10-09, 2026-10-12, and 2026-10-13): 18,008 rows over
four retained pages, zero quarantines/deactivations, and 20 missing listings
still pending rather than retired. Cross-environment secret-store verification
and the separately deferred final 30-day shadow run remain open. Exact counts
and source references are in the branch workstream handoff and validation
journal. The updated staged tree hash is retained in the external redacted
receipt rather than self-recorded inside the tree being hashed.

## Backend and Marketstack correction — 2026-10-11 15:09 UTC

The current backend coverage harness passed all `2,728` unit tests across 55
shards and all `390` Docker-backed PostgreSQL/Redis integration tests. Combined
coverage was `82%`, above the 75% gate. Migration compatibility passed for all
three changed migration files, and the previous-release `/health` smoke
returned `200`. The ordinary `make branch-tests` and `make
test-backend-coverage` wrappers stalled before starting a visible test process;
the same manifest-declared `backend_coverage.py --shard-size 50` harness was
therefore run directly with the assigned worktree runtime environment. This
backend result is not provider live acceptance.

The 2026-10-11 Marketstack account-usage attempt made one successful AAPL EOD
data request, then failed because the expected monthly usage counters were
absent. Its owner-private response archive stores the response body, not HTTP
headers. The durable usage ledger preserves one HTTP request, 3,692 response
bytes, and the observed generic `x-rate-limit-remaining: 0` header; it provides
no matching limit or monthly reset. That header cannot establish the monthly
account baseline. The request is accounted as one Marketstack data call; no
second request will be made merely to inspect headers. The false
`fetch_account_usage` adapter, live case, manifest requirement, and bootstrap
policy have been removed again.

APILayer's general rate-limit guide says subscribed plans normally return
daily/monthly limit and remaining headers on every request, but it does not
identify a Marketstack-specific endpoint billing contract. The Marketstack
response recorded here did not carry those four fields. Do not transplant the
general APILayer behavior onto this key without Marketstack-specific evidence;
the documented dashboard remains the current source for its account baseline.
Marketstack history and venue discovery remain blocked until the account's
monthly baseline is reconciled; discovery also requires a reviewed MIC and
page-cost bound.

The latest zero-transport preflight evaluated all `26` providers, admitted `19`
and quarantined `7`, with zero provider requests. Alpha Vantage, EODHD, and
Nasdaq lack enough current daily headroom for their full test reservations;
Massive lacks a current shared-minute baseline; Tiingo lacks current hourly,
daily, monthly-bandwidth, and unique-symbol baselines; Marketstack lacks its
full monthly account baseline and a reviewed discovery MIC/page-cost bound;
Dinari Sandbox lacks a verified quota/reset and operation-cost profile. The
current tree is dirty, so earlier provider receipts are not exact-tree
acceptance evidence.

## Backend gate refresh — 2026-10-10 19:12 UTC

The Docker-backed `make test-backend-coverage` gate completed on the current
working tree: 2,712 unit tests and 389 integration tests were collected, the
command exited successfully, and combined coverage was 82% against the 75%
threshold. This validates backend code and PostgreSQL/Redis integration; it is
not provider live acceptance. The provider matrix below remains the separate
external-service gate, and the prior 17-provider live run remains dirty-source
evidence until exact-candidate receipts cover every admitted manifest.

## Latest provider-matrix execution — 2026-10-10 18:05 UTC

Marketstack's prior `fetch_account_usage` case was removed after source
inspection showed it fetched one AAPL EOD data row, not account quota state.
The response did not establish a monthly baseline. Its registry capability and
live-manifest mapping now reflect that; history/price and discovery operations
remain subject to their own quota admission controls.

The latest full live execution ran all manifest cases for the 17 providers
admitted by shared-ledger preflight: 46/47 passed, with 96 measured HTTP
requests and 47,751,891 response bytes. Nine providers were held before
transport. The one failure was SEC Company Facts: the test reached quota
settlement, but the coordinator emitted a generic error while retaining the
reservation. A safe diagnostic now reports only the internal exception class;
a follow-up run of that exact SEC case passed 1/1. The 17-provider run and the
retry are `not_current_source` because the worktree is dirty, and do not close
all-provider live acceptance. Receipts are appended in the workstream
validation journal.

The latest zero-network full-roster preflight at `2026-10-10T18:30:07Z`
evaluated all 26 providers, admitted 17, held nine, and sent zero provider
requests. The held providers and reasons are: Alpha Vantage, EODHD, and Nasdaq
for insufficient current daily headroom; Massive, Tiingo, Marketstack, and
direct xStocks for unknown account/IP usage baselines; Dinari for an
unpublished Sandbox quota/reset/cost contract; Marketstack additionally for
an unresolved MIC and discovery-page cost; and Bybit xStocks for verified
request-egress jurisdiction evidence. Bybit's public-data gate does not require
user trading/product eligibility. This is a preflight hold, not nine provider
test failures. The 17-provider live run and its receipts remain
`not_current_source` because the worktree is dirty; they do not close the
all-provider candidate gate.

Provider-usage research found that Massive's official FAQ says keys on one
account share subscriptions and limits, so a second key adds no capacity; the
reviewed REST docs do not identify a cumulative usage endpoint. Tiingo's
current documentation specifies quota windows but does not document a usage
counter API; its older `/account/usage` path was already tested and returned a
404, so it will not be retried. Sources: [Massive account FAQ](https://massive.com/knowledge-base/categories/faq),
[Tiingo API documentation](https://www.tiingo.com/documentation/).

### Marketstack: if the dashboard is the only usage source

Marketstack says to monitor current quota use in its account dashboard; the
reviewed API documentation does not provide an account-usage endpoint. If the
dashboard confirms the configured Free plan and its 100-request monthly limit,
record its current `used` count as a dashboard baseline—not as a provider API
call. The service derives the unit, 100-request safety limit, shared account
scope, and conservative rolling 30-day window from the provider contract:

There is now a first-party source conflict to resolve before treating even that
allowance as confirmed: the [pricing page](https://marketstack.com/pricing/)
currently says Free includes 100 requests/month, while the [FAQ](https://marketstack.com/faq)
contains both a 100-request statement and a conflicting 1,000-request
statement. Until the account dashboard or Marketstack support confirms the
allowance for this specific key, keep the configured 100-request cap as a
conservative safety bound; do not raise it based on the FAQ's 1,000 figure.

```sh
curl -X POST "$APP_ORIGIN/api/v1/market-data/quota-coordinator/baselines" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "marketstack",
    "capability": "price_history",
    "dimension": "requests_per_month",
    "used_units": "<actual integer from dashboard>",
    "observed_at": "<actual timezone-aware observation timestamp>",
    "evidence_reference": "dashboard:marketstack:2026-10-10"
  }'
```

This is a template, not a runnable request: replace both placeholders with the
actual current dashboard count (as a JSON integer) and observation time; do not
send an API key, screenshot, URL, or dashboard contents. Then inspect the
durable remaining headroom:

```sh
curl "$APP_ORIGIN/api/v1/market-data/quota-coordinator/baselines?provider=marketstack&capability=price_history&dimension=requests_per_month" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

This baseline can only admit data operations whose reservation fits the
remaining conservative budget. It does not resolve Marketstack's separately
unconfirmed `/exchanges/{mic}/tickers` page cost or which MICs to query for a
complete US venue set. If the dashboard shows a different plan or allowance,
do not submit this baseline against the default Free-plan contract; update the
provider-specific plan configuration with evidence first. Marketstack's FAQ
and support page explicitly direct users to the dashboard for current usage:
[FAQ](https://marketstack.com/faq), [support and plan details](https://marketstack.com/contact).

### Dinari Sandbox quota evidence remains incomplete

Dinari's publicly hosted [API License with SLA](https://assets.dinari.com/forms/Dinari_API_License_w_SLA_20240611.pdf)
states a maximum of one million API calls per rolling 30-day period. That
document does not establish whether the stated allowance applies to this
Sandbox account/key, whether Sandbox has a separate lower throttle, the
provider's reset-boundary semantics, or the account's current consumed usage.
Keep routine Dinari operations quarantined and retain only the already-tested,
one-request-per-UTC-day read-only canary until the applicable account contract
and usage baseline are established. Do not treat the license-wide figure as a
verified Sandbox rate limit or quota profile.

## Latest full-roster preflight — 2026-10-10 17:36 UTC

The zero-provider-request preflight read the existing owner-private durable
quota ledger and evaluated all 26 providers. It admitted 17 and held nine:
Alpha Vantage (daily headroom below the nine-request matrix reservation),
EODHD (daily headroom below 15), Nasdaq (daily headroom below two), Massive
(current shared-minute usage unknown), Tiingo (hour/day/unique-symbol/monthly
bandwidth baselines unknown), Dinari (provider reset/cost contract incomplete),
Marketstack (discovery MIC and page-cost contract missing), Bybit xStocks
(user and egress jurisdiction evidence missing), and direct xStocks (deployment
jurisdiction and active public-minute baseline missing). No provider request
was sent. `Tradier`, `IBKR`, and `Ondo` remain explicit user deferrals, not
failed providers.

Tiingo's quota *limits* are documented, not unknown: its current Starter plan
publishes 500 unique symbols/month, 50 requests/hour, 1,000 requests/day, and
1 GB monthly bandwidth. Its general docs state hourly reset each hour, daily
reset at midnight Eastern, and monthly bandwidth reset on the first at
midnight Eastern; the unique-symbol reset anchor and exact hourly bucket model
remain unspecified. The configured account uses the separately owner-reported
custom profile (500 unique symbols/month, 50 requests/hour, 1,000 requests/day,
2 GB bandwidth/month), not an assumption that the public Starter bandwidth
limit applies.

The current account-usage baseline is incomplete. The owner-reported dashboard
snapshot reconciled at `2026-10-15T12:15:49Z` recorded 50/50 hourly requests and
992/1,000 daily requests remaining; local app settlements after that snapshot
are retained in the durable ledger. Its hourly observation has expired under
the application's one-hour safety envelope, so OHLCV, current price, profile,
and search remain quarantined. Tiingo's documentation links `/account/usage`
as an account webpage, not a documented machine-readable quota API. Previous
bounded checks did not return usable counters (redirect/404 and a separate
Cloudflare 403); do not retry the account URL or spend market-data quota to
manufacture a baseline. A fresh operator dashboard observation or a verified
native counter contract is required before those calls can be admitted. No
Tiingo provider request was made during this refresh.

Sources: [Tiingo API documentation](https://www.tiingo.com/documentation/),
[Tiingo pricing](https://www.tiingo.com/account/billing/pricing), and
[Tiingo API introduction](https://www.tiingo.com/blog/presenting-tiingo-api/)
(the latter points to the account-usage webpage but is not a usage API spec).

Marketstack documentation research narrows its discovery question but does
not yet safely settle the cost of `/exchanges/{mic}/tickers` pages. Official
pricing says Free is 100 requests/month and EOD-only; its FAQ says a request
with five specifically queried ticker symbols consumes five requests. The
documented ticker-list endpoint is paginated and scoped by MIC, but the reviewed
sources do not explicitly say whether a list page is charged as one API request
or by the number of returned ticker rows. Therefore the integration still
reserves no discovery requests until that distinction and a venue MIC are
resolved. The fresh receipt is in the append-only validation journal; it is
preflight evidence only, not live acceptance.

At `17:39:58Z`, the Marketstack case named `fetch_account_usage` passed with
one HTTP request and 430 response bytes, but inspection of its adapter shows
it actually requests one AAPL EOD row; it is not a native quota-only endpoint.
The response's generic `X-Rate-Limit-Remaining` value lacks a matching limit
or reset and cannot establish monthly usage. The focused one-symbol history
preflight at `17:46Z` was blocked before transport because the active monthly
usage baseline is still unknown. The full-roster preflight separately holds
discovery for the MIC and page-cost questions. The live receipt is
`not_current_source` because the worktree is dirty.

## Current dirty-worktree validation — 2026-10-10 16:22 UTC

The current working tree's Docker-backed backend gate passed `2,701` unit
tests and `389` PostgreSQL/Redis integration tests with `82%` combined line
coverage. Its append-only `backend_coverage` receipt is at `15:33:48Z`.

A fresh full-roster provider run then passed all `47/47` manifest cases for
the `17` providers currently admitted by the durable quota/jurisdiction
preflight, making `100` measured HTTP requests. There were no failed or skipped
cases. The other nine providers were quarantined before transport: Alpha
Vantage, Bybit xStocks, Dinari Sandbox, EODHD, Marketstack, Massive, Nasdaq,
Tiingo, and direct xStocks. The detailed redacted result is receipt
`provider_live_matrix` at `16:22:09Z` in the workstream validation journal.
The runner returned `not_current_source` because 108 source paths were dirty;
this is live evidence for the working tree, not exact-candidate acceptance.
No provider was reported as fully accepted by this partial-roster run.

## Fresh no-network admission check — 2026-10-10 17:18 UTC

A new zero-request preflight evaluated all 26 registered providers and again
admitted 17 while quarantining Alpha Vantage, Bybit xStocks, Dinari Sandbox,
EODHD, Marketstack, Massive, Nasdaq, Tiingo, and direct xStocks. The durable
receipt confirms that no provider HTTP request was sent. Daily-headroom holds
will be retried after their applicable usage windows; Massive and Tiingo still
need current account-use baselines; Marketstack discovery still needs its MIC
and full-page billing cost; the tokenized venues still need deployment and
eligibility evidence. These are not credentials-missing failures.

At the time of this checkpoint, the Dinari Sandbox canary was held by the
previous implementation's account-profile requirement; no request was made.
That gate is now replaced with an application-only one-request-per-UTC-day
reservation for a single read-only catalogue connectivity check. This local
ceiling is not Dinari's provider quota. The provider-specific profile remains
unknown, so recurring/multi-operation tests and ordinary routing stay blocked.

The Dinari canary implementation in the current source captures both successful
and provider-error response bodies and archives them through the owner-private,
mode-0600 response archive before quota settlement. The bodies are not written
to canonical production data tables. Unit regressions assert both the success
and error archive paths. The older summary-table entry below claiming that
canary bodies are discarded is stale and superseded by the current code/tests;
the 2026-10-06 handoff entry records that historical intermediate change.
Current official [Quickstart](https://docs.dinari.com/docs/quickstart) confirms
Sandbox stock-list reads require no Entity, KYC, or account funding, and the
official [Stock Data guide](https://docs.dinari.com/docs/stock-data) documents
the stock-list and market-data endpoints. The reviewed public pages still do
not publish a Sandbox request quota, reset boundary, or endpoint-cost schedule,
so a new canary remains blocked until a safe account-specific quota contract
can be established.

## Latest exact-candidate evidence — 2026-10-10 14:36 UTC

The current staged candidate tree
`93d688e1745d84f1f07cf72ec1082d25161f10c3` (parent
`65a467b43d7830b0875d9c3ad538e47a06d4a6db`) passed all 17 currently admissible
provider manifests: 47 cases, zero failures, zero skips, 100 HTTP requests,
and 51,714,799 response bytes. The providers were Alpaca, Binance, Coinbase,
CoinGecko, SEC EDGAR, Finnhub, FINRA, FINRA OTC Directory, FMP, FRED, Gate
TradFi, Kraken, Kraken xStocks, MarketData.app, OpenFIGI, Robinhood Tokens,
and Twelve Data. The provider receipt verifier confirmed all 17 against this
exact candidate and made zero provider requests.

The aggregate gate remains incomplete for Alpha Vantage, Bybit xStocks, Dinari
Sandbox, EODHD, Marketstack, Massive, Nasdaq, Tiingo, and direct xStocks. The
fresh full-roster preflight at 14:45:39 UTC used the owner-private durable
quota ledger, evaluated all 26 providers, admitted 17, quarantined those 9,
and sent zero provider requests. Exact reasons remain in the corresponding
`provider_live_preflight` record in the workstream validation journal. A
restricted, non-elevated attempt could not read the private ledger and showed
22 eligible / 4 locally quarantined; that is an environment-permission
diagnostic, not the authoritative account-headroom result. Rerunning through
the authorized private-ledger path restored the correct 17 / 9 result.

The provider receipts and response archives remain outside Git. The owner has
already authorized private persistent storage of returned provider data; all
successful and failed live response bodies are retained in the owner-private
archive and are never silently dropped by the probe harness. No missing API
credentials or new owner approvals are needed for work to continue. Some
provider-specific facts may still require account-dashboard evidence or actual
deployment-egress details if public documentation and local configuration
cannot establish them.

## Fresh EODHD usage-only probe — 2026-10-10 14:56 UTC

The restricted preflight could not read the owner-private durable quota ledger,
so it stopped with zero provider requests. Re-running through the authorized
ledger path passed the same no-network preflight. The EODHD account-usage-only
case then passed `1/1` at `14:56:54Z` (one HTTP request; 305 response bytes).
Its full redacted response body was durably appended to the owner-private
response archive, and the quota observation was reconciled into the durable
usage coordinator. A follow-up zero-network EODHD full-manifest preflight still
held the data matrix because its 15-call daily reservation does not fit current
headroom. No history, price, or discovery request was made. This focused receipt
is `not_current_source` because the worktree is dirty; it is not provider-matrix
acceptance.

A full-roster no-network preflight at `15:00:04Z`, using the same authorized
durable quota coordinator after that EODHD snapshot, still admits 17 of 26
providers and holds the same nine. It sent zero provider requests. The refreshed
EODHD native daily usage data did not create enough headroom for the 15-call
manifest reservation; no hold cleared. The full blocker details are recorded
in the corresponding `provider_live_preflight` journal entry.

## Fresh Marketstack usage observation — 2026-10-10 15:05 UTC

The focused Marketstack usage-only live case passed `1/1` at `15:05:57Z` with
one AAPL EOD request (430 response bytes); the full redacted body is in the
owner-private archive. The response exposed only `X-Rate-Limit-Remaining`,
without a matching monthly limit or reset. The adapter correctly preserves it
as an unclassified observation and does not seed monthly quota headroom. A
focused history/price preflight no longer trips over the separate discovery
settings, but it remains blocked because `requests_per_month` usage baseline
is unknown. Venue discovery remains independently blocked on its exchange/MIC
and page-cost evidence. The live receipt is `not_current_source` because the
worktree is dirty and is not complete-provider acceptance.

## Validation after operation-scoped Marketstack gating — 2026-10-10

The focused runner/provider unit suites passed `281/281`. The full required
backend gate then passed `2,701` unit tests and `389` Docker PostgreSQL/Redis
integration tests (`3,090` total), with `55,172/66,935` covered lines (`82.43%`,
above the 75% threshold). Scoped test-container cleanup succeeded; no host-wide
Docker prune was used. The workstream validator passed all 30 records and
`git diff --check` passed.

The post-change full-roster preflight at `15:35:07Z` evaluated all 26 providers,
admitted 17, held the same nine, and sent zero provider requests. It confirms
the Marketstack change did not weaken full-manifest admission: directory
discovery still requires its own MIC/page-cost evidence and the other providers
remain held by their exact quota-baseline, headroom, quota-contract, or
deployment-egress findings. The current code change therefore improves
operation-level diagnostics/testing but does not turn the aggregate live gate
green.

## Fresh full-roster preflight — 2026-10-10 12:39 UTC

A current no-network preflight evaluated all 26 providers using the existing
owner-private durable quota ledger. The first sandboxed attempt could not
write that ledger because its directory is outside the worktree's writable
paths; rerunning the same zero-request check with the workflow's authorized
private-ledger access succeeded. This was an execution-environment boundary,
not a damaged or read-only ledger. The successful preflight admitted 17
providers, held 9, and sent zero provider requests. There are no missing API
credential variable names.

Current holds: Alpha Vantage (9-request daily reservation does not fit current
headroom), EODHD (15-call daily reservation does not fit), and Nasdaq (two
directory files do not fit current daily headroom); Massive and Tiingo (active
account usage baselines are unknown); Bybit xStocks and direct xStocks
(deployment-egress jurisdiction evidence is missing); Dinari Sandbox
(account-specific quota/reset/operation-cost profile is incomplete); and
Marketstack discovery (exchange/MIC and venue-wide page cost are unresolved).
The separate focused Kraken xStocks probe remains incomplete because its
catalogue was empty, not because it was in this preflight's held set.

## Fresh focused probes — 2026-10-10 12:37 UTC

The full roster remains at 17 admitted and 9 held; the latest no-network
preflight made zero provider requests. A dedicated EODHD account-usage probe
then passed `1/1` at `12:36Z` with exactly one HTTP request. This refreshed its
provider-native usage observation but did not make the complete 15-call EODHD
manifest admissible: the immediately following focused preflight still found
insufficient daily headroom. No EODHD history/discovery manifest calls were
made.

Kraken xStocks' focused preflight passed without transport. Its live manifest
case then passed the discovery request at `12:37Z` (one HTTP request; 678,579
response bytes), but the returned catalogue was empty. The result is retained
as a successful empty discovery observation, not as asset-lookup or pricing
acceptance: both operations remain without live positive-response evidence,
and the runner correctly reports the provider matrix incomplete. No symbol or
quote was synthesized. Both focused live receipts remain `not_current_source`
because the candidate worktree is dirty.

These probes do not change the full-roster hold set or turn the admitted
subset into all-provider acceptance. The detailed request measurements and
receipts are in the append-only workstream validation journal.

## Current state — 2026-10-10 11:48 UTC

The full live runner at `11:41Z` re-evaluated the complete 26-provider roster
against the durable shared quota coordinator, admitted 17 complete manifests,
and held Alpha Vantage, Bybit xStocks, Dinari Sandbox, EODHD, Marketstack,
Massive, Nasdaq, Tiingo, and direct xStocks before transport. It then ran the
admitted 17-provider subset: 46/47 cases passed, 97 measured HTTP requests;
the SEC issuer-CIK directory case failed while settling its durable quota
reservation. Its response was archived before settlement, and the reservation
was retained as pending (not refunded). A preflight for that exact SEC case
then passed with no request, and an immediate isolated retry passed 1/1 with
one request. This makes the settlement failure non-reproducible so far, but
the original 17-provider run remains a failed receipt and is not rewritten as
a pass. The focused retry and full subset both remain `not_current_source`
because the worktree is dirty. Kraken xStocks still has no live catalogue
assets, so asset-lookup and price-lookup operations remain unexercised.

Massive's official account FAQ/blog documents dashboard request monitoring
(request ID, status, user agent, response size, IP/location, and key), but no
documented API snapshot or reset-boundary contract. This gives an operator a
way to inspect recent account activity; it does not establish the current
baseline until that account view is actually reconciled. Source:
[Massive dashboard monitoring](https://massive.com/blog/free-data-apis).

At `11:52:44Z`, Marketstack's dedicated account-usage-only case passed `1/1`
with one HTTP request. The private redacted usage ledger retained only the
generic `x-rate-limit-remaining: 0` header for that response; it did not
contain the documented-by-adapter monthly/day limit-and-remaining header
pairs or a reset boundary. Do not interpret the generic zero as monthly
remaining or seed the monthly baseline from it. This validates the bounded
probe transport but not Marketstack quota reconciliation or discovery
admission. Its response body is preserved in the owner-private archive; the
usage receipt and full-matrix gate remain `not_current_source` because the
candidate checkout is dirty.

At `11:58:36Z`, the zero-network full-roster preflight again evaluated all 26
providers, admitted 17, and held 9; zero provider requests were sent. Current
holds are Alpha Vantage, EODHD, and Nasdaq (complete-manifest daily headroom);
Massive, Tiingo, and direct xStocks (current shared-usage baselines); Dinari
Sandbox (account-specific quota/reset/operation-cost contract); Marketstack
(exchange-page cost and MIC); and Bybit xStocks (deployment egress evidence).
The current no-network receipt is in the append-only workstream validation
journal.

Current first-party contract review did not resolve the Marketstack listing
page charge: pricing and the contact FAQ state 100 Free requests per month,
while the FAQ also includes one contradictory 1,000/month sentence; its
billing FAQ charges per requested ticker but does not specify exchange-wide
listing pages. Dinari documents the Sandbox stock-list endpoint and pagination,
but does not publish a current Sandbox request ceiling, reset, endpoint weight,
or usage snapshot. Neither missing fact was replaced with a guessed limit.
Focused Marketstack adapter/quota-contract tests passed `27/27`.

The current dirty worktree also passed the full combined backend coverage gate
on `2026-10-10`: 2,698 unit tests and 389 Docker-backed integration tests,
combined coverage `82.39%` (`55,137/66,920` lines) against the required 75%.
This is local integration evidence only; it does not turn held providers or
dirty-source live receipts into all-provider acceptance.

## Current state — 2026-10-10 10:20 UTC

The all-provider manifest run at `10:07:01Z` admitted 17 providers, quarantined
9, and made 94 measured HTTP requests. Across its 47 cases, 45 passed, one
failed before its next HTTP request because Twelve Data's live quota guard
refused another history read, and one Kraken xStocks case skipped after the
live catalogue returned no xStocks pairs. Twelve Data was re-preflighted alone
without network calls, and its complete two-case manifest passed at
`10:09:10Z` (6 measured HTTP requests). After correcting Kraken's case to retain
its successful empty-catalogue observation rather than pytest-skip it, the
focused case passed at `10:16:07Z` with one measured request and archived
678,580 response bytes. The runner explicitly remains incomplete for
`get_tokenized_asset` and `get_tokenized_price` because the live catalogue
provided no symbol to look up; this is not a provider-acceptance pass. The
focused Kraken receipt and earlier receipts all remain `not_current_source`,
and the source has changed again since the 10:07 matrix. The runner now has a
regression proving that a passing empty-catalogue case cannot satisfy missing
asset/price operations (103 runner unit tests pass). The full-roster preflight
still admits 17 and holds 9. Exact holds: Alpha Vantage (daily
headroom), Bybit xStocks (deployment egress jurisdiction), Dinari Sandbox
(quota/reset/operation costs), EODHD (daily headroom), Marketstack (discovery
page cost), Massive (current shared-minute usage baseline), Nasdaq (daily
directory headroom), Tiingo (hour/day/month/symbol/bandwidth baselines), and
direct xStocks (deployment egress jurisdiction and public-minute baseline).
The durable coordinator was accessible for all live runs. Run IDs and per-case
measurements are in the append-only validation journal.

At `10:31:26Z`, the admitted-subset run executed all 17 provider manifests:
`47/47` pytest cases passed, with 98 measured HTTP requests and 52,044,720
archived response bytes. The overall receipt is still incomplete because the
Kraken xStocks catalogue returned no instruments, leaving live asset-lookup
and price-lookup operations unexercised. No other manifest case failed or
skipped. Receipt `ecea0ba3-73b5-420e-947e-12d03b08c714` is `not_current_source`
because the checkout is dirty; the nine non-admitted providers were not
called. This is useful refreshed evidence, not all-provider acceptance.

At `10:25:23Z`, the full-roster zero-transport preflight was repeated against
the owner-private shared coordinator: 17 provider manifests admitted, 9 held,
zero provider requests. The holds remain provider-specific (quota headroom or
active-usage evidence, unresolved Marketstack listing-page cost/MIC, Dinari
quota/reset semantics, and deployment-egress evidence); there is no global
coordinator failure. This refresh does not change the 10:20 live-test result
or make the dirty source acceptable.

## Current state — 2026-10-10 09:55 UTC

The latest no-transport full-roster preflight at `09:55:18Z` evaluated all 26 providers:
17 were eligible for their complete manifest and 9 were quarantined for
provider-specific headroom/baseline, operation-cost, or deployment-egress
evidence. It made zero provider requests. The complete manifest therefore
remains blocked; this does not mean the 17 eligible providers failed. The
Docker-backed combined NMS/OTC reconciliation integration test also passed
(`1/1`, 38.39 seconds) on the current dirty tree. This proves the service
persists a complete Nasdaq snapshot and a complete FINRA OTC snapshot in one
cycle; it does not activate the daily schedule or constitute the all-provider
live gate. The nine current holds are Alpha Vantage (daily headroom), Bybit
xStocks (deployment egress jurisdiction), Dinari Sandbox (unpublished quota,
reset, and operation costs), EODHD (daily headroom), Marketstack (discovery
operation cost), Massive (current shared-minute usage baseline), Nasdaq
(daily directory headroom), Tiingo (hour/day/month/symbol/bandwidth baselines),
and direct xStocks (deployment egress jurisdiction and public-minute baseline).

## Latest admitted-subset live run — 2026-10-09 17:11 UTC

A shared-ledger preflight evaluated all 26 providers and admitted 13; 13 were
held before transport for provider-specific usage baselines/headroom, missing
quota or operation-cost facts, or deployment-egress evidence. No credential
variable names were missing. The 13 admitted providers then passed their
complete manifest suites: `41/41` cases, zero failures/skips, 73 measured HTTP
requests, and 43,309,130 archived response bytes. The providers were Alpaca,
Binance, Coinbase, CoinGecko, EDGAR, FINRA, FINRA OTC Query API, FMP, FRED,
Kraken, MarketData.app, OpenFIGI, and Twelve Data. The exact per-provider
receipt is in `ops/workstreams/feat-market-data-provider-platform/validation.jsonl`
under run `85818bc8-5b2e-455a-8cd7-06796d6f992a`.

This is not all-provider or exact-source acceptance: the other 13 providers
were not called, and the receipt is `not_current_source` because the worktree
is dirty. The measured requests were recorded in the persistent shared quota
ledger. A no-network preflight at `2026-10-09T17:12:07Z` then rechecked the
full roster and still admitted those same 13 providers; no provider request
was made by that check. The other 13 remain held by their specific usage,
quota/cost, daily-headroom, or egress findings in the workstream receipt.
Run another preflight before spending any provider quota.

At `2026-10-09T17:16:31Z`, the zero-network preflight was rerun after correcting
Bybit's quota accounting. Bybit is no longer held for an unknown anonymous
five-second usage baseline: the configured 600-per-5-second IP limit now uses
an explicitly application-only baseline, while the authenticated UID headers
remain telemetry only. It is still held before transport until actual
deployment egress jurisdiction is evidenced. No Bybit request was sent.

At `2026-10-09T17:21:15Z`, the full zero-network preflight admitted 14 and held
12 of the 26 providers. Alpha Vantage is newly admitted: its key-specific
one-second and one-minute limits now explicitly initialize application usage
in the shared local coordinator; its distinct 25-requests-per-24-hours pool
remains ledger-backed and was not reset or seeded. No provider requests were
made. Alpha's complete 9/9 manifest had already passed earlier that day, so it
was not repeated. This remains neither all-provider acceptance nor
exact-source acceptance because the other 12 providers are quarantined and
the checkout is dirty.

The Docker-backed backend gate then completed at `2026-10-09T17:51:56Z`:
`2,663/2,663` unit tests across 54 shards, `388/388` integration tests, and
82.35% combined coverage (75% minimum). The durable receipt records this as
backend validation only; it does not change the 14/12 provider admission split
or make the dirty-source live receipts exact-source acceptance.

Gate TradFi's provider-specific 5-requests/second/IP usage contract now tracks
application requests in the shared quota ledger and retains Gate's documented
`X-Gate-RateLimit-*` fields as telemetry without inferring a reset from the
normal-response timestamp. Kraken xStocks shares its public-IP quota scope
with Kraken crypto. A fresh no-network preflight at `17:56:05Z` admitted 16 and
held 10 providers. The focused Gate/Kraken live run at `17:56:42Z` passed the
Gate catalogue, asset, and order-book operations in four requests. Kraken's
one-page live AssetPairs response had no xStocks pairs; only its catalogue
operation was exercised, and the runner correctly leaves live evidence
incomplete for Kraken asset lookup and ticker. The post-run preflight at
`17:57:24Z` still admits 16 and holds 10. This is not all-provider acceptance.

Robinhood's Stock Token API docs publish a 60-requests/second public-IP
ceiling and caching behavior, but no current-use counter. Its provider-specific
contract now initializes only application-observed usage in the shared local
coordinator. Focused contract/coordinator/telemetry tests passed `12/12`; the
zero-request full preflight at `17:58:33Z` admits 17 and holds 9. Robinhood's
complete live manifest has not yet been rerun against this source.

## Exact quota-bounded case runs

The owner's final decision is to proceed with private single-user automation
and persistent storage even where a provider's terms would otherwise restrict
those uses. `PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK=true` is enabled by
default in local, RPi, and credentialed-CI configuration; these terms are not
an approval gate. Authentication/entitlement, quota, response-size, and
geographic-access checks remain independent and fail closed. Historical rows
below that still ask for provider-term permission are stale; they are retained
as historical evidence, not current blockers.

Use `--case PROVIDER:TEST_FUNCTION` when only selected manifest cases should
spend quota. The Alpha Vantage example below selects exactly two cases and
currently sends two requests if the durable preflight admits them; do not use
it as a request to rerun a completed probe without first checking quota state:

Every actual canonical live run requires an explicit `--max-http-requests`
value. This non-negative integer caps HTTPX transport attempts across the
entire runner invocation, including provider batches, redirects, auth/helper
requests, and retries. Select the value from the reviewed operation/case budget;
the runner supplies no guessed default. Zero intentionally denies the first
send. The cap supplements, and never replaces, native durable quota admission
and settlement, response retention, holds, or global authentication/rate-limit
stops. Exhaustion fails the full test and stops later cases; it cannot turn a
partial universe traversal into success. `--preflight-only` and
`--verify-candidate-receipts` remain no-HTTP operations and do not require a
cap. Live command examples below use
`${PROVIDER_LIVE_RUN_HTTP_LIMIT:?set the reviewed non-negative ceiling}` so
they cannot silently run without one.

```sh
scripts/run-live-provider-probes.py --provider alpha_vantage \
  --case alpha_vantage:test_alpha_vantage_credentialed_current_price \
  --case alpha_vantage:test_alpha_vantage_credentialed_search --preflight-only
```

The preflight must clear before running the same command without
`--preflight-only`. Each selectable case must have an explicit mapping to the
provider operation(s) it tests; unsupported or ambiguous selectors fail before
transport. Exact case-to-operation maps are now validated across the live
manifest. For candidate validation, a fully staged tree may be tested one exact
case slice at a time; each receipt is outside the worktree and remains
non-acceptance evidence on its own. Final acceptance requires the receipt
verifier to account for every manifest case and required operation for each
provider against the same staged candidate tree. This allows quota-limited
cases to be collected across provider reset windows without treating partial
coverage as a pass.

For a staged candidate, first run the exact case's `--preflight-only` command
without `--allow-staged-candidate`; only run the live candidate command if the
durable quota preflight admits it. All provider/application/test/workflow source
files must be staged and unchanged. Unstaged edits are allowed only in this
branch's already-staged `ops/workstreams/<branch-slug>/` records: those are
execution notes and do not change the source candidate hash. Untracked files
and unstaged changes anywhere else still block candidate validation:

```sh
scripts/run-live-provider-probes.py --provider alpha_vantage \
  --case alpha_vantage:test_alpha_vantage_credentialed_daily --preflight-only
scripts/run-live-provider-probes.py --provider alpha_vantage \
  --case alpha_vantage:test_alpha_vantage_credentialed_daily \
  --allow-staged-candidate \
  --max-http-requests "${PROVIDER_LIVE_RUN_HTTP_LIMIT:?set reviewed cap}" \
  --candidate-receipt-file /tmp/market-data-provider-candidate-live.jsonl
```

Repeat for each exact manifest case as quota permits. Once every required
provider has complete case coverage, verify accumulated receipts against the
current staged tree (this makes no provider requests):

```sh
scripts/run-live-provider-probes.py \
  --verify-candidate-receipts /tmp/market-data-provider-candidate-live.jsonl
```

The receipt file is local, outside Git, and created with owner-only permissions.
An incomplete-coverage result is expected until all required cases have passing
receipts; do not rerun already-passed data calls merely to remove that status.

## Current FINRA OTC acceptance — 2026-10-07

The official FINRA Symbol Directory Query API route is now live-validated and
supersedes the earlier ORF-only blocker below. The credentialed traversal used
the current `otcSecurityMaster` partition and returned 18,009 rows, all with
unique symbols, in four pages (5,000, 5,000, 5,000, and 3,009). The partition
date was stable at 2026-10-07. The live manifest case passed `1/1` in 10.63s.
Its receipt is `not_current_source` only because this worktree was dirty; it
must be rerun after the final commit for current-source acceptance.

The integration follows `record-total`, persists each raw page before
normalization, rejects duplicates or changing totals/partition dates, and never
treats a partial traversal as complete. FINRA's documented 500,000 maximum
offset is handled as an explicit fail-closed boundary requiring filtered
tranches if this dataset ever grows that large; data is not silently omitted.
The exact Query API contract is 1,200 synchronous requests/minute/IP, 5,000
records/request, 3 MB maximum synchronous payload, and 10 GB downloaded/month
for this public credential. The request pool and byte pool are coordinated
durably with other FINRA operations. The owner-private ledger contains the
11,030,150-byte investigation/live baseline. ORF remains available as an
optional separately entitled adapter, but is no longer required for the full
current OTC roster.

The authoritative post-change backend gate passed on 2026-10-07: all 2,578
unit tests, all 388 Docker-backed integration tests, and 82% combined line
coverage against the 75% minimum. The run also completed its scoped Docker
cleanup without a host-wide prune.

## Previous continuation audit — 2026-10-06

This is the latest gate evidence for the dirty worktree as of
`2026-10-06T18:31:46Z`; verify its source SHA with `git rev-parse HEAD`. It
supersedes the October 4 status below where the two records differ, but does
not turn preflight or focused tests into acceptance.

| Acceptance area | Current result | Evidence / remaining action |
| --- | --- | --- |
| Alpaca paper account | Seven-case live manifest passed | Seven cases passed with eight HTTP requests, covering daily/intraday history, latest price, account usage, stock/crypto profiles, and assets/corporate actions. The response archive contains 6,526,882 bytes; no order endpoint ran. Receipt: `not_current_source` because the worktree is dirty. |
| Binance keyless crypto coverage | Three-case live manifest passed | Three cases passed at 17:38 UTC with five HTTP requests: universe discovery, account-usage snapshot, bounded daily history, current price, and history. The private archive retained 17,685,466 response bytes. Receipt: `not_current_source` because the worktree is dirty. |
| Alpha Vantage listing status | One bounded live case passed | Exactly one request at 17:23 UTC; its 1,068,761-byte response was retained privately and parsed as 14,483 active rows (8,598 stocks, 5,885 ETFs) with six exchange labels and no OTC label. This does not prove all-US/OTC completeness. Receipt: `not_current_source`; preserve all prior account usage and check quota before any further call. |
| Alpha Vantage current price and symbol search | Prior bounded cases passed; current use blocked before transport | The owner confirmed no outside use during the preceding 24 hours, but the shared ledger preserves this app's own requests. The 18:31:46Z full preflight reports current one-second and one-minute usage baselines unknown. No Alpha Vantage request was sent in this continuation; do not infer permanent key exclusivity or clear app reservations from the outside-use attestation. |
| Alpha Vantage forward earnings calendar | One bounded live case passed at 18:17 UTC | Exact case selection cleared preflight under a temporary invocation-only account scope based on the owner's no-outside-use attestation. It used exactly one request; the 298,887-byte CSV response is retained in the owner-private archive and contains 4,574 data rows with the documented calendar columns. The durable receipt is `not_current_source` because the worktree is dirty. The shared ledger now shows 25 Alpha Vantage requests in the conservative rolling 24-hour window (24 before this run); do not make another call until an earlier request ages out and fresh preflight admits it. No persistent exclusivity setting was changed. |
| Nasdaq NMS directory | Live admission blocked today | The official two-file test would consume the client-imposed two-requests-per-market-day cap. Current shared-ledger headroom is below that reservation, so preflight sent zero Nasdaq requests. The application window resets at midnight US/Eastern; retry only after that boundary and a fresh preflight. |
| Finnhub | Live admission blocked before transport | Current focused preflight found active minute and per-second baselines unknown for all five enabled operations; zero requests were sent. The private usage ledger preserves historical native response headers from 2026-09-15 (`X-RateLimit-Limit: 60`, `Remaining: 58`, `Reset: 2026-09-15T16:08:45Z`), proving those responses carried a reset epoch at that time, but this is too old to establish current account usage. Finnhub's public docs publish the separate 30-calls/second hard cap but do not document these headers. Personal-use/retention rights are independently unresolved. |
| MarketData.app account usage | Fresh live snapshot passed | The `/user` account-usage-only case passed with one request at 17:29 UTC. Retained response headers report a 10,000-credit limit, 10,000 remaining, and OPRA entitlement delayed 15 minutes. This refreshes quota/entitlement evidence only; no price/history/options endpoint ran. Receipt is `not_current_source` because the worktree is dirty. The configured trial expiry remains October 11, 2026 at 18:09 Lisbon time. |
| MarketData.app data-bearing live cases | Now fail closed before transport | Added exact case selection for options, history, quote, and usage tests with explicit operation mappings. The current option-surface case preflight is blocked because the test runner durably archives response bodies and current terms require deleting downloaded data when the subscription ends; provider retention exception evidence is absent. No options-chain request was sent. |
| EODHD and Marketstack data-bearing live cases | Now fail closed before transport | EODHD is blocked by unresolved account/reset and display-use controls. Marketstack's Free-plan cap is modeled as 100 requests per rolling 30 days; data-bearing calls still require archive-rights evidence, and universe discovery additionally requires a reviewed MIC and per-page charge. Focused preflights sent zero requests. |
| EODHD native account-usage endpoint | Bounded live probe passed at 16:42 UTC | The documented `/api/user` usage-only case passed `1/1` with one request and reconciled the live per-key request-window observation into the durable quota coordinator. No market data was fetched. Its data-bearing routes remain blocked on display/use rights; this receipt is `not_current_source` because the worktree is dirty. |
| FINRA ORF live admission | Required, but blocked before transport | The 18:31:46Z full preflight sent zero requests and still requires `FINRA_OTC_SOURCE_KIND`, inactive-file URL, TRAQS username, refresh token, and durable token-state path. The quota/cost profile, written access/use terms, and full-OTC coverage also remain unverified. Current ORF/FINRA/live-runner/secret-wiring tests passed `166/166`; no ORF request was made. The only owner action currently needed is FINRA's written answer on individual access, use/retention, quota, and coverage; do not enter TRAQS credentials until FINRA confirms eligibility. |
| Dinari Sandbox canary payload isolation | Current source archives payloads; stale contrary note superseded | Successful and provider-error canary reads are archived privately before quota settlement and are excluded from canonical data tables. Unit tests verify both paths. The unknown Sandbox quota/profile still blocks a fresh canary. The earlier 2026-10-06 “discard bodies” intermediate state is preserved in the chronological handoff but is not the current source behavior. |
| Full provider matrix | Not accepted | Latest full 26-provider no-transport preflight at 18:31:46Z sent zero requests. It found 91 quota/cost/baseline findings, 17 safety/rights findings, 17 unresolved operation dispositions, and five missing ORF environment inputs (categories overlap). Alpha Vantage's current one-second/minute baselines are unknown; no call was attempted. See the redacted receipt in `ops/workstreams/feat-market-data-provider-platform/validation.jsonl`. |
| Full backend unit/integration gate | Incomplete; latest attempt failed | The declared Docker-backed gate reached about 72% and exited `152` without a pytest summary, so it is not a pass and the migration test did not run in that attempt. The same command subsequently passed migration compatibility for 47 changed files (`origin/master` → checked-out schema; prior-release app `/health` 200). At the same time, kernel logs recorded OOM kills in the separate active ETF research-runner container. This is a possible resource interaction, not established causation; that container/worktree was not altered. Do not retry the heavy suite until the resource condition is understood. |
| Workstream validation and scoped checks | Partial pass | The latest workstream validator and `git diff --check` pass; the ORF/FINRA/live-runner/secret-wiring suite passed `166/166`, and changed workflow suites passed `31/31`. These focused results do not replace the incomplete full backend gate. |
| Deployment/CI secret stores and 30-day shadow run | Unverified / not started by design | No remote secret store or deployment was accessed. The shadow run remains the final gate after controllable criteria pass and separate approval. |

The full workstream handoff records the detailed chronology and external
actions in `ops/workstreams/feat-market-data-provider-platform/handoff.md`.

## 2026-10-09 refresh

The table above is a historical snapshot. A fresh full-matrix preflight at
`2026-10-09T00:33:23Z` evaluated all 26 requested providers, sent zero provider
requests, found no missing environment-variable names, and remains
`blocked_before_transport`: six providers are eligible and 20 are quarantined.
There are 99 provider-specific quota/cost/baseline findings plus six required
safety findings (overlap is expected); this is an admission failure, not a
failed provider test. The durable quota coordinator is ready when run with
access to the owner-only quota ledger.

The owner-attested Alpha Vantage no-use statement was recorded in that ledger
for its 1-second, 60-second, and 24-hour request windows. The next checks
verified the 24-hour pool, but the shorter rolling baselines expired before
the full preflight reached transport admission. The full suite therefore still
quarantines Alpha Vantage for unknown 1-second and 60-second active usage. No
Alpha Vantage HTTP request was sent. Clearing those short windows requires a
provider-supported live remaining-usage observation or an explicit assurance
that this key is used only through the shared quota coordinator; a stale
zero-use snapshot is not sufficient.

The full Docker backend gate subsequently passed 2,631 unit tests and 388
integration tests at 82% combined coverage. This verifies backend behavior,
not live acceptance for the 20 quarantined providers. The source tree remains
dirty, so prior focused live passes are not yet current-source acceptance.

## 2026-10-09 latest admission and attempted admitted-subset run

At `2026-10-09T11:28:19Z`, a fresh full preflight evaluated all 26 providers.
Twelve were independently eligible (`alpaca`, `binance`, `coinbase`,
`coingecko`, `edgar`, `finra`, `finra_otc_directory`, `fred`, `kraken`,
`marketdata_app`, `openfigi`, `twelve_data`); 14 were quarantined for
provider-specific quota, usage-baseline, or explicit safety-control findings.
The preflight made zero provider requests. Thus “the all-provider gate is red”
means at least one required provider is held; it does not mean all 26 failed.

The first attempt to run the 12-provider manifest lacked elevated filesystem
access and stopped before tests or network access because the managed execution
sandbox exposed the shared private SQLite quota ledger as read-only. No
temporary, empty ledger was substituted because that would erase cross-session
quota accounting. A later run with elevated access succeeded: all 38 manifest
cases passed across the 12 admitted providers (Alpaca, Binance, Coinbase,
CoinGecko, EDGAR, FINRA, FINRA OTC Directory, FRED, Kraken, MarketData.app,
OpenFIGI, and Twelve Data), with no failures or skips. It made 64 provider
requests and received 41,684,760 response bytes. The exact receipt is appended
at `2026-10-09T12:03:31Z`, run ID
`3f8eca87-1d97-4632-a416-4692fe8e7b24`; it is `not_current_source` because the
tree is dirty. This was a bounded provider-subset pass, not all-provider
acceptance.

A fresh full preflight at `2026-10-09T12:03:55Z`, after usage reconciliation,
admits 11 providers and quarantines 15. Twelve Data is newly held because its
current per-minute credit headroom is below the full-matrix reservation (6
units). The 64 live requests are accounted for in the shared ledger. Do not
repeat the passing subset solely to refresh evidence; final acceptance still
requires running the complete required matrix from the final committed source.

The current dirty tree's full backend coverage gate subsequently passed:
2,647/2,647 unit tests (53 shards), 388/388 Docker-backed integration tests,
and 82% combined line coverage against the 75% minimum. The scoped Docker
cleanup completed. This is current backend implementation evidence only; it
does not replace provider live acceptance. See the branch handoff for the
exact source HEAD and run details.

## 2026-10-09 latest recorded evidence — through 17:01 UTC

The bounded FMP manifest passed `3/3` at `16:45:02Z` (eight measured HTTP
requests). The focused provider/quota/runner/secret-wiring suite passed
`547/547`; the full backend coverage gate passed `2,651/2,651` unit tests and
`388/388` integration tests at 82.34% combined line coverage. These are
positive implementation and provider-specific results, not all-provider live
acceptance; the FMP receipt still says `not_current_source` because the source
tree is dirty.

The historical all-provider preflight snapshot at `16:53:48Z` successfully accessed the
owner-wide durable quota ledger, evaluated all 26 providers, and sent zero
provider requests. It admitted 13 and quarantined 13: Alpha Vantage, Bybit
xStocks, Dinari, EODHD, Finnhub, Gate TradFi, Kraken xStocks, Marketstack,
Massive, Nasdaq, Robinhood Tokens, Tiingo, and xStocks. Findings are
provider-specific at that time: missing current-use baselines, insufficient live-test
headroom for EODHD/Nasdaq, unresolved Dinari Sandbox quota/cost data,
Marketstack discovery scope/cost, the then-unresolved Massive reference-bucket
limit, and tokenized-provider egress evidence. Massive's quota contract was
subsequently corrected: its current Basic-access documentation applies a
single 5-requests/minute Stocks asset-class limit to the stock operations in
this adapter. The current hold is only for reconciling active shared-key usage
before sending more requests. This is a safety-preflight
hold, not 13 failed API tests. The detailed zero-network receipt is in
`ops/workstreams/feat-market-data-provider-platform/validation.jsonl`.

Massive's current first-party Basic-access FAQ says reference data, corporate
actions, and minute aggregates work on Basic and the 5-request/minute limit is
per asset class. The earlier interpretation that reference calls use a second,
undocumented bucket was incorrect and has been removed from the runtime
contract. Stock history, reference, and corporate-action calls now reserve from
the same Stocks account bucket. The provider-published minute boundary and
native current-use counter remain unknown; the application uses a rolling
60-second reservation envelope and still requires a trustworthy current-use
baseline before live admission.

An Alpha Vantage provider-focused zero-network preflight cleared using the
owner's earlier no-use attestation and an invocation-only exclusive-scope
override; that override was not persisted to local, CI, or deployment
configuration. The bounded Alpha Vantage manifest then passed `9/9` at
`16:59:31Z` with exactly nine measured HTTP requests. It covered daily,
weekly, and monthly history; complete listing-status retrieval; current price;
symbol search; IPO calendar; forward earnings calendar; and earnings history.
The shared quota ledger accounted for the requests. Its receipt is
`not_current_source` because the worktree is dirty; this does not clear the
other 13 providers still held by the full-matrix preflight.

Focused EODHD preflights at `17:00:31Z` and `17:01:42Z` tested whether its
profile entitlement case or its smaller history/price/discovery case could fit
the remaining free-plan daily pool. Both were blocked before transport: the
profile case reserves ten daily credits, the mapped small-read suite reserves
five, and current headroom is below both; the active per-minute usage baseline
is also unknown. No EODHD requests were sent. Retry after the documented daily
reset, starting with a fresh preflight.

## Historical acceptance audit — 2026-10-04

This is the current implementation boundary for
`feat/market-data-provider-platform` at the checked-out source (verify with
`git rev-parse HEAD`). “Verified” means
repository-controlled behavior has automated evidence; it does not imply
that external entitlement, licensing, deployment, or account state has been
approved.

| Acceptance area | Current state | Evidence / remaining action |
| --- | --- | --- |
| Canonical FIGI identity, issuer/listing history, quarantine | Verified in code/tests | `backend/app/models/`, identity/mastering services, focused unit suites |
| Series-scoped OHLCV, provenance, rollups, adjustments | Verified in code/tests | market-data persistence and series tests |
| Exchange sessions and freshness | Verified in code/tests | session/calendar models and freshness tests |
| Capability/entitlement/quota/health routing | Implemented; live promotion blocked | exact provider contracts, baselines, and legal controls remain unresolved |
| Daily core refresh | Verified | UTC-dated idempotency key fix `410c25e73` |
| Refresh throughput | Verified/configurable | `MARKET_DATA_REFRESH_QUEUE_BATCH_SIZE`, commit `ba3893314`; deployment tuning still needs latency/quota evidence |
| High-alert polling and evaluator preflight | Verified in code/tests | grouped alert preflight paths; deployed cadence still requires runtime validation |
| Events, earnings, SEC facts, FINRA short interest, options, tokenized paths | Implemented with fixtures; selectively live-proven | provider entitlement/legal/account gates remain open |
| Provider-specific operation costs and response-byte accounting | Implemented | unresolved provider plans still fail closed |
| Admin/diagnostic APIs and queue telemetry | Verified in code/tests | backend provider, coverage, quarantine, session, queue, shadow, and bounded historical-event refresh endpoints |
| Compatibility aliases and yfinance isolation | Verified | yfinance remains explicit compatibility only |
| Provider contract/live workflow enforcement | Verified | manifest, reservation, redaction, candidate-tree, and receipt checks |
| Durable cross-session usage | Verified locally; deployment reconciliation open | owner ledger works; GitHub/RPi/production stores remain unverified |
| NMS universe | Complete Nasdaq Trader two-file snapshot live-tested | production materialization/reconciliation and full-venue coverage still required |
| OTC universe | Daily List/lifecycle and candidate parsers implemented | authorized complete security-master source and rights are still required |
| SEC directory/materialization | Staged policy implemented | clean dry-cycle review and operator admission remain required |
| Dinari Sandbox isolation | Verified in policy; exact candidate live run pending | canary payloads are archived privately; they do not enter canonical production data, and ordinary routing remains disabled |
| Full current-candidate live matrix | Not accepted | 2026-10-04 18:04:08 UTC no-transport preflight: 26 providers evaluated, `0/0` live cases, 80 quota/cost/baseline records, 12 rights/safety records, and 21 unresolved operation dispositions; categories overlap; no provider transport occurred; source is dirty |
| Full-stack browser profile | Not accepted | Dirty candidate run: 147 passed, 4 failed, 109 skipped; the four failures passed on one focused retry. The separately enabled board-visual matrix ran 104 cases: 12 passed and 92 exceeded the committed screenshot-diff threshold. No frontend edit or baseline change is authorized in this branch. |
| 30-day deployed shadow run | Not started by design | final gate only after all preceding controls pass |

Latest changed-candidate evidence (2026-10-07): the Docker-backed combined
backend gate passed all `2,575` unit tests and all `388` integration tests at
82.34% line coverage. The bounded runner now uses 50-test unit shards and
streams subprocess output; the previously suspected ETF-heavy shard was also
isolated and passed `50/50` in 15.27 seconds. Focused FINRA/runtime/quota regressions passed `211/211`,
and SEC/universe/FINRA directory/short-interest/tokenized pagination suites
passed `135/135`. New exact-provider live runs on this dirty candidate passed
Alpaca `7/7` (8 requests), Binance `3/3` (5 requests), OpenFIGI `3/3` (3
requests), and MarketData.app `7/7` (9 requests, including the bounded option-
history path and the unbounded-history refusal). All four receipts are in
`validation.jsonl` and usage is coordinated through the owner ledger; they are
not full-matrix or exact-source acceptance.
The EODHD `/user` and MarketData.app `/user/` account-usage-only suites also
passed `1/1` each. MarketData.app's fresh native counters removed five
previously unknown per-operation quota-baseline findings; EODHD's snapshot
refreshed its account state but the remaining profile reservation still
exceeds today's headroom, so no profile request was attempted. The new
`make provider-live-preflight` diagnostic reports current blockers and stops
before transport; its receipt explicitly cannot count as live evidence.

The latest resumed-goal validation then ran the complete branch-scoped browser
suite against a seeded stack with provider egress denied. It completed 260
cases: 147 passed, four failed, and 109 skipped. The four failed cases were
`F9c-template-comparison`, `F8p-90-90`, `F8p-90-90-history`, and `F8u`; an
isolated rerun passed all four (`4/4`), so their full-suite failures are
treated as flaky/unreproduced, not silently waived. The normal suite's visual
spec guard leaves the board-guided matrix skipped, so the dedicated
`test:visual:board` command was also run explicitly: 104 cases, 12 passed and
92 failed screenshot comparisons against the committed Linux snapshots. The
observed diffs were typically 1–3%, above the unchanged 0.5% threshold, across
multiple viewport scales and UI/data states; no screenshot baseline or
frontend source was changed. The research-runner sandbox and bounded resource
probes passed, and the exact branch Compose project was then cleaned up with
its scoped volumes and images.

After mechanically formatting the remaining changed Python files, Ruff lint
and formatting checks passed for all 41 changed Python files. Focused provider,
quota, runtime, secret-wiring, live-runner, and workflow tests passed
`898/898`; all 30 workstream records validate. The latest full-provider
preflight (`2026-10-04T18:04:08Z`) still stops before transport with zero
requests and the same overlapping `80/12/21` quota/rights/operation blocker
counts. This remains a diagnostic preflight, not provider acceptance. After
the FRED-terms clarification, the FRED/provider-rights, quota, secret-wiring,
and registry focused suites passed `450/450`; the strict structured-browser
receipt validator passed `4/4`, and the RPi provider-secret names-only
preflight contract passed within a `36/36` deployment/secret-wiring suite; no
remote deployment store was accessed. All 30 workstream records validate. The
validation ledger remains append-only.

After those focused calls, the full manifest preflight at
`2026-10-04T14:52:39Z` again stopped before selecting providers or transport:
`0/0`, 80 provider quota/cost/baseline records, 12 safety/rights records, and
21 unresolved operation cases. The 80 records include insufficient remaining
headroom for EODHD's profile operation and Nasdaq's two-request client cap after
their respective focused suites; no further EODHD or Nasdaq calls should run
until the provider-specific windows have reset and their current use is
reconciled. The receipt also records Marketstack discovery as blocked on its
unverified exchange-page charge, current monthly allowance/reset evidence,
archive authority, and explicit MIC. A bounded historical-event admin route
also now resumes cursor pages and skips completed windows unless refresh is
explicit. The full-matrix receipt is diagnostic because the source is dirty;
the no-transport full run itself added no provider requests.

Marketstack ticker discovery now matches its documented
`/exchanges/{mic}/tickers` path; the previous `exchange=` query filter was not
documented. Its public “one request per specific ticker” billing statement
does not establish the cost of an exchange-wide page, so there is no seeded
discovery cost. `MARKETSTACK_DISCOVERY_MAX_PAGE_COST` plus
`MARKETSTACK_DISCOVERY_COST_EVIDENCE` must be configured from provider/account
evidence before routing; the former guessed value is also removed from existing
provider-source rows during refresh. This is separate from the monthly cap,
reset, and archive-rights gates.

The focused Marketstack adapter/quota/runner/secret-wiring suite passes
`353/353`; the associated runtime/registry/universe suite passes `128/128`.
Ruff lint, `git diff --check`, both root and RPi Compose parses, and validation
of all 30 workstream records pass. No Marketstack HTTP request was made.

The subsequent broad deterministic provider replay on the same dirty source
passed all `597` tests under `backend/tests/unit/providers` and all `526`
provider-platform service/runtime/routing/quota/universe/event/short-interest/
secret-wiring/live-runner regressions (`1,123` tests total). Ruff lint and
`git diff --check` also pass; the workstream validator accepts all 30 records
and its workflow tests pass `3/3`. These suites made no provider HTTP requests.
The full Docker backend coverage gate remains pending: a read-only container
check at 15:07 UTC showed an active Playwright/frontend/research stack belonging
to `feat-tc2000-frontend-rework`, which this branch must not modify or stop.

Earlier changed-candidate evidence (2026-10-04): the combined Docker-backed
backend integration/coverage gate passed `2,858/2,858`, 89 warnings, and
82.23% coverage in 1,108.02 seconds. The refreshed quota/coordinator/
registry/runtime/live-runner/secret-wiring suite passed `318/318` in 51.01
seconds; Ruff, `git diff --check`, and workstream validation passed. The
full-stack browser profile is still not accepted: the current-candidate run
passed 150, failed 4, and skipped 106; an isolated retry passed three of the
four, while `F9c-template-comparison` reproduced the same chart-toolbar hit
target overlap. This is frontend-owned and remains untouched in this branch.
Bounded
current-candidate live suites also passed Alpaca `7/7`, Binance `3/3`, OpenFIGI
`3/3`, MarketData.app `7/7`, EODHD `3/3`, and Nasdaq's full-directory case
`1/1`. Their request/byte totals and individual receipts are in
`validation.jsonl`. All are dirty-worktree results, not committed-source
results. After those calls, the refreshed full manifest preflight stopped
before transport at `0/0`, recording 79 provider-specific
quota/cost/baseline blockers, 10 safety/rights blockers, and 21 unresolved
operation cases. It made zero provider requests and is not a live-matrix pass.
Massive stock history, reference, and corporate-action operations are charged
to the same documented 5-requests/minute Stocks bucket; no separate reference
limit is configured. Massive can still be held if its active rolling-minute
usage baseline is unknown. EODHD lacks daily headroom for its remaining expected
profile-denial probe, and Nasdaq's two-request client cap is exhausted for the
current market day; wait for each documented reset before any repeat.

The subsequent Binance run at `2026-10-04T02:29Z` initially passed two cases
and safely failed before the next current-price transport when its native
fixed-minute IP baseline expired at the `02:29` boundary. The shared ledger
shows the account counter had been sampled at `02:28:58Z`; no HTTP 429/418 was
received. Inspection also found that Binance history made an unnecessary
second empty-page request after a short page, while the bounded 30-day case
reserved only one page's two request-weight units. The adapter now stops after
a short page, and the general estimator accounts for the provider's inclusive
end boundary. Live probes refresh the native counter only after that fixed
minute reset. Regressions passed `35/35`, Ruff passed, and the coordinator-
gated retest passed `3/3`; the latest case measured one HTTP request each for
latest OHLCV, bounded OHLCV, current price, and universe discovery. This is
still dirty-worktree evidence, not exact-candidate acceptance. The earlier
receipt remains historical evidence of the extra request; its fixed-minute
window has expired, and the new live run established a current native baseline.

The provider-documentation review corrected several quota details without
making provider calls: FMP's current public guidance does not promise one
universal daily reset time, so its native boundary remains `provider_defined`
while the client enforces a rolling 24-hour safety envelope; Tiingo currently publishes 1 GB
monthly bandwidth; Marketstack's conservative free-plan allowance is 100
requests/month and its FAQ charges each requested ticker separately while not
publishing a reset anchor. The Marketstack FAQ also conflicts with its pricing
page by mentioning 1,000 monthly requests, so the lower published cap remains
the safe configured value. Current FRED Services Terms additionally prohibit
API use tied to software/system or AI/ML development and prohibit persistence,
caching, archiving, or database incorporation absent prior written permission.
FRED API-key guidance also says each application user must use their own key;
this server-key integration is therefore restricted to an explicitly owner-only
personal deployment until per-user keys and a user-facing terms flow exist.
FRED remains non-routable; these are rights and credential-boundary gates, not
just a quota-implementation issue.
Sources and per-provider evidence are recorded in `docs/data-providers.md` and
the workstream handoff.

The same audit found and fixed an under-accounting defect: an account-usage
probe could previously omit every unknown quota dimension, even if its native
response did not report that pool. Runtime and live-probe admission now omit
only mapped dimensions; every other metered pool needs a verified or explicit
client-owned baseline. At the time, Twelve Data's daily counter had not been
mapped to a reviewed quota unit, so `/api_usage` correctly failed closed. A
subsequent review of the current Basic pricing and usage-control documentation
established separate pools: 8 weighted credits/minute, 800 API requests/day,
and a one-credit/one-request `/api_usage` probe. The adapter now reserves those
two units separately and bootstraps each only from its matching native counter.
The earlier probe's usage remains in the historical local ledger; because it
occurred on a previous UTC day, it does not count against today's daily pool.

The branch workstream remains `in_progress`, not ready for human review or
complete. Its unresolved rows are acceptance requirements, not optional
follow-up work; see the current workstream handoff and validation receipts for
the exact account, legal/source, universe, and target-secret-store items.

For a fresh blocker report that cannot send provider traffic, run:

```sh
make provider-live-preflight
```

This evaluates the current provider manifest, credential presence, recorded
quota baselines, rights controls, and operation dispositions, then stops before
the live-test lock and pytest subprocess even if every check is clear. It does
not require `RUN_LIVE_PROVIDER_TESTS=1`; its redacted
`provider_live_preflight` receipt has `transport_started=false`,
`provider_http_requests=0`, and `live_acceptance=false`. The quota coordinator
may reconcile an already-persisted interrupted reservation for safety, but the
preflight itself does not reserve new provider usage. A clear preflight is not
evidence that any external API works; only the exhaustive manifest-driven live
matrix below can establish that.

The live matrix is intentionally separate from normal unit/integration runs:

```sh
PROVIDER_LIVE_USAGE_SCOPE=local-dev RUN_LIVE_PROVIDER_TESTS=1 \
  rtk uv run --project backend python scripts/run-live-provider-probes.py \
  --allow-staged-candidate \
  --max-http-requests "${PROVIDER_LIVE_RUN_HTTP_LIMIT:?set reviewed cap}"
```

The command performs a preflight, prints missing inputs and non-routable
controls, runs the exact manifest-backed provider cases (including the public
tokenized-security matrix), and returns non-zero when credential, usage,
quota, or source-admission checks block a required case. A missing credential
is never reported as a passing skip. The
pre-commit `--allow-staged-candidate` mode requires every tracked change to be
staged, no unstaged or untracked paths, no credential-bearing paths, and no
configured/credential-shaped secrets in staged additions. It materializes that
index into a temporary, isolated source tree and
runs pytest from that exact tree, then prints its `git write-tree` ID; it does
not modify the workstream ledger. Candidate mode may run the full matrix, one
provider's complete manifest, exact manifest case slices, or Dinari's
separately capped Sandbox canary. A provider-slice or canary receipt is not
full live acceptance; it lets us collect exact-candidate evidence when
provider-specific quota windows or approved canary limits differ.
Save successful slices outside the source worktree so the candidate remains
unchanged, for example:

```sh
PROVIDER_LIVE_USAGE_SCOPE=local-dev RUN_LIVE_PROVIDER_TESTS=1 \
  rtk uv run --project backend python scripts/run-live-provider-probes.py \
  --provider alpaca --allow-staged-candidate \
  --max-http-requests "${PROVIDER_LIVE_RUN_HTTP_LIMIT:?set reviewed cap}" \
  --candidate-receipt-file /secure/local/path/provider-candidate.jsonl
```

Repeat for each provider as its own quota admission allows. The receipt file
contains redacted operation counts/status evidence, not response payloads or
credentials. Once slices have been collected, verify the exact currently
staged tree and parent without making provider requests:

Dinari is the explicit exception to complete-provider-manifest evidence:
ordinary Sandbox operations remain quarantined because the account quota and
operation-cost profile is unpublished. The approved candidate canary is
accepted only when the exact staged tree produces one successful catalogue
request, with every other Dinari operation still represented by the intentional
no-request safety disposition:

```sh
PROVIDER_LIVE_USAGE_SCOPE=local-dev RUN_LIVE_PROVIDER_TESTS=1 \
  DINARI_SANDBOX_CANARY_AUTHORIZED=true \
  DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE='owner-approved canary' \
  DINARI_SANDBOX_CANARY_MAX_REQUESTS=1 \
  rtk uv run --project backend python scripts/run-live-provider-probes.py \
  --provider dinari --dinari-sandbox-canary --allow-staged-candidate \
  --max-http-requests "${PROVIDER_LIVE_RUN_HTTP_LIMIT:?set reviewed cap}" \
  --candidate-receipt-file /secure/local/path/provider-candidate.jsonl
```

The candidate verifier checks the canary's single-request cap, exact test case,
same-run HTTP/byte evidence, current candidate tree and parent, and explicit
quarantine of normal Sandbox operations. It does not count the canary as full
Dinari coverage or enable application routing.

```sh
rtk uv run --project backend python scripts/run-live-provider-probes.py \
  --verify-candidate-receipts /secure/local/path/provider-candidate.jsonl
```

This succeeds only if every required provider has either all successful
manifest-case receipts or its specifically approved canary receipt, tied to the
same staged tree and current parent SHA.
It does not trust a single provider's pass as matrix acceptance. If evidence is
missing, stale for another tree, failed, skipped, or incomplete, the verifier
prints the provider-specific gap and exits non-zero. After the verifier passes,
commit the unchanged index, verify `git rev-parse HEAD^{tree}` matches the
verified tree ID, then record the commit/tree and aggregate receipt in the
branch workstream. Provider/case/canary candidate runs require exactly one
`--provider`. Case slices count only after every case in that provider's
manifest has passing evidence; account-usage-only probes never substitute for
provider coverage.
Candidate mode captures and redacts pytest output, and refuses to start network
calls if credentials, usage scope, durable quota admission, or the FINRA source
admission is incomplete. The owner has authorized private single-user use and
persistent storage across providers; do not treat provider terms as an owner-
approval gate. Authentication, actual account entitlements, quotas, explicit
geographic-access controls, and response safety remain independent gates.
Nasdaq publishes no numeric quota, but a separate local two-request-per-day
cap bounds its two official files; that cap is not represented as a vendor
allowance. Any missing credential, failed or skipped case, quota response,
missing same-run operation evidence, or source change blocks acceptance. The
wrapper
returns exit code `2` for an incomplete credential/usage preflight or a
non-passing staged candidate.
For focused implementation follow-up, the same lock, usage ledger, preflight,
and manifest can select one or more provider suites without spending other
providers' quotas:

```sh
PROVIDER_LIVE_USAGE_SCOPE=local-dev-bybit RUN_LIVE_PROVIDER_TESTS=1 \
  rtk uv run --project backend python scripts/run-live-provider-probes.py \
  --provider bybit_xstocks \
  --max-http-requests "${PROVIDER_LIVE_RUN_HTTP_LIMIT:?set reviewed cap}"
```

Omitting `--provider` always runs the complete registered live matrix; provider
selection is diagnostic evidence only and never substitutes for the full
current-source acceptance run.

When a provider's native account-usage endpoint is the only currently safe
operation (for example, before its first durable pool baseline exists), use
the narrowly scoped account snapshot mode. It requires exactly one provider
and still performs credential, durable-ledger, quota, lock, redaction, and
same-run receipt checks:

```sh
PROVIDER_LIVE_USAGE_SCOPE=local-dev-account-bootstrap RUN_LIVE_PROVIDER_TESTS=1 \
  rtk uv run --project backend python scripts/run-live-provider-probes.py \
  --provider eodhd --account-usage-only \
  --max-http-requests "${PROVIDER_LIVE_RUN_HTTP_LIMIT:?set reviewed cap}"
```

This always produces a focused receipt; it cannot be mistaken for full
provider capability coverage or a full-matrix acceptance pass.

Providers explicitly deferred by the user in the active branch workstream are
excluded from that executable matrix only when their plan records the deferral;
the redacted receipt records the exact provider and rationale. Their adapters
remain fixture-covered and non-routable. A missing key for any non-deferred
provider, any failed case, or any skip still blocks a passing full-matrix receipt.
The provider secret-wiring suite also checks the live manifest itself: every
registered provider must name at least one bounded live test, or carry an
explicit exclusion rationale for an internal, legacy, or descriptor-only
entry. This prevents a provider from being added with fixtures but no live
acceptance surface.

Alpha Vantage's raw-history fixture matrix now covers all three documented
free time-series aggregations: `TIME_SERIES_DAILY` (the bounded 100-point
`compact` window), `TIME_SERIES_WEEKLY`, and `TIME_SERIES_MONTHLY`. The latter
two are full native series endpoints and still reserve one provider query each;
the adapter rejects adjusted requests for all three before transport because
the adjusted daily endpoint is premium-only. A future credentialed live case
may select one weekly or monthly range. The documented 25-requests/day
dimension remains labelled `provider_defined` for audit, while the runtime
enforces its explicit provider-scoped rolling 24-hour application envelope.
This is not presented as Alpha Vantage's native reset semantics. If a current
provider confirmation or reviewed account observation establishes a calculable
native boundary, set `ALPHA_VANTAGE_REVIEWED_RESET` and record the source in
`ALPHA_VANTAGE_QUOTA_EVIDENCE`; those optional values are wired through
local/RPi Compose and the manual GitHub workflow and replace the safety
envelope only when both are valid.
Alpaca is handled independently: its official market-data contract defines a
200-requests/minute account pool, and the native `X-RateLimit-*` headers are
retained as the current remaining/reset observation. Optional
`ALPACA_REVIEWED_RESET`/`ALPACA_QUOTA_EVIDENCE` values can document a future
plan change, but they are not required to route the current documented plan.
Corporate-action pages are fetched and persisted one page at a time; the
cursor is durable, so a later job resumes until every page is collected. No
local page bound is used to discard data.
It also prints routing-safety preflights for FINRA's asynchronous result-byte
bound, FINRA OTC's reviewed operation-cost/terms/completeness/redistribution/
poll controls, the MarketData.app reviewed account-plan/credit pair and
operation-specific option-chain symbol bound, and the operation-level
Tiingo/FMP byte-bound maps. A direct adapter read can therefore be green while
Finnhub is treated similarly: its observed 60/minute and 30/second ceilings
remain two independent dimensions, and each has its own explicit rolling
application envelope. The provider-defined labels remain visible for audit;
optional `FINNHUB_REVIEWED_MINUTE_RESET`/`FINNHUB_REVIEWED_SECOND_RESET` values
plus independent evidence can replace those envelopes. No shared window or
generic request fallback is inferred.
The same preflight also reports
its provider remains non-routable:
missing, invalid, partial, or non-positive safety controls are reported
explicitly and never guessed.
The owner's final private-use decision removes separate xStocks product-term
and user-country gates for these private, read-only public data adapters. Bybit
xStocks retains only its technical egress check: Bybit says US/Mainland-China
IP addresses receive HTTP 403, while its published public quota remains 600
requests per five seconds. The live runner and direct adapter require only the
non-secret `BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_*` evidence before
a request; they do not require Bybit trading-user eligibility evidence.
The same preflight reports whether the non-secret
`MARKETSTACK_DISCOVERY_EXCHANGE` venue scope is configured; history can still
be probed with only the key, but discovery remains non-routable without it.
The separate Marketstack quota preflight also requires the reviewed monthly
limit/reset/evidence controls; the conflicting provider pages are never
resolved by a generic default.
EODHD's detailed API-limits page documents 1,000 HTTP requests/minute and says
each successful response carries `X-RateLimit-Limit` / `X-RateLimit-Remaining`;
429 includes `Retry-After`. The Free-plan pricing card conflicts at 20/minute.
The configured key returned 1,200/1,199 on 2026-10-14, which is retained as
key-specific evidence; the runtime default remains the documented 1,000/minute
and does not dynamically widen from headers. Use `EODHD_REVIEWED_MINUTE_*` only
with complete current account evidence to configure this key's 1,200 limit.
The separate Free allowance is 20 weighted daily API-call credits (midnight
GMT); `/api/user` costs zero daily credits but consumes one minute request.
Sources: [Free-plan pricing](https://eodhd.com/pricing) and [API limits](https://eodhd.com/financial-apis/api-limits).
Coinbase's live case is blocked before transport until its exact internal,
automated, persistent, non-redistributed use has current written authority
recorded in the scoped `COINBASE_MARKET_DATA_USE_*` settings. FRED remains
blocked unless its quota scope, provider-side automated-use exception, and
rights evidence for every series exposed by the adapter are configured. Owner
retention permission is final and is not a FRED gate. These gates are sent
through local, RPi, and GitHub live environments but default false or empty; a
successful transport-only probe would not establish these rights.
Before invoking pytest, the wrapper acquires an exclusive local lock at
`~/.config/charting-platform/provider-live.lock` (override with
`PROVIDER_LIVE_LOCK_FILE`). A second worktree on the same host therefore exits
with code `3` without making provider calls. This lock is only local
single-runner serialization; quota admission is handled separately by the
durable provider-quota coordinator before each live operation. Local worktrees
share the owner-only SQLite coordinator by default. GitHub live validation
requires a persistent PostgreSQL coordinator and fails closed without it. A
deployment's default named-volume SQLite coordinator is durable for its
backend/worker containers but is not shared with GitHub or another host. If
those environments use credentials whose quota belongs to the same provider
account, point them to the same persistent coordinator and configure matching
`PROVIDER_QUOTA_ACCOUNT_SCOPES`; separate API keys alone do not prove separate
provider quota pools. Independently owned accounts may use isolated
coordinators and scopes.
The coordinator does not infer that an empty local ledger means an unused
provider account. A new finite dimension has an unknown starting balance and
blocks routing/probes until it receives an exact active-window baseline.
Currently, an administrator records a provider-dashboard attestation at
`POST /api/v1/market-data/quota-coordinator/baselines`; inspect the aggregate
coordinator at `GET /api/v1/market-data/quota-coordinator` and exact current
dimension status at
`GET /api/v1/market-data/quota-coordinator/baselines?provider=...&capability=...`.
The status reports unknown/verified state, snapshot usage, local settled debits
since that snapshot, in-flight reservations, and remaining headroom. The
request supplies only provider, capability, dimension, used units,
timezone-aware observation time, and a structured evidence locator; unit,
limit, quota group, account scope, and reset window are derived from the
reviewed provider contract. Use a reference such as
`dashboard:marketdata-app:2026-09-16`: a source, provider, and date or
human-readable descriptive slug. Do not include free text, URLs, screenshots,
API keys, bearer tokens, token-labeled values, or opaque key-shaped references;
legacy evidence values outside this grammar are withheld from admin responses.
Reconcile each applicable finite dimension separately; never translate one
unit type to another. For a fixed reset window, a newer provider snapshot
cannot erase coordinator-confirmed local debits. For a rolling window, an
equal-time replay cannot lower the baseline, but a strictly newer provider
snapshot may decrease as older usage ages out; local settled debits after that
snapshot are counted separately.

The general quota-coordinator summary resolves active limits from the current
provider contract, including plan and expiry settings, and exposes the stored
limit separately as `recorded_limit_units`. If providers sharing a bucket
disagree or the current contract cannot be uniquely matched, current limit and
headroom are unknown rather than stale persisted values.

`PROVIDER_QUOTA_EXCLUSIVE_ACCOUNT_SCOPES` is an explicit JSON map of exact
scope aliases to booleans. Mark a scope `true` only after confirming every
client of that provider account uses the same durable coordinator. A verified
scope can safely roll a zero baseline forward at a provider-defined fixed reset
or after a full rolling window elapses. Leave it unset if manual scripts,
uncoordinated deployments, or other clients may spend the same allowance; in
that case refresh the baseline for each active window.
Each live pytest process also appends measured per-provider operation, HTTP
request, and response-byte totals to the external
`~/.config/charting-platform/provider-live-usage.jsonl` ledger (override with
`PROVIDER_LIVE_USAGE_LEDGER`). This supplements, rather than replaces, the
application database's durable runtime quota windows; it makes direct live-test
consumption visible across local sessions without storing credentials or
payloads. Separately, the live test harness now archives every observed,
credential-redacted response body to the owner-private
`~/.config/charting-platform/provider-live-responses.jsonl` file (override with
`PROVIDER_LIVE_RESPONSE_ARCHIVE`). The response archive is preflighted before
network access, appended and fsynced after each measured operation, and kept
outside Git. A missing/unwritable archive or mismatch between HTTP responses
and captured bodies makes the live case fail; the request usage is still
settled and receipted. GitHub live jobs continue to publish aggregate usage
receipts only, not payload archives, because their runner is ephemeral and
public-repository artifacts are not an appropriate permanent store for raw
provider data.

Provider-native account-usage snapshots may reconcile a baseline automatically
only when the provider adapter has an explicit exact mapping for the reviewed
dimension. The current implementation permits this for MarketData.app's
`credits_per_day` pool, EODHD's `calls_per_day` pool, Twelve Data's
`credits_per_minute` and `requests_per_day` pools, CoinGecko's
`calls_per_month` pool, Binance's `request_weight_per_minute` pool, Alpaca's
`market_data_requests_per_minute` pool, and OpenFIGI's mapped request pool when the provider response returns the matching
reviewed limit, a current reset timestamp, and a valid consumed counter (or an
exact `limit - remaining` equivalent). Each reconciliation is labelled
`provider_account_observation` and uses the same durable coordinator. A plan,
limit, window, or reset mismatch remains observation-only and cannot widen
routing. Other provider pools still require operator attestation because their
native usage surfaces do not establish an equivalent dimension safely. Binance
uses the explicit one-weight `/api/v3/time` probe; it never treats an empty
local ledger as zero usage.

The provider seed also records the exact set of dimensions that each native
usage endpoint can reconcile. During bootstrap, only those mapped pools may be
omitted from the probe's pre-call quota debit because the same response
establishes their post-call baseline. Any other pool must already be safely
chargeable; otherwise the probe itself is blocked before transport, as are
ordinary operations. This prevents a successful partial usage snapshot from
masking an unobservable or unit-mismatched pool.

The direct live-test account snapshot cases use this same reconciliation path
after the provider response has been durably settled. This is important across
sessions: a successful `/user` or `/api_usage` test is not merely a receipt; it
can establish the exact active baseline for the explicitly allow-listed pools before
the next run. EODHD remains intentionally observation-only when its `/user`
response reports a stale `apiRequestsDate`, because no current daily reset has
been proven. The live receipt records the provider-native observation and the
reconciliation disposition separately, without copying the response payload or
secret.

### Updating a provider plan or establishing a new baseline

Quota policy is configuration, not a source-code constant. When an account is
created, upgraded, renewed, or moved between trial and paid plans, update the
provider-specific non-secret settings in that environment and then attest the
active window through the admin API. Do not copy a value from one provider or
account to another, and do not use an empty ledger as evidence of zero usage.

For MarketData.app, set the exact reviewed plan/limit pair. Trial plans also
require a timezone-aware expiry; after that instant the runtime deliberately
falls back to `free_forever`/100 credits per day. A paid-plan change requires
replacing the plan, limit, and (if applicable) expiry in the same environment;
the `/user/` response is an observation and cannot silently widen routing:

```dotenv
MARKETDATA_APP_REVIEWED_PLAN=starter_trial
MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT=10000
MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT=2026-10-11T18:09:00+01:00
```

After observing the provider dashboard or an explicitly supported native
account-usage response, record each finite dimension separately. The request
contains only observed usage and a non-secret evidence locator; the reviewed
limit, unit, reset boundary, account scope, and quota group come from the
provider contract:

Binance, Twelve Data, and EODHD explicitly declare a first-snapshot bootstrap
control. When a pool the response actually reconciles has no active durable
baseline, the account-usage operation may omit that pool's debit and reserve
the deployment-scoped serialized probe slot; the returned snapshot must
reconcile the pool before ordinary reads can reserve it. Other metered pools
must have a verified or explicitly client-owned baseline so their probe cost
can be charged. If the response is malformed, stale, leaves an unreported
pool unknown, or the baseline ledger is unavailable, the operation remains
fail-closed. Once a pool is verified, later account snapshots reserve the
normal provider-specific cost for that pool.
The bootstrap slot is an application safety control, not a provider quota and
must not be reported as provider entitlement.

```sh
curl -X POST "$APP_ORIGIN/api/v1/market-data/quota-coordinator/baselines" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "marketdata_app",
    "capability": "account_usage",
    "dimension": "credits_per_day",
    "used_units": 137,
    "observed_at": "2026-09-16T18:00:00+01:00",
    "evidence_reference": "dashboard:marketdata-app:2026-09-16"
  }'
```

Inspect the result before enabling or widening workers:

```sh
curl "$APP_ORIGIN/api/v1/market-data/quota-coordinator/baselines?provider=marketdata_app&capability=account_usage" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Use `calls_per_day`, `requests_per_minute`, bandwidth, and other dimensions
as separate attestations when a provider exposes more than one pool. Never
convert calls to bytes or credits. An unknown reset boundary, mismatched plan
and limit, stale observation, or incomplete dimension map remains non-routable
until an operator records a current exact baseline.

The durable coordinator also contains a reservation-linked live-receipt
registry (`provider_quota_ledger_live_receipt`). This is the authoritative
link between a live test observation and the exact quota reservation that was
admitted in that coordinator. Each registry row stores only the reservation
ID, provider, operation, run ID, usage scope, bounded receipt status, and
reconciliation timestamps/state; it never stores credentials, response
payloads, request/byte measurements, or inferred quota units. The wrapper
registers the row after the operation settles, including when a provider
failure leaves the reservation unresolved.

Before a new live matrix makes any network request, the runner opens the same
durable coordinator and reconciles every registered non-reconciled receipt.
Pending reservations are recovered conservatively using the units originally
reserved by the coordinator, never measurements copied from a JSONL artifact.
Settled or not-sent reservations are idempotent no-ops. An uncertain or
lease-expired reservation, a missing reservation, or an identity mismatch
blocks the run and requires provider-native/operator reconciliation. Legacy
JSONL rows have no reservation ID and are therefore never imported into this
registry or used to alter quota accounting. This ordering prevents a crashed
live process from silently starting another quota-consuming run against an
unknown reservation state.

The two receipt surfaces have deliberately different authority:

* The coordinator's reservation and live-receipt tables are authoritative for
  admission, settlement, and recovery within the configured provider account
  scope. They must be backed up with the quota ledger/database.
* `provider-live-usage.jsonl` and GitHub's uploaded JSONL artifact are
  redacted, aggregate audit evidence. They remain useful for measured
  request/operation/byte reporting and manual account reconciliation, but they
  are observational only: they do not create reservations, settle a
  reservation, infer a provider limit/reset, or change routing. The checked-in
  merger may deduplicate them into an owner-managed audit ledger, but it must
  not be treated as a substitute for the durable coordinator.

If the coordinator or its receipt registry cannot be opened, written, locked,
or reconciled, the live runner fails closed before transport. Restore the
coordinator from a trusted backup or record a fresh exact provider baseline
for every affected finite dimension before enabling that provider again; an
empty replacement database is not evidence of zero external usage.
Each receipt row also contains a bounded `operation_usage` map keyed by the
explicit adapter operation (for example `get_instrument_profile` or
`fetch_tokenized_historical_prices`). Each entry contains only operation count,
HTTP-request count, response bytes, and failed-operation count. Older receipts
without this map remain valid and are reported with an empty operation
breakdown. The admin usage response exposes the normalized breakdown under
`live_test_usage.operation_breakdown`; these observations remain separate from
runtime reservations and never infer a provider quota or reset window.
The live wrapper supplies one fresh run ID and records each observation under
the exact pytest node ID. Candidate receipts require current-run evidence for
every manifest case and required operation; prior ledger rows cannot satisfy
the check. MarketData.app's unbounded historical-option test is separately
typed as a no-request policy block, not transport evidence. EODHD's expected
free-plan profile `403` is recorded as an explicit entitlement denial rather
than a successful data response or an unexpected provider failure. A passing
pytest count without these correlated observations cannot produce a green
matrix receipt. The receipt distinguishes required live reads, expected
entitlement denials, intentional no-request policy cases, user-deferred
providers, and unresolved operational bounds. Only unresolved dispositions
keep capability evidence incomplete; policy and denial rows remain visible as
non-data coverage and cannot be mistaken for a successful quote or history
read.
When `RUN_LIVE_PROVIDER_TESTS=1`, the live pytest session first opens the
configured ledger for a zero-byte append and exits with code `2` before any
provider test runs if that path is not writable. This prevents a filesystem
permission failure at teardown from spending provider quota without a receipt.
The same startup check requires a bounded, printable
`PROVIDER_LIVE_USAGE_SCOPE`; direct pytest invocations cannot silently create
new unattributed `unspecified` receipts.
Direct live pytest is additionally rejected unless the manifest runner marks
the process with its internal matrix-run marker; this keeps approved provider
deferrals and routing/legal preflight controls in force for every external
request.
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
The live test helpers make that distinction executable: every direct provider
operation first reserves its exact reviewed quota dimensions in the durable
coordinator, then marks the request context admitted. Opt-in live pytest
sessions install synchronous and asynchronous HTTPX transport guards that
reject any request without that active reservation before it is sent. All
current external provider adapters use HTTPX; a future adapter using another
transport must add an equivalent tested pre-send guard before it can be
admitted to the live manifest.
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
`provider-live-staging` environment for staging runs and its
`provider-live-master` environment for master runs, with same-named
environment secrets and with `EDGAR_USER_AGENT` and (only after source confirmation)
`FINRA_OTC_SOURCE_KIND`, `FINRA_OTC_SYMBOL_DIRECTORY_URL`, and (for the documented ORF pair)
`FINRA_OTC_INACTIVE_SECURITY_MASTER_URL` environment variables. ORF additionally requires the
separate TRAQS credentials `FINRA_ORF_USERNAME` and `FINRA_ORF_REFRESH_TOKEN`; do not reuse
the FINRA Gateway client ID/secret for this file API. Put the reviewed non-secret safety settings
`ALPACA_REVIEWED_RESET`, `ALPACA_QUOTA_EVIDENCE`, `ALPACA_CORPORATE_ACTIONS_MAX_PAGES` (compatibility/fairness setting only), `EDGAR_REVIEWED_RESET`, `EDGAR_QUOTA_EVIDENCE`, `MASSIVE_MARKET_DATA_USE_AUTHORIZED`,
`MASSIVE_REVIEWED_RESET`, `MASSIVE_QUOTA_EVIDENCE`,
`MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE`, `MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE`,
`MASSIVE_MARKET_DATA_USE_REVIEWED_AT`, `MASSIVE_MARKET_DATA_USE_EXPIRES_AT`, `FINRA_ASYNC_MAX_RESULT_BYTES`, `FINRA_EQUITY_DATA_USE_AUTHORIZED`, `FINRA_EQUITY_DATA_USE_AUTHORITY_REFERENCE`, `FINRA_EQUITY_DATA_USE_AUTHORITY_SCOPE`, `FINRA_EQUITY_DATA_USE_REVIEWED_AT`, `FINRA_EQUITY_DATA_USE_EXPIRES_AT`, `FINRA_OTC_OPERATION_COSTS`,
`FINRA_OTC_SOURCE_REVIEWED`, `FINRA_OTC_SOURCE_EVIDENCE`,
`FINRA_OTC_REVIEWED_SOURCE_URL`, `FINRA_OTC_REVIEWED_INACTIVE_SOURCE_URL`,
`FINRA_OTC_TERMS_REVIEWED`, `FINRA_OTC_COMPLETENESS_REVIEWED`,
`FINRA_OTC_REDISTRIBUTION_REVIEWED`, `FINRA_OTC_POLL_INTERVAL_SECONDS`,
`FINRA_ORF_CUSIP_LICENSED`,
`FINRA_ORF_CUSIP_LICENSE_EVIDENCE`,
`TIINGO_OPERATION_BYTE_BOUNDS`, `TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET`,
`TIINGO_REVIEWED_HOURLY_RESET`, `TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE`,
`TIINGO_HOURLY_QUOTA_EVIDENCE`, `TIINGO_PROVIDER_ARCHIVE_TERMS_AUTHORIZED`,
`TIINGO_PROVIDER_ARCHIVE_TERMS_EVIDENCE`, `FMP_OPERATION_BYTE_BOUNDS`,
optional `FMP_REVIEWED_DAILY_RESET` (blank enforces a rolling 24-hour safety
window without asserting FMP's native reset), optional
`FMP_REVIEWED_BANDWIDTH_RESET`, `FMP_DAILY_QUOTA_EVIDENCE`,
`FMP_BANDWIDTH_QUOTA_EVIDENCE` (blank evidence overrides use the official
FMP pricing/FAQ sources for the selected plan; current account usage still
requires a separate durable dashboard/native baseline),
`FMP_PROVIDER_ARCHIVE_TERMS_AUTHORIZED`, `FMP_PROVIDER_ARCHIVE_TERMS_EVIDENCE`,
`PROVIDER_RATE_LIMIT_SEEDS`, `PROVIDER_FRESHNESS_SEEDS`,
`PROVIDER_USAGE_PROFILE_SEEDS`,
`MARKETDATA_APP_REVIEWED_PLAN`, `MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT`,
`MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT` for trial plans,
`MARKETSTACK_REVIEWED_MONTHLY_LIMIT` (defaults to the documented Free cap of
100; a different account plan requires `MARKETSTACK_QUOTA_EVIDENCE`), optional
`MARKETSTACK_REVIEWED_MONTHLY_RESET` (blank enforces rolling 30 days; a
provider-reviewed native boundary also requires quota evidence), and
`PROVIDER_FREE_ONLY_CHECKPOINT` (defaults true; denies paid and trial plans to
all callers during the integration checkpoint),
`PROVIDER_CHECKPOINT_OPERATION_HOLDS` (JSON provider-to-operation reason map;
the code default preserves every current checkpoint exclusion and is enforced
by normal resolver/executor paths before transport, independently of whether a
smaller call could fit current quota; service labels `bulk_fetch:*`,
`fetch_rfr_ohlcv`, and `reconcile_universe_page:*` are evaluated against their
canonical upstream operations without changing quota or evidence labels),
`ALLOW_PAID_PROVIDER_ROUTING` (defaults false; true permits only separately
reviewed paid plans only after checkpoint mode is deliberately disabled; it
does not satisfy aggregate cost admission or authorize paid activation),
and `MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS` in the same environment's
configuration variables. The SEC directory controls
`MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED`,
`MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_ISSUERS`,
`MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_EVENTS_PER_ISSUER`,
`MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_SUBMISSIONS_REQUESTS`, and
`MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ISSUER_MATERIALIZATION_MODE`, and
`MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_REVIEWED_CYCLE_COUNT` are also passed
through as non-secret variables. The workflow passes these controls
through without inventing entitlements. Configure each environment
independently; a GitHub variable never inherits the local `~/.config` setting.
The local MarketData.app account's configured Starter Trial/10,000-credit
entitlement expired at `2026-10-11T18:09:00+01:00`. Runtime configuration now
falls back to the Free Forever/100 daily-credit contract. The configured trial
label and expiry remain as history; they do not mean the trial quota is still
active. Do not copy that account's key or plan configuration into GitHub;
provision and review a separate CI account first.
The workflow's manual-dispatch `dinari_sandbox_canary` input is opt-in. When it
is enabled, the job runs only the Dinari Sandbox canary and reads
`DINARI_SANDBOX_CANARY_AUTHORIZED`,
`DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE`, and
`DINARI_SANDBOX_CANARY_MAX_REQUESTS` from that environment's configuration
variables; leaving the input off keeps the normal full-matrix behavior, where
Dinari remains blocked by its unpublished quota/entitlement gate.
In GitHub, leave the MarketData.app pair blank/zero, the option bound at zero,
and the SEC directory scan disabled with a zero submissions bound until that
environment has its own reviewed account/entitlement and scan controls. Keep
required reviewers enabled. Ordinary
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

On 2026-09-14, the operation-attributed current-head matrix collected 49 cases
and passed 43/49. The six honest outcomes were Alpha Vantage's three typed
free-key capacity responses plus missing `TRADIER_API_KEY`,
`IBKR_READ_ONLY_URL`/`IBKR_READ_ONLY_SESSION_COOKIE`, and
`ONDO_GLOBAL_MARKETS_API_KEY`. The owner-managed receipt run
`5e42d113-3e2a-4b81-a055-35109f365d73` recorded 26 provider rows, 97 HTTP
requests, 78 measured operations, and 23,159,806 response bytes; every row now
contains explicit operation keys (including the newly credentialed Alpaca,
EDGAR, MarketData.app, and Dinari reads). This remains transport and usage
evidence only; no provider entitlement, quota, legal, deployment, or routing
promotion is implied.

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
the configured account, not a promotion of FMP routing: the current official
pricing contract defines a 500 MB trailing-30-day bandwidth pool (the account
reports 512 MB, so the implementation retains the conservative
500,000,000-byte ceiling). FMP still requires a complete operator-reviewed
`FMP_OPERATION_BYTE_BOUNDS` map and current bandwidth entitlement evidence.
An older FAQ states 15:00 `America/New_York`, but newer official FMP limit
guidance says no single reset time should be promised and directs operators to
the dashboard. The seed preserves `provider_defined` as the native reset and
enforces a rolling 24-hour safety window; an account-reviewed native reset is
optional and can replace it. Current dashboard evidence and an initial usage
baseline remain required, as does the reviewed rolling-bandwidth evidence.
FMP's `FMP_REVIEWED_BANDWIDTH_RESET` remains only an optional override for a
future plan. In addition, the FMP Terms prohibit
copying/downloading content absent prior written approval, so persistent
archive rights are independently required. Analyst-estimate/price-target
endpoints remain outside this adapter until their plan entitlements are
separately validated.

The same day, the configured Massive key passed the bounded reference, IPO
calendar, and market-holiday live case. Search, one `reference/ipos` page, and
one `marketstatus/upcoming` response all produced valid transport/schema
evidence; the normalized results preserved IPO status/date and holiday
exchange/status/open/close fields and applied the requested windows. The
assertion intentionally allows a valid empty calendar window, so this proves
the integration contract without fabricating an IPO or holiday row; non-empty
rows are useful additional evidence but are not required for transport
correctness.

Historical note: a bounded run on 2026-09-05 returned a successful response
from the then-configured FINRA OTC candidate and exercised full pagination.
Subsequent review found that the current public FINRA catalog does not list
`otcSecurityMaster`. This old transport result is not source-availability,
completeness, or rights evidence and is not an instruction to repeat the call.
The live test now skips before network access unless source review and a
non-secret evidence reference are configured; a skip is not acceptance proof.

A later bounded rerun passed the other six keyless probes but received an honest
OpenFIGI HTTP 429 after additional anonymous traffic. After the documented
anonymous window reset, the bounded keyless matrix passed again; the
intermediate 429 remains recorded as rate-limit evidence, not hidden.

The historical standalone venue-disambiguated OpenFIGI probe passed `1/1`, but
that direct test predates the manifest's durable quota reservation and usage
ledger. It is not current acceptance evidence and must not be run as a
standalone live check. Use the manifest-backed runner instead:

```sh
PROVIDER_LIVE_USAGE_SCOPE=local-dev RUN_LIVE_PROVIDER_TESTS=1 \
  rtk uv run --project backend python scripts/run-live-provider-probes.py \
  --provider openfigi \
  --max-http-requests "${PROVIDER_LIVE_RUN_HTTP_LIMIT:?set reviewed cap}"
```

Earlier backend deterministic gate snapshot (not the current dirty candidate):

- complete backend unit gate: `2,333 passed`, `70.70%` line coverage, 37
  warnings, above the configured `55%` threshold; the direct workstream
  validator passed all 30 records. The Docker-backed PostgreSQL/Redis gate is
  still separately required and was not substituted by this unit result.
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

Historical bounded transport evidence exists for EDGAR, Alpaca, MarketData.app,
and the Dinari Sandbox pair. The latest exact-source Alpaca matrix passed its
native usage bootstrap plus six bounded data/metadata/event cases; ordinary
Alpaca routing now uses the documented 200/min pool with a conservative rolling
60-second safety envelope and native reset-header baseline. The latest SEC EDGAR
manifest preflight stopped before transport because
the reset boundary and current durable IP baseline are not yet reviewed. Tradier, Ondo, and
IBKR are intentionally deferred. Every deployment and CI environment must
still provide its own operator contact value.

The complete 37-case manifest rerun at 2026-09-11T17:43:45Z passed 33 cases.
The four honest outcomes were Alpha Vantage's documented 25-requests/day
capacity response for IPO-calendar and exact credential preflights for the
intentionally deferred Tradier, IBKR, and Ondo providers. Aggregate request and
response-byte telemetry was written outside Git; no credential or payload was
persisted.

Dinari Sandbox connectivity validation is available only through the explicit
`--dinari-sandbox-canary --provider dinari` runner mode. Because Dinari does not
publish a numeric Sandbox request quota/reset, this mode is restricted to one
read-only catalogue request per UTC day under a local application safety
policy, reserved in the shared durable quota ledger. This is not represented as
Dinari's provider quota and does not authorize recurring tests or application
routing. The runner requires `DINARI_SANDBOX_CANARY_AUTHORIZED=true`, a
non-secret `DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE`, and exactly
`DINARI_SANDBOX_CANARY_MAX_REQUESTS=1`. It disables retries for this test. The
process cap consumes one slot per attempted HTTP request (including failures)
as an additional backstop, and the runner's exclusive live-run lock prevents
concurrent local canaries. The test records only
redacted request/byte observations, while every captured successful or failed
response body is retained in the owner-private raw-response archive under the
owner's explicit persistent-storage authorization. Payloads remain isolated
from canonical production market-data tables. The receipt is marked
`canary_mode=dinari_sandbox`. These controls do not infer Dinari's entitlement,
and ordinary routing remains fail-closed.

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
`FMP_OPERATION_BYTE_BOUNDS` JSON maps. FMP additionally requires current
call/bandwidth usage evidence and a verified initial quota baseline; current
first-party guidance does not promise a universal reset time, so its 250/day
pool is protected by a rolling 24-hour safety envelope unless the exact
account reset is reviewed. A previously cited FAQ's 15:00
`America/New_York` statement is not a safe default for every account. Both
providers also require explicit written archive rights:
Tiingo's Starter/Trial plan forbids durable storage and its ordinary Paid Plan
requires deletion at plan end, while FMP requires prior written approval to
copy/download content. The `*_PROVIDER_ARCHIVE_TERMS_*` values record a provider-
side exception, not owner storage permission (which is already granted).
Ordinary plan terms or operator belief are insufficient. The documented
rolling-30-day bandwidth boundary is used by default and may be replaced only
by an explicit reviewed override.
Tiingo's exact distinct-symbol and hourly ceilings use provider-scoped rolling
31-day and one-hour application safety envelopes by default. The
`TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET` / `TIINGO_REVIEWED_HOURLY_RESET` values
and independent evidence fields remain optional native-reset overrides; no
generic cross-provider limiter is used.
When all controls are present, the runtime reserves the documented bandwidth
pool before execution and settles it to measured response bytes; incomplete or
invalid maps or reset controls remain fail-closed.
EODHD's Free-plan pricing table says 20 HTTP requests/minute; its API-limits
page conflicts by saying 1,000/minute on every plan. The runtime conservatively
caps this Free key at 20 requests per rolling 60-second window until a live
account-native header resolves the conflict, and accounts weighted daily
credits independently (20/day, midnight GMT). The native `/api/user` endpoint
costs zero daily credits, reports the active daily limit/date, and successful
responses carry the current per-key minute limit/remaining headers. If its lazy
daily counter still reports a prior date, that is evidence of zero charged
usage in the current GMT day; the prior-day amount is retained separately as
`calls_per_day_last_active`. Minute headers seed usage only when the active
native limit is at least the local cap and observed usage fits within that cap;
they never widen the policy automatically. EOD/profile access remains
entitlement-gated independently of quota. `EODHD_REVIEWED_MINUTE_*` settings
are reserved for explicit account-specific overrides backed by exact reset and
quota evidence. Sources: [Free-plan pricing](https://eodhd.com/pricing) and
[API limits](https://eodhd.com/financial-apis/api-limits).
The exact current-source account probes on 2026-09-16 passed for Twelve Data
and EODHD. Twelve Data reconciled its native 8-credit minute pool after one
`/api_usage` request, while its documented 800-credit UTC-day pool remained
unreconciled because the endpoint exposes no cumulative daily counter. EODHD's
`/user` response was also valid, but its reported usage date was stale; the
daily baseline therefore remained observation-only and no reset was invented.
Per-dimension operation maps follow the same fail-closed rule: an explicitly
empty map is a reviewed zero-cost exclusion for that dimension (for example, a
synchronous FINRA read against the separate asynchronous-dataset pool), while
a non-empty map that omits an operation is unreviewed. The manifest runner may
add a positive, operation-specific reservation bound only for a bounded live
case whose adapter estimator is already reviewed; that bound is not a runtime
default and does not widen provider routing for arbitrary ranges.
The usage summary derives `window_ends_at` from each policy's explicit calendar
reset (including Eastern-time month/day and 09:30 ET boundaries), rather than
adding a nominal 31-day duration. Fixed and rolling windows retain their
duration semantics, so active-window diagnostics expire at the same boundary
used by admission across short months and daylight-saving transitions.
Tiingo's documented pool magnitudes are retained. Its general API
documentation states that daily requests reset at midnight EST and monthly
bandwidth resets on the first day of each month at midnight EST; the source
does not define the distinct-symbol monthly reset anchor or an hourly
timezone/boundary. Those two dimensions retain their provider-defined labels
for audit but use explicit provider-scoped rolling 31-day and one-hour safety
envelopes by default; the durable `provider_quota_identity` ledger therefore
does not invent a cross-provider limit. FINRA's public-credential byte pool
retains its provider-defined monthly label for audit but uses a conservative
provider-scoped rolling 31-day safety envelope; the durable byte ledger still
requires a current baseline before admission. FINRA's synchronous short-interest and OTC
Daily List calls reserve a maximum 3,000,000 response bytes (the conservative
decimal interpretation of FINRA's ambiguous 3 MB ceiling) against the public
credential's published 10 GB monthly pool. FINRA says an exhausted public
credential is disabled until the first day of the following month, but does not
publish the reset timezone or byte convention, so the runtime records a
provider-defined reset, preserves the conservative rolling 31-day safety
envelope, and still requires a current baseline; measured bytes settle the
reservation. FINRA also publishes 20 asynchronous requests per minute per
dataset/API account and a 100,000-record maximum per asynchronous request. Its
asynchronous submit/poll/presigned-download path is implemented as a
documentation-faithful direct adapter. A positive
`FINRA_ASYNC_MAX_RESULT_BYTES` promotes the signed download operation into the
durable rolling-window byte reservation; the default `0` remains non-routable
because there is not yet a durable, quota-aware partition and recovery job for
potentially large results. Every byte yielded by the stream—including the
chunk that crosses a configured bound or bytes received before a transport
failure—is retained as base64 response evidence with a SHA-256 digest in the
durable provider request log when the call runs through the provider runtime.
The result remains incomplete and non-routable until a durable, quota-aware
partition/recovery job is implemented; preserving a partial body does not
claim that the full dataset was obtained.
FINRA short-interest and Daily List do not require a per-provider owner-storage
approval. The owner's private-retention permission is final. Access still
depends on the configured FINRA API credentials and quota baseline. OTC full-
universe snapshots are a different source: they need the documented ORF active
and inactive files, separate TRAQS access, and source-specific terms evidence.

FRED v1 records the official 120-requests/minute threshold but remains non-routable
until reviewed quota-scope evidence, provider-terms evidence for automated use,
a compliant application-user/API-key boundary, and rights evidence for each
series are supplied. The owner's private-retention permission is final and is
not a missing gate. The server-key implementation
accepts only `FRED_APPLICATION_USER_SCOPE=owner_personal_only` with a non-empty
`FRED_APPLICATION_USER_SCOPE_EVIDENCE`; it cannot serve multiple app users with
one shared FRED key. Multi-user support also requires the FRED terms link and
user agreement/privacy disclosures in the application, outside this
backend-only branch's scope.
Controls include `FRED_REVIEWED_LIMIT_SCOPE`,
`FRED_REVIEWED_REQUESTS_PER_MINUTE` (1..120),
`FRED_REVIEWED_QUOTA_EVIDENCE`, `FRED_REVIEWED_RESET`, and
`FRED_RESET_EVIDENCE`. FRED v1 does not publish the reset boundary, so the
reset label and its current provider/account evidence are independent required
controls; `rolling` is not assumed from the 120/minute headline.
`FRED_AUTOMATED_USE_AUTHORIZED=true`,
`FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE`, and the per-series
`FRED_SERIES_RIGHTS_EVIDENCE` JSON map. The old boolean terms-review control
is not accepted as permission. Until all applicable controls are satisfied,
the FRED live case checks the policy gate without making an API request and is
not external live evidence. Coinbase's 10 public requests/second rate limit
does not establish legal permission: its live case also makes no request until
written authority covers automated/AI use and persistent, non-redistributing
use; the configured evidence fields are
`COINBASE_MARKET_DATA_USE_AUTHORIZED`,
`COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE`,
`COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE=internal_ai_automated_persistent_nonredistributed`, and
`COINBASE_MARKET_DATA_USE_REVIEWED_AT` (plus the optional
`COINBASE_MARKET_DATA_USE_EXPIRES_AT`). Nasdaq Trader publishes no numeric
polling allowance; the runtime instead enforces a client-imposed cap of two
conditional file requests per calendar day, not a claim about Nasdaq's quota.
IBKR
now has a concrete read-only Client Portal Gateway adapter for security search,
raw historical equity/futures bars, and latest-price snapshots. The gateway
login remains interactive and session-bound; no options capability is claimed,
and raw bars are never labeled as adjusted. The generic futures path uses the
provider `conid`; configure `IBKR_CONID_MAP` when symbol search is ambiguous,
and observe IBKR's two-year post-expiry futures-history limit. Live evidence
still requires an operator-owned `IBKR_READ_ONLY_URL` and
`IBKR_READ_ONLY_SESSION_COOKIE`.

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
permission to guess a ticker or a quota. Kraken's current xStocks availability
guidance states that EEA clients cannot access xStocks order-book trading
through Kraken API. The 2026-10-09 Portugal-hosted empty catalogue is consistent
with that limitation, but does not prove whether a separate read-only or
partner route exists. The live acceptance runner therefore requires measured
asset and price HTTP evidence and keeps Kraken xStocks incomplete when discovery
returns no assets. See [Kraken's availability guidance](https://support.kraken.com/articles/xstocks-availability).

**Superseding live evidence (2026-10-10):** the earlier empty response used
the unfiltered currency catalogue. Kraken's xStocks examples show that
`AssetPairs` needs `aclass_base=tokenized_asset`, while the API changelog says
`Ticker` needs `asset_class=tokenized_asset`. With both filters, discovery
returned xStocks from the Portugal-hosted test. The adapter now deduplicates
internal pair aliases by provider `altname` without dropping their raw keys,
and the bounded exact-candidate live case passed discovery, asset lookup, and
ticker in three requests (`351,983` response bytes; run
`766ca0ef-add2-4e9c-b4b0-9f5f33e88b7b`; candidate tree
`799c62853a20b19c7970cc0117d761b1c116eeba`). It proves one current market's
read-only endpoints, not full token catalogue reconciliation, regional trading
entitlement, or the all-provider acceptance gate. Kraken references:
[API changelog](https://docs-legacy.kraken.com/api/docs/change-log/),
[xStocks SDK example](https://python-kraken-sdk.readthedocs.io/en/stable/03_examples/rest_examples/xstocks_rest_examples.html).

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

Historical operation-gap snapshot (2026-09-10): an earlier checkout listed
FINRA asynchronous submit/poll/download; Massive search/discovery and
IPO/calendar continuation; Alpha Vantage search/quote/discovery; Marketstack
discovery; Tiingo search; Twelve Data search/quote/discovery; EODHD/FMP
discovery; Binance/Kraken full-range, quote, and discovery; Coinbase's
full-range/quote/discovery; and direct tokenized metadata as unresolved. That
list is retained only as provenance. It is not a current claim: subsequent
manifest and adapter work changed several entries, and a prose list must not
override the exact source checkout.

Current-source inventory checkpoint (2026-09-16): the authoritative operation
surface is the combination of `LIVE_REQUIRED_OPERATIONS`,
`LIVE_OPERATION_DISPOSITIONS`, explicit method aliases, service-operation
aliases, and the manifest in `scripts/run-live-provider-probes.py`. The pure
`provider_method_inventory_errors()`/`live_matrix_inventory_errors()` checks
fail closed when a public concrete provider method is absent from the required
manifest, a reviewed alias, a local-only exclusion, or an explicit
disposition. Current aliases include `fetch_latest_ohlcv` -> `fetch_ohlcv` and
the bounded service paths `fetch_rfr_ohlcv`, `bulk_fetch`, and
`reconcile_universe_page`; these aliases provide accounting/coverage
classification, not additional endpoint evidence. The runner also emits
these maps and all current dispositions in the redacted evidence object.

The runner's current preflight output, not this document, is the source of
truth for unresolved capability coverage. In particular, an empty disposition
map for a provider means that no unresolved disposition is recorded for the
methods represented by its manifest/aliases; it does not by itself prove
complete universe, history-depth, or entitlement coverage. Before claiming a
capability-exhaustive run, execute the exact current-source manifest and
resolve every `deferred`/`blocked` disposition that the preflight reports.
Expected entitlement denials, intentional no-request policy blocks, and
explicit user deferrals remain visible in receipts but are typed separately
from unresolved live coverage. Focused provider runs may collect transport
evidence, but they cannot override an unresolved full-matrix disposition.

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
The provider's pricing page states 100 requests/month. Its FAQ contains a
contradictory 1,000-request answer but elsewhere says the Free plan serves
accounts below 100; the contact FAQ repeats 100 and documents per-symbol
charging. The contract retains that conflict while capping the Free plan at
100 requests in any rolling 30 days. A plan-specific limit can be configured
through `MARKETSTACK_REVIEWED_MONTHLY_LIMIT` with quota evidence; the optional
`MARKETSTACK_REVIEWED_MONTHLY_RESET` uses a provider-reviewed native boundary,
otherwise the stricter rolling safety applies. This resolves quota admission
without resolving the inconsistent FAQ text. Data/archive rights and the
exchange-wide listing-page cost remain separate gates.

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
`FRED_REVIEWED_REQUESTS_PER_MINUTE`, `FRED_REVIEWED_RESET`, and the associated
quota/storage/automated-use/series-rights evidence) rather
than an opaque generic blocker. FINRA asynchronous result bytes, Nasdaq polling,
xStocks quota/legal eligibility, Bybit endpoint/UID state, and Tiingo/FMP
operation byte maps remain non-routable because their reviewed controls are not
configured.

The wrapper also reports the remaining provider-specific admission gates
explicitly: Coinbase's written-use authority, FRED's v1 limit scope/adjustable-
limit/storage/automation/per-series-rights review, Nasdaq Trader's unpublished
vendor quota (bounded locally by two file requests per calendar day), xStocks' unpublished public
quota plus its official US-person/jurisdiction/redistribution restriction,
and Bybit's endpoint/UID header state. A positive live read for any of these
providers is therefore not treated as routing admission.

The MarketData.app adapter was also checked against the current official API
root during this checkpoint: versioned resources are under
`https://api.marketdata.app/v1` (not `/api/v1`). At the user's direction, count
the 30-day trial from 2026-09-11 18:09 Europe/Lisbon. The
per-provider configuration therefore uses the 10,000-credit daily Starter
Trial allowance until the explicit expiry `2026-10-11T18:09:00+01:00`, then
falls back to the Free Forever 100/day allowance; an operator can revise plan,
limit, and expiry for a later upgrade. The reset is 09:30 America/New_York and
the account-wide concurrent ceiling is 50. The adapter path, Bearer-auth
shape, and durable release-only in-flight reservation are fixture/unit tested.
A credentialed live read passed on 2026-09-11; this historical evidence does
not verify the current source tree or prove remaining account/legal gates.

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

The current OpenFIGI contract is environment-specific and must not be
collapsed into one generic request rate. With no API key, the mapping endpoint
allows 25 requests/minute and five jobs/request, scoped to anonymous traffic;
with `OPENFIGI_API_KEY`, it allows 25 requests/6 seconds and 100 jobs/request,
scoped to the key. The runtime selects the matching contract, and the adapter
preserves the provider's `ratelimit-limit`, `ratelimit-remaining`, and
`ratelimit-reset` headers, including typed retry timing on HTTP 429. Focused
coverage now includes the native account-usage parser and dynamic baseline
reconciliation; the manifest's keyless account-usage case consumes one mapping
request and must be run through the durable live runner, not standalone.

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

The superseding bounded credentialed rerun on 2026-09-12 passed all `10/10`
selected provider tests after the Dinari UUID miss-safety correction: SEC EDGAR
profile, filing/facts, and complete ticker/exchange-directory pagination passed
`3/3` (5 operations, 6 HTTP requests); Alpaca paper daily/intraday/latest/assets
and corporate-action transport passed `4/4` (5 operations, 5 HTTP requests);
MarketData.app option and five-minute history passed `2/2` (4 operations, 4
HTTP requests); and Dinari Sandbox metadata, fair price, quote, all four
documented history windows, news, dividends, and splits passed `1/1` (12
operations, 23 HTTP requests). The network-enabled receipt was merged into the
owner-managed ledger with `accepted=4`, `duplicates=0`, `rejected=0`; the
earlier sandbox-DNS attempt recorded zero requests and was not merged. This is
positive transport/schema evidence only: no provider quota, account-plan,
commercial, redistribution, or response-dependent routing gate was promoted.

The same operator environment also passed the bounded MarketData.app account
introspection probe (`test_marketdata_app_credentialed_account_usage_snapshot`,
`1/1`). It called the unversioned `/user/` endpoint and validated the native
credit limit, remaining balance, per-request charge, reset timestamp, and
options-data entitlement. The provider returned a 10,000-credit daily header;
this is retained as observational evidence only. The reviewed
`MARKETDATA_APP_REVIEWED_PLAN`/`MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT`
pair and response-priced option-chain bound remain required before routing.
Accepted reviewed plan identifiers are `free_forever`, `starter_trial`,
`trader_trial`, `starter`, and `trader`; trial identifiers remain explicitly
time-limited and are not silently treated as perpetual paid plans. A trial
also requires `MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT` to be a future,
timezone-aware ISO-8601 value. Missing or naive trial expiries remain
non-routable. An elapsed but valid trial expiry is not an error: runtime quota
and entitlement automatically fall back to Free Forever at 100 credits/day.
The old implementation incorrectly excluded `/user/` from daily credits. The
official rate-limit rules say each successful 200/203 response consumes at
least one credit, and the official Go SDK describes `CreditsConsumed` as the
charge for the `/user/` request itself. The current policy counts one credit
after a baseline exists and uses an explicit provider-native bootstrap mapping
for the first bounded snapshot; the returned post-request counters establish
the exact daily pool. The older zero-credit settlement below is historical
evidence for the superseded policy and does not validate current quota safety.

The corrected current dirty-worktree bounded rerun on 2026-09-16 passed 7/7
MarketData.app cases (9 upstream requests, 17,241 response bytes), including
the `/user/` snapshot. Its reservation-linked receipt shows the account-usage
call held only the concurrency lease and settled zero daily-credit units. The
receipt is intentionally `not_current_source` until the implementation is
committed and revalidated at the exact candidate SHA; it is transport and
quota-settlement evidence, not promotion evidence.

Historical option quotes remain response-priced, not freely/unboundedly
routable. The live test exercises exactly one OCC contract over an explicit
three-inclusive-calendar-date window; its date-range estimator reserves one
daily credit before HTTP. The no-bound case is a deliberate zero-request
regression. The official [Option Quotes pricing contract](https://www.marketdata.app/docs/api/options/quotes/)
prices historical responses at one credit per 1,000 quotes. The safety status
therefore describes unbounded calls as non-routable while allowing a caller
with a reviewed range-derived per-call bound; it does not mean all bounded
historical quote validation is prohibited.

On 2026-09-13, the complete lock-protected matrix was rerun against the
existing owner-managed environment with the external usage ledger enabled. It
collected 47 cases and passed 41. The three Alpha Vantage event/earnings cases
returned the provider's typed documented 25-requests/day capacity response;
the exact intentional credential preflights for Tradier, IBKR, and Ondo also
failed because those credentials remain absent. All other configured and
keyless/tokenized cases produced positive bounded transport evidence. The
runner returned exit code 2 and made no acceptance claim; the aggregate receipt
remains outside Git and no credentials or response payloads were persisted.

On 2026-09-13, the Dinari Sandbox adapter was revalidated after isolating
intermittent HTTP 500 responses during the compound live case. The previous
implementation re-enumerated the full Stock catalogue for every UUID-based
price, quote, history, news, dividend, and split read. It now retains validated
Stock metadata only within the current provider instance, while new instances
still perform fresh metadata resolution. Dinari reads additionally use a
provider-specific bounded recovery of at most two short-backoff retries for
HTTP 500; 4xx/rate-limit failures and all other providers remain typed and
fail-fast. Tokenized unit coverage passed `72/72`, including persistent-500
retry exhaustion; the focused provider/registry/quota/secret slice passed
`197/197`, and the real Dinari
Sandbox compound case passed `1/1`. The complete matrix then passed `41/47`:
the three Alpha Vantage event/earnings operations returned typed documented
capacity responses, while Tradier, IBKR, and Ondo remained exact credential
preflights. The run returned exit code 2 and made no acceptance claim; no
credentials or payloads were persisted.

On 2026-09-13, the Dinari recovery boundary was tightened after review of the
observed failure surface: the two-attempt HTTP 500 recovery is now selected
only for hosts ending in `.sandbox.dinari.com`, while the documented
production host remains fail-fast until production evidence justifies a
different policy. The production-host regression passed with exactly one
request and preserved the typed 500 response. Tokenized unit coverage passed
`73/73`; the focused provider/registry/quota/secret slice passed `198/198`;
the complete backend unit suite passed `2,043/2,043`; the isolated PostgreSQL
integration suite passed `383/383`; and the authoritative combined backend
gate passed `2,426/2,426` at `81.44%` coverage with 89 warnings using cleaned
testcontainer session `ea357249-d45b-488e-97cf-302ccdfcb7c3`. No provider
calls, credentials, or response payloads were persisted. The live matrix and
all provider/legal, CI/deployment, reconciliation, migration, and shadow
gates remain unchanged and non-accepted.

On 2026-09-13, the current-source lock-protected matrix was rerun after the
Dinari host-scoped retry change. It collected 47 cases and passed 41. The
three Alpha Vantage event/earnings cases returned typed documented capacity
responses; Tradier, IBKR, and Ondo remained exact missing-credential
preflights. The routing safety preflight continued to enumerate the specific
unreviewed controls for Alpaca corporate actions, FINRA async/OTC, FRED,
Nasdaq, xStocks, Bybit, Marketstack discovery, MarketData.app, Tiingo, and
FMP. Exit code 2 is intentional for this incomplete matrix and no acceptance
claim was made; aggregate usage remained outside Git and no credentials or
payloads were persisted.

On 2026-09-13, the same 47-case matrix was rerun with the configured Alpaca
paper, MarketData.app, Dinari Sandbox, and other owner-managed credentials
from an escalated network-enabled environment. It again produced `41` positive
bounded transport observations. The only six non-passes were the three
Alpha Vantage capacity responses (the supplied free key was already at its
documented 25-requests/day / one-request-per-second capacity), and the exact
intentional missing-credential preflights for Tradier, IBKR, and Ondo. The
runner still returned exit code `2` because this is not a complete acceptance
matrix; the safety preflight continued to keep all unreviewed quota, legal,
redistribution, and response-dependent controls non-routable. Only aggregate
usage was written to the operator-owned external ledger; no credentials or
response payloads entered Git.

On 2026-09-13, after the provider-platform migration graph repair, the current
source checkpoint `db3c0eda5` was exercised again under the external live-use
lock. The manifest collected 47 cases and passed 41. Alpha Vantage's IPO and
earnings reads returned its typed documented free-key capacity response; the
intentional Tradier, IBKR, and Ondo credential preflights remained exact. The
routing safety preflight continued to list only the provider-specific controls
that are deliberately unreviewed. Aggregate usage was written to the operator
ledger outside Git; this run is current transport evidence, not an acceptance
or routing-entitlement claim.

On 2026-09-13, a separate network-enabled focused run exercised only the newly
configured providers and passed `11/11`: Alpaca daily/intraday/latest/assets
and corporate actions; SEC EDGAR filings, Company Facts, and complete
ticker/issuer directory pagination; MarketData.app option surface, account
usage, and intraday history; and Dinari Sandbox metadata, price/quote,
DAY/WEEK/MONTH/YEAR aggregates, news, dividends, splits, and corporate actions.
The aggregate receipt was written to the owner-managed temporary ledger
`/private/tmp/charting-provider-live-usage-new-providers-20260913.jsonl` only;
no credentials or response payloads entered Git. This is transport/schema
evidence and does not promote any unreviewed quota, account-plan, commercial,
redistribution, or response-dependent routing control.

On 2026-09-13, the current tokenized-issuer-identity checkpoint was revalidated
with network access and the owner-managed credentials. The bounded selection
passed `13/13`: SEC EDGAR profile, filings/Company Facts, and complete
ticker/issuer directory pagination; Alpaca daily/intraday/latest/assets and
corporate actions; MarketData.app options, account usage, and intraday history;
and Dinari Sandbox metadata, price/quote, DAY/WEEK/MONTH/YEAR history, news,
dividends, splits, and corporate actions. The redacted receipt contained 8
provider rows, 33 upstream requests, and 13,092,191 response bytes in
`/private/tmp` only; no credentials or payloads entered Git. This confirms
current transport/schema behavior, not provider quota, commercial,
redistribution, or routing entitlement.
On 2026-09-13, the complete available-provider matrix was rerun against the
current checkout with the owner-managed environment and a temporary redacted
usage ledger. It collected 44 executable cases (the intentionally deferred
Tradier, IBKR, and Ondo cases were excluded from this bounded run) and passed
`41/44`. All public
crypto and tokenized probes, SEC EDGAR, Alpaca, Massive, CoinGecko, FRED,
FINRA/OTC, Tiingo, Twelve Data, Marketstack, EODHD, FMP, MarketData.app, and
Finnhub cases passed. The three non-passes were Alpha Vantage's typed provider
capacity responses for IPO-calendar and earnings-calendar/history calls after
the shared free key had reached its documented daily allowance. This is
provider-quota evidence, not a transport/schema acceptance claim for those
three operations. The temporary receipt contained 26 aggregate provider rows,
94 upstream requests, 23,311,979 response bytes, and no credentials or
payloads; it remained outside Git. The repository merger accepted all 26 rows
into the mode-0600 owner-managed ledger, preserving this usage evidence across
future sessions without copying secrets or raw responses.

On 2026-09-13, the configured Massive key also passed a bounded reference,
IPO-calendar, market-holiday, and adjusted daily aggregate-bars read. The
aggregate adapter exercised the documented custom-bars transport and returned
validated split-adjusted OHLCV rows; the redacted receipt contained four
upstream requests and 442,597 response bytes with no credentials or payloads.
Focused Massive/provider coverage passed `223/223`, and the receipt merger
accepted one provider row into the mode-0600 owner-managed ledger. This is
transport/schema evidence only: Stocks Basic's five-call/minute, two-year
history, and redistribution terms still keep Massive historical routing
opt-in pending operator review.

The authoritative Docker-backed combined backend gate then passed `2,460/2,460`
at `81.68%` combined coverage with 89 warnings in 410.51 seconds. Isolated
testcontainer session `6fc6e49e-17de-479b-b4f2-b395fb6cabe6` was cleaned without
host-wide pruning. No frontend or ETF-provider adapter files changed.

The Massive live case was then expanded to cover both a split-adjusted daily
range and a raw five-minute intraday range. It passed with five upstream
requests and 447,607 response bytes; the redacted receipt merger accepted one
provider row. This is still bounded transport/schema evidence and does not
promote Massive's free-plan history or redistribution entitlement.

On 2026-09-13, the rotated Dinari Sandbox credentials were revalidated with a
focused identity assertion. The compound case passed `1/1` (12 operations,
14 upstream requests): the provider-native Stock UUID parsed as a UUID and the
catalogue record exposed at least one stable economic-underlying identifier
(the live AAPL row exposed composite FIGI and CIK). The redacted receipt was
accepted into the owner-managed ledger with `accepted=1`, `duplicates=0`,
`rejected=0`. This strengthens token-to-issuer reconciliation evidence only;
Dinari commercial, quota, historical-aggregate, and redistribution reviews
remain required before routing admission.

On 2026-09-13, the Massive live case was expanded to exercise the official
single-ticker overview in addition to search, IPO, holiday, split-adjusted D1,
and raw M5 reads. It passed `1/1` with six upstream requests and 448,964
response bytes; the metadata response carried a matching AAPL symbol and
stable identifier fields. The redacted receipt merger accepted one row into
the owner-managed ledger. This is bounded transport/schema evidence only and
does not promote Massive history or redistribution terms.

The authoritative Docker-backed combined backend gate after this metadata
change passed `2,464/2,464` at `81.68%` coverage with 89 warnings in 507.76
seconds, using isolated testcontainer session
`e92d7385-12e1-4379-a92f-167ce5abe08c`. Cleanup removed only that workstream's
containers; no frontend or ETF-provider adapter files changed.

On 2026-09-13, the bounded credentialed live suite was refreshed against
current source checkpoint `750f02d57` for the newly configured providers. All
`11/11` selected test bodies passed: Alpaca history/intraday/latest/assets and
corporate actions; SEC EDGAR filings, Company Facts, and complete
ticker/issuer directory pagination; MarketData.app options, account usage,
and intraday history; and Dinari Sandbox metadata, price/quote,
DAY/WEEK/MONTH/YEAR history, news, dividends, splits, and corporate actions.
The redacted receipt recorded 5 Alpaca HTTP requests and 6,487,828 bytes, 6
EDGAR requests and 6,236,111 bytes, 5 MarketData.app requests and 20,561
bytes, and 14 Dinari requests and 182,346 bytes. The aggregate receipt was
accepted into the mode-0600 owner-managed ledger with `accepted=4`; no
credentials or provider payloads entered Git. This remains transport/schema
evidence only and does not promote any unreviewed quota, account-plan,
commercial, redistribution, or response-dependent routing control.

On 2026-09-16, the current-source MarketData.app focused matrix was rerun
against the configured Starter Trial account and the durable local coordinator.
The first run exposed a real adapter defect: `get_current_price` reused a
one-day candle window and returned `None` when the delayed candle surface had
no observation for the current date. The adapter now uses the documented
`/v1/stocks/quotes/{symbol}/` endpoint, validates its parallel arrays without
truncation, and falls back from last trade to midpoint/bid/ask only when those
provider fields are present. The corrected rerun passed `7/7` cases (account
usage, daily and five-minute candles, option expirations/chain, bounded
historical option quotes, the deliberate no-request guard, and latest price).
The receipt is exact committed provider-source evidence for
`2f6e7384a57eafa9c284c88880d18f402a2c261e`; the later `d59819476` commit only
records the receipt and handoff. The Starter Trial `10,000/day` plan and its
configured expiry remain the authoritative local quota contract.

On 2026-09-16, the explicit Dinari Sandbox canary was run with transient
owner controls and a per-process request cap of `20`. Its compound manifest
case passed `1/1` with `14` upstream requests and `180,169` response bytes,
covering catalogue/identity, price, quote, DAY/WEEK/MONTH/YEAR aggregate
history, news, dividends, splits, and corporate actions. A preceding
zero-request preflight stopped before transport when those owner controls
were absent. No sandbox payload was persisted to canonical data and no
authorization control was stored in Git. This is isolated Sandbox
transport/schema evidence only; Dinari's numeric quota/reset, commercial
terms, redistribution rights, and production routing remain non-routable.

## 2026-10-04 Massive current-contract audit

The current first-party [Basic-access FAQ](https://massive.com/knowledge-base/article/how-quickly-can-i-access-massives-market-date)
states that reference data, corporate actions, and minute aggregates are
available on Basic, at five requests per minute per asset class. All stock
adapter operations now share the Stocks bucket. The exact provider reset
boundary and native active-use counter remain undocumented; the client uses a
rolling 60-second safety envelope without claiming that this is Massive's
native reset rule. When Massive returns 429 without a usable provider
retry/reset header, the provider is held for 60 seconds as recovery behavior;
this is not represented as a provider reset contract.

Current [Market Data Terms](https://massive.com/legal/market-data-terms-of-service)
(updated 2025-08-28) give Individual subscribers personal/non-business display
use, prohibit copying and non-display use absent express prior written
consent, and require deletion of all market data if the account is terminated,
restricted, or suspended. Massive's current [app-use guidance](https://massive.com/knowledge-base/article/which-plan-do-i-need-to-show-massive-data-in-my-app)
also requires a Business subscription when any other person can see the data,
including internal staging users and testers. These are recorded provider-term
facts, not a missing owner-approval gate: the owner has explicitly authorized
private automated use and durable retention for this single-user research app,
including where a provider's terms would otherwise require separate written
permission. Do not make Massive non-routable or request another owner approval
on that basis. Authentication, actual plan entitlements, and the provider's
documented request quota remain independent controls.

The 2026-10-04 audit itself made no Massive request. Its then-current
`2,858/2,858` Docker-backed test result and `0/0` full-matrix preflight were
historical and did not establish live Massive behavior. The owner's later
explicit private-retention decision supersedes the archive-rights hold recorded
at that time.

## 2026-10-06 continuation: OpenFIGI, ORF, SEC, and full-gate status

OpenFIGI's selected keyless live suite passed `3/3` (mapping, profile
resolution, and native usage snapshot), with three HTTP requests and 93,567
response bytes. The receipt is `not_current_source` because this worktree is
dirty, so it is transport/schema evidence, not acceptance of the current tree.
No Alpha Vantage or FINRA request was made during this continuation.

FINRA ORF's focused fixture suite passed `32/32`; its `2026-10-06T18:37:41Z`
preflight stopped before transport (`0` provider requests) because the ORF
source selector, inactive-file URL, assigned TRAQS username, refresh token,
and durable token-state path are not configured. Reviewed terms/use, file-pair
coverage, operation costs, and polling controls also remain required and must
be grounded in FINRA's written answer, not inferred. The existing FINRA
Gateway key does not substitute for TRAQS access.

The SEC EDGAR-only preflight at approximately `18:39Z` also stopped before
transport. Its 10-requests/second provider ceiling is documented, but the
shared IP-scope one-second usage baseline is unknown across seven live
operations; no request was sent to try to establish that baseline.

The previously implicated mocked Regan adapter test passed in isolation
(`1/1`, `2.77s`), so its former hang did not reproduce in that bounded rerun.
This does not clear the full unit/integration gate, whose latest result remains
incomplete (exit `152`). The current host has active containers from the
parallel ETF and other worktrees and about `2.4 GiB` available memory; no new
Docker-backed full gate was launched. GitHub secret-store verification also
remains open because the GitHub CLI is unavailable in this environment.

The local MarketData.app trial boundary is present only in the private shared
env file (`0600`), using the owner's key-email timestamp plus 30 days in
Europe/Lisbon: `2026-10-11T18:09:00+01:00`. App-config parsing selects the
reviewed Starter Trial pool (`10,000` credits/day) and automatically falls
back to Free Forever (`100`/day) once the timestamp elapses. The focused
MarketData.app preflight at `2026-10-06T18:41:48Z` recognized the account plan
and sent zero requests, but correctly remains blocked from live data until
MarketData.app's subscription-end deletion term is covered by a provider
exception. No credentials were added to Git.

## 2026-10-06 continuation: ORF access and backend coverage retry

The owner's permission for private durable storage from every provider is
final; it is not an open approval item. FINRA ORF is implemented and its
offline adapter/authentication fixtures passed `32/32` in this continuation.
Live ORF still requires actual TRAQS product access: an assigned TRAQS
username, MFA-enabled account, and the separate programmatic refresh token.
The FINRA Gateway OAuth credentials do not serve this purpose. Keep the token
private; configure it locally after access is provisioned. Even after access,
ORF's ORF-specific security master must not be described as complete coverage
of all US OTC securities/venues without reconciliation evidence.

The owner reports no external Alpha Vantage use in the preceding 24 hours.
The app ledger records its own `24/25` daily requests, latest at
`2026-10-06T17:23:55Z`; no Alpha Vantage calls were made in this continuation.
This leaves no safe unreserved capacity in the app ledger until the existing
window resets or the provider account meter is reconciled.

Retried the combined Docker-backed backend gate with Docker permission and an
isolated temporary quota-ledger directory. Docker readiness passed; pytest
reached approximately 72% and exited `152` without a summary or test count,
and the Make target returned `2`. Its scoped cleanup removed only the two
testcontainers for this worktree; no host-wide prune occurred. This is
inconclusive and does not pass the full backend acceptance gate. No external
provider requests were made.

## 2026-10-06 continuation: ORF readiness recheck

The FINRA ORF directory and OAuth fixture suites passed `70/70` together;
workstream validation passed. A focused live preflight at `19:59Z` stopped
before transport (`0` provider requests). It requires the ORF source selector,
inactive-file URL, separate TRAQS username and refresh token, plus its private
token-state file. A writable durable quota ledger is also required before any
live attempt. The ORF-specific cost map, source/use agreement, download quota
and reset scope, retention answer, completeness/venue scope, and explicit
source evidence remain unverified. The owner reports no other Alpha Vantage
use in the prior 24 hours, but the app's own ledger still records `24/25`
requests through `2026-10-06T17:23:55Z`; no new Alpha Vantage request was made.

## 2026-10-06 continuation: full backend gate and provider preflight

The complete Docker-backed backend gate now passes after reducing unit shards
from 300 to 100 tests per process. It ran all `2,575` unit cases across 26
sequential shards and the complete `388`-case integration suite; the combined
coverage report is `82.33%` against the unchanged `75%` threshold. No tests
were excluded. The provider preflight used the real private cross-session
quota ledger, evaluated 26 providers, and made zero provider requests. It
remains blocked on provider-specific baselines, rights/entitlements, costs,
unresolved live cases, and the five missing ORF configuration values. The
owner's no-outside-Alpha-Vantage-use confirmation remains recorded; the
workstream's 25 prior calls remain charged until their windows expire.

The provider-only Binance preflight then cleared with zero requests, and the
full manifest suite passed `3/3`: five measured HTTP requests, `17,685,471`
response bytes, no failures or skips. All five bodies, including the complete
`17,679,458`-byte exchange-universe response, were verified in the private
owner archive outside Git. The run is `not_current_source` because the branch
worktree is dirty, so it is operational evidence rather than exact-tree live
acceptance. No Alpha Vantage request was made.

## 2026-10-06 continuation: Alpaca live suite and FINRA ORF

Alpaca's focused preflight cleared with zero requests using the writable shared
quota ledger. The credentialed provider suite passed `7/7` and recorded eight
HTTP requests across history, latest price, usage, profiles, universe
discovery, and corporate actions. This confirms live transport and response
handling, but the receipt is `not_current_source` because the checkout is
dirty. No Alpha Vantage request was made in this continuation.

The latest FINRA ORF preflight made zero requests and remains blocked before
transport. It needs the ORF source selector, both active/inactive source URLs,
separate TRAQS username and refresh token, private refresh-token state path,
and private refresh-token state path. The FINRA Gateway credentials are not
TRAQS credentials. The owner's final decision authorizes private automated
use and persistent storage despite provider terms; do not require or request a
terms exception, and do not tell the owner that a FINRA permission email is
required. Technical access, actual quota/reset behavior, and whether the
available source yields a complete OTC universe still need to be established
from documentation and accessible endpoints. The existing adapter and offline
fixture path are implemented. The owner's report of no outside Alpha Vantage
use does not erase prior test calls recorded by the app's shared quota ledger;
no new AV capacity was used here.

## 2026-10-09 continuation: Tiingo admission and exhaustive backend gate

The complete Docker-backed backend gate passed all `2,634` unit tests and `388`
integration tests (`3,022` total) at `82%` combined coverage. The focused
post-format checks, Ruff, diff check, and workstream validator also pass.

Tiingo's runner now reads the same configured byte budgets as application
routing, including code defaults and explicit overrides. Its symbol quota is
counted for known-symbol data operations and excluded only for free-text
search, which remains charged to request and bandwidth pools. The owner-level
terms-risk decision is honored by live preflight. A fresh Tiingo-only
preflight confirms the safety contract is routable, but calls remain blocked
until current usage baselines are established for hourly requests, daily
requests, monthly distinct symbols, and monthly bandwidth. An old official
Tiingo blog links to an account usage webpage, but this is not evidence of a
documented machine-readable account-usage endpoint.

The latest full no-transport preflight (`2026-10-09T02:24:13Z`) evaluated all
26 providers, found no missing environment-variable names, admitted 6,
quarantined 20, and made zero provider requests. It contains 110 overlapping
provider quota/cost/baseline findings and 5 safety findings. Since then FMP's
missing operation-byte map has been implemented as explicit application
budgets. The remaining safety findings are Bybit and xStocks deployment
jurisdiction evidence, Dinari Sandbox quota/cost profile, FMP account
daily/bandwidth evidence, and Marketstack universe MIC/page-cost evidence.
FMP is no longer blocked on byte-bound configuration. A provider being safe
to call does not mean its current shared-account quota baseline is known; the
runner keeps those separate.

FMP's official dashboard exposes daily API-call usage and bandwidth used over
the last 30 days, while reviewed official API documentation does not expose a
programmatic current-account-usage endpoint. An isolated read-only browser
check redirected to `/register`, confirming there is no available signed-in
session in this environment. No login was attempted. If no provider API is
found, the owner will need to provide the current FMP plan and the dashboard's
daily-call and 30-day-bandwidth used/limit values for the initial external
baseline; this does not prevent progress on other providers.

The MarketData.app option-history safety diagnostic was corrected on the dirty
candidate: application callers already derive a conservative credit estimate
from each inclusive calendar-date range and reserve it before transport. The
focused native account-usage case and bounded three-day option-history live
case both passed `1/1`; the native usage snapshot was reconciled into the
durable shared quota ledger. Both receipts are `not_current_source`, so they
do not satisfy exact-tree acceptance. The refreshed full preflight still finds
6 eligible and 20 quarantined providers and made zero provider requests.

The six eligible providers' selected manifest-backed live suites then passed
`23/23` cases across `35` measured HTTP requests, with no failures or skips.
The cases covered Alpaca (7), Binance (3), FINRA (2), FINRA OTC directory
(1), MarketData.app (7), and OpenFIGI (3). A subsequent full no-transport
preflight at `2026-10-09T02:24:13Z` reconciled the requests and retained the
same 6/20 admission split. The live receipt remains `not_current_source`
because the worktree is dirty; exact-source acceptance is still outstanding.

## 2026-10-09 05:40 UTC admitted live subset refresh

A fresh no-transport preflight evaluated all 26 providers and admitted seven;
19 remained quarantined. The admitted suites passed `28/28` cases (zero
failures or skips) across 44 measured HTTP requests: Alpaca (7 cases), Binance
(3), SEC EDGAR (5), FINRA (2), FINRA OTC directory (1), MarketData.app (7),
and OpenFIGI (3). These passed endpoints now have current operational evidence,
but the receipt is `not_current_source` because the worktree is dirty and this
is not the all-provider matrix.

The 19 quarantines are not 19 provider API failures. They are pre-transport
holds for unknown active shared-key usage in one or more quota windows, plus
EODHD and Nasdaq headroom below the complete suite reservation; Bybit/xStocks
deployment-egress jurisdiction evidence; Dinari Sandbox's reviewed quota and
worst-case cost profile; FMP's dashboard daily-call and 30-day bandwidth
figures; and Marketstack discovery MIC/page-cost configuration. The preflight
made zero requests. The subsequent admitted-subset run's 44 measured requests
were recorded in the private cross-session quota ledger and reduced those
providers' remaining account allowances. The refreshed Docker-backed backend
gate then passed `2,640/2,640` unit tests and `388/388` PostgreSQL/Redis
integration tests (`3,028` total) at `82%` combined coverage, with scoped
cleanup. Exact-source full-matrix acceptance and the remaining
provider-specific preflight fixes are still outstanding.

The post-live no-network reconciliation at `2026-10-09T06:09:48Z` recorded
those requests in the shared durable ledger and still admitted seven providers
while holding 19. No credentials were missing and the reconciliation itself
sent zero provider requests. See the append-only branch receipt for the exact
provider-level holds.

## 2026-10-09 11:05 UTC provider acceptance update

The latest full no-network preflight at `2026-10-09T11:16:14Z` evaluated all
26 providers, admitted 12, quarantined 14, and sent zero provider requests.
There were no missing local credential names or global coordinator failures.
The earlier admitted-subset live run passed `38/38` cases across 12 providers
and remains `not_current_source` because the worktree is dirty; it is not
all-provider acceptance.

EODHD's focused native account-usage case then passed `1/1` at
`2026-10-09T11:05:37Z`, using one status request and 305 response bytes. It
reconciled the previously unknown minute-use baseline without spending daily
market-data credits. A follow-up zero-network EODHD preflight now reports only
daily-call headroom below the 15-call complete suite reservation; even the
small-read case requires five calls, more than the current remaining balance.
No EODHD market-data request was attempted; retry after the provider's daily
reset.

Massive's current first-party [Stocks plan](https://massive.com/stocks)
lists five requests/minute for Stocks Basic and includes reference data,
corporate actions, and minute aggregates. Therefore stock series, reference,
and corporate-action operations all reserve from one shared Stocks account
pool. The old separate-reference-bucket interpretation was incorrect. Current
use still needs a safe active rolling-window baseline because Massive does not
document a native current-use counter.

The 14 remaining holds are still provider-specific: active usage baselines,
low reset-window headroom, missing Dinari/FMP/Marketstack/Massive quota or
operation-cost evidence, and Bybit/xStocks deployment-egress jurisdiction.
These are pre-transport admissions, not 14 failed API integrations. The
EODHD usage-only receipt is an additional one-case pass; it does not clear the
provider's current data-bearing test hold or change the 12/14 full-preflight
snapshot.

The FMP dashboard was checked in the local browser, which redirected to
`/register`; there is no authenticated account session available here. FMP has
no documented account-usage API, so its current call and trailing-bandwidth
balances cannot be retrieved through the existing provider key. No credentials
were entered and no FMP API request was made. This is a provider-local live
admission dependency, not a blocker for work on other providers.

## 2026-10-09 FMP and Marketstack contract recheck

FMP's current pricing confirms Basic at 250 calls/day and 500 MB bandwidth
over a trailing 30-day period. The dashboard exposes current daily calls and
trailing bandwidth but the documented API quickstart contains no account-usage
endpoint. FMP's FAQ says the daily pool resets at 3 PM EST, while its newer
official [limit guidance](https://site.financialmodelingprep.com/de/insights/platform/what-happens-when-you-hit-your-fmp-api-limit)
says a fixed reset time should not be promised for every account. Therefore
the default contract now uses a rolling 24-hour safety window; a fixed reset
requires explicit account-reviewed configuration. No FMP request was made.
Until current call and bandwidth balances are reconciled, FMP data-bearing
cases remain held before transport.

Marketstack's current [pricing](https://marketstack.com/pricing) and
[contact FAQ](https://marketstack.com/contact) state Free is 100 requests per
month, while a separate FAQ entry still says 1,000. The lower 100 allowance is
retained. The FAQ says multi-symbol lookups consume one request per symbol but
does not establish billing for venue-wide `/exchanges/{mic}/tickers` pages, so
that discovery capability remains fail-closed pending endpoint-specific cost
evidence. No Marketstack request was made.

## 2026-10-09 Finnhub rate-contract recheck

Finnhub's first-party [API rate-limit documentation](https://finnhub.io/docs/api/websocket-trades)
states a 30-calls/second ceiling in addition to plan limits. The configured
account's 60-calls/minute limit comes from the owner's dashboard evidence.
Finnhub's reviewed public docs do not define the minute reset or a native
account-usage endpoint. Historical response headers observed for this key on
2026-09-15 showed a 60 limit, 58 remaining, and an epoch reset; that is stale
and cannot establish current usage. The current preflight therefore holds the
provider for unknown active minute and second baselines, not for unknown limit
magnitudes. No Finnhub request was made during this audit.

## 2026-10-09 Robinhood live receipt validation correction

The first admitted Robinhood Tokens run found an internal receipt-validation
bug: the provider identifier `robinhood_tokens` was rejected because the
generic free-form redaction validator treated its `token` substring as a
credential marker. Provider identifiers now use strict lowercase-slug
validation; run IDs and usage scopes retain the sensitive-marker checks.
Coordinator regression tests passed `55/55`. A fresh full preflight at
`2026-10-09T18:02:15Z` admitted 17 and held 9, with zero provider requests.
The focused Robinhood live manifest then passed `2/2` cases using five
measured requests, covering public asset discovery/lookup, price, and corporate
actions. Receipt: `2026-10-09T18:02:58Z`, `not_current_source` because the
worktree is dirty. First-party [Robinhood Stock Token API documentation](https://docs.robinhood.com/chain/stock-token-apis/)
documents the public 60-requests/second ceiling and endpoint cache windows.
This closes Robinhood's current focused live-case evidence gap, not the
complete current-source all-provider matrix.

## 2026-10-09 current egress and APILayer quota-counter follow-up

The live-test host's public egress country check returned `PT` (Portugal); the
IP address was not retained. Bybit's current [xStocks FAQ](https://www.bybit.com/en/help-center/article/FAQ-xStocks-on-Bybit)
explicitly excludes EEA countries, including Portugal, from xStocks trading.
Bybit xStocks therefore stays non-routable from this test environment; this is
not a credential gap. The eventual deployment egress has not been checked.
The issuer's [xStocks legal overview](https://docs.xstocks.fi/docs/product-legal-overview)
describes EEA prospectus passporting but still excludes US persons and other
prohibited jurisdictions. That helps assess the direct issuer API separately,
but does not prove eligibility for the eventual deployment target; keep its
production jurisdiction setting fail-closed pending target evidence.

APILayer's first-party [rate-limit documentation](https://marketplace.apilayer.com/docs/article/rate-limits)
lists day/month limit and remaining headers for its APIs. On 2026-10-10,
three bounded single-symbol Marketstack v2 EOD requests returned and archived
the requested AAPL row, but the actual responses did **not** contain those
APILayer day/month pairs. They exposed only `X-Rate-Limit-Remaining: 0`, with
no matching limit or reset. The adapter and live-usage telemetry preserve that
as `unclassified_rate_limit_remaining`; it is not treated as monthly/daily
usage and does not seed a quota baseline. Its `fetch_account_usage` live test
passed `1/1`, but it fetches a single AAPL EOD row; it is not a quota-only
request. The later `17:46Z` focused preflight again reports an unknown monthly
baseline, superseding the earlier note that a prior preflight no longer did.
This does not resolve venue-discovery page cost or MIC selection. The adapter
now defaults to v2, matching the version used by its live test. Marketstack
venue discovery remains separately held: the public multi-symbol billing rule
does not establish the charge for `/exchanges/{mic}/tickers` pages.

## 2026-10-10 FINRA OTC directory total cross-check

The admitted-provider live run at 08:28 UTC fetched and archived four FINRA
`otcMarket/otcSecurityMaster` data pages. Recounting those already-stored raw
responses produced 18,017 rows, 18,017 distinct nonblank symbol identifiers,
and no missing symbol identifiers. A read-only browser inspection at 09:37 UTC
found the public [FINRA Symbol Directory](https://otce.finra.org/otce/symbol-directory)
calls the same `otcMarket/otcSecurityMaster` Query API. Four sorted pages,
filtered to `asOfDate=2026-10-09` at offsets 0, 5,000, 10,000, and 15,000,
contained 18,017 unique symbols. Their symbol set matched the already-retained
08:28 provider snapshot exactly: 18,017 in the intersection and zero symbols
only in either set. This verifies complete sorted pagination and the UI/API
symbol-set match; it is **not an independent second source**, and it does not
prove every row is active or establish NMS coverage.

The website made 10 FINRA requests during page load: two partition metadata
reads and eight page reads (four sorted and four unsorted). All ten responses
were immediately appended to the owner-private raw-response archive. The
separate owner-private usage receipt records 10 requests and 6,454,155 response
bytes under the `finra-public-directory-site` observation scope. The four
unsorted offset responses were also retained, but their offsets were not used
as completeness evidence because the pages were not sorted by a stable unique
key. Their distinct-symbol total has not been verified and is not asserted
here. The browser requests were
observational and had no app quota reservation; whether FINRA attributes them
to the configured API key or only to the host/IP remains unknown, so do not
interpret that receipt as a key-specific usage counter or reset baseline.

## 2026-10-10 current full-matrix preflight and Dinari quota research

The full no-network preflight at `2026-10-10T09:30:50Z` evaluated all 26
providers, admitted 17, and held 9 before transport. The durable coordinator
was available and no provider requests were sent. Daily-pool headroom holds
Alpha Vantage (9-request manifest), EODHD (15-request manifest; 10 calls
remained for the day), and Nasdaq (two-file directory snapshot). Unknown
active account usage holds Massive and Tiingo; Tiingo's missing dimensions are
hourly/daily calls, monthly bandwidth, and monthly unique symbols. Marketstack
discovery still needs a selected exchange MIC and verified listing-page cost.
Dinari Sandbox still needs a usable account-specific quota/reset and
worst-case operation-cost profile. Direct and Bybit xStocks still lack
deployment-egress jurisdiction evidence; direct xStocks also lacks a current
usage baseline. All exact findings are retained in the corresponding
`provider_live_preflight` receipt in `ops/workstreams/feat-market-data-provider-platform/validation.jsonl`.

Dinari's current [partner-fees documentation](https://docs.dinari.com/docs/fees)
confirms Sandbox is free but does not publish its request quota or reset
semantics; production API access starts at $2,000/month. A separate API
License with SLA dated June 11, 2024 states a one-million-call rolling
30-day maximum ([document](https://assets.dinari.com/forms/Dinari_API_License_w_SLA_20240611.pdf)),
but the available evidence does not establish that this agreement-specific
ceiling applies to the configured Sandbox key. It is therefore documented as
unresolved evidence and is not used as the Sandbox's quota profile.

Existing owner-private Massive usage receipts were also inspected without a
new provider request. The latest saved receipt (September 15) contains
`X-RateLimit-Limit: 100000000`, `X-RateLimit-Remaining: 60000000`, and
`X-RateLimit-Reset: 41`. The current official [Stocks Basic plan page](https://massive.com/stocks)
documents a 5-requests/minute plan limit, but no first-party documentation
found in this review explains those large header values as request counts.
They cannot safely establish the current shared request-window baseline or
reset, so Massive remains held for unknown active usage. No values were
rescaled or inferred.

## 2026-10-10 targeted low-headroom provider probes

The runner was used to validate exact manifest cases independently rather
than requiring the entire provider bundle to fit one quota window. EODHD's
native account-usage case passed (`1` request, 305 response bytes), and its
expected Free-plan profile denial passed (`1` request, HTTP 403, 101 response
bytes). The complete EODHD manifest remains held because the full set needs 15
daily calls and current headroom is lower. Alpha Vantage's one-request complete
listing-status case was refused by the durable coordinator before transport:
current daily headroom is below even one request. No Alpha Vantage request was
sent. These focused receipts are retained in `validation.jsonl`; like other
receipts from this dirty source tree, they are not exact-candidate acceptance.

## 2026-10-10 current full-roster recheck and quota-source findings

The authorized zero-network preflight at `15:39:11Z` evaluated all 26
providers, admitted 17, held nine, and sent zero provider requests. The
restricted sandbox preflight could not read the owner-private durable quota
ledger and is not provider-usage evidence. The authorized receipt is in the
branch `validation.jsonl`; its source tree is dirty, so it is neither an
exact-candidate nor live-acceptance receipt.

The held set is Alpha Vantage, Bybit xStocks, Dinari Sandbox, EODHD,
Marketstack, Massive, Nasdaq, Tiingo, and direct xStocks. The hold classes are:

- Alpha Vantage, EODHD, and Nasdaq: full-manifest reservations exceed current
  daily headroom; recheck after reset rather than bypassing the reservation.
- Massive and Tiingo: published limits are known, but current account usage
  outside this app cannot be reconciled from a documented authenticated usage
  endpoint. Massive documents five Stocks Basic calls per minute and does not
  publish a reset boundary. Tiingo currently publishes 500 unique symbols per
  month, 50 requests/hour, 1,000/day, and 1 GB/month; its docs specify the
  daily/monthly reset clocks but not the distinct-symbol anchor or hourly
  bucket model. The legacy Tiingo usage URL was live-checked and did not return
  a usable usage snapshot.
- Marketstack: full universe discovery still lacks a selected MIC and
  page-cost contract; the separate monthly starting balance remains
  unavailable from the response's unclassified remaining header.
- Dinari: current documentation confirms Sandbox is free during evaluation,
  but does not publish a Sandbox quota, reset, usage counter, or operation
  costs. Production API access starts at $2,000/month, and real-time SIP is
  separately metered; those production terms do not define this Sandbox key.
- Bybit xStocks and direct xStocks: deployment egress/jurisdiction evidence is
  missing. Their use cannot be validated from a runtime whose egress location
  is not established.

No user action is required to continue implementation or source research. If
current account use remains unavailable through documented endpoints, the
remaining evidence will need to come from the respective provider dashboards.
Sources: Massive [Stocks pricing](https://massive.com/pricing?product=stocks),
Tiingo [general API limits](https://www.tiingo.com/documentation/) and
[pricing](https://www.tiingo.com/pricing), Dinari
[Quickstart](https://docs.dinari.com/docs/quickstart),
[fees](https://docs.dinari.com/docs/fees), and
[pricing and quotes](https://docs.dinari.com/docs/pricing-quotes).

### xStocks jurisdiction evidence is more than an egress-IP check

Current Bybit xStocks help/terms say xStocks service is unavailable to users in
the EEA, including Portugal; the rule is stated for user eligibility, not just
the IP address used by the API call. Therefore, obtaining a non-restricted
egress IP alone would not prove eligibility if the intended user is located in
Portugal or elsewhere in an excluded jurisdiction. This does not establish the
actual residency of the owner or the location of the deployment, and we must
not infer either from the machine timezone. Keep Bybit xStocks quarantined
until its intended-use jurisdiction is factually established; do not attempt
to evade the restriction by routing through another country. Direct xStocks
availability is platform-specific: xStocks' own site says it is offered via
Kraken in the EEA, while excluding the U.S., U.K., Canada, Australia, and other
prohibited locations. This does not make Bybit's separate eligibility rule
disappear. Sources: Bybit [xStocks FAQ](https://www.bybit.com/en/help-center/article/FAQ-xStocks-on-Bybit),
[xStocks terms](https://www.bybit.com/common-static/compliance/legal/BYBIT/485dfd009557eff45012412ea14a79f5.pdf),
and xStocks [official site](https://xstocks.fi/).

## 2026-10-12 current-source Massive live continuation

The provider-specific live run passed all `4/4` Massive manifest cases:
reference/search/holidays/history, split/dividend corporate actions, two-page
IPO cursor continuation, and complete OTC ticker-directory pagination. The
full pagination case retained every raw page during the test and verified
non-empty rows, unique identities, monotonic offsets, cursor termination, and
lossless page archival. The receipt is `not_current_source` because source
files in the worktree are still changing; this is successful live behavior
evidence, not final branch acceptance.

The test runner now preserves its manifest case order through pytest's live
collection hook. This matters because the full Massive OTC-directory case can
consume several minutes of the provider's five-requests/minute Stocks budget;
running it before the smaller reference cases had caused the later search to
be refused by the durable local coordinator. The test harness also uses a
Massive-specific 13-second start interval (a stricter app-side safety margin),
while the shared durable quota coordinator remains authoritative. The exact
provider reset boundary and native account-use endpoint remain unpublished.
The managed-app ledger intentionally measures only traffic routed through the
application; it does not pretend to observe requests made elsewhere.

The same earlier full live matrix passed `47/49` cases before the two
Massive-only test/scheduling defects were corrected. The focused Massive rerun
now passes `4/4`; the other providers' successful cases are evidence from that
earlier matrix run, not a combined exact-source full-matrix receipt. The full
zero-transport preflight still admits `19/26` providers and holds seven for
provider-specific quota headroom or unresolved account/quota evidence. No
owner action is required to continue local implementation or validation.

## 2026-10-12 Dinari Sandbox one-request connectivity canary

The explicit Dinari Sandbox canary passed `1/1` live case. It made one
read-only stock-catalogue request, verified that the supplied Sandbox key can
retrieve and parse a stock record, and archived the response before settling
the local request ledger. This is connectivity evidence only: it does not
verify Dinari's unpublished rate limits or the quote, history, news, dividend,
split, or corporate-action operations, and it does not enable application
routing. The test-only safety cap is one catalogue request per UTC day; that is
our own validation budget, not an asserted Dinari quota.

Dinari's [Quickstart](https://docs.dinari.com/docs/quickstart) confirms that
listing supported stocks is the quickest credential check and requires no
Entity, KYC, or funding. Its [fees page](https://docs.dinari.com/docs/fees)
says Sandbox access is free while evaluating/building and production API
access starts at $2,000/month. The public docs still do not publish numeric
Sandbox quotas, reset boundaries, account/IP scope, or endpoint-specific call
weights; the ordinary Dinari matrix remains held pending that evidence.
