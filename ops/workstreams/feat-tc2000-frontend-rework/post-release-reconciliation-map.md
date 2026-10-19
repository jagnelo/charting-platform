# TC2000 post-release reconciliation map

Prepared 2026-10-19 from read-only inspection of the exact published objects
listed below. This is an execution map, not imported product code, checkpoint
acceptance, or permission to merge. The coordinator must first release Provider
and then ETF through synchronized green staging.

## Pinned preparation boundary

| Role | Exact object | Current disposition |
| --- | --- | --- |
| synchronized staging | `26443f94c5b9fd3741d28db392fecf9aafe9c699` / CI `39294027643` | green common baseline; zero product checkpoints |
| Provider candidate | `a8440efb82232a8b217df9c7330fab1795b257c9` / CI `39305740911` | candidate only; corrected backend, migration, and held-operation gates still control acceptance |
| ETF preparation | `d1c560dc95d681fb5c67bf8916846a2f354bb5f5` | preparation only; actual bridge work waits for released Provider staging |
| TC source | `c8d386d01c65b3eb31e8ddc8f30df1c00822837f` / CI `39140104361` | ordinary feature CI green; full 104-case visual and upstream consumer gates open |
| coordinator geometry repair | `e995d501c56bbd3427d8023a0b14e8ef6e37677b` / CI `39312017050` | branch-green repair; full local profile and green staging delivery pending |

The reviewed local-only Help references already delivered at the TC source are
unchanged. Their functional keyboard/scroll/readability requirements and
`0.005` screenshot tolerance remain in force. `REF-HELP-V25` remains
`required_missing`; no local reference is official V25 evidence.

## Release sequence and stop conditions

1. Wait for the coordinator to accept Provider and publish it through green
   staging. Inspect that exact staging object and its receipt; do not import the
   Provider feature object directly.
2. Wait for ETF to consume that released Provider baseline, receive its own
   acceptance, and publish through a subsequent green staging object. Inspect
   that exact object and receipt; do not import the ETF feature object directly.
3. Only after both releases, merge the coordinator-named staging SHA into this
   TC branch through the normal feature workflow. Re-run the scope guard before
   product edits so common files are classified rather than silently adopted.
4. Reconcile each seam below. Preserve upstream authority over routing,
   credentials, transport, ingestion, refresh, holdings parsing, and constituent
   resolution. TC owns consumer behavior, workstation presentation, derived
   analytics, immutable Study/Code use, and explicit unavailable states.
5. Stop on any schema ambiguity, hidden fallback to stale/unresolved data,
   changed provider admission semantics, migration graph divergence without a
   reviewed additive merge, or caller break requiring a material product-policy
   choice. Never substitute a direct sibling import.

## Contract and test map

### 1. Canonical instrument identity

- Producer authority to inspect after release:
  `backend/app/models/instrument_identity.py`,
  `backend/app/models/instrument.py`,
  `backend/app/services/instrument_mastering.py`,
  `backend/app/services/market_data_identity.py`, and
  `backend/tests/integration/api/test_canonical_instrument_boundary.py`.
  Preserve canonical instrument IDs, provider-symbol lifecycle, identifier
  effective/known/retired times, and quarantined ambiguity.
- TC consumers to reconcile:
  `backend/app/services/market_data.py`,
  `backend/app/services/watchlist_sources.py`,
  `backend/app/services/instrument_events.py`,
  `frontend/src/stores/watchlist.ts`, and the workstation research/Market Map
  consumers. Remove no canonical fields and never infer identity from a display
  symbol when the producer reports unresolved or ambiguous identity.
- Focused proof: canonical-boundary API tests; watchlist-source resolution tests;
  Market Map/breadth source-identity assertions; negative duplicate-symbol,
  retired-symbol, and unresolved-identity cases.

### 2. Series identity, scope, coverage, and derived-bar lineage

- Producer authority:
  `backend/app/models/market_data_foundation.py`,
  `backend/app/models/ohlcv.py`,
  `backend/app/services/market_series.py`,
  `backend/app/services/ohlcv_coverage.py`,
  `backend/app/services/market_data_persistence.py`, and OHLCV schemas/routers.
  Preserve `market_series_id`, deterministic `scope_key`, timeframe including
  `Y1`, feed/session/source scope, adjustment basis/version, provenance,
  continuation, completeness, and raw snapshot lineage.
- TC authority:
  its derived-bar columns and semantics (`is_derived`, `source_timeframe`,
  `derivation_method`, `derived_at`, `source_bar_count`, `source_start`, and
  `source_end`). A later authoritative provider bar must replace local derived
  lineage rather than retain a false derived marker.
- Focused proof: market-series identity and scoped OHLCV conflict tests; coverage
  API tests; TC market-data derivation/replacement tests; chart/breadth/Market Map
  current, partial, unavailable, and explicit-gap paths. Assert that different
  scope keys never coalesce and that derived bars cannot masquerade as raw
  provider observations.

### 3. Corporate-action factors

- Producer seam:
  `backend/app/models/instrument_event.py`, resumable instrument-event pages,
  provider event provenance, and adjustment-basis/version fields.
- TC seam:
  `backend/app/services/instrument_events.py`,
  `backend/app/services/market_data.py`, and migrations
  `ff1a2b3c4d5e`, `ff2a3b4c5d6e`. Preserve explicit provider
  `adjustment_factor`, factor version, materialization history, and bar
  reconciliation; do not calculate a second authoritative factor from prices.
- Focused proof: instrument-event service tests, explicit-factor materialization,
  consistent factor-version reads, split/dividend ordering, replay idempotency,
  and unadjusted/partially adjusted negative cases.

### 4. ETF WatchList and constituent lineage

- ETF authority to inspect only after its green staging release:
  `backend/app/models/etf_holdings.py`,
  `backend/app/services/etf_holdings_capability.py`,
  `backend/app/services/etf_holdings.py`,
  `backend/app/services/watchlist_sources.py`,
  `backend/app/routers/etf_holdings.py`, and ETF/watchlist schemas. Preserve
  composition/as-of/known/published times, source provider, quality,
  completeness, schema fingerprint, point-in-time request, row/holding type,
  resolution state, and explicit current/stale/unavailable capability.
- TC consumers:
  `backend/app/services/watchlist_sources.py`,
  `backend/app/routers/watchlists.py`,
  `frontend/src/stores/watchlist.ts`,
  `frontend/src/components/workstation/VirtualWatchlistTool.vue`, and Study/
  breadth universe selectors. Current resolved equities may be analytic input;
  stale last-known rows stay display-only; unavailable, pending, future-known,
  cash, derivative, placeholder, and unresolved rows cannot become constituents.
- Focused proof: ETF capability and checkpoint-consumer tests, watchlist source
  API/store tests, point-in-time exclusion of future-known snapshots, stale and
  unavailable presentation, row-aware constituent filtering, and Study/Strategy
  historical-universe tests. Assert lineage survives WatchList materialization.

### 5. Additive migration reconciliation

- Current exact heads from the coordinator audit are staging
  `fe4f5a6b7c8d`, Provider `b6e9a42d1c73`, TC `a7c91e03d54b`, and
  Strategy `slv2_0008`; ETF currently shares the staging head but still requires
  an additive holdings-capability/schema migration after Provider release.
- TC's chain remains `ff0a1b2c3d4e` -> `ff1a2b3c4d5e` ->
  `ff2a3b4c5d6e` -> `a7c91e03d54b`. Provider's installed historical
  `b6c7d8e9f0a1` shape and additive corrective `ff5a6b7c8d9e` must both be
  honored.
- After each released staging merge, enumerate the actual graph. Add a merge
  revision only if the released graph still has multiple heads. Never reparent,
  rewrite an applied body, stamp, reset, or speculate against unpublished DDL.
- Required proof when execution is authorized: fresh PostgreSQL upgrade to head;
  upgrade from staging `26443f94`; upgrade from the accepted Provider release;
  upgrade from the accepted Provider+ETF release; schema and seed equivalence
  across fresh/existing paths; downgrade safety only where repository policy
  requires it. This preparation turn intentionally runs none of those gates.

### 6. Favorites, API, router, config, defaults, and caller compatibility

- Reconcile shared registration and startup paths line by line:
  `backend/app/main.py`, `backend/app/config.py`, router exports and registrations,
  `backend/app/routers/favorites.py`, `backend/app/schemas/favorites.py`,
  `frontend/src/lib/api.ts`, `frontend/src/router/index.ts`,
  `frontend/src/stores/favorites.ts`, Compose files, `.env.example`, and Makefile.
- Preserve existing URLs, payload defaults, optional-field behavior, auth/error
  semantics, Favorites kinds/order/persistence, and legacy callers. Provider and
  ETF defaults must remain fail-closed and cannot activate credentials, routing,
  refresh, trials, or live calls merely because TC starts.
- Focused proof: favorites router/store tests, application-route tests, startup
  and config parsing tests, old/minimal payload callers, unknown extra/absent
  optional fields, and disabled-provider startup. Any rename requires an
  additive compatibility route or explicit coordinator-reviewed migration.

### 7. Immutable Code/Study outputs consumed by Strategy

- TC authority:
  `backend/app/routers/code.py`, `backend/app/schemas/code.py`,
  `backend/app/services/code_validation.py`, Study/research services,
  `frontend/src/lib/workstation/studyArtifacts.ts`, and Study/Code stores and
  components. Preserve immutable version IDs, output names/types/contracts,
  source and execution lineage, structured errors, and isolated-runner results.
- Strategy consumer seam:
  Strategy may reference immutable Code/Study versions and outputs but must not
  mutate them or reinterpret capability/unavailable states. Promotions must bind
  exact version/output contracts and retain universe/PIT lineage.
- Focused proof: code API integration tests; code validation and Study factory
  source tests; Study artifact capability/accessibility tests; Strategy immutable
  reuse, promotion, schema mismatch, ETF PIT exclusion, dynamic universe, and
  unavailable-source tests. Assert rejected output-contract changes leave prior
  immutable versions runnable and auditable.

## Geometry and visual gates kept separate

The coordinator-owned `e995d501` F9c geometry repair is deliberately not copied
or reimplemented here. Once it arrives through a named green staging release,
re-run ordinary populated-RSP Remove and Plots actions at desktop and narrow
width with unchanged clicks and diagnostics. This can update TCP1 evidence only;
it cannot close TCP2.

TCP2 still requires the complete normalized 104-case visual matrix in a granted
isolated slot. TCP4 still requires the combined functional/browser profile on
the final reconciled source. Ordinary CI, static checks, or the reviewed local
Help references cannot substitute for those gates. TCP5 remains coordinator
review and clean publication at `ready_for_human_review`; TC never self-merges.
