# fix/arm64-ci-emulation

This branch repairs the independent GitHub platform gate. The exact master
replay at `5124146980b37f6d6b5080d737f801933700b0c5` passed backend, frontend,
and Playwright validation but failed at the final ARM64 image stage with
`exec format error`: GitHub's amd64 runner had no binfmt/QEMU registration for
executing `linux/arm64` Dockerfile `RUN` instructions.

The workflow change registers Docker's QEMU action immediately before the
authoritative gate. This is CI-only infrastructure; native ARM64 Mac builds
and RPi deployment tooling are not changed.

## 2026-08-29 — Workflow branch closure

The human authorized closure of this workflow-only branch. Its source changes are reachable from master. The branch is no longer an active development line; its remote ref and workstream record remain as audit history. Any future work starts from green `staging`, and product/deployment gaps are not claimed complete merely because the implementation is reachable from `master`.
