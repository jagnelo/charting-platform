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

Implementation is in progress. Human closure authorization remains pending.

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
