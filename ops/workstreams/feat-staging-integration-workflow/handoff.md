# feat/staging-integration-workflow

## Authorization and intent

The human explicitly approved a persistent `staging` integration line, removal of local candidate
worktrees from the active workflow, architecture-neutral normal CI, and deployment-triggered RPi
platform validation. This branch depends on the earlier workflow-policy/lifecycle branches because
it supersedes their integration mechanism while preserving their intent and historical accounting.

## Active context

Implement and validate the executable staging workflow, CI routing, worktree ancestry rules,
target-specific RPi configuration, migration baseline, canonical agent policy, human documentation,
and focused workflow regressions. No staging bootstrap, integration, promotion, or deployment is
authorized by this implementation request alone.

## Current state

The human exceptionally authorized this branch to complete its normal lifecycle, including the
one-time integration into `master` and bootstrap of `staging` after the exact gate is green.
The branch is now `ready_for_integration`; the final closure checkpoint records the validated
implementation SHA and uses `integration_capture: exact branch HEAD` so the integration command
captures the final docs-only checkpoint without an impossible self-referential hash.

The first exhaustive gate passed backend coverage (`1646` tests) and frontend Vitest (`922`),
then failed `F8e.swing-analysis` after `153` browser tests passed and `106` skipped. The screenshot
showed `Plots 0` after returning to XLB: the inherited test waited for the RSI PUT request but not
its successful response before later navigation. The oracle remains unchanged; the harness now
waits for the successful response before asserting restoration. First-failure screenshot, video,
error context, and the complete RTK log were preserved for diagnosis.

A later exact-tree exhaustive rerun passed the backend and frontend suites, then retained two
additional inherited browser failures. `F9e-shell-menus-keyboard` proved that the workspace
menu's bounded DOM-attachment retry could steal focus back to its listbox after a rapid valid
keyboard command. The retry now runs only when focus is still outside the mounted menu.
`F8s-personal-watchlist-error` clicked Add Tool during dock activation without waiting for the
new WatchList tab; it now follows the same visible-tab/active-tab synchronization used by the
neighbouring accepted watchlist flows. Their behavioural oracles are unchanged. The full log is
the RTK tee record `1787608580_make_validate-integration_INTEGRATION_BR.log`; the corresponding
Playwright screenshots, videos, and error contexts were retained under `frontend/test-results`
through diagnosis; the focused reruns then replaced that generated directory, while the durable
failure classification and RTK log reference remain here and in `validation.jsonl`.

Both repaired cases now pass together once and for 10 consecutive repetitions each (`20/20`).
The initial focused launch failure was a macOS sandbox denial before Chromium started, not a test
result; the approved browser execution boundary then exercised the actual application successfully.

The final exact-tree `make validate-integration` completed with exit code `0`. It replayed frozen
dependency/export checks, migration compatibility, Ruff and frontend static/build checks, backend
and frontend coverage suites, Compose and deployment contracts, provider/research-runner checks,
the full seeded functional browser suite, four-environment visual suite, and branch-declared
workflow tests. It used no QEMU or target-specific image build and removed only the exact branch
Compose project and volumes afterward. The branch is ready for human review, but human closure,
integration, staging bootstrap, promotion, and deployment are not authorized.

Final diff review then found and closed a remote-reference race: an external staging/master
advance during a long GitHub gate could previously be compared against a cached remote-tracking
reference. Integration and promotion now fetch the relevant remote head after the exact CI run and
reject any advance before declaring success or writing a receipt. `staging-status` also resolves
the actual master worktree instead of treating the caller's feature checkout as master. Fourteen
focused workflow regressions and Ruff checks pass after this hardening. The subsequent exact-tree
exhaustive replay also completed with exit code `0`, including the full browser and four-environment
visual suites, then removed only the branch-scoped Compose resources. This is the final validated
tree for the implementation commit.

GitHub Actions independently replayed implementation commit
`d845653e34bacc9dfafc1eb75d4a7f7d9b28604c` in run
`32786834842`. Backend Tests, Frontend Unit Tests, Branch-declared Tests, and E2E Tests
(Playwright) all passed. The Exhaustive Integration Gate was correctly skipped because this is a
feature branch; the workflow requires that gate on `staging` and `master`. The Node 20 action-runtime
deprecation messages are warnings from upstream action versions, not test failures. This evidence
checkpoint intentionally does not claim its own follow-up commit as the tested implementation SHA,
avoiding an infinite metadata-only validation loop.

During the human-facing `.ai` inventory, `make worktree-overview` exposed a first-bootstrap gap:
it assumed that the new persistent `staging` branch already existed, so it could not report the
pre-bootstrap worktree state. It now explicitly compares branches with `master` until `staging`
exists, includes `comparison_base` in its JSON, and automatically reverts to staging comparison
after bootstrap. This does not permit closure before staging integration; it makes that blocked
state visible. The focused workflow suite passes (`14/14`) and the complete integration gate passed
again, including backend/frontend coverage, functional Playwright (`154` passed), all four visual
environments (`104` passed), and cleanup of only this branch's full-stack resources.

## 2026-08-27 — Scoped CI/CD housekeeping authorization and pre-staging archive

The human explicitly authorized agents to complete CI/CD-only housekeeping end-to-end when its
declared validation remains green, while retaining human closure for product behaviour,
provider-monitoring behaviour, deployment implementation/target configuration, live-provider
probes, and any red/flaky/inconclusive gate. The workflow documentation now records this scope.

Added the separate `worktree-archive-pre-staging` path. It is storage housekeeping only: before
the persistent `staging` branch exists, it removes a local checkout only when the worktree is
clean, outside the root checkout, not in a merge, stopped, synchronized with its remote, and its
exact tip is already reachable from synchronized `master`. It keeps the remote branch and tracked
workstream record; it never claims staging acceptance and never deletes remote history. Normal
`worktree-close` remains staging-only. The human-facing overview reports this eligibility
separately from ordinary close.

Focused validation: workflow tests passed (`16/16`), workstream validation passed (`28` records),
Python syntax and `git diff --check` passed. No application or deployment behaviour was changed.

## Local archive disposition

With the standing CI/CD housekeeping authorization, the following redundant local checkouts were
archived after the guarded pre-staging checks passed: `docs/parallel-workflow-final-receipt`,
`docs/parallel-workflow-final-receipt-v2`, `feat/integration-gate-completeness`,
`fix/arm64-ci-emulation`, `fix/ci-gate-timeout`, `fix/integration-replay-registration`,
`fix/master-gate-observability`, `fix/playwright-popout-teardown`,
`fix/research-runner-probe-portability`, and `fix/research-runner-probes`.

For each branch, the exact local tip matched `origin/<branch>`, the tip was already reachable from
the synchronized `master`, the checkout was clean and outside the root integration checkout, no
merge was in progress, Docker reported no running managed project, and only the local worktree and
local branch were removed. Every remote branch and tracked workstream record remains available;
this is not semantic topic closure. No provider, product, staging, or RPi worktree was removed.

The workflow now also exposes `worktree-archive-subsumed` for a child branch whose exact tip is
contained in a named cumulative parent worktree. It removes only that redundant local checkout
after proving both branches are clean and remote-synchronized, the child is an ancestor of the
parent, no child Compose project is running, and both worktrees are under `.ai/worktrees`. Remote
branches and tracked records remain; this is explicitly not a second merge mechanism.

The first invocation exposed and corrected an implementation detail: the current caller can itself
be the cumulative parent worktree, so the root-integration guard must compare against the actual
`master` worktree path rather than the caller's checkout path. The corrected helper is validated
before any predecessor is removed.

The six predecessor checkouts (`chore/worktree-cleanup-audit`, `feat/dependent-branch-policy`,
`feat/human-intent-guard`, `feat/workflow-unification`, `feat/worktree-operations-overview`, and
`fix/integration-candidate-lifecycle`) were then archived with that guard. Each child was clean,
remote-synchronized, and contained in this cumulative parent; only its local checkout/local branch
was removed. The cumulative `feat/staging-integration-workflow` checkout remains active, and every
remote child branch plus its tracked workstream record remains available for the eventual staging
integration audit.

The post-correction overview now identifies the actual `master` checkout correctly. The cumulative
staging worktree is reported as blocked only because it is not yet published on `master` (and while
this checkpoint is being recorded, its own correction files are temporarily dirty); it is never
eligible for local archival. The five retained active worktrees are clean, synchronized, and
eligible for storage-only pre-staging archive if their local checkouts are later no longer useful.

Final focused rerun after the archive-tool changes passed: `make validate-focused-integration
INTEGRATION_BRANCH=feat/staging-integration-workflow` completed with the workstream validator,
workflow syntax checks, the 17 workflow tests, and all declared branch tests green. The first
unprivileged invocation failed only because the sandbox could not read the UV cache; the unchanged
command passed through the approved execution boundary. No application or deployment gate was
waived.

The local `fix/arm64-ci-qemu` checkout was also archived with the pre-staging guard. Its exact tip
is already published on synchronized `master`; its remaining physical-Pi rehearsal is externally
blocked. The remote branch and deployment workstream record remain available, and no other
deployment or product checkout was removed.

The completed archival run removed all six child checkouts; the first retry message about the first
child being absent was only because the shell had already completed that child before its output
stream closed. A follow-up inventory confirmed none of the six local worktree registrations or
local branches remain, while every corresponding `origin/<branch>` ref is still present.

The allocator reclamation pass was then run. It removed only runtime registry entries and generated
env files whose worktree paths were no longer registered and whose exact managed Compose projects
were confirmed stopped. The registry now contains only `master` and the five retained active
worktrees; no active allocation, port, volume, network, or configuration was reclaimed.

## 2026-08-27 — Operational-tail lifecycle and allocator residue cleanup

The normal branch comparison remains `staging` after bootstrap. The new
`worktree-archive-operational-tail` command is explicitly pre-staging-only and refuses once a
local or remote `staging` ref exists. Before bootstrap it can remove a closed local branch whose
implementation is already in synchronized `master` only when the branch is clean and remote-
synchronized, Docker proves its managed projects are stopped, and every unmerged path is under
that branch's own workstream record. It retains the remote branch and record; it cannot remove
product, deployment, or unrelated documentation changes.

Using that guard, `fix/provider-monitoring-hardening`, `fix/workflow-hardening`, and
`fix/master-gate-hardening` were marked `closed` as superseded active lines and their local
checkouts/local refs were removed. Their implementation boundaries are already in `master`; the
remote branches and closure/evidence records remain. The cumulative staging branch and the RPi
deployment worktree were not removed.

The runtime allocator now removes only generated `.ai/runtime/*.env` files whose allocation IDs
are no longer registered. After the archive, the registry and env directory contain only the
`master`, `feat/staging-integration-workflow`, and `fix/rpi-deployment-contract` allocations.

Validation: `backend/tests/unit/test_worktree_runtime.py` plus
`tests/workflow/test_staging_workflow.py` passed `21/21` with `--no-cov`; Python syntax and
`git diff --check` passed. The implementation checkpoint was pushed and synchronized; the
enclosing commit is verified by `git rev-parse`.

## 2026-08-27 — Exceptional closure and exact final gate

The human explicitly authorized this branch to proceed through closure, integration, and the
one-time staging bootstrap. The final implementation checkpoint `2f97d7dc02e61d8cb088f969df08b86080499024`
passed the complete local integration gate: frozen dependencies/export consistency, migrations,
Ruff, backend coverage, frontend type-check/unit coverage/build, Compose/deployment contracts,
research-runner probes, seeded functional Playwright (`154 passed, 106 skipped`), four-environment
visual Playwright (`104 passed`), and the branch-declared tests. The branch's exact GitHub Actions
run `33106269877` also passed Backend Tests, Frontend Unit Tests, Branch-declared Tests, and E2E
Tests; its exhaustive job was correctly skipped because the branch is not yet `staging` or `master`.

The final closure record is documentation-only. It therefore uses
`integration_capture: exact branch HEAD`: the staging integration command must capture and record
the final synchronized branch SHA rather than attempting an impossible self-referential commit
hash. No migration or deployment action is included in this closure.

## Next exact action

From the clean root `master` checkout, recheck that `master` is still synchronized and not marked
degraded, merge this exact branch tip once with a non-fast-forward boundary, push and verify the
result, then run `make staging-bootstrap CONFIRM=<new-master-sha>`. If master is dirty, advanced,
or marked degraded, stop without modifying it and repair/replay that exact master revision first.

## 2026-08-27 — Integration and staging bootstrap completed

The explicitly authorized one-time lifecycle is complete. The final synchronized source tip
`289b2acdfbe939f85b2a5cf42ce198cb2877f069` was merged once into `master` as merge boundary
`540621d7cdd88ebe4ef9ef11b0675a867ea252b9` and pushed to `origin/master`. GitHub's independent
master replay passed Backend Tests, Frontend Unit Tests, Playwright, and the exhaustive integration
gate.

`staging` was then created from that exact green master SHA, pushed to `origin/staging`, and its
independent CI replay also passed Backend Tests, Frontend Unit Tests, Playwright, and the exhaustive
integration gate. Both branches and the persistent staging worktree are clean and synchronized;
neither is marked degraded.

The local `feat/staging-integration-workflow` worktree and local branch were removed only after
this verification. The remote `origin/feat/staging-integration-workflow` ref remains at the exact
closure tip, preserving its branch history and workstream record. The record is now marked
`integrated`; its remaining work is only the future normal staging integration/promotion rehearsal.
RPi deployment remains intentionally standby and was not attempted.

## 2026-08-27 — Post-bootstrap staging replay remediation

The first corrective documentation push to staging exposed one inherited product race in the
exhaustive browser suite (`F8e.swing-analysis`). The browser trace showed one successful RSI save
followed by three delayed `PUT /instrument-indicators/{id}` requests with an empty indicator list
while chart state was being hydrated during navigation. Those programmatic clear/hydrate updates
were incorrectly treated as user edits and could overwrite the saved stack; this was not a reason
to weaken the browser oracle or merely extend its timeout.

`frontend/src/stores/chart.ts` now schedules automatic persistence only after an explicit indicator
mutation marks the stack dirty. Hydration remains visible to the user but cannot write an empty
intermediate state. `frontend/tests/unit/stores/test_stores.test.ts` holds the indicator GET open and
asserts that no write occurs during that interval. The focused store suite passed 38/38, the complete
frontend Vitest coverage suite passed 923/923, and the rebuilt staging stack passed ten consecutive
`F8e.swing-analysis` repetitions. The complete workstation flow file passed 151 tests with two
documented skips. The exact staging SHA remains blocked from promotion until its independent GitHub
exhaustive replay is green.
