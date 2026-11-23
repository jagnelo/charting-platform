# fix/coalesce-history-duplicates

Created from `staging` at `4d5bd9544f4abf973e4d3ab5c3ec3233b01cf072`.

## Human authorization

- Recorded at: 2026-11-23T18:02:13.399835+00:00
- Request: Stop legacy duplicate deepest-range history children from each spending a provider call: at drain time fold a duplicate into the oldest open sibling for the same series and repoint its parents
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: draft; the implementation agent must complete scope, acceptance criteria, tests, and local validation profile before creating a goal.

Update this handoff at each coherent boundary.

## Production finding (2026-11-23)

After release 4d5bd954 removed the provider-permit deadlock, about a quarter of Alpaca D1 calls returned no data.
Most were repeats: ESZ6 (a futures contract Alpaca does not serve) had 40 open deepest-range history children,
each draining and calling Alpaca on its own. Production held about 35k open duplicate deepest-range children
(about 40% of the open refresh queue), every one created by hourly maintenance before enqueue-time sibling
joining shipped in 896ad20f (2026-11-20 23:10Z). None were created after that, but nothing folded the existing ones.

## Fix

- `coalesce_history_duplicate` (data_preparation.py): when a drain leases a deepest-range history child and an
  older waiting sibling of the same series exists (same adjustment and feed pin; rows another drain holds are
  skipped), the duplicate's parent refs move to that sibling, its parents' dependency `job_ids` are repointed,
  the sibling keeps the wider end, the more urgent priority and any coarse derivation, and the duplicate records
  `coalesced_into` and waits on the sibling. Parent rows are locked before the child row, matching enqueue joins.
- `coalesced_history_summary` + worker: once the sibling completed and covers the duplicate's range, the duplicate
  completes with the sibling's outcome (plus `coalesced_into`) without a provider call.
- `_open_latest_history_sibling` skips folded duplicates so later requests join the real survivor.

## Not changed

Per-instrument "no data" from Alpaca for price history is not remembered (metadata no-data is, for 7 days), so
instruments Alpaca never serves still cost one request per refresh cycle. Measure after deploy before changing.

## Validation

Unit 4580 passed; integration 666 passed / 2 skipped; worker regression test fails on the previous code.
