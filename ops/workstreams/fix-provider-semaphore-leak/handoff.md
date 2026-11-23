# fix/provider-semaphore-leak

Created from `staging` at `6d70107def8e2797a46db54b8ea3ad02e635d8a1`.

## Human authorization

- Recorded at: 2026-11-23T12:13:04.194198+00:00
- Request: Fix the production refresh-queue stall ('Yes, fix it here'): since 2026-11-22 02:00Z every drain blocks forever on the in-process provider semaphore in execute_provider_call because early-exit paths await a settle call before semaphore.release(); a drain cancelled by the arq job timeout during that await leaks the permit, and Alpaca's default concurrency of 1 then blocks all its calls. Release the permit on every path, including cancellation.
- The human asked to fix the next throughput problem here ("Yes, fix it here"); investigating it found this stall.
- Closure: delegated to the Desktop orchestrator (2026-11-13 standing delegation, see plan.yaml). Production
  deployment still needs the human's explicit approval for that deploy.

## Production finding

**The refresh queue stalled for 34 hours.** From 2026-11-22 02:00Z:
- Completions fell from about 2,000 per hour to 50-75 per hour, with 69k jobs queued and 85k claimable.
- Alpaca daily-bar requests fell from about 1,500-1,900 per hour to about 30-40.
- Every drain (6 follow-up drains and the quarter-hour tick) ran its full 600 s and was cancelled by the arq
  job timeout, every 15 minutes.
- Postgres had no active query and worker CPU was 0.2%: the drains were asleep.

**Where they waited:** the cancelled drain's traceback ends in `execute_provider_call` at
`await semaphore.acquire()` (provider_runtime.py), reached from `_plan_and_fetch_history_chunk` ->
`fetch_ohlcv`.

**Two ways to lose the permit:** `execute_provider_call` took the provider's in-process `asyncio.Semaphore`
before quota admission and returned it only after result bookkeeping. Providers without a configured
`max_concurrency` (Alpaca, Finnhub, xStocks and Robinhood tokens in production) get a single permit.

1. **Deadlock.** This is the main cause and was confirmed live after a restart.
   - After its Alpaca request, the permit holder updates `instrument_provider_capability_status`, still
     holding the permit.
   - Another drain had already updated the same row in its open transaction and was waiting for the permit.
   - So the holder waits on that drain's row lock (`pg_blocking_pids`), and the drain waits on the holder's
     permit.
   - Postgres cannot see the semaphore half, so nothing breaks the cycle until arq cancels a drain at 600 s.
   - Drains coalesce onto the same instruments (SOXX, XLK, SPY, QQQ, SMH, NVDA repair slices), so it recurs
     within minutes.
   - At 12:16Z, four minutes after a worker restart, session 1081283's UPDATE was blocked by session 1081267,
     which had been idle in transaction for 500 s.
2. **Cancellation leak.**
   - Five early-exit paths awaited a quota settle before `semaphore.release()`.
   - A job-timeout cancellation during that await skipped the release and lost the permit for the life of
     the process.

Over the stall day the stacks of timed-out jobs show the result: 629 drains waiting at
`await semaphore.acquire()`, and 160+ waiting on Postgres replies.

**Mitigation tried:** the production worker was restarted at 2026-11-23 12:12:50Z (same image and config).
That cleared a leaked permit, but the deadlock re-formed by 12:16Z, so only the code fix helps.

## Fix

**The permit now covers only the outbound provider request.** It is held with `async with semaphore` around
the executor call that invokes the provider.
- Quota admission, request-log writes, settles and result bookkeeping all run without it. A permit holder
  can no longer wait on the database, which removes the deadlock.
- `async with` releases on every exit, including cancellation, and the early-exit paths no longer hold a
  permit. That removes the whole leak class.

Admission, quota accounting and concurrency limits are unchanged. Local concurrency still bounds in-flight
requests per provider.

## Evidence

`test_provider_runtime_semaphore_release.py`:
- **Deadlock shape:** two concurrent calls share one permit, and the first call's bookkeeping finishes only
  after the second call has sent its request. On the old code it times out (deadlock). With the fix both
  complete. The test also asserts the permit is held during the request and not during admission or
  bookkeeping.
- **Cancellation:** the contract settle raises `CancelledError` on three paths:
  - coordinator denied;
  - coordinator raised;
  - local burst bucket denied.

  On each path the permit is free afterwards, and the next caller acquires it within 1 s.

All four tests fail on the previous `provider_runtime.py` and pass with the fix.
