# Provider integration checkpoint review packet

Status: preparation only; human checkpoint acceptance is pending. This packet
does not authorize a merge, provider activation, deployment, paid routing, or
the 30-day operational trial. The full original roadmap remains open.

## Evidence boundary

- Current pushed code commit: `4077f07213ce4c7989bed88ffdd2ad91545915aa`.
- The provider-live run is still bound only to its exact source `1afb89658d1d84e801069e1f19d7ee4f985c7e1e` (`186ab98a-6971-4a3f-affd-d0a2d8286106`, 2026-10-15 20:56Z): 20/27 provider manifests, 56 cases passed, zero failed/skipped, 136 HTTP requests and 55,732,001 response bytes. It is `incomplete_preflight`, not all-provider acceptance. Twenty durable quota-ledger receipts were recorded. No live evidence is rebound to `4077f07`.
- The receipt does not include a per-run response-archive row count. I did not scan the multi-gigabyte private archive; therefore retention evidence here is the per-operation harness check and absence of archive-failure dispositions, not an independent archive-wide audit.
- Seven manifests were quarantined before transport: Alpha Vantage, CTA Plan, Dinari, EODHD, Marketstack, Nasdaq, Tiingo. The precise operation holds are below. Do not spend calls or infer success from prior-source receipts.
- Ancestor CI `38798881420` for `1ab6f798` is green (backend, branch-declared migration check, and Playwright: 151 passed, 109 expected skips). For pushed commit `4077f07`, GitHub currently reports no commit status checks; exact-source hosted CI is pending/not evidenced. Local Docker backend gate passed 2,772 unit + 395 integration tests (82% combined coverage) before a final small unreviewed-plan predicate hardening; that final predicate passed the focused regression. Neither result substitutes for current hosted CI.
- The coordinator-owned browser repair remains outside this worktree. Await its exact green staging result before any staging-to-feature reconciliation. No frontend files were changed here.

## ICP1–ICP7 disposition

| Gate | Evidence and present disposition | Remaining acceptance work |
|---|---|---|
| ICP1 — identity and lifecycle | Checkpoint minimum: tested stable instrument/issuer/listing/provider-symbol identity, provenance/history retention and ambiguity quarantine, plus legacy symbol/API compatibility. Relevant tests include `backend/tests/unit/providers/test_openfigi.py`, `backend/tests/unit/services/test_instrument_sync_metadata.py`, `backend/tests/unit/services/test_market_data_identity.py`, provider-symbol lifecycle/quarantine migrations, and existing-instrument/API compatibility tests. Known venue and universe mapping gaps must be listed honestly. | No fresh full-market snapshot is a pre-integration ICP1 requirement. Full, same-session NMS/OTC/SEC reconciliation, ticker-change/delisting completeness and venue mapping remain full-roadmap work; partial/stale source evidence must never be treated as complete or used to claim absence. |
| ICP2 — shared provider governance | Capability/entitlement/routing and durable, multi-dimensional quota coordinator contracts are exercised by `test_provider_quota_coordinator.py`, `test_provider_quota_contract.py`, `test_provider_routing.py`, and `test_provider_runtime.py`. `PROVIDER_FREE_ONLY_CHECKPOINT=true` is a shared route constraint that overrides `ALLOW_PAID_PROVIDER_ROUTING`: paid plans are denied even when the paid flag is true; trials and unreviewed plans are always denied. `provider_entitlement_admission()` returns the decision, and `list_provider_status()` exposes it as `entitlement_admission`. Disabling checkpoint mode deliberately restores the full-roadmap paid opt-in path. Docker backend gate passed 2,772 unit + 395 integration tests before the final unreviewed-plan predicate hardening; the final predicate has a focused regression pass. | Shared aggregate admission for the approved 20 EUR/USD-equivalent recurring ceiling does not exist; it is not needed to prove this free-only checkpoint boundary. Provider owns that aggregate ICP2 contract as roadmap work; ETF owns its ICP6 bridge wiring and actual request/page/retry accounting after green Provider staging. Do not invent FX or add an ETF ledger. No paid activation is authorized. Current exact-source hosted CI remains unverified. |
| ICP3 — series, coverage and refresh | Scoped series/provenance, gap planning, session-aware freshness, refresh coalescing/leases and explicit partial coverage have tests in `test_market_data.py`, `test_exchange_catalog.py`, `test_arq_worker.py`, and `test_market_data_admin.py`; current-source backend CI passes. Strategy Lab integration exercises successful local-data evaluation and full/partial coverage previews. | Refresh current-source full-stack evidence after staging reconciliation; ensure each downstream consumer continues to distinguish stale, partial, missing and unavailable data without hidden provider calls. |
| ICP4 — provider operations | The latest retained live receipt is bound only to `1afb89658d1d84e801069e1f19d7ee4f985c7e1e`: 20/27 manifests, 56/56 cases, 136 requests, and 55,732,001 response bytes. Its operation-level outcomes are in `validation.jsonl`; it is not exact evidence for `4077f07`. Seven slices remain safely uncalled/held as detailed below. | Keep quota/contract-held slices non-routable; do not spend quota merely to refresh evidence or relabel the old receipt. If a held slice is required for checkpoint acceptance, its exact exclusion needs a concrete human disposition. The current live matrix remains explicitly incomplete; no freshness or receipt rebinding is claimed. |
| ICP5 — migrations, startup and secrets | Checkpoint minimum: additive migrations, fresh/existing DB equivalence, startup/default compatibility, tested local secret/config boundary, and exact-source branch CI. Tests include `test_local_and_rpi_compose_pass_secrets_only_to_trusted_provider_processes`, provider configuration wiring, and the secret-free live workflow contract. The 50-migration fresh/upgrade equivalence and prior-release health check are historical dirty-candidate evidence, not bound to `4077f07`. | Obtain current exact-source hosted CI and source-bound migration-equivalence evidence where required by the branch gate. GitHub/RPi/deployment secret-store verification is target onboarding/deployment readiness, required before using those targets, not before Provider integration. No deployment readiness is claimed. |
| ICP6 — consumers | Producer-side success/unavailable behavior is exercised by shared identity, coverage, provider status, quota, and route-admission tests. Consumer-facing examples include ETF `test_coverage_summary_reports_missing_partial_and_full_ranges` and Strategy `test_create_list_version_and_run_strategy` / `test_preview_strategy_coverage_summarizes_universe_and_benchmark`. There is no TC2000-specific consumer test in this branch. Ownership/remainder is listed in `plan.yaml`: ETF owns holdings adapter/bridge and request/page/retry accounting; TC2000 owns consumer use; Strategy Lab owns its consumer integration. | Pre-integration minimum is the usable producer contract, actual tested success/unavailable examples, and named downstream owner/remainder—not sibling wiring. Actual ETF/TC2000/Strategy reconciliation and consumer-specific tests happen after Provider is green in staging. ETF shared-call contract: `app.services.provider_runtime.execute_provider_call(db, capability, operation, *, provider_name, operation_cost_overrides, invoke, ...)`; denial prevents `invoke`. Read-only decision callable: `provider_entitlement_admission(entitlement)` returns `allowed`, `reason_code`, `configured_plan`, `is_free`, `checkpoint_free_only`, `basis`; `list_provider_status()` exposes it as `entitlement_admission`. This is routing eligibility, not aggregate subscription cost. |
| ICP7 — reviewable source | Commit `4077f07` is pushed; all 23 original criteria and their owner/continuation dispositions remain in `plan.yaml`. Exact-source current hosted CI has no reported status checks yet. The only provider-live receipt remains the incomplete 20/27 receipt on `1afb896`; it is not rebound to current source. | Complete the applicable exact-source validation/CI and coordinator staging reconciliation, then publish a clean pushed packet for concrete human checkpoint acceptance. Neither historical green ancestor CI nor local tests establish current-source CI. |

## Current operation dispositions

Called and observed on exact `1afb896`: Alpaca, Binance, Bybit xStocks, Coinbase,
CoinGecko, SEC EDGAR, Finnhub, FINRA short-interest/events, FINRA OTC directory,
FMP, FRED, Gate TradFi, Kraken, Kraken xStocks, MarketData.app, Massive,
OpenFIGI, Robinhood tokens, Twelve Data, and xStocks. Every recorded operation
in those manifests passed its transport/schema assertion except the expected
entitlement-denial cases called out below. MarketData.app's current/options
probe operations were exercised, but that does not complete the broader
options/Greeks roadmap criterion.

| Operation or provider slice | Safe disposition and reason |
|---|---|
| `alpha_vantage/discover_universe_page` | Held before HTTP: daily headroom below the full 9-call reservation. |
| `cta_plan/discover_universe_page` | Held before HTTP: two daily directory units unavailable for this run. |
| `eodhd/discover_universe_page` | Held before HTTP: daily headroom below the 16-call reservation. |
| `nasdaq/discover_universe_page` | Held before HTTP: two daily directory units unavailable for this run. |
| Dinari Sandbox normal operations (`discover_tokenized_assets`, `fetch_tokenized_corporate_actions`, `fetch_tokenized_dividends`, `fetch_tokenized_historical_prices`, `fetch_tokenized_news`, `fetch_tokenized_splits`, `get_tokenized_asset`, `get_tokenized_price`, `get_tokenized_quote`) | Held/non-routable: account-reviewed reset/quota and worst-case operation-cost profile is absent. No assumption of a published Sandbox cap. |
| `marketstack/fetch_ohlcv` and `get_current_price` | Held before HTTP: monthly headroom does not cover the reserved calls; owner reported monthly allowance exhausted. |
| `marketstack/discover_universe_page` | Held/non-routable: exchange MIC and page cost remain unresolved; no pagination call is made. |
| Tiingo `fetch_ohlcv`, `get_current_price`, `get_instrument_profile`, `search_instruments` | Held before HTTP: current rolling-hour usage baseline is unknown. |
| `coingecko/fetch_account_usage` | Called and classified as expected entitlement denial: Demo key cannot use the Pro-only `/key` endpoint; quota accounting remains local/durable. |
| `finnhub/fetch_ohlcv` | Called and classified as expected entitlement denial: configured free key returned HTTP 403 for stock candles. |
| `fmp/discover_universe_page` | Called and classified as expected entitlement denial: Basic key returned HTTP 402 for `stable/stock-list`; keep universe discovery disabled pending confirmed entitlement. |
| Bybit xStocks restricted-egress route | A provider-level no-request safety disposition remains recorded while deployment-egress evidence is unresolved. Other explicitly listed tokenized metadata/price operations did receive bounded probes; neither fact is a blanket pass for the restricted route. |
| FINRA `submit_async_dataset`, `poll_async_dataset`, `download_async_result` | Generic transport legs were not invoked by an admitted dataset service. Async result download remains non-routable until streamed durable persistence and measured-byte admission can safely retain the complete result; never truncate or discard rows. |
| Tradier, IBKR, Ondo | Explicit user deferrals; keep non-routable. They are not counted as passed providers. |
| Paid plans and production Dinari | No activation. `PROVIDER_FREE_ONLY_CHECKPOINT=true` denies reviewed paid routes regardless of `ALLOW_PAID_PROVIDER_ROUTING`; trials and unreviewed plans are denied. Aggregate recurring-cost admission is not part of this free-only checkpoint and remains roadmap work. |

The live harness archived successful operation payloads to the owner-private
archive outside the repository and recorded quota usage in the durable shared
coordinator. No ledger or archive was reset, deleted, or copied into Git for
this packet. See the evidence boundary above for the limit of the archive
verification performed here.

## Coordinator and acceptance gates still open

1. Wait for the exact coordinator browser-repair staging gate to turn green; do
   not import its frontend changes here. Then reconcile the green staging base
   into this branch and revalidate this exact combined source.
2. Obtain terminal current-source branch CI and required full profile after that
   reconciliation; current green ancestor CI does not satisfy this.
3. Keep the seven held provider operations non-routable unless exact admission
   facts permit a safe test. The retained receipt is 20/27 on source `1afb896`,
   with 136 requests; it remains incomplete and is not current-source evidence.
   Do not fabricate freshness or rebind it. If any held operation is asserted
   to be required for this checkpoint, obtain a concrete human disposition for
   that operation; temporary quota holds are not silently treated as accepted
   permanent deferrals.
4. The shared hard free-only route constraint is implemented in commit
   `4077f07` and tested against both paid-toggle states with zero transport.
   No aggregate-budget subsystem is required for this free-only checkpoint;
   the 20 EUR/USD-equivalent ceiling remains full-roadmap Provider work and paid
   activation stays disabled.
5. Checkpoint ICP5 requires the tested local secret boundary/config only.
   Environment-specific GitHub/RPi/deployment secret stores, full-universe
   reconciliation, and actual downstream branch wiring are post-integration
   roadmap gates. After Provider is green in staging, downstream owners perform
   and validate their reconciliation. The 30-day shadow trial remains deferred
   until separately authorized.
6. Produce a clean pushed exact-source packet and request concrete human
   acceptance. The coordinator owns staging integration; this packet is not
   closure, merge authorization, deployment approval, or full-roadmap completion.
