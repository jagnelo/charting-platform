# feat/market-data-provider-platform

Created from `staging` at `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`.

## Human authorization

- Recorded at: 2026-09-04T16:12:23.412849+00:00
- Request: Implement the approved US-first multi-provider market-data platform plan: canonical FIGI-based identity and issuer model; exchange/session calendars; market-series scoped raw/canonical OHLCV with local rollups and adjustments; provider capability/entitlement/quota routing; US universe/lifecycle, events, SEC fundamentals, FINRA short interest, current options with local high-fidelity Greeks, optional futures and crypto providers; backend admin/diagnostic APIs; and disabled 30-day shadow monitoring. Backend/data only; do not modify frontend or ETF constituent provider work.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: ready; scope, acceptance criteria, branch tests, and the docker-backed full-integration validation profile are recorded in `plan.yaml`.

## Current implementation boundary

- Phase: implementation and integration validation.
- Delivered in this boundary: additive FIGI/issuer identity, series and session/calendar models, durable quota/routing/refresh queue primitives, SEC facts/FINRA/event records, QuantLib Greeks, and backend diagnostics; concrete opt-in Tiingo/Twelve Data/Finnhub/Marketstack/EODHD/FMP adapters; Nasdaq equity/ETF directory evidence; conservative worker-only US universe lifecycle reconciliation; exchange-aware core D1 coverage snapshots; and migration `4d5e6f708192`.
- CIK is retained as issuer evidence rather than a security key. New symbols without a security-level identifier remain provisional/quarantined instead of being silently merged, while provider symbol/listing history and repeated-missing evidence remain durable.
- Validation: final combined backend unit + PostgreSQL/Redis integration gate passed (`1673 passed`, `80.13%` coverage, requirement `75%`). Focused adapter/lifecycle/monitoring checks also pass (`21/21`); no frontend files were changed.
- Next: human review of the backend-only branch. Operators must separately record reviewed optional-provider entitlements, confirm authoritative US venue feeds, and run the separately approved production/30-day shadow activation; those actions remain disabled and out of scope here.
- The root worktree has unrelated user changes in `docs/etf-provider-universe.md`; they are intentionally preserved and out of scope.
- The workflow session record `ops/workstreams/feat-market-data-provider-platform/session.json` is intentionally updated by session lifecycle commands and may be dirty at checkpoint time.

Update this handoff at each coherent boundary.
