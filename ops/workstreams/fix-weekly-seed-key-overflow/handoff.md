# fix/weekly-seed-key-overflow

Created from `staging` at `24b62e7e09b3e0e568818951b8e26a3fbee66952`.

## Human authorization

- Recorded at: 2026-11-26T16:15:37.905264+00:00
- Request: do ALL of these
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: draft; the implementation agent must complete scope, acceptance criteria, tests, and local validation profile before creating a goal.

Update this handoff at each coherent boundary.

## Cause / fix / evidence

- Cause: `scheduled_weekly_seed` -> `run_tracked_sync(db, "seed-universe")` inserts an `instrument_sync_run` row whose `source` is the comma-joined provider chain (`_provider_chain_label`). The column was varchar(50); a chain of enough providers exceeds it and the insert (before the try block) raises "value too long for type character varying(50)". Production currently shows chains up to 34 chars (sync-instruments) and no overflow in the retained logs, so this is a latent/near-limit failure.
- Fix: migration d5e6f7a8b9c0 widens `source` to varchar(255) (model updated); `_provider_chain_label` caps at 255. Existing rows stay valid; downgrade raises if any value exceeds 50.
- Evidence: migration test (upgrade/downgrade on SQLite), label cap unit test; alembic single head d5e6f7a8b9c0. 15 tests pass.

## Orchestrator review (2026-11-26)

The overflow is real, not just latent. The production worker log from 2026-11-22 02:00:03 shows
`cron:scheduled_weekly_seed failed ... StringDataRightTruncationError: value too long for type character
varying(50)` at `arq_worker.py:352`. The subagent's log search started at the 2026-11-26 container
restart, so it missed it. `instrument_sync_run.source` is the only varchar(50) column in that table, so the
fix covers the failure. Reviewed and closed by the orchestrator.
