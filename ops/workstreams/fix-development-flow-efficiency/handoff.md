# fix/development-flow-efficiency

## Current state

Root-authorized workflow repair is implemented locally in the assigned branch.
The native unbudgeted goal on this same visible thread is active. The Root
bootstrap exception is recorded in `plan.yaml`: the reviewed local plan and
exclusive claim remain required; a plan-only push is skipped; normal clean,
synchronized exact-source checks still apply at integration.

## Changes

- Added exact changed-path lanes. Metadata/workstream changes run durable
  hash/scope/narrative guards; workflow-only changes run workflow regressions.
  Both require an exact trusted successful full product qualification for the
  parent SHA and prove the current diff contains only allowlisted paths. Missing
  prior evidence, unknown paths, product changes, and renames touching runtime
  inputs fall back to broad validation.
- Staging remains the single full integration gate at cross-feature batch
  boundaries. Master promotion now checks the exact successful staging workflow,
  push event, SHA, complete required job set, and synchronized refs, then runs
  release identity/provenance checks. The promotion helper requires exact
  staging and master run IDs and the explicit same-SHA reuse mode; the master
  verifier itself checks the complete successful staging job set. Master
  publishes only the uniquely named `Master Release Provenance` status; no
  duplicate integration-gate alias is emitted. Receipt schema 2 records
  same-SHA reuse explicitly, and the RPi reader accepts both the previous
  schema-2 job list and legacy `github_replay=pass` receipts.
- The observer makes one status-only read per three minutes for up to 243
  minutes, covering the 45-minute backend prerequisite plus the 180-minute
  exhaustive gate; it fetches job details once after terminal status and reports
  expiry as pending, and seeks at most 12 retry attempts only after a failed
  allowlisted setup step. Rate-limit/access failure remains unavailable evidence.

## Measured cost implication

The observed feature baseline is about 31 minutes backend plus 23 minutes
browser tests per push, roughly 54 minutes; workstream-only closure repeated the
same jobs. Eligible guarded pushes avoid those product jobs after exact parent
qualification. The focused workflow suite completed 192 tests in 2.31 seconds
locally, and the required runtime/YAML narrative guard passed in 9.21 seconds.
The prior roughly two-hour master replay is removed for the identical staging
SHA; master release verification has a 10-minute job bound. Staging still runs
the full gate once per meaningful batch.

## Validation

- Workflow tests: 195 passed in 2.91 seconds after the observer and promotion guards.
- After the final `branch-tests.json` broad-lane correction, the affected
  classifier/temp-Git sequence and local-profile checks passed 9/9 in 0.56
  seconds; the full workflow suite was not rerun for this allowlist-only edit.
- Workstream record validator: passed for this branch's ready plan.
- Runtime/YAML narrative guard: passed, 1 test in 9.23 seconds with `--no-cov`.
- Ruff check and format check: passed for all changed Python files.
- `git diff --check`: passed.
- No full product/browser/Docker/provider suite was rerun locally; no pass is
  claimed for any skipped suite beyond trusted, exact same-source prior evidence.

## Closure state

At published SHA `26cf65de`, Root accepted the bounded implementation under the
human's standing delegation and left exact pushed-source CI to Root. The later
API review reopened only the duplicate job-name and scoped-parent fallback
findings listed below. No integration, promotion, or deployment is performed
from this worktree. The live ticker repair release remains independent.

## Root review correction addendum

Root identified two concrete issues after published SHA `26cf65de`:
GitHub emits duplicate display names when the master compatibility alias is
skipped, and a later eligible commit cannot reuse full qualification at the
exact common ancestor after its immediate parent has only scoped CI. The
corrective commit removes the alias and permits ancestor fallback only after a
direct full-delta allowlist check plus full qualification of that same SHA.
Product-bearing unqualified parents remain broad. The prior acceptance record
and tests remain historical evidence; these two corrections are the only
reopened scope.

The focused correction suite passed 90/90 in 1.68 seconds. It covers the
workflow-wide unique display-name invariant, master release-only success
requirements, previous schema-2 receipt compatibility, the actual shell
sequence after a scoped parent, and a product-bearing negative ancestor case.
Root's corrective acceptance confirms all 18 reviewed implementation hashes and
technically accepts AC1/AC4/AC8/AC9. Exact pushed-source CI remains pending for
Root; no product suite was rerun. The first canonical promotion must use the
qualified helper from persistent staging with Root coordinator cwd and the
explicit schema-2 same-SHA receipt; Root owns integration, promotion, and
deployment.

The accepted workflow-file hash was `b7b50f28…`; `git diff --check` exposed one
extra blank line at EOF, which was removed without logic changes. The final
workflow-file hash is `ff8bab6a…`; exact CI on the new published SHA is the
authority for that final file.

## AC10 staging single-gate follow-up

Human authorized this bounded throughput follow-up before Root's canonical
adoption. Root reviewed the first draft and requested legacy four-job
qualification compatibility, explicit receipt profile round-tripping, and a
stronger staging exclusion check; those corrections are included. Staging now
runs changed-scope and then the unchanged `make validate-integration` gate.
Standalone backend, frontend-unit, and E2E jobs are skipped on staging and are
not prerequisites of the full gate. Broad feature branch checks remain.

The baseline staging path spends about 28-32 minutes waiting on standalone
backend tests before starting the gate, while frontend-unit and standalone E2E
also run separately. The single-gate path removes that backend lead time and
separate runner jobs; expected critical-path reduction is at least 28-32
minutes, plus any frontend/E2E time extending beyond it. The complete existing
backend, frontend, functional browser, strict visual, provider-safe, migration,
workstream, and cleanup phases remain in the Makefile gate and run once.

Focused regressions cover staging routing, unchanged Makefile phases, broad
feature behavior, strict new-profile job statuses, legacy four/five-job full
evidence, prior qualification on staging/master, receipt read/write profile
semantics, and rejection of scoped master evidence. The final focused run is
99 passed in 1.80 seconds. Root's final review verified the current source
hashes and accepted AC10 under the human's standing delegation; durable
acceptance is in `workflow-AC10-implementation-technical-acceptance.json`. All
AC1-AC9 acceptance and history are preserved. No Makefile, product source,
collector, other worktree, protected branch, integration, promotion, or
deployment was changed. The independent 45cc release remains untouched.

## AC10 closure

All ten criteria are complete and the branch is ready for integration. The
only remaining gates are exact CI on this new pushed SHA and Root's protected
canonical staging/master adoption. `integration_capture: exact branch HEAD`.
Root retains integration, promotion, and deployment ownership.

## Independent E2E scheduling follow-up

Root-authorized follow-up changes only `e2e.needs` to `[changed-scope]`. The
E2E job already installs its own dependencies and browser, builds and starts its
own Compose stack, runs Playwright, and always tears the stack down. This lets
it run beside backend and frontend-unit jobs. Focused structural and
final-evidence regressions passed 7/7 in 0.34 seconds; exact branch qualification
still requires unique completed successful backend, frontend-unit, and E2E
jobs (or the existing trusted scoped profile). Root's delegated technical
acceptance is recorded in
`.ai/staging-attempts/workflow-parallel-browser-context-root-review-20261105.json`;
the authorized publication preserves merge parents `45cc820` and `05d98ea`.
No product, Makefile, runtime-tree, or protected-branch change was made. Exact
CI and release ownership remain with Root.

## Hosted branch command portability

Exact run `42096402834` on `ea0d3c4` remains **overall red**: Backend Tests,
Frontend Unit Tests, and E2E passed, but Branch-declared failed before pytest
because current plan commands embedded a workstation `UV_PROJECT_ENVIRONMENT`
and local-only UV flags. This workstream has no `branch-tests.json`, so the
runner executes the plan's `branch_tests` directly. Updated only those
current/future command declarations to `uv run --project backend`; historical
`validation.jsonl` entries remain unchanged.

The actual `scripts/run-branch-tests.py` completed under a hosted-like
environment without host project/cache overrides, `UV_NO_SYNC`, `UV_OFFLINE`,
or `rtk` in the generated commands: 211 workflow tests passed in 2.36 seconds,
the narrative guard passed 1/1 in 12.22 seconds, and 47 workstream records
validated. The focused runner test, changed-file Ruff, own-record validator and
diff checks also passed. Root's delegated acceptance is conditional on this
portable runner proof, which is now satisfied; no full product/browser/Compose
matrix was rerun. The red `ea0d3c4` run is retained as failed history. Root owns
exact CI, qualified-base context, and final publication/adoption.

## Fail-fast branch manifest validation follow-up

Root activated this bounded follow-up under the human's urgent workflow mandate.
The branch first merged exact synchronized-green staging/master commit
`a9ee26d46ca057d4bbc0bf3fc51e3507157bf6a7` normally. Provider run
`42204424643` spent about 23 minutes in Backend Tests before its
Branch-declared job immediately failed on `plan.yaml` / `branch-tests.json`
parity. The existing `execution_manifest` validator now has a
`--validate-only` mode that checks explicit manifests without executing
commands and accepts the existing no-manifest plan fallback.

The Changed-path validation scope job invokes that check before path
classification on ordinary feature pushes and PRs. Direct master/staging pushes
skip the feature manifest check; PRs still validate their source branch. Backend,
frontend-unit, E2E, and branch-declared jobs already require changed-scope, so a
manifest mismatch fails before product jobs begin. The runner itself is added
as one exact workflow-tool allowlist path; prior qualification and broad fallback
rules are unchanged. Guidance now documents the local pre-publication check.

Checkpoint files: `.github/workflows/ci.yml`, `docs/agent-orchestration.md`,
`scripts/ci-change-scope.py`, `scripts/run-branch-tests.py`,
`tests/workflow/test_ci_change_scope.py`,
`tests/workflow/test_run_branch_tests.py`, and this workstream's `plan.yaml`,
`handoff.md`, `validation.jsonl`, and `session.json`.

Root conditionally accepts this narrow checkpoint after focused checks and exact
closing-tip CI. Focused runner/scope regressions and actual no-manifest
validation-only CLI proof passed; no branch commands ran in validation-only
mode. Product behavior, provider policy, sibling worktrees and protected refs
were not changed. Root owns exact CI and integration. `integration_capture:
exact branch HEAD`.

## Changed-scope step-order correction

Root's exact CI run `42209366171` on `4ca8133` failed one existing structural
assertion because the new validation step displaced `Classify exact changed
paths` from index 1; 214 other workflow tests passed. Moved the validation-only
step after classification in the same job. The job still completes before any
backend, frontend-unit, E2E, or branch-declared job can start, and all prior
qualification and scope guards remain unchanged. The corrected full fast
workflow suite passed 215/215 in 1.81 seconds. The `4ca8133` overall CI remains
red and unqualified; Root owns push and exact CI for this corrective commit.
