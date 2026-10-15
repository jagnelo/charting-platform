# ETF integration checkpoint: etf-holdings-integration-1

Prepared under the human's 2026-10-15 central-first resume direction. Planning
is authorized; implementation checkpoint acceptance remains pending. The full
objective and fourteen original criteria remain verbatim in `plan.yaml` under
`roadmap_goal` and `roadmap_acceptance_criteria`. Its disposition table specifies
each delivered scope, remainder, owner and continuation acceptance test. This
checkpoint does not close the full ETF roadmap.

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
- ETF adapter methods are async and open their own HTTP clients. Passing an async
  adapter method as the existing synchronous `invoke` callback would return an
  unawaited coroutine inside the executor and cannot prove successful fetch or
  request-level admission. A bridge needs the accepted producer's compatible
  async/transport contract, not just a top-level wrapper around adapter output.

The exact current tree is `13fd50a789b1c09e11a74ef178cb505521c38f4c`. The
adapter, refresh, and EDGAR source blobs equal their previously inventoried
blobs (`508c7458…`, `a235ffbe…`, and `63ac7778…` respectively), so the lexical
transport inventory below remains current despite later resolver and workstream
changes. The common repair release is already an ancestor; it did not include a
Provider product checkpoint. Do not use these current-tree primitives to infer
that the Provider contract is accepted or sufficient.

The bridge's first implementation review must therefore reconcile, from the
green staged producer, (1) exact capability and migration values, (2) a
non-bypassable entitlement/environment decision for each issuer operation, (3)
reviewed request units and recurring-cost admission, (4) durable reservation
and settlement identifiers for each actual outbound attempt, (5) an awaited
async invocation path or equivalent proven transport boundary, and (6) linked
health/admission/raw-artifact lineage. Before that source exists, only tests of
ETF's persisted consumer outcomes and documented test obligations are valid;
mocking a proposed provider API is not shared-runtime evidence.

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
- Existing writer claim: `bb0f68af-76ab-45c0-83f1-52d805be699f`. Resume this
  claim; do not create a second writer or transfer it implicitly.

## Concrete interface map

Locations below are authoritative source names, not promises about unstaged
interfaces. Provider ref inspected during preparation: `65a467b43`.

| Contract | ETF source now | Provider source inspected | Required reconciliation |
| --- | --- | --- | --- |
| Fund and constituent identity | `ETFProfile.instrument_id`, `Instrument`, issuer product IDs, explicit artifact identity validation in `etf_holdings_refresh.py` | `market_data_identity.apply_domain_identity`, instrument mastering/reconciliation, provider symbol bindings | Preserve canonical instrument/security/listing distinctions; unresolved/ambiguous identities stay explicit. Never synthesize a new identity from a ticker-only match or overwrite historical membership. |
| Capability | No `ETF_HOLDINGS` enum member | `ProviderCapability`, `providers.registry._capability_names`, runtime seed order | ETF owns enum, additive migration, native registry facade and capability seed after staged import. Verify every persisted enum-bearing table; do not create fake generic providers merely to make discovery green. |
| Admission | `_refresh_adapter_route` and dated refresh call issuer adapter directly | `provider_runtime.resolve_provider_chain` and `execute_provider_call` | Bind to the exact reviewed issuer/provider and operation before any network call. Retain environment, terms, authentication, live-verification, instrument-support and review-expiry exclusions. |
| Quota | ETF canary bounds and route-specific retries; no shared reservation | `provider_quota_coordinator.reserve_provider_quota_async` / `settle_provider_quota_async`, shared private ledger; runtime operation/dimension cost checks | Reserve/settle actual outbound requests, redirects/pages/retries as the reviewed contract requires. Unknown quota/reset/account baseline or unknown operation cost must deny before transport. Never assume an entire multi-request holdings fetch costs one request. |
| Monthly cost | No located shared monthly-budget contract | No aggregate recurring-cost admission API located in inspected runtime/config/models | Required shared repair: aggregate all active provider subscriptions, currency/equivalence policy and reviewed incremental cost; keep total at or below 20 EUR/USD-equivalent monthly. Free/already-entitled sources first; paid activation still requires explicit approval. Implement in the shared governance owner after central coordination, never as an ETF-only budget ledger. |
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
quota, async invocation semantics, or admission identifiers remain unresolved;
this inventory does not invent them. It is a current-source preparation result,
not shared-runtime acceptance.

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
