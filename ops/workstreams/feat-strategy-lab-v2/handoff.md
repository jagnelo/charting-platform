# feat/strategy-lab-v2

Created from `staging` at `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`.

## Human authorization

- Recorded at: 2026-09-15T19:48:24.815519+00:00
- Request: Implement the approved Strategy Lab v2 plan; honor the repository AI-driven workflow rules and active branch boundaries.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: ready; session goal is active and the workstream remains `in_progress`.

Update this handoff at each coherent boundary.

## 2026-09-15 - Approved implementation plan

The human explicitly activated implementation of the agreed Strategy Lab v2
plan. The assigned worktree is `feat/strategy-lab-v2`, created through the
repository's guarded workflow from synchronized `staging` at
`8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`. Bootstrap commit
`52a67c6cc74e4b8e4efe95e9d608bce821b8bd02` is published and synchronized.

The initial implementation is limited to new engine-neutral backend package
paths and package-co-located focused tests. A read-only ownership audit found
that the active provider workstream owns `backend/tests/`; v2 tests therefore
stay under `backend/app/strategy_lab_v2/tests/` and are run by explicit pytest
path. The package may define contracts for later adapters but must not
modify provider-platform, ETF, or TC2000 worktrees; current Strategy Lab routes
and services; shared models, migrations, application registration, worker/task
entrypoints, global dependencies, Compose, or frontend until the three parallel
branches reach staging and every overlap is semantically reconciled. The next
phase consumes their staged capability, point-in-time membership, and immutable
CodeVersion/Study Lab contracts without duplicating their ownership.

Nautilus v2 remains the sole authoritative engine target, gated on stable
publication and the branch conformance suite. Current official release evidence
still identifies the v2 line as release candidates; no candidate is eligible
for production enablement. The engine-neutral core can progress independently.
The eventual runtime uses a separate isolated worker environment and a Rust
adapter for canonical forward events. Backtests and persistent broker-free
shadow instances have separate worker capacity. The frontend remains a later
TC2000-native dockable suite in a separately authorized branch.

The branch-owned plan records the architecture, all final acceptance criteria,
the current parallel-safe boundary, deferred shared-path gates, and
`full_stack_browser` completion profile. Initial focused package work can use
unit checks; the complete branch must pass the repository's full backend,
database/Redis, migration, Compose, worker, API, browser, and exact-tip gates.
`make branch-validate` currently validates all workstream records. The
session-local goal is active.

Session `603da09c-b640-4018-9f40-c62f4564b074` owns this worktree. Do not edit
another worktree, even if dependency work advances in parallel; reconcile its
staged changes here only after an authorized staging update.

## 2026-09-15 - Engine-neutral core checkpoint

The initial engine-neutral implementation is committed locally as
`4f265239c1b736e50ba7bf514f0986ca663eebc9`; a separate focused documentation
correction is `1d934e578cb3a75f37d31ec30b6d551d004452b5`. Both commits are in the
assigned worktree. They add only `backend/app/strategy_lab_v2/` and
`docs/strategy-lab-v2.md`. No active provider, ETF, TC2000, model, migration,
router, worker, dependency, Compose, or frontend path was changed.

Focused evidence on the code checkpoint: `cd backend && rtk uv run pytest
app/strategy_lab_v2/tests -q --override-ini addopts=` passed (9 tests),
`rtk uv run ruff check app/strategy_lab_v2` passed, and
`rtk uv run mypy app/strategy_lab_v2` passed. The focused pytest override avoids
applying the repository-wide coverage threshold to this package-only slice; it
does not satisfy the final full-suite gate.

The core now includes typed immutable domain and strategy-package contracts,
canonical content fingerprints, preflight classification and degradation,
semantic snapshot-to-requirement matching, SDK input/intent contracts,
deterministic search and walk-forward planning, Decimal baseline metrics,
attempt/forward-event lifecycle helpers, and result provenance binding trial,
successful attempt, package/strategy, portfolio, snapshot, metric, engine/build,
dependency, assumptions, seed, and output artifact identities.

Important trust boundary: `DataSeriesManifest` binds an upstream
`coverage_evidence_digest`, but the engine-neutral package cannot resolve or
validate that evidence document. `DataSnapshot` checks manifest semantics and
range continuity only; it trusts the upstream attestation reference. Before any
execution path exists, the provider-platform adapter must validate the attested
series content, range, row count, calendar, and semantic dimensions. Host-side
portfolio allocation/shared-risk execution, complete metrics, persistence, API,
isolated strategy runtime, workers, local Compose services, and authoritative
Nautilus execution remain unfinished. Do not treat this checkpoint as a usable
simulator or sandbox.

Publication hold: after the implementation commit, the exact command
`rtk git push origin feat/strategy-lab-v2` was denied by the elevated execution
approval reviewer. Its stated issue was that the transcript did not establish
the private `origin` destination as a trusted organization-owned repository or
contain explicit authorization for that destination. The pre-operational local
implementation/doc tip is `1d934e578cb3a75f37d31ec30b6d551d004452b5`; after
this workstream-record checkpoint, verify its enclosing commit externally with
`rtk git rev-parse HEAD`. The remote `origin/feat/strategy-lab-v2` remains
`d2497f43084d52d3e66b40a91be25dd2678620be`. Do not retry through another shell,
API, plugin, or indirect route. Continue independent local work; ask the human
to explicitly authorize this exact remote destination before attempting normal
publication again.

## 2026-09-15 - Shared-account allocation and metrics checkpoint

The second parallel-safe implementation slice is committed locally as
`6def980311f7c5aef05ffcc13646d9beeae5c5aa`. It adds event-aligned component
target resolution, deterministic conflict policies, cash-equity-only signed
notional risk checks, all-or-nothing shared limits, explicit flat targets, and
34-digit deterministic Decimal arithmetic. Product classes without a registered
and policy-allowed risk model fail closed. Raw order sizing and engine routing
remain unsupported.

Metrics v2 now adds explicit-currency account P&L/return, drawdown duration,
Ulcer, annualized return/volatility, Sharpe/Sortino/Calmar, monetary recovery
factor, empirical nearest-rank VaR/expected shortfall, and trade-quality/streak
summaries. Each value records its calculation and basis conventions. Equity
curves currently mean equally spaced post-start marks; timestamps and
irregular-time annualization remain unsupported. Exposure/capital, execution
cost, attribution, rolling, distribution, sensitivity, calendar metrics,
persistence, APIs, workers, isolated execution, and Nautilus integration remain
open.

Validation on the exact implementation tree: focused package pytest passed 30
tests; Ruff and mypy passed; `git diff --check` passed. `make branch-validate`
is rerun after this operational checkpoint. The package-only checks do not
satisfy the planned full-stack completion profile.

Publication remains a transport hold, not a product blocker. The current
implementation tip is `6def980311f7c5aef05ffcc13646d9beeae5c5aa`; the recorded
remote tip is `d2497f43084d52d3e66b40a91be25dd2678620be`, so the local branch is
four commits ahead after this implementation commit. The previous elevated
push for an earlier payload was rejected by the private-repository egress
review. No push of the current range has been attempted. Do not retry
`rtk git push origin feat/strategy-lab-v2` until the human explicitly authorizes
the exact current destination and range; continue independently scoped local
work and never claim synchronization.

The prior next-action context has been completed at the checkpoint below. Keep
shared integration deferred until provider, ETF, and TC2000 reach staging and
their exact contracts are reconciled. Maintain `in_progress`; closure,
integration, promotion, and deployment are not authorized.

## 2026-09-15 - Run-scoped observations and result metrics checkpoint

The next engine-neutral result slice is committed locally as
`82749796ac520a227288e7fa54dfed3a589a3983`. It adds normalized event-time and
sequence points, account exposure snapshots, fill cost observations, and
component P&L observations. All run observations carry a run-attempt identity;
component P&L is bound to one common result bundle and reconciles exactly to
portfolio gross/net P&L, including an explicit unallocated residual when needed.

Metrics v3 now provides event-sampled cash-equity notional/equity and cash/equity
ratios, run-scoped fill-cost summaries, and reconciled component P&L
contributions. Exposure measures are sample-weighted, not time-weighted or
margin utilization. Cost totals and bps are null unless every fill has an
explicit complete cost report; partial/unavailable reports are counted and
reported category values are labelled as observed rather than complete. FX,
slippage, cost models, and attribution methods require adapter-provided evidence;
the core infers none of them. Stable canonical observation digests travel with
metric calculation bases. Independent review found no remaining actionable
P0-P2 findings after the run-identity and incomplete-cost fixes.

Exact-tip package validation at the implementation commit passed: focused
package pytest (39 tests), Ruff, mypy (16 files), and `git diff --check`. This is
not the planned full-stack validation profile. Existing deferred gaps include
calendar-aware rebalance semantics, irregular-time/rolling/distribution/
sensitivity/calendar metrics, product-specific risk models beyond cash
equities, verified provider coverage evidence, persistence, APIs, workers,
isolated strategy execution, Compose services, and authoritative Nautilus v2
execution/conformance.

The branch remains local and is six commits ahead of recorded remote
`d2497f43084d52d3e66b40a91be25dd2678620be`; no push of this current range was
attempted. The previous private-repository egress hold remains unchanged. Do not
publish through another route; continue local work under this session. Next:
define and test immutable calendar-versioned rebalance policy and schedule
semantics in package-owned paths. Keep provider, ETF, TC2000, shared runtime,
migration, API registration, Compose, and frontend ownership boundaries intact.

## 2026-09-15 - Calendar-aware rebalance scheduling checkpoint

The next engine-neutral slice is committed locally as
`32019aa8518114f1ca658d2b9e9f24c8c2f53083`. `PortfolioComposition` now binds an
optional typed, versioned `CalendarRebalancePolicy`. The new `rebalance.py`
contract pins that policy to an immutable content-addressed session calendar
with explicit trading/closed dates, timezone/tzdb versions, source evidence,
venue-assigned session labels, and UTC session segments (including split
sessions, overnight trading dates, DST, and early closes).

The pure planner supports each-session, ISO-weekly, monthly, quarterly, and
yearly cadence, first/last actual session selection, open-before-events or
close-after-events decision boundaries, and explicit misfire policy. Weekly and
larger cadences require complete calendar period coverage; requested ranges use
inclusive venue session labels. No calendar is fetched or inferred. The planner
does not map boundaries to engine event sequences, apply component capital
weights, emit orders, or imply fills at open/close prices; those remain adapter
and execution work.

Exact-tip package validation passed: focused pytest (48 tests), Ruff, mypy (18
files), and `git diff --check`. Independent review found no remaining actionable
P0-P2 findings after correcting the stale rebalancing documentation. This is
still package-only validation, not the planned full-stack browser/DB/Redis/
worker/Compose gate.

The local branch is eight commits ahead of recorded remote
`d2497f43084d52d3e66b40a91be25dd2678620be`; no push of this current range was
attempted, and the previous private-repository egress hold is unchanged. Next
bounded work: add run-attempt-scoped timestamped account-equity observations
and rigorous calendar-period metric inputs, explicitly preserving irregular
event timing and rejecting unsupported external-cash-flow assumptions. Keep
all parallel provider, ETF, TC2000, shared runtime, migration, API, Compose, and
frontend boundaries unchanged. Maintain `in_progress`; closure, integration,
promotion, and deployment remain unauthorized.

This operational checkpoint updates only the following branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/plan.yaml`
- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-09-16 - Replicate seed and sensitivity evidence checkpoints

The seed-provenance implementation is committed locally as
`6ec5074e696a4333dd9fe5b59ec0f693fb0477f9`, with its separate ops record at
`cefa6c468501c990676587f0e39287f9976bc56b`. It adds deterministic replicate
seed schedules while preserving the default single-trial identity and legacy
seed path. Focused validation passed 60 package tests, Ruff, MyPy (18 source
files), and `git diff --check`.

The sensitivity-evidence implementation is committed locally as
`69faca1941157ff1597e209ce6d2679af08fcd70`, with its separate ops record at
`f19db3e634b822f1cf27257e18d7ea33b3332137`. It distinguishes unpaired runs,
shared-seed provenance, and unverified keyed-stream pairing claims; it does not
assert statistical independence or calculate numeric deltas. Focused validation
passed 60 package tests, Ruff, MyPy (18 source files), and `git diff --check`;
the workstream validator passed all 30 records after the checkpoint update.

The recorded origin remains
`d2497f43084d52d3e66b40a91be25dd2678620be`. The private-origin publication
hold remains unchanged: no push was attempted for these exact ranges and no
alternate publication route is authorized.

## Scope recorded - stable metric calculation identity and run evidence

This bounded engine-neutral context owns only
`backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/metrics.py`,
`backend/app/strategy_lab_v2/tests/test_metrics.py`,
`backend/app/strategy_lab_v2/tests/test_observations.py`, and
`docs/strategy-lab-v2.md`. It introduces a versioned structured
calculation definition and typed evidence references on calculated metrics.
The stable calculation fingerprint excludes observed values, sample sizes,
display strings, and run evidence; per-family effective parameters are recorded
where they change calculation semantics. Formula version v6 remains unchanged.
No metric deltas, statistical inference, comparator, API, persistence, worker,
runtime, Compose, frontend, provider, ETF, TC2000, or shared path is included.

Exact focused checks pass: 62 Strategy Lab v2 tests (`--no-cov` to avoid the
repository-wide coverage threshold on this focused selection), Ruff, MyPy (18
source files), and `git diff --check`. Independent read-only review initially
found an overbroad annualization parameter on cadence-independent metrics; it
was narrowed to annualized/risk-adjusted metrics and re-reviewed with no
remaining P0-P2 issue. The formula compatibility test now confirms that changing
`periods_per_year` preserves total-return identity while changing annualized
return identity.

The five product files listed above were committed locally in
`f34fb2564d62c8721f1b518ca093876271f3e3ca`; the later checkpoint below records
that completed changeset. Keep the existing publication hold; do not push
without exact-payload authorization. The enclosing operational checkpoint SHA
will be verified externally with `git rev-parse` rather than written into
itself.

## Completed context - Trial seed-sharing and replicate provenance

This implementation context owned only
`backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/experiments.py`,
`backend/app/strategy_lab_v2/tests/test_core.py`, and
`docs/strategy-lab-v2.md`. Preserve the existing per-candidate seed output as
the default, and add an explicit shared-seed-per-scenario-and-replicate policy
plus typed trial randomization provenance (master seed, effective seed,
replicate index, seed-group fingerprint, derivation version). This is a seed
assignment contract only: equal initial seeds do not prove event-level paired
randomness or statistical comparability when an engine consumes sequential or
otherwise unkeyed random streams. One-factor paired sensitivity, engine RNG
attestation, API/persistence, workers, and runtime integration remain deferred.
Keep provider, ETF, TC2000, shared runtime, migration, route, Compose, and
frontend ownership unchanged.

Compatibility review: preserve the old `ScientificTrial.trial_id` for the
default per-candidate, single-replicate, unscoped schedule. Its typed assignment
retains master/effective seed, seed-group fingerprint, and derivation version,
but excludes the legacy schedule metadata from trial identity. Explicit shared,
scoped, or replicated schedules bind the group provenance and replicate count
into trial identity. The regression compares builder output with the prior
explicit-effective-seed construction. A subsequent independent review also
found that callers could pair a valid digest with the wrong effective seed; the
contract now checks derived seeds against supported versioned digests and
rejects unknown derivation versions. Explicit-seed records are separately
validated and cannot claim generated schedule provenance.

The implementation is committed locally as
`6ec5074e696a4333dd9fe5b59ec0f693fb0477f9`. It preserves legacy default seed
values and trial IDs, adds deterministic shared-per-scenario/replicate seed
assignments, carries replicate count and seed-group provenance, validates the
effective seed against the supported digest version, and rejects unsupported or
inconsistent assignments. Equal initial seeds still do not claim paired draws.

Exact focused validation passed: 60 package tests, Ruff, MyPy (18 source files),
`git diff --check`, and `make branch-validate` (30 workstream records).
Independent review found no remaining P0-P2 issue. This is package-level
evidence only; the full-stack/DB/Redis/API/worker/Compose/Nautilus completion
gates remain outstanding.

Publication state is `committed_locally_pending_push`. At the implementation
commit boundary, `HEAD` is `6ec5074e696a4333dd9fe5b59ec0f693fb0477f9` and
`origin/feat/strategy-lab-v2` is
`d2497f43084d52d3e66b40a91be25dd2678620be`; the exact range is
`d2497f43084d52d3e66b40a91be25dd2678620be..6ec5074e696a4333dd9fe5b59ec0f693fb0477f9`.
No push of this range was attempted because exact-payload authorization for the
private origin is unavailable. Do not use an alternate transport. The separate
ops checkpoint for this seed-provenance slice was committed locally before the
next sensitivity-evidence implementation recorded below. Do not treat this
implementation-only range as a new authorization to publish the full branch.

## 2026-09-16 - Sensitivity randomization-evidence checkpoint

The implementation is committed locally as
`69faca1941157ff1597e209ce6d2679af08fcd70`. It adds an engine-neutral
`SensitivityComparisonEvidence` contract that requires successful results to
share their fixed execution context and distinguishes `unpaired`,
`shared_seed_only`, and `pairing_claim_unverified`. An equal integer seed alone
does not establish a common randomization group; matched scenario/replicate seed
provenance is required for the shared-seed-only label. A structurally complete
keyed-stream claim binds both attempts, the engine build, trace artifacts, and a
matched-draw artifact, but the contract deliberately cannot authenticate these
artifacts or prove engine conformance. No verified paired-stream or statistical
independence classification is emitted until a trusted verifier/registration
receipt exists. Retries of one scientific trial are not treated as sensitivity
replicates. This contract classifies randomization provenance only; it does not
compare metric semantics, calculate metric deltas, or perform paired inference.

Independent review initially identified overclaims around independence and
unverified paired evidence, plus an invalid exact comparison of run-dependent
metric calculation-basis strings. The implementation now uses neutral
`unpaired` and unverified-claim levels, and separates provenance classification
from metric compatibility. Re-review found no remaining P0-P2 issue.

Exact implementation-commit validation passed: 60 package tests, Ruff, MyPy
(18 source files), and `git diff --check`. `make branch-validate` passed all 30
records on an elevated retry after the default sandbox denied UV cache metadata
access; this was the repository validator only. These focused checks do not
satisfy the DB/Redis/API/worker/Compose/Nautilus/security/full-stack acceptance
gates.

At this implementation boundary, local HEAD is
`69faca1941157ff1597e209ce6d2679af08fcd70`, 18 commits ahead of recorded
`origin/feat/strategy-lab-v2`
(`d2497f43084d52d3e66b40a91be25dd2678620be`). No push was attempted because
exact-payload authorization for the private origin is unavailable; do not
publish through another route. The separate ops checkpoint will be committed
after these implementation results are recorded.

The next bounded slice in that handoff, separating stable calculation identity
from run-specific evidence, was implemented in
`f34fb2564d62c8721f1b518ca093876271f3e3ca` and is recorded below. Numeric
one-factor descriptive sensitivity deltas remain the next metric slice. Keep
paired statistical inference deferred until the worker has a trusted keyed-
stream verifier and aligned per-observation outputs. Preserve all provider,
ETF, TC2000, shared runtime, persistence, API, worker, Compose, and frontend
boundaries.

This checkpoint updates only these branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-09-16 - Metric calculation identity and evidence checkpoint

The implementation changeset is committed locally as
`f34fb2564d62c8721f1b518ca093876271f3e3ca`. It adds a versioned structured
calculation definition and typed evidence references to metric values. Stable
fingerprints bind metric identity, units, basis, formula version, and only
effective calculation parameters; observed values, sample sizes, display text,
null state, and run-specific evidence do not alter that calculation identity.
All eight current metric families emit stable formula IDs, Decimal context,
effective parameters where semantically relevant, and typed input/calendar/fill/
attribution evidence. The catalog remains v6 because estimator formulas did
not change. This is an identity primitive, not a metric comparator.

Exact focused validation passed: 62 package tests with `--no-cov`, Ruff, MyPy
(18 source files), and `git diff --check`. The initial focused pytest invocation
ran under the repository-wide coverage threshold and exited nonzero at 7.24%
coverage versus the required 55%; it was rerun successfully with `--no-cov`.
`make branch-validate` passed all 30 workstream records on the documented
elevated retry after the default sandbox blocked UV cache metadata access.
Independent review caught an overbroad `periods_per_year` parameter on
cadence-independent metrics; the implementation was narrowed and re-reviewed
with no remaining P0-P2 issue. This package-only evidence does not satisfy the
full-stack/DB/Redis/API/worker/Compose/Nautilus acceptance gates.

The local branch is 20 commits ahead of recorded
`origin/feat/strategy-lab-v2` at
`d2497f43084d52d3e66b40a91be25dd2678620be`. The exact pending range ends at
`f34fb2564d62c8721f1b518ca093876271f3e3ca`. No push was attempted: exact-payload
authorization for the private origin remains unavailable, and no alternate
transport is authorized. The default sandbox denied UV cache metadata access
for repository workflow commands; the exact session-status command succeeded
on the documented narrow elevated retry. No sandbox setting was changed, and
no other worktree or shared/provider/frontend path was touched.

Next bounded implementation context: add run-scoped descriptive one-factor
metric deltas using `MetricValue.calculation_fingerprint` to require compatible
calculation semantics. Preserve unpaired/shared-seed provenance labels; do not
claim statistical significance or paired inference without trusted keyed-stream
verification and aligned per-observation outputs. Only the three branch-owned
workstream records below remain in this checkpoint; stop this session after
the ops checkpoint per the repository soft-stop rule.

This checkpoint updates only these branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

The soft-stop `agent-session-checkpoint` completed under the existing session
claim. Its `dirty_paths` capture dropped the leading `b` from the first modified
path (`backend/...` appeared as `ackend/...`), because the helper strips leading
status whitespace before removing the porcelain prefix. Raw `git status` confirms
the correct path. I corrected only this workstream's `session.json`; the helper
implementation is outside this branch's owned scope and was not changed.

## 2026-09-15 - Calendar-period equity metrics checkpoint

The next engine-neutral slice is committed locally as
`5a5177ea28d5a1b50d225aaa5b400d46f4a411aa`. It adds immutable,
run-attempt-scoped account-equity intervals bound to a versioned session
calendar. Calendar metrics reconcile account equity deltas less explicit
external cash flows and support each-session, ISO-weekly, monthly, quarterly,
and yearly buckets. Period completeness requires the prior actual session
close through the period's final actual session close; returns are null for
incomplete coverage or external flows (time-weighted returns are not inferred).

Independent review identified and resolved one P2 comparison risk: a partial
window could otherwise emit a value named as a full calendar-period return.
The partial-period test now asserts the null and its explicit reason. Exact-tip
focused validation passed: 51 package tests, Ruff, mypy (18 source files), and
`git diff --check`. `ruff format --check` would reformat ten package files,
including existing code, so broad formatter churn was not applied. The focused
checks do not satisfy the planned database/Redis, API, worker, Compose, Nautilus,
security, or full-stack validation gates.

The branch is ten commits ahead of recorded remote
`d2497f43084d52d3e66b40a91be25dd2678620be`; this slice has not been pushed and
the prior private-repository publication hold remains unchanged. No shared or
parallel branch was touched. Next bounded engine-neutral slice: implement
run-scoped rolling return/risk series with explicit session sampling, complete
window coverage, and minimum-observation rules. Keep provider, ETF, TC2000,
shared runtime, persistence, API, worker, Compose, and frontend boundaries
unchanged. Maintain `in_progress`; closure, integration, promotion, and
deployment remain unauthorized.

This checkpoint updates only these dirty branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-09-15 - Rolling and calendar-period equity metrics checkpoint

The implementation changeset is committed locally as
`2d9d8865bc69292dcd1c48719fa6ab803686af3f`. It adds typed rolling session-close
metric points, exact session-window coverage, explicit annualization and
risk-free assumptions, and rolling P&L/return/volatility/Sharpe/Sortino/drawdown/
duration/Ulcer metrics. Calendar-period and rolling aggregators now require
complete external-flow reports for adjusted net P&L and explicit flow-occurrence
evidence for return/risk eligibility. Independent review found and resolved the
zero-net offsetting-flow case; a zero net amount with any flow event now withholds
return and equity-path risk metrics. An intermediate focused run also exposed an
unavailable-flow test fixture that retained stale occurrence evidence; the
fixture was corrected to omit both amount and occurrence, and the final exact-tip
checks pass.

Exact-tip focused validation passed: 56 package tests, Ruff, MyPy (18 source
files), and `git diff --check`. Independent review found no remaining concrete
defect. This is package-only evidence, not the planned full-stack/DB/Redis/API/
worker/Compose/Nautilus completion gates.

The implementation commit remains pending publication at
`2d9d8865bc69292dcd1c48719fa6ab803686af3f`; the separate ops checkpoint is
being committed on top of it. The recorded remote tip is
`d2497f43084d52d3e66b40a91be25dd2678620be`. No push of the current range was
attempted because the prior private-repository egress review rejected a payload
and the exact current range has not been authorized. Do not retry through an
alternate route. Verify the enclosing ops commit with `git rev-parse` after
commit rather than creating a self-referential hash update. No parallel worktree
or shared/provider/frontend path was modified.

Next bounded slice: run-scoped session-return distribution metrics over the
validated account-equity intervals and exact session calendar. Keep sensitivity
analysis deferred until common-random-seed/matched-trial semantics are defined.
Continue to preserve provider, ETF, TC2000, shared runtime, migration, API,
worker, Compose, and frontend boundaries. Maintain `in_progress`; closure,
integration, promotion, and deployment remain unauthorized.

This checkpoint updates only these branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## Scope recorded before implementation - Run-scoped session-return distributions

The implementation context owned only
`backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/metrics.py`,
`backend/app/strategy_lab_v2/tests/test_core.py`,
`backend/app/strategy_lab_v2/tests/test_observations.py`, and
`docs/strategy-lab-v2.md`. It added typed, run-scoped close-to-close return
quantiles and empirical VaR/expected-shortfall outputs, using explicit inclusive
session-label bounds, exact calendar adjacency and predecessor-close evidence,
minimum sample rules, and the current external-flow fail-closed contract. The
global metric catalog advanced to v6 without changing the v5 equity-curve
estimator semantics. No histogram bins, sensitivity ranking, APIs, persistence,
workers, runtime, Compose, frontend, provider, ETF, TC2000, or shared paths are
in scope. The prior private-repository egress hold remains: continue locally
from the verified clean boundary; do not publish without exact-payload
authorization.

## 2026-09-16 - Run-scoped session-return distribution checkpoint

The implementation is committed locally as
`444193415f0236536767892d6f28effaec39d4ec`. It adds a typed, run-scoped
distribution summary and exact-calendar-bounded close-to-close session-return
quantiles, empirical VaR, and expected shortfall. Inclusive trading-session
bounds require every actual session observation and its preceding actual
session-close mark. Nearest-rank calculations record their effective ranks/tail
counts and use exact integer-rational ceiling arithmetic so high-precision
probabilities cannot move a rank at a Decimal rounding boundary. Incomplete
coverage, incomplete flow reports, or any flow event (including zero-net
offsetting flows) withholds the entire distribution. The catalog is v6; existing
equity-curve estimator semantics are unchanged. Histogram bins and sensitivity
analysis remain out of scope for this slice.

Exact implementation-commit validation passed: focused package pytest (59
tests), Ruff, MyPy (18 source files), and `git diff --check`. Independent
read-only review found no remaining concrete defect. `make branch-validate`
passed all 30 records on an elevated retry after the default sandbox denied UV
cache metadata access; the retry ran only that repository validator. These
package checks do not satisfy the final full-stack/DB/Redis/API/worker/Compose/
Nautilus acceptance gates.

Publication remains a transport hold. Local HEAD is
`444193415f0236536767892d6f28effaec39d4ec`; recorded
`origin/feat/strategy-lab-v2` remains
`d2497f43084d52d3e66b40a91be25dd2678620be`, so this branch is 14 commits ahead.
No push of this exact current range was attempted. The earlier private-repository
egress review rejected a prior payload, and the current remote/range does not
have exact-payload authorization; do not publish through another route.

Next bounded context: define and test deterministic common-random-seed and
replicate semantics for matched one-factor sensitivity analysis. Only after
those semantics are pinned should the comparison contract be added; do not
silently compare trials with independently derived seeds. Keep all active
provider, ETF, TC2000, shared runtime, persistence, API, worker, Compose, and
frontend ownership boundaries unchanged. This separate checkpoint updates only
the branch-owned handoff, session state, and validation journal below.

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-09-16 - Descriptive one-factor metric delta (in progress)

The bounded implementation context owns only
`backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/sensitivity.py`,
`backend/app/strategy_lab_v2/tests/test_core.py`,
`backend/app/strategy_lab_v2/tests/test_sensitivity.py`, and
`docs/strategy-lab-v2.md`. It adds a run-scoped descriptive delta that requires
exactly one canonical parameter change, a matching structured metric
calculation fingerprint, and identical projected measurement-scope identities.
The scope binds the frozen snapshot and its referenced coverage claims,
experiment/scenario, portfolio currency, execution context, formula identity,
and applicable session-calendar evidence. It does not authenticate upstream
coverage claims. Null/incompatible cases are explicit unavailable outcomes;
sample sizes and the existing unpaired/shared-seed/unverified-pairing labels
are preserved. This context makes no significance, ranking, replicate-aggregate,
or paired-inference claim.

The product changeset is committed locally as
`9da8d667e327aca619cc93bd8d22eac123e688a5`. Post-commit focused validation
passed at this exact SHA: 75 Strategy Lab v2 tests, Ruff, focused Ruff formatting
checks for the new comparator/test files, MyPy (20 source files), and
`git diff --check`. Independent read-only review found two missing contract
invariants; both were fixed with direct-construction tests, and the re-review
found no remaining concrete issue. This is package-level evidence, not the final
database/Redis/API/worker/Compose/Nautilus/full-stack acceptance gates.

The ordinary sandbox denied creation of the worktree `.git/index.lock` on the
first commit attempt. Read-only checks found the worktree index owned by the
current user and no stale lock. The repository's narrow elevated Git retry then
committed the already-reviewed staged changeset successfully. No sandbox setting
was changed. This is the documented workflow recovery, not a product blocker.

The required schema-4 session checkpoint initially needed the repository
`agent-session-goal-state` helper to move the takeover marker from
`resumed_after_takeover` to `active`, matching the still-active thread goal.
The checkpoint then passed on the narrow elevated retry after default UV cache
metadata access was denied. Its known dirty-path helper bug removed the leading
`o` from the first path; raw `git status` showed the exact three branch-owned ops
files, and `session.json` was corrected manually. No other path is dirty.

The local branch was 22 commits ahead of
`origin/feat/strategy-lab-v2` at `d2497f43084d52d3e66b40a91be25dd2678620be`
after the product commit. No push was attempted: the private-origin exact-payload
authorization hold remains, and this agent will not use an alternate transport.
The separate ops checkpoint will add one commit above the last recorded
pre-checkpoint SHA; verify the enclosing final SHA externally with `git
rev-parse` rather than chasing a self-referential session hash.

`make branch-validate` passed all 30 workstream records on the narrow elevated
retry after the default sandbox denied UV cache metadata access, including a
final pass after the checkpoint refresh, exact dirty-path correction, and
validation-journal update. The required schema-4 session checkpoint is current
for the product SHA, with the active goal recorded. Exact next action: stage and
review only the three branch-owned ops files, commit the separate checkpoint,
then verify clean status and the exact final `HEAD`/remote hashes externally.
Do not publish the branch while the exact-payload hold remains.

Next bounded action after this ops checkpoint: from a verified clean local
boundary, inspect remaining parallel-safe Strategy Lab v2 core gaps and choose
the next backend-owned slice. Keep paired inference/profitability ranking
deferred until trusted aligned observations exist. This ops checkpoint updates
only these branch-owned files:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

Do not mutate another worktree or provider, ETF, TC2000, shared runtime, API,
persistence, Compose, or frontend path.

## 2026-09-16 - Descriptive one-factor replicate summaries (in progress)

The next bounded implementation context owns only
`backend/app/strategy_lab_v2/sensitivity.py`,
`backend/app/strategy_lab_v2/tests/test_sensitivity.py`, and
`docs/strategy-lab-v2.md`. It adds a deterministic descriptive comparison over
complete baseline and variant replicate groups of successful
`RunResultManifest` values. The groups must differ in exactly one canonical
parameter, contain one result for each distinct scientific trial, and cover
every planned replicate index exactly once. Fixed experiment, scenario,
snapshot, capability, portfolio, engine/build, dependency, assumption, metric
calculation, and measurement-calendar scopes must agree. Missing, duplicate,
null, or incompatible replicates fail closed rather than silently shrinking the
sample. Results retain the per-arm randomization provenance and report
descriptive per-arm summaries plus the difference of sample means. Equal
replicate indices or seeds are not treated as verified paired draws; no
significance, confidence interval, candidate ranking, or independence claim is
made.

Read-only gap audit confirmed that the current v6 package already has account
performance, trade-quality, cash-equity exposure, fill-cost, component
attribution, calendar/rolling, session-return-distribution, and one-run metric
delta calculators. This replicate-level summary is the next parallel-safe
metric gap. Time-weighted returns requiring external-flow boundary valuations,
irregular-time annualization, true margin/capital utilization, financing outside
fill reports, and trusted paired inference remain deferred. Provider, ETF,
TC2000, persistence, API, worker, runtime, migration, Compose, and frontend work
remain outside this context.

The preceding one-factor delta product commit is
`9da8d667e327aca619cc93bd8d22eac123e688a5`; its separate ops checkpoint is
`dfe93ae7014074be066ef677a3c7b985a500956e`. External verification after that
checkpoint found local `HEAD` at `dfe93ae7014074be066ef677a3c7b985a500956e`,
`origin/feat/strategy-lab-v2` at
`d2497f43084d52d3e66b40a91be25dd2678620be`, and a clean worktree (23 commits
ahead). The private-origin exact-payload export hold remains; no push of this
current range was attempted, and no alternate transport is authorized. Continue
from the clean local boundary without claiming remote synchronization.

This scope-selection checkpoint updates only this branch's `plan.yaml`,
`handoff.md`, `session.json`, and `validation.jsonl`. Validate and commit those
records separately before changing the three implementation-context paths
listed above. The session checkpoint helper rejects a changed plan until
`agent-session-plan-ready` runs; the repository helper requires the plan update
to be committed and the local branch head to match its remote before it can mark
the plan ready. Because the exact private-origin range is still under its
authorization hold, the replicate implementation must not start until that
plan-ready gate is satisfied. After this scope checkpoint is locally committed,
the next action is to obtain exact-payload authorization for the resulting
`origin/feat-strategy-lab-v2..HEAD` range, publish only through the approved Git
path, verify synchronized hashes, then run the required plan-ready/session-state
reconciliation. Do not bypass the gate or use another transport.

## 2026-09-16 - Synchronization and plan-ready reconciliation

The human explicitly authorized the exact current export after the prior
private-origin safeguard. The approved elevated command
`rtk git push origin feat/strategy-lab-v2` succeeded for
`d2497f43084d52d3e66b40a91be25dd2678620be..0f0d85c214de6828d8e15b6d03d60adcb1551c2a`.
Post-push verification found a clean worktree and matching local/remote HEAD at
`0f0d85c214de6828d8e15b6d03d60adcb1551c2a`.

`make agent-session-plan-ready SESSION_ID=e2731935-179c-4c35-b5d2-aadf7b4857f7`
passed after synchronization. The resumed session goal was recorded as active
with `make agent-session-goal-state ... STATE=active`, and the required
`make agent-session-checkpoint SESSION_ID=e2731935-179c-4c35-b5d2-aadf7b4857f7`
passed through the approved elevated UV path. The session record now reflects
the synchronized publication state. This operational reconciliation is being
committed separately; verify its enclosing commit externally with
`git rev-parse` rather than writing a self-referential SHA into the record.

The next bounded implementation action is the already scoped descriptive
one-factor replicate summary in the engine-neutral package. Keep the strict
complete-replicate, fixed-context, no-ranking/no-inference boundary and all
provider, ETF, TC2000, persistence, API, worker, runtime, migration, Compose,
and frontend ownership gates intact.

## 2026-09-16 - Descriptive replicate-summary implementation checkpoint

The scoped engine-neutral metric slice is complete in product commit
`3767730ec32ee7cf19b0e4d44fac7caf664f8baf`. It adds immutable typed
`ReplicateRandomizationSummary`, `NearestRankStatistic`,
`ReplicateMetricStatistics`, `OneFactorReplicateMetricSummary`, and explicit
`ReplicateMetricSummaryUnavailable` outcomes in `sensitivity.py`, plus the
`summarize_one_factor_metric_replicates()` API and compatibility alias
`compare_one_factor_metric_replicates()`.

The summary requires successful results covering every planned replicate index
exactly once on each arm, rejects duplicate trials/attempts and inconsistent
arm parameters, enforces exactly one canonical parameter change, and binds one
fixed execution and metric-measurement scope. It preserves each arm's realized
observation sample sizes and full seed provenance, computes Decimal means,
nearest-rank median/minimum/maximum and configured quantiles, and exposes only
the signed difference of arm means. It never ranks candidates or claims
significance, independence, or verified pairing. Focused sensitivity tests now
cover deterministic ordering/statistics, shared-seed-only labeling, incomplete
groups, and null values.

Validation on the exact implementation tree passed 18 focused sensitivity
tests, 80 package tests, Ruff for the changed package files, MyPy for the
changed source and tests, and `git diff --check`. A package-wide Ruff format
check still reports seven pre-existing formatting differences in unrelated
files; no unrelated formatting was changed.

The implementation commit was pushed once through the approved elevated Git
path, but the private-origin safeguard rejected the newer payload before Git
because exact authorization for `0f0d85c214de6828d8e15b6d03d60adcb1551c2a..3767730ec32ee7cf19b0e4d44fac7caf664f8baf` was not established. No alternate
transport or retry was used. The current clean local boundary is
`3767730ec32ee7cf19b0e4d44fac7caf664f8baf`; the remote remains
`0f0d85c214de6828d8e15b6d03d60adcb1551c2a`. The operational record below is
being committed separately; derive the full pending range externally before
any authorized retry.

Next action is blocked only on exact authorization to publish the current
range, followed by plan-ready/session reconciliation for the changed plan. Do
not begin another implementation context, integrate, promote, deploy, or
touch provider, ETF, TC2000, shared runtime, persistence, API, worker, Compose,
or frontend paths while this synchronization gate is unresolved.

## 2026-09-16 - Standing authorization and synchronized implementation boundary

The human granted standing authorization to publish the current Strategy Lab
v2 implementation and its branch-owned operational records. The approved
elevated `rtk git push origin feat/strategy-lab-v2` succeeded for the full
pending range `37a293bc691325460fe75eac4ff9138438da1a54..6b8b6b68a6fd41abcca28f3ca6c9a5e3fbe16669`.
Post-push verification found a clean worktree and matching local/remote HEAD
at `6b8b6b68a6fd41abcca28f3ca6c9a5e3fbe16669`.

The required `agent-session-plan-ready`, `agent-session-goal-state ...
STATE=active`, and `agent-session-checkpoint` workflow gates all passed under
the authorized elevated path. Session metadata now records the synchronized
boundary and an active goal. The next bounded action is to inspect and
implement the next engine-neutral metric slice; no provider, ETF, TC2000,
persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths are opened by this authorization.

## 2026-09-16 - Flow-adjusted return implementation checkpoint

The next package-owned metric slice is complete in product commit
`ec670600a3eda08eea7ee40ea05b61becb45ed83`. It adds the immutable
`ExternalCashFlowBoundaryObservation` and binds ordered interior pre-flow and
post-flow marks to each `AccountEquityIntervalObservation`. Boundary amounts
must reconcile the parent interval's reported flow; zero and offsetting flows
remain observable rather than being collapsed into a false no-flow claim.

`calculate_time_weighted_return_metrics()` now geometrically links the
subperiod factors around every explicit flow, withholds results when native flow
reports are incomplete or boundary evidence is missing, and emits an explicit
elapsed-UTC annualized return using a caller-supplied days-per-year convention.
Existing calendar, rolling, and distribution aggregators remain intentionally
unchanged and fail closed for flow-bearing inputs until they consume this
boundary evidence directly.

Validation on the exact implementation tree passed all 83 Strategy Lab v2
package tests, Ruff checks for the changed files, MyPy for the package, and
`git diff --check`. No provider, ETF, TC2000, persistence, API, worker,
Compose, Nautilus, frontend, integration, promotion, or deployment paths were
changed. The next bounded slice is the boundary-aware wiring for those existing
calendar/rolling/distribution aggregators.

## 2026-09-16 - Calendar-period boundary wiring checkpoint

Product commit `88cc14dda12aa43f49a18e5199248ec25e05283e` wires the explicit
flow-boundary path into `calculate_calendar_period_metrics()`. Complete
flow-bearing periods now report the geometrically linked return when all
pre/post marks are present; missing boundary evidence remains an explicit null
reason. Net P&L continues to reconcile the reported flow independently.

The exact package tree still passes all 83 tests, Ruff, and MyPy. The remaining
boundary-aware metric work is limited to rolling-window and session-distribution
aggregators; no shared provider, ETF, TC2000, persistence, API, worker,
Compose, Nautilus, frontend, integration, promotion, or deployment paths were
changed.

## 2026-09-16 - Rolling and distribution boundary wiring checkpoint

Product commit `f7bb6383bcdafb3695c07061b313fc7c71f6e9b5` completes the
boundary-aware metric wiring. Rolling windows now use geometrically linked
flow-adjusted returns and normalized wealth marks for volatility, Sharpe,
Sortino, drawdown, duration, and Ulcer calculations. Session-return
distributions use the same per-session factors and retain
`returns_flow_adjusted` provenance on the typed summary contract.

The exact implementation tree passed all 83 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`; the consolidated range was published under
the explicit destination authorization and local/remote HEAD match at
`f7bb6383bcdafb3695c07061b313fc7c71f6e9b5`. The next bounded engine-neutral
metric slice is capital/margin utilization or financing evidence. No provider,
ETF, TC2000, persistence, API, worker, Compose, Nautilus, frontend,
integration, promotion, or deployment paths were changed.

## 2026-09-16 - Engine-reported capital and margin utilization checkpoint

The next package-owned metric slice adds immutable
`AccountCapitalMarginObservation` records and
`calculate_capital_margin_utilization_metrics()`. Each observation binds a
portfolio version, run attempt, ordered engine point, positive account equity,
initial and maintenance requirements, supplied capacities, base currency, and
valuation evidence. The calculator emits equally sample-weighted means and
observed maxima for requirement-to-capacity and requirement-to-equity ratios.
It accepts ratios above one as diagnostics and never infers margin, leverage,
or buying power from notional exposure.

The exact implementation tree passed 85 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Financing evidence outside fill reports and
trusted paired inference remain open metric gaps. No provider, ETF, TC2000,
persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths were changed.

## 2026-09-16 - Trial-bound evaluation-window checkpoint

The metric-scope slice adds immutable `EvaluationWindow` records with explicit
evaluation start/end, purpose, and optional warm-up start. The window is bound
into `ScientificTrial` identity and projected into `SensitivityMetricScope`;
`SensitivityComparisonEvidence` now rejects variants that use different
evaluation or warm-up windows. Offset-aware timestamps normalize to UTC and
invalid ranges fail closed.

The exact implementation tree passed 94 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Additional risk evidence and all persistence,
API, worker, and runtime gates remain open. No provider, ETF, TC2000,
persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths were changed.

## 2026-09-16 - Explicit stress-scenario evidence checkpoint

The next engine-neutral risk slice adds `StressScenarioObservation` and
`calculate_stress_scenario_metrics()`. Adapter-supplied initial/stressed equity
and P&L must reconcile exactly and bind a shock-definition digest plus engine
evidence. The calculator emits descriptive scenario/loss counts, average and
worst stressed returns and P&L, and minimum stressed equity. It does not
construct shocks, extrapolate outcomes, or issue a solvency/risk verdict.

The exact implementation tree passed 94 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Metric-scope completeness and all persistence,
API, worker, and runtime gates remain open. No provider, ETF, TC2000,
persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths were changed.

## 2026-09-16 - Explicit financing-cost evidence checkpoint

The next package-owned metric slice adds immutable
`FinancingCostObservation` events and bounded `FinancingCostReport` records.
`calculate_financing_cost_metrics()` keeps financing outside fill-cost reports,
tracks complete/partial/unavailable coverage explicitly, and publishes the
signed reported cash effect for all supplied events. It publishes derived net
financing cost only when every supplied report is complete; incomplete coverage
cannot be interpreted as zero financing. Report and event digests, model
identity, base currency, ordered points, and scope are bound to the metrics.

The exact implementation tree passed 88 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Trusted paired-stream inference remains the next
metric gap. No provider, ETF, TC2000, persistence, API, worker, Compose,
Nautilus, frontend, integration, promotion, or deployment paths were changed.

## 2026-09-16 - Aligned paired-observation metrics checkpoint

The next metric slice adds `PairedMetricObservation` and
`calculate_paired_metric_metrics()`. A verified keyed-stream receipt is
required; observations are keyed, deduplicated, canonically ordered, and
validated as finite Decimal baseline/variant values. The calculator emits
descriptive baseline/variant means, signed mean delta, nearest-rank median,
minimum/maximum delta, and sample standard deviation with receipt and input
digests. It intentionally does not rank candidates, estimate significance, or
claim an inferential model.

The exact implementation tree passed 91 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Metric-scope completeness, risk/stress evidence,
and all persistence/API/worker/runtime gates remain open. No provider, ETF,
TC2000, persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths were changed.

## 2026-09-16 - Keyed common-random stream verification checkpoint

The next engine-neutral slice adds `pairing.py` with typed
`KeyedRandomDraw` inputs and `verify_keyed_random_stream_pairing()`. The
verifier requires registered engine-build/conformance and stream-contract
digests, rejects empty, duplicate, unmatched, or value-mismatched draws, and
emits a deterministic `KeyedRandomStreamPairingReceipt`. Sensitivity evidence
can bind that receipt and is classified as `verified_paired`; the downstream
comparison remains descriptive and makes no significance or ranking claim.

The exact implementation tree passed 90 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Aligned per-observation inferential metrics,
ranking, significance, and all shared persistence/API/worker/runtime gates
remain open. No provider, ETF, TC2000, persistence, API, worker, Compose,
Nautilus, frontend, integration, promotion, or deployment paths were changed.

## 2026-09-16 - Static strategy-source preflight checkpoint

Product commit `ddac66de4` adds `strategy_validation.py`, a deterministic AST
preflight that binds every result to the exact source digest and rejects
disallowed or relative imports, filesystem/network roots, dynamic-code calls,
aliases of dangerous builtins, and private-object introspection. A forbidden
root remains rejected even when a caller attempts to broaden the allowlist. The
preflight is intentionally an early rejection layer, not the runtime security
boundary: isolated execution, no-network/read-only filesystem enforcement,
resource limits, secret exclusion, and adversarial container tests remain open.

The exact implementation tree passed all 100 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`; the product commit is published at the
authorized `origin/feat-strategy-lab-v2` destination. Persistence, API, worker,
artifact, Compose, Nautilus, frontend, integration, promotion, and deployment
paths remain unchanged. The next bounded slice is an engine-neutral
artifact/result-integrity contract while preserving this static-preflight and
runtime-isolation boundary.

## 2026-09-16 - Artifact payload integrity checkpoint

The next engine-neutral slice adds `artifacts.py` with raw-byte SHA-256 content
addressing and `ArtifactIntegrityReceipt`. `verify_artifact_payload()` compares
an already-read payload to its immutable manifest's digest and exact byte
length, returning deterministic `digest_mismatch` and/or
`byte_length_mismatch` evidence without retaining bytes or performing storage
I/O. Invalid payload types fail fast; retrieval, atomic publication, retention,
and worker/storage ownership remain deferred.

The exact implementation tree passed all 104 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Static source preflight remains an early
rejection layer rather than the runtime security boundary. Persistence, API,
worker, artifact-store, Compose, Nautilus, frontend, integration, promotion,
and deployment paths remain unchanged.

## 2026-09-16 - Artifact publication-plan checkpoint

`artifact_publication.py` adds a storage-neutral publication decision that can
only be produced from a verified `ArtifactIntegrityReceipt`. It requires
immutable create-if-absent semantics, reuses an already-present content
address without overwriting it, and exposes pin requirements from the manifest
retention class. It performs no storage I/O and does not claim atomicity until a
future adapter implements and tests that operation.

The exact implementation tree passed all 107 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Runtime artifact storage, retention
enforcement, persistence, API, worker, Compose, Nautilus, frontend,
integration, promotion, and deployment paths remain unchanged.

## 2026-09-16 - Result artifact integrity checkpoint

`result_integrity.py` adds a pure result-level verification contract for
successful `RunResultManifest` records. It requires one unique, verified
payload receipt for every referenced output artifact, reports missing,
unexpected, foreign, or unverified digests deterministically, and binds the
coverage result to the full manifest fingerprint. It performs no storage I/O
and does not certify engine semantics or publication atomicity.

The exact implementation tree passed all 107 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Execution-attempt lifecycle, persistence,
API, worker, artifact-store, Compose, Nautilus, frontend, integration,
promotion, and deployment paths remain unchanged.

## 2026-09-16 - Execution-attempt lease checkpoint

`lifecycle.py` now includes typed `ExecutionAttemptLease` records and
`acquire_attempt_lease()`. Leases can be acquired only by running attempts,
renew only while active with monotonic timestamps, and transition explicitly to
released or expired states. The pure contract supplies worker-side lease
evidence without persistence, scheduling, or automatic clock access; result
publication must still be guarded by a live lease in the future worker.

The exact implementation tree passed all 110 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Capability execution preflight, persistence,
API, worker, artifact-store, Compose, Nautilus, frontend, integration,
promotion, and deployment paths remain unchanged.

## 2026-09-16 - Engine capability-binding checkpoint

`execution_capabilities.py` adds a typed binding between the strict/degraded
data preflight and a registered engine build/conformance identity. Product,
execution-model, and account-model gaps fail closed; a non-authoritative engine
can provide compatibility evidence but cannot publish authoritative results.
The binding is engine-neutral and performs no runtime loading or execution.

The exact implementation tree passed all 113 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Forward-event/result-state handling,
persistence, API, worker, artifact-store, Compose, Nautilus, frontend,
integration, promotion, and deployment paths remain unchanged.

## 2026-09-16 - Forward event-state application checkpoint

`apply_forward_event_observation()` now applies classified canonical events to a
`ForwardInstance` without implicit replay or state loss. Contiguous accepted
events advance the stored event identity/sequence; gaps, duplicates, and
out-of-order events preserve the cursor; corrections increment an append-only
counter and retain the prior decision cursor. Event arrival timestamps remain
monotonic, and the function performs no persistence or external event I/O.

The exact implementation tree passed all 113 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Forward-state persistence/idempotency,
database/API, workers, artifact-store, Compose, Nautilus, frontend,
integration, promotion, and deployment paths remain unchanged.

## 2026-09-16 - Execution authorization-gate checkpoint

`execution.py` adds `authorize_execution()`, which composes accepted static
source validation, trial-bound capability evidence, matching running-attempt
identity, and an active worker lease into one immutable authorization record.
The gate fails closed on unsupported capability, mismatched trial/lease, bad
source, non-running attempts, expired leases, or non-monotonic timestamps. It
does not import or invoke an engine, access storage, or carry secrets.

The exact implementation tree passed all 116 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Forward-state persistence/idempotency,
database/API, workers, artifact-store, Compose, Nautilus, frontend,
integration, promotion, and deployment paths remain unchanged.
