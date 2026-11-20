# fix/tokenized-price-payload

Created from `staging` at `873eb20796ff40eb2f0c7418c34c6f6163feecd5`.

## Human authorization

- Recorded at: 2026-11-20T07:49:27.369136+00:00
- Request: please get it into a state that honors my requirements. Proceed, and yes, investigate
- Closure: delegated to the Desktop orchestrator (2026-11-13 standing delegation, see plan.yaml). Production
  deployment still needs the human's explicit approval for that deploy.

## Production finding (2026-11-20, read-only inspection of charting-first-human-4687bd0c)

From 07:15Z every quarter-hour `cron:scheduled_tokenized_asset_refresh` failed (~11s each) with
`PendingRollbackError ... Original exception was: TypeError: Object of type Decimal is not JSON serializable`.
The failing row was a `gate_tradfi` quote for instrument 34315: `GateTradfiProvider.get_tokenized_price` put its
parsed order book (`{"bid": Decimal, "ask": Decimal, "price": Decimal}`) into `raw_payload`, which is written to
the JSON `TokenizedAssetObservation.payload` and `LatestPriceSnapshot.payload` columns.

The per-asset `try/except` in `refresh_tokenized_prices` caught the flush error but the shared session stayed in
a failed transaction, so every later asset and the final commit raised. The batch cursor is only committed with
the batch, so every tick restarted on the same asset: no tokenized quote can be refreshed until this is fixed.

## Fix

1. `GateTradfiProvider.get_tokenized_price` keeps provider-style decimal strings in the quote payload (the record's
   `bid`/`ask`/`price` stay `Decimal`).
2. `upsert_tokenized_asset` stores a JSON-safe copy of any observation/snapshot payload (`Decimal` to string,
   `datetime`/`date` to ISO 8601, other non-JSON values to strings).
3. `refresh_tokenized_prices` runs each asset's persistence in a savepoint: a failure is recorded and rolled back
   alone; the provider call's quota/request log, the other assets, the commit and the cursor proceed.
4. The loop reads its batch values (ids, provider, cursor) before any I/O: a rolled-back savepoint expires the
   ORM rows it touched, and the async session cannot lazy-load them afterwards (found by the PostgreSQL test).

## Evidence

- `tests/integration/test_tokenized_price_refresh_postgres.py` (real PostgreSQL/asyncpg): old code fails with
  the production `TypeError` then `PendingRollbackError`; the fix passes.
- New unit tests: Gate payload JSON round trip (with/without a catalogue hit), Decimal/datetime payload stored as
  JSON strings, one failing asset isolated. All four fail on the old code.
- Every unit module that references tokenized assets: 865 passed (`ENV_FILE=/dev/null`; with the local
  `.env.dev`, four Tiingo quota-contract tests fail on its plan settings, unrelated to this change). Ruff clean.

## Next

Orchestrator: verify exact CI on the final head, `staging.py integrate`, wait for the exhaustive gate, promote,
build and back up the release, then ask the human to approve the production deploy. After deploy, confirm the
next `scheduled_tokenized_asset_refresh` ticks succeed and the gate_tradfi snapshot for instrument 34315 updates.

## Staging attempt 1: a46eb6797 (2026-11-20), red on an infrastructure probe

Exact-source feature CI on 0ad1c6587 was green. Integration produced staging `a46eb6797`, whose Exhaustive
Integration Gate (run 44704760479, attempt 1) failed only at `stage=research-runner-probes`, sub-stage
`stage=resources exit=1`: the bounded memory-cgroup/tmpfs/concurrent-memory pressure probe
(`ops/probe-research-runner-resources.sh`) against the isolated research-runner container. Every earlier gate
stage passed. The job log needs a GitHub sign-in, so the exact sub-probe is not visible here; the CI retry
coordinator (run 44711174571) did not classify it for an automatic rerun.

Classification: hosted-runner resource-probe failure, unrelated to this change. This branch touches only
tokenized provider/service code and tests; the research-runner container, its limits, the probe scripts and the
Makefile are unchanged from staging `873eb2079`, whose gate passed the same probe at 07:43Z. In the previous 60
staging CI runs (since 2026-10-24) this is the first failure of this stage; the other 12 failures were
Playwright functional/visual or lint stages. The probe and test are unchanged and not weakened; a fresh staging
gate on a new integration commit must pass before promotion.
