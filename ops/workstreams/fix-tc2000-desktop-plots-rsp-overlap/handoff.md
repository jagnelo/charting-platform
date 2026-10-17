# fix/tc2000-desktop-plots-rsp-overlap

## Current checkpoint

Coordinator-owned technical repair, created from synchronized green `staging`
at `2734c6a57f79c7c6a3c5a2c6a8cad99d29e43745` (Exhaustive Integration Gate
run `39013106548`, success). This does not modify or accept the TC feature
branch. No product source has been changed yet.

## Human authorization

The human explicitly directed the coordinator to deliver the remaining F9c
geometry fix through synchronized green staging: “TCP1 remains incomplete until
the coordinator-owned geometry repair is delivered through synchronized green
staging.” The earlier standing authorization for narrow technical repairs also
allows the coordinator to close this exact fix without per-fix human signoff.
No master promotion, deployment, paid activation, quota spend, operational
trial, or unsafe operation is authorized.

## Reproduced failure to close

At source `389069a32682f97c51c0a6dd5cca99be3bb23c2a`, desktop `1920x1080`
default US Top Down with populated RSP `+23.50%`, Plots bounds were
`x=1061 y=107.5 w=42.58 h=18`; Remove RSP bounds were
`x=1013 y=107.5 w=91.55 h=15`. Their hit rectangles overlap, the Plots center
resolves to Remove RSP, and an ordinary non-forced Playwright click is
intercepted. The independent `390x800` TC Classic layout had separate hits and
passed normal Plots, menu close and Remove RSP actions.

The target branch currently demonstrates the already-green staging source;
the coordinator must reproduce the failure here before changing product code.
The currently running `fix/watchlist-plot-live-configuration` CI is a separate
F8u issue and must not be claimed as closing this F9c geometry defect.

## Ownership and validation

- Branch/worktree: `fix/tc2000-desktop-plots-rsp-overlap`.
- Workstream plan: `ops/workstreams/fix-tc2000-desktop-plots-rsp-overlap/plan.yaml`.
- Only owned paths are the shared chart component, focused F9c browser coverage,
  and this branch's workstream.
- Use fresh internal-only fixtures with seeded local market data; keep provider
  routing/refresh disabled and credentials blank. Do not touch assigned feature
  services, volumes, accounts or data.
- Preserve all browser assertions, retry/timeouts and screenshot references,
  masks and tolerances. The 104-case visual matrix, exact-source ordinary CI and
  exact pushed staging Exhaustive Integration Gate remain required.
- After a green staging release, notify the TC and Provider owners with the
  exact synchronized staging SHA and downstream reconciliation instructions;
  retain their full roadmaps.

Next: inspect current chart layout and its existing F9c test, reproduce on this
branch with ordinary pointer actions, then implement and verify the narrow
responsive geometry correction.
