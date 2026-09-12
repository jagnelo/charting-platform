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
> live-probe evidence. The current local validation snapshot (2026-09-12)
> has passing EDGAR, Alpaca, MarketData.app, and Dinari Sandbox probes. The
> Dinari probe initially used the live host and returned HTTP 401; after the
> operator-only endpoint was corrected to the documented Sandbox host, the
> replacement Sandbox pair passed. Tradier, Ondo, and IBKR are intentionally
> deferred. None of these observations alone overrides the separate quota,
> terms, entitlement, and reconciliation gates.

Operation-cost maps are provider-specific and reviewed against the adapter's
actual transport shape. Alpha Vantage's search, daily history, latest-price,
listing, IPO-calendar, and annual/quarterly earnings operations each reserve
one provider query; a future pagination or compound lookup must change that
map before the operation can be treated as quota-safe. No operation silently
inherits a universal request cost when a provider contract declares
operation-level accounting.

History adjustment is an explicit routing requirement. The market-data service
passes the requested `adjusted` value into provider resolution before quota
reservation and transport. Alpha Vantage's free daily endpoint and IBKR's
historical endpoint are raw-only in the supported contracts, so adjusted
requests are filtered before a raw-only provider can be selected; raw requests
remain eligible. The current raw-only admission list includes Alpha Vantage,
IBKR, Tiingo, Twelve Data, Finnhub, Marketstack, EODHD, FMP, Tradier,
MarketData.app, and the Binance/Coinbase/Kraken exchange feeds. The platform
does not silently synthesize split/dividend adjustments from a raw response.
The registry publishes `adjusted_price_history` separately from
`price_history`; at this revision it is advertised only for Alpaca and the
explicit legacy yfinance compatibility path, so consumers do not infer
adjustment semantics from the presence of an OHLCV method.

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

Durable quota windows are keyed by provider, documented dimension, and an
explicit `quota_group` when the vendor's allowance is shared across
capabilities. For example, MarketData.app's daily credits and concurrent
request ceiling use the reviewed `account` group, so history, quotes, and
options cannot each spend an independent copy of the same account budget.
When a contract omits the field, the compatibility key is the requested
capability; the runtime never infers account sharing from a generic scope label.
Existing windows are backfilled by migration `7d8e9f0a1b2c`, and admin/usage
diagnostics expose both the request capability and bucket group.

## Provider capability and quota ledger

The table below is the checked-in contract used by `ProviderPolicy` and the
durable `ProviderQuotaWindow` counters. “Unknown” is deliberate; it is not a
placeholder estimate. Limits are for the named plan/scope only and must be
re-reviewed when credentials or billing plans change.

| Provider | Implemented data surface | Credential/config key | Documented usage contract | Reset/scope | Routing status |
|---|---|---|---|---|---|
| Alpaca | US stocks/ETFs + crypto OHLCV, latest, corporate actions, assets | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_TRADING_BASE_URL` | 200 historical API calls/min; corporate-actions pages accept 1–1,000 records (1,000 requested) | provider/account window; free IEX feed restriction applies; paper/live assets host is explicit; corporate-actions page count remains an explicit local safety bound | history/latest and paper-account assets/corporate-actions live-proven 2026-09-12; event routing requires `ALPACA_CORPORATE_ACTIONS_MAX_PAGES` |
| Massive | US ticker search and reference universe | `MASSIVE_API_KEY` (or legacy `MARKETDATA_API_KEY`) | 5 requests/min, Basic Stocks | API key / minute | credentialed reference search live-proven |
| Alpha Vantage | Raw daily OHLCV, symbol search, listings, IPO calendar events, historical annual/quarterly earnings with EPS estimates and surprise metrics | `ALPHA_VANTAGE_API_KEY` | 25 requests/day (free key); `compact` daily output is latest 100 points, `full` and adjusted daily history are premium; `EARNINGS` is one query per symbol | API key / provider-defined day | compact raw daily history and the bounded AAPL earnings normalization are live-proven; adjusted history is rejected explicitly; IPO-calendar remains subject to its documented capacity response |
| SEC EDGAR | issuer/ticker/exchange directory, profiles, filings/earnings, XBRL facts | `EDGAR_USER_AGENT` | 10 requests/sec total across an IP | IP / rolling fair-access window | contract recorded; profile and complete directory pagination live-proven 2026-09-12 with the supplied contact value |
| OpenFIGI | FIGI/ISIN/CUSIP/SEDOL mapping and profile enrichment | optional `OPENFIGI_API_KEY` | 25 requests/min without key (keyed plan has separate 6-sec/100-job contract) | IP or key / rolling | keyless contract recorded; live probe required |
| Binance | public crypto OHLCV, ticker, USDT universe | none | Current Spot REST documentation exposes a 6,000 request-weight/min IP ceiling. Adapter operations use documented weights: single-symbol price 2 and exchange-info discovery 20. Historical OHLCV costs weight 2 per 1,000-candle page; the requested range is conservatively paged and reserved before execution; response `X-MBX-USED-WEIGHT-*` and `Retry-After` headers are retained on capacity failures | IP / fixed minute; 429/418 protection | exact-weight price/discovery and bounded historical operations admitted only when the calculated weight fits |
| Coinbase Exchange | public crypto candles, ticker, USD products | none | 10 public requests/sec, burst up to 15; candle responses cap at 300 bars | IP / rolling | history is explicitly paged and reserves `ceil(requested candles / 300)` calls; keyless live evidence required |
| Kraken | public crypto OHLC, ticker, USD pairs | none | safe public frequency <=1 request/sec; pair/IP limits apply; OHLC responses cap at 720 bars | IP/pair / rolling | history follows the provider `last` cursor and reserves `ceil(requested candles / 720)` calls; keyless live evidence required |
| CoinGecko Demo | crypto search, metadata, market-cap universe | `COINGECKO_API_KEY` | 100 calls/min and 10,000 calls/month | Demo key / minute + calendar month | credentialed search live-proven |
| FINRA | consolidated short interest (OAuth Query API), OTC Daily List lifecycle/corporate-action deltas, and generic asynchronous Query API jobs | `FINRA_CLIENT_ID`, `FINRA_CLIENT_SECRET` | 1,200 synchronous requests/minute/IP; 20 asynchronous submissions/minute/dataset/account; max 5,000 records and 3 MB per synchronous response; public credential capped at 10 GB downloaded/month | OAuth client / IP + dataset/account + calendar-month credential bandwidth | synchronous datasets live-proven; async submit/poll/presigned-download flow is fixture-tested and becomes routable only with a positive reviewed result-byte bound; the default unbounded path remains fail-closed |
| FINRA OTC directory | current `otcSecurityMaster` DAPI snapshot, or configured pipe-delimited OTC/OTCBB mirror | `FINRA_OTC_SYMBOL_DIRECTORY_URL` plus reviewed operation-cost/terms controls | Official FINRA synchronous platform ceiling: 1,200 requests/minute/IP and 3 MB maximum response; source-specific polling and redistribution terms still require review | configured source / rolling IP request window | full current DAPI pagination is live-proven; response-dependent partition/page cost is fail-closed by default and becomes routable only with a complete reviewed operation-cost map plus source governance controls |
| FRED | macro/rates/FX daily series | `FRED_API_KEY` | FRED v1 documents up to 120 requests/minute before HTTP 429, but does not publish the enforcement scope; the terms permit provider-adjusted limits plus series-specific copyright/redistribution restrictions. The separate v2 2-requests/second rule is not applied to this v1 adapter | provider-defined scope / rolling minute; adjustable | **numeric ceiling recorded; enforcement scope, adjustable-limit, and terms gates remain non-routable** |
| Nasdaq Trader | official `nasdaqlisted.txt`/`otherlisted.txt` US NMS listing/lifecycle files | none | No numeric public limit in the symbol-directory definition; each refresh conditionally requests both files and records response headers | public service / unknown | **discovery evidence only; quota unknown; compound two-file operation is explicitly observable** |
| Tiingo | EOD history, search, profiles | `TIINGO_API_KEY` | 500 unique symbols/month, 50/hour, 1,000/day, 1 GB/month (free Starter); monthly bandwidth resets on the first day at midnight Eastern | API key / multiple windows | EOD live-proven; response bytes and distinct provider-symbol claims are durable; routing still requires a complete reviewed `TIINGO_OPERATION_BYTE_BOUNDS` map (the 500-symbol pool is not request-count accounting) |
| Twelve Data | multi-timeframe candles, quote, search, US universe | `TWELVE_DATA_API_KEY` | 8 credits/min and 800/day Basic; time-series responses cap at 5,000 points and each request costs one credit | API key / minute + day | bounded history is explicitly paged by start/end range and reserves `ceil(requested points / 5,000)` credits; configured live evidence remains required |
| Finnhub | profile/search, historical earnings, forward earnings calendar, and universe; candle adapter retained for higher entitlements | `FINNHUB_API_KEY` | observed free account 60 calls/min; all plans also have a 30 calls/sec hard cap | token / minute + rolling second | profile, historical earnings, and forward calendar live-proven; both earnings surfaces are registered under `earnings`; free stock candles returned 403 and are explicitly non-routable |
| Marketstack | daily EOD history and venue-scoped ticker discovery | `MARKETSTACK_API_KEY`, `MARKETSTACK_DISCOVERY_EXCHANGE` | Free-plan pricing publishes 100 requests/month and one year of history; a stale FAQ sentence says 1,000, so the checked-in contract uses the lower 100-request ceiling; EOD responses expose 100-row pagination metadata | key / calendar month | history follows returned pagination and reserves a conservative page count before execution; discovery is fail-closed until an explicit MIC/exchange code is configured, and is supplementary rather than complete US venue reconciliation; daily history live-proven |
| EODHD | long-history daily EOD, fixture-covered fundamentals/profile adapter, US exchange list | `EODHD_API_KEY` | Free 20 API calls/day and 1,000 requests/minute; EOD free history is limited to one year; the supplied free key returned HTTP 403 for Fundamentals, while the official plan description limits free access to EOD history and exchange lists; data-heavy endpoints consume multiple calls (fundamentals/options 10, intraday/technical/news 5) | API key / minute requests + GMT calendar-day call budget | EOD daily/weekly/monthly history live-proven; Fundamentals is explicitly non-routable for the current free entitlement and its 403 is retained as typed evidence |
| FMP | stable-API daily history, profile, stock list, and earnings calendar | `FMP_API_KEY` | observed free account 250 calls/day and 512 MB/30 days; the dashboard does not publish a reset anchor, so the request allowance is enforced conservatively as a rolling 24-hour window and bandwidth is tracked as a rolling 30-day constraint | key / rolling 24-hour request window + rolling 30-day bandwidth | stable EOD history and `earnings-calendar` normalization live-proven for the configured key; response bytes are durable; routing requires complete reviewed `FMP_OPERATION_BYTE_BOUNDS` |
| Tradier | US daily history, quotes/search, current option expirations/chains with provider Greeks | `TRADIER_API_KEY` | 60/min sandbox; 120/min production market-data quota, response headers expose remaining/reset | token / minute | option endpoints normalize OCC symbols, contract fields, and nested Greeks; account live evidence required |
| MarketData.app | delayed US stocks/options candles, option expirations, current option-chain normalization, and historical/current single-contract option quotes | `MARKETDATA_APP_API_KEY` | 100 credits/day free, reset 09:30 ET; 50 account-wide concurrent requests; free/trial history limited to one year; expirations cost 1 credit/call, current chain/quote calls cost per returned contract/symbol, historical quotes/chains per 1,000 observations/contracts | key / reset-day credits + durable in-flight concurrency; option-chain admission additionally requires `MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS` | credentialed daily-candle, expirations/option-chain, and historical option-quote adapter paths live-proven 2026-09-12; the live option-chain probe is bounded to 20 contracts, while chain routing remains fail-closed at the default zero bound |
| IBKR | read-only Client Portal Gateway security search, instrument profile, raw historical OHLCV, and latest-price snapshots; options/futures-specific methods remain unimplemented | `IBKR_READ_ONLY_URL`, `IBKR_READ_ONLY_SESSION_COOKIE`, optional `IBKR_CONID_MAP` | Global 10 requests/sec/session; historical endpoint 50 requests/minute, max 5 concurrent, and max 1,000 bars per response; endpoint-specific pacing and penalty-box behavior apply | authenticated gateway session / rolling endpoint windows; interactive gateway login is required and may need to be renewed daily | concrete adapter is fixture-covered; raw history/latest/profile remain non-routable until a gateway session and bounded live evidence are supplied; adjusted history is filtered before routing |
| xStocks (Backed) | tokenized equity/ETF catalogue, deployments, indicative prices, multipliers, supply and corporate actions | none for documented public reads; optional `XSTOCKS_API_KEY` | Numeric public quota is not published; official legal materials state xStocks are not available in the United States or to U.S. persons | public endpoint / unknown | public metadata and price-endpoint probe passed; an explicit null quote while the selected token's session was closed is retained as provider state; non-routable until quota, jurisdiction, and redistribution eligibility are verified |
| Robinhood Chain Stock Tokens | tokenized-stock catalogue, chain deployments, multiplier, indicative bid/ask and corporate actions | none for documented public reads | 60 requests/sec for the public Stock Token API; cached responses and edge `429` responses apply | public IP / rolling second | bounded live asset + quote probe passed; read-only and non-routable until entitlement is promoted |
| Bybit xStocks | xStocks spot instrument catalogue and ticker bid/ask/last | none for public market-data endpoints | 600 HTTP requests per 5 seconds per IP outer limit; API limits are rolling per second per UID and endpoint, with `X-Bapi-Limit*` headers documented but not emitted by the current unauthenticated public edge | IP + endpoint/UID / rolling | bounded live asset + ticker probe passed; endpoint/UID accounting and reliable native-header state required before routing |
| Gate TradFi stock API | public US stock-token symbol catalogue and order-book bid/ask | none for public symbol/order-book endpoints | 5 requests/sec/IP for each documented public TradFi stock endpoint (`/stock/symbols`, `/stock/symbols/detail`, `/stock/market/{symbol}/orderbook`) | IP / rolling | bounded live symbol + order-book probe passed; the runtime applies a conservative aggregate 5-request/sec capability window |
| Kraken xStocks | provider-native xStocks pair discovery and public ticker when such pairs are published | none | Kraken public safe-frequency guidance is approximately 1 request/sec; pair/IP accounting applies | IP/pair / rolling | live catalogue probe passed with no currently published xStocks pair; no synthetic mapping is created |
| Ondo Global Markets | authenticated tokenized US stock/ETF metadata, chain addresses/ISIN/tags, indicative latest prices, display-only primary/underlying market summaries (including 24-hour price history and underlying metrics), and OHLC candles | `ONDO_GLOBAL_MARKETS_API_KEY` | OpenAPI documents HTTP 429/account rate limiting but no numeric quota; endpoint caching and display-only/non-oracle restrictions apply | API key/account / provider-defined | concrete metadata/latest-price/market-summary/OHLC adapter is fixture-covered; no live credential evidence yet; remains non-routable until account terms/quota are reviewed |
| Dinari | partner-authenticated dShare stock/ETF metadata, provider UUIDs, CAIP-10 deployments, FIGI/CIK/CUSIP metadata, current fair price, bid/ask quote, DAY/WEEK/MONTH/YEAR aggregate history, news, dividends, and splits | `DINARI_API_KEY_ID`, `DINARI_API_SECRET_KEY`, `DINARI_API_BASE_URL` | Numeric account/partner quota is not published; US SIP/NBBO quotes are metered and may incur per-query fees, with display/redistribution and partner-approval requirements | API key ID/secret + partner account / provider-defined | replacement Sandbox pair live-proven 2026-09-12 against https://api-enterprise.sandbox.dinari.com/api/v2; remains non-routable until commercial, US eligibility, quota, and redistribution terms are reviewed |
| Alpaca tokenization network | catalogue-only tokenization-network candidate, distinct from Alpaca market-data keys | authorized-participant access required | Market-data credentials do not entitle tokenization-network access | account / unknown | descriptor only; not routable |
| yfinance | legacy broad fallback, options/futures compatibility only | none | No official quota/SLA; unofficial scraping | unknown | legacy-only and disabled by default |
| ETF holdings internal | platform's issuer/SEC holdings ingestion | internal configuration | Internal job/provider budgets, not an external market-data API | internal | generic bridge only; issuer-specific work remains on ETF branch |

Nasdaq Trader's directory is listing evidence, not a complete delisting-event feed.
The adapter excludes test issues, retains Nasdaq Financial Status Indicators
(including deficient or bankrupt-but-listed issues), and uses repeated complete
absence plus separate lifecycle evidence before marking a listing inactive.
See the [official symbol-directory definitions](https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs).
The adapter also sends `If-None-Match` and `If-Modified-Since` on subsequent
polls when Nasdaq returns `ETag` or `Last-Modified`, reusing the cached parsed
file on a `304 Not Modified`. This reduces repeated downloads without
inventing a numeric polling allowance; quota admission remains disabled until
Nasdaq publishes a reviewed contract.

The FRED adapter uses the v1 endpoint. Its [v1 errors documentation](https://fred.stlouisfed.org/docs/api/fred/errors.html)
states that up to 120 requests per minute are allowed before HTTP 429, but it
does not publish the enforcement scope. The [v1 API terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html)
also allow the provider to adjust bandwidth and transaction limits. The
separate [v2 errors documentation](https://fred.stlouisfed.org/docs/api/fred/v2/errors.html)
mentions a 2-requests/second threshold for v2; the runtime deliberately does
not apply that v2 rule to the v1 adapter. The runtime records the published
120/minute dimension plus the unresolved enforcement-scope, adjustable-limit,
and series-rights gates, and keeps FRED non-routable until those are reviewed. An
operator may promote a deployment only by supplying all three non-secret
controls: `FRED_REVIEWED_LIMIT_SCOPE` (`api_key`, `account`, `ip`, or
`deployment`), `FRED_REVIEWED_REQUESTS_PER_MINUTE` (a conservative positive
integer no greater than 120), and `FRED_SERIES_TERMS_REVIEWED=true`. When all
three are present, the runtime replaces the unresolved seed dimensions with
that explicitly reviewed conservative contract; no value is inferred from the
generic provider defaults. The
[FRED API terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html) also
allow the provider to change bandwidth/transaction limits, place
series-specific copyright restrictions on third-party data, and require a
non-endorsement notice. Missing `FRED_API_KEY` raises an explicit
`ProviderNotConfiguredError`; HTTP 429/418 responses are preserved as typed
capacity failures with provider headers and `Retry-After` timestamps rather
than returning an empty series or price. FRED remains non-routable until the
scope and downstream usage/redistribution policy are explicitly reviewed.
Marketstack's [pricing page](https://marketstack.com/pricing) publishes the
free 100-request/month plan; its [FAQ](https://marketstack.com/faq) contains a
conflicting 1,000-request sentence, so the runtime records the lower 100 limit
and remains gated on account/terms review. The explicit
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

Tiingo and FMP publish bandwidth pools but do not publish one universal maximum
response size for every adapter operation. The runtime therefore does not
invent a byte ceiling. An operator who has reviewed the current endpoint
contract may set complete JSON maps in `TIINGO_OPERATION_BYTE_BOUNDS` and
`FMP_OPERATION_BYTE_BOUNDS`, for example:

```env
# Do not copy guessed values: populate each map only with reviewed provider
# endpoint ceilings. Empty or partial maps intentionally remain non-routable.
TIINGO_OPERATION_BYTE_BOUNDS={}
FMP_OPERATION_BYTE_BOUNDS={}
```

Every operation exposed by the relevant adapter must be present with a positive
bound, including `get_current_price`, which uses the adapter's bounded latest
history request path, `bulk_fetch`, which is used by the deep-history worker,
and FMP's `fetch_market_events`, which calls the stable earnings calendar.
Complete maps move the provider's documented bandwidth pool into the
same durable multidimensional reservation path as request limits; response
bytes settle the reservation after execution. Tiingo additionally publishes a
500-unique-symbol monthly pool, which cannot be represented as one unit per
request: repeated symbols and multi-symbol operations are tracked by the
durable `provider_quota_identity` ledger. Missing, zero, malformed, or partial
byte maps still leave the provider non-routable; the symbol pool itself is no
longer approximated as request count.

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

### Tokenized securities boundary

Tokenized products are first-class instruments, not ticker aliases. Each stored
instrument receives a stable provider-scoped `domain_key` and retains the
provider asset ID, chain/network, contract deployment(s), token ISIN when
published, underlying symbol/ISIN, multiplier, supply, backing classification,
and corporate-action payload. The economic underlying is linked only when the
existing canonical instrument match is unambiguous; a ticker collision leaves
the relationship unresolved rather than merging two securities.

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

xStocks has an additional US eligibility gate: its [official legal notice](https://xstocks.com/us)
states that xStocks are not available in the United States or to U.S. persons.
The public metadata adapter may retain non-trading observations for research,
but those observations cannot be routed as an eligible US data or trading
source unless the operator documents a lawful, jurisdiction-specific basis and
redistribution permission.

Dinari's [stock-data guide](https://docs.dinari.com/docs/stock-data) documents
provider-native Stock UUIDs, aggregate DAY/WEEK/MONTH/YEAR history, news, and
live price/quote endpoints. Its [pricing guide](https://docs.dinari.com/docs/pricing-quotes)
distinguishes the computed fair price from bid/ask quotes, and notes that US
SIP/NBBO data is metered. The adapter never treats CIK/CUSIP/FIGI fields as the
token's primary identity and never fabricates volume for the aggregate history.
Dinari's [US-customer requirements](https://docs.dinari.com/docs/us) make partner
approval, regulatory, data-security, and redistribution review a deployment
gate, so having a key alone does not make this provider routable.

Ondo's [API overview](https://docs.ondo.finance/api-reference/overview),
[market-data endpoint](https://docs.ondo.finance/api-reference/assets/get-market-data-for-an-asset),
and [OpenAPI contract](https://docs.ondo.finance/openapi.json) document the
API-key protected metadata, latest-price, market-summary, and OHLC endpoints.
The OHLC adapter accepts
only the provider's published interval/range pairs and returns primary-token
and underlying-stock candles separately. Ondo explicitly marks price feeds as
display-only and not suitable as an oracle; its OpenAPI documents HTTP 429 but
does not publish a numeric quota, so this provider remains fail-closed pending
account-specific terms and usage evidence.

The runtime records provider-specific quota dimensions and refuses to route a
tokenized provider when any dimension is unknown, weighted per endpoint, or
requires response-header/account enforcement that is not yet fully modeled.
Quote refresh accounting also follows the adapters' actual request shape. The
standard tokenized `get_tokenized_price` operations reserve two provider
requests (asset metadata plus quote/order-book), while discovery and asset reads
reserve one. Dinari's quote, historical, news, dividend, and split operations,
and Ondo's market-summary and OHLC operations likewise reserve two requests
because each resolves
provider metadata before the data read. Robinhood additionally reserves four
requests: one asset lookup plus the bounded three-attempt quote retry worst
case. This prevents a successful quote response or bounded retry from being
recorded as fewer requests than the adapter may actually make. Dinari's history
deliberately returns aggregate OHLC without inventing volume; Ondo's OHLC
interval/range combinations are validated against the provider's published
finite matrix and every candle retains explicit primary-versus-underlying
market scope. Both adapters preserve raw provider payloads for provenance.
Bybit's official [rate-limit contract](https://bybit-exchange.github.io/docs/v5/rate-limit)
publishes both the 600/5-second/IP outer ceiling and rolling per-second
endpoint/UID limits. The current public xStocks responses were live-probed and
did not emit the documented `X-Bapi-Limit*` headers; the adapter retains those
headers if they appear, but absence is not converted into a guessed allowance.
Bybit remaining-limit headers are reconciled only when they exactly match the
reviewed coarse outer contract, but endpoint/UID limits and reliable native
header state keep that route non-routable until they are modeled. Gate's public stock contract is
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

Corporate actions use a dedicated `tokenized_corporate_actions` capability and
a separate opt-in schedule so an operator can budget event-feed quota
independently from quote polling. Set
`TOKENIZED_EVENT_REFRESH_ENABLED=true`, with bounded
`TOKENIZED_EVENT_REFRESH_MAX_PROVIDERS` and
`TOKENIZED_EVENT_REFRESH_PAGE_SIZE`, in both the backend and worker
environment. xStocks is read in separate historical and upcoming requests;
Robinhood exposes one combined action feed. Every request uses the exact
`fetch_tokenized_corporate_actions` operation cost declared for that provider.
Rows are persisted as provisional `MarketEvent` records with the complete raw
provider payload. A token is linked only when an explicit provider asset ID or
unique token symbol matches the stored token detail; otherwise the event is
retained unlinked for later reconciliation rather than guessed onto an
underlying ticker. Exchange token adapters without an action endpoint are
reported as unsupported and never invoked.

| Provider   | Role        | Auth required           | Cost     |
|------------|-------------|-------------------------|----------|
| alpaca     | Primary     | API key + secret        | Free     |
| fred       | Primary     | API key                 | Free     |
| binance    | Primary candidate (weight-accounting gate) | None | Free |
| coingecko  | Primary     | Free demo API key       | Free     |
| edgar      | Primary     | Contact User-Agent      | Free     |
| yfinance   | Explicit legacy/options fallback only | None (unofficial) | Free, no SLA |
| openfigi   | Supplementary | Optional API key      | Free     |
| massive    | Optional reference/IPO-calendar corroboration | Optional API key | Free tier / 5 requests/minute |
| alpha_vantage | Optional daily-history corroboration | Optional API key | Free tier / quota |
| tiingo / twelve_data | Optional EOD/intraday history | API key | Free/low-cost quota |
| finnhub | Optional intraday/profile/search | API key | Free/low-cost quota |
| marketstack / eodhd / fmp | Optional EOD/history/profile | API key | Free/low-cost quota |

Concrete adapters now exist for the cheap/keyless exchange and REST surfaces
listed above (`coinbase`, `kraken`, `tradier`, and `marketdata_app` included).
IBKR has a concrete read-only Client Portal Gateway adapter for profile/search,
raw historical bars, and latest-price snapshots. It intentionally does not
automate the gateway's interactive login, does not claim options/futures
methods that are not implemented, and refuses to label raw bars as adjusted.
Its documented 10-requests/second session ceiling, 50 historical-requests/
minute ceiling, five-concurrent-history limit, and 1,000-bar response cap are
recorded; the adapter remains non-routable until a gateway session and bounded
live evidence are supplied. Credentials, quota, and
personal-use/redistribution terms are never inferred from an API key alone.
The implementation follows IBKR's [historical market-data endpoint](https://ibkrcampus.com/docs/web-api/v1/endpoints/market-data/historical-market-data),
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
  compatibility columns.
- `exchange_session_rule` and `exchange_calendar_exception` retain versioned
  sessions, holidays, early closes, overnight trade-date rules, and source
  provenance.
- `provider_quota_window`, `provider_workload_lease`, and
  `provider_routing_decision` make reservations and routing explanations
  durable across workers; administrators can inspect them through the
  backend-only `/api/v1/market-data/*` diagnostics routes.
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
  a complete universe and records core D1 coverage after a successful run.
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

Corporate actions use the current v1 endpoint and follow its `next_page_token`
cursor. Because the number of requests is response-dependent, the checked-in
usage profile deliberately has no fixed event cost. Runtime event routing is
fail-closed until a positive, conservative `ALPACA_CORPORATE_ACTIONS_MAX_PAGES`
bound is reviewed for the deployment; the bound is reserved as the worst-case
request cost and the adapter raises before issuing an unreserved page. Direct
live probes may still exercise the full cursor with the default zero control.

**Capabilities**

| Capability           | Detail                                              |
|----------------------|-----------------------------------------------------|
| `price_history`      | All US equities + crypto, all timeframes, 5+ years |
| `latest_price`       | Current bar close for equities and crypto           |
| `instrument_events`  | Corporate actions: splits, reverse splits, dividends|
| `universe_discovery` | ~9 000 active US equities + USDT-quoted crypto      |

**Rate limits**: 200 requests/minute on data endpoints (free IEX feed). The
runtime estimates the complete `next_page_token` history request count from
the requested range and reserves every conservative 1,000-bar page before
execution; latest-bar lookbacks use the same bound.

Corporate actions use Alpaca's current `GET /v1/corporate-actions` market-data
endpoint with the `symbols`, `types`, `start`, `end`, and `page_token` contract.
The deprecated v2 announcements endpoint is not used; payable dates are read
from `payable_date` and long ranges follow the provider page token.

**Getting credentials**:
1. Create a free account at alpaca.markets
2. Generate Paper Trading API keys from the dashboard
3. Set `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` in `.env.dev`

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
   reviews the account scope and series rights; then set the three controls
   described above in the deployment secret/config store.

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
  dimensions are reserved independently. CoinGecko publishes the monthly cap
  but does not specify its reset boundary in the pricing contract, so the
  runtime uses a conservative provider-defined rolling window until an
  account-native usage observation confirms the boundary.
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

**Rate limit**: max 10 requests/second per SEC guidelines.

---

### MarketData.app (`marketdata_app`)

**Role**: Authenticated US stock/ETF candles and options data, including
expiration discovery, current chains, and historical single-contract quotes.
**Auth**: `MARKETDATA_APP_API_KEY` (Bearer token)

The adapter follows the documented `/v1` endpoints and preserves OCC symbols,
provider timestamps, quote fields, and historical null Greeks. The provider
documents 100 daily credits on Free Forever accounts, reset at 09:30
America/New_York, plus a 50-request concurrency ceiling. Free/trial accounts
receive delayed data and only one year of historical data. See the provider's
[rate-limit](https://www.marketdata.app/docs/api/rate-limiting/),
[free-account](https://www.marketdata.app/docs/account/free-accounts/),
[option-chain](https://www.marketdata.app/docs/api/options/chain/), and
[option-quotes](https://www.marketdata.app/docs/api/options/quotes/)
documentation. The repository's 100-credit seed is specifically the documented
Free Forever contract; an account that returns another native limit is not
silently promoted. Record the reviewed account plan and exact matching daily
limit in `MARKETDATA_APP_REVIEWED_PLAN` (`free_forever`, `starter`, or `trader`)
and `MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT` (`100`, `10000`, or `100000`).
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

This is a separate discovery adapter for FINRA's current public
`otcSecurityMaster` DAPI dataset and for an explicitly configured
pipe-delimited OTC/OTCBB mirror. The DAPI path resolves the newest `asOfDate`
partition, pages to the provider's `record-total`, preserves each raw source
record, and exposes the source URL in every page. The recommended source is:
`https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster`.

The source is publicly reachable and full pagination is covered by the live
probe. FINRA's platform documentation publishes the synchronous 1,200
requests/minute/IP and 3 MB response ceilings, which are recorded in the
provider contract. The provider remains non-routable until the source URL is
explicitly configured and operations supplies a positive reviewed
`FINRA_OTC_OPERATION_COSTS` map for both `discover_universe_page` and
`reconcile_universe_page`. Those costs are conservative charges for the
response-dependent cold refresh, not a guessed one-request default. Routing
also requires independent affirmative controls for source terms,
complete-universe interpretation, redistribution, and a positive
`FINRA_OTC_POLL_INTERVAL_SECONDS`; these controls record review decisions but
do not claim FINRA has published a minimum polling interval. The Daily List
adapter remains the lifecycle-delta path and is not substituted for this
current security master.

FINRA's asynchronous Query API result payloads are documented as unbounded.
The adapter therefore requires a positive `FINRA_ASYNC_MAX_RESULT_BYTES` (or
an explicit per-call bound), validates `Content-Length` when supplied, and
enforces the limit while streaming chunks so oversized bodies are not
materialized in memory. A positive configured bound also becomes the
operation-specific reservation against the provider's durable 10 GiB monthly
credential budget; the signed leg consumes no API-request-minute dimension and
settles to measured bytes. The default `0` remains fail-closed and
non-routable, because an unbounded provider result cannot be admitted safely.

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
ALPACA_CORPORATE_ACTIONS_MAX_PAGES=0 # positive reviewed bound required before Alpaca event routing

# FRED
FRED_API_KEY=your_fred_key
FRED_REVIEWED_LIMIT_SCOPE=
FRED_REVIEWED_REQUESTS_PER_MINUTE=0
FRED_SERIES_TERMS_REVIEWED=false

# CoinGecko
COINGECKO_API_KEY=your_coingecko_demo_key

# SEC EDGAR — no key, but User-Agent is required
# Set a real application/contact value before enabling SEC calls; blank is intentionally fail-closed.
EDGAR_USER_AGENT=

# OpenFIGI (optional)
OPENFIGI_API_KEY=your_openfigi_key

# FINRA OAuth (required for current API)
FINRA_CLIENT_ID=
FINRA_CLIENT_SECRET=
FINRA_TOKEN_URL=https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token
FINRA_API_BASE_URL=https://api.finra.org
FINRA_SHORT_INTEREST_URL=
FINRA_OTC_DAILY_LIST_URL=
FINRA_OTC_SYMBOL_DIRECTORY_URL=https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster
FINRA_OTC_OPERATION_COSTS={}
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
# Account plan/limit must be explicitly reviewed together. Supported daily
# pairs are free_forever/100, starter/10000, and trader/100000. Leave blank/0
# when the account entitlement is not confirmed; native headers never widen it.
MARKETDATA_APP_REVIEWED_PLAN=
MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT=0
# Current option chains consume one credit per returned symbol. Set this only
# after reviewing the exact request filters; zero keeps chain routing closed.
MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS=0
TRADIER_API_KEY=
FMP_API_KEY=                  # Financial Modeling Prep — fundamentals, forward estimates

# Optional complete US universe/lifecycle reconciliation (worker only)
MARKET_UNIVERSE_RECONCILIATION_ENABLED=false
MARKET_UNIVERSE_MISSING_CONFIRMATIONS=3
```

---

## Provider Chain Defaults

The default provider chain can be overridden per capability via `PROVIDER_CHAIN_SEEDS`
(JSON dict in `.env.dev`). The free-source-first new-workstation baseline is:

```env
PROVIDER_CHAIN_SEEDS={"instrument_search":["edgar","massive","alpha_vantage"],"instrument_metadata":["edgar"],"price_history":["alpaca","alpha_vantage"],"latest_price":["alpaca","alpha_vantage"],"instrument_events":["alpaca","edgar","finnhub"],"universe_discovery":["alpaca","edgar","massive","nasdaq","finra_otc_directory","alpha_vantage"],"tokenized_corporate_actions":["robinhood_tokens","xstocks"]}
TOKENIZED_PROVIDER_PRIORITY=["robinhood_tokens","xstocks","bybit_xstocks","gate_tradfi","kraken_xstocks","dinari","ondo_global_markets"]
```

Adding `yfinance` requires an explicit legacy/options deployment decision and must never
silently broaden a new-workstation chain.

Massive's IPO-calendar adapter uses the documented
[`reference/ipos`](https://massive.com/docs/rest/stocks/corporate-actions) endpoint.
Each cursor page is an independently metered request; the adapter returns the
continuation URL without silently following it, and applies date bounds locally.
The same adapter also exposes the documented
[`marketstatus/upcoming`](https://massive.com/docs/rest/indices/market-operations)
forward holiday and early-close feed as normalized `market_holiday` events.

Priority within a chain is refined at runtime by health scores (EWMA latency, success rate,
completeness).  A provider that consistently fails for a given symbol class (e.g. Binance
receiving equity symbols) will be naturally deprioritised by the circuit-breaker logic.

---

## Coverage Summary

| Data type                    | Primary provider  | Fallback        |
|------------------------------|-------------------|-----------------|
| US equity OHLCV              | alpaca            | alpha_vantage (quota-limited) |
| US equity/ETF universe discovery | alpaca / SEC directory / Nasdaq NMS files | massive / FINRA OTC directory (explicit source) / alpha_vantage |
| US splits + dividends        | alpaca            | edgar           |
| Crypto OHLCV                 | binance / coinbase / kraken | Alpaca (where symbol coverage applies) |
| Crypto universe discovery    | Nasdaq Trader (US listings) + exchange APIs | CoinGecko Demo |
| Crypto metadata              | coingecko         | —               |
| Interest rates (RFR, yields) | fred              | —               |
| Major forex daily rates      | fred              | —               |
| Macro indicators             | fred              | —               |
| US company profile           | edgar             | —               |
| Historical earnings dates    | edgar             | —               |
| US options chains            | yfinance (explicit legacy), Tradier/MarketData.app when entitled | *(no default current-chain route)* |
| Futures / commodities        | yfinance (explicit legacy) | IBKR generic read-only adapter (futures-specific methods not implemented) |
| Forward earnings estimates   | Finnhub forward calendar; FMP `earnings-calendar` | Finnhub and FMP calendars are live-proven for configured keys; FMP routing remains byte-bound gated |
| IPO calendar                 | Massive `reference/ipos`; Alpha Vantage `IPO_CALENDAR` | Massive returns cursor-paged IPO rows; each page is charged separately and date bounds are applied locally |
| Market holidays / early closes | Massive `marketstatus/upcoming` | Forward-only exchange rows with open/close/status provenance; one request per refresh |
| Analyst price targets        | *(excluded)*      | *(capability stub)* |

Remaining gaps are tracked in [project-todos.md](project-todos.md).
