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
