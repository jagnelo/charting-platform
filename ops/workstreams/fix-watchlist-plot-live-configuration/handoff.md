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
