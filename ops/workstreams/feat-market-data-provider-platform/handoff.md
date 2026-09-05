# feat/market-data-provider-platform

Created from `staging` at `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`.

## Human authorization

- Recorded at: 2026-09-04T16:12:23.412849+00:00
- Request: Implement the approved US-first multi-provider market-data platform plan: canonical FIGI-based identity and issuer model; exchange/session calendars; market-series scoped raw/canonical OHLCV with local rollups and adjustments; provider capability/entitlement/quota routing; US universe/lifecycle, events, SEC fundamentals, FINRA short interest, current options with local high-fidelity Greeks, optional futures and crypto providers; backend admin/diagnostic APIs; and disabled 30-day shadow monitoring. Backend/data only; do not modify frontend or ETF constituent provider work.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: ready; scope, acceptance criteria, branch tests, and the docker-backed full-integration validation profile are recorded in `plan.yaml`.

## Current implementation boundary

- Phase: corrective implementation and integration validation (not ready for review yet).
- Delivered in this boundary: additive FIGI/issuer identity, series and session/calendar models, durable multi-dimensional quota/routing/refresh queue primitives, SEC facts/FINRA/event records, QuantLib Greeks, and backend diagnostics; concrete opt-in Tiingo/Twelve Data/Finnhub/Marketstack/EODHD/FMP/Tradier/MarketData.app/Coinbase/Kraken adapters; official Nasdaq Trader directory ingestion; conservative worker-only US universe lifecycle reconciliation; exchange-aware core D1 coverage snapshots; and the explicit-quota migration `ff5a6b7c8d9e`.
- CIK is retained as issuer evidence rather than a security key. New symbols without a security-level identifier remain provisional/quarantined instead of being silently merged, while provider symbol/listing history and repeated-missing evidence remain durable.
- Provider resolution treats blank or `unreviewed` entitlement plans as non-routable even when paid-provider routing is enabled; the paid switch only admits explicitly reviewed plans.
- Provider resolution also requires a documentation-backed quota contract. Generic 60/minute, 15-burst, 2-concurrency, and 30-second cooldown values have been removed; unknown dimensions remain NULL/unknown and are excluded from routing. Durable reservations now track each provider budget dimension and calendar/reset semantics.
- 429/418/quota responses are typed, reset-aware, circuit-opening capacity failures. HTTP OHLCV routes expose 503 plus `Retry-After`/provider metadata instead of presenting capacity exhaustion as “no data”.
- Optional REST adapters no longer turn missing credentials or upstream HTTP failures into a false empty success; missing configuration is explicit and rate-limit responses remain observable by the runtime.
- Coordination note: `feat/etf-holdings-constituents` is developing in parallel and may provide overlapping ETF identity/discovery evidence. This branch preserves ETF adapter ownership there; any overlap should be reconciled at integration through the canonical identity contract.
- Validation: the corrective backend unit suite passes `1314/1314`, and the Docker-backed backend integration suite passes `369/369` (2026-09-05). The focused quota/routing/runtime suite passes `28/28`; all 15 checked-in quota seeds validate complete reset/limit/unit/scope/source evidence, including FINRA's documented synchronous ceiling; migration compatibility passed against the previous release head; Ruff is clean for the changed provider/runtime surface. The latest network-enabled bounded keyless live matrix passes `6/6` (OpenFIGI, SEC EDGAR with a real contact User-Agent, Nasdaq Trader, Binance, Coinbase, and Kraken), and the standalone OpenFIGI probe passes `1/1` after its anonymous window reset. An intermediate rerun received an honest OpenFIGI HTTP 429 after additional anonymous traffic; that transient provider-rate-limit result is retained as operational evidence, not hidden. The full credentialed matrix is intentionally not claimed as passed: its preflight reports the exact missing variables, returns exit code `2`, and those providers remain non-routable until an operator configures and executes them.
- Next: populate the ignored `backend/.env.dev` values, execute every credentialed live probe, resolve any provider-specific failures or quota-contract evidence gaps, and run the complete production NMS/OTC reconciliation. The NMS/SEC directory adapters and bounded keyless evidence are already implemented; OTC still needs an operator-approved source with documented terms and quota. Only then may this workstream move to `ready_for_human_review`; deployment and the separately approved 30-day shadow activation remain out of scope.
- The root worktree has unrelated user changes in `docs/etf-provider-universe.md`; they are intentionally preserved and out of scope.
- The workflow session record `ops/workstreams/feat-market-data-provider-platform/session.json` is intentionally updated by session lifecycle commands and may be dirty at checkpoint time.

Update this handoff at each coherent boundary.
