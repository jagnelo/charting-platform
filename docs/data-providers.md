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
> live-probe evidence. Alpaca, Tradier, and MarketData.app remain `not_run` in
> this revision and cannot enter a chain merely because a key is later added.

## Provider capability and quota ledger

The table below is the checked-in contract used by `ProviderPolicy` and the
durable `ProviderQuotaWindow` counters. “Unknown” is deliberate; it is not a
placeholder estimate. Limits are for the named plan/scope only and must be
re-reviewed when credentials or billing plans change.

| Provider | Implemented data surface | Credential/config key | Documented usage contract | Reset/scope | Routing status |
|---|---|---|---|---|---|
| Alpaca | US stocks/ETFs + crypto OHLCV, latest, corporate actions, assets | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | 200 historical API calls/min | provider/account window; free IEX feed restriction applies | contract recorded; live evidence required |
| Massive | US ticker search and reference universe | `MASSIVE_API_KEY` (or legacy `MARKETDATA_API_KEY`) | 5 requests/min, Basic Stocks | API key / minute | credentialed reference search live-proven |
| Alpha Vantage | Daily OHLCV, symbol search, listings, IPO events | `ALPHA_VANTAGE_API_KEY` | 25 requests/day (free key); `compact` daily output is latest 100 points, `full` is premium | API key / provider-defined day | compact daily history live-proven |
| SEC EDGAR | issuer/ticker/exchange directory, profiles, filings/earnings, XBRL facts | `EDGAR_USER_AGENT` | 10 requests/sec total across an IP | IP / rolling fair-access window | contract recorded; keyless live evidence required |
| OpenFIGI | FIGI/ISIN/CUSIP/SEDOL mapping and profile enrichment | optional `OPENFIGI_API_KEY` | 25 requests/min without key (keyed plan has separate 6-sec/100-job contract) | IP or key / rolling | keyless contract recorded; live probe required |
| Binance | public crypto OHLCV, ticker, USDT universe | none | Current Spot REST documentation exposes a 6,000 request-weight/min IP ceiling. Adapter operations use documented weights: single-symbol price 2 and exchange-info discovery 20. Historical OHLCV costs weight 2 per 1,000-candle page; the requested range is conservatively paged and reserved before execution; response `X-MBX-USED-WEIGHT-*` and `Retry-After` headers are retained on capacity failures | IP / fixed minute; 429/418 protection | exact-weight price/discovery and bounded historical operations admitted only when the calculated weight fits |
| Coinbase Exchange | public crypto candles, ticker, USD products | none | 10 public requests/sec, burst up to 15 | IP / rolling | contract recorded; keyless live evidence required |
| Kraken | public crypto OHLC, ticker, USD pairs | none | safe public frequency <=1 request/sec; pair/IP limits apply | IP/pair / rolling | contract recorded; keyless live evidence required |
| CoinGecko Demo | crypto search, metadata, market-cap universe | `COINGECKO_API_KEY` | 100 calls/min and 10,000 calls/month | Demo key / minute + calendar month | credentialed search live-proven |
| FINRA | consolidated short interest (OAuth Query API), OTC Daily List lifecycle/corporate-action deltas, and generic asynchronous Query API jobs | `FINRA_CLIENT_ID`, `FINRA_CLIENT_SECRET` | 1,200 synchronous requests/minute/IP; 20 asynchronous submissions/minute/dataset/account; max 5,000 records and 3 MB per synchronous response; public credential capped at 10 GB downloaded/month | OAuth client / IP + dataset/account + calendar-month credential bandwidth | synchronous datasets live-proven; async submit/poll/presigned-download flow is fixture-tested but remains non-routable until unbounded async-result byte accounting is safely reserved |
| FINRA OTC directory | current `otcSecurityMaster` DAPI snapshot, or configured pipe-delimited OTC/OTCBB mirror | `FINRA_OTC_SYMBOL_DIRECTORY_URL` | Official FINRA synchronous platform ceiling: 1,200 requests/minute/IP and 3 MB maximum response; source-specific polling and redistribution terms still require review | configured source / rolling IP request window | full current DAPI pagination is live-proven; explicit quota is recorded, but adapter remains non-routable until source configuration and terms review are complete |
| FRED | macro/rates/FX daily series | `FRED_API_KEY` | The deployed adapter uses FRED v1; its official errors page documents 429 throttling but no fixed numeric ceiling, so no limit is inferred from the separate v2 documentation | API key / provider-defined | **not routable until the deployed API version's ceiling is verified** |
| Nasdaq Trader | official `nasdaqlisted.txt`/`otherlisted.txt` US NMS listing/lifecycle files | none | No numeric public limit in the symbol-directory definition; poll conservatively and record response headers | public service / unknown | **discovery evidence only; quota unknown** |
| Tiingo | EOD history, search, profiles | `TIINGO_API_KEY` | 500 unique symbols/month, 50/hour, 1,000/day, 1 GB/month (free Starter); monthly bandwidth resets on the first day at midnight Eastern | API key / multiple windows | EOD live-proven; response bytes are now observed and durable, but **not routable until byte-budget reservation/enforcement exists** |
| Twelve Data | multi-timeframe candles, quote, search, US universe | `TWELVE_DATA_API_KEY` | 8 credits/min and 800/day Basic; cost is symbols/endpoint-weighted | API key / minute + day | daily history and configured one-credit operation live-proven |
| Finnhub | profile/search, earnings events/universe; candle adapter retained for higher entitlements | `FINNHUB_API_KEY` | observed free account 60 calls/min; all plans also have a 30 calls/sec hard cap | token / minute + rolling second | company profile live-proven; free stock candles returned 403 and are explicitly non-routable |
| Marketstack | daily EOD history and ticker discovery | `MARKETSTACK_API_KEY` | Free-plan pricing publishes 100 requests/month and one year of history; a stale FAQ sentence says 1,000, so the checked-in contract uses the lower 100-request ceiling | key / calendar month | daily history live-proven |
| EODHD | long-history daily EOD, fundamentals/profile, US exchange list | `EODHD_API_KEY` | Free 20/day and 20/min, one-year history; paid $19.99/month adds 100k/day, 1,000/min, 30+ years | API key / minute + day | daily history live-proven |
| FMP | stable-API daily history, profile, stock list | `FMP_API_KEY` | observed free account 250 calls/day and 512 MB/30 days; the dashboard does not publish a reset anchor, so the request allowance is enforced conservatively as a rolling 24-hour window and bandwidth is tracked as a rolling 30-day constraint | key / rolling 24-hour request window + rolling 30-day bandwidth | stable EOD history live-proven; response bytes are now observed and durable, but **not routable until byte-budget reservation/enforcement exists** |
| Tradier | US daily history, quotes/search; options-capable REST surface | `TRADIER_API_KEY` | 60/min sandbox; 120/min production market-data quota, response headers expose remaining/reset | token / minute | adapter + contract recorded; account live evidence required |
| MarketData.app | delayed US stocks/options candles (options surface is optional) | `MARKETDATA_APP_API_KEY` | 100 credits/day free, reset 09:30 ET; 50 concurrency; free/trial history limited to one year | key / reset-day + concurrency | adapter + contract recorded; account live evidence required |
| IBKR | account-bound stocks/options/futures/crypto via read-only Web API descriptor | deployment-specific `IBKR_READ_ONLY_URL` | Global 10 requests/sec/session; `/iserver/marketdata/history` max 5 concurrent; endpoint-specific pacing and a 15-minute penalty box apply | session/account / endpoint | pacing contract recorded; descriptor only, no routing until a funded-account adapter/evidence exists |
| xStocks (Backed) | tokenized equity/ETF catalogue, deployments, indicative prices, multipliers, supply and corporate actions | none for documented public reads; optional `XSTOCKS_API_KEY` | Numeric public quota is not published | public endpoint / unknown | public metadata/price probe passed; non-routable until quota is verified |
| Robinhood Chain Stock Tokens | tokenized-stock catalogue, chain deployments, multiplier, indicative bid/ask and corporate actions | none for documented public reads | 60 requests/sec for the public Stock Token API; cached responses and edge `429` responses apply | public IP / rolling second | bounded live asset + quote probe passed; read-only and non-routable until entitlement is promoted |
| Bybit xStocks | xStocks spot instrument catalogue and ticker bid/ask/last | none for public market-data endpoints | 600 HTTP requests per 5 seconds per IP outer limit; endpoint/UID limits and response headers are additional constraints | IP + endpoint/UID / rolling | bounded live asset + ticker probe passed; endpoint/UID accounting required before routing |
| Gate TradFi stock API | public US stock-token symbol catalogue and order-book bid/ask | none for public symbol/order-book endpoints | 5 requests/sec/IP for stock public endpoints | IP + endpoint / rolling | bounded live symbol + order-book probe passed; non-routable until endpoint accounting is wired |
| Kraken xStocks | provider-native xStocks pair discovery and public ticker when such pairs are published | none | Kraken public safe-frequency guidance is approximately 1 request/sec; pair/IP accounting applies | IP/pair / rolling | live catalogue probe passed with no currently published xStocks pair; no synthetic mapping is created |
| Ondo Global Markets | catalogue-only candidate for tokenized US stocks/ETFs | onboarding/API credentials required | Provider terms and quota not publicly verified in this branch | account / unknown | descriptor only; not routable |
| Dinari | catalogue-only tokenized-equity infrastructure candidate | partner/API access required | Commercial terms and quota not publicly verified in this branch | account / unknown | descriptor only; not routable |
| Alpaca tokenization network | catalogue-only tokenization-network candidate, distinct from Alpaca market-data keys | authorized-participant access required | Market-data credentials do not entitle tokenization-network access | account / unknown | descriptor only; not routable |
| yfinance | legacy broad fallback, options/futures compatibility only | none | No official quota/SLA; unofficial scraping | unknown | legacy-only and disabled by default |
| ETF holdings internal | platform's issuer/SEC holdings ingestion | internal configuration | Internal job/provider budgets, not an external market-data API | internal | generic bridge only; issuer-specific work remains on ETF branch |

Nasdaq Trader's directory is listing evidence, not a complete delisting-event feed.
The adapter excludes test issues, retains Nasdaq Financial Status Indicators
(including deficient or bankrupt-but-listed issues), and uses repeated complete
absence plus separate lifecycle evidence before marking a listing inactive.
See the [official symbol-directory definitions](https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs).

The FRED adapter uses the v1 endpoint. Its [v1 errors documentation](https://fred.stlouisfed.org/docs/api/fred/errors.html)
confirms 429 throttling but does not publish a fixed number; the v2 page's
two-requests-per-second example is therefore not applied to this adapter.
Marketstack's [pricing page](https://marketstack.com/pricing) publishes the
free 100-request/month plan; its [FAQ](https://marketstack.com/faq) contains a
conflicting 1,000-request sentence, so the runtime records the lower 100 limit
and remains gated on account/terms review.

The platform uses a capability-based provider chain.  For each data type the runtime selects the
highest-scoring available provider, falls back to the next, and so on.  Initial priorities below
reflect `base_priority` seeding; the runtime's EWMA health scores refine ordering over time.

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
expose exchange-native market surfaces. A provider returning no current
xStocks pairs is recorded as an empty catalogue, never as evidence that a
traditional share is the same token.

The runtime records provider-specific quota dimensions and refuses to route a
tokenized provider when any dimension is unknown, weighted per endpoint, or
requires response-header/account enforcement that is not yet implemented. The
live matrix is explicit and bounded:

```sh
RUN_LIVE_PROVIDER_TESTS=1 rtk uv run --project backend pytest \
  tests/live/test_tokenized_providers_live.py -m live --no-header -q --no-cov
```

The latest verified run passed all five public probes. Robinhood's public
price edge returned `local_rate_limited` during one run; its adapter now uses a
finite provider-specific retry budget, honors `Retry-After` when present, and
surfaces repeated 429s. The Kraken catalogue returned no current xStocks pair.
That evidence is retained as a routing/coverage fact, not hidden by a generic
retry or an invented symbol.

| Provider   | Role        | Auth required           | Cost     |
|------------|-------------|-------------------------|----------|
| alpaca     | Primary     | API key + secret        | Free     |
| fred       | Primary     | API key                 | Free     |
| binance    | Primary candidate (weight-accounting gate) | None | Free |
| coingecko  | Primary     | Free demo API key       | Free     |
| edgar      | Primary     | Contact User-Agent      | Free     |
| yfinance   | Explicit legacy/options fallback only | None (unofficial) | Free, no SLA |
| openfigi   | Supplementary | Optional API key      | Free     |
| massive    | Optional reference corroboration | Optional API key | Free tier / quota |
| alpha_vantage | Optional daily-history corroboration | Optional API key | Free tier / quota |
| tiingo / twelve_data | Optional EOD/intraday history | API key | Free/low-cost quota |
| finnhub | Optional intraday/profile/search | API key | Free/low-cost quota |
| marketstack / eodhd / fmp | Optional EOD/history/profile | API key | Free/low-cost quota |

Concrete adapters now exist for the cheap/keyless exchange and REST surfaces
listed above (`coinbase`, `kraken`, `tradier`, and `marketdata_app` included).
IBKR remains a descriptor because it is account/session-bound; its documented
pacing contract is recorded, but no capability is routable until a funded
account/session adapter is supplied and tested. Credentials, quota, and
personal-use/redistribution terms are never inferred from an API key alone.
FINRA now uses its OAuth client flow and has the documented synchronous quota
ceiling recorded; credential, terms, and live evidence are still required. A
provider becomes routable only after the governance record and live evidence
satisfy the contract.

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
  expose these records to backend operators without enabling a route.
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

**Capabilities**

| Capability           | Detail                                              |
|----------------------|-----------------------------------------------------|
| `price_history`      | All US equities + crypto, all timeframes, 5+ years |
| `latest_price`       | Current bar close for equities and crypto           |
| `instrument_events`  | Corporate actions: splits, reverse splits, dividends|
| `universe_discovery` | ~9 000 active US equities + USDT-quoted crypto      |

**Rate limits**: 200 requests/minute on data endpoints (free IEX feed).

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
  dimensions are reserved independently; the monthly counter resets on the
  first calendar day.

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
  `EDGAR_USER_AGENT="MyApp myemail@example.com"`
- SEC guidelines require this header to be set to a real contact.

**Rate limit**: max 10 requests/second per SEC guidelines.

---

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
explicitly configured and operations records current terms, completeness/
retention policy, polling allowance, and redistribution boundaries. The Daily
List adapter remains the lifecycle-delta path and is not substituted for this
current security master.

FINRA's asynchronous Query API result payloads are documented as unbounded.
The adapter therefore requires a positive `FINRA_ASYNC_MAX_RESULT_BYTES` (or
an explicit per-call bound), validates `Content-Length` when supplied, and
rejects bodies above the bound. This is only an adapter safety guard; the
async capability remains non-routable until durable monthly bandwidth
accounting can reserve and settle the provider's 10 GiB credential budget.

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

# FRED
FRED_API_KEY=your_fred_key

# CoinGecko
COINGECKO_API_KEY=your_coingecko_demo_key

# SEC EDGAR — no key, but User-Agent is required
EDGAR_USER_AGENT=charting-platform your.email@example.com

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
FINRA_ASYNC_MAX_RESULT_BYTES=0

# Optional adapters (disabled until governance records reviewed entitlements)
TIINGO_API_KEY=
TWELVE_DATA_API_KEY=
FINNHUB_API_KEY=
MARKETSTACK_API_KEY=
EODHD_API_KEY=
MARKETDATA_APP_API_KEY=       # MarketData.app — US delayed stocks/options
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
PROVIDER_CHAIN_SEEDS={"instrument_search":["edgar","alpaca","massive","alpha_vantage"],"instrument_metadata":["edgar"],"price_history":["alpaca","alpha_vantage"],"latest_price":["alpaca","alpha_vantage"],"instrument_events":["alpaca","edgar"],"universe_discovery":["alpaca","edgar","massive","nasdaq","alpha_vantage"]}
```

Adding `yfinance` requires an explicit legacy/options deployment decision and must never
silently broaden a new-workstation chain.

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
| Futures / commodities        | yfinance (explicit legacy) | optional IBKR descriptor |
| Forward earnings estimates   | *(excluded)*      | *(capability stub)* |
| Analyst price targets        | *(excluded)*      | *(capability stub)* |

Remaining gaps are tracked in [project-todos.md](project-todos.md).
