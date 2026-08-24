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
