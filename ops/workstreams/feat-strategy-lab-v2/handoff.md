# feat/strategy-lab-v2

Created from `staging` at `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`.

## Human authorization

- Recorded at: 2026-09-15T19:48:24.815519+00:00
- Request: Implement the approved Strategy Lab v2 plan; honor the repository AI-driven workflow rules and active branch boundaries.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: draft; the implementation agent must complete scope, acceptance criteria, tests, and local validation profile before creating a goal.

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
`make branch-validate` currently validates all 30 workstream records. The
session-local goal is active. Initial canonical serialization and immutable
domain contracts are now being added only under the new package; capability,
SDK intents, experiment expansion, metrics, and deterministic tests follow.

Session `603da09c-b640-4018-9f40-c62f4564b074` owns this worktree. Do not edit
another worktree, even if dependency work advances in parallel; reconcile its
staged changes here only after an authorized staging update.
