# ETF integration checkpoint: etf-holdings-integration-1

## Current Provider producer release — 2026-10-20 20:58Z

Provider is accepted and released in synchronized green staging at exact SHA
`9b230ba4c97126a2937667138c6eb2a0aa297baf`; exact CI `39484176087` and
Exhaustive job `118849529356` are terminal green. The coordinator's release
record and canonical receipt are linked from the current ETF handoff and plan.
This supersedes prior unreleased-Provider statements only for this release. It
does not accept ETF or close any of its fourteen roadmap criteria.

The ETF owner fetched and verified the exact staging ref and is reconciling
that single SHA in the assigned ETF branch. Staging omitted/deleted ETF-owned
source and durable workstream records; those exact ETF files are being
preserved while shared source conflicts are resolved semantically. Provider's
imported workstream remains byte-for-byte as released. After merge, inspect the
actual producer API—not earlier candidate notes—before implementing
`ETF_HOLDINGS`, its additive capability enum/schema/disabled seed, identity and
issuer policy bindings, per-attempt shared admission and settlement, recurring
budget admission, health and request/artifact lineage. Preserve all
zero-transport denial cases and the pre-existing current/degraded/stale/partial/
unavailable and historical/PIT consumer contracts. Unknown/unreviewed routes
remain held; no issuer sweep or replay is authorized. The required local
`full_stack_browser` gate awaits a coordinator-assigned safe fixture slot.

Prepared under the human's 2026-10-15 central-first resume direction. Planning
is authorized; implementation checkpoint acceptance remains pending. The full
objective and fourteen original criteria remain verbatim in `plan.yaml` under
`roadmap_goal` and `roadmap_acceptance_criteria`. Its disposition table specifies
each delivered scope, remainder, owner and continuation acceptance test. This
checkpoint does not close the full ETF roadmap.

## Exact common green staging reconciliation — 2026-10-16 13:10Z

Coordinator direction authorized the ETF owner to reconcile exact synchronized
green staging commit `0145b65992b8692ce69f82f804f83f6c8e551fea` at the next safe
owner boundary. Its Exhaustive Integration Gate `38896729111` passed. This
commit contains common cleanup/resource/flaky-test repairs only; it is not
acceptance of Provider or ETF product scope and does not authorize this branch
to merge into persistent staging.

The branch was clean at `8eccbdf522c0cf29e9ebcbc0e65a8e02c39c1044` before the
merge. One content conflict in `frontend/tests/e2e/flows.spec.ts` was resolved
by retaining the released shared popup cleanup helper and one-shot conflict
response while preserving the ETF recovery assertion, cross-window rationale,
page-count check and browser diagnostics. Focused unit validation passed 2
files / 10 tests. Full ETF validation remains required and was not run during
Provider's heavy-validation priority. The actual Provider product checkpoint
remains unaccepted; ETF bridge implementation and shared-runtime contract tests
remain gated on its exact accepted green staging release. No live issuer/SEC
requests, quota spend, retained-data cleanup, deployment or sibling/staging
write occurred.

## Source and evidence reconciliation

### ETF-tree Provider runtime snapshot — 2026-10-15, source HEAD 13fd50a

This snapshot is from the actual ETF worktree after the released common repair
merge, not from the unmerged Provider feature branch. It is an interface audit,
not acceptance of a Provider checkpoint. On this tree:

- `backend/app/models/provider_runtime.py` defines nine `ProviderCapability`
  values and no `ETF_HOLDINGS` member. `ProviderEntitlement.is_free` defaults
  true; a default value is not reviewed ETF permission.
- `resolve_provider_chain` in `backend/app/services/provider_runtime.py`
  selects enabled policy rows joined to free entitlements, then excludes an
  expired review, disallowed environment, open circuit, missing provider or
  explicitly unsupported capability. An unknown per-instrument support status
  is not excluded by this function. The eligibility query does not itself
  validate publisher terms, account scope, operation cost, or an aggregate
  subscription commitment.
- `execute_provider_call` writes a `ProviderRequestLog`, records provider health,
  and invokes a synchronous callback using `run_in_executor`. It does not call a
  durable per-request quota reservation/settlement API. `_get_bucket` is a
  process-local token bucket. `_usage_cost_for_operation` falls back to one
  request for a missing or malformed cost and clamps non-positive values to one;
  it is usage telemetry, not proof of the actual publisher quota or money cost.
- The current ETF tree contains no `reserve_provider_quota_async`,
  `settle_provider_quota_async`, `cost_cents`, or aggregate recurring-subscription
  admission implementation under `backend/app`. This is bounded to the actual
  checked-out tree; it does not claim those APIs cannot exist in a later accepted
  Provider source.
- ETF adapter methods are async and open their own HTTP clients. The coordinator's
  read-only review of the current Provider source confirms `execute_provider_call`
  accepts a synchronous `invoke`, executes it via `run_in_executor` with copied
  telemetry context, and does not await a coroutine returned by `invoke`. Passing
  an async adapter directly could therefore let an unawaited coroutine appear to
  be a successful result. Provider must document this existing sync contract; it
  is not required to implement the ETF bridge before its own checkpoint. After
  accepted green Provider staging, ETF owns a backward-compatible adapter/transport
  integration that completes the async operation exactly once before the shared
  runtime settles it, with each outbound attempt individually admitted.

Policy onboarding follows the same producer/consumer ownership boundary:
Provider supplies generic reviewed-policy, admission, and durable-ledger
mechanics, but does not have to review/onboard all ETF publishers before its
first checkpoint. After exact green Provider release, ETF owns binding its
actual issuer/host/account/operation contexts and onboarding evidence-backed
ETF policies through the shared runtime. Unknown or inadequate evidence keeps
that operation non-routable; this does not create a circular Provider
pre-merge requirement or narrow the full ETF publisher/symbol roadmap.
Cached, historical, and point-in-time reads remain network- and
reservation-free. No cost, quota, terms, account, or retention values may be
invented, and no second ledger may be introduced.

The runtime implementation snapshot was recorded at
`13fd50a789b1c09e11a74ef178cb505521c38f4c`. The current full branch tip at this
resume is `159d1df48c8a242d6ace076e9accbfc901b1552d`; a source diff from the
runtime snapshot to that tip contains only the three security-sentinel test
parameter additions in `test_etf_holdings_resolution.py`. The adapter,
refresh, and EDGAR source blobs still equal their inventoried blobs
(`508c7458…`, `a235ffbe…`, and `63ac7778…` respectively), so this lexical
transport inventory remains current. The common repair release is already an
ancestor; it did not include a Provider product checkpoint. Do not use these
runtime primitives to infer that the Provider contract is accepted or sufficient.

The bridge's first implementation review must therefore reconcile, from the
green staged producer, (1) exact capability and migration values, (2) a
non-bypassable entitlement/environment decision for each issuer operation, (3)
reviewed request units and recurring-cost admission, (4) durable reservation
and settlement identifiers for each actual outbound attempt, (5) Provider's
documented synchronous invoke/telemetry contract and the ETF-owned exactly-once
async compatibility boundary, and (6) linked health/admission/raw-artifact
lineage. Provider need not build the ETF adapter bridge before its checkpoint.
Before green staging exists, only tests of ETF's persisted consumer outcomes
and documented obligations are valid; mocking a proposed Provider API is not
shared-runtime evidence.

## ETF-owned Study Lab screenshot readiness repair

The adjacent-chart readiness repair is already implemented on this ETF branch
in `frontend/tests/e2e/tc2000_visual.spec.ts`, source commit
`b01f59bf156e7a43efe3d9a7897a648ca97f0b16`. It calls the existing
`waitForShellReady` helper before navigating to Study Lab, then requires a
rendered `.chart-tool .uplot` and absence of `.chart-tool .tool-state` before the
sandbox-error screenshot. The existing screenshot files, visual assertions,
and `maxDiffPixelRatio: 0.005` remain unchanged. The branch-owned focused matrix
passed 12/12 comparisons across all four display projects, three repetitions
each, with retries disabled (`.ai/validation/etf-sandbox-visual-focused-20261015.log`).

The current released common repair `82d881e76be8de538abb6ec5c454d96afe0ee56a`
is already merged through ETF commit `bff2d390eaf128d54a5bb588298a3b528c9a6785`.
Its canonical CI run `38805309009` is reported green with all 104 visual cases
passing and no browser retries/flakes; this is common-repair evidence, not ETF
checkpoint acceptance. A coordinator cross-check additionally reports that
both unchanged 1080p Study Lab gap screenshots passed 3/3 using the
read-only-DejaVu secure-localhost fixture. The matching fixture artifacts are
not present in this ETF worktree, so retain that result as coordinator-reported
evidence rather than an independently collected ETF receipt.

The most recent complete ETF-owned local profile in this worktree is the
historical `8e84e7a75fd7c60deb9255f5c9da9b5fe5475e85` run: exit 0, backend 1938,
frontend 948, functional 154 passed / 106 declared skips, and visual 104/104
passed; exact-source CI `38788420409` was green. This predates the released
common repair merge and later ETF identity regression commits, so it does not
validate current HEAD. The corresponding 260-case browser process is terminal;
no replay process is currently visible in this worktree. The required combined
`full_stack_browser` profile and current exact-source CI remain pending after
Provider's reserved first heavy-validation slot and accepted producer contract.

- Preparation baseline: `f2670b0bbde8bb680173d847a43734f7391745f7`.
- Previously validated implementation: `5854dd2fc70e7424280782c3a61df5f6ed5b04c6`.
  Their diff contains only four operational files; application and test source
  are identical at resume. Preserve the existing implementation receipt rather
  than repeating costly issuer requests solely because the session resumed.
- Historical exact-source CI: run `37643014307`, backend/frontend/branch tests
  and hosted E2E passed. Local full profile passed 154 functional E2E cases,
  106 intentional skips, 104 visual comparisons at the unchanged 0.5% threshold,
  948 frontend tests, backend coverage, build/types, migration/Compose and
  research-worker checks. These are prior-source receipts, not proof that a
  future combined runtime passes.
- Historical live outcomes: local 532 passed / 14 classified skips; hosted
  528 passed / 18 classified skips. Every skipped route remains unverified.
  Neither a registry entry nor past live success guarantees current transport.
- Baseline registry is 496 providers / 422 native / 74 fallback; preserve the
  15 Tier-0 and 156 Tier-1 symbol investigations and every dated issuer audit.
  Recompute using the exhaustive source tests before publishing this context.
- Existing writer claim: `f206bbc5-abbf-473a-a44f-fb5706c81282`. Resume this
  claim; do not create a second writer or transfer it implicitly.

## Concrete interface map

Locations below are authoritative source names, not promises that an unstaged
candidate is released. The current read-only preparation inspected exact
Provider candidate `a8440efb82232a8b217df9c7330fab1795b257c9`; coordinator
reviews explicitly do not accept or release it. The earlier `65a467b43`
inspection remains historical evidence above.

| Contract | ETF source now | Provider source inspected | Required reconciliation |
| --- | --- | --- | --- |
| Fund and constituent identity | `ETFProfile.instrument_id`, `Instrument`, issuer product IDs, explicit artifact identity validation in `etf_holdings_refresh.py` | `market_data_identity.apply_domain_identity`, instrument mastering/reconciliation, provider symbol bindings | Preserve canonical instrument/security/listing distinctions; unresolved/ambiguous identities stay explicit. Never synthesize a new identity from a ticker-only match or overwrite historical membership. |
| Capability | No `ETF_HOLDINGS` enum member | `ProviderCapability`, `providers.registry._capability_names`, runtime seed order | ETF owns enum, additive migration, native registry facade and capability seed after staged import. Verify every persisted enum-bearing table; do not create fake generic providers merely to make discovery green. |
| Admission | `_refresh_adapter_route` and dated refresh call issuer adapter directly | `provider_runtime.resolve_provider_chain` and `execute_provider_call` | Bind to the exact reviewed issuer/provider and operation before any network call. Retain environment, terms, authentication, live-verification, instrument-support and review-expiry exclusions. |
| Quota | ETF canary bounds and route-specific retries; no shared reservation | `provider_quota_coordinator.reserve_provider_quota_async` / `settle_provider_quota_async`, shared private ledger; runtime operation/dimension cost checks | Reserve/settle actual outbound requests, redirects/pages/retries as the reviewed contract requires. Unknown quota/reset/account baseline or unknown operation cost must deny before transport. Never assume an entire multi-request holdings fetch costs one request. |
| Monthly cost | No ETF-owned budget ledger, by design | Shared `ProviderRecurringCostBudget`, revision and commitment models plus `configure_provider_recurring_cost_budget`, `admit_provider_recurring_cost` and `provider_recurring_cost_status`; single-currency, evidence-revisioned, account/environment-deduplicated, and paid activation remains false | Consume the released shared commitment/admission state during ETF policy onboarding/startup validation. Do not charge recurring cost per request, invent FX, assume `execute_provider_call` performs recurring-cost admission, or add an ETF ledger. Missing/unknown commitment evidence keeps the route disabled. |
| Health and availability | `ETFHoldingsAdapterState` plus bounded canary history and circuit evidence | `ProviderHealthState`, `ProviderRequestLog`, `provider_availability` observations | Persist shared transport health/admission outcome and ETF content health separately with linked lineage. A successful HTTP request cannot make stale/partial/unverified holdings current. |
| Retention | `ETFHoldingsRawArtifact`, immutable versioned snapshots/rows, composition/known/published/fetched time | Shared request logs and retained response payloads | Preserve raw artifacts and request/entitlement/quota references, including failed parse/schema evidence. Do not discard already queried pages or overwrite an older snapshot with a correction. |
| Consumer truth | `holdings_capability_for_profile/symbol`, basket current gate, explicit historical selection, API capability schema | Shared routing availability and canonical identity | Denied refresh: no prior data means unavailable; prior usable data is last-known/degraded, or stale after its deadline. Keep source-tier, failure classification, identity and snapshot lineage visible. Reads must not spend quota. |
| Worker/startup | Refresh/bootstrap/date/backfill/canary jobs, disabled opt-in canaries | Shared coordinator startup, default routing controls and migrations | Cover every issuer and SEC network entry point; reject bypasses, preserve retry/backfill resumability, and start application/worker with additive migrations. Do not activate canaries or a trial through a default change. |

## ETF-owned bridge design and remaining implementation

The detailed shared cost-admission producer/consumer contract and conditional
free-only checkpoint acceptance matrix are in [shared-cost-admission.md](shared-cost-admission.md).
They distinguish existing quota/cost settlement from recurring-budget admission;
neither the proposed contract nor a free default marks the original budget
criterion complete.

The bridge is an ETF consumer of the shared runtime. It does not own a second
token bucket, entitlement table, recurring-budget ledger, health scheduler, or
quota coordinator. The following wiring is required once Provider is present
in synchronized green staging; it is not implemented by this preparation note.

### Current outbound transport inventory

Read-only source scan at validated application/test code SHA
`8e84e7a75fd7c60deb9255f5c9da9b5fe5475e85` confirms that the eventual shared
admission bridge cannot be verified at only the top-level refresh function:

| ETF source | Literal source inventory | Integration implication |
| --- | --- | --- |
| `backend/app/services/etf_holdings_adapters.py` | 339 `async with httpx.AsyncClient` constructions; 462 `client.get` and 22 `client.post` expressions; 88 callable `requests.get` references, eight direct `requests.get(...)` expressions and three `requests.post` references; one `subprocess.run` curl transport path. | Issuer adapters independently open clients; some use multi-request product-page/token/data flows, pagination, retry, or HTTP-client fallbacks. Intercepting only the adapter result or one outer fetch cannot prove each outbound attempt was admitted or settled. Preserve exact publisher/product identity through each request. |
| `backend/app/services/etf_holdings_refresh.py` | Three direct async-client GET flows: issuer-feed discovery, SEC fund-ticker discovery, and single-profile SEC identifier enrichment. | Discovery/enrichment traffic is distinct from holdings refresh and must not become an ungoverned path. Decide explicitly which operations are required and how their actual costs/quota are represented. |
| `backend/app/services/etf_holdings_edgar.py` | Two async-client contexts and three `client.get` expressions across SEC submission/archive discovery and filing-document ingestion. | SEC reconstruction is an outbound fallback/backfill path, not proof of issuer-current support; it still requires the agreed shared admission/no-bypass behavior when invoked. |

These are lexical counts, not request totals or a claim that every listed call is
reachable for every route. Redirects can add network attempts inside a client,
and `requests`/curl fallbacks are additional transports. The final integration
must derive a reviewed, executable route-to-operation inventory from the
accepted Provider API, then add transport-level tests that count every actual
request and prove denied next attempts never leave the process. Unknown cost,
quota, or admission identifiers remain unresolved. The producer invocation
shape is no longer ambiguous per the coordinator's review: its callback is
synchronous, executor-run, and does not await returned coroutines; ETF's
backward-compatible async consumer adaptation remains to be implemented after
the producer is released. This inventory does not invent quota/cost semantics.
It is a current-source preparation result, not shared-runtime acceptance.

1. Merge only the centrally released green staging SHA into the clean unfrozen
   ETF source. Record starting source/staging hashes, exact staging CI, source
   freeze/release state and conflict decisions. Do not import Provider directly.
2. Add `ProviderCapability.ETF_HOLDINGS = "etf_holdings"` and its additive enum
   migration, reconcile migration heads and seed/registry completeness. Preserve
   disabled/unreviewed behavior when no reviewed issuer entitlement exists.
3. Expose the existing provider-specific adapter through a narrow ETF registry
   facade with an exact canonical instrument, issuer product ID, provider symbol
   and concrete current/dated operation. Charge and report the actual publisher
   and shared account/host scope. A fallback-only adapter or unverified symbol
   is not a native-enabled declaration. A successor route retains both old and
   current issuer identities and snapshot provenance.
4. Attach governance at the transport boundary as well as the logical operation.
   Existing adapters may fetch a product page, a file, several pages or categories,
   retry through `requests`, or invoke SEC fallback. All actual attempts need
   documented quota accounting and raw-response retention. The runtime's existing
   `invoke` executes a synchronous callable in a thread; ETF adapters are async.
   Reconcile that boundary without passing an unawaited coroutine as a successful
   result or opening a second unrelated runtime. A single batch wrapper cannot
   establish per-request quota evidence.
5. Apply shared recurring budget and entitlement checks atomically before
   transport. Return exact denial causes; do not auto-enable issuer rows based
   only on old registry/live evidence. Shared quota rejection is never permission
   to bypass the runtime via a direct adapter or an unaccounted SEC fallback.
6. Validate artifact identity/date/completeness before accepting a fresh snapshot.
   Link shared request/admission/health evidence to ETF state and retained raw
   artifacts. Schema errors remain failures with inspectable raw evidence. Preserve
   last-known data and its original source and knowledge timestamps.
7. Reconcile current, dated and historical consumers, explicit current analysis,
   canaries, retry/backfill and background enrichment. No interactive analytic
   loop performs hidden provider fan-out. Explicit historical inspection never
   rewrites an artifact or silently relabels it current.

## Executable acceptance matrix

Preparation regression module:
`backend/tests/unit/services/test_etf_holdings_checkpoint_consumers.py`.
It exercises actual capability/API/basket consumers over persisted outcomes;
it does not mock a shared runtime and then claim runtime integration passed.
Its fourteen cases pass within the complete 1,536-test backend unit suite.
The preparation also reproduced and fixed the historical correction lookahead
in `baskets._load_etf_snapshot`; all 611 adapter invariants and Ruff/format checks
pass. The final staged-runtime/full-profile evidence remains open.

| Scenario | Consumer evidence prepared now | Required staged-runtime evidence |
| --- | --- | --- |
| Current complete native artifact | Current capability, canonical constituent and exact snapshot/source lineage | Reviewed identity/entitlement/quota/budget accepted; actual bridge fetch/ingest and linked usage/health/raw evidence |
| Entitlement/environment denied | Stored failure remains degraded; historical artifact inspectable; current basket rejects | No transport invoked; exact shared denial persisted; no SEC or direct-adapter bypass |
| Unknown/exhausted quota | Typed failure remains visible to API/current-analysis gate | Real shared reservation rejects without request; all byte/credit/request/symbol dimensions, retries/pages and settlements accounted |
| Budget exhaustion | Last-known artifact retained; current analysis rejects denied-refresh state | One shared aggregate budget across ETF and other providers; concurrent admission and restart do not double-spend or reset charges |
| Identity mismatch/unresolved | Failure classification retained; no current basket | Real canonical binding conflict or mismatched issuer artifact fails closed without rewriting historical identity |
| Open circuit | Last-known/degraded outcome explicit | Shared circuit suppresses transport; content-health circuit/freshness remains distinct; recovery revalidated |
| Healthy transport, stale content | Successful health alone cannot make expired holdings current | Actual shared success plus stale holdings date yields stale, never current-analysis usable |
| No prior snapshot | Failed admission remains unavailable with no displayable last-known data | Runtime denial creates truthful state without inventing a snapshot |
| Historical correction | Date-selected basket excludes data learned after that date; explicit snapshot selection remains inspectable | API and Strategy-facing point-in-time membership agree, including composition/known/published timing and canonical identities |
| Native/fallback | Existing exhaustive registry/audit/parser tests retained | SEC and fallback-only routes never satisfy issuer-current capability, even after HTTP/parse success |

## Pre-release ETF bridge reconciliation checklist — 2026-10-17

This is the bounded ETF-owned preparation that can be completed before the
Provider checkpoint is accepted. Persistent staging is clean at
`6dc178c12498236a2a0060533305e20cf47438b7` with exact exhaustive CI green.
Coordinator-supplied evidence records Provider branch source
`bc45e4b223a4abfd89de15e2c7278ed17d43a698` and ordinary branch CI
`39070049292` as successful, including 151 E2E passes and 109 expected skips.
The Provider checkpoint is still unaccepted and has not been released through
green staging; its required local profile/fixture evidence remains open. These
receipts therefore do not authorize a merge or establish the shared runtime.

### Release gate and source reconciliation

Before changing ETF product code, the ETF owner must verify all of the following
against one coordinator release receipt:

1. Provider has an explicit conditional checkpoint-acceptance decision, its
   exact accepted source is an ancestor of persistent staging, and exact staging
   exhaustive CI is green for that merged source.
2. The accepted staging source identifies the concrete shared capability,
   policy/admission, entitlement, quota reservation/settlement, aggregate-cost
   or accepted free-only boundary, health, identity, and availability callables.
   Missing interfaces or semantic fields remain blockers; ETF does not guess
   names, prices, quota units, reset windows, currencies, or defaults.
3. Only the released staging SHA is merged into this clean ETF worktree. Record
   pre-merge ETF/staging SHAs, merge parents, conflicts, shared-path decisions,
   migration heads, and the exact coordinator receipt. Do not import Provider
   or TC commits directly.
4. Re-run the static route-to-operation inventory on the combined source before
   implementation. Bind every issuer, account, host, operation, redirect, page,
   retry, alternate client, discovery request and SEC fallback to reviewed
   shared policy. An unmapped or unknown operation stays non-routable.

### Exact ETF-owned bridge contracts

| Boundary | ETF implementation responsibility | Required invariant |
| --- | --- | --- |
| Capability and registry | Add `ProviderCapability.ETF_HOLDINGS`, its additive migration/seed, and a narrow facade over existing issuer adapters. | Disabled/unreviewed routes remain unavailable; fallback-only or quarantined routes never become native-current by registration alone. |
| Canonical identity | Bind `ETFProfile.instrument_id`, canonical fund/security/listing identity, issuer product identity, provider symbol, publisher and account scope to each operation. | Ticker-only matches and future-like tickers cannot create synthetic equity identities; conflicts fail closed without rewriting historical snapshots. |
| Admission and entitlement | Ask the accepted shared runtime for the exact operation before each outbound attempt. | Unknown, expired, restricted, paid/trial, wrong-environment or otherwise unreviewed evidence denies before transport and cannot fall through to SEC or a direct adapter. |
| Quota and aggregate cost | Consume shared durable reservation/settlement and the accepted recurring-cost/free-only decision. | Each request, redirect, page, retry and fallback is accounted independently; no ETF ledger, guessed exchange rate, implicit zero, or batch-wide single charge exists. |
| Async execution | Adapt async issuer transports to the accepted producer invocation contract and await completion exactly once. | A coroutine cannot be recorded as a successful response; cancellation, timeout and exception paths settle or retain reservations once under the producer rule. |
| Health and raw evidence | Link shared decision/request/reservation/settlement/health identifiers to `ETFHoldingsRawArtifact` and ETF adapter state. | Transport success is distinct from content identity, schema, completeness and freshness; failed content retains inspectable evidence and creates no fresh snapshot. |
| Consumer lineage | Feed capability API, refresh/canary/worker, basket/current-analysis and historical consumers from the same persisted outcome. | Reads make no network call or reservation; composition, publication, fetched and knowledge timestamps remain immutable and point-in-time selection avoids lookahead. |

The resulting states have one meaning across all consumers:

- `current`: the latest identity-matched, complete native artifact passed shared
  admission and ETF content validation and is within its reviewed freshness
  window.
- `degraded`: a prior usable snapshot remains displayable after a failed or
  denied refresh, with the new failure and original snapshot lineage visible;
  it is not accepted for an explicitly current analysis.
- `stale`: a prior usable snapshot exists but is beyond its freshness deadline;
  it remains inspectable and is rejected by current-analysis gates.
- `unavailable`: no usable prior snapshot exists, or canonical identity cannot
  be resolved safely; no synthetic holdings or fallback-current claim is made.

MSMR/QQQ and Militia/GOOG remain unresolved and quarantined. CI `38911867173`
retained no response body or parsed-row artifact, so it cannot distinguish page
content, selection, markup or parser behavior. Their historical successful
receipts remain history only; neither route can be enabled as current evidence
without a separately authorized retained first-party response and complete
identity/table/parser comparison.

### Deterministic consumer tests after release

Add focused tests against the real staged runtime, with all transports locally
intercepted and call-counted; do not issue issuer, Provider or SEC requests:

1. Reviewed free operation completes the async adapter exactly once, records
   shared references, retains the raw artifact and yields `current` only after
   independent identity/date/completeness validation.
2. Missing/expired/restricted terms, denied entitlement, unknown operation
   cost/quota/currency/account, unsafe environment and exhausted aggregate
   budget each produce the exact persisted denial with zero calls across
   `httpx`, `requests`, curl, redirects, retries, pagination and SEC fallback.
3. Multi-attempt routes reserve each actual attempt; denial of the second page,
   redirect or retry prevents that transport call while preserving the first
   attempt's settlement and raw/error evidence.
4. Timeout, cancellation, HTTP error, parser error and ambiguous settlement
   follow the accepted settlement rule exactly once and never create a fresh
   snapshot or double-spend on replay.
5. Open shared circuit suppresses transport; a healthy response with stale or
   incomplete holdings remains `stale`/`degraded`, never `current`.
6. Denial with prior data preserves `degraded` or `stale` lineage; denial with
   no prior data is `unavailable`; identity mismatch is unavailable and leaves
   historical identity untouched.
7. Cached capability/API reads, explicit historical selection and point-in-time
   basket/analysis perform zero admission, zero reservation and zero transport.
8. Native, fallback-only and quarantined routes preserve their classifications;
   specifically, MSMR/QQQ and Militia/GOOG remain unavailable for current-route
   acceptance until new retained evidence supports a separate reviewed change.
9. Concurrent workers, restart, duplicate idempotency replay and background
   refresh use the same shared account and ledger, without reset, double charge
   or bypass through a direct adapter.
10. Additive enum/migration upgrade, application and worker startup, disabled
    defaults, legacy callers and retained snapshots remain compatible.

Only after these focused checks pass should the normal deterministic branch
tests, PostgreSQL/Redis admission tests, complete `full_stack_browser` profile
and exact-source hosted CI run. The branch stops at `ready_for_human_review`;
the coordinator owns acceptance and persistent staging integration.

Required broader validation remains `full_integration` / `full_stack_browser`:
focused consumer/bridge/static tests; all deterministic adapters and default live
contracts; bounded opt-in final-source issuer matrix with every skip/failure
disposition; PostgreSQL/Redis runtime admission and concurrent/restart accounting;
enum/migration upgrade and application/worker startup; complete local Docker
integration and browser profile; exact-source hosted branch CI. Refresh evidence
made stale by source changes. Do not repeat paid/quota-consuming probes when
unchanged retained source evidence suffices, and never call a skipped required
operation accepted without explicit human-reviewed disposition.

## Review and continuation receipt

Final receipt must identify the exact validated implementation SHA, operational
checkpoint SHA verified externally, published source sync, staged dependency and
CI, delivered contracts, migration/default impact, enabled and unavailable
operations, raw-data retention, downstream consumer limitations and each original
roadmap remainder. `human_closure_authorization` and `closure_summary` stay pending
until human acceptance; the coordinator alone freezes and integrates the source.
No review-ready claim is made while actual staged-runtime evidence is missing.

The later operational observation remains the full 30 days with at least 95%
eligible Tier-0 checks, no two consecutive missed freshness deadlines and zero
silent identity/schema/completeness violations. It needs separate deployment and
trial activation authorization. It is not a prerequisite for this development
checkpoint. After all four checkpoints reach green staging and the coordinator
releases the source, merge that common baseline into this same branch, validate
and continue the complete original roadmap. Preserve every source receipt.

## Current central-first resume reconciliation — 2026-10-15 22:24Z

The owning ETF session resumed after first re-reading the local coordinator
copy of `feature-integration-coordination.md`, the accepted-checkpoint section
of `agent-orchestration.md`, and `provider-integration-checkpoint.md`. The
canonical UV-managed preflight/status helper confirmed the existing writer
`bb0f68af-76ab-45c0-83f1-52d805be699f`, implementation role, exact assigned
worktree, `full_integration` tier and `full_stack_browser` profile. Its initial
shared allocation-lock access was denied inside the sandbox, but the wrapper
continued and the UV-managed status helper completed; no new writer or takeover
was created.

Current ETF branch HEAD is `159d1df48c8a242d6ace076e9accbfc901b1552d`, clean
and equal to its origin branch at inspection. Exact staging repair SHA
`82d881e76be8de538abb6ec5c454d96afe0ee56a` is already the second parent of ETF
merge `bff2d390eaf128d54a5bb588298a3b528c9a6785`. This is only the released
common chart/save repair baseline; it is not a Provider or ETF product
checkpoint. The latest coordinator receipt dated 21:42Z still records
`provider_product_checkpoint: null`, no accepted product checkpoint, and no ETF
acceptance. The older central status YAML dated 16:55Z is not the latest
coordination evidence. The current human/coordinator direction reserves the
first heavy local validation slot for Provider; the ETF full profile was not
started.

The GitHub combined-status lookup for exact ETF HEAD `159d1df` returned an
empty status list. The branch contains the focused security-sentinel test
commit `dd9b7a08ce79303638c3951dd937270e97bbff33`, whose resolver module passed
52/52 with `--no-cov`; Ruff and the 31-record workstream validator passed.
This is focused test evidence only. The previously green 1938-backend,
948-frontend, 154-functional, 104-visual profile belongs to source
`8e84e7a75fd7c60deb9255f5c9da9b5fe5475e85`, before later source/merge changes,
and is retained as historical evidence rather than current acceptance. The
14-case persisted consumer suite tests stored API/basket outcomes and explicitly
does not prove shared Provider transport or admission.

Current read-only review of exact Provider candidate `a8440efb82232a8b217df9c7330fab1795b257c9`
supersedes the old present-tense snapshot while preserving it as history. The
candidate has 22 `ProviderCapability` values but still no `ETF_HOLDINGS`; its
seed path derives capabilities from the registered provider adapters and
disables stale policy rows. `execute_provider_call` is async and owns its
`AsyncSession`, admission, durable quota reservation/settlement, request log,
telemetry and health updates, but its `invoke` callback must be synchronous. It
runs that callback in an executor and rejects/does not await either a coroutine
function or an awaitable return. Shared recurring-cost budget and commitment
contracts now exist separately from `execute_provider_call`; they are not an
implicit per-request budget check and paid activation remains prohibited.

### Unreleased Provider operation-hold delta — 2026-10-19 23:44Z

Read-only comparison of the newer published Provider candidate
`023d30c615ae1bfea3a79f90d4d814242cd5711e` against the previously mapped
`a8440efb82232a8b217df9c7330fab1795b257c9` found five backend paths changed:
configuration, the shared runtime, their unit/secret-wiring tests and the
example environment. The candidate remains unreleased and still has the same
22 `ProviderCapability` values with no `ETF_HOLDINGS`. Its synchronous,
non-awaitable `execute_provider_call` invocation contract is unchanged.

The material new consumer contract is `PROVIDER_CHECKPOINT_OPERATION_HOLDS`.
While the shared free-only checkpoint is active, the resolver evaluates an
explicit provider/operation hold after entitlement admission but before adapter
construction, durable quota reservation or transport. A wildcard can hold an
entire provider. The service labels `bulk_fetch` and `fetch_rfr_ohlcv` normalize
to `fetch_ohlcv`, and `reconcile_universe_page` normalizes to
`discover_universe_page`, for hold lookup only; the original operation remains
the quota-accounting identity. Malformed hold maps fail closed. The current
candidate deliberately leaves EODHD `fetch_account_usage` outside its ordinary
market-data holds, preserving its separate reviewed bootstrap exception.

This strengthens but does not replace ETF onboarding. A hold is a checkpoint
safety exclusion, not proof of publisher identity, entitlement, terms, quota,
retention rights, recurring cost or live success. After an accepted Provider
release, ETF must map every issuer operation to the released operation catalogue
and verify that any absent or inadequate evidence remains non-routable through
the shared policy plus hold boundary. ETF must not mutate the Provider default
hold map to make a route pass, duplicate it in an ETF ledger, or treat the
absence of a hold as admission.

The combined-runtime test set must therefore add these exact cases:

1. A held ETF operation and each released service alias are rejected before
   adapter construction, reservation, request logging and every transport.
2. The original concrete operation/attempt identity still reaches shared quota
   accounting when an operation is admitted; alias normalization is not allowed
   to collapse request, page, retry or redirect costs.
3. Wildcard and operation-specific holds, malformed runtime configuration and
   an unknown ETF operation fail closed with zero HTTPX, requests, curl or SEC
   fallback calls.
4. The documented account-usage exception cannot authorize ETF holdings or
   issuer discovery, and disabling checkpoint mode is never an ETF-owned escape
   from entitlement, recurring-cost or quota admission.

Provider Actions `39342948219` and its combined browser/operation review were
still active at this audit boundary. Persistent staging remained the common
repair release `281a57bd9fb782c0f85bfb5127c713ea15037f68`; product checkpoints
remained 0/4. These source facts are preparation evidence only, not Provider or
ETF acceptance.

The post-release implementation must therefore keep `AsyncSession` on its
owning event loop and pass only a synchronous, complete one-attempt transport
callback. For an async HTTPX route, that worker callback runs an attempt-local
coroutine and client to completion in its worker thread and returns a concrete,
non-awaitable response snapshot. A `requests` fallback executes synchronously
in the same admitted worker boundary. Clients are never shared across event
loops. Automatic redirects are disabled: each redirect target, retry, page,
token request, product page, artifact request, client fallback and SEC request
re-enters shared admission before transport. Any denied/unknown/exhausted
decision must leave HTTPX, requests and curl call counts at zero for that
attempt. Curl must receive an equivalent governed one-attempt wrapper or remain
disabled.

After the coordinator releases an accepted Provider checkpoint through an
exact green synchronized staging SHA, the ETF owner will: verify and merge only
that release; record pre/post source and migration heads; add the additive
`ETF_HOLDINGS` enum migration from the released Provider head and update every
enum-bearing seed/registry/availability contract; bind reviewed issuer,
publisher/account/environment/host/operation and canonical instrument/product
identity to the shared runtime; validate shared recurring-cost commitment state
without a second ledger; and link request/reservation/entitlement/health facts
to ETF raw artifacts and snapshots only after settlement. Tests will cover
fresh and upgrade migrations, application/worker startup, exact-once concrete
transport completion and settlement/cancellation, per-hop redirect and
per-attempt fallback/page/retry admission, SEC no-bypass behavior, fail-closed
unknown/paid/trial/expired/exhausted states, concurrent quota/idempotent
settlement, content lineage, and zero-governance-work cached/historical/PIT
reads. Current/degraded/stale/partial/unavailable and historical/PIT outcomes
remain distinct; SEC is never issuer-current.

Until that explicit release, the real bridge and transport-negative integration
tests cannot safely be implemented. Exact-source CI and current-source
`full_stack_browser` remain required before ETF checkpoint review. Human
acceptance, feature-worker staging integration, promotion, deployment, paid or
trial activation, operational observation and data cleanup are not authorized.
# Bounded checkpoint final review state — 2026-10-21

Coordinator technical review is conditionally approved for the bounded ETF
checkpoint at implementation B `79e0604c0a4b398a0fd92bdd4b099c308eee43eb`.
The complete source-qualified local matrix is recorded in
`.ai/validation/etf-full-profile-a198ef83-attempt6-b-matrix.md`; it includes
the exact B strict visual/branch runs and explicitly qualifies reused A198
backend, frontend, functional, Compose/research and migration-compatibility
results by identical tested input hashes. It does not claim the interrupted
monolithic attempt exited zero. Earlier red/partial/setup evidence is retained.

The human-authorized acceptance delegation is recorded verbatim in the plan
and session: “Yes—approve that initial scope and handle checkpoint acceptance.”
The coordinator's review is conditional on mandatory terminal-green exact-C
branch CI and its guarded staging merge/EIG. Neither is claimed complete here.
Provider is accepted/released at synchronized green staging SHA
`9b230ba4c97126a2937667138c6eb2a0aa297baf` (CI `39484176087`, EIG job
`118849529356`). ETF's EICP1–EICP7 local technical review is complete on B;
exact hosted C CI is pending. The final source capture is `integration_capture:
exact branch HEAD`, avoiding a self-referential hash update.

This bounded checkpoint does not close the original ETF feature. All fourteen
original criteria, full issuer onboarding, the post-integration 30-day
observation gate and historical audit evidence remain open. The 15 Tier-0 and
156 Tier-1 investigations remain preserved. MSMR/QQQ and Militia/GOOG remain
unresolved/quarantined; unknown, quota-held, unreviewed, paid/trial and unsafe
operations remain disabled/non-routable. No live request, quota replay,
deployment or feature-worker staging integration is claimed or authorized.

The final C commit contains only ETF-owned workstream records. After it is
pushed once, record/inspect exact C CI externally without a tracked metadata
follow-up. The central coordinator owns final acceptance, guarded staging
integration and EIG; this worker stops at the prepared checkpoint handoff.
