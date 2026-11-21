# fix/quota-ledger-indexes

Created from `staging` at `896ad20fc8652fb4882c5e851cc8f3bf77982b45`.

## Human authorization

- Recorded at: 2026-11-21T00:31:33.715906+00:00
- Request: Continue the refresh-queue throughput gap ('Yes, start it'). After release 896ad20f, production
  throughput stayed flat because every provider call serialises on the SQLite quota ledger write lock, and
  its admission queries full-scan the append-only baseline/reservation tables. Index the hot ledger queries
  for new and existing ledgers.
- Closure: delegated to the Desktop orchestrator (2026-11-13 standing delegation, see plan.yaml). Production
  deployment still needs the human's explicit approval for that deploy.

## Production finding

**Release 896ad20f did not raise throughput.** It was deployed at 2026-11-20T23:10Z. Six drains ran from the
23:15 tick, and the claim query fell to 0.22 ms. Over the next 75 minutes:
- Completions stayed at about 900–1,100 per hour.
- Worker CPU fell to 2–6% and Postgres CPU to about 2%.
- Busy connections sat `idle in transaction` (ClientRead).

**History jobs wait about 5.5 s before their single Alpaca request.** This is not Alpaca's quota: the 200
requests per minute is barely used, at about 35 per minute.

**Provider requests have a global ceiling.** Across every provider, the rate stayed flat at 0.6–1.5 per
second from 18:00 to 00:30Z, whether 2 or 6 drains were running. One shared serialisation point limits it.

**That point is the quota ledger.**
- Every provider call reserves through `reserve_provider_quota`, then settles through
  `settle_provider_quota`.
- Each step runs a SQLite `BEGIN IMMEDIATE` transaction with `synchronous=FULL` on the shared ledger
  `~/.config/charting-platform/provider-quota/usage.sqlite3`.
- The ledger is append-only by policy (`_prune_old_ledger_rows` is a no-op) and was 195 MB on 2026-11-21. It
  holds 128k baselines (most are Alpaca native-header snapshots) and 278k reservations.
- Neither table had an index beyond its unique keys, so each admission full-scanned both tables while
  holding the exclusive lock:
  - the latest-baseline lookup, twice;
  - the expired concurrency-lease sweep;
  - the rolling settled-usage sum;
  - the pending count.
- That cost grows with the ledger's age.

**Replay on a copy of the production ledger, 10 granted Alpaca `fetch_ohlcv:D1` reserve and settle pairs:**

| | reserve holds the lock | settle holds the lock |
|---|---|---|
| before | 252–282 ms | 7–14 ms |
| after (this branch) | 8–26 ms | 7–17 ms |

SQLite's busy handler also sleeps waiters in growing back-off steps, so long holds cost more than their own
duration.

## Fix

**Four secondary indexes** in `provider_quota_coordinator._HOT_PATH_INDEXES`:
- baselines (account_scope, quota_group, dimension, window_seconds, observed_at): the latest-baseline lookup;
- reservations (account_scope, quota_group, dimension, created_at): rolling-window settled sums and pending
  counts;
- reservations (account_scope, quota_group, dimension, window_started_at): fixed-window sums and counts, and
  the identity-keyed release lookup;
- reservations (account_scope, state, lease_expires_at): the expired-lease sweep run at every reservation.

**How they are created:**
- Fresh ledgers get them from `create_all`.
- Existing ledgers get them from `_upgrade_hot_path_indexes`, which runs `CREATE INDEX IF NOT EXISTS`. It
  runs once per process at engine creation, under the existing SQLite schema-upgrade `BEGIN IMMEDIATE`, or
  in a transaction on PostgreSQL.
- On the production ledger copy the build took about 1.3 s.
- No row is deleted or changed, so the append-only evidence policy is untouched.

## Evidence

**Unit: `test_provider_quota_ledger_indexes.py`.**
- A fresh ledger has exactly the four indexes, with these columns.
- A populated legacy ledger (indexes dropped) gains them on first use, keeps every row, and still admits and
  settles.
- A capture of every baseline and reservation SELECT across these paths finds no `SCAN` of either table in
  SQLite's query plan:
  - fixed window;
  - rolling window;
  - unique-symbol identity, including a released identity;
  - concurrency-lease admissions.
- The test asserts that each hot query shape actually ran.
- With the indexes withheld, all three tests fail, and the plan test lists the scans.

**PostgreSQL integration: `test_provider_quota_ledger_indexes_postgres.py`.**
- A legacy ledger in an isolated schema gains the four indexes through `_engine_for`, with the expected
  column order.
- Its row survives, and re-running the upgrade is a no-op.

## Staging attempt 1: f7f6fa33c (2026-11-21), red on an infrastructure probe

Exact-source feature CI on 479cec621 was green. Integration produced staging `f7f6fa33c`, whose Exhaustive
Integration Gate (run 44856040730, attempt 1) failed only at `stage=research-runner-probes`, sub-stage
`stage=resources exit=1`: the bounded memory-cgroup/tmpfs pressure probe
(`ops/probe-research-runner-resources.sh`) against the isolated research-runner container. The job log needs a
GitHub sign-in, so the exact sub-probe is not visible here.

Classification: hosted-runner resource-probe failure, unrelated to this change. This branch touches only the
quota-ledger coordinator and its tests; the research-runner container, its limits, the probe scripts and the
Makefile are unchanged from staging `896ad20fc`, whose gate passed the same probe. The identical sub-stage
failed once before on unrelated staging `a46eb6797` (2026-11-20, classified the same way, passed on re-gate).
Two failures of this probe in about a day are worth a separate look at its margin on hosted runners; the probe
and its test are unchanged and not weakened here.

Remediation re-gate: this branch is fast-forwarded to the exact degraded staging SHA `f7f6fa33c` and integrated
with `REMEDIATE_DEGRADED=1` under the 2026-11-13 delegation, following the `a46eb6797` precedent. Exact-source
branch CI and a fresh staging Exhaustive Integration Gate are still mandatory; nothing is waived.
