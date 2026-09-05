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

## Provider capability and quota ledger

The table below is the checked-in contract used by `ProviderPolicy` and the
durable `ProviderQuotaWindow` counters. “Unknown” is deliberate; it is not a
placeholder estimate. Limits are for the named plan/scope only and must be
re-reviewed when credentials or billing plans change.

| Provider | Implemented data surface | Credential/config key | Documented usage contract | Reset/scope | Routing status |
|---|---|---|---|---|---|
| Alpaca | US stocks/ETFs + crypto OHLCV, latest, corporate actions, assets | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | 200 historical API calls/min | provider/account window; free IEX feed restriction applies | contract recorded; live evidence required |
| Massive | US ticker search and reference universe | `MASSIVE_API_KEY` (or legacy `MARKETDATA_API_KEY`) | 5 requests/min, Basic Stocks; 2-year history/EOD reference | API key / minute | contract recorded; credentialed live evidence required |
| Alpha Vantage | Daily OHLCV, symbol search, listings, IPO events | `ALPHA_VANTAGE_API_KEY` | 25 requests/day (free key) | API key / provider-defined day | contract recorded; credentialed live evidence required |
| SEC EDGAR | issuer/ticker/exchange directory, profiles, filings/earnings, XBRL facts | `EDGAR_USER_AGENT` | 10 requests/sec total across an IP | IP / rolling fair-access window | contract recorded; keyless live evidence required |
| OpenFIGI | FIGI/ISIN/CUSIP/SEDOL mapping and profile enrichment | optional `OPENFIGI_API_KEY` | 25 requests/min without key (keyed plan has separate 6-sec/100-job contract) | IP or key / rolling | keyless contract recorded; live probe required |
| Binance | public crypto OHLCV, ticker, USDT universe | none | Current Spot REST documentation exposes a 6,000 request-weight/min IP ceiling; endpoint weights are dynamic and returned in headers | IP / fixed minute; 429/418 protection | visible; endpoint-weight reconciliation required before broad routing |
| Coinbase Exchange | public crypto candles, ticker, USD products | none | 10 public requests/sec, burst up to 15 | IP / rolling | contract recorded; keyless live evidence required |
| Kraken | public crypto OHLC, ticker, USD pairs | none | safe public frequency <=1 request/sec; pair/IP limits apply | IP/pair / rolling | contract recorded; keyless live evidence required |
| CoinGecko Demo | crypto search, metadata, market-cap universe | `COINGECKO_API_KEY` | 100 calls/min and 10,000 calls/month | Demo key / minute + calendar month | contract recorded; credentialed live evidence required |
| FINRA | consolidated short interest (OAuth Query API) | `FINRA_CLIENT_ID`, `FINRA_CLIENT_SECRET` | 1,200 synchronous requests/minute/IP; max 5,000 records and 3 MB per synchronous response; 20 asynchronous requests/minute/dataset/account | OAuth client / IP + dataset/account | quota contract recorded; credential/terms/live evidence required |
| FRED | macro/rates/FX daily series | `FRED_API_KEY` | FRED v2 documents up to 2 requests/sec before 429; v1 also reserves the right to adjust limits, so no cross-version contract is assumed | API key / provider-defined | **not routable until the deployed API version's ceiling is verified** |
| Nasdaq Trader | official `nasdaqlisted.txt`/`otherlisted.txt` US NMS listing/lifecycle files | none | No numeric public limit in the symbol-directory definition; poll conservatively and record response headers | public service / unknown | **discovery evidence only; quota unknown** |
| Tiingo | EOD history, search, profiles | `TIINGO_API_KEY` | 500 unique symbols/month, 50/hour, 1,000/day, 1GB/month (free Starter); free terms prohibit durable retention | API key / multiple windows | adapter + contract recorded; free persistence terms block durable routing |
| Twelve Data | multi-timeframe candles, quote, search, US universe | `TWELVE_DATA_API_KEY` | 8 credits/min and 800/day Basic; cost is symbols/endpoint-weighted | API key / minute + day | adapter + credit contract recorded; operation costs must be verified |
| Finnhub | candles, US profile/search, earnings events/universe | `FINNHUB_API_KEY` | Plan limits are dashboard-specific; hard cap 30 req/sec, candle entitlement can be premium | token / plan-specific | **quota unknown; not routable until account evidence** |
| Marketstack | daily EOD history and ticker discovery | `MARKETSTACK_API_KEY` | Current pricing page says 100 requests/month, while an FAQ section still says 1,000; use the lower value only after account confirmation | key / calendar month | **quota ambiguous; not routable until account evidence** |
| EODHD | long-history daily EOD, fundamentals/profile, US exchange list | `EODHD_API_KEY` | Free 20/day and 20/min, one-year history; paid $19.99/month adds 100k/day, 1,000/min, 30+ years | API key / minute + day | contract recorded; credentialed live evidence required |
| FMP | daily history, profile, available-traded list | `FMP_API_KEY` | Current free allowance is account-plan dependent; public repository says up to 250/day but dashboard confirmation is required | key / plan-specific | **quota unknown; not routable** |
| Tradier | US daily history, quotes/search; options-capable REST surface | `TRADIER_API_KEY` | 60/min sandbox; 120/min production market-data quota, response headers expose remaining/reset | token / minute | adapter + contract recorded; account live evidence required |
| MarketData.app | delayed US stocks/options candles (options surface is optional) | `MARKETDATA_APP_API_KEY` | 100 credits/day free, reset 09:30 ET; 50 concurrency; free/trial history limited to one year | key / reset-day + concurrency | adapter + contract recorded; account live evidence required |
| IBKR | account-bound stocks/options/futures/crypto via read-only Web API descriptor | deployment-specific `IBKR_READ_ONLY_URL` | 10 req/sec/session plus endpoint limits; historical max 5 concurrent; market-data subscriptions/account required | session/account / endpoint | descriptor only; no routing until funded-account evidence |
| yfinance | legacy broad fallback, options/futures compatibility only | none | No official quota/SLA; unofficial scraping | unknown | legacy-only and disabled by default |
| ETF holdings internal | platform's issuer/SEC holdings ingestion | internal configuration | Internal job/provider budgets, not an external market-data API | internal | generic bridge only; issuer-specific work remains on ETF branch |

Nasdaq Trader's directory is listing evidence, not a complete delisting-event feed.
The adapter excludes test issues, retains Nasdaq Financial Status Indicators
(including deficient or bankrupt-but-listed issues), and uses repeated complete
absence plus separate lifecycle evidence before marking a listing inactive.
See the [official symbol-directory definitions](https://nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs).

The FRED ceiling note follows the [FRED API v2 error documentation](https://fred.stlouisfed.org/docs/api/fred/v2/errors.html);
FRED's v1 documentation deliberately leaves the operating ceiling adjustable.
Marketstack's pricing/FAQ disagreement is visible in its [pricing page](https://marketstack.com/pricing)
and [FAQ](https://marketstack.com/faq), so the implementation does not select a
numeric contract until the account terms are confirmed.

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
IBKR remains a descriptor because it is account/session-bound. Credentials,
quota, and personal-use/redistribution terms are never inferred from an API
key alone. FINRA now uses its OAuth client flow and has the documented
synchronous quota ceiling recorded; credential, terms, and live evidence are
still required. A provider becomes routable only after the governance record
and live evidence satisfy the contract.

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
exposes a 6,000 request-weight/minute IP ceiling; endpoint weights are
dynamic and must be accounted for from Binance's `exchangeInfo`/response
headers. Repeated 429 violations can produce an HTTP 418 IP ban.

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

**Role**: Periodic consolidated short-interest observations for US securities.
The adapter uses FINRA's `otcMarket/consolidatedShortInterest` Query API dataset
by default, preserves each raw row, and sends the documented `compareFilters`
POST shape. It normalises settlement/publication dates, current short position,
percent float, and days-to-cover values. It does not infer missing values or
treat publication dates as real-time quotes. FINRA's [API platform
documentation](https://developer.finra.org/docs) documents the OAuth flow,
throttling, synchronous record/payload limits, and this dataset. Those limits
are recorded in the provider contract; the adapter still requires an
operator-provisioned OAuth credential and reviewed terms before routing.

**Configuration**: Set `FINRA_CLIENT_ID` and `FINRA_CLIENT_SECRET` in the
ignored `.env.dev`. `FINRA_SHORT_INTEREST_URL` is an optional endpoint override;
otherwise the adapter uses the documented API base and OAuth bearer flow. Do
not put client secrets in commits or chat. The adapter remains non-routable
until the credential preflight, live probe, and current terms review pass.

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
| US equity/ETF universe discovery | alpaca / SEC directory | massive / Nasdaq / alpha_vantage |
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
