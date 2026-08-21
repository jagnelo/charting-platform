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
