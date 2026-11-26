# fix/refresh-queue-backlog

Created from `staging` at `24b62e7e09b3e0e568818951b8e26a3fbee66952`.

## Human authorization

- Recorded at: 2026-11-26T16:15:52.994374+00:00
- Request: do ALL of these
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: draft; the implementation agent must complete scope, acceptance criteria, tests, and local validation profile before creating a goal.

Update this handoff at each coherent boundary.

## Diagnosis (2026-11-26, production read-only)

Open work: 41,970 deferred, 12,719 queued, 383 retry; 648k tracking parents. All deferred/queued/retry rows are
already due (next_attempt_at in the past); the drains are the only limit. Claims/hour ~11k (3,944 completed,
5,325 quota-denied, 1,808 dependency polls). Deferred = 21k quota-denied (retry_at within 1-60 s) + 20.7k waiting
on a prerequisite (19.5k coalesced duplicates). No orphans: 0 waits on missing jobs, 0 mutual waits, 0 failed
statuses; every wait target is queued/deferred/retry/completed. Tracking parents are never closed by design
(648k, +120k/day, 57% of a sample fully terminal); they are not claimable and cost no throughput.

What bounds completions: the provider quota ledger, not the drain. Alpaca market_data_requests_per_minute
(limit 200) is reserved to 190-200 units in nearly every minute. But the ledger is debited at the reviewed
page ESTIMATE (calendar days / 1000 bars), not the HTTP requests made: last hour 3,523 measured Alpaca HTTP
requests were debited as 7,127 units; 87% of Alpaca D1 calls over 24h (152k of 175k) return no data and cost
~1.85 units each for exactly 1 request (leading pre-listing repair slices, e.g. 2016-01-04 to the listing date).
Per-hour real Alpaca use was 4-7k requests against a 12k/h true limit.

## Fix (uncommitted)

1. provider_runtime: Alpaca fetch_ohlcv settles min(reserved, measured http_requests) in both the durable
   coordinator and policy windows (unmeasured calls keep the full reservation; other providers unchanged).
   Expected: ~2x effective Alpaca admission, ~2x completions until the drain (6 chains, ~2 s/claim) binds.
2. market_data: no-data slices ended >30 days ago are remembered 7 days (was 12 h).
Tests: tests/unit/services/test_alpaca_page_settlement.py (new, fails on old code).

## Recommended, not changed

Durable (DB/Redis) leading-gap/no-data memo so deploys do not reset it; stop querying Alpaca get_instrument_profile
(96% no-data, ~7% of units); reconcile/prune terminal system_maintenance_tracking parents; park coalesced
waiters until their survivor completes instead of polling; human must approve the quota-accounting change.

## Orchestrator review (2026-11-26)

- The diagnosis is accepted. The code fixes moved to `fix/provider-negative-memo`, which already changes the
  same no-data memo in `market_data.py` and `provider_runtime.py`.
- The quota-accounting change was approved by the orchestrator under the 2026-11-13 delegation. Alpaca's
  documented limit counts real HTTP requests, so settling at measured requests (never above the
  reservation) corrects an over-debit rather than loosening a control. Production deployment still needs
  the human's approval.
- The Redis mirror now carries each slice's own TTL class: 7 days for settled slices, 12 hours otherwise.
- Follow-ups not taken here: prune terminal maintenance tracking parents, park coalesced waiters until
  their survivor completes, stop routing profile lookups to Alpaca, and look at the drain hand-over dips.
