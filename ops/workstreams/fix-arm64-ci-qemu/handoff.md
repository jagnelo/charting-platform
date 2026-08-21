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

Targeted deployment contract tests pass locally. The branch must still pass the
full integration gate and an exact push-triggered master replay before the
degraded marker may be cleared. No RPi deployment is authorized by this branch.
