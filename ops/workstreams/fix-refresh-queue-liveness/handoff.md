# fix/refresh-queue-liveness

Created from `staging` at `632554bca0fe7a25fd7e74c9f24722ffc804e59d`.

## Human authorization

- Recorded at: 2026-11-20T04:22:32.595972+00:00
- Request: please get it into a state that honors my requirements. Proceed, and yes, investigate
- Closure: delegated to the Desktop orchestrator (2026-11-13 standing delegation, see plan.yaml). Production
  deployment still needs the human's explicit approval for that deploy.

## Production finding (2026-11-20, read-only inspection of charting-first-human-4687bd0c)

Release c3a02ddd (deployed 2026-11-19 ~12:36Z) turned on whole-market discovery. The active universe grew to
34,111 instruments and the self-sustaining refresh queue stopped:

- `cron:scheduled_refresh_queue_process` failed every quarter hour since 13:06Z (62 failures):
  `asyncpg InterfaceError: the number of query arguments cannot exceed 32767` from
  `enqueue_workstation_maintenance`, which bound one parameter per active instrument when reading primary
  listings. The tick raised before `process_refresh_jobs`, so the cron never drained.
- The same query failed `scheduled_core_workstation_bootstrap` (01:00Z) and would fail the 05:00Z daily
  history cron.
- Drain chains (`task_process_refresh_jobs`) claim up to 100 jobs; instrument-metadata jobs take 1-60s, so
  batches ran into the 600s arq job timeout (13 TimeoutErrors). A cancelled drain never schedules its
  continuation, so each chain died; only the broken cron could revive them. The last chain died 23:49Z.
- Queue at inspection: 13,644 queued, 21,660 deferred, 480 retry, 3 stale leases; completions fell from
  ~150-280/h to ~0 after 15:00Z.
- Separate, not fixed here: `scheduled_daily_metadata_sync` (cap 750) timed out at 600s at 03:10Z.

## Fix

1. Planner reads primary listings by joining `instrument` with the same active/non-synthetic predicate (no
   per-id bind parameters).
2. The quarter-hour tick logs a planner failure and still drains; planning and draining share one deadline.
3. `process_refresh_jobs` stops claiming once its wall-clock budget is spent
   (`MARKET_DATA_REFRESH_DRAIN_BUDGET_SECONDS`, default 360, clamped to 1..540) and schedules a continuation.
4. The discovered-universe planning pass stops at the deadline (default/saved specs are always planned first);
   the 05:00Z daily cron uses the same bound.
5. Continuations are capped by `MARKET_DATA_REFRESH_MAX_DRAIN_CHAINS` (default 2): a drain does not hand over
   while that many other `data-preparation-*` drains are running or due within a minute in the arq queue.
   Without the cap, drains that no longer die on timeouts would accumulate one chain per tick and crowd the
   worker's four job slots.

## Evidence

- `test_maintenance_planner_survives_universe_beyond_bind_parameter_limit` (real PostgreSQL, 32,800
  instruments) fails on the old query with the production InterfaceError and passes on the fix.
- Unit: tasks, workers and data-preparation suites 232/232; Ruff check and format clean.
