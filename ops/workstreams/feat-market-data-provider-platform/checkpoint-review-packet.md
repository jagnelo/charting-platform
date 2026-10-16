# Provider integration checkpoint review packet

Status: preparation only; concrete human checkpoint acceptance is pending. This
packet does not authorize provider activation, paid routing, deployment, the
30-day operational trial, or staging integration. The complete roadmap remains
open.

The human's conditional checkpoint-acceptance delegation (timestamp supplied
as `22:55Z`) is recorded in `plan.yaml` and `handoff.md`: “Yes—approve that
initial scope and handle checkpoint acceptance.” The coordinator may accept
and merge the four checkpoints only after required cross-feature contracts and
full tests pass, using verified free operations and keeping held, unreviewed,
paid/trial and unsafe operations disabled. This is not acceptance of this exact
source and does not waive validation, authorize this feature agent to
integrate, permit deployment/paid/trial activation, or allow cleanup.

## Exact-source evidence boundary

- Current branch HEAD is clean, pushed `b09ebb1f3bd68ad7a0fbdcf14a779d10d9737841`.
  It includes released common-repair staging `82d881e76be8de538abb6ec5c454d96afe0ee56a`
  through merge `2845817d37296fae8728d72cd22a95082d67081f`. This is common
  repair only; no Provider feature acceptance is implied. No Provider-owned
  frontend files changed.
- Exact-source local Docker backend coverage passed 2,775 unit tests in 56
  shards and 395 PostgreSQL/Redis integration tests, with 82% combined
  coverage. The account-usage/secret-wiring suite passed 104/104. Ruff,
  formatting, diff checks, and branch workstream validation passed.
- Exact-source GitHub run `38832540358` for `b09ebb1` has Backend Tests,
  Frontend Unit Tests, Playwright E2E, and Branch-declared Tests green.
  Exhaustive Integration Gate was skipped because this was a feature-branch
  push, so this hosted run is not the staging exhaustive gate.
- The local `make validate-integration` attempt passed workstream validation,
  dependency/lock checks and the migration-head check; migration compatibility
  correctly reported no migration changes relative to `2845817`. It stopped
  at `npm ci`: esbuild's version check returned success but the sandbox denied
  its child process with `EPERM`. A privileged retry of the whole target was
  rejected because a later target stage runs credentialed provider probes and
  can consume shared quota. No local provider probe ran. This full local profile
  is therefore not green.
- Published commit `b09ebb1` also contains the already-completed broad Ruff
  formatting normalization (73 files identified by the formatter check)
  alongside the account-usage fix/tests. This formatting context is classified
  as complete and published; its history will not be rewritten. This
  continuation adds no broad formatting edits.
- A no-transport preflight on exact source `b09ebb1` evaluated 27 providers,
  admitted 21 and quarantined six: Alpha Vantage, CTA Plan, Dinari, Marketstack,
  Nasdaq, and Tiingo. It sent zero provider requests. EODHD is not quarantined.
  Specific current holds are listed below. This preflight is not live acceptance.
- The latest retained provider-live receipt remains bound only to
  `1afb89658d1d84e801069e1f19d7ee4f985c7e1e`
  (`186ab98a-6971-4a3f-affd-d0a2d8286106`, 2026-10-15 20:56Z): 20/27 manifests,
  56 cases passed, zero failed/skipped, 136 HTTP requests and 55,732,001
  response bytes. It is incomplete and not evidence for this source. Twenty
  durable quota-ledger receipts were recorded. No receipt was rebound.
- The historical live receipt has no per-run response-archive row count. No
  full scan of the multi-gigabyte private archive was done; retention evidence
  is the operation-level harness check and lack of archive-failure
  dispositions, not an independent archive-wide audit. Payloads and the
  shared quota ledger remain outside Git; nothing was reset, deleted or copied
  into the repository.

## ICP1–ICP7 checkpoint disposition

| Gate | Evidence / delivered checkpoint contract | Remaining work and owner |
|---|---|---|
| ICP1 — identity and lifecycle | Tests cover stable instrument/issuer/listing/provider-symbol identity, provenance and history, ambiguity quarantine, and legacy symbol/API compatibility. See OpenFIGI, instrument-sync, market-data-identity, lifecycle/quarantine migration, and compatibility tests. | Full same-session NMS/OTC/SEC universe reconciliation, all venue mappings, and complete ticker-change/delisting lifecycle remain Provider roadmap work. Partial or stale snapshots must never imply absence or completeness. |
| ICP2 — provider governance | Shared capability, entitlement, routing and durable multidimensional quota contracts are tested. `PROVIDER_FREE_ONLY_CHECKPOINT=true` denies reviewed paid market-data routes regardless of `ALLOW_PAID_PROVIDER_ROUTING`; trials are denied. Unreviewed market-data routes are denied except the exact reviewed-safe EODHD `/api/user` bootstrap: HTTPS evidence, exact `fetch_account_usage` operation, reconciled `calls_per_day`, explicit zero daily-credit operation cost; `requests_per_minute` is still reserved. Candidate selection exposes only this operation to strict admission. Positive stubbed execution uses a genuinely unreviewed `is_free=false` entitlement under both paid-toggle states. Paid, unknown, unknown-plan, and trial negatives prove zero callback execution under both toggle states, including known and bootstrap-unknown quota states. MarketData.app `/user/` is not exempt. Relevant suite: 104/104; exact-source backend CI is green. | The aggregate 20 EUR/USD-equivalent recurring-cost ceiling is not implemented; it remains Provider roadmap work and is not needed for this free-only checkpoint. ETF owns its consumer bridge and real request/page/retry accounting after Provider staging. No invented FX or ETF-only ledger. |
| ICP3 — series, coverage and refresh | Series/provenance, gap planning, session-aware freshness, refresh coalescing/leases, and explicit partial coverage are exercised by backend unit/integration and Strategy Lab tests. Full local backend gate and exact-source hosted backend job passed. | After Provider staging, consumers verify stale, partial, missing, and unavailable states remain distinct and do not trigger hidden provider requests. Downstream owners: ETF, TC2000, Strategy Lab. |
| ICP4 — provider operations | Current exact-source preflight admits 21 providers and quarantines six before transport; zero HTTP requests. Historical live evidence remains precisely source-bound and incomplete (20/27, 136 requests); it is not relabeled as current evidence. | Keep held operations non-routable. No quota spend merely to refresh evidence. If an excluded/held operation is required for this checkpoint, obtain a human disposition for that exact operation; a temporary quota shortage is not silently accepted as permanent deferral. |
| ICP5 — migrations, startup and secrets | Local secret/config boundary and trusted backend/worker wiring have tests. Reported 50-migration fresh-install/existing-database equivalence and prior-release health check are historical dirty-candidate evidence, not a clean receipt bound to `b09ebb1`. Exact-source backend and branch-declared CI jobs are green; hosted Playwright remains pending. | Rebind migration equivalence if the branch gate requires final-source proof. GitHub/RPi/deployment secret stores are target onboarding requirements before those targets are used, not pre-Provider integration requirements. No deployment readiness is claimed. |
| ICP6 — consumers | Producer success/unavailable behavior and callable contract are tested. ETF can call `app.services.provider_runtime.execute_provider_call(db, capability, operation, *, provider_name, operation_cost_overrides, invoke, ...)`; denied admission prevents `invoke`. `provider_entitlement_admission(entitlement)` returns `allowed`, `reason_code`, `configured_plan`, `is_free`, `checkpoint_free_only`, and `basis`; provider status exposes this as `entitlement_admission`. This is routing eligibility, not aggregate subscription-cost admission. Success/unavailable examples exist in ETF coverage and Strategy evaluation/coverage tests. | Before Provider staging, deliver the producer contract and named owners only; actual ETF/TC2000/Strategy adapter wiring and consumer-specific reconciliation happen after Provider is green in staging. ETF owns holdings adapter/bridge plus page/retry accounting; TC2000 and Strategy own their consumer wiring. |
| ICP7 — reviewable source | Clean pushed branch `b09ebb1` contains the released common-repair baseline. Original criteria and owner/continuation dispositions remain in `plan.yaml`. All applicable jobs in exact-source CI run `38832540358`, including Playwright E2E, passed; the staging-only exhaustive job was skipped on feature push. | Complete the required local full integration profile, then request human checkpoint acceptance. This packet is not closure or integration authorization. |

## Current operation holds

All six were blocked before provider transport by the exact-source `b09ebb1`
preflight; the run made zero requests:

| Provider / operation area | Current safe disposition |
|---|---|
| Alpha Vantage universe discovery | Held: current daily headroom is below the 9-request full-matrix reservation. |
| CTA Plan directory | Held: two daily directory units are unavailable for the matrix reservation. |
| Nasdaq directory | Held: two daily directory units are unavailable for the matrix reservation. |
| Dinari Sandbox tokenized operations | Non-routable: account-reviewed quota/reset semantics and worst-case operation-cost profile are missing. No undocumented Sandbox quota is assumed. |
| Marketstack OHLCV and directory | OHLCV held: monthly headroom is below the two-call reservation. Directory remains non-routable: MIC, page cost and operation cost are unresolved. |
| Tiingo OHLCV, price, profile and search | Held: current rolling-hour usage baseline is unknown. |

These are present operational holds, not accepted permanent omissions. Other
historical operation outcomes remain in `validation.jsonl` bound to their exact
source. For context: CoinGecko Demo `/key`, Finnhub free stock candles, and FMP
Basic `stable/stock-list` returned expected entitlement denials during their
historical probes. Tradier, IBKR and Ondo remain explicit user deferrals. FINRA
async result download remains unavailable until complete streamed persistence
and measured-byte admission are proven; rows must never be truncated or
discarded. No provider has been activated or routed through paid credentials.

## Next gates

1. Commit the recorded conditional-acceptance direction, hold source changes,
   then run the full local profile once. Its provider-probe stage may use only
   verified free operations that pass provider-specific quota admission; keep
   held, unreviewed, paid/trial and unsafe operations disabled. The earlier
   attempt stopped at sandbox `EPERM` before provider probes and made no
   provider requests.
2. Preserve the six current quota/contract holds. Do not call them or change
   admission policy without fresh exact admission facts. Do not alter the
   historical live receipt or spend held quota for cosmetic freshness.
3. After validation is terminal, refresh the clean exact-source packet for
   coordinator review. Conditional checkpoint-acceptance authority is delegated
   to the coordinator, but this source is not yet accepted. Staging integration
   remains coordinator-owned and still requires terminal tests/contracts.
4. Preserve the remaining roadmap: aggregate recurring-cost admission,
   complete US universe/lifecycle reconciliation, downstream consumer wiring,
   environment-specific secret-store onboarding, outstanding provider live
   manifests, expanded options/Greeks, and the separately authorized 30-day
   operational trial.
