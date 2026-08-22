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
