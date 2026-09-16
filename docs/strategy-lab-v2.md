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
core plans deterministic schedule boundaries from a complete pinned calendar;
applying them to allocation or engine orders/fills remains deferred. A
`TargetPositionIntent.target_fraction` is a fraction of the emitting component's
share of current account equity; the host multiplies it by that component's
capital weight. Targets are bounded by the component's capital budget unless an
explicit component-leverage limit is raised in the policy. Component targets
are resolved together at one event, conflict
handling is explicit (`reject`, `highest_priority`, or `sum_component_targets`),
and gross risk is calculated before same-instrument netting. Shared gross, net,
instrument, component, open-instrument-count, and short-position limits fail the
whole candidate batch closed; targets are never silently scaled. Raw quantity
`OrderIntent`s remain unroutable until an engine adapter supplies authoritative
instrument economics, FX conversion, and product-appropriate risk valuation.
Risk calculations use a content-addressed, per-product risk-model binding. The
current registry supports only cash-equity signed base notional; unsupported or
unregistered products, including futures and options, fail closed. These
notional concentration caps are not a complete market, margin, liquidity, or
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
before execution is enabled. Until that adapter exists, snapshot construction
trusts the upstream assertion and does not verify the attestation payload.
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
- `capabilities.py` implements strict/degraded capability-cell preflight.
  `execution_capabilities.py` binds that data decision to a registered engine
  build and conformance fingerprint, failing closed when product, execution,
  or account semantics are not supported. Non-authoritative engines may be
  executable for compatibility evidence but cannot publish authoritative
  results.
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
  intents. Every declared field is required on each provided event; intent
  validation checks the strategy's declared instrument scope.
- `strategy_validation.py` performs deterministic static source preflight before
  a strategy package can reach a future runtime. It rejects disallowed imports,
  relative imports, dynamic-code/file/network calls, and private-object
  introspection, while binding the result to the exact source digest. This is
  an early rejection layer only; it is not a substitute for the separately
  required isolated runtime and resource controls.
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
  Explicit zero targets are preserved. The only registered instrument risk
  model is cash-equity market value as signed base notional. Current exposure
  snapshots bind opaque valuation evidence which the future adapter must verify;
  futures, options, FX, crypto, and other models are not currently supported.
  This pure module does not create or route engine orders.
- `rebalance.py` validates complete local-date calendar coverage with explicit
  trading/closed days, official trading-date labels, UTC session segments,
  timezone and tzdb versions, and source evidence. It deterministically schedules
  per-session, ISO-weekly, monthly, quarterly, or yearly boundaries using the
  first/last actual session and session-open-before-events or
  session-close-after-events timing. Calendar identity is content-addressed;
  weekly/monthly/etc. schedules require complete bucket coverage so missing
  dates cannot be silently treated as holidays. DST/overnight timing is carried
  by explicit UTC instants. The output is only a decision boundary; it does not
  imply same-price fills, infer missed events, fetch calendars, or create orders.
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
  output is descriptive only: it does not rank or average candidates or
  replicates, estimate significance, or claim paired inference. A shared
  snapshot binds coverage-evidence digests as claims; this engine-neutral
  comparator cannot authenticate their referenced documents.
  The scenario digest binds the declared scenario but is not a separate typed
  evaluation-window contract. `calculate_paired_metric_metrics()` consumes
  aligned keyed observations plus a verified receipt and returns descriptive
  baseline/variant means, nearest-rank delta median, extrema, and sample
  deviation. The receipt and observations establish provenance/alignment but
  no inferential model or significance claim is made.
  `EvaluationWindow` is an immutable trial-bound interval with an optional
  warm-up start. Its fingerprint participates in trial identity and in
  sensitivity measurement scope, so variants with different evaluation or
  warm-up periods are rejected as incomparable rather than silently mixed.
  Replicates are explicit; infrastructure retries remain attempts of the same
  scientific trial.
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
  Trusted paired inference remains deferred.
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
  inference. Remaining gaps include trusted paired inference.
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
  per-trial/attempt cursors, and pure append decisions. Exact prior events can
  be replayed; stale, missing, foreign, or conflicting sequences are surfaced
  without advancing the cursor. PostgreSQL/outbox/Redis adapters still own
  atomic persistence and transport.
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
  correlation identity, and contiguous sequence numbers. Exact appends replay;
  gaps, stale sequence content, same-sequence conflicts, foreign aggregates,
  and timestamp regressions remain explicit without mutating the journal. A
  future PostgreSQL/outbox adapter must persist the returned decision
  atomically; this contract never writes or transports audit records.
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
  close without a retry. Missing admission evidence, worker drift, invalid
  lease-expiry claims, and missing retry identities fail closed; no attempt
  transition, scheduling, or engine invocation is performed.
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
- `sandbox.py` builds deterministic, shell-free Docker argv plans only after
  runtime preflight succeeds. Plans pin the runtime image digest, disable the
  network, make the root read-only, drop capabilities, disable privilege
  escalation and secrets, run as an unprivileged user, mount inputs read-only,
  bound output/CPU/memory/PID limits, and carry the explicit wall-time budget;
  execution remains a worker adapter responsibility.
- `sandbox_execution.py` executes only those validated argv plans with
  `shell=False`, a minimal secret-free environment, process-group cleanup,
  explicit wall-time enforcement, and bounded stdout/stderr capture. Typed
  results distinguish success, non-zero exit, timeout, output overflow, and
  process-start failure; Docker remains the production command boundary.
- `engine_execution.py` binds the final Nautilus invocation gate to execution
  authorization, runtime preflight, sandbox request identity, data-snapshot
  identity, and complete conformance evidence. Only a compatible Nautilus
  build can run; authoritative runs additionally require stable release
  evidence and an authoritative authorization, and no engine process is
  started while any gate is missing.
- `conformance_fixtures.py` defines typed expected/observed digest evidence for
  every required engine check. Suites reject duplicate checks and untruthful
  pass claims, require complete coverage before evidence construction, and feed
  the existing stable-release gate without importing or starting Nautilus.
- `tests/` holds focused tests adjacent to the new package because the active
  provider workstream owns `backend/tests/`.

This SDK and static preflight are not a security boundary. Trusted local Python
strategies still need the separately implemented isolated runtime (no network,
read-only filesystem, no secrets, and enforced resource/time/output limits).
The new package imports no provider, ORM, FastAPI, queue, or Nautilus modules and
performs no I/O.

Run the focused suite from `backend/` with:

```sh
rtk uv run pytest app/strategy_lab_v2/tests -q --override-ini addopts=
rtk uv run ruff check app/strategy_lab_v2
rtk uv run mypy app/strategy_lab_v2
```

The override disables the repository-wide coverage threshold for this focused
path; it is not a substitute for final full-backend coverage gates.

## Deferred integration gates

Do not add shared models/migrations, router registration, worker/task entrypoints,
global dependencies, lockfile changes, Compose services, or frontend work until
the provider-platform, ETF, and TC2000 branches reach staging and their shared
paths are semantically reconciled. Consume their canonical acquisition,
point-in-time membership, and immutable CodeVersion/Study Lab contracts rather
than building duplicate adapters or authoring flows.

Nautilus is the planned authoritative simulator, isolated from the legacy 1.x
environment. Production execution remains disabled until a stable v2 version is
pinned in a separate runtime and passes platform conformance for
multi-instrument accounting, native execution/cost models, deterministic replay,
engine lifecycle, and backtest/forward event-tape parity. Release candidates
may be used as compatibility evidence only. The local Compose worker/storage
and API phases follow shared-path reconciliation; the TC2000-native UI and any
deployed shadow soak are separate authorization boundaries.
