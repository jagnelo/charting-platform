# Strategy Lab v2 backend

Strategy Lab v2 is a local-first backend sandbox for reproducible portfolio
backtests, search and walk-forward experiments, and persistent broker-free
forward/shadow evaluation. It is a new versioned platform contract; it does not
extend or reinterpret the current Strategy Lab runner.

## Execution contract

An immutable strategy version declares its SDK version, exact dependency
artifacts, parameter schema/defaults, and content digest. A portfolio version
binds strategy versions to instrument scopes, capital budgets, priorities,
rebalancing, and shared risk policy. Before execution, a capability preflight
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
  forward-instance records. Snapshot preflight matching includes event type and
  semantic series requirements; manifest interval continuity is structural
  validation, not a substitute for upstream coverage-attestation verification.
- `capabilities.py` implements strict/degraded capability-cell preflight.
- `sdk.py` exposes declared read-only inputs and typed order/target-position
  intents. Every declared field is required on each provided event; intent
  validation checks the strategy's declared instrument scope; allocation and
  risk controls remain host responsibilities.
- `experiments.py` expands deterministic search/scenario plans and
  leakage-aware walk-forward folds.
- `metrics.py` computes versioned Decimal summaries from authoritative engine
  equity and trade-P&L series, recording basis, units, samples, annualization,
  and null reasons.
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
uv run pytest app/strategy_lab_v2/tests -q --override-ini addopts=
uv run ruff check app/strategy_lab_v2
uv run mypy app/strategy_lab_v2
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
