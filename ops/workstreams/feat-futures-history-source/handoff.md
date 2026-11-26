# feat/futures-history-source

Created from `staging` at `24b62e7e09b3e0e568818951b8e26a3fbee66952`.

## Human authorization

- Recorded at: 2026-11-26T16:16:21.646424+00:00
- Request: do ALL of these
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: draft; the implementation agent must complete scope, acceptance criteria, tests, and local validation profile before creating a goal.

Update this handoff at each coherent boundary.

# Research: free futures OHLC history (2026-11-26)

## Inventory
- Production has zero instruments of type Future and an empty future_detail table. The 13 "futures" (ESZ6, RTYZ6, FAZ6, DJEZ6, IX?Z6, XARZ6, XASZ6) are Dec-2026 CME contracts that iShares ETF holdings materialized as lightweight Stock-type instruments (field_provenance source ishares); no instrument_provider_symbol rows. They expire in Dec 2026, so they are not durable history targets.
- Code: models/instrument.py FutureDetail (expiry, is_continuous); instrument_sync/instrument_mastering set is_continuous only for Yahoo-style `=F` symbols. ProviderCapability.FUTURES_HISTORY exists (models/provider_runtime.py), registry advertises it only for yfinance and adapters with supports_futures_history (ibkr). _PROVIDER_INSTRUMENT_KINDS allows "future" only for ibkr, yfinance, kraken (spot adapter), openfigi (identifiers only).
- Unrouted adapters: alpaca, massive, alpha_vantage, tiingo, twelve_data, finnhub, eodhd, fmp are equity/crypto-only in their implementations (registry comment says so); none has a free futures endpoint wired. Kraken/Binance adapters are spot only.
- yfinance is gated: legacy-explicit, YFINANCE_PERSISTENT_STORAGE_AUTHORIZED=False because Yahoo terms prohibit automated collection. ibkr needs an account gateway and storage authorization.

## Sources evaluated
- Stooq CSV (stooq.com/q/d/l/?s=es.f&i=d): curl returns a JavaScript proof-of-work challenge page, not CSV (also for aapl.us). Passing it means solving bot detection, which is not allowed; no free automated access path. Rejected.
- CME Group (settlement files / website): the terms page returned 403 with a notice that scripts, robots and scrapers are strictly prohibited by the Data Terms of Use. Rejected.
- Cboe VX futures CSVs (cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_YYYY-MM-DD.csv): reachable without login (HTTP 200, OHLC+settle+volume+OI per contract). But covers only VIX futures, none of the instruments held; per-expiry files (no continuous series); the terms page (cboe.com/about/terms_and_conditions) returned 404 so automated-use permission could not be verified. Not adopted; possible future follow-up only if VX is wanted and Cboe terms are reviewed.
- Yahoo (yfinance): terms forbid automated collection; already gated off in this codebase. Rejected.
- CFTC: positioning reports only, no prices. FRED: spot commodity/index series (e.g. DCOILWTICO), not futures contracts; the fred adapter already exists and is a different asset class.
- Crypto perpetual futures (Kraken Futures, Binance fapi public klines): free public APIs but no such instruments exist in the database and they are not the stated gap.

## Conclusion
No legally usable free source for CME equity-index futures (or continuous front-month) daily OHLC was found. Nothing speculative implemented. Unblock options: an IBKR storage authorization (adapter already supports futures history with a conid mapping), a licensed paid feed (out of scope), or Cboe terms review for VX only.
