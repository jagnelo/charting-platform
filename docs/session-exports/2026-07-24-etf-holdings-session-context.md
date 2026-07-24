# ETF Holdings Session Context Export

Generated on: 2026-07-24

Branch: `feat/etf-holdings-constituents`

This export is intended to be uploaded into another Codex session so that it can resume with the right context. It is not a verbatim full chat transcript because this runtime does not expose a raw transcript export API. It captures the important conversation history, current paused goal, implementation state, validation state, and next concrete work.

## Current Goal

The paused goal is to replace generated or thin ETF provider adapters with full native, per-provider ETF holdings integrations for all `345` registered providers.

Core requirements repeatedly agreed in the conversation:

- SEC EDGAR remains fallback-only and must not count as native provider support.
- Every supported provider needs isolated implementation code, not a generic monolithic route.
- Every supported provider needs deterministic/static tests and opt-in live route tests.
- The system must programmatically assert that every live-backed provider has a concrete live test.
- Higher-priority providers should be those with larger ETF lineups, higher AUM, and greater coverage of the US-listed instrument universe.
- If a provider blocks backend-equivalent access after serious attempts, mark it explicitly as blocked/fallback-only and continue through the remaining providers.

## Current Implementation State

Current code-level count from `ISSUER_ADAPTER_CONFIGS`:

- Registered ETF issuer/provider configs: `345`
- Native/live-backed providers: `288`
- Fallback-only providers: `57`
- Native provider-count coverage: `83.5%`
- `FALLBACK_ISSUER_AUDITS` exists and is intended to exactly match the fallback-only set.

Important caveat: this is not the full goal. The objective is still all `345`.

## Pending Changes Being Committed

The pending code/test work at export time contains:

- Anfield route migration from retired `AEMS` route to current `ADFI` route:
  - Product page: `https://regentsparkfunds.com/our-funds/anfield-dynamic-fixed-income-etf/`
  - Holdings CSV constrained to `/csv/holdings-1031-[...]csv`
  - Product identity validation added.
  - Commodity future/option/swap-like rows classified as non-tradable derivatives rather than cash.
  - `anfield` promoted to `live_tested_default_route=True`.

- Fallback audit manifest:
  - New `IssuerFallbackAudit` dataclass.
  - New `FALLBACK_ISSUER_AUDITS` for all `57` fallback-only identities.
  - Test asserts fallback audit keys exactly equal non-live-backed configs.
  - Purpose: prevent SEC fallback or recognition-only identities being counted as native provider support.

- Tests:
  - Anfield deterministic unit fixture updated for `ADFI`.
  - Anfield opt-in live route added.
  - Fallback audit invariant added.

## Latest Known Validation

Focused validation passed:

- `backend/.venv/bin/pytest backend/tests/unit/services/test_etf_holdings_adapters.py -k 'anfield or recognition_only_adapter_has_an_explicit_source_audit or every_live_backed_adapter_owns_its_fetch_entry_point' --no-cov -q`
- `RUN_LIVE_ETF_HOLDINGS_TESTS=1 backend/.venv/bin/pytest backend/tests/live/test_etf_holdings_live_providers.py -k 'anfield or provider_matrix_covers_every_registered_issuer_adapter or live_backed_providers_each_have_a_concrete_live_route_test' --no-cov -q`
- `backend/.venv/bin/ruff check backend/app/services/etf_holdings_adapters.py backend/tests/live/test_etf_holdings_live_providers.py backend/tests/unit/services/test_etf_holdings_adapters.py`
- `git diff --check`
- `backend/.venv/bin/python -m json.tool ops/state.json >/dev/null`

Latest known full opt-in live matrix after the pending changes:

- Command: `RUN_LIVE_ETF_HOLDINGS_TESTS=1 backend/.venv/bin/pytest backend/tests/live/test_etf_holdings_live_providers.py --no-cov -q`
- Result: `292 passed, 4 failed`

Known current full live failures:

- `liberty_one` / `SPCT`: exact FilePoint POST timed out.
- `rex` / `FEPI`: official product page POST returned `403`.
- `toews` / `HRSK`: product page returned HTTP `500`; retry logic needs to handle transient 5xx or the route must be re-audited.
- `thor`: test assertion is brittle and expects a fixed row/CUSIP at a fixed row index; likely should become a semantic invariant because live holdings changed.

This means the provider registry count can be computed as `288/345`, but the live matrix cannot honestly be described as fully green until those four failures are repaired or correctly reclassified.

## User Preferences And Constraints

The user has repeatedly emphasized:

- Do not claim completion unless the code and tests prove it.
- Do not leave common ETFs broken and call the feature complete.
- Do not use generic SEC fallback as proof of provider support.
- Do not create thin generated adapters that all route through SEC.
- Use provider-specific implementation files/classes/routes in the same spirit as market data providers.
- Static mock tests alone are insufficient for provider routes because issuer websites change; opt-in live tests must exist for supported providers.
- Frontend must match existing platform UX, sizing, colors, and instrument-search behavior.

## Next Concrete Work

1. Repair the four current opt-in live provider failures:
   - LibertyOne timeout handling or source re-audit.
   - REX 403 route repair or source re-audit.
   - Toews 500 retry/source repair.
   - Thor brittle live assertion.

2. Re-run:
   - Focused `liberty or rex or toews or thor` live tests.
   - Full opt-in live provider matrix.

3. Update:
   - `ops/tasks.yaml`
   - `ops/handoff.md`
   - `ops/state.json`
   - `ops/run-report.md`

4. Continue the remaining `57` fallback-only issuers toward native implementations where first-party executable routes can be proven.

