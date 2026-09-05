# Provider live-validation matrix

The live matrix is intentionally separate from normal unit/integration runs:

```sh
RUN_LIVE_PROVIDER_TESTS=1 rtk uv run --project backend python scripts/run-live-provider-probes.py
```

The command performs a preflight, prints every missing environment variable,
runs one bounded read per provider, and returns non-zero when a credentialed
probe is blocked. A missing credential is never reported as a passing skip.
The wrapper returns exit code `2` for an incomplete credential preflight.
Secrets belong in the ignored `backend/.env.dev`; do not put them in Git or
chat. The exact names are in `backend/.env.example` and the provider ledger.

## Evidence captured in this worktree

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

The backend deterministic gates also pass on the preceding corrective revision;
the current live-test-only change has passed its changed-surface checks:

- unit suite: `1320 passed`
- Docker-backed integration suite: `369 passed`
- focused provider quota/routing/runtime tests: `33 passed`
- migration compatibility: passed against the previous release head

The full matrix correctly exposed the remaining credentialed blockers (Alpaca,
Massive, Alpha Vantage, CoinGecko, FRED, FINRA OAuth (short interest and OTC
Daily List), Tiingo, Twelve Data, Finnhub, Marketstack, EODHD, FMP, Tradier,
and MarketData.app). The FINRA OTC DAPI source itself is public and full
pagination is proven above, but it remains non-routable until its terms and
provider-specific quota are reviewed. The credentialed providers remain
non-routable or acceptance-blocked until their keys/terms/plan limits are
supplied and the corresponding probe passes. Binance's endpoint-weight
accounting and Nasdaq Trader's non-numeric polling ceiling remain explicitly
tracked rather than guessed.

With the public SEC User-Agent and official FINRA OTC DAPI URL supplied for the
run, the current full preflight passed `9` public probes and reported `15`
blocked credentialed cases; it returned exit code `2` and makes no acceptance
claim. It names these missing variables exactly:
`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `MASSIVE_API_KEY`,
`ALPHA_VANTAGE_API_KEY`, `COINGECKO_API_KEY`, `FRED_API_KEY`,
`FINRA_CLIENT_ID`, `FINRA_CLIENT_SECRET`, `TIINGO_API_KEY`,
`TWELVE_DATA_API_KEY`, `FINNHUB_API_KEY`, `MARKETSTACK_API_KEY`,
`EODHD_API_KEY`, `FMP_API_KEY`, `TRADIER_API_KEY`, and
`MARKETDATA_APP_API_KEY`. Populate them only in the ignored
`backend/.env.dev`; never paste secret values into the repository or chat.
