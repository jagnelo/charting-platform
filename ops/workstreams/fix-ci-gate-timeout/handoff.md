# fix/ci-gate-timeout

Created from `master` at `0ecc62f15ad6e78359cab7a7e4336a661043ae84`.

## Goal

Bound every CI job, with the master-only exhaustive CI replay at three hours.
The timeouts are failure boundaries, not test skips: every existing
`make validate-integration` stage remains required, and the diagnostics step
still runs when the gate fails or times out.

## Evidence

- Exact master replay `32446304260` for `0ecc62f15ad6e78359cab7a7e4336a661043ae84`
  exceeded four hours with the gate step still in progress. The prior green
  replay completed in about 58 minutes. GitHub did not expose live logs and
  cancellation was rejected for lack of repository-admin permission.
- This branch adds `timeout-minutes: 30` to backend tests, `15` to frontend
  unit tests, `45` to Playwright E2E, and `180` to the master gate. These are
  above the observed green durations while preventing unbounded CI lanes.

## Remaining

Run the workflow contract checks and the exact-candidate integration replay;
do not issue a validation receipt until the new master replay is green.

## 2026-08-29 — Workflow branch closure

The human authorized closure of this workflow-only branch. Its source changes are reachable from master. The branch is no longer an active development line; its remote ref and workstream record remain as audit history. Any future work starts from green `staging`, and product/deployment gaps are not claimed complete merely because the implementation is reachable from `master`.
