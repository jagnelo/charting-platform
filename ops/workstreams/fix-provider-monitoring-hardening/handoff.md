# fix/provider-monitoring-hardening

Created from `master` at `aecea059fa39ee43fdae36ad935c401a6b5a607e`. Update this handoff at each coherent boundary.

Implemented durable notification transition state and a cooldown-aware policy:
daily core probes notify only from the second consecutive failure, weekly sweeps
notify schema/content regressions, and recovery is emitted only after a notified
failure. Settings now receives last-success and last-failure timestamps. Focused
tests and the migration gate remain to be run.

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
