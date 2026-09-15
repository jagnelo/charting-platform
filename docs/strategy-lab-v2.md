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
- `capabilities.py` implements strict/degraded capability-cell preflight.
- `sdk.py` exposes declared read-only inputs and typed order/target-position
  intents. Every declared field is required on each provided event; intent
  validation checks the strategy's declared instrument scope.
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
  account/component P&L records. Event and fill observations are scoped to one
  run attempt so metrics cannot silently combine separate retries. Engine adapters must provide the
  evidence; the core does not perform FX conversion, infer costs, or infer P&L
  attribution from position weights.
- `experiments.py` expands deterministic search/scenario plans and
  leakage-aware walk-forward folds.
- `metrics.py` v4 computes Decimal account P&L/return, drawdown duration, Ulcer,
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
  after explicit external flows; returns are null for incomplete period coverage
  and when flows occur until a time-weighted return method is selected. Remaining
  gaps include irregular-time annualized metrics, margin/capital utilization,
  financing outside fill reports, rolling series, distributions, and sensitivity.
- `lifecycle.py` contains pure attempt/forward state transitions and event
  anomaly classification.
- `tests/` holds focused tests adjacent to the new package because the active
  provider workstream owns `backend/tests/`.

This SDK is not a security boundary. Trusted local Python strategies still need
the separately implemented isolated runtime (no network, read-only filesystem,
no secrets, and enforced resource/time/output limits). The new package imports
no provider, ORM, FastAPI, queue, or Nautilus modules and performs no I/O.

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
