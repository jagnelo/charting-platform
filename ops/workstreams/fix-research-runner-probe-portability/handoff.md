# fix/research-runner-probe-portability

Created from the degraded but synchronized master baseline at
`4fc20898d33d0ecaef503728484779d852cf7933`. The master replay reached the
research-runner resource stage but survived the nominal 2 GiB allocation on
GitHub Linux amd64 because the probe only read untouched zero pages. This
branch writes every page, preserving the bounded allocation and all existing
resource invariants.

The exact master replay remains degraded until this repair is independently
green and integrated through the full candidate gate.

## 2026-08-29 — Workflow branch closure

The human authorized closure of this workflow-only branch. Its source changes are reachable from master. The branch is no longer an active development line; its remote ref and workstream record remain as audit history. Any future work starts from green `staging`, and product/deployment gaps are not claimed complete merely because the implementation is reachable from `master`.
