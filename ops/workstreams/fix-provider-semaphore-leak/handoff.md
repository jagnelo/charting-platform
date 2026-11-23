# fix/provider-semaphore-leak

Created from `staging` at `6d70107def8e2797a46db54b8ea3ad02e635d8a1`.

## Human authorization

- Recorded at: 2026-11-23T12:13:04.194198+00:00
- Request: Fix the production refresh-queue stall ('Yes, fix it here'): since 2026-11-22 02:00Z every drain blocks forever on the in-process provider semaphore in execute_provider_call because early-exit paths await a settle call before semaphore.release(); a drain cancelled by the arq job timeout during that await leaks the permit, and Alpaca's default concurrency of 1 then blocks all its calls. Release the permit on every path, including cancellation.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: draft; the implementation agent must complete scope, acceptance criteria, tests, and local validation profile before creating a goal.

Update this handoff at each coherent boundary.
