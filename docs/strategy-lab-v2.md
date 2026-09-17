# Strategy Lab v2 backend

Strategy Lab v2 is a local-first backend sandbox for reproducible portfolio
backtests, search and walk-forward experiments, and persistent broker-free
forward/shadow evaluation. It is a new versioned platform contract; it does not
extend or reinterpret the current Strategy Lab runner.

## Execution contract

An immutable strategy version declares its SDK version, exact dependency
artifacts, parameter schema/defaults, and content digest. A portfolio version
binds strategy versions to instrument scopes, capital budgets, priorities,
and typed/versioned shared-risk and optional calendar-rebalance policies. The
core plans deterministic schedule boundaries from a complete pinned calendar,
and its pure rebalance-allocation gate applies targets only at the exact
scheduled UTC boundary. A missed boundary is classified by the occurrence's
explicit fail-run or skip-occurrence policy; it is never silently caught up at
a later event. Engine adapters still own event-tape mapping, order sizing, and
fills. A
`TargetPositionIntent.target_fraction` is a fraction of the emitting component's
share of current account equity; the host multiplies it by that component's
capital weight. Targets are bounded by the component's capital budget unless an
explicit component-leverage limit is raised in the policy. Component targets
are resolved together at one event, conflict
handling is explicit (`reject`, `highest_priority`, or `sum_component_targets`),
and gross risk is calculated before same-instrument netting. Shared gross, net,
instrument, component, open-instrument-count, and short-position limits fail the
whole candidate batch closed; targets are never silently scaled. Raw quantity
`OrderIntent`s are sized only after an engine adapter supplies authoritative
instrument economics, FX conversion, and product-appropriate risk valuation.
Risk calculations use a content-addressed, per-product risk-model binding. The
current registry covers cash-equity and crypto-spot marked notional, futures
contract notional, option delta-adjusted underlying notional, and FX pair
notional; unsupported or unregistered products fail closed. These notional
concentration caps are not a complete market, margin, liquidity, or
derivative-risk model, and passing them never authorizes order execution.
Before execution, a capability preflight
must establish the requested product, data granularity, history, adjustment,
session/feed, corporate-action, and execution-model semantics. Missing rigorous
support fails closed. A degraded run is possible only through an explicit,
evidence-backed substitution and is excluded from rigorous rankings by default.

Data acquisition and repair belong to the shared market-data platform. The
resulting series are verified and frozen into a content-addressed snapshot
before simulation; a simulator must not fetch market data. Each series binds an
upstream coverage-evidence digest in addition to its content digest. Bounds and
row count alone do not prove observations are complete: the staged provider
adapter must verify that attestation (including calendar and gap semantics)
against the series content digest, range, row count, and semantic dimensions
before execution is enabled. The package-owned `snapshot_coverage.py` and
`data_acquisition.py` contracts now record that verification and bind it to the
request, preflight, frozen snapshot, and opaque provider receipt; provider I/O,
repair, and evidence retrieval remain owned by the staged adapter.
Trial identities
include the experiment, snapshot, preflight, parameter/scenario configuration,
and deterministic seed. Infrastructure retries create new run attempts linked
to the same scientific trial. Native engine outputs, not a parallel fill model,
are the source of official account, order, position, and metric results.

Parameter grids, seeded random draws, Latin-hypercube samples, scenario matrices,
and anchored/rolling walk-forward folds are deterministic. Walk-forward planning
keeps training and out-of-sample indices separate, supports a pre-test gap and
purges prior test/embargo observations from later training. Aggregate helpers
include only each non-overlapping out-of-sample index once.

Persistent forward instances warm up once from an immutable historical
snapshot, then consume only new canonical events. Duplicate, missing, stale,
out-of-order, and corrected events are classified explicitly. Corrections do
not rewrite earlier decisions; they request a separately identified
counterfactual replay. Gap events are buffered without advancing the contiguous
cursor, so late missing events can be applied and the buffer reconciled in order.
The forward state machine never represents broker order submission.

## Current engine-neutral package

The current parallel-safe slice is in `backend/app/strategy_lab_v2/`:

- `canonical.py` provides stable JSON serialization, SHA-256 content addresses,
  and recursive immutability.
- `contracts.py` defines immutable strategy, portfolio, snapshot, experiment,
  package, trial, attempt, artifact, metric, run-result provenance, and
  forward-instance records. Portfolios carry a typed, calendar-versioned
  rebalance policy rather than an unvalidated free-form mapping. Snapshot
  preflight matching includes event type and
  semantic series requirements; manifest interval continuity is structural
  validation, not a substitute for upstream coverage-attestation verification.
  Scientific trials also carry typed randomization provenance: master/effective
  seed, policy, replicate index/count, scope and seed-group fingerprints, and
  derivation version. Generated assignments verify their effective seed against
  the supported seed-group digest; unsupported derivation versions fail closed.
  Strategy dependencies and experiment strategy collections are canonicalized
  by identity, so equivalent declaration order cannot change trial provenance.
  Authoritative metric sets likewise validate typed values and canonicalize
  `(name, basis)` records before their content-addressed fingerprint is used.
- `capabilities.py` implements strict/degraded capability-cell preflight.
  `execution_capabilities.py` binds that data decision to a registered engine
  build and conformance fingerprint, failing closed when product, execution,
  or account semantics are not supported. Non-authoritative engines may be
  executable for compatibility evidence but cannot publish authoritative
  results.
- `data_acquisition.py` binds a provider acquisition receipt to one typed
  capability preflight, frozen `DataSnapshot`, and verified snapshot-coverage
  resolution. Identity drift, stale receipts, unsupported preflight, and
  incomplete coverage reject the handoff deterministically; provider fetching,
  repair, and persistence remain adapter responsibilities.
- `execution_data_admission.py` is the final pure data gate before a Nautilus
  plan is consumed. It requires the verified acquisition handoff to match the
  scientific trial, frozen snapshot, and ready engine plan, so a worker cannot
  bypass coverage verification by passing only a snapshot digest.
- `execution.py` composes source, trial, engine, attempt, and lease checks into
  one immutable `ExecutionAuthorization`. A future worker must obtain this
  authorization before invoking an engine adapter; it carries no source bytes,
  secrets, or external-service handles.
- `forward_state.py` provides immutable, fingerprinted forward checkpoints with
  processed, buffered, correction, duplicate, and out-of-order evidence.
  Accepted/gap/correction records are idempotent when replayed, while anomaly
  counts remain observable for each newly observed event.
- `dispatch.py` defines immutable queue requests/envelopes and pure idempotency
  resolution. A repeated key with the same attempt/payload/queue replays the
  existing request; a reused key with different content is an explicit
  conflict. Redis/outbox publication still requires an atomic adapter.
- `progress.py` defines ordered worker progress, cancellation intents, and
  resumable progress state. Updates cannot reorder, change the total, move
  backward, or mutate terminal states; cancellation is idempotent and must end
  in an explicit cancelled terminal update.
- `sdk.py` exposes declared read-only inputs and typed order/target-position
  intents. Public SDK boundaries reject malformed dependency, event, position,
  context, and enum values before they reach a strategy; every declared field
  is required on each provided event, event timestamps must stay within each
  dependency's declared history interval, and intent validation checks the
  strategy's declared instrument scope.
- `strategy_validation.py` performs deterministic static source preflight before
  a strategy package can reach a future runtime. It rejects disallowed imports,
  relative imports, dynamic-code/file/network calls, private-object
  introspection, and wall-clock calls (`now`, `today`, and `utcnow`), while
  binding the result to the exact source digest. This is an early rejection
  layer only; it is not a substitute for the separately required isolated
  runtime and resource controls.
- `artifacts.py` verifies an already-read immutable payload against its
  `ArtifactManifest` using raw-byte SHA-256 and exact byte length, returning a
  digest-bound receipt with typed mismatch reasons. Retrieval, atomic
  publication, retention, and storage I/O remain adapter/worker concerns.
- `artifact_publication.py` turns verified receipts into a storage-neutral
  create-if-absent or reuse-existing plan and exposes whether the retention
  class requires a pin. It never overwrites an existing content address or
  performs publication itself.
- `result_integrity.py` verifies one-to-one coverage of every output artifact
  referenced by a successful `RunResultManifest`, rejecting missing,
  unexpected, duplicate, foreign, or unverified receipts before a result can be
  treated as complete. It does not read storage or certify engine semantics.
- `allocation.py` resolves event-aligned component target-position intents using
  typed policies, preserves existing component-attributed positions, records
  deterministic conflicts, and returns proposed versus risk-approved account targets.
  Explicit zero targets are preserved. Exact registered cash-equity, crypto-spot,
  futures, option-delta, and FX risk models are accepted only when the policy
  and snapshot bind the same model; unregistered models fail closed. Current
  exposure snapshots bind opaque valuation evidence which the adapter must verify.
  This pure module does not create or route engine orders.
- `risk_models.py` applies the registered product formulas to adapter-verified
  order economics: marked quantity value for cash/crypto, contract notional for
  futures, delta-adjusted underlying notional for options, and marked pair
  notional for FX. It returns a digest-bound signed base-notional receipt and
  deliberately omits margin, liquidity, settlement, and engine-fill claims.
- `margin_risk.py` layers an event-aligned, adapter-supplied initial/maintenance
  requirement and capacity gate over routed orders. Utilization and capacity
  breaches withhold the entire batch; the contract never infers margin from
  notional exposure or issues a solvency verdict.
- `stress_risk.py` layers explicit adapter-generated stressed-equity scenarios
  over the margin/routing decision. Loss-fraction and minimum-equity policy
  breaches withhold the entire batch while retaining shock/evidence identities;
  the package does not construct shocks or claim a solvency verdict.
- `liquidity_risk.py` layers adapter-supplied available quantity/notional and
  slippage evidence over stress, margin, and routing. Per-instrument batch
  participation and slippage ceilings are evaluated all-or-nothing; missing
  capacity is explicit and the contract makes no fill-quality guarantee.
- `settlement_risk.py` layers adapter-supplied per-order settlement cash deltas
  and per-currency free-cash evidence over liquidity, stress, margin, and
  routing. Gross settlement debits and minimum remaining-cash buffers withhold
  the entire batch; missing order estimates or currency capacity fail closed.
  Product cash flows, conversions, and settlement timing remain adapter-owned.
- `shock_construction.py` expands explicitly typed shock dimensions into stable
  scenario definitions and content-addressed identities. It never applies
  shocks, infers cross-asset effects, or calculates stressed equity; those
  operations remain engine/account-adapter responsibilities.
- `risk_pipeline.py` composes routing, margin, stress, liquidity, and settlement
  in a fixed order and verifies the fingerprint chain in one immutable
  pre-engine admission receipt. It exposes only approved routed orders and has
  no submission or fill capability.
- `order_routing.py` converts explicit `OrderIntent` quantities into
  digest-bound, adapter-supplied product-risk base-notional estimates, validates
  lot/tick/currency/model evidence, and applies the same all-or-nothing shared
  risk gate before exposing an engine-neutral routed order. Estimates are not
  fills and no order is submitted; unregistered product models remain
  fail-closed.
- `rebalance.py` validates complete local-date calendar coverage with explicit
  trading/closed days, official trading-date labels, UTC session segments,
  timezone and tzdb versions, and source evidence. It deterministically schedules
  per-session, ISO-weekly, monthly, quarterly, or yearly boundaries using the
  first/last actual session and session-open-before-events or
  session-close-after-events timing. Calendar identity is content-addressed;
  weekly/monthly/etc. schedules require complete bucket coverage so missing
  dates cannot be silently treated as holidays. DST/overnight timing is carried
  by explicit UTC instants. `rebalance_allocation.py` composes that boundary
  with typed target intents and the existing allocation/risk gate: only an
  exact event applies targets, while before-boundary, fail-run misfire, and
  skip-occurrence outcomes are immutable, content-addressed decisions. Neither
  module implies same-price fills, infers a catch-up event, fetches calendars,
  or creates orders.
- `event_tape.py` provides a frozen, snapshot-bound event sequence for replay.
  It canonicalizes cross-series ordering, rejects duplicate event identities,
  prevents one dependency from switching instruments, and requires each
  dependency's sequence and event time to advance monotonically. Deterministic
  same-time batches and explicit non-interpolating time slices are available to
  a later strategy/engine adapter. `bind_event_tape()` then verifies the tape
  against the frozen snapshot's preflight substitutions, declared effective
  intervals, series coverage, declared instruments, exact dependency fields,
  and SDK manifest, returning a content-addressed binding with per-dependency
  event counts. Acquisition, coverage attestation, and fills remain outside
  this contract.
- `replay.py` turns a verified frozen tape into one immutable SDK context per
  same-time batch, retaining only each dependency's declared trailing lookback
  and optional host-supplied position snapshots. `replay_event_tape()` repeats
  snapshot/manifest binding, invokes one stateful strategy session in
  chronological order, preserves tape/binding/source/parameter identities, and
  stops at the first typed rejection or failure. It does not apply intents or
  model fills; engine/account adapters remain responsible for those effects.
- `observations.py` defines normalized event-time/sequence points, native
  fill-cost cash effects with explicit currency-conversion and slippage-benchmark
  evidence, explicit complete/partial/unavailable cost-report coverage, and
  account/component P&L records. Account-equity intervals distinguish complete,
  partial, and unavailable external-cash-flow reports; a complete report must
  explicitly report both net amount and flow occurrence, distinguishing no flows
  from offsetting flows with a zero net amount. Event and fill observations are
  scoped to one run attempt so metrics cannot silently combine separate retries.
  Engine adapters must provide the evidence; the core does not perform FX
  conversion, infer costs, or infer P&L attribution from position weights.
- `experiments.py` expands deterministic search/scenario plans and
  leakage-aware walk-forward folds. Trial seeds remain per-candidate by default
  with the pre-existing derivation unchanged. The default also retains existing
  trial IDs: its typed seed metadata remains available without redundantly adding
  the legacy schedule to identity. An explicit shared-per-scenario-replicate
  policy assigns the same initial seed across parameter candidates within one
  fixed experiment scope, scenario, and replicate, and records the seed group
  needed for later matching. This is not evidence of paired random draws:
  stateful/unkeyed engine streams may diverge when strategies take different
  paths. `pairing.py` now verifies decoded content-addressed keyed streams
  against registered engine-conformance and stream-contract identities. It
  rejects duplicate or unmatched keys and differing draw values, then emits a
  deterministic verification receipt. The
  `SensitivityComparisonEvidence` distinguishes unpaired results (which does
  not prove statistical independence), a matched shared seed group only, and an
  unverified keyed-stream pairing claim. Equal integer seeds without matching
  scope/scenario/replicate provenance remain unpaired. The contract checks that a
  pairing claim binds both successful attempts and their engine build, declares
  complete draw-key alignment, and references trace/pairing artifacts in both
  result manifests. It cannot authenticate those bytes or engine conformance, so
  it deliberately does not label a claim as verified pairing; a receipt from
  the keyed-stream verifier is required. `sensitivity.py` adds a
  descriptive one-factor metric comparison over successful results. It requires
  identical parameter keys with exactly one canonically different value,
  matches metrics by `(name, gross/net basis)`, and requires equal non-null
  calculation fingerprints. The comparison separately binds a measurement-scope
  identity to the experiment, frozen snapshot, declared scenario, portfolio
  currency, execution context, metric calculation, referenced coverage claims,
  and session-calendar evidence. Run-specific observation digests may differ;
  both realized sample sizes and the existing randomization-evidence label are
  retained. `SensitivityComparisonEvidence` rejects mismatched fixed run
  context; the comparator returns the signed `variant - baseline` difference or
  a typed unavailable reason for missing, unversioned, incompatible, null, or
  metric-level out-of-scope inputs such as different session calendars. This
  output is descriptive only: it does not average candidates or replicates,
  estimate significance, or claim paired inference. A shared
  snapshot binds coverage-evidence digests as claims; this engine-neutral
  comparator cannot authenticate their referenced documents.
  The scenario digest binds the declared scenario but is not a separate typed
  evaluation-window contract. `calculate_paired_metric_metrics()` consumes
  aligned keyed observations plus a verified receipt and returns descriptive
  baseline/variant means, nearest-rank delta median, extrema, and sample
  deviation. The receipt and observations establish provenance/alignment but
  no inferential model or significance claim is made.
  `paired_inference.py` adds the bounded trusted-inference step separately:
  `infer_paired_mean()` requires the verified keyed-stream receipt and performs
  an inclusive two-sided exact sign-flip test for a zero paired mean delta.
  Every sign assignment is enumerated deterministically and the result records
  the observation/receipt identities, tail counts, method, null, and contract
  version. A configurable maximum of 20 observations prevents unbounded CPU;
  larger requests return typed unavailable evidence rather than an approximate
  or unseeded result. `calculate_paired_inference_metrics()` projects the
  p-value and enumeration counts as versioned metrics with explicit null
  reasons. This is statistical evidence only and never a profitability verdict.
  `EvaluationWindow` is an immutable trial-bound interval with an optional
  warm-up start. Its fingerprint participates in trial identity and in
  sensitivity measurement scope, so variants with different evaluation or
  warm-up periods are rejected as incomparable rather than silently mixed.
  Replicates are explicit; infrastructure retries remain attempts of the same
  scientific trial.
- `ranking.py` provides deterministic descriptive ordering for completed
  results within one experiment and compatible snapshot, portfolio, engine,
  allocation, metric, unit, and calculation contexts. It excludes degraded
  preflight, null, missing, unversioned, incompatible, and duplicate-trial
  results by default, retains explicit exclusion reasons, and makes no
  profitability or statistical inference claim.
- `metrics.py` v6 computes Decimal account P&L/return, drawdown duration, Ulcer,
  annualized return/volatility, Sharpe/Sortino/Calmar, recovery factor, empirical
  historical VaR/expected shortfall, and trade outcome/streak summaries from
  authoritative engine equity and trade-P&L series. The equity input contains
  equally spaced post-start marks only (not the opening balance), and
  `periods_per_year` must match that cadence; timestamped/irregular observations
  are not yet modeled for annualized time-series metrics. Currency is explicit;
  calculation/annualization basis, gross/net basis, samples, and null reasons
  travel with each metric. Tail calculations use an explicitly versioned
  nearest-rank empirical convention. Exposure metrics are equally
  sample-weighted signed cash-equity notional relative to contemporaneous equity;
  they are not time-weighted exposure or margin/capital requirements. Fill-cost
  totals and basis points are null when any fill cost report is partial or
  unavailable; category values are explicitly reported amounts, not asserted
  complete totals. Complete reports may explicitly state zero cost. Cost metrics
  use engine-reported signed cash effects, explicit base-currency conversions,
  and named slippage benchmarks, with fill notional as the stated basis-points
  denominator. Run-level component P&L attribution reconciles
  exactly to portfolio gross/net P&L and requires an explicit unallocated
  component when residual results exist. These remain only part of the planned
  catalog. `calculate_calendar_period_metrics()` adds run-scoped linked
  prior-mark-to-session-close P&L and per-period returns for each-session,
  ISO-weekly, monthly, quarterly, or yearly cadence, tied to the exact session
  calendar and complete-period flag. Net P&L reconciles account equity changes
  after explicit complete external-flow reports; it is null when those reports
  are partial or unavailable. Returns are null for incomplete period coverage.
  Flow-bearing periods use the geometric boundary-aware path when every event
  has explicit pre/post valuations, and remain null when that evidence is
  missing.
  `calculate_rolling_equity_metrics()` returns structured, run-scoped points for
  each observed close. Each window requires the requested number of consecutive
  session-close intervals plus the preceding session close; missing observations
  are explicit incomplete points, not compressed samples. Annualization periods
  and periodic risk-free target are required inputs. Rolling return, volatility,
  Sharpe, Sortino, drawdown, duration, and Ulcer metrics fail closed on incomplete
  flow evidence or external flows; net P&L remains available only with complete
  flow reports. `calculate_session_return_distribution_metrics()` adds a
  run-scoped summary over an explicit inclusive range of actual trading-session
  labels: nearest-rank close-to-close return quantiles and empirical VaR/expected
  shortfall, with no interpolation and the selected tail sample counts recorded.
  Every session must have an observation and a mark at the preceding actual
  session close. Missing coverage, incomplete external-flow reporting, or any
  external-flow event withholds the entire distribution; simple close-to-close
  returns are not presented as flow-adjusted time-weighted returns. Histogram
  bins and sensitivity ranking/inference are not part of this summary.
  `calculate_capital_margin_utilization_metrics()` adds an engine-neutral,
  run-scoped summary of event-sampled initial and maintenance margin
  requirements relative to their supplied capacities and contemporaneous
  account equity. Requirements, capacities, currency, and valuation evidence
  are authoritative adapter inputs; the calculator never infers margin,
  leverage, or buying power from notional exposure. It reports equally
  sample-weighted means and observed maxima as diagnostic ratios, including
  ratios above one, without turning them into a breach or profitability
  verdict. `calculate_financing_cost_metrics()` separately consumes bounded
  engine-reported financing-cost reports outside fill costs. Complete reports
  publish signed net financing cost; partial or unavailable reports retain
  coverage counts and reported cash effects but withhold the derived net cost.
  `calculate_stress_scenario_metrics()` separately consumes adapter-supplied
  stressed-equity observations bound to explicit shock-definition digests. It
  reports scenario counts, loss counts, average and worst stressed returns and
  P&L, and minimum stressed equity; it does not construct shocks or issue a
  solvency/risk verdict.
  Trusted paired inference is now available through the separate exact
  sign-flip calculator described above; approximate/bootstrap inference and
  inferential ranking remain outside this package boundary.
  `calculate_time_weighted_return_metrics()` now provides a strict,
  engine-neutral flow-adjusted return path. Each reported external event must
  carry explicit pre-flow and post-flow equity boundary marks whose difference
  reconciles the event cash amount; missing or incomplete flow evidence
  withholds both linked and elapsed-time annualized returns. Annualization uses
  an explicit days-per-year convention and elapsed UTC duration, so irregular
  spacing is not treated as a fixed session cadence. Calendar-period, rolling,
  and session-distribution aggregators now consume the same boundary evidence;
  flow-adjusted status is retained on distribution summaries.
  `summarize_one_factor_metric_replicates()` adds a deterministic descriptive
  baseline/variant summary over complete replicate arms. It requires one result
  per planned replicate index, one canonical parameter change, identical fixed
  execution and metric-measurement scope, and non-null values. Each arm retains
  realized observation sample sizes and seed provenance, and reports Decimal
  mean, nearest-rank median/minimum/maximum, and configured nearest-rank
  quantiles. The result exposes only the signed difference of arm means; it does
  not rank candidates, estimate significance, or claim independence or paired
  inference. Trusted paired inference is provided separately by the bounded
  exact sign-flip calculator; approximate/bootstrap inference and inferential
  ranking remain outside this package boundary.
- Every metric produced by the v2 calculators carries a versioned
  `MetricCalculationDefinition` (`strategy-lab.metric-calculation.v1`) with a
  stable formula-family ID, Decimal context, and effective formula parameters.
  `MetricEvidenceReference` records run-specific input/result digests separately;
  the digest is retained for provenance but is intentionally excluded from a
  metric's `calculation_fingerprint`. That fingerprint also excludes the output
  value, sample size, null result, and free-text display basis, while binding
  metric name, unit, gross/net basis, formula-definition version, and structured
  calculation definition. A missing structured definition (as in legacy or
  manually constructed values) yields no calculation fingerprint, so the
  descriptive comparator withholds the delta. This is a calculation-identity
  primitive; the comparator validates shared run scope, declared data/coverage
  identity, currency, calendar evidence, and calculation compatibility
  separately. Existing
  `calculation_basis` strings remain display-compatible and the formula version
  stays at v6 because this metadata addition does not change metric formulas.
- `lifecycle.py` contains pure attempt/forward state transitions, event
  anomaly classification, and typed monotonic execution-attempt leases.
  Running attempts can acquire a lease, active leases can renew, and expired or
  released leases cannot be renewed; persistence, worker scheduling, and clock
  ownership remain outside the package. `apply_forward_event_observation()`
  advances a forward instance only for contiguous accepted events, preserves
  anomaly cursors, and increments corrections without rewriting prior state.
- `pairing.py` verifies exact keyed common-random draw alignment and emits a
  content-bound receipt that can upgrade sensitivity provenance to
  `verified_paired`; it does not perform statistical inference.
- `recovery.py` defines deterministic, bounded infrastructure recovery. A
  terminal failed attempt can produce a retry plan only for explicitly
  retryable causes and while the attempt limit remains; capped exponential
  backoff is derived from the next ordinal and supplied observation time.
  Successful attempts are no-ops, cancellation is terminal by default, and
  `RecoveryPlan` is content-addressed for idempotent scheduling records.
  `RecoveryPlan.materialize_retry_attempt()` preserves the immutable trial
  identity. Durable compare-and-set, scheduling, worker restart, and engine
  disposal remain adapter responsibilities.
- `events.py` defines content-addressed execution event envelopes, typed
  per-trial/attempt cursors, and pure append decisions. Event timestamps are
  normalized to UTC at construction, so equivalent offset-aware retries retain
  one dataclass value and event identity after transport. Exact prior events
  can be replayed; stale, missing, foreign, or conflicting sequences are
  surfaced without advancing the cursor. PostgreSQL/outbox/Redis adapters
  still own atomic persistence and transport.
- `api_contracts.py` defines stable REST-boundary values for future routes:
  snapshot-bound opaque cursors round-trip deterministically with an integrity
  checksum, page envelopes require consistent continuation cursors, and
  `ApiError` carries a typed code, HTTP status, retryability, request identity,
  and recursively frozen details. Cursor checksums are not authentication;
  authorization and snapshot ownership remain route responsibilities.
- `submissions.py` defines idempotent asynchronous submission requests and
  receipts. Request fingerprints bind the operation, attempt, idempotency key,
  and payload digest while excluding transport timestamps; resolution returns
  202 acceptance/replay or 409 conflict, and contradictory prior receipts fail
  closed. Receipt creation performs no queue, database, or worker I/O.
- `submission_dispatch.py` composes that 202 receipt with the matching worker
  dispatch envelope. Submission and dispatch identities must bind to the same
  attempt, idempotency key, and payload; a receipt retry may repair a missing
  dispatch, but an existing dispatch without a receipt is a conflict. The
  returned receipt ledger and dispatch proposal remain storage-neutral for one
  compare-and-set transaction.
- `outcomes.py` defines ordered accepted/running/succeeded/failed/cancelled
  outcome updates bound to one submission and attempt. Success requires a
  content-addressed result, failures carry a typed `ApiError`, and exact
  repeats replay the existing terminal state while regressions, foreign
  identities, stale timestamps, and conflicting sequences fail closed.
- `lineage.py` defines immutable artifact-manifest lineage edges and
  owner-scoped indexes. Semantic keys exclude recording timestamps for
  idempotency, exact edges replay, changed metadata conflicts, and entries are
  deterministically ordered. Storage adapters must still enforce manifest
  existence, foreign-key constraints, and atomic persistence.
- `runtime.py` defines fail-closed isolation preflight for future strategy
  workers. A profile requires a pinned runtime image, exact vetted dependency
  digests, disabled network, read-only root, dropped capabilities, disabled
  secrets, and positive wall/CPU/memory/output limits; execution requests that
  ask for forbidden access or missing pins are rejected with explicit reasons.
  This contract does not itself create containers or enforce OS limits.
- `conformance.py` defines the engine release/conformance evidence gate. The
  required multi-instrument accounting, native order/fill/cost, deterministic
  replay, lifecycle, and forward-event-tape checks are explicit; complete
  release-candidate evidence is compatibility-only, and only a complete stable
  release can be marked authoritative.
- `result_publication.py` composes conformance, runtime isolation, and exact
  result-artifact integrity into a storage-neutral publish plan. Only a stable
  authoritative build with matching evidence can publish; already-published
  manifests replay idempotently, while build, runtime, conformance, or artifact
  mismatches reject without changing the result record.
- `progress_checkpoint.py` adds restart-safe progress checkpoints retaining
  every applied update fingerprint. Only the next contiguous sequence advances
  state; exact repeats replay, gaps wait for missing updates, and stale or
  conflicting updates fail closed. Durable storage and stream transport remain
  outside this pure contract.
- `workers.py` defines serial backtest and separately typed forward worker
  profiles, content-addressed reservations, deterministic capacity decisions,
  and idempotent release. Unsafe profiles, reused reservation identities, and
  concurrent attempts fail closed; process scheduling, lease heartbeats,
  restart recovery, and engine disposal remain adapter responsibilities.
- `artifact_retention.py` defines immutable owner-scoped retention pins and
  manifest-bound retention state. Pin adds and releases are idempotent; pinned
  classes fail closed without an active pin, while tiered/ephemeral eligibility
  is evaluated only at an explicit timestamp. The contract never deletes,
  moves, or rewrites artifact bytes.
- `lease_observations.py` defines ordered heartbeat/release envelopes and a
  restart-safe lease observation state. Exact retries replay, changed content
  conflicts, gaps/stale sequences remain visible, and expired or released
  leases reject further heartbeats. Lease identity and final heartbeat
  metadata must match; persistence and clock scheduling remain adapter-owned.
- `forward_warmup.py` defines manifest-bound warm-up completion receipts. A
  warming instance can transition to active once, seed its historical cursor,
  and replay the same receipt without rewriting live state; changed receipts,
  mismatched snapshot/carry-in, stale completion times, and cursor overwrite
  attempts fail closed.
- `forward_admission.py` adds active-instance live-event admission with
  content-addressed event identities. Contiguous events advance the existing
  checkpoint, gaps remain buffered for later reconciliation, and duplicate,
  out-of-order, correction, conflict, and exact-replay outcomes stay explicit.
  A completed warm-up cursor is seeded into the admission state so historical
  events cannot be silently replayed.
- `artifact_commit.py` defines an immutable commit ledger for verified
  publication plans. Create-if-absent finalization records one content key,
  exact retries replay it, storage-key collisions conflict, and
  reuse-existing plans fail closed until a committed record is observed. No
  bytes are written or deleted by this contract.
- `execution_summary.py` projects submission, outcome, progress, and result
  publication into one immutable API read model. It enforces identity and
  terminal-phase consistency, requires authoritative publication for success,
  and exposes ready/in-progress/terminal decisions without leaking engine
  handles or mutable worker state.
- `commands.py` defines content-addressed retry and cancellation command
  intents with idempotent receipts. Commands are accepted only when their
  outcome/progress preconditions hold; terminal cancellation, non-failed
  retry, identity mismatch, and reused command content fail closed. Applying a
  cancellation or scheduling a retry remains an adapter responsibility.
- `capability_summary.py` projects data and engine preflight into one stable
  machine-facing summary. It preserves instrument-scoped data gaps,
  engine-model gaps, degradation evidence, executable/ranking flags, and
  authoritative-publication eligibility without recomputing or weakening the
  underlying fail-closed checks.
- `forward_corrections.py` defines additive counterfactual replay commands for
  admitted correction events. Plans retain the original event identity,
  correction identity, warm-up receipt, and immutable pre-correction
  checkpoint basis; exact retries replay, changed content conflicts, and
  unadmitted/mismatched corrections fail closed without rewriting live state.
- `audit.py` defines an immutable aggregate-scoped execution audit journal.
  Entries carry typed event kinds, content-addressed payloads, actor and
  correlation identity, and contiguous sequence numbers. Occurrence timestamps
  are normalized to UTC at construction, keeping equality, identity, and
  monotonic journal checks stable across offset-changing serialization. Exact
  appends replay; gaps, stale sequence content, same-sequence conflicts,
  foreign aggregates, and timestamp regressions remain explicit without
  mutating the journal. A future PostgreSQL/outbox adapter must persist the
  returned decision atomically; this contract never writes or transports audit
  records.
- `outbox.py` defines immutable transactional-outbox messages and state.
  Request identity conflicts, content duplicates, deterministic pending order,
  and publish acknowledgements are resolved without I/O. Exact enqueue and
  acknowledgement retries replay idempotently; unknown acknowledgements reject.
  Message identity excludes scheduling timestamps, while the full record retains
  them for auditability. PostgreSQL transactionality and Redis transport remain
  adapter responsibilities.
- `audit_outbox.py` links an audit entry to its transport envelope through one
  pure atomic staging resolution. The envelope must carry the audit entry
  identity; gaps, conflicts, or rejects return both original states so an
  adapter cannot commit one side alone. A successful resolution provides the
  journal and outbox states for one PostgreSQL transaction, while a repeated
  pair replays idempotently.
- `legacy.py` defines digest-only preservation and explicit import reports for
  legacy definitions and results. Adapter-supplied mapping assessments are
  retained with the original record; unsupported imports remain inspectable,
  supported imports expose a converted identity, exact retries replay, and
  changed payload or mapping content conflicts. Reports permanently reject any
  replay-equivalence claim.
- `search_state.py` defines an immutable candidate-level search checkpoint.
  Candidates retain their scientific trial fingerprint while infrastructure
  attempts can start, fail, and retry. Active-attempt conflicts, terminal
  result conflicts, cancellation requests, and monotonic timestamps fail
  closed; exact starts, terminal receipts, and cancellation retries replay.
  Cancellation blocks new work but still requires explicit terminal receipts,
  and the module exposes no ranking or profitability verdict.
- `coverage.py` verifies a provider-supplied coverage attestation against every
  frozen `DataSeriesManifest` dimension: evidence and series digests, interval,
  row count, instrument/event semantics, session/feed, adjustment and
  corporate-action policy. Incomplete or gapped claims reject explicitly, and
  the report retains deterministic evidence identities. The verifier performs
  no provider I/O, repair, or inference; the adapter must supply the attestation
  before execution is enabled.
- `snapshot_coverage.py` composes those per-series checks into the snapshot
  admission boundary. It requires exactly one attestation for every frozen
  series, rejects missing, duplicate, unexpected, incomplete, or mismatched
  evidence, and returns a deterministic snapshot-bound verification receipt.
  Provider acquisition and execution adapters still own fetching the evidence
  and enforcing this receipt before a run starts.
- `runtime_execution.py` binds a strategy runtime request to its package/source,
  frozen input bundle, declared entrypoint, and isolation profile. Allowed
  requests advance through ordered accepted/running/terminal receipts; exact
  retries replay, terminal conflicts fail closed, and successful output size is
  checked against the declared limit. This is a protocol and receipt boundary,
  not container enforcement or an engine invocation.
- `admission.py` composes an execution authorization, accepted runtime
  preflight, and serial worker profile into one idempotent admission decision.
  It binds the worker reservation to the attempt, runtime profile, and request
  identity; exact retries replay only while the receipt's reservation remains
  active. Saturation, conflicting attempt content, profile/worker drift, and a
  reservation without a matching receipt fail closed. Ledger and worker-pool
  updates are returned together for a future adapter transaction; no queue,
  persistence, process, or engine I/O occurs here.
- `search_dispatch.py` stages candidate start, execution admission, and queue
  idempotency as one storage-neutral resolution. A saturation, cancellation,
  authorization/runtime rejection, or dispatch conflict returns the original
  candidate, admission ledger, and worker pool, preventing orphaned running
  work. Exact retries replay the candidate, admission, and dispatch evidence;
  a newly admitted attempt cannot silently reuse an existing queue message.
  Persistence and queue publication remain adapter-owned.
- `worker_recovery.py` composes an admitted attempt's lease, worker reservation,
  and deterministic infrastructure-retry plan. It releases capacity and
  materializes a new queued attempt against the same scientific trial for
  crash/expiry/transient failures, while successful or non-retryable attempts
  close without a retry. Its content-addressed recovery ledger replays exact
  release/retry requests and reports conflicting evidence instead of trying to
  release a slot twice. Recovery also applies the ordered lease-release
  observation and returns it with the released pool; missing admission
  evidence, worker drift, invalid lease-expiry claims, and missing retry
  identities fail closed; no attempt transition, scheduling, or engine
  invocation is performed.
- `result_completion.py` composes terminal runtime, outcome, progress, result
  publication, and content-addressed artifact-commit evidence. It resolves all
  artifact plans against a working ledger but returns the original ledger on
  any conflict or rejection, preventing partial finalization. Exact completion
  retries replay only when every recorded commit remains present; successful
  publication replays without a prior completion receipt are rejected. This is
  an adapter transaction boundary and performs no byte writes, result publish,
  process control, or engine I/O.
- `forward_event_transaction.py` composes live-event admission with the
  correction replay command boundary. Ordinary events retain the existing
  accepted/gap/duplicate/out-of-order decisions; corrections are committed
  only when a separately identified counterfactual replay plan also resolves.
  Missing commands, changed event or command content, and invalid replay
  evidence return the original live checkpoint, so a correction cannot be
  observed without an auditable replay basis.
- `forward_event_dispatch.py` binds admitted forward events to content-addressed
  worker dispatch envelopes. Accepted and buffered-gap events enqueue work;
  duplicate/out-of-order observations remain non-dispatching, and correction
  dispatches include the replay-plan identity. Queue idempotency conflicts and
  payload drift return the original forward checkpoint, preventing a worker
  message from being published for state that was not atomically admitted.
- `execution_event_transaction.py` links each canonical execution-event append
  to its audit-journal entry and transactional-outbox message. Event sequence
  gaps, audit gaps, identity mismatches, and outbox conflicts return every
  original state, while exact retries replay only when all three identities
  agree. Persistence adapters still own the compare-and-set transaction and
  transport; this contract performs no I/O or engine work.
- `api_resources.py` defines typed public resource identifiers, immutable
  resource documents, and snapshot-bound collection envelopes for the future
  versioned REST surface. Collection items, resource types, opaque cursors, and
  snapshot digests must agree before a page can be returned; attributes,
  relationships, and metadata are frozen and content-addressed.
- `api_router.py` provides a registration-neutral `/strategy-lab/v2` FastAPI
  router factory. It serializes resources, exact Decimal/timestamp values, and
  typed errors; validates cursor ownership at the collection boundary; exposes
  static strategy-source validation; and delegates idempotent submissions plus
  retry/cancellation commands to an injected adapter. The adapter must scope
  reads to the authenticated principal and atomically persist receipts before
  returning them. Router registration, authentication dependency selection,
  PostgreSQL compare-and-set, Redis dispatch, and worker effects remain shared
  integration concerns. Collection adapters receive the route-generated request
  identity and must return it unchanged in the collection envelope, preventing
  response evidence from being detached from the originating request.
- `postgres_resources.py` supplies the read-only persistence bridge for that
  boundary. It projects authenticated-owner aggregate snapshots into immutable
  resource documents, orders pages deterministically, and binds every cursor to
  the complete visible-set digest. Missing or foreign rows are not disclosed;
  malformed owner/resource/relationship state and snapshot drift fail closed.
  The adapter is registration-neutral and does not create migrations, mutate
  aggregates, or dispatch work.
- `postgres_submission.py` maps idempotent submission receipts and dispatch
  intents to an owner-scoped additive PostgreSQL transaction. Exact retries
  replay the durable receipt, a missing dispatch can be repaired from that
  receipt, changed content conflicts, and different principals remain isolated.
  It validates payload/fingerprint identity and stages no Redis message until a
  later outbox relay; table creation and application wiring remain gated.
- `postgres_commands.py` maps retry/cancellation commands to owner-scoped,
  transactionally locked PostgreSQL receipts. It resolves the latest injected
  outcome/progress context through the engine-neutral command state machine,
  replays exact idempotent commands, rejects content drift and terminal
  preconditions with typed API errors, and verifies receipt fingerprints before
  use. The adapter persists no worker side effect; migrations, wiring, and
  execution dispatch remain gated.
- `postgres_event_transaction.py` maps the canonical execution-event,
  append-only audit, transactional-outbox, and stream-cursor contract to one
  SQLAlchemy async transaction. It locks and re-authenticates existing rows,
  enforces contiguous sequence/cursor identity, persists all four linked rows
  atomically, supports exact replay and caller cursor compare-and-set, and
  leaves Redis publication and worker effects to later adapters; migrations
  and application registration remain gated.
- `postgres_execution_state.py` maps owner-scoped outcome and progress
  checkpoints to additive PostgreSQL rows. It locks both attempt records,
  preserves monotonic outcome transitions and progress update fingerprints,
  applies combined updates atomically, exposes an authenticated command-state
  reader, and fails closed on partial or tampered state. It remains a
  registration-neutral adapter; migrations, route wiring, and worker effects
  are still shared integration concerns.
- `postgres_worker_state.py` maps immutable worker profiles, serial reservation
  capacity, and execution-attempt lease observations to additive PostgreSQL
  rows. Profile and lease identities are re-authenticated before use; active
  reservations are guarded by a database uniqueness index and compare-and-set
  release, while ordered heartbeat/release observations are applied atomically
  with exact replay and gap/stale/conflict decisions. The adapter performs no
  process scheduling, clock polling, engine disposal, queue publication, or
  migration/application registration; those remain shared integration gates.
- `postgres_artifact_retention.py` maps manifest-bound retention state and
  owner-scoped immutable pins to additive PostgreSQL rows. Pin add/release
  operations update the pin and state fingerprints atomically, exact retries
  replay, and retention eligibility is resolved at an explicit observation time
  without deleting or tiering bytes. Malformed, foreign, tampered, or
  compare-and-set-racing rows fail closed; artifact publication, migrations,
  authorization, and storage lifecycle effects remain outside this adapter.
- `postgres_artifact_commit.py` maps immutable artifact-publication commit
  records to an additive PostgreSQL ledger. It locks and authenticates the
  complete commit set, preserves create-if-absent semantics and exact retries,
  and lets storage-key collisions return the pure conflict decision before any
  write. Artifact bytes, manifest validation, retention policy, migrations, and
  application wiring remain outside this registration-neutral adapter.
- `postgres_lineage.py` maps owner-scoped immutable artifact-lineage edges to
  an additive PostgreSQL table. Semantic keys provide idempotent replay and
  changed-edge conflicts; rows are locked, fingerprint-authenticated, and
  deterministically ordered before the pure lineage index is returned. The
  adapter does not certify manifests, create foreign-key migrations, authorize
  owners, or publish artifact bytes.
- `postgres_forward_state.py` maps persistent broker-free forward instances,
  one-time historical warm-up receipts, and content-addressed seen-event
  identities to additive PostgreSQL tables. Lifecycle transitions, warm-up
  activation, and live-event admission lock the owner-scoped rows and use
  authenticated compare-and-set updates; exact retries replay while duplicate,
  gap, out-of-order, and correction observations remain represented in the
  checkpoint. Its atomic event-transaction path persists a correction's
  counterfactual replay plan in the same transaction as the event checkpoint,
  so a correction can never be admitted without replay evidence. The adapter
  never fetches provider data, submits broker orders, starts workers, or applies
  migrations.
- `postgres_search_state.py` maps immutable experiment queues and candidate
  checkpoints to additive PostgreSQL tables. Candidate starts/retries,
  terminal receipts, and cancellation requests delegate to the pure search
  state machine and persist only through owner-scoped row locks and
  compare-and-set fingerprints. Exact retries replay, while candidate or
  experiment tampering fails closed; dispatch transport and worker effects
  remain separate integration concerns.
- `postgres_legacy.py` maps digest-only legacy import records and compatibility
  assessments to an owner-scoped additive PostgreSQL registry. Original
  metadata and mapping evidence are authenticated before each read; supported
  and unsupported imports are preserved, exact retries replay, and changed
  payload or mapping content returns the pure conflict decision. The adapter
  never reads legacy payload bytes or claims replay parity, and migrations,
  authorization, and route wiring remain shared integration concerns.
- `postgres_coverage.py` maps provider-supplied coverage attestations to an
  owner-scoped additive PostgreSQL evidence registry. Series/evidence digests,
  interval and row-count semantics, adjustment/session/feed claims, and
  attestation fingerprints are re-authenticated on read; exact registration
  retries replay and changed series content conflicts. Provider fetching,
  repair, snapshot admission, migrations, and application authorization stay
  outside this registration-neutral adapter.
- `postgres_capability.py` maps immutable data/engine capability summaries to an
  owner-scoped additive PostgreSQL read model. Report and binding identities
  are the stable key; gaps, degradations, executable/ranking flags, and
  authoritative-publication eligibility are serialized and re-authenticated so
  altered projections conflict instead of silently replacing preflight
  evidence. Capability calculation, provider entitlement, engine registration,
  migrations, and API authorization remain outside the adapter.
- `postgres_acquisition.py` maps provider-produced acquisition receipts to an
  owner-scoped additive PostgreSQL handoff registry keyed by the preflight
  request identity. Frozen snapshot, provider snapshot, coverage-resolution,
  and opaque provider-receipt digests are authenticated before reuse; exact
  retries replay and changed handoffs conflict. Fetching, repair, snapshot
  creation, provider policy, migrations, and execution admission remain
  outside this adapter.
- `postgres_snapshot_coverage.py` maps snapshot-level coverage verification
  receipts to an owner-scoped additive PostgreSQL table. Per-series reports,
  missing/unexpected digests, rejection reasons, and the complete resolution
  fingerprint are re-authenticated on read; exact retries replay and changed
  resolutions conflict. Provider fetch/repair, attestation lookup, snapshot
  creation, migrations, and execution admission remain outside the adapter.
- `postgres_execution_summary.py` maps immutable execution-status projections
  to an owner-scoped additive PostgreSQL read model. Outcome/progress state
  identities are append-only, exact retries replay, and changed content for a
  checkpoint conflicts; reads authenticate the projection and select the latest
  state for an attempt while preserving history. Submission/outcome persistence,
  result publication, migrations, authorization, and route wiring remain
  separate integration concerns.
- `postgres_result_completion.py` maps terminal result completion and the
  shared artifact commit ledger into one additive PostgreSQL transaction.
  Runtime/outcome/progress/publication evidence is resolved by the pure
  completion contract before new commits and the completion receipt are
  inserted; artifact conflicts leave both ledgers unchanged, and exact retries
  replay the existing receipt. Artifact bytes, migrations, authorization, and
  worker wiring remain outside this registration-neutral adapter.
- `postgres_result_publication.py` maps immutable publish/replay/reject plans to
  an owner-scoped additive PostgreSQL evidence table. Plan fingerprints,
  attempt/result/reproduction/build identities, and rejection reasons are
  authenticated on reads; exact retries replay while distinct decisions remain
  separate audit evidence. Publication bytes, completion coordination,
  migrations, authorization, and route wiring remain outside the adapter.
- `postgres_runtime_execution.py` maps accepted runtime state and immutable
  sandbox update receipts to owner-scoped additive PostgreSQL tables. Runtime
  transitions are resolved through the pure monotonic contract, committed with
  compare-and-set state updates, and replayed by exact sequence/fingerprint;
  sandbox materialization commits running and terminal evidence atomically.
  Process execution, artifact bytes, migrations, authorization, and official
  result publication remain separate integration concerns.
- `postgres_result_materialization.py` retains immutable `RunResultManifest`
  payloads as owner-scoped canonical JSON projections. Pure manifest validation
  runs before registration, attempt identities are single-bound, exact retries
  replay, changed candidates conflict, and payload/record fingerprints are
  authenticated on every read. Nested manifest decoding, artifact bytes,
  migrations, authorization, and publication remain separate integration
  concerns.
- `postgres_runtime_receipts.py` retains immutable strategy-runtime request and
  isolation-preflight evidence as owner-scoped canonical projections. Request
  and preflight payloads are independently content-addressed, exact retries
  replay, changed content conflicts against the same attempt/request, and
  rejected preflight reasons remain inspectable without exposing secrets or
  starting a process.
- `postgres_metrics.py` retains immutable `MetricSet` summaries as
  owner-scoped canonical projections. Metric-set payloads and compact value
  summaries are content-addressed, one attempt cannot silently replace a
  prior metric set, exact retries replay, and tampering is detected before
  metric data can be read by result/API adapters.
- `storage.py` defines the persistence adapter boundary: versioned aggregate
  snapshots, content-addressed create/update mutations, compare-and-set
  preconditions, deterministic transaction ordering, and idempotent receipts.
  Conflicts and missing aggregates return the original state, while exact
  request retries replay the recorded committed set. PostgreSQL mapping and
  transaction execution remain outside this pure contract.
- `artifact_store.py` provides the local-first raw-byte adapter for immutable
  content-addressed artifacts. It verifies manifests before publication, uses
  same-directory temporary files and atomic create-if-absent links, deduplicates
  concurrent writers, makes published files read-only, and re-verifies every
  read so tampering or path/symlink escapes fail closed.
- `artifacts.py` and `ArtifactManifest` enforce typed byte lengths, retention
  classes, and authenticated integrity receipts. Verified receipts cannot claim
  success with mismatched observed bytes, and failure reasons are canonicalized
  before publication planning so equivalent corruption evidence has one stable
  identity.
- `sandbox.py` builds deterministic, shell-free Docker argv plans only after
  runtime preflight succeeds. Plans pin the runtime image digest, disable the
  network, make the root read-only, drop capabilities, disable privilege
  escalation and secrets, run as an unprivileged user, mount inputs read-only,
  bound output/CPU/memory/PID limits, and carry the explicit wall-time budget;
  execution remains a worker adapter responsibility.
- `sandbox_execution.py` executes only those validated argv plans with
  `shell=False`, a minimal secret-free environment, process-group cleanup,
  explicit wall-time enforcement, and bounded stdout/stderr capture. The
  executor revalidates the complete hardened argv immediately before spawn so
  manually forged plans cannot add host networking, privilege, writable-root,
  or unbounded-process controls. Typed results distinguish success, non-zero
  exit, timeout, output overflow, and process-start failure; Docker remains the
  production command boundary.
- `backend/strategy_runtime/` provides the restricted invocation runner used
  inside that command boundary. It binds source bytes to the declared digest,
  repeats static source preflight, exposes only the engine-neutral SDK symbols
  and a vetted standard-library import surface, and validates every emitted
  intent against the manifest before returning a content-addressed result.
  Source/entrypoint/output failures are typed without returning exception text;
  the package still requires the hardened container for actual isolation. A
  `StrategyInvocationSession` loads one strategy instance for an entire worker
  lifetime, preserving state across monotonically advancing contexts while
  pinning seed/parameter identity and rejecting context-scope drift. Its
  explicit JSON wire protocol preserves typed values and fingerprints request
  and result envelopes. The batch protocol carries a non-empty sequence of
  contexts and an independently fingerprinted sequence of typed results, so an
  isolated worker can retain one strategy instance across a replay. The
  `run_strategy_events()` primitive stops at the first typed rejection/failure;
  `python -m strategy_runtime` accepts either the single-event or batch
  envelope, atomically publishes the matching typed result envelope, and uses
  status-based exit codes. Wire timestamps are normalized to UTC so equivalent
  instants produce byte-identical envelopes. Failure evidence is a versioned,
  exception-type-only digest; exception text and process-specific repr values
  never affect the published result. The SDK's `MarketEvent` and
  `StrategyContext` also normalize aware event times to UTC before scope and
  fingerprint checks, so direct SDK callers cannot reintroduce offset-specific
  identity drift. SDK manifests canonicalize dependency and field declaration
  order, so equivalent contracts also retain one stable manifest fingerprint.
  The dedicated worker image/entrypoint and Docker activation are still
  separate integration gates.
- `custom_metrics.py` provides the matching process-local custom-metric
  boundary. A source-bound callable receives only recursively frozen Decimal
  observations and JSON parameters, returns one finite Decimal, and is wrapped
  as a versioned `MetricValue` with input/source evidence. Static violations,
  source drift, malformed outputs, and runtime exceptions are typed without
  exposing exception text; production use still requires the hardened
  no-network container.
- Every invocation result also carries the immutable SDK manifest fingerprint
  used for validation, allowing a host adapter to reject a result produced
  under a different strategy contract even when source/context identities are
  otherwise reusable.
- Runtime request serialization/deserialization now rejects any source bytes
  whose content digest differs from the immutable SDK manifest. This keeps
  malformed source/manifest pairs out of mounted bundles instead of deferring
  the contradiction to strategy invocation.
- `engine_execution.py` binds the final Nautilus invocation gate to execution
  authorization, runtime preflight, sandbox request identity, data-snapshot
  identity, hardened sandbox argv validation, and complete conformance
  evidence. Only a compatible Nautilus build can run; authoritative runs
  additionally require stable release evidence and an authoritative
  authorization, and no engine process is started while any gate is missing.
- `redis_transport.py` publishes dispatch envelopes to Redis Streams through a
  Lua compare-and-set script. The idempotency key and stream append are staged
  atomically, exact retries replay, changed payloads conflict, and failed
  `XADD` operations remove their marker. It also creates consumer groups
  idempotently, decodes content-addressed entries, reclaims idle pending
  deliveries, and acknowledges entries with typed failure evidence. Redis
  remains transport-only; the authoritative state and outbox records stay in
  the persistence adapter.
- `outbox_relay.py` binds one authoritative outbox message to that Redis
  transport. It uses the message's semantic identity as the transport
  idempotency key and proposes the published outbox state only after enqueue or
  exact replay; Redis conflicts and failures preserve the pending state so a
  later relay can retry safely.
- `worker_consumer.py` provides the bounded Redis worker pump. It ensures the
  consumer group, reclaims idle deliveries before reading new entries, and
  requires an explicit handler receipt. Only a content-matched completed
  receipt is acknowledged; retry, rejection, handler-content drift, and Redis
  acknowledgement failure leave the delivery unacknowledged with typed
  evidence.
- `postgres_storage.py` maps the compare-and-set aggregate contract to one
  SQLAlchemy async transaction. It locks requested aggregate/receipt rows,
  preserves canonical state identity through a versioned JSON codec, uses
  idempotent inserts and guarded updates, and rolls back on concurrent races.
  Its read methods return authenticated canonical aggregate snapshots in
  deterministic key order for the resource bridge. It exposes the future
  additive schema contract but never creates tables or registers models;
  migrations remain a shared-path gate.
- `nautilus_runner.py` is the final process handoff after the Nautilus
  execution gate. Rejected, non-Nautilus, or sandbox-mismatched plans return
  before process creation; ready plans execute only through the bounded sandbox
  adapter and preserve authoritative status only for successful gated runs.
- `runtime_result_adapter.py` materializes one bounded sandbox result into the
  monotonic runtime execution state. It verifies command-plan and request
  identity, records bounded stdout digest/size for success or typed error
  identity for failure, replays exact terminal evidence, and rejects conflicting
  terminal evidence. Gated Nautilus results are envelope-checked before this
  materialization; rejected pre-process plans remain admission failures rather
  than strategy failures. This is runtime evidence only; official result
  artifacts still require the result-publication gates.
- `execution_orchestration.py` binds authorization, worker admission, runtime
  preflight/state, sandbox planning, and the gated Nautilus plan into one
  immutable worker handoff. It rejects identity drift, unhardened sandbox
  plans, already-started runtime state, output-limit changes, and unauthorized
  authoritative execution before any process or queue adapter is called.
- `worker_execution.py` revalidates that handoff immediately before process
  creation, including the admission's active serial `WorkerPoolState`,
  reservation identity, and active `LeaseObservationState` at an explicit
  `started_at`, invokes only the gated Nautilus runner, and returns typed
  process plus runtime evidence. Stale/rejected handoffs, released capacity,
  or expired leases cannot spawn; evidence that outlives its lease is rejected
  before runtime materialization. Successful, failed, and runtime-rejected
  outcomes remain storage-neutral for a later compare-and-set transaction. The
  typed resolution also rejects a contradictory worker decision/runtime-result
  pair before it can be settled.
- `worker_settlement.py` closes the serial worker lifecycle after any bounded
  handoff, including a pre-process rejection. It verifies the orchestration
  plan is still bound to the admission and pool profile, applies a deterministic
  ordered lease-release observation, releases the matching reservation only
  once, and records content-addressed evidence. Exact retries replay an
  already-released reservation and lease; changed evidence, an active pool with
  an existing receipt, an expired lease, or a missing/mismatched reservation
  fails closed and leaves recovery to the retry path.
- `worker_terminal.py` composes the terminal public outcome/progress projection
  with worker pool and lease settlement. It returns a committed proposal only
  when both terminal evidence and capacity release accept; a missing result,
  expired lease, settlement conflict, or pre-process worker rejection leaves
  every original state unchanged for the recovery or adapter path. Exact
  terminal retries replay only when both public and worker receipts match.
- `result_materialization.py` binds engine-neutral result evidence to an
  immutable `RunResultManifest`. Trial, attempt, metric, snapshot, package, and
  output-artifact identities must agree; exact retries replay an existing
  manifest and changed content conflicts. Package and artifact evidence is
  canonicalized before comparison. The manifest remains unpublished until
  artifact-integrity and authoritative publication gates succeed.
- `execution_terminal.py` projects terminal runtime evidence into the public
  outcome and progress streams as one storage-neutral decision. Successful
  runtimes require an attempt-bound result manifest, failures require a typed
  `ApiError`, cancellation requires an explicit cancellation request, and
  matching terminal retries replay while half-terminal or contradictory state
  is rejected.
- `conformance_fixtures.py` defines typed expected/observed digest evidence for
  every required engine check. Suites reject duplicate checks and untruthful
  pass claims, require complete coverage before evidence construction, and feed
  the existing stable-release gate without importing or starting Nautilus.
- `tests/` holds focused tests adjacent to the new package because the active
  provider workstream owns `backend/tests/`.

This SDK and static preflight are not a security boundary. Trusted local Python
strategies still need the separately implemented isolated runtime (no network,
read-only filesystem, no secrets, and enforced resource/time/output limits).
The package-local API router imports FastAPI only to expose a registration-neutral
factory; it imports no provider, ORM, queue, or Nautilus modules and performs no
persistence, dispatch, or engine I/O.

Run the focused suite from `backend/` with:

```sh
rtk uv run pytest app/strategy_lab_v2/tests -q --override-ini addopts=
rtk uv run ruff check app/strategy_lab_v2
rtk uv run mypy app/strategy_lab_v2
```

The override disables the repository-wide coverage threshold for this focused
path; it is not a substitute for final full-backend coverage gates.

The combined backend gate also collects the package-owned tests:

```sh
make test-backend-coverage
```

This keeps coverage honest across the package without moving tests into the
provider-owned `backend/tests` tree or adding coverage exclusions. It remains a
repository-wide integration gate and still requires Docker-backed PostgreSQL
and Redis services.

## Deferred integration gates

Do not add shared models/migrations, router registration, worker/task entrypoints,
global dependencies, lockfile changes, Compose services, or frontend work until
the provider-platform, ETF, and TC2000 branches reach staging and their shared
paths are semantically reconciled. Consume their canonical acquisition,
point-in-time membership, and immutable CodeVersion/Study Lab contracts rather
than building duplicate adapters or authoring flows. The package-local router
factory is intentionally unregistered until that reconciliation; its injected
adapter remains the only place allowed to authorize, persist, enqueue, or
execute a request.

Nautilus is the planned authoritative simulator, isolated from the legacy 1.x
environment. Production execution remains disabled until a stable v2 version is
pinned in a separate runtime and passes platform conformance for
multi-instrument accounting, native execution/cost models, deterministic replay,
engine lifecycle, and backtest/forward event-tape parity. Release candidates
may be used as compatibility evidence only. The local Compose worker/storage
and API phases follow shared-path reconciliation; the TC2000-native UI and any
deployed shadow soak are separate authorization boundaries.
