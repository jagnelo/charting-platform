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
