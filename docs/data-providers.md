# Data Providers

This document describes every data provider registered with the platform, what data each one
supplies, its priority level per capability, and where to configure its credentials.

## 2026-10-02 — Marketstack universe totals fail closed

Marketstack ticker discovery now requires strict provider pagination metadata
and advances using the raw provider page count even when local quote-type
filtering removes rows. Its `total_scope: raw` marker drives pagination while
completed reconciliation reports the filtered quote count. It no longer
substitutes the current page length when metadata is absent or malformed,
preventing a partial universe page from being mistaken for a complete snapshot.
Focused Marketstack coverage passed `21/21` plus raw-total reconciliation
coverage.

## 2026-10-10 — Marketstack quota headers observed live

The Marketstack adapter now uses its v2 API base URL and retains APILayer's
documented daily/monthly quota headers when supplied. A bounded live check
returned the requested AAPL EOD row, but this account's response exposed only
`X-Rate-Limit-Remaining: 0` without a matching limit or reset. That value is
stored as an unclassified provider-header observation and is not interpreted
as monthly allowance. The monthly quota remains fail-closed until current
account usage is reconciled. Venue-wide ticker-page cost is also still
unconfirmed, so discovery remains non-routable.

## 2026-10-13 — Marketstack request billing contract researched

Marketstack's first-party FAQ defines a metered request per stock ticker: a
request containing five symbols consumes five monthly units, not one. API
errors are documented as not counting toward this monthly allowance. Therefore
the adapter's single-symbol quote and EOD operations cost one monthly unit each;
any future multi-symbol call must reserve one unit per symbol. This does not
establish the billing cost of the paginated universe-discovery endpoint, which
remains non-routable until its endpoint-specific cost is documented.

The provider's first-party pages conflict on Free allowance: the pricing FAQ
states 1,000 requests/month in one answer, while the contact FAQ states 100;
both FAQ areas also reference the 100-request threshold. Runtime continues to
use the conservative 100-unit Free ceiling unless the account's plan and limit
are explicitly configured. The billing-cycle reset timestamp and current
account usage are not supplied by those public pages; admission requires a
fresh account baseline and configured reset boundary. Overage billing is
enabled by default in provider descriptions, so the app must reserve within
the configured allowance and never rely on overages.

Marketstack's FAQ identifies Tiingo as the source/licensor for US-exchange
stock data. Treat Marketstack as a separate API/quota path, not an independent
underlying US data feed when evaluating source diversity.

Sources: [Marketstack FAQ](https://marketstack.com/faq),
[Marketstack contact FAQ](https://marketstack.com/contact),
[Marketstack pricing](https://marketstack.com/pricing).

## 2026-10-02 — Tokenized event page validation

Tokenized corporate-action refreshes validate every returned page row before
writing events or advancing `ProviderPaginationState`. A non-object row raises
a typed failure, leaves the current page/cursor retryable, and prevents
silently dropping the malformed provider item or accepting only a prefix of the
page. Focused coverage passed `7/7` with no external provider calls.

---

## Provider Priority Overview

> **Quota safety contract (corrective revision):** the runtime never applies a
> generic rate, burst, concurrency, or cooldown. A provider is routable only
> when every required quota dimension has an explicit source, scope, unit,
> limit, and reset window. If a vendor does not publish a fixed limit (or the
> deployment plan is not verified), it remains visible to administrators but is
> `quota_unknown` and cannot be selected. A 429/418 response is recorded with
> provider headers/reset information, and defers work across capabilities that
> share the affected quota scope. A trustworthy reset opens a persistent
> circuit through that time. If no reset is provided, the policies in that
> scope are disabled until an administrator explicitly re-enables them after
> reconciling provider usage; the runtime does not invent a cooldown.
>
> `PROVIDER_MAX_CONCURRENCY` is only a process-local instrument-sync guard. It
> is not a provider limit and is never used to infer one.
>
> **Owner decision:** `PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK=true` records
> the owner's final acceptance of provider-term and retention risks for this
> private, single-user app. Do not require provider-specific written consent or
> ask the owner to approve those terms again. Provider restrictions remain
> documented as factual risk context, but do not block this owner's routing.
> This decision does not establish account entitlement, quota headroom, or
> deployment-jurisdiction eligibility, and does not override technical or
> applicable legal restrictions.
>
> A reviewed plan and configured credential are still not enough to route a
> provider: its capability must carry `passed` (or genuinely `not_required`)
> live-probe evidence. Historical bounded transport evidence exists for EDGAR,
> Alpaca, MarketData.app, and the Dinari Sandbox pair, but it is not by itself
> current-source acceptance. The latest exact-source Alpaca work proves its
> native account-usage header snapshot and rolling safety-envelope bootstrap;
> ordinary Alpaca routing still requires current-source live evidence and a
> safe quota baseline; its terms-risk decision is already on file. The latest
> SEC EDGAR manifest preflight stopped before transport
> because the documented IP window has no current durable baseline. Tradier,
> Ondo, and IBKR are intentionally deferred. None of these observations
> does not override separate quota, entitlement, jurisdiction, and
> reconciliation controls.

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

Availability probes are provider calls, not synthetic health flags. Each
successful or empty/partial probe now retains the complete normalized response
in `provider_availability_observation.response_payload` in addition to its
shape and classification, so schema regressions can be replayed without
spending another quota unit. Authentication-shaped fields (`api_key`, access
tokens, secrets, cookies, and private keys) are redacted before persistence;
pagination tokens and all other returned data remain evidence. Failed probes
retain their redacted typed error and response shape, with a null payload when
the provider returned no value.
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
These accounting profiles describe adapter cost only. The owner's recorded
`PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK=true` decision clears provider-term
gates for this private-use deployment; it does not claim that a provider
granted an exception. The same owner decision is now the default in local,
RPi, and credentialed-CI configuration. Authentication/entitlement, quota,
response-size, and geographic-access controls remain separate.

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
weight header), OpenFIGI's one-job mapping request (native `ratelimit-*`
headers), and Alpaca's bounded observation of its native
limit/remaining/reset headers. OpenFIGI's usage request itself consumes one
mapping request; its observed window is 25/minute for anonymous mapping or
25/6 seconds for keyed mapping, with the provider's response-relative reset
preserved as an absolute observation timestamp. Alpaca documents a
200-requests/minute pool but does not publish a fixed calendar-minute
boundary; the runtime therefore uses a conservative rolling 60-second safety
envelope and only seeds the durable active baseline from a matching native
snapshot:

```sh
POST /api/v1/providers/usage/account/refresh   # admin-only, explicit poll
GET  /api/v1/providers/usage/account            # admin-only, durable history
```

The refresh is admitted through the same credential, live-probe, provider
quota, operation-cost, and circuit-breaker checks as any other request. The
MarketData.app account-usage operation is the one deliberate exception to the
plan-review gate: it may be polled with the conservative seed contract before
the operator has recorded the plan, so the native response can inform that
review. It cannot admit market-data or options routing. Binance, Twelve Data,
and EODHD also declare an explicit first-snapshot bootstrap. A finite pool may
be omitted from the probe's pre-call debit only when that exact pool is listed
in the provider's native-response reconciliation map; the response then
establishes its post-call baseline, including the usage probe itself. Every
other metered pool must already have a verified or explicitly client-owned
`local_zero` baseline, or the probe is blocked before transport. A successful
partial snapshot cannot waive another unreported pool. The deployment-scoped
serialized probe slot is an application safety control, not a provider quota
or entitlement. Binance's first snapshot uses the same explicit
serialized bootstrap slot and accepts only `X-MBX-USED-WEIGHT-1M` plus the
reviewed fixed-minute boundary. The returned
limit/remaining/consumed/reset/options values are stored verbatim as
observations; they never replace the reviewed local plan, infer a reset window,
or widen routing. Providers without a documented native usage surface remain
represented by durable request/byte/header telemetry and are not queried
through a guessed endpoint. EODHD daily usage can reconcile only a current-date
`calls_per_day` baseline whose returned limit matches the reviewed contract;
its minute headers remain observational while the provider's official
minute-limit sources conflict. On 2026-09-25 the configured Free account
returned `calls_per_day=20`, `consumed=3`, and `remaining=17`, but its
`apiRequestsDate` was stale; the adapter therefore returned no reset boundary
and the live runner did not admit the counter. The same response returned
`X-RateLimit-Limit=1200` and `X-RateLimit-Remaining=1199` without a reset, so
those headers remain observational. Twelve Data's native minute-credit
observation reconciles `credits_per_minute`; its `/api_usage` body separately
reports Basic-plan daily request count and limit, reconciling the distinct
`requests_per_day` pool. These native units are not conflated: the account
probe reserves one credit and one request before transport, then establishes
the post-call baseline for both dimensions. Unreported or unit-mismatched
pools remain blocked.

Provider observations are append-only evidence. The maintenance endpoint never
deletes provider request logs or latest-price, search, universe, profile, or
identifier snapshots, regardless of the legacy `PROVIDER_REQUEST_LOG_RETENTION_DAYS`
and snapshot-retention settings. Request logs are quota and audit evidence, not
disposable operational cache. This preserves every quota-consuming provider
response and usage fact for audit, replay, and future reconciliation.

The durable quota coordinator follows the same rule: historical quota windows,
reservations, and identity claims are never deleted by maintenance, even after
their active enforcement window has elapsed. `PROVIDER_QUOTA_LEDGER_RETENTION_DAYS`
remains a compatibility/diagnostic setting, but cleanup is intentionally a
no-op until a lossless archival path exists. This keeps cross-session usage
evidence available for provider-account reconciliation.

Provider-native account-usage observations now retain both the decoded raw
provider body and the allow-listed capacity headers alongside each normalized
dimension. This preserves provider-specific fields such as usage dates, plan
metadata, and reset evidence across sessions; the migration downgrade refuses
to remove non-empty evidence rather than silently discarding it.

Profile, identifier, search, universe-discovery, and option-chain snapshots are
also append-only evidence. Identical payloads from separate provider requests
are retained as separate observations; their hashes remain useful for
comparison, but no longer act as deduplication keys. The migration refuses a
downgrade if repeated evidence would make the former unique constraints
unsafe to recreate.

Raw OHLCV observations follow the same rule: the conflict key includes the
fetch observation timestamp, so a later provider revision of an existing bar
creates a new raw observation instead of overwriting the earlier response.
Canonical bars remain projections and may be refreshed independently. A retry
with the same observation timestamp is also ignored at the raw-evidence
boundary rather than overwriting the retained payload.

Universe and identity review queues follow the same projection/evidence split.
The mutable lifecycle and reconciliation/quarantine rows remain current review
projections, while every provider lifecycle envelope, reconciliation ambiguity,
unresolved-universe candidate, and identity-quarantine candidate is appended to
its corresponding observation table. Repeated evidence therefore remains
available even when the same queue item is observed again with changed payload,
reason, venue, or candidate identifiers; queue deduplication never discards the
provider response that caused the review state.

General market events follow the same projection/evidence split. The canonical
`market_event` row remains keyed by provider event identity for reconciliation,
while each fetched provider payload is appended to `market_event_observation`.

Tokenized-asset metadata follows the same rule. `tokenized_asset_detail` is
the mutable latest-state projection used by identity and quote workflows, while
each catalog, metadata, or quote refresh appends its original provider payload
to `tokenized_asset_observation` with provider asset identity and both provider
observation and local fetch timestamps. Repeated identical responses are kept;
they are quota/audit evidence and are never deduplicated or pruned.

Fundamental facts and short-interest data also have a projection/evidence
split. The existing point-in-time rows remain compatibility projections, while
every provider response is appended to `fundamental_fact_observation` or
`short_interest_provider_observation`. A later revision for the same filing or
settlement date therefore remains available for replay and audit instead of
being silently ignored by the natural-key projection.

Option quote points follow the same rule: normalized `OptionQuotePoint` rows
serve time-series queries, while each chain or historical quote response is
also appended to `option_quote_observation` with the original payload and local
fetch timestamp. A provider revision sharing an observation timestamp cannot
erase the earlier response.

The mapping is enforced consistently by normal application routing, the direct
live-probe planner, and the manifest preflight. Missing, duplicated, or
non-existent `reconciled_dimensions` entries fail closed before transport;
they cannot authorize all unknown pools by omission.

For MarketData.app, a successful `/user/` response consumes at least one daily
credit, and the provider's Go SDK documentation explicitly describes the
reported consumed value as the charge for that `/user/` request. The usage
operation therefore reserves one credit after a baseline exists. On the first
snapshot only, the provider-specific `account_usage_bootstrap` mapping permits
the bounded usage request to reconcile the exact `credits_per_day` pool from
the native post-request counters; it does not waive any other quota dimension
or allow data/options reads before the baseline is established. Sources:
[rate-limit rules](https://www.marketdata.app/docs/api/rate-limiting/) and
[official Go `/user/` documentation](https://www.marketdata.app/docs/sdk/go/utilities/user/).

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

Owner storage decision (2026-10-05): private, persistent storage of data
returned by every provider is approved. This is settled and is not a routing
gate. Provider login/access, plan quotas, and any restrictions in a provider's
own contract remain separate provider-side facts; they are not requests for
the owner to approve storage again.

OTC, simply put: we need a complete list once, then FINRA's Daily List can
keep it updated. That Daily List reports changes; it is not the starting list.
Alpha Vantage offers the first cheap path to test: its official
`LISTING_STATUS` endpoint says it returns all active US stocks and ETFs as a
single CSV. Its public documentation does not say which venues are included,
so we cannot yet claim it covers every OTC venue. The adapter now downloads the
CSV once, keeps the exact response and every row, and separates ETF rows from
stocks. The required live test is still blocked: the owner reports no outside
use in the last 24 hours, and that evidence was recorded for the current
short rolling windows, but the live runner cannot keep the one-second baseline
valid through its full preflight yet.
Massive has a complete daily list, but the free Individual plan is not needed
for the authoritative OTC baseline. FINRA's public Symbol Directory is backed
by the official Query API `otcMarket/otcSecurityMaster` dataset. A credentialed
live traversal on 2026-10-07 returned exactly 18,009 rows and 18,009 unique
symbols as of 2026-10-07 in four losslessly retained pages (5,000 + 5,000 +
5,000 + 3,009). This is now the complete current OTC starting roster. The
Daily List supplies subsequent additions, deletions, symbol/name changes, and
corporate-action deltas. Every raw partition/page response is persisted before
normalization, and a failed or partial traversal is never accepted as a
complete snapshot. ORF remains an optional separately entitled source, not a
dependency for the baseline. Sources: [FINRA Symbol Directory](https://otce.finra.org/otce/symbol-directory),
[FINRA Query API documentation](https://developer.finra.org/docs), and
[FINRA Daily List](https://otce.finra.org/otce/dailyList).

| Provider | Implemented data surface | Credential/config key | Documented usage contract | Reset/scope | Routing status |
|---|---|---|---|---|---|
| Alpaca | US stocks/ETFs + crypto OHLCV, latest, authenticated asset metadata (exchange/status/tradability/provider asset UUID), corporate actions, assets | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_TRADING_BASE_URL`, optional `ALPACA_REVIEWED_RESET`, `ALPACA_QUOTA_EVIDENCE` | Trading API Basic is free for paper/live users; no separate daily data allowance is documented. The current official plan table states 200 historical API calls/minute, equity history since 2016, free real-time equities on IEX, and historical/latest data limited to the latest 15 minutes; the community clarification says paper and live keys share the same user-level subscription. Corporate-actions pages accept 1–1,000 records; `X-RateLimit-Limit`/`Remaining`/`Reset` headers are retained and reconciled against a rolling safety envelope. Sources: [official market-data plan table](https://docs.alpaca.markets/us/docs/about-market-data-api), [paper-key clarification](https://forum.alpaca.markets/t/key-limitations-on-paper-trading-keys/17789) | account / rolling 60-second safety envelope; free IEX feed and 15-minute recency boundary apply; paper/live assets host is explicit; every corporate-action page is persisted and resumed; Alpaca UUID is provider-native and is not promoted to a canonical FIGI/CIK | history/latest, metadata, account usage, and cursor pagination are fixture/live-covered. Automated persistent storage is within the owner's recorded private-use decision; current-source live evidence and a safe quota baseline remain required |
| Massive | US stock and OTC ticker search/reference universe, single-ticker metadata (CIK/FIGI, exchange, lifecycle, classification, description/branding), split-adjusted or raw aggregate OHLCV, historical splits/dividends, cursor-paginated IPO/market events | `MASSIVE_API_KEY` (or legacy `MARKETDATA_API_KEY`); Stocks Basic allowance is per asset class and shared by all keys on the account | Massive's current first-party Basic-access FAQ says reference data, corporate actions, and minute aggregates are available on Basic and the allowance is 5 REST requests/minute per asset class. These stock-provider operations all use the same Stocks bucket; there is no separate undocumented reference bucket. The provider's exact minute reset boundary and native current-use API are unpublished. Massive's account FAQ also confirms that multiple API keys on one account share the same subscription and limits, so rotating/adding a key cannot establish or expand the active allowance. Its account dashboard offers request monitoring (request ID, status, user agent, response size, IP/location, and key), but this is dashboard evidence rather than a documented API counter. Sources: [Basic access and rate limit](https://massive.com/knowledge-base/article/how-quickly-can-i-access-massives-market-date), [account/key FAQ](https://massive.com/knowledge-base/categories/account), [dashboard request monitoring](https://massive.com/blog/free-data-apis), [Stocks pricing and included features](https://massive.com/stocks), [All Tickers](https://massive.com/docs/rest/stocks/tickers/all-tickers) | Shared account-scoped 5-request rolling 60-second safety envelope across stock, reference, and corporate-action operations. Dashboard request monitoring can help an operator reconcile recent account use; no API snapshot or authoritative reset boundary is documented. A 429 without a usable provider reset pauses this provider for 60 seconds as local recovery behavior. OTC pages are followed to the provider's terminal cursor with no artificial page cap; every full raw page is committed before row processing, and quota-deferred scans resume from the persisted opaque cursor instead of re-fetching prior pages. If a scan spans invocations, provenance records that it is resumed; Massive never supplies lifecycle absence authority. | Massive's Individual terms describe personal use; the app is single-user/private. Provider license facts remain separately recorded and do not change the owner's authorization to privately store returned data. |
| Alpha Vantage | Raw daily, weekly, and monthly OHLCV, symbol search, active US stock/ETF listing CSV (venue coverage not documented), IPO calendar events, historical annual/quarterly earnings with EPS estimates and surprise metrics | `ALPHA_VANTAGE_API_KEY` | Current-key response (2026-10-06) recommends no faster than 1 request/second and indicated a 5-requests/minute ceiling; current official support confirms 25 requests/day but does not publish a minute cap or reset boundary. The listing-status endpoint returns one full CSV per request; daily `compact` output is latest 100 points, while documented weekly/monthly series expose long historical ranges; adjusted daily history is premium and weekly/monthly endpoints are raw; `EARNINGS` is one query per symbol | API key / per-key provider-observed 1-second pacing and 5/minute ceiling plus the published 25/day pool, each enforced separately with rolling safety windows | The complete bounded manifest passed 9/9 on 2026-10-09 using nine measured requests; the current-key short-window ceilings are reserved through the durable shared coordinator. The 1-second and 1-minute baselines are explicitly application-usage-only because Alpha Vantage exposes no native current counter; the 25/day pool remains separately tracked and is never seeded from those short-window baselines. Listing rows are retained, but venue coverage remains unverified. |
| SEC EDGAR | issuer/ticker/exchange directory, profiles, filings/earnings, XBRL facts, provisional IPO-pipeline filing candidates | `EDGAR_USER_AGENT` | 10 requests/sec total across an IP; the SEC says access resumes once traffic drops below the threshold but does not define a fixed bucket boundary | IP / provider-defined with an explicit rolling one-second application safety envelope | contract recorded; profile and complete directory pagination live-proven 2026-09-12 with the supplied contact value; duplicate ticker/CIK candidates are preserved as ambiguous and never silently resolved; IPO-pipeline case is bounded and candidate-only; User-Agent and SEC fair-access compliance remain required. The SEC says government-created and EDGAR public filing content are free to access and reuse ([Webmaster FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions)); third-party content inside filings is not treated as separately licensed provider data |
| Nasdaq Trader | Official `nasdaqlisted.txt` and `otherlisted.txt` NMS/other-exchange directories; daily listing/lifecycle snapshots | `NASDAQ_USER_AGENT` | Files are public download endpoints and must be fetched conditionally; Nasdaq Trader describes symbol lookup data as for internal non-commercial use unless separately licensed. | Provider source / per completed market day; conditional ETag/Last-Modified | Parsing and completeness checks are implemented. `otherlisted.txt` code `F` maps to Texas Stock Exchange MIC `TXSE`; TXSE identifies `F` as its SIP participant ID and `TXSE` as its MIC. All other unknown venue codes still fail closed. No per-provider owner storage approval is required; fetches still must follow the provider's published conditions and the app's daily request cap. Sources: [Nasdaq Trader symbol directory terms](https://nasdaqtrader.com/trader.aspx?id=symbollookup), [file definitions](https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs), [TXSE identifiers](https://www.txse.com/regulations/id-codes) |
| CTA Plan | Daily official Tape A/B universe, source participant, prior symbol, equity/local-issue/debt class, round lot, price increment | None; public anonymous file | CTA publishes no numeric HTTP quota; local policy reserves two requests per market day for directory index + dated CSV | Local deployment-wide request cap; not a vendor quota | Full index and CSV are stored raw before normalization; case-sensitive source symbols are preserved; unknown participant codes and malformed rows fail closed. Does not distinguish ETF/common-stock subtype and does not alone authorize whole-NMS absence. [CTA file](https://www.ctaplan.com/symbol-file), [specification](https://www.ctaplan.com/publicdocs/ctaplan/CTA_Symbol_File_Specification.pdf), [TXSE participant ID](https://www.txse.com/regulations/id-codes), [ISO MIC list](https://www.iso20022.org/market-identifier-codes) |
| OpenFIGI | FIGI/ISIN/CUSIP/SEDOL mapping and profile enrichment | optional `OPENFIGI_API_KEY` | Without key: 25 mapping requests/minute and at most 5 jobs/request. With key: 25 mapping requests/6 seconds and at most 100 jobs/request. The API exposes `ratelimit-limit`, `ratelimit-remaining`, and `ratelimit-reset`; HTTP 429 means the active window is exhausted | anonymous traffic is IP-scoped; keyed traffic is API-key-scoped; both use provider rolling/reset windows | exact contract switches from anonymous to keyed only when `OPENFIGI_API_KEY` is present; the adapter is fixture/live-covered and preserves native rate-limit headers. OpenFIGI says FIGI symbology has no licensing or reuse restrictions; third-party proprietary identifiers remain subject to their owners' licenses ([FAQ](https://www.openfigi.com/about/faq)) |
| Binance | public crypto OHLCV, ticker, USDT universe, native request-weight usage snapshot | none | Current Spot REST documentation exposes a 6,000 request-weight/min IP ceiling. Adapter operations use documented weights: single-symbol price 2 and exchange-info discovery 20. Historical OHLCV costs weight 2 per 1,000-candle page; the requested range is conservatively paged and reserved before execution. The bounded `/api/v3/time` account-usage probe reads `X-MBX-USED-WEIGHT-1M` and proves the current fixed-minute counter; response `Retry-After`/weight headers are retained on capacity failures | IP / fixed minute; 429/418 protection | exact-weight price/discovery and bounded historical operations remain baseline-gated until the native usage probe establishes the active fixed-minute window; no empty-ledger assumption. No per-provider owner storage approval is required; provider API terms and usage limits remain applicable. |
| Coinbase Exchange | public crypto candles, ticker, USD products | none | 10 public requests/sec, burst up to 15; candle responses cap at 300 bars | IP / lazy-fill token bucket | Owner's explicit provider-terms risk decision applies to private use. History, quote, and USD-products cases are in the live manifest. Coinbase publishes no current bucket-usage endpoint, so the durable coordinator tracks this app's usage across sessions; it does not represent unrelated traffic sharing the IP. |
| Kraken | public crypto OHLC, ticker, USD pairs | none | Kraken says public REST calls at 1 request/second or slower should stay within limits; OHLC/Trades are limited by IP and pair, other public endpoints by IP; REST OHLC returns at most the most recent 720 data points and does not provide older history through pagination | IP / pair / rolling | REST history follows the returned cursor for forward continuation; if a response hits the 720-row cap before the requested start, the adapter now errors instead of returning incomplete history as complete. Live probes are paced at 1.1 seconds and the durable coordinator accounts for this application's calls only; it cannot observe unrelated traffic sharing the egress IP. The required bounded live case covers a recent D1 window. Kraken publishes full-history OHLCVT ZIP archives from each pair's first trade plus quarterly incremental archives; a durable archive downloader/importer is still required for deep Kraken history. Sources: [Kraken public rate-limit guidance](https://support.kraken.com/articles/206548367-what-are-the-api-rate-limits-), [Kraken 720-point history limit and Trades alternative](https://support.kraken.com/in/articles/advanced-api-faq), [downloadable OHLCVT full-history archives](https://support.kraken.com/au/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data) |
| CoinGecko Demo | crypto search, metadata, market-cap universe | `COINGECKO_API_KEY`; configure `COINGECKO_REVIEWED_PLAN` per account | Current Demo pricing lists 100 calls/min and 10,000 calls/month; each successful request consumes one monthly credit, every request including failures consumes minute capacity, and monthly credits reset on the first UTC calendar day ([pricing](https://www.coingecko.com/en/api/pricing), [credit accounting](https://support.coingecko.com/hc/en-us/articles/13962109374489-How-does-CoinGecko-API-count-the-API-usage-credit), [reset](https://support.coingecko.com/hc/en-us/articles/16760509234713-When-does-my-request-volume-monthly-API-credit-reset)). CoinGecko's `/key` usage endpoint is Pro-only; the configured Demo key returned HTTP 401, error code 10005. The app does not retry it and does not advertise account usage for Demo. An older 2023 public-API article says 30/min for Demo; current plan pricing says 100/min ([older public-API article](https://support.coingecko.com/hc/en-us/articles/4538771776153-What-is-the-rate-limit-for-CoinGecko-API-public-plan)) | Demo API key / provider minute boundary unspecified; rolling 60-second application safety window and UTC calendar-month credit pool | Durable coordinator tracks this application's attempted minute requests and successful monthly credits; these are app-observed counters, not provider-reported totals. Runtimes sharing the key must share the coordinator or reconcile external usage. `/key` account usage becomes available only when the configured plan is changed to an entitled Pro tier. Provider terms remain informational under the owner's explicit private-use risk decision; technical quota/capability checks remain enforced |
| FINRA | consolidated short interest (OAuth Query API), OTC Daily List lifecycle/corporate-action deltas, and generic asynchronous Query API jobs | `FINRA_CLIENT_ID`, `FINRA_CLIENT_SECRET` | 1,200 synchronous requests/minute/IP; 20 asynchronous submissions/minute/dataset/account; max 5,000 records and a published 3 MB per-response synchronous ceiling. Short interest reserves two HTTP requests (cold OAuth + data) and 3,000,000 data bytes. Daily List reserves three HTTP requests (cold OAuth + partition index + data page) and 6,000,000 data bytes. Measured request/byte totals replace those upper-bound reservations after each operation. The public credential publishes a 10 GB monthly allowance and disables the credential until the first day of the following month. The native reset timezone and byte convention remain unconfirmed, so the provider-defined label is retained for audit while a conservative provider-scoped rolling 31-day safety envelope protects admission | OAuth client / IP + dataset/account + provider-defined monthly public-credential byte window with rolling 31-day application safety envelope; native reset boundary remains unresolved | synchronous datasets live-proven; async submit/poll/presigned-download remains an optional fail-closed transport helper rather than an admitted independent data capability |
| FINRA OTC data | Complete OTC Symbol Directory roster through Query API `otcSecurityMaster`; Daily List additions/deletions/symbol-name changes/corporate actions; optional ORF active/inactive masters | Query API: `FINRA_CLIENT_ID`, `FINRA_CLIENT_SECRET`; optional ORF: assigned TRAQS username, refresh token, and durable token-state file | 1,200 synchronous requests/minute/IP; 5,000 records/request; 3 MB maximum synchronous response; public credentials allow 10 GB downloaded/month. FINRA caps `offset` at 500,000, so larger datasets require filtered tranches rather than truncation. | Query API request pool is IP-scoped; the public-credential byte pool is account-scoped and shared with other FINRA Query API operations. The app uses a conservative durable rolling 31-day byte window because FINRA does not publish the native monthly reset boundary. | Live-proven on 2026-10-10: 18,017/18,017 unique symbols, four pages, stable partition date. The public Symbol Directory uses this same Query API; its four stable-key sorted pages matched the archived provider snapshot exactly, so this is pagination cross-check evidence, not independent-source corroboration. Every obtained raw page is committed before fetching its successor; duplicates, changing totals/dates, premature endings, and partial snapshots fail closed. Combined daily NMS/OTC reconciliation is scheduled for 21:00 UTC and enabled by default in Compose (`MARKET_UNIVERSE_RECONCILIATION_ENABLED=true`); verify target overrides and runtime health separately. This is distinct from the broad OHLCV refresh, disabled by default. ORF is optional and has a separate, unresolved product quota/access profile. Sources: [Symbol Directory](https://otce.finra.org/otce/symbol-directory), [Query API limits](https://developer.finra.org/docs), [Getting Started](https://developer.finra.org/node/1146). |
| OTC Markets Overnight Security Master (candidate) | Officially specified complete OTC security-master file containing OTC Markets security/company identifiers, symbols, names, security type/class, tier, reporting standard, status, reference price, and overnight-eligibility fields; pipe-delimited file plus a validation file with source/timestamp/record count; the candidate parser strictly validates the file shape and, when both files are supplied, rejects a record-count mismatch | commercial OTC Markets delivery/entitlement; specification names SFTP host `sftp.otcmarkets.com` and account-representative credentials, but grants no access | Files are published before each trading session at 5:25 PM and 7:20 PM ET on trading days, approximately 5 MB; CUSIP-included and no-CUSIP variants exist. Provider/file-delivery terms, quota, complete US-OTC coverage, and redistribution rights must be confirmed. The specification warns that CUSIP redistribution requires a separate CUSIP license | provider account / SFTP delivery contract / session cadence | **candidate only; source delivery and live routing are disabled**. This is the concrete alternative to the undocumented FINRA `otcSecurityMaster` candidate and remains outside the approved free-only routing budget until access and rights are explicitly authorized ([official specification](https://www.otcmarkets.com/files/OTC%20Markets%20Overnight%20Security%20Master%20Specification.pdf)) |
| FRED | macro/rates/FX daily series | `FRED_API_KEY` | FRED v1 documents up to 120 requests/minute before HTTP 429, but does not publish the enforcement scope or reset boundary; provider-adjustable limits and series-specific rights apply. Current terms restrict software/system-development and AI/ML-connected use plus storage/cache/archive/database incorporation absent prior written authority. FRED API-key guidance says each application user must use their own key | provider-defined scope / provider-defined minute reset until reviewed; adjustable | The owner's recorded private-use risk decision removes provider-term and retention requirements as routing gates. The local durable coordinator initializes and counts this application's requests only; it is not a provider-reported counter. Runtimes sharing the same key must share the coordinator or reconcile external calls. The v2 2-requests/second rule is not applied to this v1 adapter |
| Nasdaq Trader | official `nasdaqlisted.txt`/`otherlisted.txt` US NMS listing/lifecycle files | none | Nasdaq publishes no numeric quota for these files. The client imposes a strict maximum of two HTTP requests per calendar day (one conditional request per official file); this is a local safety ceiling, not a vendor allowance | public service / client-imposed deployment-wide daily cap | The two complete files are filtered and returned as one complete discovery page after their two conditional HTTP requests; the worker must not pseudo-paginate the already-downloaded in-memory snapshot and re-reserve the two-request cost for each local slice. The first local window is explicitly persisted at zero (`baseline_mode: local_zero`) before transport, diagnostics must not describe the cap as a Nasdaq-published quota, and two-file results remain NMS-focused rather than complete OTC coverage |
| CTA Plan | anonymous daily CTA Network A/B symbol file with listing participant, prior symbol, instrument class, round-lot and price increment | none | CTA publishes no numeric HTTP quota. Client safety policy caps the index + dated CSV at two requests per market day | public file / local deployment-wide safety cap | raw index and CSV are stored before normalization; unknown listing participants and malformed rows hold the snapshot incomplete. It complements the separate Nasdaq-listed/Tape C scope; it does not distinguish ETFs from common stock or independently authorize whole-NMS absence. Sources: [CTA symbol file](https://www.ctaplan.com/symbol-file), [layout](https://www.ctaplan.com/publicdocs/ctaplan/CTA_Symbol_File_Specification.pdf), [ISO MIC catalogue](https://www.iso20022.org/market-identifier-codes) |
| Tiingo | EOD history, search, profiles | `TIINGO_API_KEY` | Free Starter: 500 unique symbols/month, 50 requests/hour, 1,000/day, and 1 GB/month bandwidth. Tiingo's [general API documentation](https://www.tiingo.com/documentation/) states that hourly requests reset every hour, daily requests at midnight EST, and monthly bandwidth on the first of each month at midnight EST; it does not establish whether the hourly boundary is fixed/calendar or rolling, nor the distinct-symbol monthly anchor | API key / independent distinct-symbol and hourly pools with provider-scoped rolling 31-day/one-hour safety envelopes, plus calendar-day-EST daily and calendar-month-EST bandwidth pools | Tiingo's plan terms describe internal-use and retention limits; the owner's recorded private-use risk decision means these terms are not an approval gate for this single-user app. Routing remains blocked until every exposed operation has a reviewed response-byte reservation bound and current quota baselines are available. The Free Starter plan is not entitled to the separately sold Fundamentals add-on. On 2026-10-10, the legacy official blog's `/account/usage` link redirected to `www.tiingo.com/account/usage` and returned HTTP 404; an unauthenticated browser check also redirected to the app landing page. On 2026-10-11, one authenticated read-only GET to the documented API URL `https://api.tiingo.com/account/usage` redirected to `www.tiingo.com` and received Cloudflare HTTP 403 Error 1010 (`browser_signature_banned`), with no usage counters returned; the response explicitly said not to retry. This does not prove whether the endpoint works in a normal authenticated browser session, and no further request was made. See [terms](https://app.tiingo.com/tos/), [general API limits](https://www.tiingo.com/documentation/), [pricing](https://www.tiingo.com/about/pricing), and [legacy usage-link post](https://www.tiingo.com/blog/presenting-tiingo-api/) |
| Twelve Data | multi-timeframe candles, quote, search, US universe, and native account-usage snapshot | `TWELVE_DATA_API_KEY` | Basic publishes 8 weighted API credits/minute and 800 API requests/day; minute credits reset each minute and the daily request limit at 00:00 UTC. `/api_usage` costs one credit and exposes `api-credits-used`/`api-credits-left` plus body request counters. Sources: [pricing](https://twelvedata.com/pricing), [usage control](https://support.twelvedata.com/en/articles/5713553-control-over-api-usage), [credit/reset semantics](https://support.twelvedata.com/en/articles/5615854-credits) | API key / fixed minute-credit window + UTC calendar-day request window | bounded history is explicitly paged by start/end range and reserves `ceil(requested points / 5,000)` credits; `/stocks` discovery sends the documented `page` + `outputsize=500` bounds and filters one asset type per page. Native usage reconciles only unit-matched minute credits and daily request counts; the probe itself reserves one credit and one request. |
| Finnhub | profile/search, historical earnings, forward earnings calendar, and universe; candle adapter retained for higher entitlements | `FINNHUB_API_KEY` | The owner's dashboard was recorded on 2026-09-07 as a 60-calls/minute free-account ceiling; Finnhub's public docs separately state a 30-calls/second cap in addition to the plan limit. Finnhub's public docs do not describe the minute reset header, but the private live-usage ledger contains historical responses from this key with `X-RateLimit-Limit: 60`, `X-RateLimit-Remaining: 58`, and `X-RateLimit-Reset` as a Unix-epoch timestamp (observed 2026-09-15; reset was 2026-09-15 16:08:45 UTC). Treat this as evidence that the endpoint returned a native reset counter, not proof of current usage or a documented universal header contract. Separate rolling envelopes remain the enforced fallback. Sources: [Finnhub API rate-limit docs](https://finnhub.io/docs/api/websocket-trades); minute limit evidence: owner dashboard observation `operator_account_dashboard_2026-09-07`; historical response-header evidence: owner-private live-usage ledger, 2026-09-15 | token / independent minute + second provider boundaries with explicit rolling application envelopes for each dimension | profile, historical earnings, and forward calendar live-proven; both earnings surfaces are registered under `earnings`; every reviewed operation is explicitly charged against both rate dimensions, while an operation absent from the reviewed cost profile fails closed; free stock candles returned 403 and are explicitly non-routable; active shared-key usage baselines remain required before another call. No Finnhub requests were sent during the 2026-10-06 continuation. Finnhub's personal-use licensing language remains documented as provider context, not a written-approval gate for the owner's private-use deployment; current shared-key usage baselines and account entitlements remain required |
| Marketstack | daily EOD history; venue-scoped ticker discovery is implemented but currently fail-closed | `MARKETSTACK_API_KEY`, `MARKETSTACK_DISCOVERY_EXCHANGE` | Pricing and the current contact FAQ state 100 Free requests/month. The FAQ contains one contradictory 1,000/month sentence but elsewhere repeats the 100 cap; enforce the lower 100 requests per rolling 30 days until an exact native reset is confirmed. The API documentation separately states a 5 HTTP requests/second ceiling; enforce it with a rolling one-second API-key envelope because its exact bucket boundary is unpublished. Named symbols cost one request per symbol, including multi-symbol data queries; API errors are excluded. A fresh authenticated response on 2026-10-10 exposed only an unclassified `X-Rate-Limit-Remaining` counter, without a monthly limit or reset marker. Preserve it as an observation, not monthly headroom; the live snapshot therefore did not establish current account usage. Marketstack's current FAQ directs users to the Account Dashboard for current usage; no documented machine-readable usage endpoint has been found, so the external starting balance may require dashboard evidence. The reviewed sources do **not** establish the quota charge for `/exchanges/{mic}/tickers` pages. Do not infer that one fetched page costs one monthly request from pagination documentation or per-symbol billing language; an evidenced positive `MARKETSTACK_DISCOVERY_MAX_PAGE_COST` and source are required before discovery can run. Account-plan limit overrides require quota evidence; an optional reviewed native reset can replace the stricter monthly safety window | API key / distinct provider-documented one-second rate ceiling and provider-defined monthly pool protected by provider-specific rolling safety windows | History follows returned pagination. Venue discovery uses the provider-documented `/exchanges/{mic}/tickers` path, follows strict raw-page totals, and stores the full raw payload for each page before normalization. A MIC must be explicitly configured; this capability is supplementary and grants no whole-US universe or absence authority. Live-test status is recorded in the workstream and remains separate from the independent monthly-usage-baseline check. Sources: [pricing](https://marketstack.com/pricing), [billing FAQ](https://marketstack.com/contact), [API rate limit and endpoints](https://marketstack-wp.apilayer.green/documentation/), [agreement](https://marketstack.com/agreement) |
| EODHD | daily/weekly/monthly EOD history (free tier: one-year history), US exchange-symbol list, native `/api/user` account-usage snapshot; Fundamentals/profile adapter is entitlement-gated | `EODHD_API_KEY`; optional `EODHD_REVIEWED_MINUTE_LIMIT`, `EODHD_REVIEWED_MINUTE_RESET`, and `EODHD_MINUTE_QUOTA_EVIDENCE` for a reviewed key-specific override | The detailed [API limits page](https://eodhd.com/financial-apis/api-limits) documents 1,000 HTTP requests/minute, resetting every minute, with `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `Retry-After` on 429. The Free-plan card conflicts at 20/minute. The configured key's `/api/user` response reported 1,200 limit / 1,199 remaining at 2026-10-14 16:27:48Z; the repo defaults to the documented 1,000/minute and only applies 1,200 when the account-specific override has matching evidence. Free plan separately allows 20 weighted API-call credits/day, resetting midnight GMT. Costs: EOD history/search/lists/calendar 1, intraday/technical/news 5, fundamentals/options/macroeconomics 10, whole-exchange Bulk 100; `/api/user` costs zero daily credits but consumes a minute request. Free EOD history is one-year; Fundamentals/profile remains non-routable unless entitled (this key returned HTTP 403). | The owner's recorded private-use risk decision removes provider terms/display restrictions as approval gates for this single-user app. `/api/user` may bootstrap native quota evidence. Free EOD history remains one-year, and Fundamentals/profile stays non-routable where the configured account returned HTTP 403. |
| FMP | stable-API daily history, profile, earnings calendar, quotes; stock-list discovery is account-entitlement gated | `FMP_API_KEY`, `FMP_REVIEWED_PLAN`, `FMP_STOCK_LIST_ENTITLED` | The official [personal pricing table](https://site.financialmodelingprep.com/developer/docs/pricing) publishes Basic at 250 calls/day + 500 MB per trailing 30 days; Starter at 300 calls/minute + 20 GB; Premium at 750 calls/minute + 50 GB; Ultimate at 3,000 calls/minute + 150 GB. FMP's [FAQ](https://site.financialmodelingprep.com/de/faqs?code=analyst) says Basic's 24-hour allowance resets at 3 PM EST; enforce a rolling 24-hour safety window unless an account-reviewed native boundary is configured. The [dashboard](https://site.financialmodelingprep.com/developer/docs/dashboard) reports calls and bandwidth used over 30 days. The adapter reads its credential-keyed usage endpoint, validates the response against the selected plan, and archives only safe counter fields; because the response has no native reset timestamp, application rolling-window anchors remain conservative. The configured Basic key returned HTTP 402 for the documented [stable stock-list endpoint](https://site.financialmodelingprep.com/developer/docs/stable/company-symbols-list); `FMP_STOCK_LIST_ENTITLED` therefore defaults false, and discovery stays blocked until entitlement for the configured key is confirmed. The selected tier remains configuration-driven; published MB/GB limits are conservatively represented as decimal bytes and bandwidth is tracked separately over rolling 30 days. FMP's [EOD history](https://site.financialmodelingprep.com/developer/docs/stable/historical-price-eod-full) response is capped at 5,000 records; the adapter splits daily ranges into 4,500-calendar-day requests, reserves the exact request count, and rejects a capped response rather than silently treating it as complete. FMP's [earnings calendar](https://site.financialmodelingprep.com/developer/docs/stable/earnings-calendar) allows 4,000 rows/page and date windows up to 90 days; numeric pages are durably resumed, with each page independently metered and persisted. | API-key scoped plan pool plus the tier's trailing-30-day bandwidth pool; tracked as distinct usage dimensions | The owner has accepted private durable storage; quota, endpoint entitlement, and operation-specific response bounds remain independent controls. |
| Tradier | US daily history, quotes/search, current option expirations/chains with provider Greeks | `TRADIER_API_KEY` | 60/min sandbox; 120/min production market-data quota, response headers expose remaining/reset | token / minute | option endpoints normalize OCC symbols, contract fields, and nested Greeks; account live evidence required |
| MarketData.app | delayed US stocks/options candles, option expirations, current option-chain normalization, and historical/current single-contract option quotes | `MARKETDATA_APP_API_KEY` | Plan-specific: Free Forever 100/day; Starter Trial 10,000/day until configured expiry; Starter 10,000/day; Trader Trial/Trader 100,000/day. Resets 09:30 ET; 50 account-wide concurrent requests; free/trial data is at least 24h delayed and limited to one year; stock candles cost 1 credit per 1,000 returned candles (date-granular requests use a conservative full-day bound for intraday resolutions); expirations cost 1 credit/call, `/user/` usage reads consume at least 1 credit on a successful response, current chain/quote calls cost per returned contract/symbol, historical quotes/chains per 1,000 observations/contracts | key / reset-day credits + durable in-flight concurrency; configure exact plan, matching limit, and timezone-aware trial expiry separately per environment; trial quota automatically falls back to Free Forever 100/day after expiry; response-dependent candle/option costs must be estimated or bounded before routing; option-chain admission additionally requires `MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS` | credentialed daily-candle, expirations/option-chain, and historical option-quote adapter paths live-proven 2026-09-12; account `/user/` headers expose quota state but not Starter Trial vs paid Starter, so operator configuration is authoritative; authenticated counters persist across sessions without widening routing limits |
| IBKR | read-only Client Portal Gateway security search, instrument profile, raw historical OHLCV for equities and futures, and latest-price snapshots; options-specific methods remain unimplemented | `IBKR_READ_ONLY_URL`, `IBKR_READ_ONLY_SESSION_COOKIE`, optional `IBKR_CONID_MAP` | Global 10 requests/sec/session; REST historical endpoint 50 requests/minute and max 1,000 bars per response; the separate WebSocket historical-streaming API allows at most 5 concurrent subscriptions (not applied to this REST adapter); expired futures history is unavailable beyond two years after expiry; endpoint-specific pacing and penalty-box behavior apply | authenticated gateway session / rolling endpoint windows; interactive gateway login is required and may need to be renewed daily | concrete adapter is fixture-covered; raw history/latest/profile remain non-routable until a gateway session and bounded live evidence are supplied; futures should use an explicit provider `conid` mapping when symbol search is ambiguous; adjusted history is filtered before routing |
| xStocks (Backed) | tokenized equity/ETF catalogue, deployments, indicative prices, multipliers, supply and corporate actions | none for documented public reads; optional `XSTOCKS_API_KEY` | Public API responses exposed a shared 1,000-request rolling-minute `X-RateLimit-Limit`/`Remaining`/`Reset` contract across assets and corporate-actions endpoints; verified 2026-09-14 and reconciled only on an exact limit match | public API / rolling minute; provider headers are retained and cumulative use is durably reconciled | The owner has explicitly accepted private automated use and durable retention despite provider-term restrictions, so partner-term approval is not an outstanding gate. Routing remains disabled until the deployment's jurisdiction/data eligibility is evidenced through `XSTOCKS_MARKET_DATA_USE_JURISDICTION_AUTHORIZED` and `XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE`; an optional expiry can revoke admission automatically |
| Robinhood Chain Stock Tokens | tokenized-stock catalogue, chain deployments, multiplier, indicative bid/ask and corporate actions | none for documented public reads | 60 requests/sec for the public Stock Token API; cached responses and edge `429` responses apply | public IP / rolling second | bounded live asset + quote probe passed; only application-observed usage is tracked in the durable shared coordinator because no native current-use counter is documented; read-only and non-routable until entitlement is promoted |
| Bybit xStocks | xStocks spot instrument catalogue and ticker bid/ask/last | none for public market-data endpoints | Anonymous V5 traffic is bounded by the documented 600 HTTP requests per 5 seconds per IP ceiling. The separate rolling endpoint/UID headers describe authenticated API-rate state and are not a prerequisite for these unauthenticated market endpoints; they are retained as telemetry if present but are not conflated with the IP pool | shared outbound IP / rolling 5 seconds | The owner's private-use/retention decision removes provider-term acceptance as a gate. Production routing remains fail-closed until both actual deployment egress and the intended user's eligibility jurisdiction are evidenced: `BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED`/`..._EVIDENCE` establish egress; `BYBIT_XSTOCKS_MARKET_DATA_USE_USER_JURISDICTION_AUTHORIZED`/`..._EVIDENCE` establish eligibility. Current Bybit xStocks material excludes EEA users (including Portugal); a permitted egress IP does not override a user-location restriction. |
| Gate TradFi stock API | public US stock-token symbol catalogue and order-book bid/ask | none for public symbol/order-book endpoints | 5 requests/sec/IP for each documented public TradFi stock endpoint (`/stock/symbols`, `/stock/symbols/detail`, `/stock/market/{symbol}/orderbook`) | IP / rolling | bounded live symbol + order-book probe passed; the runtime applies a conservative aggregate 5-request/sec capability window and persists app usage. `X-Gate-RateLimit-Requests-Remain` and `-Limit` are retained as telemetry; `-Reset-Timestamp` is not treated as a normal reset boundary because Gate says it is a reset time only after exhaustion and otherwise returns the current timestamp |
| Kraken xStocks | provider-native xStocks pair discovery, metadata, and current ticker where exposed by Kraken Spot REST | Public read-only endpoints are unauthenticated; Kraken separately advertises API Partner Program access for partner integrations. Its regional warning specifically concerns xStocks order-book trading, not the read-only ticker demonstrated here | same Kraken public Spot REST safe frequency and shared-IP accounting as Kraken crypto: one request/second; operation costs are one request each after removing the redundant metadata lookup from price reads | shared Kraken IP / rolling | `AssetPairs` must be filtered with `aclass_base=tokenized_asset`; `Ticker` must include `asset_class=tokenized_asset`. Internal pair keys can alias the same market, so canonical identity uses `altname` while retaining all provider keys in raw metadata; Kraken's token base suffix and `ZUSD` quote are normalized separately. A Portugal-hosted live test on 2026-10-10 passed discovery, asset lookup, and ticker reads for one xStock in three paced requests. This proves those calls work for that observed market and host, not whole-catalogue completeness or trading entitlement. Sources: [Kraken API changelog](https://docs-legacy.kraken.com/api/docs/change-log/), [Kraken SDK xStocks example](https://python-kraken-sdk.readthedocs.io/en/stable/03_examples/rest_examples/xstocks_rest_examples.html), [Partner program](https://blog.kraken.com/product/api/kraken-api-partner-program-xstocks), [availability](https://support.kraken.com/articles/xstocks-availability). |
| Ondo Global Markets | authenticated tokenized US stock/ETF metadata, chain addresses/ISIN/tags, indicative latest prices, display-only primary/underlying market summaries (including 24-hour price history and underlying metrics), OHLC candles, and canonical daily history with local WEEK/MONTH/YEAR rollups | `ONDO_GLOBAL_MARKETS_API_KEY` | OpenAPI documents HTTP 429/account rate limiting but no numeric quota; endpoint caching and display-only/non-oracle restrictions apply | API key/account / provider-defined | User-deferred for now; fixture coverage exists, but no live credential evidence or numeric quota contract is recorded. The owner's private-use decision means provider-term review is not an approval gate; quota/account entitlement and any non-overridable legal or geographic restrictions remain separate evidence requirements. |
| Dinari | partner-authenticated dShare stock/ETF metadata, provider UUIDs, CAIP-10 deployments, FIGI/CIK/CUSIP metadata, current fair price, bid/ask quote, DAY/WEEK/MONTH/YEAR aggregate history, news, dividends, and splits | `DINARI_API_KEY_ID`, `DINARI_API_SECRET_KEY`, `DINARI_API_BASE_URL` | Current public docs do not publish a Sandbox-specific quota, reset, usage counter, or endpoint-weight schedule. A public API license/SLA template dated 2024-06-11 states a general maximum of 1,000,000 calls per rolling 30 days, but applicability to this Sandbox key is unverified; do not treat it as the account's active entitlement. Free Sandbox access is available while evaluating/building, while production API access officially starts at **$2,000/month**. The market-data guide calls the feed best-effort and advises a dedicated provider for intensive use; US SIP/NBBO quotes are metered and may incur per-query fees ([API license/SLA](https://assets.dinari.com/forms/Dinari_API_License_w_SLA_20240611.pdf), [official partner fees](https://docs.dinari.com/docs/fees), [Stock Data](https://docs.dinari.com/docs/stock-data), [US data rules](https://docs.dinari.com/docs/us)) | API key ID/secret + partner account / provider-defined | replacement Sandbox pair live-proven 2026-09-16 against https://api-enterprise.sandbox.dinari.com/api/v2 via the explicit 20-request application-capped canary (14 HTTP requests observed); stock and split catalogues use the current cursor contract (`limit`/`order`/`next`) with explicit legacy list fallback and explicit in-order continuation; ticker-like lookups use Dinari's documented `symbols[]` filter rather than assuming the first page is complete; UUID downstream reads reuse only validated records from the current provider instance, and a Dinari-only two-retry HTTP-500 recovery is bounded/telemetrized; Sandbox acceptance remains blocked on exact account-specific quota/reset/operation-cost evidence. Production routing separately requires its commercial account entitlement and any applicable legal/geographic eligibility. Provider-term review is not an owner-approval gate. |
| Alpaca tokenization network | catalogue-only tokenization-network candidate, distinct from Alpaca market-data keys | authorized-participant access required | Market-data credentials do not entitle tokenization-network access | account / unknown | descriptor only; not routable |
| yfinance | legacy broad fallback, options/futures compatibility only | none | No official quota/SLA; unofficial scraping | unknown | legacy-only and disabled by default |
| ETF holdings internal | platform's issuer/SEC holdings ingestion | internal configuration | Internal job/provider budgets, not an external market-data API | internal | generic bridge only; issuer-specific work remains on ETF branch |

### Data retention and provider terms

Marketstack follow-up, 2026-10-11: first-party docs identify the
exchange-scoped directory route as `/exchanges/{mic}/tickers` and document
`limit`/`offset` pagination up to 1,000 rows per page. Its FAQ says monthly
usage is billed per specific ticker lookup, multi-symbol lookups consume one
unit per requested ticker, and HTTP API errors do not count. The docs do not
say whether a directory page is billed as one request or by the number of
returned tickers. That directory operation therefore remains non-routable
until its page charge and current monthly account usage are established; do not
infer either from the pagination shape. Sources: [Marketstack API docs](https://marketstack-wp.apilayer.green/documentation/), [Marketstack billing FAQ](https://marketstack.com/faq), [Marketstack pricing](https://marketstack.com/pricing/).

Massive's quota contract remains five REST requests/minute per asset class,
shared across account keys. Since no provider-native use counter/reset boundary
is published, the local zero seed is explicitly application-only and the
coordinator enforces a shared rolling 60-second app-usage envelope; external
calls outside the managed application are not represented by that counter.
The 2026-10-11 single-case preflight passed without transport, but does not
replace the bounded current-source live test. Source: [Massive Basic limits](https://massive.com/knowledge-base/article/how-quickly-can-i-access-massives-market-date).

On 2026-10-05 the owner approved private, persistent storage for data returned
by every provider. The owner has also explicitly directed this single-user
research app to proceed with private automated use and retention even where a
provider's terms would otherwise require separate written permission. Do not
ask for those approvals again.

`PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK=true` records that operator
decision. It does not claim that any provider granted an exception. It removes
provider-term and retention clauses as routing gates for this owner's app;
authentication, account entitlement, quota, metering, service availability,
and geographic or other access restrictions remain enforced and visible. The
code default and Compose fallback remain `false` so an unconfigured
environment fails closed. The approved owner configuration sets it to `true`
in each environment that runs this single-user app; Compose passes that value
to both backend API and worker processes.

Provider-specific account limits, unresolved costs, entitlements, and genuine
access restrictions remain listed in the tables and live-preflight report.

### 2026-10-14 EODHD limits audit

The detailed [API-limits page](https://eodhd.com/financial-apis/api-limits)
specifies 1,000 HTTP requests/minute and instructs clients to use the native
headers. Its Free-plan pricing card conflicts at 20/minute. On 2026-10-14 the
configured key returned `X-RateLimit-Limit: 1200` and
`X-RateLimit-Remaining: 1199`; this is preserved as account-specific evidence,
not an automatic widening. The checked-in default is the documented 1,000/minute
ceiling; a matching explicit environment override is required to use the
observed 1,200 for this key. The separate Free-plan daily allowance is 20
weighted API-call credits, resetting at midnight GMT. Endpoint costs distinguish
request-rate units from daily call credits; `/api/user` costs zero daily credits
but does consume one request in the per-minute pool.

The `/api/user` endpoint lazily resets the daily counter on the first request
after midnight GMT. When it reports an older `apiRequestsDate`, the implementation
retains that last-active-day count as its own observation and reconciles zero
usage for the current GMT day; it does not carry yesterday's credits forward
or fabricate a current-day count. The free historical EOD endpoint remains
limited to one year, and Fundamentals/profile access remains separately
entitlement-gated (the configured free key returned HTTP 403).

### 2026-10-01 EODHD extra-call balance retention

EODHD's documented `/user` response also includes `extraLimit`, the remaining
balance of purchased extra API calls. This is a non-expiring buffer consumed
only after the daily call allowance is exhausted; it does not increase the
daily limit and has no daily reset boundary. The adapter now retains it as the
observation-only `extra_calls` dimension (`remaining` only), while preserving
the complete provider body in the durable usage observation. It is deliberately
not admitted to routing or baseline reconciliation because it is a balance,
not a reviewed quota window.

### 2026-10-02 Marketstack empty-page pagination handling

Marketstack EOD pagination may return an explicit zero-count page when a
symbol/date range has no observations. The adapter now treats `count: 0` as a
terminal empty result only when it does not contradict the declared `total`;
an empty page before a positive total remains a typed failure so missing rows
cannot be silently accepted. The full optional-provider suite covers both
valid empty terminal pages and contradictory metadata.

### 2026-09-25 Tiingo usage-account audit

Tiingo's current official documentation publishes the Starter ceilings and
reset families (hourly requests, daily requests at midnight Eastern, and
monthly bandwidth at the first of the month Eastern), but its documented
`/account/usage` URL redirects from the API host to a web account page rather
than returning a machine-readable usage payload. The implementation therefore
does not fabricate an account baseline from the plan card or from local request
counts. Tiingo remains fail-closed until a reviewed machine-readable usage
source or explicit operator evidence establishes the account's prior usage and
any unresolved reset model; operation byte bounds and internal-use terms remain
separate admission controls.

Nasdaq Trader's directory is listing evidence, not a complete delisting-event feed.
The adapter excludes test issues, retains Nasdaq Financial Status Indicators
(including deficient or bankrupt-but-listed issues), and uses repeated complete
absence plus separate lifecycle evidence before marking a listing inactive.
See the [official symbol-directory definitions](https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs).

In plain English: FINRA's Daily List tells us what changed; the complete
starting list comes from FINRA's official Query API
`otcMarket/otcSecurityMaster` dataset. A credentialed traversal on 2026-10-07
returned 18,009 rows and 18,009 unique symbols across four pages with a stable
partition date. Each raw page is retained before normalization, and a partial
or inconsistent traversal cannot count as a complete snapshot. Daily List
records supply later lifecycle changes. Alpha Vantage's listing CSV is not an
OTC completeness source because its venue coverage is unspecified. Massive's
documented All Tickers `market=otc` route is an alternative technical source,
not the current authoritative baseline. FINRA ORF is a separate optional
active/inactive file product: it requires its own TRAQS access and agreement;
the FINRA Gateway key does not grant that access, and CUSIP content may require
separate licensing. Do not confuse ORF with the Query API source used for the
verified snapshot. The remaining acceptance check is a clean exact-source run
against the committed implementation; the historical 2026-10-07 traversal is
evidence, but is not a substitute for that exact-source check. Owner approval
for private persistent storage is already settled.
The adapter also sends `If-None-Match` and `If-Modified-Since` on subsequent
polls when Nasdaq returns `ETag` or `Last-Modified`, reusing the cached parsed
file on a `304 Not Modified`. This reduces repeated downloads without
inventing a numeric provider allowance. Because Nasdaq does not publish a
numeric polling quota, the client separately limits itself to one conditional
request per official file per calendar day (two requests total); this is a
local safety policy, not a vendor-reviewed quota.

The FRED adapter uses the v1 endpoint. Its [v1 errors documentation](https://fred.stlouisfed.org/docs/api/fred/errors.html)
states that up to 120 requests per minute are allowed before HTTP 429 and warns
that continued non-compliance can cause a temporary block, but it does not
publish the enforcement scope or reset boundary. The [FRED API terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html)
allow the provider to adjust bandwidth and transaction limits. The
separate [v2 errors documentation](https://fred.stlouisfed.org/docs/api/fred/v2/errors.html)
mentions a 2-requests/second threshold for v2; the runtime deliberately does
not apply that v2 rule to the v1 adapter. The current FRED terms contain
automated-use and retention restrictions. The owner has explicitly accepted
that provider-terms risk for this private, single-user application; the local
`PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK=true` setting records that choice
and does not claim FRED granted an exception. Individual series can contain
third-party data, which remains documented as a provider fact but is not an
owner-consent gate under the owner's decision.

The [FRED API-key guidance](https://fred.stlouisfed.org/docs/api/api_key.html)
says every application should have a distinct key and every user of an
application must use their own key. If an application is built for other users,
the API terms also require the app to link the terms, bind users to them in its
own terms, provide an appropriate privacy policy where applicable, and display
the required non-endorsement notice. This integration has one server-configured
key and no per-user-key or user-facing FRED-terms flow. Multi-user FRED support
is not enabled. For the owner's private deployment, the explicit terms-risk
setting bypasses these provider-term controls. It does not bypass quota
admission or live tests.

For this owner configuration, the app enforces FRED's published 120-requests-
per-minute v1 ceiling with one durable shared API-key bucket and a rolling
60-second safety window. This is the app's conservative limiter, not a claim
that FRED uses that scope or reset boundary: both provider details remain
explicitly marked unpublished in the contract. The provider may change limits;
a FRED 429 stops further FRED calls and requires the contract to be reviewed.
Other deployments keep the default-off terms gate and may configure the
explicit `FRED_REVIEWED_*` controls with account-specific evidence. The
owner-risk setting never substitutes for credentials, quota reservations, or
measured live responses.
Missing `FRED_API_KEY` raises an explicit
`ProviderNotConfiguredError`; HTTP 429/418 responses are preserved as typed
capacity failures with provider headers and `Retry-After` timestamps rather
than returning an empty series or price. Do not enable a new series merely
because another series has an authority reference.

Coinbase Exchange publishes a technical public REST ceiling of 10
requests/second/IP with a burst of 15, implemented as a lazy-fill token bucket
(continuous refill, no calendar reset). Its [official REST rate-limit documentation](https://docs.cdp.coinbase.com/exchange/rest-api/rate-limits)
defines the bucket behavior; its [US market-data terms](https://www.coinbase.com/legal/market_data?country=US&currency=USD)
describe restrictions on automated and AI-related use. The owner has explicitly
accepted provider-terms risk for private, single-user research use; the local
`PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK=true` records that decision without
claiming a provider exception. The account's access, exact public bucket, and
429 behavior remain enforced. Live cases now cover one bounded daily candle,
one ticker quote, and the USD product catalogue. Coinbase does not document a
current bucket-usage counter, so the durable coordinator records this app's
requests across sessions and initializes an explicit app-usage-only baseline;
it does not claim visibility into unrelated traffic from the same IP.
Marketstack's [pricing page](https://marketstack.com/pricing) publishes the
Free plan at 100 requests/month. The [FAQ](https://marketstack.com/faq) has one
contradictory 1,000-request answer but elsewhere says the Free plan serves
accounts below 100; the [contact FAQ](https://marketstack.com/contact) repeats
the 100-request cap and per-symbol charging rule. The provider-specific
contract retains that conflict while enforcing no more than 100 requests in
any rolling 30 days, because the exact monthly reset boundary is unpublished.
An account-plan limit override requires quota evidence; a reviewed native reset
is optional and replaces the stricter rolling window if supplied. Marketstack
also documents a separate ceiling of **5 HTTP requests per second**; the app
enforces it with a rolling one-second API-key envelope because the provider
does not publish that rate bucket's exact boundary. This ceiling is independent
of the monthly credit pool and its account-usage baseline. Marketstack
counts one request per ticker even when a request contains multiple symbols,
does not count API errors, and documents notifications at 75%, 90%, and 100% of the allowance. Its
[overage documentation](https://marketstack.com/billing-overages-documentation)
describes a maximum 5% overdraft and disabling at 120% unless overage billing
is enabled. Those are account-billing behaviors, not permission to route; the
client stops at the configured cap and does not rely on overage billing.
The explicit `MARKETSTACK_DISCOVERY_EXCHANGE` requirement is operation-scoped:
ticker discovery/reconciliation stays disabled until a MIC and safe page-cost
bound are configured, while EOD history and quote reads may route with the API
key alone. The adapter uses Marketstack's documented
`/exchanges/{mic}/tickers` route, not an assumed `exchange=` filter on
`/tickers`. Its request specifies an exchange and no individual symbols, so the
provider's one-request-per-named-symbol rule cannot simply be applied to each
returned row; however, pagination documentation does not establish the
monthly charge for this catalogue endpoint either. Therefore the charge is
unknown, not one call per page or one call per symbol. Require a provider-native
counter observation or specific first-party billing evidence before setting
`MARKETSTACK_DISCOVERY_MAX_PAGE_COST` and its evidence reference. The full raw
response page is durably archived before normalization. Discovery is a
supplementary single-MIC catalogue, not evidence of complete US venue/listing
coverage or authority to deactivate other venues. The [APILayer rate-limit
documentation](https://marketplace.apilayer.com/docs/article/rate-limits)
documents day/month limit and remaining headers for its APIs, but does not
establish Marketstack's exact reset boundary or confirm the charge for this
catalogue endpoint. Those exact headers are allow-listed for telemetry, but
the current live evidence does not establish a page-specific quota delta.
Until a measured counter change or provider-specific billing statement
confirms this endpoint's page-cost semantics, discovery remains fail-closed.

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

Tiingo and FMP have bandwidth pools but do not publish a universal maximum
response size for each adapter operation. Tiingo's EOD docs describe the
response fields and inclusive date-range query, but no maximum response rows or
bytes. The app therefore uses explicitly identified *application reservation
budgets*, not purported vendor limits. Tiingo history is split into complete,
gapless calendar-year requests; each request reserves its operation-specific
byte budget, and the total reservation is multiplied by the exact number of
requests. The defaults are configurable and can be tightened or widened by
operation. If a response exceeds its budget, the complete response is retained
in the provider request log and the operation fails without truncating its
body; it is not silently treated as complete canonical data. See Tiingo's
[EOD endpoint schema](https://www.tiingo.com/documentation/end-of-day) and
[plan bandwidth limits](https://www.tiingo.com/pricing).

FMP also has no universal operation response-size maximum. Its complete
per-operation map is therefore seeded with application reservation budgets,
not purported vendor limits: 1 MiB per EOD response, 64 KiB per quote, 256 KiB
per profile, 8 MiB per 4,000-row earnings page, and 32 MiB for the unpaged
stock-list response. That stock-list endpoint is independently gated: the
configured Basic key returned HTTP 402 in a live probe, so `FMP_STOCK_LIST_ENTITLED`
defaults to `false`; changing the plan label alone does not enable discovery.
The EOD adapter requests no more than 4,500 calendar days
per response under FMP's documented 5,000-row cap; earnings pages follow the
documented 4,000-row limit. Exact history request counts multiply each
per-response budget before transport. These limits are configurable. An
over-budget complete body is retained and the operation fails; no rows are
silently truncated or dropped. FMP's [current official pricing](https://site.financialmodelingprep.com/developer/docs/pricing)
lists Basic at 250 calls/day and 500 MB over the trailing 30 days; its [FAQ](https://site.financialmodelingprep.com/de/faqs?code=analyst)
documents the 24-hour reset at 3 PM EST. FMP's [dashboard](https://site.financialmodelingprep.com/developer/docs/dashboard)
shows calls and bandwidth, but reviewed API docs do not document a public
account-usage API. The integration uses the dashboard's credential-keyed usage
endpoint (an undocumented/internal interface, so schema changes fail closed),
validates the response against the selected plan, and persists only sanitized
counters plus application-side rolling reset anchors.
The active quota tier is selected with `TIINGO_REVIEWED_PLAN=starter|power`;
these use the exact public individual-plan allowances. `custom` requires all
four exact account quotas and a non-secret evidence reference, and remains
non-routable if any value is missing. This makes a future plan change a
configuration change rather than a code edit. Current public pricing lists
Starter at 500 unique symbols/month, 50 requests/hour, 1,000/day, and 1 GB
bandwidth/month; Power at 110,237 symbols/month, 10,000/hour, 100,000/day,
and 40 GB/month. The previously owner-reported 2 GB bandwidth figure is not
treated as a quota because it may describe usage rather than allowance; the
default remains the published Starter 1 GB ceiling until the account's exact
plan/allowance is confirmed. Reset families are timezone-aware where
documented; hourly and unique-symbol boundaries retain their provider-scoped
safety envelopes until Tiingo establishes their exact anchors. See Tiingo's
[pricing table](https://www.tiingo.com/about/pricing) and [general usage
documentation](https://www.tiingo.com/documentation/).
`TIINGO_OPERATION_BYTE_BOUNDS` and `FMP_OPERATION_BYTE_BOUNDS` are JSON maps:

```env
# Tiingo defaults are application reservation budgets per HTTP response, not
# provider limits. A complete map is required; empty/partial maps disable it.
TIINGO_OPERATION_BYTE_BOUNDS={"fetch_ohlcv":1048576,"fetch_latest_ohlcv":1048576,"get_current_price":65536,"bulk_fetch":1048576,"search_instruments":4194304,"get_instrument_profile":1048576}
TIINGO_REVIEWED_PLAN=starter # starter, power, or custom
TIINGO_CUSTOM_UNIQUE_SYMBOLS_PER_MONTH=0 # custom only; all four custom limits and evidence are required
TIINGO_CUSTOM_REQUESTS_PER_HOUR=0
TIINGO_CUSTOM_REQUESTS_PER_DAY=0
TIINGO_CUSTOM_BANDWIDTH_BYTES_PER_MONTH=0
TIINGO_CUSTOM_QUOTA_EVIDENCE=
TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET=
TIINGO_REVIEWED_HOURLY_RESET=
TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE=
TIINGO_HOURLY_QUOTA_EVIDENCE=
# FMP defaults are application reservation budgets per HTTP response, not
# vendor limits. A complete map is required; empty/partial maps disable it.
FMP_OPERATION_BYTE_BOUNDS={"fetch_ohlcv":1048576,"fetch_latest_ohlcv":1048576,"get_current_price":65536,"bulk_fetch":1048576,"get_instrument_profile":262144,"fetch_market_events":8388608,"discover_universe_page":33554432}
# Optional account-reviewed native boundary; blank uses strict rolling-24-hour safety.
FMP_REVIEWED_DAILY_RESET=
# Optional override; the current official free-plan contract is rolling_30_days.
FMP_REVIEWED_BANDWIDTH_RESET=
FMP_DAILY_QUOTA_EVIDENCE= # optional documentation/account evidence override; public plan sources are the default
FMP_BANDWIDTH_QUOTA_EVIDENCE= # optional evidence override; live usage is reconciled to the durable ledger separately
TIINGO_PROVIDER_ARCHIVE_TERMS_AUTHORIZED=false # ignored when the owner risk decision is true
TIINGO_PROVIDER_ARCHIVE_TERMS_EVIDENCE=
FMP_PROVIDER_ARCHIVE_TERMS_AUTHORIZED=false # ignored when the owner risk decision is true
FMP_PROVIDER_ARCHIVE_TERMS_EVIDENCE=
```

The owner's retention and provider-term risk decision is final; these
provider-specific written-approval variables are not required for this app
when `PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK=true`. The terms are retained
above as factual context, not as an outstanding human approval or routing
blocker. Quotas, operation costs, data entitlements, and response-byte bounds
remain independent technical admission requirements.

FMP's Basic plan documents 250 calls/day, but current limit guidance says not
to promise one reset time for every account. The native reset therefore remains
`provider_defined`; the quota contract enforces a rolling 24-hour application
safety window unless an account-reviewed native boundary is provided. The FMP
dashboard is still needed to establish current call and trailing-bandwidth
usage before initializing the durable baseline.
See [Tiingo terms](https://app.tiingo.com/tos/) and
[FMP terms](https://site.financialmodelingprep.com/terms-of-service).

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

Nasdaq Trader's `nasdaqlisted.txt` and `otherlisted.txt` remain valuable
official listing evidence, but the two files must not be assumed to be a
complete roster of every US NMS primary listing market. Nasdaq Trader's own
definitions enumerate only a subset of codes in `otherlisted.txt`, while CTA
Plan publishes a distinct daily Tape A/B symbol file over anonymous HTTPS. The
CTA file is described as covering all CTA Network A and Network B symbols,
provides a primary-listing participant code and (since November 2025) a prior
symbol, and is generated from an 8:00 pm ET data cut. Its current specification
also distinguishes CTA-eligible equities, local issues, and debt instruments;
these categories and every participant-code-to-MIC mapping must be preserved
and validated before reconciliation. The CTA Plan adapter now retrieves the
latest published daily Tape A/B file, retains the complete index and CSV in the
durable discovery snapshot, and holds the source incomplete if any row is
malformed or carries an unknown participant code. It preserves the source
symbol's exact spelling because distinct CTA rows may differ only by case;
canonical ticker normalization and cross-provider identity reconciliation are
separate and still fail closed on collisions. It uses a local two-request
daily safety ceiling (index plus file); CTA publishes no numeric HTTP quota.
The file does not distinguish ETFs from common stocks. Nasdaq-listed
securities remain a separate Tape C scope. These source scopes are not yet
combined into one same-session snapshot, so neither may authorize whole-NMS
absence or support a claim of complete all-venue US listings. Nasdaq Trader
remains useful as independent cross-check and lifecycle evidence. Sources:
[CTA Symbol File](https://www.ctaplan.com/symbol-file), [CTA Symbol File
specification](https://www.ctaplan.com/publicdocs/ctaplan/CTA_Symbol_File_Specification.pdf),
and [Nasdaq Trader directory definitions](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs).

Neither Nasdaq Trader nor the CTA file is a complete OTC Markets listing or
delisting feed. OTC's current complete starting snapshot is FINRA's official
Query API `otcMarket/otcSecurityMaster` dataset; the credentialed 2026-10-07
traversal returned 18,009 rows in four pages, with all raw pages archived.
FINRA Daily List supplies lifecycle deltas. A clean exact-source run on the
committed implementation remains an acceptance check before claiming current
production readiness. Massive All Tickers `market=otc` is an alternative
technical source; FINRA ORF is a distinct, separately entitled file product.
Neither is required to reinterpret the Query API evidence, and no website
scraping is used.

For a Nasdaq Trader run to count as complete source evidence, every declared
total must equal the number of rows actually collected. A cursor that skips
rows, terminates early, changes its declared total, or omits/malforms the
terminal `File Creation Time` marker fails directory parsing. Both official
files' generation dates must agree; they are retained in reconciliation
provenance. Nasdaq's field definition does not specify a timezone, so the
encoded calendar date is used without conversion. A directory miss counts only
once for a distinct file-generation date matching a completed exchange
session, so rereading a stale or 304-cached snapshot cannot manufacture
delisting confirmations. This source-local completeness does not make it
whole-NMS absence evidence: CTA Tape A/B and Nasdaq-listed/Tape C evidence must
also be complete for that session before a combined NMS absence decision.
Rows whose venue is missing or cannot be mapped to
the supported Nasdaq Trader MIC set (`XNAS`, `XNYS`, `ARCX`, `XASE`, `BATS`,
`IEXG`, `TXSE`) likewise fail closed instead of becoming venue-less listings.
The `F` code maps to `TXSE` using TXSE's official participant/MIC identifiers
and Nasdaq's 2026 feed notice. The archived October 11, 2026 two-file response
contains 13,260 active rows, including 16 TXSE rows; raw responses remain
retained while the corrected candidate parses and its reconciliation path is
covered by a PostgreSQL integration test. Successful NMS runs persist deterministic `venue_coverage`
provenance with expected,
observed, missing, and per-MIC row counts; this makes a complete Nasdaq Trader
snapshot with no rows for a particular venue distinguishable from malformed
venue evidence, but does not prove complete all-venue NMS coverage.
The FINRA OTC Query API directory is the planned OTC snapshot source; it never
receives NMS absence authority. Its own provider quota/cost admission and exact
source acceptance remain independent checks. ORF, if used, has separate
availability, entitlement, and operation-cost controls and is not a fallback
that may be silently substituted. The user's private persistent-storage
approval is settled; it is not an outstanding owner-approval gate.

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

xStocks' public API reference says its public endpoints require no API key and
include asset metadata, pricing, multipliers, oracle, reserve, and corporate-
action data ([developer guide](https://docs.xstocks.fi/developers), [API
reference](https://docs.xstocks.fi/apis/openapi)). Issuer materials separately
describe product-distribution and user-eligibility restrictions. Per the
owner's final decision, this single-user private, read-only collector does not
gate public data calls on those product restrictions. This records the owner's
operational decision; it is not a legal interpretation or issuer endorsement.
The adapter remains quota-controlled and captures the public response headers.

Bybit xStocks is gated only on its technical API egress restriction: Bybit's
[API integration guide](https://bybit-exchange.github.io/docs/v5/guide) says IP
addresses located in the U.S. or Mainland China receive HTTP 403. The Bybit
product FAQ's user-verification and excluded-country language concerns trading
eligibility; this adapter makes anonymous read-only market-data requests, not
orders or trading-account calls. Therefore user-country evidence is no longer
required. Configure the non-secret
`BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_*` controls separately for
each runtime after verifying its actual outbound IP region; egress from a
blocked region remains non-routable despite the owner's private-use decision.

Kraken xStocks use provider symbols such as `AAPLx`, `TSLAx`, and `SPYx`, not
the literal word `xstock`; discovery recognizes this provider-documented
suffix marker in the human-readable pair name. Kraken's
[official FAQ](https://support.kraken.com/articles/xstocks-faq) says xStocks are not
accessible in the United States or to U.S. persons. The latest bounded live
`AssetPairs` response returned no matching pair, so asset lookup and price
operations remain unverified (the live case is an explicit skip, not proof).
Do not enable this adapter for a U.S.-restricted deployment; actual deployment
eligibility and public API partner access remain to be verified separately.

Dinari's [stock-data guide](https://docs.dinari.com/docs/stock-data) documents
provider-native Stock UUIDs, aggregate DAY/WEEK/MONTH/YEAR history, news, and
live price/quote endpoints. Its [pricing guide](https://docs.dinari.com/docs/pricing-quotes)
distinguishes the computed fair price from bid/ask quotes, and notes that US
SIP/NBBO data is metered. Dinari's [partner-fees guide](https://docs.dinari.com/docs/fees)
states that production API access starts at $2,000/month; Sandbox access is the
appropriate environment for evaluation and fixture/live transport validation,
not production entitlement evidence. The adapter never treats CIK/CUSIP/FIGI fields as the
token's primary identity and never fabricates volume for the aggregate history.
Dinari's [June 11, 2024 API License with SLA](https://assets.dinari.com/forms/Dinari_API_License_w_SLA_20240611.pdf)
states a maximum of 1,000,000 API calls per rolling 30-day period with no
rollover. That is an agreement-specific ceiling: the current public docs do not
establish that it applies to a free Sandbox key or disclose a separate Sandbox
rate/reset contract. Keep Sandbox limits unknown unless the accepted account
agreement confirms applicability; do not treat the canary's local request cap
as Dinari's allowance.
The canonical `Y1` timeframe is a calendar-year bucket for this tokenized
history bridge; ordinary market-data adapters must advertise an explicit
annual interval or remain unsupported rather than mapping `Y1` to daily data.
Dinari's [US-customer requirements](https://docs.dinari.com/docs/us) make partner
approval, regulatory, data-security, and redistribution review a deployment
gate, so having a key alone does not make this provider routable.

The current Sandbox key can be exercised only by the explicit isolated live
canary (`--dinari-sandbox-canary --provider dinari`). The canary does not write
Sandbox observations into canonical production data tables, but every response
body it obtains is durably archived in the owner-private redacted live-response
archive, like other live probes. Dinari's public API
license/SLA template dated 2024-06-11 states a maximum of 1,000,000 API calls
per rolling 30-day period, while current public documentation says Sandbox is
free during evaluation/building and does not publish a Sandbox-specific cap,
endpoint cost schedule, or native usage counter. The older generic license
ceiling is useful evidence, but it does not prove that this account accepted
that exact version or that the same allowance applies to its Sandbox key. The
isolated connectivity canary permits exactly one read-only stock-catalogue
request per UTC day, reserved through the shared durable ledger. That ceiling
is explicitly an application test policy, not a claim about the provider's
limit. It requires `DINARI_SANDBOX_CANARY_AUTHORIZED=true`, a non-secret
`DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE`, and
`DINARI_SANDBOX_CANARY_MAX_REQUESTS=1`. The canary does not retry, archives its
response privately, and does not write canonical market data. Recurring or
multi-operation live tests and ordinary routing remain blocked until the
non-secret `DINARI_SANDBOX_QUOTA_PROFILE` records account-applicable quota,
reset semantics, evidence source, and worst-case operation costs. Do not
silently promote the 2024 generic license ceiling to a confirmed current
Sandbox plan. Outside canary mode, the Sandbox transport may retry one logical
HTTP read up to two times
after a transient HTTP 500. Its minimum operation-cost map therefore reserves
three HTTP attempts per underlying request (for example, a two-request quote
operation reserves six); the reviewed profile may reserve more, but the
validator rejects values below these code-enforced worst-case costs.
Ordinary provider routing remains disabled until the commercial, eligibility,
and redistribution review is complete. The canary's isolation is not a
data-discard policy: response payloads are retained privately before quota
settlement can be reported as successful.

To populate that profile, obtain Dinari's account-specific answer for the
Sandbox key: requests/second, minute, day, and month limits (if any); whether
each counter is per key, account, organization, or egress IP; rolling versus
calendar reset boundaries and timezone; whether stock-list, quote, history,
news, dividend, split, and corporate-action calls have different weights; the
applicable response headers and 429/`Retry-After` behavior; and whether the
dashboard or API exposes current usage. Ask explicitly whether the
one-million-calls-per-rolling-30-days limit in the 2024 API License applies to
this Sandbox account. The public [environment reference](https://docs.dinari.com/reference/environments)
and [API reference](https://docs.dinari.com/reference/getstocks) describe the
Sandbox host and data endpoints but do not establish these quota details; the
[partner-fees page](https://docs.dinari.com/docs/fees) says Sandbox is free
while evaluating/building and production API access starts at $2,000/month.
Those price statements do not supply a Sandbox rate-limit contract. Keep the
canary blocked until the account-specific answers are entered as a reviewed,
non-secret profile.

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
pool. Since Bybit does not expose a remaining-use counter for the anonymous IP
pool, the shared durable coordinator starts an application-only zero baseline
for this exact 600-per-5-second provider pool. It counts this platform's
requests across its local worktrees without claiming visibility into unrelated
traffic from the same outbound IP. Bybit also documents that API requests from U.S. or Mainland-China IPs
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
`TOKENIZED_EVENT_REFRESH_MAX_PROVIDERS` is a per-run fairness budget, not a
permanent provider allow-list: when more providers are eligible than the
budget, durable action-feed state prioritizes providers with no/incomplete
state and then rotates completed providers by oldest successful observation.
This prevents a stable provider-chain order from starving later providers. A
token is linked only when an explicit provider asset ID or
unique token symbol matches the stored token detail; otherwise the event is
retained unlinked for later reconciliation rather than guessed onto an
underlying ticker. Exchange token adapters without an action endpoint are
reported as unsupported and never invoked.

Tokenized quote and aggregate-history batches use the same lossless fairness
principle at the asset level. A durable numeric asset cursor advances after
each bounded batch, including batches containing caught provider failures, so
one repeatedly failing token cannot occupy every run's first slot and starve
later active tokens. The failed asset remains eligible and is retried after
the active set rotates; a process failure before commit leaves the cursor at
the prior batch for safe retry.

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
clean* dry-cycle report may the exact `completed_cycle_count` be supplied to
the admin-only `POST /api/v1/market-data/sec-directory-candidates/materialize`
endpoint, with a bounded batch size of at most 500 rows. It consumes the
already-retained report and makes **zero SEC requests**; interrupted batches
resume from remaining `would_create` decisions. The service verifies that the
number is the latest completed cycle, every source row is present and clean,
and the SEC source fingerprint matches. Approval is one-cycle only; a
failed/dirty cycle, source change, or intervening cycle requires a new clean
dry scan and review. Materialization creates only missing `Issuer` rows from
the SEC-conformed company name and CIK, records source/ticker provenance, and
never creates instruments/listings, changes existing names, or deactivates
records. Conflicting names and CIK/domain-key collisions remain quarantined.
The optional `create_missing` scan mode remains available for a fresh bounded
scan, but the persisted-report endpoint is preferred so already-fetched SEC
rows are not downloaded again.

SEC directory candidate reports are append-only across scan cycles. The filing
parser also retains every matching prospectus/registration filing in each
retrieved submissions response; local batch settings are compatibility and
fairness controls, not retention limits.
Each `SecIssuerDirectoryCandidate` additionally retains the exact normalized
provider-adapter row in `source_payload`, and the admin candidate report
returns it, so fields received from SEC are not lost behind the admission
projection. The additive migration refuses downgrade while that evidence is
non-empty.

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
may change. The Equity Specific Terms separately permit conditional
redistribution to non-commercial end users; broader audience support is not
part of this internal application. The owner has explicitly accepted the
provider-terms risk for private, single-user automated use and persistent
storage, so the application does not require a separate FINRA terms/storage
attestation and must not describe terms approval as a current routing blocker.
Credentials, measured quotas, complete source pagination, and live acceptance
remain independent routing gates. The async result byte bound is an application
safety/accounting requirement, not a claim that FINRA publishes a provider-wide
maximum result size; async result downloads remain non-routable until their
bounded, durable storage path is implemented.

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
- Missing option-chain Greeks are now estimated at ingestion with the
  QuantLib American CRR model; provider-supplied values remain authoritative.
  The full estimated output and valuation inputs are preserved under
  `extra_greeks.local_greek_estimation`. CRR's unavailable vega/rho use
  finite-difference sensitivities against the same American pricing engine.
  If QuantLib is unavailable or fails, delta/gamma explicitly fall back to the
  legacy Black-Scholes estimate and record that model/version instead.

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
conservative number of 1,000-candle pages from the requested range, including
the inclusive end boundary, and reserves the complete weight before execution.
The adapter stops after a short page rather than issuing a quota-wasting empty
follow-up request. A range whose calculated weight cannot fit
the current documented window is deferred rather than charged as one call.
Repeated 429 violations can produce an HTTP 418 IP ban; response usage and reset
headers are captured when capacity failures occur.

No API key is required for the documented public endpoints. Durable market-data
routes remain fail-closed until the provider-specific archive-authority fields
in the configuration reference below are populated from an applicable written
grant; the native account-usage probe is exempt because it stores usage evidence
only, not market data.

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
| `account_usage`         | `/key` account/key limits and monthly usage; key-specific counters are required for the API-key-scoped quota contract, and active minute consumption is not exposed |

**Notes**:
- CoinGecko is the authoritative source for crypto universe discovery and metadata.
- For OHLCV, Binance is preferred; CoinGecko's OHLC endpoint has coarser granularity.
- Current Demo pricing lists 100 calls/minute and 10,000 monthly credits.
  An older 2023 public-API article says 30 calls/minute for Demo; the current
  plan page is the checked-in contract, while this source discrepancy remains
  visible for future account verification. Each successful request consumes
  one monthly credit; unsuccessful requests still count against the minute
  limit. Monthly credits reset on the first UTC calendar day, not on a rolling
  30-day period ([pricing](https://www.coingecko.com/en/api/pricing),
  [usage-credit FAQ](https://support.coingecko.com/hc/en-us/articles/13962109374489-How-does-CoinGecko-API-count-the-API-usage-credit),
  [reset FAQ](https://support.coingecko.com/hc/en-us/articles/16760509234713-When-does-my-request-volume-monthly-API-credit-reset)).
- The published quota says “per minute” but does not specify fixed versus
  rolling reset mechanics. The contract retains this as an unknown provider
  boundary and applies a stricter rolling 60-second application envelope;
  this does not relabel the provider's native window.
- The `/key` support guide documents a native usage endpoint and the Demo
  authentication guide confirms the Demo root URL and `x-cg-demo-api-key`
  header. The detailed API reference example uses the Pro host and also
  exposes key-specific counters alongside account-wide counters. A prior
  Demo-key probe against the Pro host returned HTTP 401 `10005`; that does not
  prove whether the Demo host supports `/key`. The adapter now requires the
  key-specific fields and deliberately ignores account-wide call totals for
  its API-key-scoped baseline. Live acceptance is pending: the exact one-call
  Demo probe is not admitted while shared per-minute active use is unknown.
  Do not infer zero monthly usage. Sources: [usage endpoint support guide](https://support.coingecko.com/hc/en-us/articles/6472655452953-How-to-Check-Your-API-Call-Usage-via-Endpoint), [Demo authentication guide](https://coingecko-api-v3.readme.io/v3.0.1/reference/authentication), [API usage response schema](https://docs.coingecko.com/reference/api-usage).
- Provider terms remain documented for transparency, but the owner has
  expressly directed that provider terms and retention restrictions are not
  gating criteria for this private single-user research platform. Technical
  authentication, quotas, endpoint availability, data completeness, and the
  no-loss persistence requirements remain enforced independently.
- The `/key` adapter reports a native monthly balance/reset and the plan's
  minute ceiling; it does not report current minute consumption. The exact
  monthly baseline is therefore reconcilable, while the usage probe itself
  remains gated until its one-request minute cost can be safely admitted.
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

**Rate limit**: SEC guidance caps aggregate traffic at 10 requests/second,
regardless of how many machines a user employs. If traffic exceeds the limit,
the source says the IP may be restricted; access may resume after traffic has
remained below the threshold for 10 minutes. The provider does not expose a
current usage counter or a fixed bucket boundary for this public endpoint. The
application therefore enforces a rolling one-second request envelope, honors
`Retry-After` when returned, and places an EDGAR scope on a 10-minute hold
after a recognized SEC rate-limit response without a reset header. A separate
durable active-IP baseline is still required before a live operation can be
admitted; no empty-ledger usage is assumed. A descriptive User-Agent and SEC
fair-access compliance remain required. Sources: [SEC Developer Resources](https://www.sec.gov/about/developer-resources)
and [SEC Internet Security Policy](https://www.sec.gov/files/privacy.htm).

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

Twelve Data documents two distinct Basic-plan pools: 8 weighted credits per
fixed minute and 800 API requests per UTC calendar day. Its official [pricing
page](https://twelvedata.com/pricing) identifies the daily limit, while its
[credits documentation](https://support.twelvedata.com/en/articles/5615854-credits)
states that the daily Basic quota resets at 00:00 UTC. Endpoint weights are
provider-specific and must remain in the checked-in usage profile; the runtime
does not substitute one request for an unknown endpoint weight. The optional
native `fetch_account_usage` operation calls the documented `/api_usage`
endpoint (itself charged one credit), records the returned plan, and persists
the exact `api-credits-used`/`api-credits-left` pool as a named
`credits_per_minute` observation with the next fixed-minute reset. Official
[usage-control documentation](https://support.twelvedata.com/en/articles/5713553-control-over-api-usage)
says `/api_usage` returns the current plan and remaining credits, and that the
probe costs one API credit. Its body exposes `current_usage`/`plan_limit` and,
for daily-limited plans, `daily_usage`/`plan_daily_limit` as request counts.
The adapter stores the minute credit headers and the body request counters in
separate dimensions. The account-usage probe reserves one minute credit and
one daily request, then reconciles the post-call counters. Native observations
never widen routing beyond the exact reviewed limit, unit, and reset.

The current [Twelve Data Terms](https://twelvedata.com/terms) allow access,
processing, and storage only for tier-authorized internal use, prohibit Free
Tier commercial use, restrict non-display use to the subscription tier, limit
storage/cache duration to the documentation, and require deletion of Data
within 30 days after termination or expiration. The [Basic Free plan](https://twelvedata.com/pricing)
lists internal non-display use, not internal display. This application persists
provider responses and may later display them to its single authorized user;
neither an API key nor the Basic quota proves those rights or perpetual
retention. Therefore provider-runtime ingestion requires the provider-specific
`TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_*` exception controls and evidence explicitly
covering internal display and non-display automation plus retention after
subscription/account end. The account-usage endpoint and ephemeral live probes
remain separately metered and do not persist the returned market-data payload;
their success is not evidence that canonical archive routing is authorized.

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
configured by changing the plan/limit pair. The shared
`PROVIDER_FREE_ONLY_CHECKPOINT` gate defaults true and denies every paid plan
and every trial plan for all callers, even when
`ALLOW_PAID_PROVIDER_ROUTING=true`. This checkpoint gate is independent of the
full-roadmap paid-routing opt-in. Setting it false deliberately leaves
checkpoint mode; only then can `ALLOW_PAID_PROVIDER_ROUTING=true` admit a
reviewed paid plan. Unknown/unreviewed plans and trials remain denied in both
modes. Neither setting implements aggregate cost admission or authorizes paid
activation. The approved 20 EUR/USD-equivalent shared cost contract remains
Provider-owned ICP2 work before paid activation can be proposed. Plan/limit
configuration remains provider-specific and may be set separately for local
development, protected CI, and production.

The checkpoint also has an operation-level exclusion map,
`PROVIDER_CHECKPOINT_OPERATION_HOLDS`. It is a JSON object keyed first by
provider and then by canonical upstream operation name; `*` holds every
operation for that provider. Service workload labels are canonicalized only
for this safety decision: `bulk_fetch:*` and `fetch_rfr_ohlcv` are checked as
`fetch_ohlcv`, while `reconcile_universe_page:*` is checked as
`discover_universe_page`. Their original operation names remain unchanged for
quota costing, request logs, and live-evidence provenance. The in-code default
keeps CTA Plan, EODHD data operations,
Marketstack, Tiingo, Dinari Sandbox, and Bybit xStocks unavailable for the
current checkpoint reasons while deliberately leaving only EODHD's reviewed
zero-daily-credit `fetch_account_usage` bootstrap available. These holds run in
the shared resolver before adapter construction, quota reservation, or
transport and are shown in provider-status diagnostics. They are not quota
estimates and cannot be bypassed by `ALLOW_PAID_PROVIDER_ROUTING`. Replace the
complete map per environment only after each removed operation has reviewed
entitlement, cost/quota headroom, and exact-source live evidence. Setting
`PROVIDER_FREE_ONLY_CHECKPOINT=false` leaves checkpoint mode and disables this
temporary exclusion layer; the normal entitlement, quota, cost, and routing
controls continue to apply. Capability discovery with no operation is
diagnostic and does not claim that every operation is transport-eligible;
every real executor call supplies and checks its concrete operation.
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
calendar day) inside the service and reserves it before execution. Invalid or
reversed date ranges are not sent; no fixed-cost fallback or arbitrary maximum
history span is imposed. The bounded live probe uses one contract and an
explicit three-calendar-date window, reserving one credit before transport.
This probe validates a bounded request and does not itself test the provider's
entire historical retention depth.
For historical option quotes, the provider documents HTTP 404 with `s=no_data`
as a valid empty-result response (for example, a valid contract with no quotes
in the requested interval). The adapter maps only that exact response to an
empty series; other 404 responses remain typed provider failures.

The adapter also exposes the documented authenticated `GET /user/` account
introspection endpoint through `fetch_account_usage()`. It preserves the
provider-reported credit limit, remaining credits, request charge, reset time,
and options-data entitlement without deriving a plan or changing routing. The
endpoint is unversioned (`https://api.marketdata.app/user/`) even though data
resources use `/v1`; the provider documents a 404 response as “no account
information”, which is represented as no snapshot. See the official
[Python client account/rate-limit documentation](https://www.marketdata.app/docs/sdk/py/client/)
and [Go user endpoint documentation](https://www.marketdata.app/docs/sdk/go/utilities/user/).

The current [Terms of Service](https://www.marketdata.app/terms/) license
self-service data for personal, non-professional use and require deleting all
downloaded data if the subscription ends. The terms' professional-use
definition also lists research, testing, and monitoring when use extends beyond
personal, individual activity, so the plan/credit setting alone cannot
classify this application. The public terms do not grant perpetual retention
after subscription termination. Durable provider ingestion therefore requires
the provider-specific `MARKETDATA_APP_PROVIDER_RETENTION_TERMS_*` exception,
with evidence covering the exact single-user use, automated monitoring,
display/non-display processing, and perpetual archive retention. Existing
plan/expiry settings still control the 10,000-credit/day trial and its
100-credit/day Free Forever fallback; they do not grant data rights. Direct
live probes also append every observed response body to the owner-only live
response archive. The live runner therefore applies the same retention-rights
gate to these data-bearing probes; an API key, free trial, or requested plan
does not itself authorize retaining the returned data. This prevents a test
from bypassing the source-rights gate while creating a persistent archive.

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
requires an operator-provisioned OAuth credential, current-window quota
baselines, and reviewed data-use terms before routing. The synchronous
short-interest adapter requests 1,000 rows per page, validates FINRA's
`Record-Total` and available page headers, and returns a symbol/window-bound
continuation cursor. Its compatibility list method refuses to return a partial
first page as complete. The admin ingestion path
`POST /api/v1/market-data/short-interest/{instrument_id}/refresh` persists each
raw provider row and its normalized observation in the same transaction as the
next cursor. Its `max_pages` limit is a per-call fairness bound; callers resume
the persisted cursor on a later call and the service never marks an unfinished
query complete. A terminal offset-range condition persists the page rows and
leaves an explicit failed state and durable unresolved cursor instead of
claiming completeness or dropping the continuation. The admin refresh endpoint
accepts `retry_blocked=true` after its retrieval path is corrected; ordinary
scheduled calls do not repeatedly spend quota on an unchanged impossible range.

The shared cursor-paginated market-event ingestion path (including the FINRA
Daily List) also commits each validated page's exact source payload, request
accounting, and continuation cursor before it asks for another page. The
unbounded-history scan starts from FINRA's authoritative available-date index,
not an assumed earliest date; the remaining Daily List history is held as
durable one-day cursor segments. If a single partition exceeds the 500,000
offset ceiling, ingestion commits the returned rows and preserves the
unresolved cursor. It remains visibly incomplete until a usable retrieval
path is available and can be explicitly retried with `retry_blocked=true`.

An admin can request a specific historical or forward event window with
`POST /api/v1/market-data/events/refresh?provider=finra&start=YYYY-MM-DD&end=YYYY-MM-DD&max_pages=1`.
The endpoint requires one explicit provider and a closed date window, defaults
to one page per invocation, and returns pagination status plus whether a
continuation remains. Repeating the call resumes the persisted cursor; a
completed window is not queried again unless `force_refresh=true` is explicit.
The scheduled event task remains a separate forward-looking refresh path.

This is targeted per-instrument ingestion, not yet an automatic whole-US-
universe short-interest sweep. The provider supports symbol-filtered queries;
an all-instrument sweep still needs a separately measured workload budget and
provider quota headroom, because FINRA's 10 GB monthly allowance is shared and
each synchronous response can be as large as 3 MB. No ticker is silently
excluded by a page budget, but this branch does not claim whole-universe
short-interest coverage.

FINRA's [Equity Data terms](https://developer.finra.org/specific-terms-equity-data)
and [general API terms](https://developer.finra.org/finra-api-terms-service)
govern licensed access independently from credentials and quotas. For the
current private, non-commercial, non-redistributed use, the Equity Specific
Terms expressly allow internal personal/professional use and creation of
derivative data; their Data Retention section says “Not applicable.” The
general terms restrict use to authorized users and licensed purposes. The
runtime therefore does not require a second owner-storage attestation for
short-interest or Daily List data; the owner's blanket private-storage approval
is already recorded. The separate `FINRA_EQUITY_DATA_USE_*` compatibility
settings are not a routing switch. If the app's audience changes, distribution
to third-party end users is permitted only for non-commercial personal or
professional use and subject to FINRA attribution, no incremental fee for
FINRA data, no further redistribution by end users, and commercially
reasonable compliance controls. That broader audience mode is not part of the
current internal-use configuration.

The public credential has a separate 10 GB data-download allocation per month;
FINRA says an exhausted public credential stays inactive until the first day of
the following month. The API Console can show credential usage. FINRA's
public docs do not specify the byte convention or reset timezone, so admission
records the native monthly period and uses a conservative provider-scoped
rolling 31-day safety envelope, with measured response bytes settling durable
reservations. Before live Query API tests, reconcile the current API Console
meter into the shared quota baseline; a local ledger cannot reveal outside
usage on the same credential.

**Configuration**: Set `FINRA_CLIENT_ID` and `FINRA_CLIENT_SECRET` in the
ignored `.env.dev`. `FINRA_SHORT_INTEREST_URL` and
`FINRA_OTC_DAILY_LIST_URL` are optional endpoint overrides; otherwise the
adapter uses the documented API base and OAuth bearer flow. Do not put client
secrets in commits or chat. Synchronous short-interest and Daily List operations
have a conservative documented quota contract and can be routed after credential
and live-evidence gates; the separate OTC security-master directory remains
non-routable until its live quota and source-completeness controls are ready.

Each authenticated dataset call can include a cold OAuth token request before
the dataset POST. Runtime accounting therefore reserves two requests for
short-interest and Daily List operations; a warm token cache may consume only
the dataset request, but the reservation never undercounts a cold process.

### FINRA OTC directory (`finra_otc_directory`)

The selected complete starting roster is FINRA's documented Query API
`otcMarket/otcSecurityMaster`, the same dataset called by FINRA's public OTC
Symbol Directory. Pagination uses the provider's `record-total` and stable-key
sorted offsets. The adapter retains each full response page before row
normalization, checks totals and snapshot date across pages, and fails closed
on duplicates or incomplete traversal. The 2026-10-10 live traversal returned
18,017 rows over four pages, and the four sorted pages observed by the public
directory matched the archived API symbol set exactly. Since both paths use
the same Query API, that comparison verifies pagination, not an independent
source. FINRA Daily List supplies lifecycle deltas between full snapshots.
The combined daily NMS/OTC reconciliation worker is implemented and enabled by
default in application and Compose configuration; set
`MARKET_UNIVERSE_RECONCILIATION_ENABLED=false` to disable it explicitly. This
feature branch does not activate or change the live deployment. Provider quota
admission, complete-snapshot validation, and three-distinct-snapshot-day
absence safeguards remain active.

The adapter also retains separate parsers for legacy DAPI/pipe-delimited
fixtures, OTC Markets pipe-delimited files, and the optional FINRA ORF file
pair. ORF's `EQUITYMASTERAC` and `EQUITYMASTERIN` are a distinct TRAQS product,
not the current Query API source; ORF requires its own account credentials,
quota profile, and persistent refresh-token state. It is not required for the
selected Query API directory path.

The official [OTC Markets Security Data product](https://www.otcmarkets.com/market-data/reference-and-pricing-data/security-data)
is the researched fallback if FINRA cannot provide a permitted, complete
source. OTC Markets lists this security file at approximately $1,500/month for
internal use or $2,000/month when external display is included, far above the
approved $20/month provider-spend ceiling. Its current
[agreements and forms](https://www.otcmarkets.com/market-data/agreements-and-forms)
also establish that data-file access is licensed, not an unrestricted public
API. A public stock-screener page is not evidence of permission for automated
ingestion or persistent use; do not scrape it as a substitute. Reconsider the
paid file only through a separate, evidence-based cost proposal. It is not a
current implementation dependency.

ORF is not a free/public endpoint: FINRA's [ORF file specification, version 15.1](https://www.finra.org/sites/default/files/2024-08/Equity_API_File_Downloads_ORF.pdf)
requires a TRAQS/OKTA user with MFA and product authorization. The file API
uses a separate TRAQS refresh-token flow (`POST /refresh`, then bearer-
authenticated `POST DownloadHandler.ashx` requests carrying the assigned
TRAQS username), not the FINRA Gateway client-credentials flow used by
short-interest/query datasets. The published file specification documents the
token lifetime and file availability hours, but does not publish a numeric
request quota or reset window. Therefore ORF remains non-routable until FINRA
confirms the applicable request/download limits (including account scope and
reset) or those are otherwise established from authoritative response
headers; the integration does not guess them. Configure `FINRA_ORF_USERNAME`,
`FINRA_ORF_REFRESH_TOKEN`, and the optional `FINRA_ORF_TOKEN_URL`; the supplied
FINRA Gateway OAuth pair is not a substitute and is not treated as proof that
this specific product entitlement exists. The current [TRAQS ORF User Guide
v3.3 (March 2026)](https://www.finra.org/sites/default/files/2026-03/TRAQS_ORF_User_Guide_v3.3.pdf)
confirms programmatic refresh-token use and authorization at the specific ORF
facility/file level. The [ORF file specification v15.1](https://www.finra.org/sites/default/files/2024-08/Equity_API_File_Downloads_ORF.pdf)
states refresh tokens expire after six months and access tokens after 3,600
seconds; its programmatic example also reads the returned `refresh_token` and
uses it for the next exchange. The adapter therefore stores the latest token
atomically in an owner-only (`0600`) `FINRA_ORF_REFRESH_TOKEN_STATE_FILE`, with
a cross-process lock shared by API and worker processes; a missing path blocks
before any token request. Local Compose mounts the host directory configured
by `FINRA_ORF_REFRESH_TOKEN_STATE_HOST_DIR` (default under the user's
`~/.config/charting-platform/provider-secrets/finra-orf`), and RPi Compose uses
the corresponding persistent deployment directory. GitHub-hosted runners are
ephemeral and cannot satisfy this cross-run state contract; ORF live CI remains
blocked unless a persistent private self-hosted path or equivalent secret
store is configured. Expired refresh tokens must still be manually reissued in
TRAQS. The standard
[ORF Files Web Access Agreement](https://www.finra.org/sites/default/files/AppSupportDoc/p539848.pdf)
limits ORF participant/API file use to internal ORF processing and restricts
using the files to populate reference-data databases/products for resale or
distribution. The separate [ORF Reference Data
Agreement](https://www.finra.org/sites/default/files/2024-10/ORF_Reference_Data_Agreement.pdf)
is a vendor agreement with a different, tightly controlled non-commercial
service/redistribution license and audit obligations; it must not be assumed to
apply automatically to an individual private analytics app. ORF is an optional
alternative and is not required for the current OTC route. Its adapter remains
non-routable unless FINRA confirms which agreement/access path applies and its
separate account, quota, and source controls are configured. This does not
block the FINRA Query API `otcSecurityMaster` plus Daily List path. FINRA's file
specification says CUSIP is blank for
accounts without a CGS license, so the rest of the directory can be used
without that optional identifier. Configure
`FINRA_ORF_CUSIP_LICENSED` and evidence only when the license exists. A
non-empty CUSIP without license evidence fails the complete source response
rather than silently dropping the field. Set
`FINRA_OTC_SOURCE_KIND=finra_orf_security_master`, configure both
`FINRA_OTC_SYMBOL_DIRECTORY_URL` and
`FINRA_OTC_INACTIVE_SECURITY_MASTER_URL`, and keep only the ORF route disabled
until its separate product access, agreement, MFA, terms, completeness,
polling, and any CUSIP-license requirements are actually in place. The old
FINRA route and OTC Markets delivery are not live sources; no source is silently
promoted to complete OTC coverage.

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

#### Optional alternative: FINRA ORF

The selected OTC source is FINRA's Query API `otcMarket/otcSecurityMaster`
security-master dataset plus Daily List lifecycle updates. Its full starting
snapshot was live-validated at 18,009 unique rows across four pages. ORF/TRAQS
is a distinct optional source and is not needed to proceed; no owner action is
currently requested for ORF. The details below apply only if ORF is chosen
later as an additional source.

The ORF adapter and mocked end-to-end flow are implemented; live access is not
configured. The FINRA Gateway API key does not unlock ORF. Before entering any
ORF-specific credentials, contact FINRA Operations at `FINRAOperations@finra.org` (or
866-776-0800, option 2) and ask whether an individual/non-member can receive
production TRAQS access to both ORF security-master files and whether the
planned single-user private app, automated downloads, and durable private
archive are permitted under the applicable agreement. Also ask for any fee,
request/download quota and reset/scope, and the agreement governing the
reference-data use. The published ORF file specification does not give a
numeric request quota, so this remains a hard stop until FINRA answers; the
separate FINRA Query API quota must not be reused as an ORF limit.

Do not treat the public ORF Reference Data Agreement as a routine API signup.
It is written as an agreement with a "Vendor" and allows internal ORF
processing plus specified services to non-commercial external users; FINRA
must confirm in writing that the owner’s individual, single-user application
fits the intended account and license category. The agreement also requires
verifiable access/use records for at least five years and permits FINRA review
of those records and premises/personnel, and includes broad vendor
indemnification. Ask FINRA to explain which of those duties apply to this
individual use before accepting the agreement. The published agreement does
not plainly answer whether already-downloaded security-master data may remain
in the private archive after access or the agreement ends; obtain an explicit
answer before enabling permanent retention. These are review points for the
owner, not permissions inferred by this implementation.

If FINRA confirms access and permitted use, the remaining credential steps
are: obtain an assigned TRAQS username (not your email address), log in with
Okta MFA, then choose `API` → `Programmatic` → `Get Token` and copy the refresh
token. Store those values only in the private local/deployment secret store as
`FINRA_ORF_USERNAME` and `FINRA_ORF_REFRESH_TOKEN`; never commit or paste the
refresh token into repository files. The app rotates it into the configured
private durable state file. The documented refresh token lasts six months and
the access token one hour. CUSIP access is optional; leave it disabled unless
you separately hold the CGS license.

FINRA Operations email template (FINRA publishes `FINRAOperations@finra.org` for
production TRAQS/MFA account-access questions and `FINRA-TSCSM@finra.org` for
API-download questions):

To: FINRAOperations@finra.org

CC: FINRA-TSCSM@finra.org

> I am an individual developer, not a FINRA member firm. Can I obtain
> production TRAQS/API access to download the ORF active and inactive Equity
> Security Master files for a private, single-user analytics application? The
> application would download them automatically and retain a private archive.
> Please confirm whether this use is permitted, which agreement and account
> type apply, any fees, the request/download limits and reset window (including
> account/IP scope), whether the active/inactive files cover all US OTC-listed
> securities and venues (including securities not reported to ORF), and whether
> the archive may be retained if access or the agreement ends. The published
> Reference Data Agreement appears to be for a Vendor and includes five-year
> access/use recordkeeping and audit obligations and broad indemnification;
> please confirm whether it applies to an individual using a private,
> single-user application and what obligations that would impose. Please
> confirm whether CUSIP is omitted without a CGS license and the steps to
> obtain an assigned TRAQS username and programmatic refresh token.

FINRA documents up to 5,000 records and 3 MB per synchronous response, versus
up to 100,000 records and no 3 MB payload cap per asynchronous request. The
offset parameter is capped at 500,000 (so a 5,000-record synchronous query can
reach at most 505,000 rows without additional filters). The published
`Record-Total`, `Record-Offset`, `Record-Limit`, `Total-Records-On-Page`,
`Record-Max-Limit`, and `Response-Payload-Max-Size` headers are paging evidence,
not optional hints to treat a short page as end-of-data. The FINRA Daily List
adapter requires and validates `Record-Total`, follows each page through the
durable market-event cursor service, and splits explicitly bounded date ranges
if the offset ceiling would otherwise prevent complete enumeration. A total
that is absent, malformed, or inconsistent with the response headers fails the
page; it is never treated as a complete result. Every well-formed returned row
is retained, including rows whose dates unexpectedly fall outside the
requested filter. If the reported total changes during pagination, the current
page is emitted for persistence before the segment restarts at offset zero;
stable FINRA Daily List IDs make the replay idempotent rather than discarding
already-observed rows.

For unbounded or one-sided history, the adapter first reads FINRA's documented
`/partitions/group/otcMarket/name/OTCDAILYLIST` index, then stores every
available `calendarDay` as a durable date-sized cursor segment and queries each
day separately. This avoids guessing an earliest date and works through the
500,000 offset ceiling without an artificial page or date cap. The full
partition-index response is retained by provider request telemetry. If a
single calendar-day partition itself exceeds the synchronous offset range,
the fetched rows and unresolved cursor are retained and ingestion stays
blocked; that exceptional case still needs FINRA's asynchronous or another
documented retrieval path. A blocked cursor can be explicitly retried with
`retry_blocked=true` on the admin event-refresh endpoint after the retrieval
path changes.

FINRA's asynchronous Query API result payload bytes are documented as
unbounded by the per-response body-size ceiling in the
[FINRA platform usage limits](https://developer.finra.org/node/1146), but each
async request is still limited to 100,000 records and the API account is
throttled to 20 async requests per minute per dataset. Public credentials have
a separate 10 GB monthly download allowance; FINRA says an exhausted Public
credential is disabled until the first day of the following month
([FINRA FAQ](https://developer.finra.org/support)). FINRA does not publish the
reset timezone or byte convention, so the account-byte contract remains
provider-defined and is guarded by a conservative rolling 31-day envelope.

The adapter requires a positive `FINRA_ASYNC_MAX_RESULT_BYTES` (or an explicit
per-call bound), validates `Content-Length` when supplied, and enforces the
bound while streaming. Successful bodies are still buffered in memory up to
that bound, so this convenience method is not a durable large-result ingestion
path. A positive configured bound becomes the operation-specific reservation
against the monthly public-credential allowance (conservatively modeled as
10,000,000,000 bytes), then successful downloads settle to measured bytes.
Partial bytes yielded before a stream error are measured and settled too; they
must not be mistaken for a complete dataset. The default `0` remains
fail-closed because the generic async adapter does not yet provide durable
streaming persistence, quota-aware query partitioning, and recovery. Async
retrieval above FINRA's 100,000-record request limit must be partitioned with
dataset filters; no truncated result is marked complete.

The three generic async adapter methods are transport primitives, not separate
admitted market-data capabilities. The live matrix records them as
`transport_not_applicable` until a concrete FINRA dataset service owns the
complete submit/poll/download lifecycle, durable streaming destination,
request-specific byte reservation, and filtered-tranche recovery. This does
not hide a current data gap: short-interest and OTC Daily List are separately
required live operations and use synchronous provider partitions/date windows
with page-level persistence. If a smallest available partition ever exceeds
the synchronous offset range, the fetched pages and continuation remain
blocked/retryable rather than being declared complete or discarded.

The status endpoint must be polled with a Bearer token no more than once per
minute (FINRA's recommendation). Its result link is presigned, must be fetched
without an Authorization header, and expires two hours after the completed
status response or 24 hours after result creation, whichever comes first.
The runtime keeps that signed link transiently for the download, but recursively
redacts credential fields and signed-query values from captured provider
response payloads before they reach durable request telemetry; the link is also
excluded from the async job's diagnostic representation. Ordinary status and
market-data fields remain available.
These operation-specific constraints are documented in the [FINRA Query API
contract](https://developer.finra.org/docs). The synchronous
`fetch_short_interest` operation reserves one published 3 MB response ceiling.
OTC Daily List `fetch_market_events` reserves two such ceilings because it
reads the authoritative partition index and then one data page. Both settle
the reservation to their total measured response bytes.

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
FRED_APPLICATION_USER_SCOPE=
FRED_APPLICATION_USER_SCOPE_EVIDENCE=
FRED_AUTOMATED_USE_AUTHORIZED=false
FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE=
FRED_SERIES_RIGHTS_EVIDENCE={}

# Alpha Vantage API key. The owner's global private-use terms-risk decision is
# final; provider-specific approval variables are not required for this app.
ALPHA_VANTAGE_API_KEY=

# Coinbase Exchange API key. Owner terms-risk decision is recorded globally.
COINBASE_API_KEY=
COINBASE_MARKET_DATA_USE_AUTHORIZED=false
COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE=
# Must equal internal_ai_automated_persistent_nonredistributed if authorized.
COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE=
COINBASE_MARKET_DATA_USE_REVIEWED_AT=
COINBASE_MARKET_DATA_USE_EXPIRES_AT=

# Binance public crypto API. Retention permission is approved by the owner;
# API limits and the provider's current terms remain separate.

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

# Nasdaq Trader's public directory files.
NASDAQ_USER_AGENT=charting-platform market-data-universe

# OpenFIGI (optional; empty uses the documented anonymous 25/minute, 5-job contract)
OPENFIGI_API_KEY=your_openfigi_key

# FINRA OAuth (required for current API)
FINRA_CLIENT_ID=
FINRA_CLIENT_SECRET=
FINRA_TOKEN_URL=https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token
# ORF is an optional alternative and uses a separate TRAQS refresh-token flow.
FINRA_ORF_USERNAME=
FINRA_ORF_REFRESH_TOKEN=
FINRA_ORF_TOKEN_URL=https://apidownload.finratraqs.org/refresh
FINRA_API_BASE_URL=https://api.finra.org
FINRA_SHORT_INTEREST_URL=
FINRA_OTC_DAILY_LIST_URL=
FINRA_OTC_SOURCE_KIND=finra_otc_query_api
FINRA_OTC_SYMBOL_DIRECTORY_URL=https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster
FINRA_OTC_INACTIVE_SECURITY_MASTER_URL=
FINRA_OTC_OPERATION_COSTS={}
FINRA_OTC_SOURCE_REVIEWED=false
FINRA_OTC_SOURCE_EVIDENCE=
FINRA_OTC_REVIEWED_SOURCE_URL=
FINRA_OTC_TERMS_REVIEWED=false
FINRA_OTC_COMPLETENESS_REVIEWED=false
FINRA_OTC_REDISTRIBUTION_REVIEWED=false
FINRA_OTC_POLL_INTERVAL_SECONDS=86400
FINRA_ORF_CUSIP_LICENSED=false
FINRA_ORF_CUSIP_LICENSE_EVIDENCE=
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
BYBIT_XSTOCKS_MARKET_DATA_USE_USER_JURISDICTION_AUTHORIZED=false
BYBIT_XSTOCKS_MARKET_DATA_USE_USER_JURISDICTION_EVIDENCE=
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
MARKET_UNIVERSE_RECONCILIATION_ENABLED=true
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
its entitlement separately. `PROVIDER_FREE_ONLY_CHECKPOINT` defaults true and
is the shared hard free-only routing boundary for the integration checkpoint;
it denies paid and trial entitlements for all callers. Outside that mode,
`ALLOW_PAID_PROVIDER_ROUTING` remains the full-roadmap opt-in for reviewed paid
plans, not aggregate recurring-subscription cost admission or paid-activation
authorization. Unknown and trial plans are always denied. The approved
20 EUR/USD-equivalent monthly ceiling is not implemented; Provider owns that
shared ICP2 work and ETF owns ICP6 consumer validation. This lets each
production, CI, RPi, or local
environment reflect its own account tier without credentials or account-
specific quota values entering Git.
Runtime/admin policy changes are stored in the application database and must
remain source-backed and auditable.

---

## Provider Chain Defaults

The default provider chain can be overridden per capability via `PROVIDER_CHAIN_SEEDS`
(JSON dict in `.env.dev`). The free-source-first new-workstation baseline is:

```env
PROVIDER_CHAIN_SEEDS={"instrument_search":["edgar","massive","alpha_vantage"],"instrument_metadata":["edgar","massive","alpaca"],"price_history":["alpaca","alpha_vantage"],"latest_price":["alpaca","alpha_vantage"],"instrument_events":["alpaca","massive","edgar","finnhub","alpha_vantage"],"universe_discovery":["alpaca","edgar","massive","nasdaq","cta_plan","finra_otc_directory","alpha_vantage"],"tokenized_historical_prices":["dinari","ondo_global_markets"],"tokenized_corporate_actions":["robinhood_tokens","xstocks","dinari"]}
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
