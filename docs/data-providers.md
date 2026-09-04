# Data Providers

This document describes every data provider registered with the platform, what data each one
supplies, its priority level per capability, and where to configure its credentials.

---

## Provider Priority Overview

The platform uses a capability-based provider chain.  For each data type the runtime selects the
highest-scoring available provider, falls back to the next, and so on.  Initial priorities below
reflect `base_priority` seeding; the runtime's EWMA health scores refine ordering over time.

| Provider   | Role        | Auth required           | Cost     |
|------------|-------------|-------------------------|----------|
| alpaca     | Primary     | API key + secret        | Free     |
| fred       | Primary     | API key                 | Free     |
| binance    | Primary     | None                    | Free     |
| coingecko  | Primary     | Free demo API key       | Free     |
| edgar      | Primary     | None (User-Agent only)  | Free     |
| yfinance   | Explicit legacy/options fallback only | None (unofficial) | Free, no SLA |
| openfigi   | Supplementary | Optional API key      | Free     |
| massive    | Optional reference corroboration | Optional API key | Free tier / quota |
| alpha_vantage | Optional daily-history corroboration | Optional API key | Free tier / quota |

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

**Rate limits**: 1 200 request-weight/minute.  Each klines call has weight 1.

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
- Rate limit: ~30 requests/minute on free Demo tier.

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

# Pre-existing paid provider slots (not yet implemented)
MARKETDATA_API_KEY=           # MarketData.app — US options with real greeks
FMP_API_KEY=                  # Financial Modeling Prep — fundamentals, forward estimates
```

---

## Provider Chain Defaults

The default provider chain can be overridden per capability via `PROVIDER_CHAIN_SEEDS`
(JSON dict in `.env.dev`). The free-source-first new-workstation baseline is:

```env
PROVIDER_CHAIN_SEEDS={"instrument_search":["edgar","massive","alpha_vantage"],"instrument_metadata":["edgar"],"price_history":["alpaca","alpha_vantage"],"latest_price":["alpaca","alpha_vantage"],"instrument_events":["alpaca","edgar"],"universe_discovery":["alpaca","massive","alpha_vantage"]}
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
| US equity universe discovery | alpaca            | massive / alpha_vantage |
| US splits + dividends        | alpaca            | edgar           |
| Crypto OHLCV                 | binance           | —               |
| Crypto universe discovery    | binance + coingecko | —             |
| Crypto metadata              | coingecko         | —               |
| Interest rates (RFR, yields) | fred              | —               |
| Major forex daily rates      | fred              | —               |
| Macro indicators             | fred              | —               |
| US company profile           | edgar             | —               |
| Historical earnings dates    | edgar             | —               |
| US options chains            | *(excluded)*      | *(capability stub)* |
| Futures / commodities        | *(excluded)*      | *(capability stub)* |
| Forward earnings estimates   | *(excluded)*      | *(capability stub)* |
| Analyst price targets        | *(excluded)*      | *(capability stub)* |

Remaining gaps are tracked in [project-todos.md](project-todos.md).
