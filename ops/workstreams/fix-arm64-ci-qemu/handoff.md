# fix/arm64-ci-qemu

Created from `master` at `ca27acbf6ee09e543d57dbec4a7ffdf64c4c3b52`.

## Incident

The exact master replay `32524824692` passed backend, frontend, and Playwright
jobs, then timed out after 180 minutes in `make validate-integration`. The
preserved log shows `qemu: uncaught target signal 4 (Illegal instruction)` in
the frontend Dockerfile's `npm ci` step while building the ARM64 image on the
x86 GitHub runner. This is an image-build/emulation failure, not an application
test failure.

## Repair

The frontend Dockerfile now builds static assets with
`FROM --platform=$BUILDPLATFORM node:20-alpine` and serves them from
`FROM --platform=$TARGETPLATFORM nginx:alpine`. The final image remains
linux/arm64, while Node runs natively on the builder architecture. A contract
test locks this split in place.

## Validation boundary

Targeted deployment contract tests, the full local integration gate, and the
branch CI replay all pass. The local gate completed 1,646 backend tests,
frontend coverage/type/build checks, 260 functional Playwright tests (154
passed/106 skipped), 104 visual tests, research-runner probes, and all three
Linux ARM64 image builds. Branch CI run `32538510336` is green. During exact
candidate validation, one Playwright performance test flaked (`canvas` count 5
vs expected 3); its screenshot/video/error context was retained under the
candidate worktree, and the exact test passed on an immediate isolated rerun
(7.5s). A subsequent candidate run also saw three chart-surface readiness
failures (F9c-transform, F9c-template-transform, F9c3-keyboard); with the exact
integration fixture setting (`E2E_SEED_MARKET_DATA=true`), all three passed on
an isolated retry in 31.7s. Both first failures and retries are recorded rather
than treated as invisible retries. The branch is ready for exact-SHA candidate
integration; the degraded marker must remain until the resulting master SHA
receives a green push-triggered replay. No RPi deployment is authorized by
this branch.

The next exact candidate (`2bd1e4b0a6080bd553310f844399a836bdca1c18`) also
exposed four browser timing/readiness failures in one seeded run: F8e swing
analysis, F8s family-map drilldown, F8s breadth, and the workstation churn
guard. Their first-failure artifacts remain in that candidate worktree. Each
exact test was rerun against the same isolated candidate stack with the required
market-data fixture and passed (1, 1, 5, and 1 tests respectively). These are
retained as flaky evidence; they do not justify silently converting the full
gate to green.

The candidate reached branch-declared tests, which exposed a workflow-record
error: this workstream had listed `make validate-integration` as one of its own
tests, causing recursive re-entry into the authoritative gate. The candidate
was stopped before recursion. The plan now declares only the targeted RPi
contract test; the outer integration gate remains the sole full-gate invocation.

The following exact candidate (`1cf2f0226f6c2c90f37a2c5a8009fc6f32b6c9ab`,
source `0a11b152c23ef7aa4d4caf00dce094742510a30b`) reached the full functional
Playwright suite with 153 passed and 106 skipped, but the workstation
performance guard (`workstation_performance.spec.ts:101`, repeated
multi-window churn) failed again. Its first-failure report and browser
artifacts remain under `.ai/integration/fix-arm64-ci-qemu-d5e955c60508/frontend/test-results`.
The exact test was rerun on the same candidate/runtime and passed in 13.4s;
this is diagnostic evidence only and does not turn the red exhaustive gate
green. The candidate stack was stopped with its exact project command. A fresh
full candidate gate remains required before publication.

The next exact candidate (`6c786de0d818b1000ab12c50b9e7bb890c475740`, source
`268b660f62d3798331b8df5115a45a4eff37ba8d`) passed the full functional suite,
but the four-environment board visual suite failed one readiness assertion:
`visual-1080p-125`, `tc2000_visual.spec.ts:472`, where
`.workstation__layout-state` was still present before the Study Lab original
surface. The run produced 103 passed and 1 failed visual scenarios; the first
failure screenshot/video/error context is retained under
`.ai/integration/fix-arm64-ci-qemu-ee975ed49839/frontend/test-results`. The
same exact scenario passed in 19.2s after an isolated stack restart, recorded
as diagnostic only. The candidate stack was stopped exactly. A fresh full gate
is still required; no master publication or RPi deployment is authorized.

The next exact candidate (`f4f7f0853c90a922b67f7d112e90e7d5e43e479b0`, source
`065c761ee0c6cd158bc1481e5a6650a3cee3c5bc`) passed backend, frontend, stack
health, research-runner probes, and deterministic checks, but the functional
Playwright suite failed only the workstation churn guard at
`workstation_performance.spec.ts:101`: expected canvas count 3, received 5
after the bounded 15-second cleanup poll. First-failure screenshot/video/error
context is retained under
`.ai/integration/fix-arm64-ci-qemu-fd0b1f40bd21/frontend/test-results`. The
candidate stack was stopped exactly. This is recorded as a red exhaustive
candidate; no publication or RPi deployment is authorized. Docker cleanup was
run after teardown and reclaimed 5.609 GB, leaving 4.55 GB of images and no
build cache; unrelated running worktree stacks remained running.
