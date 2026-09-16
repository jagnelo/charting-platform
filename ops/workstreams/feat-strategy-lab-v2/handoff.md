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

## Active changeset - Trial seed-sharing and replicate provenance

This next implementation context owns only
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
private origin is unavailable. Do not use an alternate transport. Exact next
action: finish this separate operational checkpoint, then continue with an
engine-neutral sensitivity result model that distinguishes independent,
shared-seed-only, and genuinely paired evidence; keyed-stream eligibility stays
deferred to engine conformance.

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
