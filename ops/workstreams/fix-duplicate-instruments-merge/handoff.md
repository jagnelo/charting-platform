# fix/duplicate-instruments-merge

Created from `staging` at `24b62e7e09b3e0e568818951b8e26a3fbee66952`.

## Human authorization

- Recorded at: 2026-11-26T16:16:35.842566+00:00
- Request: do ALL of these
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: draft; the implementation agent must complete scope, acceptance criteria, tests, and local validation profile before creating a goal.

Update this handoff at each coherent boundary.

## Diagnosis (production, SELECT only, 40,015 instrument rows)

"Duplicate" = one real-world security stored as more than one `instrument` row. There is no shared
FIGI/ISIN/CIK between the pairs (identifiers are unique per type/value, `domain_key` is unique), so DB
constraints cannot see them. Same ticker + same instrument type + (same active ticker/venue listing | agreeing
D1 closes | pure `.`/`-` separator spelling) identifies them.

Counts (non-retired, non-tokenized, non-synthetic, excluding FX/crypto/futures):

- Pairs via identical active ticker/venue listing: 338 groups / 339 extra rows (the "~341"): 175 composite-FIGI
  row vs legacy CUSIP row, 148 composite-FIGI row vs keyless quarantined row, 5 share-class false positives
  (CENT/CENTA, FOX/FOXA, NWS/NWSA, RUSHA/RUSHB, UA/UAA: different CUSIPs, never merged).
- Broader same-symbol/type groups: 848 non-canonical rows planned; 806 have >=95% agreeing D1 closes over >=20
  overlapping bars, 1 disagrees, 41 have too little bar overlap (reported, not merged). Extra rows beyond the 341
  are keyless alpaca/finnhub rows on a different venue label (NYSE American vs NYSE) from the edgar/massive row.
  18 pairs are separator variants (BRK.B vs BRK-B).
- Not duplicates (left alone): tokenized wrappers of the same ticker (gate/robinhood), `$` preferred spellings
  (AGM$I vs AGMI), 4,298 `retired` rows, share classes with different CUSIPs.

Causes: (1) `market_universe._reconcile_rows` identifier branch deliberately set `instrument = None` ("a new stable key
is stronger than a legacy ticker/venue match"), minting a FIGI row next to the legacy `instrument_sync.seed_universe`
CUSIP row (created 2026-11-05/13 vs 2026-11-19); (2) keyless discovery rows (edgar CIK-only / alpaca / finnhub) whose
exact ticker+venue lookup missed because providers label venues differently, quarantined as "no stable external
identifier"; (3) `.`/`-` class-share spellings. No unique constraint can be added safely: listings legitimately share
(ticker, venue) in existing data and duplicates have disjoint identifiers.

## Design

- Root cause: `market_universe._adoptable_legacy_listing` adopts the single active, exchange-qualified, same-type
  legacy row (domain key absent/CUSIP/ISIN/SEDOL, no contradicting identifier, compatible name).
- Existing rows: `app/services/instrument_dedup.py` + arq cron `scheduled_instrument_duplicate_merge` (every 15 min,
  25 pairs/pass, 240s budget, `INSTRUMENT_DUPLICATE_MERGE_*` settings). Task, not migration: repo data repairs are
  bounded worker jobs; a migration would hold locks across 67 FK tables/millions of bars during deploy.
  Migration `b1c2d3e4f5a7` only adds the `instrument_merge_log` audit table (old id -> surviving id).
- Canonical row: strongest key (composite FIGI > FIGI > ISIN > CUSIP > SEDOL > none), issuer link, lowest id.
- Safety checks: no conflicting identifier/domain key, name compatible, evidence required, FX/crypto/futures/tokenized
  excluded, advisory lock, per-pair transaction, `lock_timeout 5s`, `statement_timeout 120s`, rows locked in id order,
  pair deferred if the duplicate has a `leased` refresh job. Re-planned each pass => idempotent/resumable.
- FK repoint is catalog-driven (all 67 FK columns incl. future_detail/option_detail/tokenized underlying, market_group
  representatives, synthetic constituents); unique collisions resolved by dropping the duplicate-side row (canonical
  wins; bars = union). market_series merged by scope (derived-d1-<id> feed scopes remapped), bars' `scope_key`
  `series:<id>:session` rewritten, series children repointed. Queued job JSON payload instrument ids rewritten.
  Duplicate INTERNAL identifiers dropped; primaries demoted so the survivor keeps exactly one.

## Rollout notes

- Review first: `merge_duplicate_instruments(AsyncSessionLocal, dry_run=True)` returns planned/skipped counts by cause.
- Merging is irreversible (duplicate rows deleted); `instrument_merge_log.detail` records moved/dropped counts.
  Dropped rows = duplicate-side rows that collided with canonical ones (e.g. identical bars).
- Old instrument ids (bookmarks, JSON payloads outside market_refresh_job) now dangle; resolve via instrument_merge_log.
- Disable with `INSTRUMENT_DUPLICATE_MERGE_ENABLED=false`. Deploy migration before the worker.
- Tests: unit 64 passed (test_instrument_dedup + test_market_universe); integration 8 passed
  (test_instrument_dedup_postgres.py); migration/unit sweep 21 passed; ruff clean.
