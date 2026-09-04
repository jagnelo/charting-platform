# feat/market-data-provider-platform

Created from `staging` at `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`.

## Human authorization

- Recorded at: 2026-09-04T16:12:23.412849+00:00
- Request: Implement the approved US-first multi-provider market-data platform plan: canonical FIGI-based identity and issuer model; exchange/session calendars; market-series scoped raw/canonical OHLCV with local rollups and adjustments; provider capability/entitlement/quota routing; US universe/lifecycle, events, SEC fundamentals, FINRA short interest, current options with local high-fidelity Greeks, optional futures and crypto providers; backend admin/diagnostic APIs; and disabled 30-day shadow monitoring. Backend/data only; do not modify frontend or ETF constituent provider work.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: ready; scope, acceptance criteria, branch tests, and the docker-backed full-integration validation profile are recorded in `plan.yaml`.

## Current implementation boundary

- Phase: identity and market-series foundation.
- Next: synchronize the session record with `make agent-session-start`, then add additive PostgreSQL models/migration and compatibility-safe service tests.
- The root worktree has unrelated user changes in `docs/etf-provider-universe.md`; they are intentionally preserved and out of scope.

Update this handoff at each coherent boundary.
