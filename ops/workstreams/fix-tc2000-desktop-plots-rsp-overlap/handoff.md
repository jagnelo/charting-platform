# fix/tc2000-desktop-plots-rsp-overlap

## Current checkpoint

Coordinator-owned technical repair. The F8u watchlist/live-plot repair is
merged into persistent staging at `6dc178c12498236a2a0060533305e20cf47438b7`;
exact staging Actions run `39033839693` passed, including Playwright and the
Exhaustive Integration Gate. The repair branch contains that exact green
staging tip and the F9c geometry/test change. Exact-source branch CI run
[`39039551432`](https://github.com/jagnelo/charting-platform/actions/runs/39039551432)
checked out `d5aac522b144d57d93df817be2a1699e0ac6e568` and passed all applicable
jobs. Its Playwright log ran `F9c-default-topdown-hit-targets` after the real
Golden Layout splitter setup; the suite ended with 152 passed, 109 skipped,
zero failed. The Exhaustive Integration Gate was skipped as expected for
branch-only CI. The human's log review places F9c as case 15, followed by case
16. This confirms the actual splitter drag and narrow chart setup reached the
ordinary hit-target assertions and interactions. PTRD1–PTRD3 are exercised by
this hosted regression; PTRD4 remains open for the required local functional/
visual profile and later staging gate. The feature branch remains untouched.

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

The local candidate uses chart-container width rather than viewport width to
move comparison controls clear of Plots, and makes only the comparison wrapper
pointer-transparent while keeping its input/buttons interactive. A focused
ordinary-click browser regression was added for the desktop saved-template
flow and the existing TC Classic mobile path. Neither the geometry nor these
new flows have been run against the combined `41d5b6b` source yet; do not claim
F9c closure from the F8u staging pass.

The first exact-source CI attempt (`39037522747`, source `dfb34977`) passed
backend, branch-declared and frontend-unit jobs, but Playwright failed before
the F9c interactions because the factory layout had no chart surface under
520px. The test now keeps the viewport at 1920x1080 and drags the actual
rightmost Golden Layout splitter to create the narrow dock. The exact-source
run above confirms the browser test reached and passed the geometry and ordinary
pointer assertions. This hosted run does not complete the required local
functional/visual profile or the later staging gate.

## Ownership and validation

- Branch/worktree: `fix/tc2000-desktop-plots-rsp-overlap`.
- Workstream plan: `ops/workstreams/fix-tc2000-desktop-plots-rsp-overlap/plan.yaml`.
- Only owned paths are the shared chart component, focused F9c browser coverage,
  and this branch's workstream.
- Use fresh internal-only fixtures with seeded local market data; keep provider
  routing/refresh disabled and credentials blank. Do not touch assigned feature
  services, volumes, accounts or data.
- The latest human-reported read-only host check showed about 1.7 GiB available.
  My direct read-only `free -h` check at 2026-10-17 23:25 UTC showed 1.1 GiB
  available. The latest Docker inventory attempt was denied by the socket
  permission boundary; the previous read-only inventory showed multiple
  retained Provider validation projects and the assigned TC project running,
  without identifying active fixture ownership. Capacity and ownership are
  therefore not safe to assume. Do not start a duplicate Compose fixture or
  competing browser matrix, and do not stop or clean any service.
- Preserve all browser assertions, retry/timeouts and screenshot references,
  masks and tolerances. The 104-case visual matrix, exact-source ordinary CI and
  exact pushed staging Exhaustive Integration Gate remain required.
- After a green staging release, notify the TC and Provider owners with the
  exact synchronized staging SHA and downstream reconciliation instructions;
  retain their full roadmaps.

Next: when fixture ownership and host capacity are safe, run the required
isolated full local functional/visual profile with one worker and zero retries.
Keep the existing assertions, screenshot references, masks and tolerances
unchanged. Only after all required local checks pass should the repair closure
be recorded and the guarded staging workflow run again.

The 2026-10-17 operational receipt updates this branch-owned record set:
`ops/workstreams/fix-tc2000-desktop-plots-rsp-overlap/plan.yaml`,
`ops/workstreams/fix-tc2000-desktop-plots-rsp-overlap/handoff.md`,
`ops/workstreams/fix-tc2000-desktop-plots-rsp-overlap/session.json`, and
`ops/workstreams/fix-tc2000-desktop-plots-rsp-overlap/validation.jsonl`.
