# Handoff: fix-gate-flakes-and-live-acceptance-test

## A. E2E flakes (e2e-functional)
- Root cause not provable without the CI trace. Strongest candidate: after the second watchlist POST resolves,
  `submitCreate` closes the create form asynchronously, shifting the sidebar list while the test clicks
  "More options". A click landing mid-shift never toggles the menu (`sidebarMenuId` stays null), so the later
  `Rename` click waited 60s for an item that was never rendered. The app logic (menu state keyed by id,
  keyed v-for, document click closed by `.stop`) was reviewed and has no menu-closing path on list refresh.
  The same unverified click-then-menuitem pattern exists in the F14 drawing test.
- Fix (test only): wait for the create form to be gone after each create; `openWatchlistRowMenu` asserts the
  trigger's `aria-expanded` goes false -> true, so a swallowed click fails in 5s naming the real cause. F14 does
  the same for the Lines flyout. No retries, no timeout changes.
- flows.spec.ts 21.4m: 189 serial tests in one worker with `--retries=0`; no single root cause found. Not changed.
- Not run locally (needs the Docker stack); tsc clean on both specs.

## B. stage=backend-coverage exit=2
- `exit=2` is make's generic status for any failing recipe (`$(MAKE) test-backend-coverage`), so it hides the real
  status. scripts/backend_coverage.py can fail via any shard (pytest 1, 124 timeout 300s unit / 900s integration,
  137 OOM), `coverage report --fail-under` (exit 2), or its own collection checks. Public annotations contain only
  the generic line; job logs are unavailable, so the cause of the two historical failures is unknown.
- Added diagnostics: each failure prints `::error title=Backend coverage failed::<label> exit=N (reason); failing
  tests: ...` (failing IDs from a per-shard junitxml), also for collection and coverage-report failures.
- Test: tests/workflow/test_backend_coverage.py::test_failed_shard_emits_annotation_*.

## C. test_all_provider_calling_services_require_full_live_acceptance
- Real gap: backend/app/services/identity_batch.py calls execute_provider_call/get_provider but was missing from
  `provider_service_modules` in scripts/agent-session.py, so changes to it would not require full live acceptance.
  Added it (test untouched).
- CI: tests/workflow runs only in the `workflow` changed-scope lane (ci.yml "Check workflow behavior"); the broad
  lane runs only declared branch tests, so this test never ran there. Lane left unchanged (reported only).
