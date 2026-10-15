# Shared cost admission: ETF consumer contract

Status: ETF-owned integration preparation, not an implemented shared API or an
accepted scope reduction. The original roadmap still requires one shared
aggregate monthly ceiling of 20 EUR/USD-equivalent across active providers.
No subscription, paid probe, deployment, trial, or routing activation is
authorized by this document. The staging coordinator reconciles the producer
contract with the Provider owner before accepting the ETF checkpoint.

## Evidence boundary

Read-only inspection on 2026-10-15 found these existing Provider interfaces:

| Source | Existing behavior | What it does not establish |
| --- | --- | --- |
| `provider_runtime.resolve_provider_chain` | Applies shared entitlement, policy, health and configuration eligibility; excludes non-free entitlements when `ALLOW_PAID_PROVIDER_ROUTING` is false. | A consumer-specific, non-bypassable free-only operation policy or an aggregate recurring-subscription budget. |
| `provider_runtime.execute_provider_call` | Resolves the provider chain, checks operation costs and usage dimensions, then reserves/executes/settles shared calls. Supports exact `provider_name`, instrument, symbol and usage identity. | ETF capability/adapter wiring, all async issuer transports, or a whole multi-request fetch being one correctly charged request. |
| `provider_quota_coordinator.reserve_provider_quota_async` / `settle_provider_quota_async` | Shared durable quota reservation and settlement. | Currency conversion, monthly subscription activation approval or recurring spend admission. Quota units are not automatically monetary cents. |
| `provider_routing.settle_workload_lease(..., cost_cents=Decimal("0"))` | Adds cost to matching `ProviderQuotaWindow.cost_cents` during successful settlement. | Pre-transport reservation of money, aggregation of subscription commitments, a currency policy or proof that the default zero is the reviewed actual cost. |
| `settings.ALLOW_PAID_PROVIDER_ROUTING = False` | Default excludes reviewed paid plans from normal routing. | Proof that the same reviewed paid plan is excluded when a broad deployment flag is true. The setting is an explicit configurable switch, not an immutable checkpoint boundary. |

The inspected checkout's HEAD was
`65a467b43d7830b0875d9c3ad538e47a06d4a6db`, but its candidate has staged and
unstaged changes. In particular, the current uncommitted test
`test_free_only_checkpoint_boundary_rejects_reviewed_paid_provider` establishes
eligibility with the paid flag true and exclusion with it false. That is a
useful proposed default-config test, not a committed/passing receipt, not
evidence that true still denies, and not the aggregate-budget implementation.
Do not execute, stage, or modify the sibling candidate from this ETF worktree.
Refresh this map against the accepted, green staged producer before coding the
consumer. An interface not found here is not proof that none exists elsewhere.

## Shared admission decision needed before ETF transport

The bridge must obtain a shared decision for the exact canonical fund, publisher,
account scope, operation, entitlement revision and deployment environment.
It must not infer permission from a successful old issuer scrape, `is_free`
alone, a registry entry, a missing cost field, or an unused paid-routing switch.

The producer must identify the existing callable/contract, or supply the shared
repair, covering these semantics. Names below describe evidence fields, not
invented API attributes:

- Explicit allow/deny and a stable reason; link the reviewed source and terms,
  free/paid classification, account and applicable review/expiry evidence.
- Explicit reviewed operation cost and unit. Unknown, null, malformed, negative,
  non-finite or expired monetary/quota evidence is not silently zero.
- Atomic shared reservation before each actual outbound attempt, with durable
  settlement and a stable idempotency identity. Record the real publisher and
  account even when an adapter is reached through an issuer alias or successor.
- Retain request/admission/reservation/settlement references with ETF raw
  artifacts and health outcomes. No per-ETF in-memory budget or second ledger.
- Denial happens before any `httpx`, `requests`, curl, redirect hop, page, retry
  or SEC fallback can leave the process. No alternate transport bypass.
- A content/parse failure is still an attempted request; billable usage follows
  the reviewed publisher contract, not whether a fresh ETF snapshot was stored.
- Cached API/current/historical reads spend no quota or money. An explicitly
  requested refresh/backfill/canary uses the same shared admission boundary.

### Full recurring-budget contract (original roadmap)

Provider owns the aggregate ledger and admission; ETF consumes its decisions.
The shared contract must count active recurring subscriptions plus reviewed
incremental charges without counting the same shared subscription once per
capability, fund, worker or alias. Preserve recorded currency, billing period,
recurring commitment, activation authorization and any normalization evidence.
The approved conversion/equivalence rule must be identified explicitly; neither
this branch nor a test may invent a current exchange rate or treat 20 EUR and
20 USD as an unreviewed interchangeable quantity.

Concurrent Provider/ETF workers cannot reserve beyond the remaining aggregate
ceiling. Restarts cannot erase commitments, reset consumption, or charge the
same idempotent settlement twice. Ambiguous timeout/crash settlements remain
conservatively reserved until reconciled under the producer's documented rule.
An attempted activation or reservation over the approved ceiling denies before
transport. Cancellation does not retrospectively refund a retained contractual
commitment. An approved existing subscription still counts toward the platform
total; already entitled is not synonymous with zero cost.

### Conditional free-only development checkpoint

The central handoff permits proposing a tested free-only checkpoint instead of
building a new budget subsystem now. This is a conditional alternative, not an
automatic ETF acceptance decision and not completion of the full budget goal.

For that alternative, the producer/coordinator must document which exact
operations are reviewed zero-recurring/zero-incremental cost and demonstrate
that the accepted checkpoint cannot select or activate a paid plan. A false
default flag alone is insufficient evidence for the broader claim that a
reviewed paid operation cannot slip through a different caller or flag value.
Either the accepted contract supplies an explicit shared free-only operation
constraint, or checkpoint startup/configuration validation rejects the enabling
configuration and all call paths preserve that boundary. This is a choice for
the shared producer/coordinator, not permission to add a second ETF policy
engine. A reviewed free trial with a later automatic paid commitment cannot be
assumed zero-cost; absent an accepted non-billing proof it remains excluded.

No automatic downgrade to this alternative is made here. The exact excluded
operations, aggregate-budget remainder, owner, continuation acceptance test and
checkpoint acceptance must be recorded. The original 20-unit monthly
requirement remains open until its real shared contract is delivered and tested.

## Producer/consumer integration acceptance matrix

These are required cases after the producer is accepted into green staging;
they are not claimed to pass today. Use real shared runtime and PostgreSQL/Redis
accounting where applicable, with deterministic intercepted issuer transports.

| Case | Required assertion and owner |
| --- | --- |
| Reviewed eligible free operation | Provider admits under the accepted free policy; ETF invokes the exact publisher, records shared references, retains raw response, and accepts only independently validated fresh complete identity-matched holdings. |
| Unreviewed terms, reuse restriction, expired review or missing account evidence | Provider denies; ETF invokes no transport or fallback, stores the exact denial and preserves prior artifacts. Global X's recorded reuse restriction must pass this review, not be ignored because its page is public. |
| Reviewed paid entitlement | Full budget path needs explicit paid activation plus all normal admission checks; free-only checkpoint denies with zero calls. Exercise both flag states or prove the true configuration is refused before any operation. |
| Trial or already-entitled paid subscription | Provider accounts actual commitment and review/expiry; no automatic free classification, activation or billing. ETF has no independent override. |
| Unknown cost, currency, conversion rule or aggregate balance | Deny before network. Zero is accepted only when affirmatively reviewed, never as the `cost_cents` argument's default. |
| Aggregate balance at/below/over boundary | Producer tests exact arithmetic, cross-provider subscription deduplication and atomic concurrent admission; ETF tests both allowed exact-boundary and denied over-boundary outcomes. No guessed currency conversion. |
| Pages, redirects, `requests`/curl retry and SEC fallback | Account each actual request/attempt under its real reviewed quota/cost contract; deny an exhausted second attempt before sending it. Assert no recursive direct-adapter bypass. |
| Failed parse, HTTP error, timeout and uncertain result | Preserve raw/error/admission lineage; settle or retain reservations under the actual provider billing contract. No arbitrary refund, double charge or fresh snapshot. |
| Concurrent workers, restart and duplicate settlement | Producer ledger remains durable/idempotent; ETF replay and backfill cannot reset or duplicate charges. Inspect exact same account scope across consumers. |
| Denied refresh with existing snapshot | ETF retains snapshot and source/knowledge timestamps; marks degraded or stale as appropriate; current-analysis requests reject non-current data. |
| Denied refresh without snapshot | ETF exposes unavailable with exact cause; no synthetic current data. |
| Read-only API, historical inspection and analysis | No admission reservation or network request; retain exact snapshot/canonical identity and point-in-time lineage. |

## Release and remainder record

1. Coordinator/Provider names the selected existing/full/free-only contract and
   exact producer source/tests. ETF records the decision here without editing
   sibling files or weakening its roadmap.
2. Only after Provider is integrated and exact staging CI is green, merge the
   released staging baseline into this clean unfrozen ETF branch. Reconcile the
   actual interface, capability migration, registry and all transport call paths.
3. Execute the matrix against that real combined runtime. Existing persisted
   consumer tests are useful regression evidence, not proof of shared admission.
4. Run focused, full local Docker/browser and exact-source hosted validation.
   Publish an exact clean source receipt, enabled/excluded operations and any
   explicitly accepted remainder. Do not claim this document satisfies EICP3.
5. Keep the full monthly-budget and post-deployment observation requirements
   visible for continuation. No deployment or trial activation follows from a
   development checkpoint or a green test run.

## Central reconciliation update — 2026-10-15

The coordinator's published reconciliation at staging workflow commit
`98f0b888817c461fa00e6e310c5b378b0c4c512f` confirms that the Provider product
baseline has not been released. Its exhaustive/Playwright CI was still running
when the handoff arrived. Provider has been asked to either deliver the shared
aggregate subscription-cost admission contract or demonstrate a tested
free-only checkpoint boundary. ETF has not imported Provider code, merged
staging, or started another local full gate in response.

The exact consumer contract required from Provider is:

1. Given the canonical fund/instrument, actual publisher and account scope,
   environment, concrete operation, entitlement and terms revision, and
   current review/expiry evidence, return a durable allow/deny decision with a
   stable denial reason. Missing or ambiguous identity, account, terms, or
   review evidence denies before transport.
2. For an allow, provide the reviewed cost/quota basis for this operation and
   its actual outbound attempt. Cost, currency, billing period, reset window,
   or quota dimensions that are unknown, stale, malformed, negative, or
   non-finite deny; ETF must not infer a price, exchange rate, quota, or zero
   from an omitted field or settlement default.
3. Apply shared quota and cost admission atomically before every outbound
   attempt. The transport boundary must cover redirects, pagination, retries,
   alternate HTTP clients, and SEC fallback. Each attempt carries a stable
   idempotency key and durable reservation/settlement reference. An exhausted
   next attempt is denied before that request leaves the process. HTTP, timeout,
   or parse failure still records the attempt and follows Provider's reviewed
   billing/uncertain-settlement rule; it does not silently refund or create a
   fresh ETF snapshot.
4. Aggregate recurring commitments once per actual subscription across all
   providers and consumers, retain the source currency and billing period, and
   use only a coordinator-approved currency/equivalence policy. Atomically
   deny new commitments or usage that would exceed the approved 20 EUR/USD-
   equivalent monthly ceiling. Concurrent calls, process restarts, timeouts,
   and duplicate settlement cannot overspend, clear, or double-count it.
5. The current no-paid-activation rule is absolute: ETF cannot activate a
   subscription, start a billable trial, or change entitlement. Existing paid
   commitments must remain visible to the shared aggregate calculation. A
   conditional free-only checkpoint must deny every paid or uncertain-cost
   operation even if a general routing flag is enabled; it must enforce that
   at the shared boundary or reject the unsafe configuration at startup for
   every caller. A false default flag alone does not satisfy this contract.
6. Reads of cached/current/historical ETF data perform no provider request and
   reserve no quota or money. A denied refresh preserves raw artifacts and
   snapshot provenance, stores the decision/reason, and exposes unavailable
   when there is no prior usable snapshot or degraded/stale when one exists.
   It cannot make historical data current or bypass admission through a
   background worker, API, direct adapter, or fallback.

These are semantic requirements, not proposed names or signatures for a new
Provider API. Provider must identify the actual accepted callable and evidence
fields, or identify the shared repair owner and its staged contract. ETF will
adapt only after that producer contract is present in coordinator-released,
green staging. No ETF-owned ledger or guessed per-request price is implied.

### Independent tests still required

The persisted-consumer preparation tests cover snapshot, API, basket, denial,
freshness, and point-in-time behavior. They do not exercise Provider admission.
Once the producer interface is identified, ETF still needs independent
consumer-contract tests against the real shared runtime (with issuer transports
intercepted and call-counted):

- Allowed, reviewed free operation reaches only its exact issuer route and
  stores shared decision/reservation/settlement references with the validated
  raw artifact.
- Missing, expired, ambiguous, or restricted terms; unknown cost/quota/currency;
  denied entitlement; and exhausted budget each produce the exact persisted
  denial and zero calls through every HTTP client, redirect, retry, page,
  worker, and SEC fallback path.
- The accepted free-only boundary denies when the general paid-routing flag is
  true as well as false, or unsafe startup configuration fails before serving
  any operation. No test may activate a paid plan or trial.
- A multi-attempt operation reserves each reviewed attempt; after a denied
  page/redirect/retry reservation there is no corresponding transport call.
  Transport, HTTP, timeout, and parser failures retain raw/error evidence and
  settle or hold the reservation according to Provider's actual contract.
- Concurrent ETF/other-provider admission, process restart, ambiguous
  settlement, and duplicate idempotency replay preserve the same aggregate
  balance. These tests require the real shared database/ledger; mocks alone do
  not establish this behavior.
- A denial with prior data retains source, composition, fetched, and
  knowledge-time lineage and rejects current analysis when stale/degraded; a
  denial without prior data remains unavailable. Cached and historical reads
  assert zero transport and zero reservation.

Provider owns producer-side tests for subscription deduplication, currency
equivalence, exact ceiling arithmetic, atomic concurrent admission,
restart/uncertain-settlement recovery, and enforcement of the paid-activation
boundary. ETF owns its adapter/consumer no-transport and truthful-state tests.
The two suites must run against the same staged runtime for checkpoint
acceptance. None of these new shared-contract tests is claimed implemented or
passing by this documentation update; no tests were run for this documentation
only change.

### Common repair baseline consumed — 2026-10-15 21:40Z

The exact synchronized common repair baseline `82d881e76be8de538abb6ec5c454d96afe0ee56a`
is merged into the ETF branch. This release repairs shared workstation behavior;
it does not contain an accepted Provider product checkpoint or the
`ETF_HOLDINGS` producer contract. Provider owns the first heavy local validation
slot, and the actual ETF adapter/capability/async transport bridge remains gated
on Provider's reviewed green product contract. The complete admission matrix
above remains required and unchanged.

The coordinator's current semantic boundary remains: a general routing flag
whose default is false is not proof that every caller rejects unsafe
`paid=true`. Before any real page request, retry, redirect, or SEC fallback, an
unknown/paid cost, quota, entitlement, account, or terms decision must fail
closed at the shared admission boundary. ETF must not add a second ledger or
infer that omitted cost is zero. Previously retained ETF identity and mixed
asset-kind evidence (including futures and cash rows) remains required when
mapping shared canonical identities; ticker-like strings must never synthesize
equity identities. Neither this baseline merge nor bounded unit/type checks
constitutes EICP3/ETF product acceptance.
