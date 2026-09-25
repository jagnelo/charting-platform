# Data Providers

This document describes every data provider registered with the platform, what data each one
supplies, its priority level per capability, and where to configure its credentials.

---

## Provider Priority Overview

> **Quota safety contract (corrective revision):** the runtime never applies a
> generic rate, burst, concurrency, or cooldown. A provider is routable only
> when every required quota dimension has an explicit source, scope, unit,
> limit, and reset window. If a vendor does not publish a fixed limit (or the
> deployment plan is not verified), it remains visible to administrators but is
> `quota_unknown` and cannot be selected. A 429/418 response is recorded with
> provider headers/reset information, opens the affected circuit, and defers
> work; it is not retried in a tight loop.
>
> `PROVIDER_MAX_CONCURRENCY` is only a process-local instrument-sync guard. It
> is not a provider limit and is never used to infer one.
>
> A reviewed plan and configured credential are still not enough to route a
> provider: its capability must carry `passed` (or genuinely `not_required`)
> live-probe evidence. Historical bounded transport evidence exists for EDGAR,
> Alpaca, MarketData.app, and the Dinari Sandbox pair, but it is not by itself
> current-source acceptance. The latest exact-source Alpaca work proves its
> native account-usage header snapshot and rolling safety-envelope bootstrap;
> ordinary Alpaca routing still requires current-source live evidence and the
> separate terms gate. The latest SEC EDGAR manifest preflight stopped before transport
> because the documented IP window has no current durable baseline. Tradier,
> Ondo, and IBKR are intentionally deferred. None of these observations
> overrides the separate quota, terms, entitlement, and reconciliation gates.

Operation-cost maps are provider-specific and reviewed against the adapter's
actual transport shape. Alpha Vantage's search, daily/weekly/monthly history,
latest-price, listing, IPO-calendar, and annual/quarterly earnings operations
each reserve one provider query; a future pagination or compound lookup must
change that map before the operation can be treated as quota-safe. No
operation silently inherits a universal request cost when a provider contract
declares operation-level accounting.

Massive historical bars use a caller-supplied page estimate derived from the
requested timeframe and the documented 50,000-base-aggregate page ceiling;
each cursor page is therefore reserved before execution rather than charged as
an invented single request.

History adjustment is an explicit routing requirement. The market-data service
passes the requested `adjusted` value into provider resolution before quota
reservation and transport. Alpha Vantage's free daily/weekly/monthly endpoints and IBKR's
historical endpoint are raw-only in the supported contracts, so adjusted
requests are filtered before a raw-only provider can be selected; raw requests
remain eligible. The current raw-only admission list includes Alpha Vantage,
IBKR, Tiingo, Twelve Data, Finnhub, Marketstack, EODHD, FMP, Tradier,
MarketData.app, and the Binance/Coinbase/Kraken exchange feeds. The platform
does not silently synthesize split/dividend adjustments from a raw response.
The registry publishes `adjusted_price_history` separately from
`price_history`; at this revision it is advertised for Alpaca, Massive, and the
explicit legacy yfinance compatibility path, so consumers do not infer
adjustment semantics from the presence of an OHLCV method.
The same guard is enforced when an adapter is called directly (including live
probes and maintenance paths): raw-only providers reject `adjusted=True` before
transport, and exchange bars retain explicit `raw`/`provider-native`
provenance.

The backend provider-policy diagnostics also expose the required and currently
missing environment-variable names for each provider. These are names only;
secret values are never returned. This lets operators distinguish an absent
credential or non-secret scope setting from an unreviewed entitlement or quota
contract without turning the diagnostics endpoint into a secret store.
Routing-safety controls are exposed separately: FINRA's positive async result
bound and the complete Tiingo/FMP operation-byte maps have their own required
and missing-variable fields, so a configured credential cannot be mistaken for
safe routing when response-size accounting is still incomplete.

The same explicit accounting applies to the one-request surfaces of Alpaca,
Massive, Alpha Vantage, FRED, OpenFIGI, Coinbase, Kraken, Marketstack, Finnhub,
FMP, Tiingo, and Tradier. The deep-history worker's `bulk_fetch` operation is
also explicitly mapped for the single-request history adapters (Alpha Vantage,
FRED, Finnhub, and Tradier); it is never charged through an unreviewed
operation fallback. Range/pagination-dependent history operations are either charged
from a caller-computed estimate (for example Alpaca, Coinbase, Kraken,
Marketstack, and Twelve Data) or remain fail-closed behind their reviewed byte
maps; they are not represented by a misleading fixed one-request profile.
These accounting profiles describe adapter cost only; the Coinbase and FRED
terms/rights gates independently block direct network use until their required
written authorities are configured.

Durable quota windows are keyed by provider, documented dimension, and an
explicit `quota_group` when the vendor's allowance is shared across
capabilities. For example, MarketData.app's daily credits and concurrent
request ceiling use the reviewed `account` group, so history, quotes, and
options cannot each spend an independent copy of the same account budget.
When a contract omits the field, the compatibility key is the requested
capability; the runtime never infers account sharing from a generic scope label.
Existing windows are backfilled by migration `7d8e9f0a1b2c`, and admin/usage
diagnostics expose both the request capability and bucket group.

### Provider-native account usage observations

Local request logs and quota windows are durable across processes and sessions,
but they cannot know a provider's account-side counters unless that provider
publishes an introspection endpoint.  Such counters therefore have a separate
`account_usage` capability and observation table. The current concrete
implementations are MarketData.app's authenticated `GET /user/` endpoint,
Twelve Data's `/api_usage` endpoint, EODHD's `/user` endpoint, Binance's
public `/api/v3/time` endpoint (which exposes its native one-minute request
weight header), and Alpaca's bounded observation of its native
limit/remaining/reset headers. Alpaca documents a 200-requests/minute pool but
does not publish a fixed calendar-minute boundary; the runtime therefore uses
a conservative rolling 60-second safety envelope and only seeds the durable
active baseline from a matching native snapshot:

```sh
POST /api/v1/providers/usage/account/refresh   # admin-only, explicit poll
GET  /api/v1/providers/usage/account            # admin-only, durable history
```

The refresh is admitted through the same credential, live-probe, provider
quota, operation-cost, and circuit-breaker checks as any other request.  The
MarketData.app account-usage operation is the one deliberate exception to the
plan-review gate: it may be polled with the conservative seed contract before
the operator has recorded the plan, so the native response can inform that
review.  It cannot admit market-data or options routing. Binance, Twelve Data,
and EODHD also declare an explicit first-snapshot bootstrap: when a finite provider pool
has no active durable baseline, only a deployment-scoped serialized probe slot
is reserved; the native response must establish the exact pool before ordinary
reads can reserve it. This is an application safety control, not a provider
quota or entitlement. Binance's first snapshot uses the same explicit
serialized bootstrap slot and accepts only `X-MBX-USED-WEIGHT-1M` plus the
reviewed fixed-minute boundary. The returned
limit/remaining/consumed/reset/options values are stored verbatim as
observations; they never replace the reviewed local plan, infer a reset window,
or widen routing. Providers without a documented native usage surface remain
represented by durable request/byte/header telemetry and are not queried
through a guessed endpoint. EODHD daily usage can reconcile only a current-date
`calls_per_day` baseline whose returned limit matches the reviewed contract;
its minute headers remain observational while the provider's official
minute-limit sources conflict. Twelve Data's native minute-credit observation can
reconcile the exact reviewed `credits_per_minute` coordinator baseline; its
separately documented daily allowance is stored as an observation only until
the provider exposes a stable daily counter. The bootstrap contract records
these mappings per provider; a native usage endpoint never grants an unknown
second pool an implicit zero baseline. For example, Twelve Data's daily
`credits_per_day` pool remains non-routable after `/api_usage` until an exact
daily baseline is independently established.

Provider observations are append-only evidence. The maintenance endpoint never
deletes provider request logs or latest-price, search, universe, profile, or
identifier snapshots, regardless of the legacy `PROVIDER_REQUEST_LOG_RETENTION_DAYS`
and snapshot-retention settings. Request logs are quota and audit evidence, not
disposable operational cache. This preserves every quota-consuming provider
response and usage fact for audit, replay, and future reconciliation.

Raw OHLCV observations follow the same rule: the conflict key includes the
fetch observation timestamp, so a later provider revision of an existing bar
creates a new raw observation instead of overwriting the earlier response.
Canonical bars remain projections and may be refreshed independently.

General market events follow the same projection/evidence split. The canonical
`market_event` row remains keyed by provider event identity for reconciliation,
while each fetched provider payload is appended to `market_event_observation`.

Tokenized-asset metadata follows the same rule. `tokenized_asset_detail` is
the mutable latest-state projection used by identity and quote workflows, while
each catalog, metadata, or quote refresh appends its original provider payload
to `tokenized_asset_observation` with provider asset identity and both provider
observation and local fetch timestamps. Repeated identical responses are kept;
they are quota/audit evidence and are never deduplicated or pruned.

The mapping is enforced consistently by normal application routing, the direct
live-probe planner, and the manifest preflight. Missing, duplicated, or
non-existent `reconciled_dimensions` entries fail closed before transport;
they cannot authorize all unknown pools by omission.

For MarketData.app specifically, `/user/` is tracked as an explicit
account-usage operation and occupies the account-wide in-flight concurrency
lease, but its reviewed per-dimension cost map excludes `credits_per_day`.
The native `x-api-ratelimit-consumed` value is therefore not replaced by a
synthetic one-credit debit. This also lets a fresh durable coordinator perform
the first account snapshot without a manually invented starting credit
baseline; all actual data/options operations still require the exact reviewed
plan/limit baseline before routing.

Deployments may opt into a once-daily worker snapshot by setting
`PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED=true` and naming an explicit JSON list
in `PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS` (for example,
`["marketdata_app"]`). An empty list never means all providers. The worker
polls at 15:00 UTC, after MarketData.app's documented 09:30
`America/New_York` reset in both daylight and standard time; the schedule is a
poll cadence, not a quota assumption. Each named provider still passes through
its own credentials, reviewed quota, and circuit-breaker checks, and a provider
without an implemented native usage endpoint remains a durable no-observation
result.

Direct credentialed live probes are accounted separately in the owner-managed
cross-session ledger. Each receipt retains a bounded operation breakdown with
the measured operation count, HTTP-request count, response bytes, and failures;
the admin usage diagnostics expose it as
`live_test_usage.operation_breakdown`. This preserves endpoint-specific
attribution for shared provider accounts without converting observations into
quota reservations or inventing provider-native units, resets, or limits.

## Provider capability and quota ledger

The table below is the checked-in contract used by `ProviderPolicy` and the
durable `ProviderQuotaWindow` counters. “Unknown” is deliberate; it is not a
placeholder estimate. Limits are for the named plan/scope only and must be
re-reviewed when credentials or billing plans change.

Historical routing also requires a machine-readable lookback contract in the
provider entitlement. The descriptive `history_depth` field remains useful for
operator diagnostics, but it cannot admit a date-bounded request by itself.
Providers with a documented finite lookback publish exactly one of
`quota_policy.history_constraints.earliest_date` (for a fixed provider-
advertised calendar start), `max_lookback_years`, or the equivalent
`max_lookback_days`; malformed, missing, future, or ambiguous bounds fail
closed. A fixed date is preferred when the provider publishes a calendar start
so the contract does not drift as the current date advances.
Normal bounded OHLCV fetches pass their requested start date through this gate.
Epoch-style bulk hydration intentionally omits that admission bound so each
provider can return the maximum history it actually exposes, with the result
still bounded and validated by the adapter.

Published bandwidth pools expressed by vendors as GB/MB are represented as
conservative decimal-byte ceilings when the provider does not explicitly state
binary units. This prevents the local guard from permitting more bytes than a
decimal interpretation would allow; the contract records the basis explicitly.

| Provider | Implemented data surface | Credential/config key | Documented usage contract | Reset/scope | Routing status |
|---|---|---|---|---|---|
| Alpaca | US stocks/ETFs + crypto OHLCV, latest, authenticated asset metadata (exchange/status/tradability/provider asset UUID), corporate actions, assets | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_TRADING_BASE_URL`, optional `ALPACA_REVIEWED_RESET`, `ALPACA_QUOTA_EVIDENCE` | Trading API Basic is free for paper/live users; no separate daily data allowance is documented. The current official plan table states 200 historical API calls/minute, equity history since 2016, free real-time equities on IEX, and historical/latest data limited to the latest 15 minutes; the community clarification says paper and live keys share the same user-level subscription. Corporate-actions pages accept 1–1,000 records; `X-RateLimit-Limit`/`Remaining`/`Reset` headers are retained and reconciled against a rolling safety envelope. Sources: [official market-data plan table](https://docs.alpaca.markets/us/docs/about-market-data-api), [paper-key clarification](https://forum.alpaca.markets/t/key-limitations-on-paper-trading-keys/17789) | account / rolling 60-second safety envelope; free IEX feed and 15-minute recency boundary apply; paper/live assets host is explicit; every corporate-action page is persisted and resumed; Alpaca UUID is provider-native and is not promoted to a canonical FIGI/CIK | history/latest, metadata, account usage, and cursor pagination are fixture/live-covered; the native account snapshot establishes the active baseline before metered routing; optional reset/evidence settings document future plan changes |
| Massive | US ticker search/reference universe, single-ticker metadata (CIK/FIGI, exchange, lifecycle, classification, description/branding), split-adjusted or raw aggregate OHLCV, historical splits and dividends for all canonical timeframes | `MASSIVE_API_KEY` (or legacy `MARKETDATA_API_KEY`) | Stocks Basic: 5 API calls/minute per asset class, two years of historical data, EOD/reference/minute aggregates, and corporate actions; the published plan does not state the minute reset boundary; aggregate pages accept at most 50,000 base aggregates; splits/dividends accept at most 5,000 rows and may continue with `next_url` | API key / provider-defined minute boundary with an explicit rolling 60-second application safety envelope; the current stocks-only adapter conservatively shares one API-key bucket (it never assumes an unimplemented asset-class partition); validated history and corporate-action cursors are followed until completion; metadata overview costs one request | reference, metadata, adjusted daily, raw five-minute history, and corporate actions remain terms-gated. The legacy page-bound setting no longer excludes pages; a configured key alone is not legal authorization; options/crypto adapters must supply an asset-class partition before using the provider's per-class allowance |
| Alpha Vantage | Raw daily, weekly, and monthly OHLCV, symbol search, listings, IPO calendar events, historical annual/quarterly earnings with EPS estimates and surprise metrics | `ALPHA_VANTAGE_API_KEY` | 25 requests/day (free key); daily `compact` output is latest 100 points, while documented weekly/monthly series expose long historical ranges; adjusted daily history is premium and weekly/monthly endpoints are raw; `EARNINGS` is one query per symbol; the provider does not publish the daily reset boundary/timezone | API key / provider-defined day with an explicit rolling 24-hour application safety envelope | raw daily/weekly/monthly history and bounded earnings normalization are fixture-covered; adjusted history is rejected explicitly; a range older than the 100-point daily compact window fails closed instead of returning a partial slice; IPO-calendar remains subject to its documented capacity response; future plan changes may override the safety envelope with reviewed reset evidence |
| SEC EDGAR | issuer/ticker/exchange directory, profiles, filings/earnings, XBRL facts, provisional IPO-pipeline filing candidates | `EDGAR_USER_AGENT` | 10 requests/sec total across an IP; the SEC says access resumes once traffic drops below the threshold but does not define a fixed bucket boundary | IP / provider-defined with an explicit rolling one-second application safety envelope | contract recorded; profile and complete directory pagination live-proven 2026-09-12 with the supplied contact value; duplicate ticker/CIK candidates are preserved as ambiguous and never silently resolved; IPO-pipeline case is bounded and candidate-only; User-Agent and SEC fair-access compliance remain required |
| OpenFIGI | FIGI/ISIN/CUSIP/SEDOL mapping and profile enrichment | optional `OPENFIGI_API_KEY` | Without key: 25 mapping requests/minute and at most 5 jobs/request. With key: 25 mapping requests/6 seconds and at most 100 jobs/request. The API exposes `ratelimit-limit`, `ratelimit-remaining`, and `ratelimit-reset`; HTTP 429 means the active window is exhausted | anonymous traffic is IP-scoped; keyed traffic is API-key-scoped; both use provider rolling/reset windows | exact contract switches from anonymous to keyed only when `OPENFIGI_API_KEY` is present; the adapter is fixture/live-covered and preserves native rate-limit headers |
| Binance | public crypto OHLCV, ticker, USDT universe, native request-weight usage snapshot | none | Current Spot REST documentation exposes a 6,000 request-weight/min IP ceiling. Adapter operations use documented weights: single-symbol price 2 and exchange-info discovery 20. Historical OHLCV costs weight 2 per 1,000-candle page; the requested range is conservatively paged and reserved before execution. The bounded `/api/v3/time` account-usage probe reads `X-MBX-USED-WEIGHT-1M` and proves the current fixed-minute counter; response `Retry-After`/weight headers are retained on capacity failures | IP / fixed minute; 429/418 protection | exact-weight price/discovery and bounded historical operations remain baseline-gated until the native usage probe establishes the active fixed-minute window; no empty-ledger assumption |
| Coinbase Exchange | public crypto candles, ticker, USD products | none | 10 public requests/sec, burst up to 15; candle responses cap at 300 bars | IP / rolling | route and live-read blocked by default: written Coinbase authority must cover this application's automated/AI use and persistent storage; non-redistribution remains required; rate-limit compliance alone is not legal authorization |
| Kraken | public crypto OHLC, ticker, USD pairs | none | safe public frequency <=1 request/sec; pair/IP limits apply; OHLC responses cap at 720 bars | IP/pair / rolling | history follows the provider `last` cursor and reserves `ceil(requested candles / 720)` calls; keyless live evidence required |
| CoinGecko Demo | crypto search, metadata, market-cap universe | `COINGECKO_API_KEY` | 100 calls/min and 10,000 calls/month; CoinGecko documents that monthly call credits reset on the first day of each month regardless of billing date ([pricing](https://www.coingecko.com/en/api/pricing), [support clarification](https://support.coingecko.com/hc/en-us/articles/16760509234713-When-does-my-request-volume-monthly-API-credit-reset)) | Demo key / rolling minute + UTC calendar-month pool | credentialed search live-proven; the official [`/key` usage endpoint](https://docs.coingecko.com/reference/api-usage) is restricted to Pro subscribers and returned HTTP 401 `10005` for the configured Demo key, so the monthly contract is now exact but an active account baseline is still required before routing |
| FINRA | consolidated short interest (OAuth Query API), OTC Daily List lifecycle/corporate-action deltas, and generic asynchronous Query API jobs | `FINRA_CLIENT_ID`, `FINRA_CLIENT_SECRET` | 1,200 synchronous requests/minute/IP; 20 asynchronous submissions/minute/dataset/account; max 5,000 records and a published 3 MB synchronous-response ceiling. The adapter reserves 3,000,000 bytes per synchronous operation (decimal interpretation, conservative because FINRA does not define the byte convention); the public credential publishes a 10 GB monthly allowance and disables the credential until the first day of the following month. The native reset timezone and byte convention remain unconfirmed, so the provider-defined label is retained for audit while a conservative provider-scoped rolling 31-day safety envelope protects admission | OAuth client / IP + dataset/account + provider-defined monthly public-credential byte window with rolling 31-day application safety envelope; native reset boundary remains unresolved | synchronous datasets live-proven; async submit/poll/presigned-download flow is fixture-tested and becomes routable only with a positive reviewed result-byte bound plus the provider-defined monthly reset admission; the default unbounded path remains fail-closed |
| FINRA OTC directory | Candidate `otcSecurityMaster` DAPI-shaped adapter or explicitly supplied pipe-delimited mirror; current public FINRA catalog does not establish `otcSecurityMaster` as an available dataset | `FINRA_OTC_SYMBOL_DIRECTORY_URL` plus source-evidence, operation-cost, terms, completeness, redistribution, and polling controls | FINRA's 1,200 synchronous requests/minute/IP and 3 MB/response are platform-wide ceilings only; they do not establish this candidate dataset's availability, quota applicability, or source-specific rights. Any synchronous response bound uses 3,000,000 bytes locally | configured source / no assumed provider quota | **non-routable and no live request permitted** until current FINRA documentation or written provider confirmation is recorded; prior pagination probe is transport-only historical evidence, not source authorization |
| OTC Markets Overnight Security Master (candidate) | Officially specified complete OTC security-master file containing OTC Markets security/company identifiers, symbols, names, security type/class, tier, reporting standard, status, reference price, and overnight-eligibility fields; pipe-delimited file plus a validation file with source/timestamp/record count; the candidate parser strictly validates the file shape and, when both files are supplied, rejects a record-count mismatch | commercial OTC Markets delivery/entitlement; specification names SFTP host `sftp.otcmarkets.com` and account-representative credentials, but grants no access | Files are published before each trading session at 5:25 PM and 7:20 PM ET on trading days, approximately 5 MB; CUSIP-included and no-CUSIP variants exist. Provider/file-delivery terms, quota, complete US-OTC coverage, and redistribution rights must be confirmed. The specification warns that CUSIP redistribution requires a separate CUSIP license | provider account / SFTP delivery contract / session cadence | **candidate only; source delivery and live routing are disabled**. This is the concrete alternative to the undocumented FINRA `otcSecurityMaster` candidate and remains outside the approved free-only routing budget until access and rights are explicitly authorized ([official specification](https://www.otcmarkets.com/files/OTC%20Markets%20Overnight%20Security%20Master%20Specification.pdf)) |
| FRED | macro/rates/FX daily series | `FRED_API_KEY` | FRED v1 documents up to 120 requests/minute before HTTP 429, but does not publish the enforcement scope or reset boundary; provider-adjusted limits and series-specific rights apply. Current terms also restrict specified AI/ML development/training uses and storing/caching/archiving data | provider-defined scope / provider-defined minute reset until reviewed; adjustable | **non-routable by default** until quota scope/reset evidence, actual application use, persistent-storage authority, and per-series rights are evidenced; the separate v2 2-requests/second rule is not applied to this v1 adapter |
| Nasdaq Trader | official `nasdaqlisted.txt`/`otherlisted.txt` US NMS listing/lifecycle files | none | Nasdaq publishes no numeric quota for these files. The client imposes a strict maximum of two HTTP requests per calendar day (one conditional request per official file); this is a local safety ceiling, not a vendor allowance | public service / client-imposed deployment-wide daily cap | bounded directory retrieval can route under the local cap; the first local window is explicitly persisted at zero (`baseline_mode: local_zero`) before transport, diagnostics must not describe the cap as a Nasdaq-published quota, and two-file results remain NMS-focused rather than complete OTC coverage |
| Tiingo | EOD history, search, profiles | `TIINGO_API_KEY` | Free Starter: 500 unique symbols/month, 50 requests/hour, 1,000/day, and 1 GB/month bandwidth. Tiingo's [general API documentation](https://www.tiingo.com/documentation/general) states that hourly requests reset every hour, daily requests reset at midnight EST, and monthly bandwidth resets on the first of each month at midnight EST; it does not establish whether the hourly boundary is fixed/calendar or rolling, nor the distinct-symbol monthly anchor | API key / independent distinct-symbol and hourly pools with provider-scoped rolling 31-day/one-hour safety envelopes, plus calendar-day-EST daily and calendar-month-EST bandwidth pools | EOD live-proven; response bytes and distinct provider-symbol claims are durable; routing requires a complete reviewed `TIINGO_OPERATION_BYTE_BOUNDS` map. The exact 500-symbol and 50/hour ceilings use explicit provider-scoped rolling safety envelopes by default; `TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET`, `TIINGO_REVIEWED_HOURLY_RESET`, and their independent evidence fields remain optional native-reset overrides. Fundamentals is not assumed included: verify the account's add-on entitlement before routing it. See the [general API limits](https://www.tiingo.com/documentation/general) and [pricing](https://www.tiingo.com/about/pricing) pages |
| Twelve Data | multi-timeframe candles, quote, search, US universe, and native account-usage snapshot | `TWELVE_DATA_API_KEY` | 8 credits/min and 800/day Basic; time-series responses cap at 5,000 points and each request costs one credit; documented `/api_usage` costs one credit and returns the current plan plus `api-credits-used`/`api-credits-left` headers | API key / fixed minute + UTC calendar day | bounded history is explicitly paged by start/end range and reserves `ceil(requested points / 5,000)` credits; `/stocks` discovery now sends the documented `page` + `outputsize=500` bounds and filters one asset type per page; first account snapshot uses only the explicit serialized bootstrap probe until a native pool baseline is established, then normal minute/day charging applies; the daily pool is not inferred from minute headers |
| Finnhub | profile/search, historical earnings, forward earnings calendar, and universe; candle adapter retained for higher entitlements | `FINNHUB_API_KEY` | observed free account 60 calls/min; all plans also have a 30 calls/sec hard cap | token / independent minute + second provider boundaries with explicit rolling application envelopes for each dimension | profile, historical earnings, and forward calendar live-proven; both earnings surfaces are registered under `earnings`; every reviewed operation is explicitly charged against both rate dimensions, while an operation absent from the reviewed cost profile fails closed; free stock candles returned 403 and are explicitly non-routable; future provider-native reset evidence can replace the envelopes through separate configuration |
| Marketstack | daily EOD history and venue-scoped ticker discovery | `MARKETSTACK_API_KEY`, `MARKETSTACK_DISCOVERY_EXCHANGE` | Free-plan pricing publishes 100 requests/month while the FAQ still says 1,000; the checked-in seed uses the lower ceiling and leaves the monthly boundary unresolved; EOD responses expose 100-row pagination metadata | key / provider-defined monthly window (cap conflict and reset boundary unresolved) | history transport follows returned pagination, but routing requires an operator-reviewed `MARKETSTACK_REVIEWED_MONTHLY_LIMIT`, `MARKETSTACK_REVIEWED_MONTHLY_RESET`, and `MARKETSTACK_QUOTA_EVIDENCE`; discovery additionally requires an explicit MIC/exchange code and is supplementary rather than complete US venue reconciliation |
| EODHD | daily EOD history (daily/weekly/monthly aggregation), fixture-covered Fundamentals/profile adapter, US exchange-symbol list, documented `/user` account-usage snapshot | `EODHD_API_KEY`, plus reviewed minute-pool controls for ordinary routing | [Free Starter plan](https://eodhd.com/lp/historical-eod-api) says 20 API-call credits/day and 20 requests/minute; EOD history is limited to one year. **Official-source conflict:** EODHD's [general API limits](https://eodhd.com/financial-apis/api-limits) and [Quick Start](https://eodhd.com/financial-apis/quick-start-with-our-financial-data-apis) state 1,000 requests/minute. The client keeps a conservative 20/min seed only as audit metadata and refuses ordinary routing until `EODHD_REVIEWED_MINUTE_LIMIT`, `EODHD_REVIEWED_MINUTE_RESET`, and `EODHD_MINUTE_QUOTA_EVIDENCE` identify the exact account pool; a positive reviewed provider-native limit is accepted without an arbitrary upper cap. A credentialed `/user` observation returned a stale `apiRequestsDate` and `X-RateLimit-Limit: 1200`; both remain observation-only and never widen policy until reset/evidence are reviewed. The `/user` response reports the active daily call count/limit and midnight-GMT date; native daily baseline reconciliation is accepted only when the returned date is current. Fundamentals/profile is non-routable unless the plan grants it (the supplied free key returned HTTP 403); fundamentals/options cost 10 credits and intraday/technical/news 5 when entitled | API key / provider-defined minute pool until reviewed + GMT calendar-day call-credit budget | EOD daily/weekly/monthly history, exchange-symbol list, and the bounded account-usage bootstrap remain implemented; ordinary data routing is fail-closed while account-specific minute reset/evidence remain unresolved |
| FMP | stable-API daily history, profile, stock list, and earnings calendar | `FMP_API_KEY` | The configured account reports 250 calls/day and 512 MB / 30-day bandwidth, while the current official [pricing page](https://site.financialmodelingprep.com/developer/docs/pricing) states a 500 MB free-plan pool measured over a trailing 30-day window. The client uses the conservative 500,000,000-byte ceiling and the documented rolling window; the daily-call reset remains provider-defined but is enforced by an explicit rolling 24-hour application safety envelope | key / independent provider-defined daily-request pool with rolling 24-hour application safety envelope plus documented rolling 30-day bandwidth pool | stable EOD history and `earnings-calendar` normalization are live-proven for the configured key; response bytes are durable; routing requires a complete `FMP_OPERATION_BYTE_BOUNDS` map and `FMP_BANDWIDTH_QUOTA_EVIDENCE`; `FMP_REVIEWED_DAILY_RESET`/`FMP_DAILY_QUOTA_EVIDENCE` are optional native-reset overrides, while `FMP_REVIEWED_BANDWIDTH_RESET` remains an optional future-plan override |
| Tradier | US daily history, quotes/search, current option expirations/chains with provider Greeks | `TRADIER_API_KEY` | 60/min sandbox; 120/min production market-data quota, response headers expose remaining/reset | token / minute | option endpoints normalize OCC symbols, contract fields, and nested Greeks; account live evidence required |
| MarketData.app | delayed US stocks/options candles, option expirations, current option-chain normalization, and historical/current single-contract option quotes | `MARKETDATA_APP_API_KEY` | Plan-specific: Free Forever 100/day; Starter Trial 10,000/day until configured expiry; Starter 10,000/day; Trader Trial/Trader 100,000/day. Resets 09:30 ET; 50 account-wide concurrent requests; free/trial data is at least 24h delayed and limited to one year; stock candles cost 1 credit per 1,000 returned candles (date-granular requests use a conservative full-day bound for intraday resolutions); expirations cost 1 credit/call, current chain/quote calls cost per returned contract/symbol, historical quotes/chains per 1,000 observations/contracts | key / reset-day credits + durable in-flight concurrency; configure exact plan, matching limit, and timezone-aware trial expiry separately per environment; trial quota automatically falls back to Free Forever 100/day after expiry; response-dependent candle/option costs must be estimated or bounded before routing; option-chain admission additionally requires `MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS` | credentialed daily-candle, expirations/option-chain, and historical option-quote adapter paths live-proven 2026-09-12; account `/user/` headers expose quota state but not Starter Trial vs paid Starter, so operator configuration is authoritative; authenticated counters persist across sessions without widening routing limits |
| IBKR | read-only Client Portal Gateway security search, instrument profile, raw historical OHLCV for equities and futures, and latest-price snapshots; options-specific methods remain unimplemented | `IBKR_READ_ONLY_URL`, `IBKR_READ_ONLY_SESSION_COOKIE`, optional `IBKR_CONID_MAP` | Global 10 requests/sec/session; REST historical endpoint 50 requests/minute and max 1,000 bars per response; the separate WebSocket historical-streaming API allows at most 5 concurrent subscriptions (not applied to this REST adapter); expired futures history is unavailable beyond two years after expiry; endpoint-specific pacing and penalty-box behavior apply | authenticated gateway session / rolling endpoint windows; interactive gateway login is required and may need to be renewed daily | concrete adapter is fixture-covered; raw history/latest/profile remain non-routable until a gateway session and bounded live evidence are supplied; futures should use an explicit provider `conid` mapping when symbol search is ambiguous; adjusted history is filtered before routing |
| xStocks (Backed) | tokenized equity/ETF catalogue, deployments, indicative prices, multipliers, supply and corporate actions | none for documented public reads; optional `XSTOCKS_API_KEY` | Public API responses exposed a shared 1,000-request rolling-minute `X-RateLimit-Limit`/`Remaining`/`Reset` contract across assets and corporate-actions endpoints; verified 2026-09-14 and reconciled only on an exact limit match | public API / rolling minute; provider headers are retained and cumulative use is durably reconciled | bounded public metadata, price, and corporate-action reads are proven; still non-routable until API automation/partner terms and deployment jurisdiction/data-use eligibility are established. Runtime admission additionally requires the non-secret `XSTOCKS_MARKET_DATA_USE_AUTHORIZED`, `XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE`, `XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE=internal_automated_persistent_nonredistributed`, `XSTOCKS_MARKET_DATA_USE_REVIEWED_AT`, `XSTOCKS_MARKET_DATA_USE_JURISDICTION_AUTHORIZED`, and `XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE` controls; an optional expiry can revoke admission automatically |
| Robinhood Chain Stock Tokens | tokenized-stock catalogue, chain deployments, multiplier, indicative bid/ask and corporate actions | none for documented public reads | 60 requests/sec for the public Stock Token API; cached responses and edge `429` responses apply | public IP / rolling second | bounded live asset + quote probe passed; read-only and non-routable until entitlement is promoted |
| Bybit xStocks | xStocks spot instrument catalogue and ticker bid/ask/last | none for public market-data endpoints | Anonymous V5 traffic is bounded by the documented 600 HTTP requests per 5 seconds per IP ceiling. The separate rolling endpoint/UID headers describe authenticated API-rate state and are not a prerequisite for these unauthenticated market endpoints; they are retained as telemetry if present but are not conflated with the IP pool | shared outbound IP / rolling 5 seconds | bounded live asset + ticker probe is transport evidence only; production routing is now fail-closed until the deployment proves eligible non-US/non-Mainland-China egress and records explicit automated/persistent-use authority through `BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED`, `BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE`, `BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE=internal_automated_persistent_nonredistributed`, `BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT`, `BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED`, and `BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE`; an optional expiry can revoke admission automatically |
| Gate TradFi stock API | public US stock-token symbol catalogue and order-book bid/ask | none for public symbol/order-book endpoints | 5 requests/sec/IP for each documented public TradFi stock endpoint (`/stock/symbols`, `/stock/symbols/detail`, `/stock/market/{symbol}/orderbook`) | IP / rolling | bounded live symbol + order-book probe passed; the runtime applies a conservative aggregate 5-request/sec capability window |
| Kraken xStocks | provider-native xStocks pair discovery and public ticker when such pairs are published | none | Kraken public safe-frequency guidance is approximately 1 request/sec; pair/IP accounting applies | IP/pair / rolling | live catalogue probe passed with no currently published xStocks pair; no synthetic mapping is created |
| Ondo Global Markets | authenticated tokenized US stock/ETF metadata, chain addresses/ISIN/tags, indicative latest prices, display-only primary/underlying market summaries (including 24-hour price history and underlying metrics), OHLC candles, and canonical daily history with local WEEK/MONTH/YEAR rollups | `ONDO_GLOBAL_MARKETS_API_KEY` | OpenAPI documents HTTP 429/account rate limiting but no numeric quota; endpoint caching and display-only/non-oracle restrictions apply | API key/account / provider-defined | concrete metadata/latest-price/market-summary/OHLC/history adapter is fixture-covered; no live credential evidence yet; remains non-routable until account terms/quota are reviewed |
| Dinari | partner-authenticated dShare stock/ETF metadata, provider UUIDs, CAIP-10 deployments, FIGI/CIK/CUSIP metadata, current fair price, bid/ask quote, DAY/WEEK/MONTH/YEAR aggregate history, news, dividends, and splits | `DINARI_API_KEY_ID`, `DINARI_API_SECRET_KEY`, `DINARI_API_BASE_URL` | Numeric account/partner quota is not published; free Sandbox access is available while evaluating/building, while production API access is a commercial partner service that officially starts at **$2,000/month**; US SIP/NBBO quotes are metered and may incur per-query fees, with display/redistribution and partner-approval requirements ([official partner fees](https://docs.dinari.com/docs/fees)) | API key ID/secret + partner account / provider-defined | replacement Sandbox pair live-proven 2026-09-16 against https://api-enterprise.sandbox.dinari.com/api/v2 via the explicit 20-request application-capped canary (14 HTTP requests observed); stock and split catalogues use the current cursor contract (`limit`/`order`/`next`) with explicit legacy list fallback and explicit in-order continuation; ticker-like lookups use Dinari's documented `symbols[]` filter rather than assuming the first page is complete; UUID downstream reads reuse only validated records from the current provider instance, and a Dinari-only two-retry HTTP-500 recovery is bounded/telemetrized; remains non-routable until commercial, US eligibility, quota, and redistribution terms are reviewed |
| Alpaca tokenization network | catalogue-only tokenization-network candidate, distinct from Alpaca market-data keys | authorized-participant access required | Market-data credentials do not entitle tokenization-network access | account / unknown | descriptor only; not routable |
| yfinance | legacy broad fallback, options/futures compatibility only | none | No official quota/SLA; unofficial scraping | unknown | legacy-only and disabled by default |
| ETF holdings internal | platform's issuer/SEC holdings ingestion | internal configuration | Internal job/provider budgets, not an external market-data API | internal | generic bridge only; issuer-specific work remains on ETF branch |

Nasdaq Trader's directory is listing evidence, not a complete delisting-event feed.
The adapter excludes test issues, retains Nasdaq Financial Status Indicators
(including deficient or bankrupt-but-listed issues), and uses repeated complete
absence plus separate lifecycle evidence before marking a listing inactive.
See the [official symbol-directory definitions](https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs).

The complete-OTC source decision is intentionally explicit. FINRA's public
catalog documents the OTC Daily List but does not establish a current complete
`otcSecurityMaster` dataset. OTC Markets publishes an [Overnight Security
Master specification](https://www.otcmarkets.com/files/OTC%20Markets%20Overnight%20Security%20Master%20Specification.pdf)
and a [US Security Master specification](https://www.otcmarkets.com/files/US-Security-Master-File-Specification%20-%20v1.0.pdf),
including SFTP delivery details, but those documents are specifications rather
than an access or redistribution grant. Until a delivery account, terms,
quota, cadence, and complete-coverage evidence are authorized, the candidate
must remain non-routable and FINRA Daily List remains lifecycle-only.
The adapter also sends `If-None-Match` and `If-Modified-Since` on subsequent
polls when Nasdaq returns `ETag` or `Last-Modified`, reusing the cached parsed
file on a `304 Not Modified`. This reduces repeated downloads without
inventing a numeric provider allowance. Because Nasdaq does not publish a
numeric polling quota, the client separately limits itself to one conditional
request per official file per calendar day (two requests total); this is a
local safety policy, not a vendor-reviewed quota.

The FRED adapter uses the v1 endpoint. Its [v1 errors documentation](https://fred.stlouisfed.org/docs/api/fred/errors.html)
states that up to 120 requests per minute are allowed before HTTP 429, but it
does not publish the enforcement scope. The [v1 API terms](https://fred.stlouisfed.org/legal/terms/)
also allow the provider to adjust bandwidth and transaction limits. The
separate [v2 errors documentation](https://fred.stlouisfed.org/docs/api/fred/v2/errors.html)
mentions a 2-requests/second threshold for v2; the runtime deliberately does
not apply that v2 rule to the v1 adapter. FRED's [current terms](https://fred.stlouisfed.org/legal/terms/)
restrict storing, caching, or archiving FRED content by default and prohibit
specified AI/ML development and training uses absent authorization. Some
series also contain third-party data with separate rights. Since this
application persists observations and may use data in automated workflows,
FRED remains non-routable until written authority covers the actual
application use, persistence, and each requested series. A former boolean
“terms reviewed” switch is not proof. Promotion requires reviewed quota
scope/evidence, `FRED_PERSISTED_STORAGE_AUTHORIZED=true` plus
`FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE`,
`FRED_AUTOMATED_USE_AUTHORIZED=true` plus
`FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE`, and a non-empty
`FRED_SERIES_RIGHTS_EVIDENCE` JSON map keyed by every FRED series ID used. The
quota controls are `FRED_REVIEWED_LIMIT_SCOPE` (`api_key`, `account`, `ip`, or
`deployment`), `FRED_REVIEWED_REQUESTS_PER_MINUTE` (positive and no greater
than 120), `FRED_REVIEWED_QUOTA_EVIDENCE`, `FRED_REVIEWED_RESET`, and
`FRED_RESET_EVIDENCE`. FRED v1 does not publish the reset boundary, so the
reset label must be an admission-safe reviewed value backed by current
provider/account evidence; no rolling window is inferred. No provider request is made while
any applicable control is missing; a passing local policy-gate test is not
live API evidence. The terms permit FRED to change bandwidth/transaction
limits, require a non-endorsement notice, and reserve series-specific rights.
Missing `FRED_API_KEY` raises an explicit
`ProviderNotConfiguredError`; HTTP 429/418 responses are preserved as typed
capacity failures with provider headers and `Retry-After` timestamps rather
than returning an empty series or price. Do not enable a new series merely
because another series has an authority reference.

Coinbase Exchange publishes a technical public REST ceiling of 10
requests/second/IP with a burst of 15, but that limit is not permission to use
the data in this application. Its [market-data terms](https://www.coinbase.com/en-in/legal/market_data)
restrict use in AI/ML development, training, or operation absent prior express
written consent, as well as redistribution. Consequently no live Coinbase
request or normal routing is allowed unless the exact intended automated,
persistent, non-redistributing use has written authority recorded through
`COINBASE_MARKET_DATA_USE_AUTHORIZED`,
`COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE`,
`COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE=internal_automated_persistent_nonredistributed`,
and a current `COINBASE_MARKET_DATA_USE_REVIEWED_AT` (with an optional expiry).
A compliant
10 requests/second limiter does not satisfy this legal gate.
Marketstack's [pricing page](https://marketstack.com/pricing) publishes the
free 100-request/month plan; its [FAQ](https://marketstack.com/faq) contains a
conflicting 1,000-request sentence, so the runtime records the lower 100 limit
and remains gated on account/terms review. Marketstack counts one request per
ticker even when a request contains multiple symbols, does not count API errors,
and documents notifications at 75%, 90%, and 100% of the allowance. Its
[overage documentation](https://marketstack.com/billing-overages-documentation)
describes a maximum 5% overdraft and disabling at 120% unless overage billing
is enabled. Those are account-billing behaviors, not permission to route: the
monthly reset instant is still unpublished, so the provider remains
fail-closed until the reset boundary and account overage setting are reviewed.
The explicit
`MARKETSTACK_DISCOVERY_EXCHANGE` requirement is operation-scoped: ticker
discovery/reconciliation stays disabled without a reviewed MIC, while EOD
history and quote reads may route with the API key alone.

Tradier is intentionally configured against the production market-data base URL
in this branch, so its checked-in 120/minute contract applies only to a
production token. Tradier's [endpoint guide](https://docs.tradier.com/docs/endpoints)
states that production brokerage APIs require a Tradier brokerage account,
partner, or advisor relationship; the sandbox requires a brokerage signup and a
paper-trading token. A sandbox token must not be placed in `TRADIER_API_KEY`
while the production contract is active: supporting sandbox mode requires a
separate provider identity and 60/minute quota seed rather than silently
reusing the production policy. Tradier's documented JSON wrappers are handled
explicitly by the adapter: history rows are under `history.day|week|month`,
search rows under `securities.security`, and single-row responses may be
objects rather than arrays.
The concrete option adapter also uses the documented
`markets/options/expirations` and `markets/options/chains` endpoints. It keeps
the provider OCC symbol separate from the canonical option contract, preserves
the raw row, normalizes calls/puts, bid/ask/mark/volume/open interest, and
records nested provider Greeks when present. Each endpoint reserves one
production-token request; no sandbox token is treated as production evidence.

Tiingo and FMP have plan bandwidth pools but do not publish one universal
maximum response size for every adapter operation. The runtime therefore does
not invent a byte ceiling. An operator who has reviewed the current endpoint
contract may set complete JSON maps in `TIINGO_OPERATION_BYTE_BOUNDS` and
`FMP_OPERATION_BYTE_BOUNDS`, for example:

```env
# Do not copy guessed values: populate each map only with reviewed provider
# endpoint ceilings. Empty or partial maps intentionally remain non-routable.
TIINGO_OPERATION_BYTE_BOUNDS={}
TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET=
TIINGO_REVIEWED_HOURLY_RESET=
TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE=
TIINGO_HOURLY_QUOTA_EVIDENCE=
FMP_OPERATION_BYTE_BOUNDS={}
FMP_REVIEWED_DAILY_RESET=
# Optional override; the current official free-plan contract is rolling_30_days.
FMP_REVIEWED_BANDWIDTH_RESET=
FMP_DAILY_QUOTA_EVIDENCE=
FMP_BANDWIDTH_QUOTA_EVIDENCE=
```

Every operation exposed by the relevant adapter must be present with a positive
bound, including `get_current_price`, which uses the adapter's bounded latest
history request path, `bulk_fetch`, which is used by the deep-history worker,
and FMP's `fetch_market_events`, which calls the stable earnings calendar.
Complete maps move the provider's documented bandwidth pool into the
same durable multidimensional reservation path as request limits; response
bytes settle the reservation after execution. Tiingo additionally publishes a
500-unique-symbol monthly pool, which cannot be represented as one unit per
request. The provider's general API documentation fixes the 1,000-request
daily pool at midnight EST and the monthly bandwidth pool at the first of each
month at midnight EST. It says only that hourly requests reset every hour,
without a timezone/boundary contract, and does not define the unique-symbol
pool's monthly reset anchor. The local identity ledger therefore records
distinct-symbol usage under an explicit provider-scoped rolling 31-day safety
envelope, while the hourly pool uses an explicit rolling one-hour safety
envelope. The provider-defined labels remain visible for audit and reviewed
native reset/evidence settings may replace the safety envelopes; no generic
cross-provider window is inferred. Repeated symbols and multi-symbol
operations are tracked by `provider_quota_identity`.
The currently configured Starter plan does not establish a Fundamentals
add-on entitlement, so Fundamentals must stay gated until separately
verified. Missing, zero, malformed, or partial byte maps still leave
Tiingo/FMP routing non-routable; the symbol pool itself is not approximated as
request count.

The platform uses a capability-based provider chain.  For each data type the runtime selects the
highest-scoring available provider, falls back to the next, and so on.  Initial priorities below
reflect `base_priority` seeding; the runtime's EWMA health scores refine ordering over time.

Optional REST adapters also reject provider-native JSON error envelopes that
arrive with HTTP 200 (for example, Twelve Data `status=error`, FMP `Error
Message`, Finnhub `error`, or MarketData.app `s=error`). These become typed
provider failures, and rate/quota wording becomes a typed capacity failure;
none is silently normalized to an empty bar/profile result.

### US venue coverage boundary

The official Nasdaq Trader `nasdaqlisted.txt`/`otherlisted.txt` files and SEC
`company_tickers_exchange.json` are implemented as listing/lifecycle evidence
for NMS and SEC-reporting issuers. They are not a complete OTC Markets listing
or delisting feed. The reconciler therefore records a partial/failed run when
the source page set is incomplete and never presents NMS/SEC evidence as proof
of complete OTC coverage. Closing that gate requires an operator-approved OTC
source with documented terms and a verified quota contract; no undocumented
scraping endpoint is substituted.

For an NMS run to count as complete lifecycle evidence, every declared Nasdaq
total must equal the number of rows actually collected. A cursor that skips
rows, terminates early, or changes its declared total fails the run and cannot
contribute absence evidence. Rows whose venue is missing or cannot be mapped to
the supported Nasdaq Trader MIC set (`XNAS`, `XNYS`, `ARCX`, `XASE`, `BATS`,
`IEXG`) likewise fail closed instead of becoming venue-less listings. Successful
NMS runs persist deterministic `venue_coverage` provenance with expected,
observed, missing, and per-MIC row counts; this makes a complete snapshot with
no rows for a particular venue distinguishable from malformed venue evidence.
The FINRA OTC directory remains a candidate-only source until its independent
availability, completeness, terms, redistribution, polling, and operation-cost
controls are reviewed; it never receives NMS absence authority.

### Tokenized securities boundary

Tokenized products are first-class instruments, not ticker aliases. Each stored
instrument receives a stable provider-scoped `domain_key` and retains the
provider asset ID, chain/network, contract deployment(s), token ISIN when
published, underlying symbol and every published stable identifier (FIGI,
composite FIGI, ISIN, or CUSIP), multiplier, supply, backing classification,
and corporate-action payload. Underlying linkage is stable-ID-first: the
canonical instrument fields, domain keys, and active identifier registry are
checked in FIGI/composite-FIGI/ISIN/CUSIP order before any symbol lookup. If
multiple supplied identifiers disagree, or a supplied identifier is not
resolved uniquely, the relationship remains unresolved; it is never weakened
to a ticker match. Ticker fallback is retained only when no stable underlying
identifier is supplied and exactly one active listing has that symbol; a
collision leaves the relationship unresolved rather than merging two
securities.

The current public adapters are read-only. They do not submit orders, mint,
redeem, transfer tokens, or index wallets. Tokenized perpetuals and other
derivatives remain separate derivative instruments. xStocks and Robinhood
expose issuer/product metadata and indicative prices; Bybit, Gate, and Kraken
expose exchange-native market surfaces. Dinari exposes provider UUID-based
metadata, fair price/quote, aggregate history, news, dividends, and splits;
Ondo exposes chain/ISIN metadata, indicative prices, display-only primary and
underlying market summaries, and OHLC candles for both token and underlying
markets. Its market summary preserves 24-hour price-history points,
holder/multiplier/session metadata, and underlying 52-week, volume,
shares-outstanding, and market-cap fields without inventing omitted values. A provider returning no current
xStocks pairs is recorded as an empty catalogue, never as evidence that a
traditional share is the same token.

xStocks has an additional eligibility gate: its [official legal notice](https://xstocks.com/us)
states that xStocks are not available in the United States or to U.S. persons,
and its [partner page](https://xstocks.com/partner) says integrations are
subject to eligibility review and partners must implement geographic
compliance. The developer guide does say public metadata endpoints need no API
key, but that does not establish permission for automated continuous
collection: the linked [Terms of Service](https://xstocks.com/documents/xstocks-terms-of-service.pdf)
include automated-retrieval/use restrictions for the Site/Services. Therefore
the quota is now correctly recorded and enforced, while xStocks remains
non-routable until the API-specific terms/partner permission and this
deployment's jurisdiction/data-use eligibility are confirmed. Public responses
may still be exercised by the bounded validation suite as transport evidence;
they are not proof of production rights.

The same fail-closed rule is enforced by normal application routing and by
live preflight. Configure the `XSTOCKS_MARKET_DATA_USE_*` controls separately
in each environment (the expiry is optional but, when supplied, must be
future-dated); a key or a successful public read alone never makes xStocks
routable.

Bybit xStocks is gated independently. Bybit documents that requests from
U.S. and Mainland-China IP addresses are restricted, so its public 600/5-second
IP ceiling is not sufficient evidence for application routing. Configure the
`BYBIT_XSTOCKS_MARKET_DATA_USE_*` controls only after verifying the deployment's
actual egress and the permitted automated/persistent use; missing or expired
controls prevent the adapter from making a transport request.

Dinari's [stock-data guide](https://docs.dinari.com/docs/stock-data) documents
provider-native Stock UUIDs, aggregate DAY/WEEK/MONTH/YEAR history, news, and
live price/quote endpoints. Its [pricing guide](https://docs.dinari.com/docs/pricing-quotes)
distinguishes the computed fair price from bid/ask quotes, and notes that US
SIP/NBBO data is metered. Dinari's [partner-fees guide](https://docs.dinari.com/docs/fees)
states that production API access starts at $2,000/month; Sandbox access is the
appropriate environment for evaluation and fixture/live transport validation,
not production entitlement evidence. The adapter never treats CIK/CUSIP/FIGI fields as the
token's primary identity and never fabricates volume for the aggregate history.
The canonical `Y1` timeframe is a calendar-year bucket for this tokenized
history bridge; ordinary market-data adapters must advertise an explicit
annual interval or remain unsupported rather than mapping `Y1` to daily data.
Dinari's [US-customer requirements](https://docs.dinari.com/docs/us) make partner
approval, regulatory, data-security, and redistribution review a deployment
gate, so having a key alone does not make this provider routable.

The current Sandbox key can be exercised only by the explicit non-persisting
live canary (`--dinari-sandbox-canary --provider dinari`). That mode requires
the non-secret operator controls `DINARI_SANDBOX_CANARY_AUTHORIZED`,
`DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE`, and the positive per-process
`DINARI_SANDBOX_CANARY_MAX_REQUESTS` cap. The cap is an application safety
budget, not a claim about Dinari's unpublished Sandbox entitlement; ordinary
provider routing remains disabled until the commercial, quota, eligibility, and
redistribution review is complete.

Dinari's SEC CIK is retained as the token detail's first-class
`underlying_cik`, separate from the provider Stock UUID. When an issuer with
that CIK is already materialized, `underlying_issuer_id` links to it; the
refresh never creates an issuer implicitly from token metadata and records an
unresolved issuer link otherwise.

Ondo's [API overview](https://docs.ondo.finance/api-reference/overview),
[market-data endpoint](https://docs.ondo.finance/api-reference/assets/get-market-data-for-an-asset),
and [OpenAPI contract](https://docs.ondo.finance/openapi.json) document the
API-key protected metadata, latest-price, market-summary, and OHLC endpoints.
The OHLC adapter accepts
only the provider's published interval/range pairs and returns primary-token
and underlying-stock candles separately. The canonical tokenized-history
adapter uses Ondo's documented daily `all` range for the primary token and
performs deterministic local WEEK/MONTH/YEAR rollups when requested; the
underlying-stock rows remain separate and are never silently substituted for
the token. Ondo explicitly marks price feeds as display-only and not suitable
as an oracle; its OpenAPI documents HTTP 429 but
does not publish a numeric quota, so this provider remains fail-closed pending
account-specific terms and usage evidence.

The runtime records provider-specific quota dimensions and refuses to route a
tokenized provider when any dimension is unknown, weighted per endpoint, or
requires response-header/account enforcement that is not yet fully modeled.
Quote refresh accounting also follows the adapters' actual request shape. The
standard tokenized `get_tokenized_price` operations reserve two provider
requests (asset metadata plus quote/order-book), while discovery and asset reads
reserve one. Dinari's quote, historical, news, dividend, and split operations,
and Ondo's market-summary, OHLC, and canonical historical operations likewise
reserve two requests
because each resolves
provider metadata before the data read. Dinari's symbol-scoped corporate-action
operation reserves three requests (metadata, dividends, and splits); the global
split-only path safely uses the same bound because each invocation reads one
explicit cursor page. Dinari split callers may request a later page with the
durable opaque `next` cursor from the preceding page, including after a
provider-instance restart; the adapter rejects missing/repeated cursors and
returns an empty page only after an observed terminal cursor. The refresh
service applies a per-job page fairness budget and persists the continuation so
later pages are eventually ingested rather than excluded. UUID metadata lookups refuse a paginated first-page miss
instead of returning a false not-found result; callers must first advance the
documented catalogue cursor explicitly (for example through
`discover_tokenized_assets(page=...)`).
Robinhood additionally reserves four
requests: one asset lookup plus the bounded three-attempt quote retry worst
case. This prevents a successful quote response or bounded retry from being
recorded as fewer requests than the adapter may actually make. Dinari's history
deliberately returns aggregate OHLC without inventing volume; Ondo's OHLC
interval/range combinations are validated against the provider's published
finite matrix and every candle retains explicit primary-versus-underlying
market scope. Both adapters preserve raw provider payloads for provenance.
Bybit's official [rate-limit contract](https://bybit-exchange.github.io/docs/v5/rate-limit)
publishes a 600/5-second/IP outer ceiling and separate rolling per-second
endpoint/UID limits. These xStocks reads call the documented anonymous public
market endpoints (`instruments-info` and `tickers`), so the adapter enforces
the shared IP ceiling; it does not require authenticated endpoint/UID headers
that these public responses do not emit. Those headers remain telemetry if an
edge begins returning them, and are not incorrectly reconciled against the IP
pool. Bybit also documents that API requests from U.S. or Mainland-China IPs
are restricted; the public source must therefore run only from an eligible
egress region. Gate's public stock contract is
static and IP-scoped in the official provider-wide rate-limit table, so its
public read route is eligible after the bounded live probe; any returned
remaining-limit headers remain observational rather than a routing
prerequisite. The
live matrix is explicit and bounded:

```sh
RUN_LIVE_PROVIDER_TESTS=1 rtk uv run --project backend pytest \
  tests/live/test_tokenized_providers_live.py -m live --no-header -q --no-cov
```

The latest verified run passed all seven public probes, including bounded
historical/upcoming corporate-action reads for xStocks and Robinhood.
Robinhood's public price edge returned `local_rate_limited` during one run; its adapter now uses a
finite provider-specific retry budget, honors `Retry-After` when present, and
surfaces repeated 429s. The Kraken catalogue returned no current xStocks pair.
That evidence is retained as a routing/coverage fact, not hidden by a generic
retry or an invented symbol.

Persisted tokenized products can also receive bounded quote refreshes through
the normal provider runtime. Set `TOKENIZED_ASSET_REFRESH_ENABLED=true` and a
conservative `TOKENIZED_ASSET_REFRESH_MAX_ASSETS` in the backend and worker
environment to enable the opt-in 15-minute schedule. Each quote uses the
provider asset ID as its usage identity, reserves documented quota dimensions
before the request, records transport telemetry, and stores a separate
`LatestPriceSnapshot` for the token instrument. The schedule is disabled by
default and never calls a provider during evaluation.

Historical tokenized aggregates use a separate durable path from quote
polling. Set `TOKENIZED_HISTORICAL_REFRESH_ENABLED=true` only after the
provider-specific history quota and redistribution terms are reviewed, and set
bounded `TOKENIZED_HISTORICAL_REFRESH_MAX_ASSETS` plus
`TOKENIZED_HISTORICAL_REFRESH_TIMESPAN` (`DAY`, `WEEK`, `MONTH`, or `YEAR`) in both
backend and worker environments. The daily worker currently admits only
providers exposing `fetch_tokenized_historical_prices` (Dinari and Ondo), routes
by the owning provider asset ID, and persists through the canonical
`OHLCVBar`/`MarketSeries` path. It preserves provider-native raw `24_7`
candles, stores the raw response provenance, and leaves volume, VWAP, and
adjustment fields unset/RAW when the provider does not supply them; yearly
aggregates are admitted only when the selected adapter explicitly supports
them. Unknown
operation costs or entitlements remain non-routable, and the feature is
disabled by default.

Historical aggregates are routed through the dedicated
`tokenized_historical_prices` capability (Dinari and Ondo), rather than
being charged or admitted as generic `tokenized_assets` traffic. This keeps
catalogue/quote entitlements independent from historical-series entitlements;
providers without the explicit `fetch_tokenized_historical_prices` adapter
surface cannot be selected for the worker.

Tokenized catalogue discovery is separately scheduled once daily and remains
disabled by default. After provider quota and terms review, enable
`TOKENIZED_CATALOG_REFRESH_ENABLED` and set bounded
`TOKENIZED_CATALOG_REFRESH_MAX_PAGES` /
`TOKENIZED_CATALOG_REFRESH_PAGE_SIZE` in both backend and worker environments.
The refresh uses the provider runtime for every page, reports a full final
page as `partial`, and preserves redacted provider/page failures while later
qualified providers continue.

Corporate actions use a dedicated `tokenized_corporate_actions` capability and
a separate opt-in schedule so an operator can budget event-feed quota
independently from quote polling. Set
`TOKENIZED_EVENT_REFRESH_ENABLED=true`, with bounded
`TOKENIZED_EVENT_REFRESH_MAX_PROVIDERS`,
`TOKENIZED_EVENT_REFRESH_MAX_PAGES`, and
`TOKENIZED_EVENT_REFRESH_PAGE_SIZE`, in both the backend and worker
environment. xStocks is read in separate historical and upcoming requests;
Robinhood exposes one combined action feed; Dinari exposes global splits and
symbol-scoped dividend/split rows but has no upcoming filter, so that semantic
is rejected rather than guessed. Every request uses the exact
`fetch_tokenized_corporate_actions` operation cost declared for that provider.
Rows are persisted as provisional `MarketEvent` records with the complete raw
provider payload. Per-job page limits persist the exact numeric page or opaque
cursor and resume it on later runs; they never discard later action pages. A
token is linked only when an explicit provider asset ID or
unique token symbol matches the stored token detail; otherwise the event is
retained unlinked for later reconciliation rather than guessed onto an
underlying ticker. Exchange token adapters without an action endpoint are
reported as unsupported and never invoked.

Market-wide event feeds use the separate `market_events` capability. The
backend service `app.services.market_events.refresh_market_events` fans out a
bounded window to selected providers that advertise this capability and
persists each `MarketEventRecord` idempotently by `(source, event_key)`. Exact
provider-symbol mappings and unique SEC CIK matches are linked to canonical
instruments/issuers; ticker-only matches that resolve to more than one active
venue remain unlinked for reconciliation. A provider failure is returned as a
per-provider result while successful observations from other providers are
retained. The ARQ entry point is disabled by default; enable it in both backend
and worker environments with:

```env
MARKET_EVENTS_REFRESH_ENABLED=true
MARKET_EVENTS_REFRESH_LOOKAHEAD_DAYS=90
MARKET_EVENTS_REFRESH_MAX_PROVIDERS=8
MARKET_EVENTS_PRELISTING_ENABLED=true
MARKET_EVENTS_PRELISTING_LOOKAHEAD_DAYS=90
MARKET_EVENTS_PRELISTING_MAX_EVENTS=500
```

The worker refreshes a bounded UTC `today`-through-lookahead window once per
day. Provider-specific operation costs, entitlement gates, and quota
dimensions remain authoritative, so enabling the schedule cannot make an
unknown or non-routable provider callable. This backend persistence path does
not require a provider call on reads: authenticated clients can query the
bounded persisted market-event calendar at `GET /api/v1/calendar/market-events`
with inclusive `start`/`end` dates and optional `event_type`, `source`,
`instrument_id`, `issuer_id`, and `limit` filters. Events with only a timestamp
remain queryable when no effective date was published, and provider payloads
and provisional status are returned for provenance-aware consumers.
After persistence, the backend runs the bounded `market_event_consensus_v1`
reconciliation pass. It groups only exact event-type plus canonical target
(instrument, issuer, or explicit venue MIC) plus occurrence-date matches. Rows
without a stable target/date remain ungrouped. A group with multiple sources is
`corroborated` only when every compared semantic field agrees; differing values
become a durable `conflicted` group with per-source values, while a single
source remains `single_source`. Provider rows and raw payloads are never
overwritten. Operators can inspect these groups through the authenticated
admin-only `GET /api/v1/market-data/event-consensus` endpoint, filtered by
status, event type, instrument, or issuer. Reconciliation is quota/fairness
bounded but uses durable event-ID continuation state keyed by the requested
date window, so a later invocation resumes after the last processed row rather
than restarting at row zero and starving later observations. The same durable
continuation protects opt-in future-listing materialization and promotion; an
ambiguous early candidate cannot starve later candidates. Every persisted
event is eventually considered, while the raw provider row remains immutable.
Future IPO/IPO-pipeline observations
can additionally be materialized by the opt-in
`app.services.market_event_prelisting` workflow. It creates one auditable
candidate per consensus group. An inactive `provisional` stock instrument is
created only after a corroborated (or explicitly resolved) multi-provider
consensus supplies the same valid symbol and company name, plus either the
same venue MIC in every observation or one shared FIGI/ISIN/CUSIP observed by
at least two providers. Single-source, missing-field, conflicting-symbol/name/
identifier, and unresolved-venue evidence is retained as a quarantined
candidate and cannot create or route an instrument. Promotion still requires
one unique active FIGI/ISIN/CUSIP match, or an exact provider-symbol plus
exchange-MIC match across provider sources. Operators can inspect candidates
via the admin-only `GET /api/v1/market-data/prelisting-candidates` endpoint.
This is still a backend candidate layer, not a frontend calendar authority; no
frontend surface is added by this branch.

EDGAR's filing-driven IPO pipeline can be scanned across the known issuer table
through a separately disabled `MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_ENABLED`
worker. Its durable cursor advances through issuer CIKs in bounded batches and
records `partial` versus `complete` cycles in `market_event_scan_state`; this is
an auditable best-effort enrichment layer, not proof of global SEC coverage.

The separately disabled `MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED` worker
pages SEC's `company_tickers.json` ticker-association file into unique CIK
batches and reuses the bounded submissions parser. SEC explicitly warns that
these files do not guarantee accuracy or scope; traversing every row is not
complete US-listed issuer/security or NMS/OTC venue reconciliation. The durable
report is a candidate/filing-enrichment source, not a security-master or
tradability authority. See the [SEC API guide](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
and [SEC access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

The durable offset is pinned to a source fingerprint. If SEC's association
snapshot changes mid-cycle, the scan fails and restarts from page zero rather
than combining snapshots. A dry scan
(`MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ISSUER_MATERIALIZATION_MODE=disabled`)
reports `missing_issuer_candidates`, `existing_issuers`, and identity conflicts
without writing issuer rows. Only after an operator inspects the *complete,
clean* dry-cycle report may the exact `completed_cycle_count` be supplied via
`MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_REVIEWED_CYCLE_COUNT` alongside
`create_missing`. The service verifies that the number is the latest completed
cycle and that SEC's source fingerprint still matches. Approval is one-cycle
only; a failed/dirty cycle, conflict, source change, or intervening cycle
requires a new clean dry scan and review. Materialization creates only missing
`Issuer` rows from the SEC-conformed company name and CIK, records source/ticker
provenance, and never creates instruments/listings, changes existing names,
or deactivates records.

SEC directory candidate reports are append-only across scan cycles. The filing
parser also retains every matching prospectus/registration filing in each
retrieved submissions response; local batch settings are compatibility and
fairness controls, not retention limits.

Scanning requires a positive,
deployment-reviewed `MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_SUBMISSIONS_REQUESTS`
bound; one submissions request is attempted per CIK in each worker invocation,
and the bound must be at least
`MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_ISSUERS`. This is a per-invocation
ceiling, not a provider daily allowance. Zero stays fail-closed. SEC's
published 10 requests/second limit is an aggregate speed ceiling, not a
daily/monthly request allowance or approval to run a full scan. The worker is
scheduled daily when enabled, but manual retries add invocations; the
deployment owner must set and monitor the operational budget accordingly.
The separate NMS/OTC security-master reconciliation remains required for US
venue completeness.

| Provider   | Role        | Auth required           | Cost     |
|------------|-------------|-------------------------|----------|
| alpaca     | Primary     | API key + secret        | Free     |
| fred       | Primary     | API key                 | Free     |
| binance    | Primary candidate (weight-accounting gate) | None | Free |
| coingecko  | Primary     | Free demo API key       | Free     |
| edgar      | Primary     | Contact User-Agent      | Free     |
| yfinance   | Explicit legacy/options fallback only | None (unofficial) | Free, no SLA |
| openfigi   | Supplementary | Optional API key      | Free     |
| massive    | Optional reference/metadata/IPO-calendar corroboration | Optional API key | Free tier / 5 requests/minute |
| alpha_vantage | Optional daily-history, IPO-calendar, and forward-earnings corroboration | Optional API key | Free tier / 25 requests/day |
| tiingo / twelve_data | Optional EOD/intraday history | API key | Free/low-cost quota |
| finnhub | Optional intraday/profile/search | API key | Free/low-cost quota |
| marketstack / eodhd / fmp | Optional EOD/history/profile | API key | Free/low-cost quota |

Concrete adapters now exist for the cheap/keyless exchange and REST surfaces
listed above (`coinbase`, `kraken`, `tradier`, and `marketdata_app` included).
IBKR has a concrete read-only Client Portal Gateway adapter for profile/search,
raw historical bars for equities and futures, and latest-price snapshots. It
intentionally does not automate the gateway's interactive login, does not
claim options methods that are not implemented, and refuses to label raw bars
as adjusted. Futures are addressed by the provider's contract identifier
(`conid`); callers should configure `IBKR_CONID_MAP` when a futures symbol is
ambiguous, and expired-futures history is subject to IBKR's two-year limit.
Its documented 10-requests/second session ceiling, 50 REST historical-requests/
minute ceiling, and 1,000-bar response cap are recorded. The five-concurrent
limit belongs to WebSocket `smh` historical streaming, not the REST endpoint
used by this adapter, so it is not inherited by REST routing. The adapter
remains non-routable until a gateway session and bounded live evidence are
supplied. Credentials, quota, and
personal-use/redistribution terms are never inferred from an API key alone.
The implementation follows IBKR's [historical market-data endpoint](https://ibkrcampus.com/docs/web-api/v1/endpoints/market-data/historical-market-data),
[WebSocket historical market-data request](https://ibkrcampus.com/docs/web-api/v1/ws/market-data/historical-market-data-request),
[pacing-limitations contract](https://ibkrcampus.com/docs/web-api/v1/pacing-limitations),
[account preflight](https://ibkrcampus.com/docs/web-api/api-reference/trading/trading-accounts/get-brokerage-accounts),
and [snapshot field-31 contract](https://ibkrcampus.com/docs/web-api/api-reference/trading/trading-market-data/get-md-snapshot).
FINRA now uses its OAuth client flow and has the documented synchronous quota
ceiling recorded; credential, terms, and live evidence are still required. The
current [FINRA API Terms of Service](https://developer.finra.org/finra-api-terms-service)
restrict licensed materials to authorized users and permitted uses, prohibit
bulk-distributor/service-bureau use and access outside the licensed APIs, and
may change. The implementation therefore keeps legal entitlement separate from
quota/live evidence: FINRA data remains non-redistributable by default until
the operator records the applicable dataset terms and downstream audience. The
async result byte bound is an application safety/accounting requirement, not a
claim that FINRA publishes a provider-wide maximum result size. A provider
becomes routable only after the governance record and live evidence satisfy the
contract.

## Market-data platform boundary

The market-data foundation is provider-agnostic and additive to the existing
symbol APIs:

- `instrument.domain_key` is a namespaced stable identifier (`figi:...` where
  available), while the integer `instrument.id` remains the hidden relational
  surrogate.  Issuers/legal entities live in `issuer`; CIK/LEI and ticker
  changes are retained as evidence rather than used as implicit merges.
- Candidates without an unambiguous stable identifier are written to
  `instrument_identity_quarantine` for review.  The OpenFIGI ticker mapper
  refuses ambiguous venue/type results instead of selecting the first row.
- `market_series` scopes every future canonical/raw series by venue, provider
  feed, session, timeframe, and adjustment basis/version.  Existing
  `ohlcv_bar` and `market_bar_observation` rows remain readable through nullable
  compatibility columns. The `market_series_default` mapping selects one
  stable canonical series for legacy symbol/timeframe reads; alternate feeds
  remain addressable by explicit `market_series_id` and are never merged into
  the default result. Migration `a0b1c2d3e4f5` creates the mapping table.
  Cold/latest provider fetches use the same attachment path, so newly persisted
  latest bars cannot fall back to a legacy `NULL` series that would disappear
  from subsequent compatibility reads.
  Bulk historical refreshes and the risk-free-rate history path use this same
  series attachment before persistence.
  Synthetic recomputation readback applies the selector as well, preserving
  the same no-mixing rule for derived chart series.
  If a canonical mapping exists without matching bars, the selector retains
  readable legacy history until canonical observations are actually present.
  Provider batches with mixed sessions, feeds, adjustment bases, or adjustment
  versions are partitioned into separate series before persistence.
  Provider refreshes create/reuse a deterministic series and persist a
  `scope_key` (series ID plus session, or `legacy:<session>` for pre-series
  rows) in both bar tables. All OHLCV upserts target that scoped key, so
  different feeds or sessions cannot overwrite one another. Migration
  `9f0a1b2c3d4e` backfills existing rows; PostgreSQL execution remains subject
  to the Docker-backed migration gate.
- `exchange_session_rule` and `exchange_calendar_exception` retain versioned
  sessions, holidays, early closes, overnight trade-date rules, and source
  provenance.
- `provider_quota_window`, `provider_workload_lease`, and
  `provider_routing_decision` make reservations and routing explanations
  durable across workers; administrators can inspect them through the
  backend-only `/api/v1/market-data/*` diagnostics routes.
- `market_refresh_job` now persists each attempt's `started_at`, `finished_at`,
  and redacted `result_summary` in addition to its queue/lease status. Worker
  outcomes distinguish observed bars from an empty provider response and
  preserve retry/defer reasons without exposing lease tokens. The admin
  `/api/v1/market-data/refresh/queue` response exposes these fields so broad
  evaluators and operators can distinguish completed, empty, retry, deferred,
  and still-leased work without making a provider call inside evaluation.
- Strategy Lab rules, Radar signal replay, the current reusable `/breadth`
  snapshot, and both production/ARQ-compatible indicator-alert paths now run a
  shared local OHLCV coverage preflight before evaluation. Grouped high-alert
  price polling and grouped indicator snapshots occur before evaluation; alert
  history requirements come from the canonical indicator registry, including
  explicit composite-window handling and exclusion of numeric parameters that
  are not history windows.
  The preflight reports exact required ranges, bounded missing slices, freshness
  state, minimum-history readiness, and per-timeframe readiness; unresolved
  instruments are withheld from evaluation. Repair enqueueing is opt-in through
  the run's `queue_coverage_repairs` assumption and always uses the durable
  refresh queue, so evaluators never call a provider directly. Benchmark-family
  breadth now reports per-metric readiness plus a separate cap-benchmark
  result; future non-Strategy signal engines and persisted evaluator run-status
  separation remain explicit follow-ups.
- `market_coverage_snapshot`, `provider_shadow_observation`, and
  `market_data_anomaly` retain coverage gaps, disabled-routing comparisons, and
  reviewable provider disagreements. `/coverage`, `/shadow`, and `/anomalies`
  expose these records to backend operators without enabling a route. The
  shadow report additionally returns an explicit `core_daily_coverage` status
  (including eligible D1 snapshot counts, expected/observed bars, the 0.99
  threshold, and `threshold_met`), quota-capacity event totals, and open
  anomaly counts by severity. Missing coverage evidence is reported as
  `insufficient_evidence`, never as a passing zero.
- `market_universe_reconciliation_run` and
  `market_universe_lifecycle_observation` retain complete discovery-run counts,
  provider symbol/venue presence, repeated missing confirmations, and
  provisional listing-discovered/delisted-candidate events. The opt-in worker
  `reconcile_market_universe` never treats an empty/failed provider response as
  a complete universe and records core D1 coverage after a successful run. It
  follows every validated provider continuation without an arbitrary local
  universe-size/page ceiling; each raw page is committed before normalization
  so a worker interruption cannot erase an already-obtained, quota-consuming
  response. Repeated/non-progressing cursors and contradictory totals still
  fail closed, while the retained snapshots remain available for a later
  continuation/reconciliation attempt.
- QuantLib American-option calculations are labeled with model/version/input
  provenance and fall back explicitly to the legacy Black-Scholes estimator
  when the model cannot be evaluated.

The optional provider descriptors and new routing tables do not enable broad
polling by themselves.  New defaults remain disabled until entitlement and
coverage evidence meets the workstream activation bar.

---

## Providers

ETF holdings provider coverage has a separate market-universe reconciliation
because issuer, promoter, brand, adviser, and white-label publisher identities
do not map 1:1. See [ETF Provider Universe](etf-provider-universe.md) for the
current LSEG Lipper promoter target and registry gap.

### Alpaca Markets (`alpaca`)

**Website**: [alpaca.markets](https://alpaca.markets)  
**Auth**: `ALPACA_API_KEY` + `ALPACA_SECRET_KEY`  
**Free tier**: ✓ — free paper-trading account is sufficient for all data endpoints  
**Data feed**: controlled by `ALPACA_DATA_FEED` (`"iex"` free, `"sip"` requires paid subscription)
**Trading host**: controlled by `ALPACA_TRADING_BASE_URL`; use the paper host
(`https://paper-api.alpaca.markets/v2`) for paper credentials (the safe default)
or explicitly set the live host (`https://api.alpaca.markets/v2`) for live
credentials. Historical/latest market-data calls continue to use
`https://data.alpaca.markets/v2`.

Corporate actions use the [current v1 endpoint](https://docs.alpaca.markets/us/reference/corporateactions-1) and follow its `next_page_token`
cursor. Each successful page is stored as an immutable raw snapshot together
with normalized rows and the continuation token. Snapshots are append-only, so
a later response for the same query/page cannot overwrite earlier evidence.
Jobs may stop after a page
for quota/fairness reasons and resume later; no local page bound permanently
excludes any provider page or action family.

The official Basic market-data plan publishes US stock/ETF historical data
since 2016, with the free feed's documented delayed/latest-data restriction.
The entitlement therefore uses the fixed machine-readable bound
`earliest_date=2016-01-01`; bulk history never sends an invented epoch start.

**Capabilities**

| Capability           | Detail                                              |
|----------------------|-----------------------------------------------------|
| `price_history`      | All US equities + crypto, all timeframes, 5+ years |
| `latest_price`       | Current bar close for equities and crypto           |
| `instrument_events`  | Corporate actions: splits, reverse splits, dividends|
| `universe_discovery` | ~9 000 active US equities + USDT-quoted crypto      |

**Rate limits and plan boundary**: The official Trading API Basic plan is free
for both paper and live accounts, has no separate daily market-data allowance,
and allows 200 historical API calls/minute. Basic equity real-time coverage is
IEX, and both historical and latest equity data are limited to the latest
15 minutes; history begins in 2016. Paper/live keys point at the same user-level
data subscription, so changing key type does not create another quota pool.
The runtime estimates the complete `next_page_token` history request count from
the requested range and reserves every conservative 1,000-bar page before
execution; latest-bar lookbacks use the same bound. It never models the Broker
API partner limits for these Trading API credentials.

Corporate actions use Alpaca's current `GET /v1/corporate-actions` market-data
endpoint with the `symbols`, `types`, `start`, `end`, and `page_token` contract.
The deprecated v2 announcements endpoint is not used; payable dates are read
from `payable_date` and long ranges follow the provider page token.

**Getting credentials**:
1. Create a free account at alpaca.markets
2. Generate Paper Trading API keys from the dashboard
3. Set `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` in `.env.dev`

---

### Massive (`massive`)

**Website**: [massive.com](https://massive.com)
**Auth**: `MASSIVE_API_KEY` (the legacy `MARKETDATA_API_KEY` alias is also accepted)
**Free tier**: ✓ — Stocks Basic is listed as 5 API calls/minute, two years of
history, EOD/reference data, corporate actions, technical indicators, and
minute aggregates. The exact plan terms and redistribution rights remain an
operator review item.

**Capabilities**

| Capability | Detail |
|---|---|
| `instrument_search` | US ticker/reference search |
| `instrument_metadata` | Single-ticker overview with CIK, composite/share-class FIGI, exchange, active/delisted lifecycle fields, SIC classification, description, employee/share-count fields, and branding payload when published |
| `universe_discovery` | Cursor-paged active US stock reference universe |
| `price_history` | Raw or split-adjusted custom bars for M1/M5/M15/M30/H1/H2/H4/H12/D1/W1/MN |
| `market_events` | Cursor-paged IPO calendar and forward market holidays/early closes |
| `instrument_events` / `corporate_actions` | Split and dividend history from the independently paginated `/stocks/v1/splits` and `/stocks/v1/dividends` endpoints; ex-dividend and payable dates are preserved as separate normalized events |

The aggregate adapter uses [`/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}`](https://massive.com/docs/rest/stocks/aggregates), requests the documented 50,000-base-aggregate maximum, and follows only validated `api.massive.com` continuation URLs. It records the response adjustment flag, request ID, provider row, and normalized UTC timestamp in bar provenance. Historical and latest-window reservations are calculated from the requested base-candle count, so pagination never silently falls back to one request.

Corporate-action reads are two independent endpoint families. The adapter
validates every continuation URL and follows both endpoint cursors until the
provider reports completion. The old local page-bound setting is retained only
as a compatibility configuration name; it is never used to discard rows or
make an incomplete response look complete.

Massive history is intentionally not in the default `price_history` chain: the
free five-call/minute and two-year limits are materially narrower than Alpaca's
reviewed route. Operators may add it to an explicit chain after confirming
their plan, history entitlement, and redistribution terms.

---

### FRED — Federal Reserve Economic Data (`fred`)

**Website**: [fred.stlouisfed.org](https://fred.stlouisfed.org)  
**Auth**: `FRED_API_KEY`  
**Free tier**: ✓ — completely free, key is for identification only

**Capabilities**

| Capability      | Detail                                                         |
|-----------------|----------------------------------------------------------------|
| `price_history` | Daily observations for mapped series (rates, forex, macro)     |
| `latest_price`  | Most recent observation for any mapped series                  |

**Mapped symbols** (canonical platform symbol → FRED series):

| Platform symbol | FRED series   | Description                        |
|-----------------|---------------|------------------------------------|
| `^IRX`          | `DTB3`        | 3-Month T-Bill (risk-free rate)    |
| `^FVX`          | `DGS5`        | 5-Year Treasury CMT                |
| `^TNX`          | `DGS10`       | 10-Year Treasury CMT               |
| `^TYX`          | `DGS30`       | 30-Year Treasury CMT               |
| `FEDFUNDS`      | `FEDFUNDS`    | Effective Federal Funds Rate       |
| `EURUSD=X`      | `DEXUSEU`     | EUR/USD daily exchange rate        |
| `GBPUSD=X`      | `DEXUSUK`     | GBP/USD daily exchange rate        |
| `JPYUSD=X`      | `DEXJPUS`     | JPY/USD (inverted convention)      |
| `CADUSD=X`      | `DEXCAUS`     | CAD/USD (inverted convention)      |
| `AUDUSD=X`      | `DEXUSAL`     | AUD/USD daily exchange rate        |
| `CPIAUCSL`      | `CPIAUCSL`    | CPI All Urban Consumers SA         |
| `UNRATE`        | `UNRATE`      | US Unemployment Rate               |
| `VIXCLS`        | `VIXCLS`      | CBOE VIX (daily)                   |
| `DCOILWTICO`    | `DCOILWTICO`  | WTI Crude Oil price                |

**Note**: FRED supplies single scalar values per observation; the provider stores
`open = high = low = close = value` with `volume = null`.  Only `D1` (and lower-frequency)
timeframes are meaningful.

**Getting credentials**:
1. Register at [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html)
2. Set `FRED_API_KEY` in `.env.dev`
3. Keep the routing controls at their fail-closed defaults until operations
   reviews the account scope, reset boundary, storage/automated-use authority,
   and series rights; then set the reviewed controls described above in the
   deployment secret/config store.

---

### Binance (`binance`)

**Website**: [binance.com](https://www.binance.com)  
**Auth**: None — all endpoints used are public  
**Free tier**: ✓ — no account or API key needed

**Capabilities**

| Capability           | Detail                                                   |
|----------------------|----------------------------------------------------------|
| `price_history`      | All USDT-quoted crypto pairs, all timeframes, full history|
| `latest_price`       | Real-time last price for any USDT pair                   |
| `universe_discovery` | All active USDT spot trading pairs (~400+ coins)         |

**Symbol convention**: Platform uses `BTC-USD`; Binance uses `BTCUSDT`.
The provider translates transparently.

**Rate limits**: the current [Spot REST documentation](https://developers.binance.com/en/docs/products/spot/rest-api)
exposes a 6,000 request-weight/minute IP ceiling; the official [Spot REST
endpoint definitions](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md)
define weight 2 for `/api/v3/ticker/price` with one `symbol` and weight 20 for
`/api/v3/exchangeInfo`. The adapter charges those exact values. Historical
`/api/v3/klines` calls cost weight 2 each; the runtime calculates the
conservative number of 1,000-candle pages from the requested range and reserves
the complete weight before execution. A range whose calculated weight cannot fit
the current documented window is deferred rather than charged as one call.
Repeated 429 violations can produce an HTTP 418 IP ban; response usage and reset
headers are captured when capacity failures occur.

**No configuration required.**

The provider also exposes a bounded `account_usage` capability. It uses the
one-weight `/api/v3/time` call and accepts only the provider's native
`X-MBX-USED-WEIGHT-1M` counter plus the reviewed 6,000-weight ceiling and next
UTC-minute reset. Missing or malformed headers remain non-reconcilable; the
client never treats an empty local ledger as zero Binance usage.

---

### CoinGecko (`coingecko`)

**Website**: [coingecko.com](https://www.coingecko.com)  
**Auth**: `COINGECKO_API_KEY` (free Demo key)  
**Free tier**: ✓ — Demo key is free; register at coingecko.com/en/api

**Capabilities**

| Capability              | Detail                                                  |
|-------------------------|---------------------------------------------------------|
| `instrument_search`     | Coin search by name or ticker                           |
| `instrument_metadata`   | Full coin profile: market cap, platforms, links, rank   |
| `universe_discovery`    | Market-cap-ordered crypto universe (10 000+ coins)      |

**Notes**:
- CoinGecko is the authoritative source for crypto universe discovery and metadata.
- For OHLCV, Binance is preferred; CoinGecko's OHLC endpoint has coarser granularity.
- Rate limit: 100 calls/minute and 10,000 calls/month on the Demo plan. Both
  dimensions are recorded independently. CoinGecko documents that monthly
  credits reset on the first day of each month, regardless of billing date;
  the runtime therefore models the pool as a UTC calendar-month window. The
  Demo `/key` usage endpoint remains Pro-only, so an active account baseline
  is still required before routing and no counter is fabricated.
- A metadata lookup consumes two HTTP calls (`/search` provider-ID resolution
  plus `/coins/{id}`); runtime accounting reserves both calls and the ranked
  search result avoids ambiguous ticker-to-coin mappings.

**Getting credentials**:
1. Register at [coingecko.com/en/api](https://www.coingecko.com/en/api)
2. Copy your Demo API key
3. Set `COINGECKO_API_KEY` in `.env.dev`

---

### SEC EDGAR (`edgar`)

**Website**: [data.sec.gov](https://data.sec.gov)  
**Auth**: None — SEC requires only a descriptive `User-Agent` header  
**Free tier**: ✓ — completely free, no account needed

**Capabilities**

| Capability            | Detail                                                        |
|-----------------------|---------------------------------------------------------------|
| `instrument_metadata` | US company profile: name, exchange, SIC, CIK, fiscal year end|
| `instrument_events`   | Historical 10-Q/10-K filing dates as earnings event records   |
| `market_events`       | Provisional S-1/F-1/424B* IPO-pipeline candidates for a supplied CIK |

**Earnings date accuracy**: EDGAR records filing submission dates, not the earnings call date.
Large-caps typically file 1–5 days after earnings; small-caps can take up to 40 days.
These dates are suitable for historical context and event-proximity calculations, not
for time-sensitive intraday use.

**Configuration**:
- Set `EDGAR_USER_AGENT` in `.env.dev` to identify your application, e.g.:
  `EDGAR_USER_AGENT="ChartingPlatform <real contact email>"`
- The angle-bracket value above is documentation-only and is rejected by the
  runtime. Replace it with a real contact before enabling SEC calls; blank or
  placeholder values fail closed.

The first profile or earnings-event lookup in a cold process resolves the
ticker through `company_tickers.json` and then fetches the issuer submissions
resource, so runtime accounting reserves two requests for those compound
operations. Warm directory/profile caches may reduce observed transport
without weakening the reservation.

`fetch_ipo_pipeline_events(cik, start, end, max_events)` is a separate,
explicitly bounded market-event operation. It performs one submissions read
for the supplied CIK and normalizes recent `S-1`, `S-1/A`, `F-1`, `F-1/A`, and
`424B*` filings as provisional `ipo_pipeline` candidates. It never enumerates
all issuers or fetches archived submission files implicitly, and its filing
date must not be presented as an exact listing date.

**Rate limit**: max 10 requests/second per SEC guidelines. The SEC says access
resumes once traffic falls below that threshold but does not publish a fixed
bucket boundary. The runtime therefore enforces an explicit rolling one-second
application safety envelope; this is not presented as the SEC's native reset
semantics. A descriptive User-Agent and SEC fair-access compliance remain
required.

---

### Twelve Data (`twelve_data`)

**Role**: Optional multi-timeframe US candles, latest price, symbol search,
and bounded US equity/ETF catalogue discovery.
**Auth**: `TWELVE_DATA_API_KEY` (query parameter).

The adapter requests at most 5,000 points per `/time_series` page and reserves
the exact calculated page count before transport. It requests intraday output
in UTC, preserves the provider's exchange timezone for daily bars, and rejects
adjusted-history requests because the adapter exposes raw observations only.
Universe discovery is explicitly page- and asset-type-scoped; a missing or
contradictory provider count is an error, not permission to infer completion.

Twelve Data documents two distinct Basic-plan credit pools: 8 credits per
fixed minute and 800 credits per UTC calendar day. Endpoint weights are
provider-specific and must remain in the checked-in usage profile; the runtime
does not substitute one request for an unknown endpoint weight. The optional
native `fetch_account_usage` operation calls the documented `/api_usage`
endpoint (itself charged one credit), records the returned plan, and persists
the exact `api-credits-used`/`api-credits-left` minute pool as a named
`credits_per_minute` observation with the next fixed-minute reset. The public
contract does not provide a stable daily-counter response shape, so the adapter
does not fabricate a `credits_per_day` observation from the minute headers.
Native observations are telemetry until an exact provider-specific baseline
mapping is reviewed; they never widen routing automatically. See the official
[usage-control](https://support.twelvedata.com/en/articles/5713553-control-over-api-usage)
and [credits](https://support.twelvedata.com/en/articles/5615854-credits)
documentation.

### MarketData.app (`marketdata_app`)

**Role**: Authenticated US stock/ETF candles and options data, including
expiration discovery, current chains, and historical single-contract quotes.
**Auth**: `MARKETDATA_APP_API_KEY` (Bearer token)

The adapter follows the documented `/v1` endpoints and preserves OCC symbols,
provider timestamps, quote fields, and historical null Greeks. Current-price
reads use the documented delayed stock-quotes endpoint (`/v1/stocks/quotes/`)
instead of treating a one-day candle window as a quote; this remains valid on
weekends/holidays and for delayed or historical-only entitlements. The provider
documents 100 daily credits on Free Forever accounts, 10,000 on Starter, and
100,000 on Trader, reset at 09:30 America/New_York, plus a 50-request
concurrency ceiling. Free and trial accounts are limited to data at least 24
hours old and one year of history. Each account is limited to one active IP;
account sharing and data redistribution are prohibited. See the provider's
[rate-limit](https://www.marketdata.app/docs/api/rate-limiting/),
[free-account](https://www.marketdata.app/docs/account/free-accounts/),
[option-chain](https://www.marketdata.app/docs/api/options/chain/), and
[option-quotes](https://www.marketdata.app/docs/api/options/quotes/)
documentation. Configure `MARKETDATA_APP_REVIEWED_PLAN` and its exact daily
limit: `free_forever`/100, `starter_trial`/10,000, `trader_trial`/100,000,
`starter`/10,000, or `trader`/100,000. A trial additionally requires a
timezone-aware ISO-8601 `MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT`; missing or
invalid expiry fails closed. While a configured trial is active, the runtime
reserves its documented daily pool. At or after expiry, it automatically
changes the effective entitlement and quota to Free Forever/100 credits per
day, without requiring a deployment-time plan edit. A later paid upgrade is
configured by changing the plan/limit pair; because routing is free-only by
default, paid plans additionally require `ALLOW_PAID_PROVIDER_ROUTING=true`.
This plan/limit configuration is provider-specific and may be set separately
for local development, protected CI, and production.
Quant/Prime plans use a different per-minute contract and remain outside this
daily-plan gate until their dimensions are modeled explicitly.

Option expiration lookups cost one credit. Current chains/quotes cost one
credit per returned option symbol; historical chains/quotes cost one credit
per 1,000 returned symbols/quotes. The runtime records the provider-native
`X-Api-Ratelimit-*` headers, settles the actual per-response charge, and
reconciles cumulative remaining-credit state only when the returned limit
matches the reviewed account contract. A native limit mismatch is retained as
telemetry but cannot widen local admission or settle a different quota. Since a current chain is
response-priced, routing requires a positive operator-reviewed
`MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS` value. The adapter applies the
documented `strikeLimit` filter and rejects a response larger than that bound;
zero remains fail-closed. Historical single-contract quote history derives a
conservative date-range reservation (at most one end-of-day observation per
calendar day) before execution.

The adapter also exposes the documented authenticated `GET /user/` account
introspection endpoint through `fetch_account_usage()`. It preserves the
provider-reported credit limit, remaining credits, request charge, reset time,
and options-data entitlement without deriving a plan or changing routing. The
endpoint is unversioned (`https://api.marketdata.app/user/`) even though data
resources use `/v1`; the provider documents a 404 response as “no account
information”, which is represented as no snapshot. See the official
[Python client account/rate-limit documentation](https://www.marketdata.app/docs/sdk/py/client/)
and [Go user endpoint documentation](https://www.marketdata.app/docs/sdk/go/utilities/user/).

### Yahoo Finance (`yfinance`) — Explicit legacy/options fallback

**Role**: Opt-in compatibility provider for retained legacy/options or other explicitly configured capabilities. It is not part of any new-workstation default or acceptance path.
**Auth**: None (unofficial library — no API key)  
**Free tier**: ✓ (unofficial)

**Capabilities**: Existing adapter surface includes search, metadata, OHLCV, latest price,
events, identifiers, discovery, and option chains. Every value retains provider provenance.

**Primary unique coverage**:
- US and non-US options chains (the only free source)
- Forward earnings estimates and analyst price targets
- Major futures and commodity symbols (e.g. `ES=F`, `CL=F`, `GC=F`)
- Broad global price history fallback

**Caveats**: Unofficial API — no SLA, rate limits enforced opaquely, structure can break
without notice. Should be deprioritized via provider policy once primary providers are active.

---

### OpenFIGI (`openfigi`)

**Role**: Stable identifier enrichment (FIGI, Composite FIGI).  
**Auth**: `OPENFIGI_API_KEY` (optional — unauthenticated requests allowed at lower rate)

**Capabilities**: `instrument_identifiers`

The provider-native `fetch_account_usage` observation sends one bounded
mapping job and requires OpenFIGI's `ratelimit-limit`, `ratelimit-remaining`,
and response-relative `ratelimit-reset` headers. The exact anonymous
(`mapping_requests_per_minute`) or keyed (`mapping_requests_per_6_seconds`)
dimension is persisted and reconciled into the durable quota ledger; missing
or malformed headers fail closed. This consumes one mapping request and is
never treated as a free metadata read.

### FINRA (`finra`)

**Role**: Periodic consolidated short-interest observations plus OTC lifecycle
and corporate-action deltas. The adapter uses FINRA's
`otcMarket/consolidatedShortInterest` and `otcMarket/OTCDAILYLIST` Query API
datasets, preserves each raw row, and sends the documented `compareFilters`
POST shape. It normalises settlement/publication dates, current short position,
percent float, days-to-cover values, and Daily List event dates/types. The
Daily List is explicitly a delta feed for new/deleted issues, symbol/name
changes, and other actions; it is not a complete current OTC security master
and cannot by itself close the initial OTC-universe reconciliation gate. It
does not infer missing values or treat publication dates as real-time quotes.
FINRA's [API platform documentation](https://developer.finra.org/docs) documents
the OAuth flow, throttling, synchronous record/payload limits, and these
datasets. Those limits are recorded in the provider contract; the adapter still
requires an operator-provisioned OAuth credential and reviewed terms before
routing.

The public credential's 10 GB allowance is retained with its provider-defined
monthly reset label because FINRA does not publish the reset timezone or byte
convention. Admission nevertheless uses a conservative provider-scoped rolling
31-day safety envelope for the byte pool, with measured response bytes settling
reservations in the durable ledger. This protects the credential without
pretending that FINRA's native boundary is known; a later reviewed native reset
may replace the safety envelope.

**Configuration**: Set `FINRA_CLIENT_ID` and `FINRA_CLIENT_SECRET` in the
ignored `.env.dev`. `FINRA_SHORT_INTEREST_URL` and
`FINRA_OTC_DAILY_LIST_URL` are optional endpoint overrides; otherwise the
adapter uses the documented API base and OAuth bearer flow. Do not put client
secrets in commits or chat. Synchronous short-interest and Daily List operations
have a conservative documented quota contract and can be routed after credential,
live, and terms gates; the separate OTC security-master directory remains
non-routable until its current terms and quota are reviewed.

Each authenticated dataset call can include a cold OAuth token request before
the dataset POST. Runtime accounting therefore reserves two requests for
short-interest and Daily List operations; a warm token cache may consume only
the dataset request, but the reservation never undercounts a cold process.

### FINRA OTC directory (`finra_otc_directory`)

This adapter supports three explicitly separated source shapes: a legacy
DAPI/pipe-delimited source, the official OTC Markets pipe-delimited shape, and
FINRA's documented ORF file-download pair. The ORF pair is the complete-source
path: `EQUITYMASTERAC` (active issues) and `EQUITYMASTERIN` (inactive issues),
downloaded as pipe-delimited files from the endpoints in FINRA's [ORF file
download specification](https://www.finra.org/sites/default/files/2024-08/Equity_API_File_Downloads_ORF.pdf).
The parser validates `FINRA_OTC_ID`, symbol, description, and status, preserves
CUSIP/suffix/effective and inactive timestamps, rejects malformed rows and
duplicate symbol/suffix keys, and requires both snapshots before returning a
complete universe. The Daily List remains a lifecycle delta and is not a
replacement for the two complete masters.

ORF is not a free/public endpoint: FINRA states that an [ORF Web Access
Agreement](https://www.finra.org/filing-reporting/orf/technical-notices/reminder-otc-trade-reporting-facility-orf-migration)
is required, and production reference-data files require product entitlement
and [MFA](https://www.finra.org/filing-reporting/technical-notices/finra-api-reference-data-mfa-production-access-20241209).
The supplied FINRA OAuth pair is therefore not treated as proof that this
specific product entitlement exists. Set `FINRA_OTC_SOURCE_KIND=finra_orf_security_master`,
configure both `FINRA_OTC_SYMBOL_DIRECTORY_URL` and
`FINRA_OTC_INACTIVE_SECURITY_MASTER_URL`, and keep routing disabled until the
agreement, MFA, terms, completeness, polling, and redistribution reviews are
recorded. Legacy/DAPI and OTC Markets parsers remain available only behind the
same source-evidence gates; no source is silently promoted to complete OTC
coverage.

Routing requires a non-secret evidence reference in
`FINRA_OTC_SOURCE_EVIDENCE`, exact reviewed-URL matches for both configured
files (`FINRA_OTC_REVIEWED_SOURCE_URL` and
`FINRA_OTC_REVIEWED_INACTIVE_SOURCE_URL` in ORF mode), an affirmative
`FINRA_OTC_SOURCE_REVIEWED`, a positive reviewed `FINRA_OTC_OPERATION_COSTS`
map for both `discover_universe_page` and `reconcile_universe_page`, plus
independent terms, complete-universe, redistribution, and positive
polling-interval controls. The cost map bounds the two-file cold refresh and
OAuth request cost; no one-request default is inferred. FINRA's published
synchronous 1,200 requests/minute/IP and 3 MB response ceilings are platform
limits only and do not establish this application's product entitlement or
redistribution rights.
Generic universe reconciliation requires authoritative `total` metadata to be
an actual integer; boolean, numeric-string, fractional, negative, or malformed
totals fail closed.

FINRA's asynchronous Query API result payloads are documented as unbounded by
the [FINRA platform usage limits](https://developer.finra.org/docs).
The adapter therefore requires a positive `FINRA_ASYNC_MAX_RESULT_BYTES` (or
an explicit per-call bound), validates `Content-Length` when supplied, and
enforces the limit while streaming chunks so oversized bodies are not
materialized in memory. A positive configured bound also becomes the
operation-specific reservation against the provider's durable 10 GiB monthly
credential budget; the signed leg consumes no API-request-minute dimension and
settles to measured bytes. The default `0` remains fail-closed and
non-routable, because an unbounded provider result cannot be admitted safely.
This async-only bound does not gate the synchronous `fetch_short_interest` or
OTC Daily List `fetch_market_events` operations: both use the published 3 MB
synchronous response ceiling and reserve that conservative maximum against the
same monthly byte budget before settling to observed response bytes.

### SEC Company Facts (`edgar`)

The EDGAR adapter exposes raw Company Facts observations with namespace, fact,
unit, period, filing/acceptance timestamps, accession, and the original payload.
Curated ratios and statement mappings remain a separate downstream concern so
point-in-time consumers can choose an explicit filed/accepted knowledge boundary.

---

## Configuration Reference

All provider settings go in `.env.dev` (development) or equivalent environment file.

```env
# Alpaca Markets
ALPACA_API_KEY=your_alpaca_key_id
ALPACA_SECRET_KEY=your_alpaca_secret
ALPACA_DATA_FEED=iex          # iex (free) | sip (paid consolidated feed)
ALPACA_TRADING_BASE_URL=https://paper-api.alpaca.markets/v2  # live keys: https://api.alpaca.markets/v2
ALPACA_CORPORATE_ACTIONS_MAX_PAGES=0 # compatibility only; every continuation is persisted and resumed until complete
MASSIVE_CORPORATE_ACTIONS_MAX_PAGES=0 # legacy compatibility setting; provider pagination is always followed to completion
MASSIVE_REVIEWED_RESET= # optional override; default safety envelope is rolling 60 seconds
MASSIVE_QUOTA_EVIDENCE= # optional evidence for a provider-native reset override

# FRED
FRED_API_KEY=your_fred_key
FRED_REVIEWED_LIMIT_SCOPE=
FRED_REVIEWED_REQUESTS_PER_MINUTE=0
FRED_REVIEWED_QUOTA_EVIDENCE=
FRED_REVIEWED_RESET=
FRED_RESET_EVIDENCE=
FRED_PERSISTED_STORAGE_AUTHORIZED=false
FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE=
FRED_AUTOMATED_USE_AUTHORIZED=false
FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE=
FRED_SERIES_RIGHTS_EVIDENCE={}

# Coinbase Exchange — rate limits do not imply data-use permission
COINBASE_API_KEY=
COINBASE_MARKET_DATA_USE_AUTHORIZED=false
COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE=
# Must equal internal_automated_persistent_nonredistributed if authorized.
COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE=
COINBASE_MARKET_DATA_USE_REVIEWED_AT=
COINBASE_MARKET_DATA_USE_EXPIRES_AT=

# CoinGecko
COINGECKO_API_KEY=your_coingecko_demo_key

# SEC EDGAR — no key, but User-Agent is required
# Set a real application/contact value before enabling SEC calls; blank is intentionally fail-closed.
EDGAR_USER_AGENT=
# SEC publishes 10 requests/second but not a fixed reset boundary; the runtime
# uses a rolling one-second application safety envelope. These are optional
# only if replacing that envelope with a separately reviewed provider reset.
EDGAR_REVIEWED_RESET=
EDGAR_QUOTA_EVIDENCE=

# OpenFIGI (optional; empty uses the documented anonymous 25/minute, 5-job contract)
OPENFIGI_API_KEY=your_openfigi_key

# FINRA OAuth (required for current API)
FINRA_CLIENT_ID=
FINRA_CLIENT_SECRET=
FINRA_TOKEN_URL=https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token
FINRA_API_BASE_URL=https://api.finra.org
FINRA_SHORT_INTEREST_URL=
FINRA_OTC_DAILY_LIST_URL=
# Leave empty unless current FINRA docs or written confirmation establish this source.
FINRA_OTC_SYMBOL_DIRECTORY_URL=
FINRA_OTC_OPERATION_COSTS={}
FINRA_OTC_SOURCE_REVIEWED=false
FINRA_OTC_SOURCE_EVIDENCE=
FINRA_OTC_REVIEWED_SOURCE_URL=
FINRA_OTC_TERMS_REVIEWED=false
FINRA_OTC_COMPLETENESS_REVIEWED=false
FINRA_OTC_REDISTRIBUTION_REVIEWED=false
FINRA_OTC_POLL_INTERVAL_SECONDS=0
FINRA_ASYNC_MAX_RESULT_BYTES=0

# Optional adapters (disabled until governance records reviewed entitlements)
TIINGO_API_KEY=
TWELVE_DATA_API_KEY=
FINNHUB_API_KEY=
MARKETSTACK_API_KEY=
EODHD_API_KEY=
MARKETDATA_APP_API_KEY=       # MarketData.app — US delayed stocks/options
# Account plan/limit must match this environment's confirmed account tier.
# Pairs: free_forever/100, starter_trial/10000, trader_trial/100000,
# starter/10000, and trader/100000. Trial plans need an explicit expiry.
# Expired trials automatically fall back to free_forever/100. Native headers
# are observations and never widen the reviewed plan.
MARKETDATA_APP_REVIEWED_PLAN=
MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT=0
# Required only for starter_trial/trader_trial; timezone-aware ISO-8601.
MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT=
# Current option chains consume one credit per returned symbol. Set this only
# after reviewing the exact request filters; zero keeps chain routing closed.
MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS=0
TRADIER_API_KEY=
FMP_API_KEY=                  # Financial Modeling Prep — fundamentals, forward estimates
BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED=false
BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE=
BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE=
BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT=
BYBIT_XSTOCKS_MARKET_DATA_USE_EXPIRES_AT=
BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED=false
BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE=

# Optional future-listing candidate materialization (backend/worker only)
MARKET_EVENTS_PRELISTING_ENABLED=false
MARKET_EVENTS_PRELISTING_LOOKAHEAD_DAYS=90
MARKET_EVENTS_PRELISTING_MAX_EVENTS=500
MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_ENABLED=false
MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_LOOKBACK_DAYS=365
MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_MAX_ISSUERS=50
MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_MAX_EVENTS_PER_ISSUER=100
MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED=false
MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_ISSUERS=50
MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_EVENTS_PER_ISSUER=100
MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ISSUER_MATERIALIZATION_MODE=disabled
MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_REVIEWED_CYCLE_COUNT=0

# Optional complete US universe/lifecycle reconciliation (worker only)
MARKET_UNIVERSE_RECONCILIATION_ENABLED=false
MARKET_UNIVERSE_MISSING_CONFIRMATIONS=3
```

Provider quotas and operation-cost profiles are configuration, not immutable
per-provider assumptions. Each environment can replace the reviewed in-code
maps with `PROVIDER_RATE_LIMIT_SEEDS` (complete quota contracts) and
`PROVIDER_USAGE_PROFILE_SEEDS` (operation-specific accounting). Use
`__CODE_DEFAULT__` to retain the reviewed code defaults. A non-empty replacement
must include every provider policy that should stay routable; `{}` intentionally
removes these policies and is not a safe way to change just one provider. When a
provider plan changes, update its complete limit/window/reset/scope contract and
its entitlement separately; paid plans also require the explicit paid-routing
switch. This lets each production, CI, RPi, or local environment reflect its
own account tier without credentials or account-specific quota values entering
Git. Runtime/admin policy changes are stored in the application database and
must remain source-backed and auditable.

---

## Provider Chain Defaults

The default provider chain can be overridden per capability via `PROVIDER_CHAIN_SEEDS`
(JSON dict in `.env.dev`). The free-source-first new-workstation baseline is:

```env
PROVIDER_CHAIN_SEEDS={"instrument_search":["edgar","massive","alpha_vantage"],"instrument_metadata":["edgar","massive","alpaca"],"price_history":["alpaca","alpha_vantage"],"latest_price":["alpaca","alpha_vantage"],"instrument_events":["alpaca","massive","edgar","finnhub","alpha_vantage"],"universe_discovery":["alpaca","edgar","massive","nasdaq","finra_otc_directory","alpha_vantage"],"tokenized_historical_prices":["dinari","ondo_global_markets"],"tokenized_corporate_actions":["robinhood_tokens","xstocks","dinari"]}
TOKENIZED_PROVIDER_PRIORITY=["robinhood_tokens","xstocks","bybit_xstocks","gate_tradfi","kraken_xstocks","dinari","ondo_global_markets"]
```

The default options candidate is `marketdata_app`, not yfinance. MarketData.app
remains non-routable until its account plan/credit pair and response-priced
option-chain bound are explicitly reviewed; this keeps the default API-first
without turning a configured key or a native header into an unreviewed quota
entitlement. yfinance can be added only through an explicit legacy override.

Adding `yfinance` requires an explicit legacy/options deployment decision and must never
silently broaden a new-workstation chain.

Massive's IPO-calendar adapter uses the documented
[`reference/ipos`](https://massive.com/docs/rest/stocks/corporate-actions) endpoint.
Each cursor page is an independently metered request; the adapter returns the
continuation URL without silently following it, and applies date bounds locally.
The same adapter also exposes the documented
[`marketstatus/upcoming`](https://massive.com/docs/rest/indices/market-operations)
forward holiday and early-close feed as normalized `market_holiday` events.

Massive's [`custom bars`](https://massive.com/docs/rest/stocks/aggregates)
adapter also maps the platform's M1/M5/M15/M30/H1/H2/H4/H12/D1/W1/MN
timeframes to the provider's multiplier/timespan endpoint. It preserves the
provider adjustment flag and payload, follows only HTTPS continuation URLs on
`api.massive.com`, rejects conflicting duplicate timestamps and invalid OHLC
rows, and reserves `ceil(calendar-base-aggregates / 50,000)` requests before a
historical or latest-window call. This is deliberately not added to the
default price-history chain: the free plan's five-call/minute and two-year
limits require explicit operator routing review.

Massive's [`ticker overview`](https://massive.com/docs/rest/stocks/tickers/ticker-overview)
endpoint is exposed as `instrument_metadata`. It validates that the returned
ticker matches the request, preserves CIK/composite FIGI/share-class FIGI
identifiers, normalizes exchange/currency/type and active/delisted timestamps,
and retains provider classification, description, share-count, employee, and
branding fields without inventing values for omitted fields. The metadata
operation has an explicit one-request reservation and is supplementary to the
SEC issuer profile rather than a replacement for SEC filing facts.

Priority within a chain is refined at runtime by health scores (EWMA latency, success rate,
completeness).  A provider that consistently fails for a given symbol class (e.g. Binance
receiving equity symbols) will be naturally deprioritised by the circuit-breaker logic.

---

## Coverage Summary

| Data type                    | Primary provider  | Fallback        |
|------------------------------|-------------------|-----------------|
| US equity OHLCV              | alpaca            | Massive (opt-in, 5 calls/min) / alpha_vantage (quota-limited) |
| US equity/ETF universe discovery | alpaca / SEC directory / Nasdaq NMS files | massive / FINRA OTC directory (explicit source) / alpha_vantage |
| US splits + dividends        | alpaca            | edgar           |
| Crypto OHLCV                 | binance / coinbase / kraken | Alpaca (where symbol coverage applies) |
| Crypto universe discovery    | Nasdaq Trader (US listings) + exchange APIs | CoinGecko Demo |
| Crypto metadata              | coingecko         | —               |
| Interest rates (RFR, yields) | fred              | —               |
| Major forex daily rates      | fred              | —               |
| Macro indicators             | fred              | —               |
| US company profile           | edgar             | Massive ticker overview (CIK/FIGI, exchange, lifecycle, classification) / Alpaca authenticated asset metadata (provider-native listing identity) |
| Historical earnings dates    | edgar             | —               |
| US options chains            | MarketData.app when its reviewed plan/response bound is configured | Tradier when entitled; yfinance remains explicit legacy only |
| Futures / commodities        | IBKR generic read-only adapter (explicit conid mapping recommended) | yfinance (explicit legacy compatibility only) |
| Forward earnings estimates   | Alpha Vantage `EARNINGS_CALENDAR` (bounded 3-month operation); Finnhub forward calendar; FMP `earnings-calendar` | Alpha's 3/6/12-month horizon semantics and one-request cost are explicit; Finnhub and FMP calendars are live-proven for configured keys; FMP routing remains byte-bound gated |
| IPO calendar                 | Massive `reference/ipos`; Alpha Vantage `IPO_CALENDAR` | Massive returns cursor-paged IPO rows; each page is charged separately and date bounds are applied locally |
| Market holidays / early closes | Massive `marketstatus/upcoming` | Forward-only exchange rows with open/close/status provenance; one request per refresh |
| Analyst price targets        | *(excluded)*      | *(capability stub)* |

Remaining gaps are tracked in [project-todos.md](project-todos.md).
