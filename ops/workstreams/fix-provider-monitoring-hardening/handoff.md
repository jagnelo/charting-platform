# fix/provider-monitoring-hardening

Created from the validated `master` baseline at `740d9f0cf50ef5f02a2e39baffe6f97bd95ad696`; rebased after the ARM64 CI emulation repair. Update this handoff at each coherent boundary.

Implemented durable notification transition state and a cooldown-aware policy:
daily core probes notify only from the second consecutive failure, weekly sweeps
notify schema/content regressions, and recovery is emitted only after a notified
failure. Settings now receives latest per-capability status, last-success and
last-failure timestamps, and recent sweep metadata. Live probes are bounded by
the configured per-request timeout. Focused tests and the migration gate remain
to be run.

The branch also carries the corrected independent CI replay contract: generated
uv headers are normalized, pytest runs through `uv run`, and integration-only
coverage does not apply the combined threshold.

Worker coverage now verifies both scheduled availability jobs are disabled unless
monitoring and live-probe flags are explicitly enabled, and that enabled jobs
delegate `daily_core` and `weekly_supported_sweep` respectively. Provider and
worker focused tests pass 25/25.

The first complete provider replay passed backend and frontend unit/integration
jobs but failed 16 Playwright cases because the branch CI stack did not enable
the deterministic instrument and market-data fixtures. The failures clustered
in transform, chart, workstation, and Study Lab flows rather than provider
monitoring. The E2E job now enables both fixture flags; a fresh replay is
required.

The focused provider/worker command still exits non-zero when invoked alone
because the repository's combined coverage gate is 55% and the two focused
modules exercise only 16.07% of the backend. All 25 focused tests passed; this
is expected evidence for the branch slice, not a green substitute for the full
backend coverage gate. The full gate must be used for acceptance.

This branch is now based on the exact promoted master SHA above. Its source
replay and exact-candidate integration remain required before publication is
considered accepted.

Two exact candidates stopped at previous-release migration smoke because the
old application did not answer `/health` within the one-shot readiness window;
isolated reruns against both candidates passed with `/health 200`. The red
evidence is retained in `validation.jsonl`. The migration smoke helper now uses
a 90-second bounded startup budget and reports early process exits, and a fresh
source replay plus complete exact gate are required before publication.

That fresh source replay passed backend/frontend checks but had one Playwright
failure in the existing F8h simultaneous-pop-outs flow after retry (150 passed,
109 skipped). The failure is retained as first-failure evidence; a diagnostic
rerun is required before deciding whether the existing UI test needs a targeted
stability fix.

## 2026-08-27 — Focused evidence refresh

The declared provider slice was rerun from the frozen branch environment:
`backend/.venv/bin/pytest tests/unit/services/test_provider_availability.py -q --no-cov`
passed `5/5`; Ruff check and format check passed for the provider model/service and tests.

The targeted frontend Settings test could not start because this isolated worktree has no
`frontend/node_modules`. `npx vitest` attempted to fetch Vitest from the npm registry and failed
with `ENOTFOUND`; no test result was produced and the test oracle was not changed. The full gate
still requires a reproducible frozen frontend install before this branch can be accepted.
