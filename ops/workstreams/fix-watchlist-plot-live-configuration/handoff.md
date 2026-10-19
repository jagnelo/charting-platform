# fix/watchlist-plot-live-configuration

Created from `staging` at `2734c6a57f79c7c6a3c5a2c6a8cad99d29e43745`.

## Human authorization

- Recorded at: 2026-10-17T10:19:11.475831+00:00
- Request: Coordinate the existing Provider → ETF holdings → TC2000 → Strategy Lab v2 feature checkpoints through reconciliation, delegated technical acceptance, sequential guarded merges into persistent staging, and exact-source full validation. Deliver a combined development baseline usable for human testing within the human-approved verified-free-only scope, with quota-held, unreviewed, paid-trial, and unsafe operations disabled and full feature roadmaps retained. No master promotion, deployment, paid activation, or operational trial is authorized.
- Closure authorization: the human delegated careful technical-fix review and closure on 2026-10-15; this covers only the narrow F8u repair described by this plan. It does not accept any feature checkpoint or authorize deployment, promotion, paid activation, quota spend, or an operational trial.
- Planning state: ready. The implementation checkpoint must pass its exact-source validation and stop at `ready_for_human_review`; persistent staging integration remains coordinator-owned.

## Isolated F8u runtime disposition

The app and worker remain on an internal-only network with provider routing
disabled and provider credentials blank. The frontend requests the public
OneSignal SDK even when app credentials are blank; to keep the unchanged browser
diagnostics green without opening general egress, the test runner may use a
temporary CONNECT-only proxy allowing exactly `cdn.onesignal.com:443`. No
OneSignal API host, provider host, issuer host, paid operation, or live market
data route is allowed.

Update this handoff at each coherent boundary.

## 2026-10-17 validation checkpoint

The canonical-live-configuration repair is implemented in the only owned
product path, `frontend/src/components/workstation/WorkstationToolContent.vue`.
Configured indicator rendering and the chart-plot drop update both read the
canonical workspace window configuration, with the existing tool prop as a
fallback. The ordinary pointer path, assertions, timeouts, retries, visual
references, and tolerances are unchanged.

Local validation on the exact working-tree source passed:

- Focused watchlist/plot component tests: 89 passed across the two affected
  suites; `vue-tsc --noEmit` and the production frontend build passed.
- The unchanged F8u real pointer-drag flow passed five independent times with
  one worker and zero retries, against fresh users in a seeded internal-only
  test database. Provider routing/refresh and credentials stayed disabled;
  app/worker provider egress remained denied. The browser received only the
  public static OneSignal SDK via the temporary exact-host
  `cdn.onesignal.com:443` allowlist. No OneSignal API or market-data provider
  calls were permitted.
- The final pinned Playwright 1.62.1 Noble functional/performance profile
  completed with 154 passed, 2 expected live-data skips, zero failures, and
  zero retries. The unchanged visual-only profile passed 104/104 with the
  existing 0.5% tolerance and a read-only DejaVu font mount.
- An earlier full-profile attempt without the matching DejaVu font fallback
  produced font-sensitive visual mismatches (1.1275% and 1.33% against the
  unchanged 0.5% threshold). It is retained as a harness-mismatch/red result,
  not relabelled as green. The later visual-only profile passed without any
  oracle, screenshot, CSS, or tolerance edits.

Artifacts are retained under `/tmp/f8u-repair-evidence-20261017.hPjYj4/` in
`f8u-run-2` through `f8u-run-6` for the five passing fresh-user runs;
`f8u-run-1` preserves an initial fixture-email setup rejection that never
reached the application. The directory also contains
`functional-profile-final`, `visual-profile-dejavu`, and `full-profile`.

After the final browser run, only the exact disposable Compose project
`charting-stack-fix-watchlist-plot-live-configuration-06f23bb3` was removed.
Its nine project-labelled containers, four generated volumes, and two
networks were verified absent. The separately assigned Provider and TC2000
stacks and their unrelated Playwright containers were left running and
verified present.

AC1 and AC2 are complete. Local AC3 checks are complete; exact-source ordinary
branch CI is still pending. Do not mark this branch `ready_for_human_review`
or integrate it until the clean published tip has its exact CI receipt. This
narrow repair remains distinct from the four feature checkpoint decisions and
does not authorize deployment, paid activation, quota spend, or a trial.

## Exact CI diagnosis — 2026-10-17

The first exact-source push run `39029708580` for `62323e42b8dcf8a95ed9645a15623acb235ca3c8`
failed the `Branch-declared Tests` job before running product tests. Its step
executed the first `branch_tests` item as a shell command and exited 126 because
the plan had listed a test-file path rather than an executable command. The
hosted runner log states `/bin/sh: 1: frontend/tests/unit/components/test_virtual_watchlist_tool.test.ts: Permission denied`.
The backend and frontend jobs were still running when this failure was
inspected. No product assertion failed in this run.

The plan now declares each affected Vitest suite as an executable
`cd frontend && npx vitest run ...` command. The F8u browser test remains in the
separate local full-stack profile; no assertions or environment gates were
changed. The failed CI receipt remains red, and a fresh exact-source Actions run
on the corrected plan is required before review or staging integration.

Both corrected branch-declared commands passed locally (89 tests total), and
the repository validator accepted all 36 workstream records. The corrected
plan is published; session goal-request/progress metadata is being synchronized
before the final exact-source CI run.

## Coordinator closure checkpoint — 2026-10-17

The human delegated coordinator-owned checkpoint acceptance for getting this
work into staging. This narrowly scoped F8u repair is closed for guarded
staging integration; it does not close or alter the Provider, ETF, TC2000, or
Strategy Lab v2 feature checkpoints.

Validated implementation SHA `103ef8e1899412a5a623e8e587ec718de0458c8c` has
the local full-stack evidence above and exact branch Actions run `39030047625`
completed successfully: Branch-declared Tests, Backend Tests, Frontend Unit
Tests, and E2E Tests passed; the Exhaustive Integration Gate was skipped under
feature-branch policy. The final closure-record commit must still pass its own
exact-source branch CI before integration. The guarded staging workflow will
record the exact merge source SHA and require a green staging gate before this
repair is treated as released there.

No merge conflict has been observed in the narrow product change. If guarded
integration finds one, abort and resolve on this source branch before retrying.
There is no migration or deployment impact. Provider's remaining full
validation, operation dispositions, quota preflight, and all four feature
roadmaps remain open.

## 2026-10-19 — strict F8u follow-up

Provider exact-source Actions run `39254427018` on `bef14e0c14b4c60be4f4d54dc954f8113ef5f2f9`
is red under the strict flaky-test policy: Backend, Frontend Unit, and
Branch-declared passed; Playwright had 150 passed, 109 expected skips, and one
F8u first-attempt failure. Its normal retry passed, but this remains a red
receipt. The failing screenshot/trace is retained in Actions artifact
`12188857004`.

The failure screenshot shows the plot-library row contains a line-width input
and several controls. The test called `dragTo` on the whole row, whose default
pointer origin is its center; by the row's grid layout that can hit the
line-width input rather than the plot label and fail to start a native drag.
This is a test-origin diagnosis, not a claim that the product drop assertion
was satisfied. The follow-up starts the same ordinary drag from the visible
RSI label; it does not change the drag target, header assertion, timeout,
retries, visual references, or tolerance. The repair checkpoint is reopened
until the focused zero-retry profile and exact-source CI pass.

The corrected source passed the focused pinned Playwright 1.62.1 Noble F8u
flow five times with one worker and zero retries on 2026-10-19. Each repeat
used a distinct fixture user/workspace. Provider/OneSignal credentials were
blank; provider routing was disabled; app/worker provider egress was denied;
the browser had no direct internet route and could use only the exact-host
`cdn.onesignal.com:443` proxy. The deny proxy recorded five blocked
`api.openfigi.com` CONNECT attempts; none reached an external provider, and
there were no provider requests, quota reservations, or spend. The exact
disposable project and generated data were removed; the retained Provider and
TC2000 stacks remained intact. Receipt:
`/tmp/f8u-repair-evidence-20261019.7I4Vv9/f8u-five-run-receipt.md`.

Exact-source Actions run `39260462285` on
`8b9dc144195fc5195ca6bc5d0d62842d020af784` passed Branch-declared Tests,
Backend Tests, Frontend Unit Tests, and Playwright (151 passed, 109 expected
skips, no failures). The Exhaustive Integration Gate was skipped as required
for feature-branch CI. The earlier strict-red run remains preserved. The
closure record now marks this narrow repair ready for guarded integration, but
the final closure-record commit must itself pass exact-source CI before the
coordinator invokes `make integrate`.

## 2026-10-19 — guarded integration preflight

Exact-source Actions run `39264635908` completed green on
`0fa2abafa91d50750c4c848eedbc6e8decc7788c`: Backend, Frontend Unit,
Branch-declared, and Playwright all succeeded; Exhaustive Integration Gate was
skipped under feature-branch policy. The normal `make integrate` guard refused
to start before mutating staging because this closure summary omitted the
required `integration_capture: exact branch HEAD` declaration. The workstream
is being corrected on this source branch. Staging remains unchanged at
`94c252d6b8767714df2c6c8840a2119f5aa161dd`. The corrected closure-record tip
must pass exact-source CI before retrying guarded integration.

## 2026-10-19 — strict F8u refresh-race diagnosis

Exact-source Actions run `39269065093` on
`326a7cb727d7463a7b8b8a28afd4ba938b5e9293` is red under the strict flaky-test
policy. The other branch jobs passed; Playwright reported 150 passed, 109
expected skips, and an F8u first-attempt failure followed by a passing retry.
The receipt is red and does not qualify for staging.

The trace shows the Major US benchmarks watchlist had `aria-busy="true"` when
the pointer drag landed. The test previously began dragging as soon as the
region was visible and made a second drag attempt when the first did not create
the RSI header. The focused correction waits for the existing public
`aria-busy="false"` readiness state and makes one ordinary drag only. It keeps
the real label-to-watchlist pointer path, target, header assertion, timeout
values, screenshots, and visual tolerance unchanged. This follow-up is in
progress; do not integrate until focused validation and exact-source CI pass.

A duplicate local full-stack fixture has not been started: retained Provider
and TC2000 stacks remain owned elsewhere and their containers are active; host
available memory is about 2.2 GiB. No services were stopped or cleaned. The
stack-free watchlist suite passed 68 tests, the chart-plot suite passed 21 tests,
and the workstream validator accepted all 36 records. Next: publish this
one-drag readiness guard, inspect fresh exact-source Actions including
Playwright, then continue guarded integration if green. The focused local
five-repeat browser profile remains outstanding; do not treat the prior five
repeats on the earlier test code as proof for this one-attempt change.

## 2026-10-19 — second exact-source F8u failure and refined drag target

Exact-source Actions run `39274378927` on
`476bb54e419164c0b56cf96b55f7147fa16a1c74` is red under the strict flaky-test
policy. Backend Tests, Frontend Unit Tests, and Branch-declared Tests passed;
Playwright had 150 passed, 109 expected skips, and F8u failed its only attempt.
The run artifact is `12199905708`.

The trace confirms the target was ready (`aria-busy="false"`) and that
Playwright moved from the visible RSI label to the benchmark watchlist body.
The RSI header never appeared, and the trace's network record contains no
drop-driven workspace-snapshot update. This rules out the earlier busy-state
race but does not yet prove whether the missing step is dragover, drop, or
payload delivery. The test now uses one stepped pointer path to the watchlist's
column-header surface rather than its row body, avoiding the row-reorder drop
listeners while keeping the ordinary native drag and expected-header check.
No product code, assertion, timeout, retry policy, visual oracle, data, or
provider configuration changed.

The pinned local five-repeat profile remains unrun on this one-attempt source:
the retained Provider and TC2000 projects are still active and host available
memory is approximately 2.1 GiB. Do not start a duplicate Compose project or
stop/clean retained services. Stack-free tests may run, then publish this
test-only refinement and require fresh exact-source Actions before any staging
integration attempt. Staging remains unchanged.

## 2026-10-19 — live configuration visibility repair and local F8u pass

The latest browser trace proved the real stepped drag to the watchlist header
fires `dragstart`, `dragover`, and `drop`, with a valid RSI plot payload. The
remaining product defect was a split configuration snapshot: `addPlotColumn`
and `configuredIndicatorColumns` read the canonical live workspace window, but
`configuredColumnKeys` still read the detached `props.tool.configuration`.
Because the explicit `column_keys` list is authoritative, the RSI definition
was persisted but remained hidden. The narrow product fix makes
`configuredColumnKeys` read `liveToolConfiguration.value.column_keys`, so the
visibility list, definition renderer, and drop handler share one snapshot.
The existing pointer path and assertions were not changed in this repair.

Validation on 2026-10-19:

- `npx vitest run tests/unit/components/test_virtual_watchlist_tool.test.ts
  tests/unit/components/test_chart_plot_library.test.ts`: 89/89 passed.
- Isolated production frontend build: `vue-tsc` and Vite passed.
- Pinned `mcr.microsoft.com/playwright:v1.62.1-noble`, one worker, zero retries:
  focused F8u passed once, then five fresh repetitions passed (5/5, 54.2s).
- The exact fixture used a seeded internal-only network, blank provider and
  OneSignal credentials, provider routing disabled, and the app/worker deny
  proxy. The browser had no direct internet route; the only allowed outbound
  browser connections were six `CONNECT cdn.onesignal.com:443` requests
  (focused pass plus five repeats). The provider-deny log recorded seven
  blocked `CONNECT api.openfigi.com` attempts; none reached an external
  provider. There were no quota reservations or spend, and no visual oracle or
  assertion changes.
- The first focused attempt reached the F8u assertion but failed the final
  diagnostics check because the temporary runner used a Docker DNS alias that
  was unavailable on its internal-only network. Pointing the temporary runner
  at the same proxy's internal-network address fixed the route; no direct
  browser egress was enabled. An initial Compose recovery omitted the fixture's
  original environment variables; Compose was cancelled before confirming any
  volume recreation, then restored with the original environment. The existing
  fixture volumes were preserved through recovery and removed only during
  final cleanup.
- The unique test fixture's containers, networks, and four generated volumes
  were removed. Read-only post-cleanup inspection confirmed all pre-existing
  Provider and TC2000 stacks remained up. No sibling worktree or staging
  mutation occurred.

## 2026-10-19 — full local gates and exact-source CI green

On exact implementation SHA `dfa7f558e3b1a7c998b86b57f2609091ffd5f7c0`, the
corrected isolated Playwright fixture completed its full local profiles with
one worker and zero retries:

- Functional/performance profile: 154 passed, 2 expected live-data skips, zero
  failures, zero retries.
- Visual-only matrix: 104/104 passed. Screenshot references and the 0.5%
  threshold are unchanged; the runner used only the existing read-only DejaVu
  font mount. The human-approved local Help reference remains an interim
  reference disposition; official V25 parity remains roadmap work.
- The exact-source GitHub Actions run `39282882919` completed green on the same
  SHA. Backend Tests, Frontend Unit Tests, Branch-declared Tests, and E2E
  Playwright all succeeded. Exhaustive Integration Gate was skipped as expected
  for branch CI; it remains mandatory on the pushed staging merge.

The fixture used blank provider/OneSignal credentials, provider routing off,
an egress-denied app/worker, an internal-only test network, and only an
exact-host `cdn.onesignal.com:443` browser allowlist proxy. No live provider
route, quota reservation/spend, screenshot-oracle change, or feature-worktree
change was in scope. Cleanup targeted only project
`charting-stack-f8u-safe-research-runner-20261019-1740`: its 9 containers,
4 generated volumes, and 2 networks are absent. Read-only checks confirmed the
retained Provider and TC2000 stacks remain up. Staging remains unchanged at
this checkpoint.

The narrow repair is now `ready_for_integration`; preserve all earlier strict
red CI receipts. The final closure-record commit must itself pass exact-source
CI before `make integrate` is invoked. Provider, ETF, TC2000, and Strategy Lab
v2 acceptance gates and full roadmaps remain open.
