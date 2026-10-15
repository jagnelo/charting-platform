# Provider integration checkpoint review packet

Status: preparation only; human checkpoint acceptance is pending. This packet
does not authorize a merge, provider activation, deployment, paid routing, or
the 30-day operational trial. The full original roadmap remains open.

## Evidence boundary

- Current branch source: `1afb89658d1d84e801069e1f19d7ee4f985c7e1e`.
- The provider-live run on that exact source (`186ab98a-6971-4a3f-affd-d0a2d8286106`, 2026-10-15 20:56Z) tested 20/27 provider manifests: 56 cases passed, zero failed/skipped, 136 HTTP requests and 55,732,001 response bytes. It is `incomplete_preflight`, not all-provider acceptance. Twenty durable quota-ledger receipts were recorded. The live harness requires captured response-body count to match measured HTTP responses; archive errors fail the operation, and archive writes are redacted, owner-private, flushed and fsynced. Payloads are kept outside Git; no payloads or secrets enter this packet.
- The receipt does not include a per-run response-archive row count. I did not scan the multi-gigabyte private archive; therefore retention evidence here is the per-operation harness check and absence of archive-failure dispositions, not an independent archive-wide audit.
- Seven manifests were quarantined before transport: Alpha Vantage, CTA Plan, Dinari, EODHD, Marketstack, Nasdaq, Tiingo. The precise operation holds are below. Do not spend calls or infer success from prior-source receipts.
- Workflow fix `1ab6f79868a736535143ad8a50a649a3afacd36b` has green CI `38798881420`, including backend, branch-declared migration check, and Playwright (151 passed, 109 expected skips). Current-source CI `38804214507` has Backend Tests and Branch-declared Tests green; E2E Playwright is still running. Thus the current source does not yet have a complete green CI result, and the green `1ab6` result is historical evidence for an ancestor.
- The coordinator-owned browser repair remains outside this worktree. Await its exact green staging result before any staging-to-feature reconciliation. No frontend files were changed here.

## ICP1–ICP7 disposition

| Gate | Evidence and present disposition | Remaining acceptance work |
|---|---|---|
| ICP1 — identity and lifecycle | Stable instrument/issuer/listing/provider-symbol models, FIGI resolution, provenance and quarantine are implemented. `test_openfigi.py`, `test_instrument_sync_metadata.py`, and PostgreSQL-backed `test_market_universe_reconciliation.py` are the checkpoint tests named in `plan.yaml` under ICP1; current-source backend CI passes. Prior complete CTA + Nasdaq equity/ETF and FINRA OTC snapshots are historical source evidence, not a fresh current-source universe receipt. | Reconcile a fresh, same-session complete NMS union plus complete OTC/SEC lifecycle evidence on the accepted source; retain every source row and cursor, and verify ticker-change/delisting handling. |
| ICP2 — shared provider governance | Capability/entitlement/routing and durable, multi-dimensional quota coordinator contracts are exercised by `test_provider_quota_coordinator.py`, `test_provider_quota_contract.py`, `test_provider_routing.py`, and `test_provider_runtime.py`. `PROVIDER_FREE_ONLY_CHECKPOINT=true` is a shared route constraint that overrides `ALLOW_PAID_PROVIDER_ROUTING`: paid plans are denied even when the paid flag is true; trials and unreviewed plans are always denied. `provider_entitlement_admission()` returns the decision, and `list_provider_status()` exposes it as `entitlement_admission`. Disabling checkpoint mode deliberately restores the full-roadmap paid opt-in path. The exact dirty source passed the full Docker-backed backend gate: 2,772 unit + 395 integration tests, 82% combined coverage. | Shared aggregate admission for the approved 20 EUR/USD-equivalent recurring ceiling does not exist; the free-only boundary is not a monthly budget. Provider owns that ICP2 contract; ETF owns its ICP6 bridge wiring and actual request/page/retry accounting after green Provider staging. Do not invent FX or add an ETF ledger. No paid activation is authorized. Exact-source hosted CI and browser gate remain to be refreshed after publication. |
| ICP3 — series, coverage and refresh | Scoped series/provenance, gap planning, session-aware freshness, refresh coalescing/leases and explicit partial coverage have tests in `test_market_data.py`, `test_exchange_catalog.py`, `test_arq_worker.py`, and `test_market_data_admin.py`; current-source backend CI passes. Strategy Lab integration exercises successful local-data evaluation and full/partial coverage previews. | Refresh current-source full-stack evidence after staging reconciliation; ensure each downstream consumer continues to distinguish stale, partial, missing and unavailable data without hidden provider calls. |
| ICP4 — provider operations | Exact-source live suite is 20/27 and 56/56 cases; operation-level observations and expected-denial/no-transport dispositions are in the exact-source receipt in `validation.jsonl`. | Close or preserve the seven quota/contract holds and remaining safe-disabled operations below. Re-run only after fresh provider-specific admission; historical evidence is not rebound to new source. |
| ICP5 — migrations, startup and secrets | Ancestor CI passed 50 changed migration checks, fresh-install/existing-database quota schema/data equivalence, previous-release health 200, and the backend/E2E jobs. Secret-wiring and RPi contract tests exist. | Obtain terminal green CI for exact `1afb896`; after coordinator staging is green, reconcile and rerun exact-source full validation. Separately verify GitHub CI, RPi, and deployment secret stores; no secret-store readiness is inferred from code tests. |
| ICP6 — consumers | The map and success/unavailable payload examples are in `plan.yaml`. ETF needs canonical identity + entitlement/quota/health/availability; ETF still owns the holdings bridge and its request/page/retry accounting. Existing API tests show a refreshed benchmark-family leg alongside an unavailable unmapped leg (`test_admin_can_refresh_selected_benchmark_family_legs_for_date`) and full/none/missing holdings coverage (`test_coverage_summary_reports_missing_partial_and_full_ranges`) in `backend/tests/integration/api/test_etf_holdings.py`. TC2000 needs canonical identity + local OHLCV + coverage/freshness/missing state; this branch has shared backend API/coverage tests, but no TC2000-consumer-specific test. Strategy Lab has a successful local-data run (`test_create_list_version_and_run_strategy`) and a mixed full/partial coverage preview (`test_preview_strategy_coverage_summarizes_universe_and_benchmark`) in `backend/tests/integration/api/test_strategy_lab.py`. Admin quota/availability tests are in `backend/tests/integration/api/test_market_data_admin.py` and `backend/tests/unit/routers/test_providers_router.py`. | ETF bridge contract: call `app.services.provider_runtime.execute_provider_call(db, capability, operation, *, provider_name, operation_cost_overrides, invoke, ...)` for shared admission plus quota reservation; `invoke` is not called when admission denies. For read-only decisions use `provider_entitlement_admission(entitlement)`, whose stable fields are `allowed`, `reason_code`, `configured_plan`, `is_free`, `checkpoint_free_only`, and `basis`. Reason codes: `reviewed_free_plan`, `checkpoint_free_only`, `trial_cost_not_admissible`, `entitlement_unreviewed`, `paid_routing_disabled`, and `reviewed_paid_opt_in`. `list_provider_status()` exposes the same decision under `entitlement_admission`. This evaluates plan-routing eligibility only, not aggregate subscription cost. ETF owns adapter wiring and actual request/page/retry accounting plus consumer-level no-transport tests after green Provider staging. These tests do not prove downstream final branch behavior or the monthly cost ceiling. |
| ICP7 — reviewable source | The source is published and has exact-source live/admission evidence; the workstream preserves all 23 original criteria and their individual owner/continuation disposition in `plan.yaml`. | Current worktree is dirty with this packet and an append-only validation-journal update; exact `1afb896` CI has Backend and Branch-declared jobs green, while E2E Playwright remains in progress. After coordinator staging is green, reconcile/revalidate, publish a clean pushed exact-source packet, complete every disposition and only then request human checkpoint acceptance. |

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
| Paid plans and production Dinari | No activation. `ALLOW_PAID_PROVIDER_ROUTING=false` keeps reviewed paid routes excluded for this checkpoint; aggregate recurring-cost admission is still absent. |

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
3. Retain the seven held provider operations until their exact admission facts
   permit safe calls, or present a precise disabled/deferred disposition for
   human checkpoint acceptance. No retries of held slices merely to refresh
   evidence.
4. The shared checkpoint free-only route constraint is implemented. Aggregate
   recurring-cost admission is still open; keep paid activation disabled until
   the 20 EUR/USD-equivalent shared contract is implemented and reviewed. ETF
   bridge wiring and consumer accounting remain ETF-owned and wait for green
   Provider staging.
5. Verify environment-specific GitHub, RPi and deployment secret stores;
   complete downstream consumer reconciliations; keep the 30-day shadow trial
   deferred until separately authorized after integration.
6. Produce a clean pushed exact-source packet and request concrete human
   acceptance. The coordinator owns staging integration; this packet is not
   closure, merge authorization, deployment approval, or full-roadmap completion.
