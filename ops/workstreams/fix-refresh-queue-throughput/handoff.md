# fix/refresh-queue-throughput

Created from `staging` at `d3e9496ccea45b3644e4e77afdcd15a8908c046c`.

## Human authorization

- Recorded at: 2026-11-20T15:56:55.226185+00:00
- Request: Yes, start it (refresh-queue throughput gap: production backlog ~76k queued with ~2 concurrent sequential drains; proceed under 'please get it into a state that honors my requirements. Proceed, and yes, investigate')
- Closure: delegated to the Desktop orchestrator (2026-11-13 standing delegation, see plan.yaml). Production
  deployment still needs the human's explicit approval for that deploy.

## Production finding

Read-only inspection of charting-first-human-4687bd0c on 2026-11-20, after the liveness fix (release 873eb207)
restarted the drains.

**The queue can't keep up with the discovered universe.**
- 34,421 active instruments.
- Open jobs: 41.9k queued history, 34.3k queued identity, about 24.5k deferred and 1.2k retry.
- Completions peaked at 3,165 per hour (13:00Z) and ran at about 1,000–1,200 per hour otherwise.
- Per-job time is short: identity has a 0.7s median and 8.1s p90; history has a 2.9s median and 4.4s p90.

**1. Drains are serial and capped at two.**
- `process_refresh_jobs` claims and runs one job at a time.
- At most `MARKET_DATA_REFRESH_MAX_DRAIN_CHAINS=2` chains run, on a worker with `max_jobs = 4`.
- The worker used about 40% of one CPU, so there is headroom for more concurrency.

**2. Every claim walks the whole table.**
- The claim SELECT (one job per claim) took 105 ms on production.
- It did a parallel index scan of `ix_market_refresh_job_priority` over all 232k rows: 33k buffers, mostly disk reads.
- Only about 100k rows are open; the rest are `completed` or `tracking` parents.
- Postgres sampled at 118% CPU during drains.

**3. Every maintenance pass forks new children.**
- Identity child keys include the hour, and history child keys include the published session end (or the hour).
- Each new maintenance parent therefore created fresh children while earlier ones still waited.
- Open jobs: 45,948 identity for 32,472 instruments, and 55,951 history for 34,421 instruments.
- Instrument 838 alone had about 100 waiting identity lookups, one per hour since 2026-11-14. Each one is
  another provider attempt once its deferral ends.

## Fix

**AC1: claim index.**
- Alembic `a7c3e5f9b2d4` and the model add the partial index `ix_market_refresh_job_claimable` on
  (priority, next_attempt_at, id) WHERE status IN ('queued','retry','deferred','leased').
- The claim query also has a redundant top-level `status IN (...)` conjunct, because PostgreSQL proves a
  partial-index predicate only from a top-level conjunct, not from the OR arms.
- `claimable_jobs_query()` is the single source of the claim SELECT.

**AC2: concurrency.**
- `MARKET_DATA_REFRESH_MAX_DRAIN_CHAINS` defaults to 6 and `ARQ_WORKER_MAX_JOBS` to 10 (clamped 4..32).
- The effective cap is `max(1, min(chains, slots - 4))`, so four slots always stay free for scheduled jobs.
- The quarter-hour tick calls `top_up_refresh_drains()` before planning. When due work exists, it enqueues
  drains up to the cap.
- The existing hand-over cap stops continuations from overshooting the cap.

**AC3: identity coalescing.**
- With no same-hour child (or only a terminal negative one), `_enqueue_identity_profile_job` joins the oldest
  queued, deferred or retry child for the same tuple: symbol, instrument_id, refresh_profile and required
  fields.
- A completed positive child in the same hour is still reused.
- Terminal negatives keep the hourly `:recovery` key.
- Leased children are never joined.

**AC4: history coalescing.**
- With no exact-key child, `_enqueue_history_dependency` joins the oldest waiting deepest-range acquisition
  child for the same instrument, timeframe and adjustment.
- Explicit-start ranges, derived-only children and older-chunk continuations are excluded.
- The joined child's end widens to the later end, with open-ended counting as latest. The wait ids are
  unioned, the analysis floor takes the earlier value, and coarse derivation is ORed.
- A repeat of an already-widened child's original key never narrows it.
- Both lookups use `FOR UPDATE SKIP LOCKED`, so a row a drain is claiming is skipped, and the joined row stays
  locked until the enqueue commits.

**Not changed: the existing duplicate backlog.** Its jobs drain normally. Re-processing a duplicate history
child fetches only the newest bars, and a duplicate identity child that resolved finishes as `ready` in about
0.5s.

## Evidence

**Unit:**
- `test_data_preparation_child_coalescing.py` has 14 tests. On the old `data_preparation.py`, 6 fail (every
  joining case) and the 8 guard cases pass.
- The data_tasks, arq_worker, queue and migration suites gained the chain-cap, top-up, worker-slot and
  migration cases.

**PostgreSQL integration:**
- `test_refresh_job_claim_index_postgres.py`: the claim plan uses `Index Scan using
  ix_market_refresh_job_claimable` with no Sort over a deep open backlog. Without the redundant conjunct it
  stayed on the priority index. The revision upgrades and downgrades on PostgreSQL.
- `test_data_preparation_child_coalescing_postgres.py`: the symbol-only identity join filters the JSON
  payload (`#>>`), and a history join skips a child locked by a concurrent claim.

## Feature CI attempt 1 (69c8d0bb4)

**Backend Tests failed on `test_strategy_chain_has_unique_ids_and_preserves_shared_base`.** That suite lives in
`app/strategy_lab_v2/tests` and pins the exact Alembic head.
- As commit 3457ce130 did for e6f7a8b9c012, the pin moves to the new head a7c3e5f9b2d4.
- The test now also asserts that a7c3e5f9b2d4's parent is e6f7a8b9c012 and that e6f7a8b9c012 stays in the
  ancestry.
- Every previous assertion is kept.

**A local run of the integration suites found
`test_system_maintenance_reenters_shared_preparation_for_later_observation`.** It pinned the old forking
behaviour: a later published session got a separate child while the first child was still queued and had
never run. Joining a waiting child is the deliberate change in AC4, so the test now covers two scenarios.
- **First child still waiting:** the later parent joins it. The test asserts the shared child's `end_at` and
  `range_end` equal the later published end, the child is still queued, both tracking parents are in its
  `parent_refs`, and the next-day pre-close observation reuses the later parent and child.
- **First child already completed:** the later observation still binds fresh child work. This is the original
  assertion: a different child with a different request key. The completed child keeps its own end.
