# feat/market-data-provider-platform

## 2026-09-25 raw OHLCV immutability correction

- `MarketBarObservation` persistence now uses conflict-do-nothing. A repeated
  fetch with the same observation timestamp cannot overwrite raw provider
  values or payload; later observations remain distinct, while canonical bars
  continue to refresh as projections.
- Market-data service tests pass `26/26` and Ruff/diff checks pass. No provider
  routing or frontend/ETF behavior changed.

## 2026-09-25 exact-current preflight after quota-ledger retention correction

- Source `dff117af3` ran the full provider manifest preflight and stopped before
  transport: `0/0` ordinary cases and zero provider requests. The receipt is
  appended to `validation.jsonl`.
- Historical quota-evidence retention did not widen routing. Provider
  quota/cost/baseline, legal/use, unresolved capability, complete NMS/OTC/SEC
  reconciliation, external secret-store, deferred-provider, publication, and
  final shadow gates remain fail-closed.

## 2026-09-25 quota-evidence retention correction

- Quota-coordinator maintenance no longer deletes old settled or uncertain
  windows, reservations, or identity claims. The historical retention setting
  remains compatibility/diagnostic metadata; cleanup is a no-op until a
  lossless archive exists.
- Coordinator tests pass `38/38`, Ruff and diff checks pass. Active quota
  enforcement is unchanged; this only prevents cross-session usage evidence
  from being discarded.

## 2026-09-25 exact-current preflight after SEC source evidence retention

- Source `def5ee1fb` ran the full provider manifest preflight and stopped before
  transport: `0/0` ordinary cases and zero provider requests. The receipt is
  appended to `validation.jsonl`.
- SEC candidate source-payload retention did not widen routing. Provider
  quota/cost/baseline, legal/use, unresolved capability, complete NMS/OTC/SEC
  reconciliation, external secret-store, deferred-provider, publication, and
  final shadow gates remain fail-closed.

## 2026-09-25 exact-current preflight after account-usage evidence correction

- Source `ab0bed0e6b5050d36730245d241bb7ce3d9f1992` ran the full manifest
  preflight and stopped before transport: `0/0` ordinary cases and zero
  ordinary provider requests. The non-secret `incomplete_preflight` receipt
  is appended to `validation.jsonl`.
- The new raw account-usage evidence path did not widen admission. The same
  explicit quota/bandwidth, legal/use, unresolved-capability, NMS/OTC/SEC,
  secret-store, deferred-provider, and final-shadow gates remain fail-closed.

## 2026-09-25 append-only account-usage evidence correction

- Provider-native account-usage observations now retain the decoded raw body
  and allow-listed capacity headers for Alpaca, OpenFIGI, Binance, Twelve Data,
  MarketData.app, and EODHD. Normalized quota dimensions remain the routing
  projection, while provider-specific usage dates, plan fields, and reset
  evidence survive across sessions.
- Migration `e6f7a8b9c0d1` adds non-null JSON evidence columns and refuses to
  downgrade while non-empty evidence would be destroyed. OpenFIGI's internal
  mapping helper now carries the validated raw response through its usage
  observation path instead of retaining only normalized rows.
- Focused provider/service/migration coverage passes; the current complete
  backend unit gate passes `2399/2399` with `37` warnings and `71.07%` coverage
  in `378.80s`; Docker-backed PostgreSQL/Redis integration passes `386/386`
  with `57` warnings in `719.90s`. Migration compatibility passes and Alembic
  reports one head (`e6f7a8b9c0d1`); Ruff and diff checks pass.
- No frontend, ETF adapter, external provider live data, deployment, or secret
  was changed. Provider-contract, universe, secret-store, deferred-provider,
  publication, and final shadow gates remain open.

## 2026-09-25 exact-current full provider preflight

- Source `fc860dc1adcd8c0b25d8dc7cebc6c674e0f95ccc` ran the full manifest
  preflight and stopped before transport: `0/0` ordinary cases and zero
  ordinary provider requests. The structured `incomplete_preflight` receipt
  is appended to `validation.jsonl`.
- The preflight continues to fail closed on explicit provider-specific quota or
  byte baselines, legal/use authority, unresolved capability evidence,
  complete NMS/OTC/SEC universe reconciliation, external secret stores, and
  deferred Tradier/IBKR/Ondo. It does not claim any skipped provider as live
  validated and does not apply a generic rate-limit fallback.

## 2026-09-25 current-source backend validation

- The complete backend unit gate passed on source
  `750f70f4aa7a3428bda5c672568fe6b94642eb38`: `2398/2398` tests, `37`
  warnings, `71.09%` total coverage, in `393.60s`.
- The Docker-backed PostgreSQL/Redis integration gate passed on the same
  source: `386/386` tests, `57` warnings, in `715.74s`; the test stack was
  cleaned up afterward without a host-wide prune.
- Migration compatibility remains clean (no migration delta since the already
  validated collision correction), Alembic reports exactly one head
  (`d5f6a7b8c9d0`), and the workstream validator accepts all `30` records.
- These are backend-only gates. They do not close the explicitly remaining
  provider-contract, universe reconciliation, secret-store, deferred-provider,
  publication, or final shadow-run gates.

## 2026-09-25 EODHD native account-usage validation

- The exact-current, account-usage-only live probe passed `1/1` on source
  `750f70f4aa7a3428bda5c672568fe6b94642eb38`; its non-secret receipt is
  appended to `validation.jsonl` and the owner-only cross-session ledger.
- The authenticated `/user` response reports the configured Free plan with a
  `calls_per_day` limit of `20`, `3` consumed, and `17` remaining. Its
  `apiRequestsDate` is stale relative to the probe date, so the adapter
  correctly exposes no reset timestamp and the runner cannot use that counter
  as a current admission baseline. The same response emitted native minute
  headers of `1200` limit and `1199` remaining without a reset boundary.
- This confirms the daily plan value but does not resolve EODHD's conflicting
  published minute contracts. Ordinary EODHD routing remains fail-closed until
  the exact minute limit, reset boundary, and evidence reference are reviewed;
  no generic fallback was added.

## 2026-09-25 migration-chain collision correction

- The final Alembic inspection found the newly chosen `d4e5f6a7b8c9` ID already
  existed in the repository's historical `add_isin_to_instrument` migration.
  The new fundamental/short-interest migration now uses unique revision
  `d6a7b8c9d0e1`; the option migration points to it.
- Alembic now reports exactly one head, `d5f6a7b8c9d0`. The affected migration
  tests pass `2/2`, the complete migration suite passes `17/17`, and Ruff/diff
  checks pass on source `0856b6e51`.
- This was a schema-graph correction only; the previously recorded full unit
  and Docker integration gates remain valid for the unchanged table operations.

## 2026-09-25 exact-current provider preflight after observation corrections

- Source `c2fb160c3f49fe69cafac824d2cee454f3debeaa` ran the full provider live
  matrix preflight and stopped before transport: `0/0` cases and zero ordinary
  provider requests. The receipt is appended to `validation.jsonl`.
- Routing remains fail-closed for the same explicit provider-specific quota or
  byte baselines, legal/use authority, unresolved capability cases, NMS/OTC/SEC
  universe evidence, external secret stores, deferred Tradier/IBKR/Ondo, and
  final shadow phase. The append-only observation corrections did not widen
  admission unsafely.

## 2026-09-25 append-only option-quote validation

- Option-chain and historical quote ingestion now appends every provider quote
  payload to `option_quote_observation`; normalized `OptionQuotePoint` rows
  remain the query projection and can no longer be the only copy of a revised
  response sharing an observation timestamp.
- Migration `d5f6a7b8c9d0`, focused option/migration coverage (`6/6`), and the
  complete migration suite (`17/17`) pass. On source `fa40d5a6f`, the full
  backend unit suite passes `2398/2398` with `37` warnings in `165.90s`, and
  the persistent Docker-backed integration suite passes `386/386` with `57`
  warnings in `459.25s`.
- No external provider request, deployment, ETF adapter change, or shadow
  activation occurred. Provider quota/legal/capability, universe,
  secret-store, deferred-provider, publication, and final shadow gates remain
  open.

## 2026-09-25 append-only fundamentals/short-interest validation

- Fundamental facts and short-interest refreshes now retain every provider
  response in immutable `fundamental_fact_observation` and
  `short_interest_provider_observation` tables. Existing natural-key rows
  remain compatibility projections, so later revisions no longer disappear.
- Migration `d6a7b8c9d0e1` and focused persistence coverage pass; the complete
  migration suite passes `16/16`. On source `772f316c1`, the full backend unit
  suite passes `2397/2397` with `37` warnings in `167.69s`, and the persistent
  Docker-backed integration suite passes `386/386` with `57` warnings in
  `461.92s`.
- No external provider request, deployment, ETF adapter change, or shadow
  activation occurred. Provider quota/legal/capability, universe,
  secret-store, deferred-provider, publication, and final shadow gates remain
  open.

## 2026-09-25 append-only tokenized-asset observation checkpoint

- Tokenized catalog/metadata refreshes now retain every provider payload in the
  immutable `tokenized_asset_observation` table. The existing
  `tokenized_asset_detail` row remains a current-state projection; repeated
  identical responses are retained rather than deduplicated or pruned.
- Added migration `d3f4a5b6c7d8`, model/service persistence, and regression
  coverage. Focused tokenized service/migration tests pass `34/34`; the complete
  migration suite passes `15/15`; Ruff, diff, and Alembic-head checks pass.
- This is a loss-prevention correction only. Provider quota/legal/capability,
  NMS/OTC/SEC universe, secret-store, deferred-provider, publication, and final
  shadow gates remain open. No external provider requests, deployment, ETF
  adapter change, or shadow activation was performed.

## 2026-09-25 tokenized-observation full validation

- The complete backend unit suite passed on source `161a8d1b4`: `2394/2394`
  tests, with `37` warnings, in `162.39s`.
- The persistent Docker-backed PostgreSQL/Redis integration suite passed on
  the same source: `386/386` tests, with `57` warnings, in `473.35s`.
- Branch workstream validation accepted all `30` records. These checks validate
  the new tokenized observation migration and runtime path; they do not close
  provider quota/legal/capability, universe, secret-store, deferred-provider,
  publication, or final shadow gates.

## 2026-09-25 Docker integration validation after market-event migration

- The complete persistent Docker-backed backend integration suite passed on
  the market-event observation source: `386/386` tests, `57` warnings, in
  `521.73s`.
- This validates the new migration/table and event persistence against the
  PostgreSQL/Redis stack. No frontend, ETF adapter, external provider, or
  shadow operation was performed.

## 2026-09-25 append-only market-event observation checkpoint

- General provider market events now have an immutable `market_event_observation`
  history table. The canonical `market_event` row remains the latest
  reconciliation projection, while every fetched payload is appended as an
  observation so provider revisions cannot erase prior evidence.
- Migration `d2e3f4a5b6c7` and focused event/prelisting/reconciliation/EDGAR/
  tokenized coverage pass `71/71`; the complete migration suite passes `14/14`;
  Ruff and diff checks pass.

## 2026-09-25 exact-current preflight refresh

- Source `2d4987df0` ran the full provider preflight and stopped before
  transport with `0/0` cases and zero provider requests. It confirms the
  append-only corrections did not widen routing unsafely.
- Remaining blockers are unchanged and explicit: unresolved provider quota or
  byte baselines, legal/use authority, capability evidence, complete
  NMS/OTC/SEC universe reconciliation, external secret stores, deferred
  Tradier/IBKR/Ondo, and the final shadow phase. The structured receipt is in
  `validation.jsonl`.

## 2026-09-25 Docker integration validation checkpoint

- The direct persistent Docker-backed backend integration run completed on the
  current source: `386/386` tests passed, with `57` warnings, in `573.15s`.
- This validates the append-only raw-bar migration and persistence behavior
  against the PostgreSQL/Redis integration stack. No frontend, ETF adapter,
  external provider, deployment, or shadow operation was performed.

## 2026-09-25 append-only raw OHLCV observation checkpoint

- Raw `MarketBarObservation` rows now include `observed_at` in their conflict
  key. A later provider revision of an existing candle therefore creates a new
  immutable raw observation instead of overwriting the earlier provider
  response; canonical bars remain refreshable projections.
- Added migration `d1e2f3a4b5c6`; its downgrade refuses to proceed if duplicate
  observations would be destroyed. Migration, market-data, and tokenized
  historical-price coverage passes `59/59`; the complete migration suite
  passes `13/13`; Ruff and diff checks pass.

## 2026-09-25 full request-audit usage reporting checkpoint

- Provider-usage summaries now read the complete append-only request-log
  history instead of applying the legacy 30-day retention filter. The rolling
  24-hour/7-day metrics remain unchanged, while retained totals and response
  bytes now include older quota evidence needed for cross-session/monthly
  reconciliation.
- Focused provider-usage, maintenance, and provider-admin router coverage
  passes `27/27`; Ruff and workstream validation pass. No external requests or
  routing admission changed.

## 2026-09-25 append-only request-audit retention checkpoint

- Provider request logs are now immutable quota/audit evidence alongside
  latest-price, search, universe, profile, and identifier snapshots. The
  maintenance endpoint cannot delete any registered provider-evidence dataset;
  its legacy retention settings remain diagnostic compatibility fields only.
- The regression now inserts an old request log and verifies both the log and
  snapshot survive maintenance. Focused maintenance/router coverage passes
  `10/10`, Ruff passes, and no provider routing or external quota was touched.

## 2026-09-25 append-only observation retention checkpoint

- Provider observation snapshots are now immutable retention evidence. The
  maintenance path no longer deletes latest-price, search, universe, profile,
  or identifier snapshots, even when legacy snapshot-retention settings are
  positive. The subsequent request-audit checkpoint extends the same
  append-only rule to provider request logs.
- Maintenance/router regressions pass `10/10`, Ruff passes, and the workstream
  validator accepts all `30` records. This closes a destructive local data-loss
  path and does not change provider routing, quota, legal, or entitlement
  gates.

## 2026-09-25 native account-usage refresh

- Exact-current account-usage-only probes passed for EODHD, Twelve Data, and
  MarketData.app (`1/1` each). These were control-plane reads only; no
  ordinary market-data, options, or universe requests were issued.
- The observations are retained as current provider evidence but do not
  promote routing: EODHD's conflicting minute contract, Twelve Data's
  separate daily-credit baseline, and MarketData.app's reviewed plan/option
  controls remain enforced exactly as configured.

## 2026-09-25 exact-current preflight refresh

- Source `33499e60d` ran the full provider preflight and stopped before
  transport with `0/0` cases and zero provider requests. The receipt confirms
  the new continuation work did not regress routing safety.
- The remaining blockers are unchanged and explicit: provider-specific quota
  baselines/byte pools, legal/use authority, unresolved capability cases,
  complete NMS/OTC/SEC universe evidence, external secret-store verification,
  deferred Tradier/IBKR/Ondo, and the final shadow phase.

## 2026-09-25 event-reconciliation continuation checkpoint

- Market-event consensus reconciliation and future-listing materialization no
  longer restart from row zero after a bounded job. Both workflows now use the
  existing durable `ProviderPaginationState` table with a date-window-scoped
  event-ID cursor, recording the next continuation and completing the cycle
  only after the final persisted row is processed. Raw provider observations
  remain immutable and are never removed by the bounded work budget.
- Prelisting promotion now has its own durable candidate-ID continuation, so an
  ambiguous early candidate cannot starve later candidates. Event
  reconciliation/materialization/promotion tests pass `15/15` across the
  focused modules; Ruff passes on the changed implementation and tests. The
  regressions prove three-row event batches process as 2+1 and a later
  resolvable candidate is reached after an earlier unresolved one.
- This closes a local starvation/data-exclusion defect only. Provider
  quota/legal/capability gates, NMS/OTC/SEC reconciliation, secret stores,
  deferred providers, publication, and the final shadow run remain open.

## 2026-09-25 latest-price raw-response retention checkpoint

- Current-price provider calls now opt into explicit response-body capture at
  the transport boundary. The normalized price remains the canonical field,
  while the raw provider body (including text fallback) is persisted in the
  latest-price snapshot provenance. If an operation performs multiple HTTP
  requests, the complete ordered response set is retained; the historical
  singular `provider_response` key remains for one-response compatibility.
- Focused telemetry/market-data/persistence regressions pass `46/46`, and Ruff
  passes for every changed implementation and test file. The earlier
  Docker-backed integration suite pass remains `386/386`; the prior exact
  full-unit evidence remains `2388/2388` before this persistence-only test
  extension. A managed rerun of the full unit wrapper did not return a final
  summary after reaching 84%, so no newer full-unit pass is claimed here.
- This is a loss-prevention correction only. It does not close provider
  quota/baseline, legal/use, capability, NMS/OTC/SEC universe, secret-store,
  deferred-provider, publication, or final shadow gates. No external provider
  requests, deployment, integration, or shadow activation were performed by
  this checkpoint.

## 2026-09-24 raw-payload and split-gate validation checkpoint

- The compatibility-only yfinance history adapter previously normalized a
  DataFrame row without retaining the original provider fields. It now stores
  the complete row under `provenance.provider_payload`; pandas/numpy scalar
  values are converted to JSON-safe Python values. The regression provider
  suite passes `264/264`.
- Runtime helpers now accept explicit operator-selected writable roots through
  `CHARTING_PLATFORM_RUNTIME_DIR` and `PROVIDER_QUOTA_LEDGER_HOST_DIR`, while
  preserving the normal owner-only defaults. This lets managed/read-only
  runners execute the same session allocator without changing production
  secret or quota behavior. Workflow tests pass `47/47`; Compose contract and
  workstream validation also pass.
- Split backend validation is green: unit suite `2387/2387` (37 warnings) and
  Docker-backed integration suite `386/386` (57 warnings). A subsequent
  combined `make test-backend-coverage` run reached roughly 72% before the
  managed runner terminated it with exit 152; pytest reported no test failure,
  so no current combined coverage rate is claimed. The last exact-head
  combined result remains `62534a2ee518e1ec8263bef662bb5a7737a5b581`,
  `2772` tests and `82.07%` line coverage.
- This checkpoint does not close the external provider quota/terms/entitlement,
  complete NMS/OTC and SEC materialization, target secret-store, deferred
  provider, publication, or final 30-day shadow gates. No integration,
  deployment, or shadow activation was performed.
- The exact-current full live preflight at source `bec4880fd1d85de2eb2a7dc9bfe8c6a757a7dbec`
  stopped before transport (`0/0`, zero provider requests) and recorded the
  same unresolved provider-specific quota/baseline, legal/use, capability,
  universe, and secret-store blockers. Its full structured receipt is in the
  append-only validation ledger.

## 2026-09-24 resumed validation and Alpaca reset-boundary handling

- Replayed the committed full provider preflight at `62534a2ee`; it stopped
  before ordinary transport with `0/0` cases and zero provider requests, while
  recording the existing provider-specific baseline, quota, legal/source,
  capability, and deployment-secret blockers.
- Refreshed the owner-scope native account snapshots for MarketData.app,
  EODHD, and Twelve Data (`1/1` each). The observations were recorded as
  aggregate-only receipts; they do not promote unresolved daily/minute pools.
- A live Alpaca usage response exposed a provider reset epoch at the current
  boundary. The coordinator correctly kept that observation
  `not_reconciled`; the live test now distinguishes observation-only evidence
  from a proven future active window instead of failing or treating it as a
  usable baseline. Focused provider/account-usage coverage passed `329/329`,
  Ruff passed, and the bounded Alpaca account-usage case passed `1/1` with one
  request. Ordinary routing remains fail-closed when the reset boundary is not
  proven.
- The Docker-backed combined backend gate then passed all `2,772` collected
  unit/integration tests with no failing-test output and `82.07%` combined line
  coverage. The repository Compose assertions also passed when executed with
  the UV-managed Python interpreter; the Make target itself still assumes a
  system `python` alias that is absent in this environment. Generated coverage
  artifacts were removed.
- The live receipts are current-source transport evidence only; they do not
  close the remaining provider terms/entitlement, NMS/OTC, SEC admission,
  environment secret-store, deferred-provider, or final shadow gates.
- The checkpoint is committed locally at `c701ab9b3`. Publication through the
  configured `github-personal` SSH alias was attempted and rejected with
  `Permission denied (publickey)`; no credential or repository state was
  exposed, and no alternate account was used.
- After the documentation checkpoint, the exact current source
  `8900c9bf8c056f37dcccb3adb9f0abd62d30fcd8` passed the bounded Alpaca
  account-usage case `1/1` with one request and 125 response bytes. The
  aggregate receipt is current-source evidence; the roster-wide preflight still
  blocks ordinary provider reads on the independent gates above.
- The subsequent exact-HEAD full provider preflight at `0fb54ef0b` again
  stopped before transport (`0/0` cases, zero provider requests). Its receipt
  refreshes the same provider-specific quota/baseline, legal/use,
  capability, universe, and target-secret blockers; no new provider was
  admitted by the Alpaca evidence.
- The exact-current MarketData.app Starter Trial matrix at source
  `272a81bca9aa58367db8bb924669b0b7a4c15c4d` passed `7/7` cases with seven
  selected live tests and six intentionally deselected cases. This refreshed
  account usage, daily/five-minute candles, latest price, option expirations,
  option chain, bounded option history, and the no-request guard for
  unbounded response-priced history under the configured durable scope.
- The isolated Dinari Sandbox canary at source `b66bf0b6775a0b52948ae4e9373a7dd8f10503dd`
  passed `1/1` with its transient owner authority controls and 20-request
  process cap. The canary exercised the configured tokenized catalogue,
  identity, price/quote, four history windows, news, dividends, splits, and
  corporate-action paths without persisting Sandbox payloads or enabling
  production routing. Dinari's numeric Sandbox quota and production terms
  remain intentionally unresolved.
- The exact-current keyless Binance matrix at source
  `ef1a928fff886490b308413a7f223c1fe80114a5` passed `3/3` with seven
  requests, covering ordinary crypto history, bounded 30-day daily history,
  latest/current price, discovery, and native weight usage. The native usage
  snapshot was reconciled before the metered reads.
- The same exact-current source passed the keyless OpenFIGI matrix `3/3`
  with three requests, covering identifier mapping, profile resolution, and
  native usage accounting. These are current keyless evidence receipts; keyed
  OpenFIGI mode remains unproven and no unrelated provider was promoted.
- The bounded Nasdaq Trader directory case at source
  `ce4f229774345e93504c94f76ea41a3b8b0deb9c` passed `1/1` with one live
  manifest case. It exercised the official `nasdaqlisted.txt` and
  `otherlisted.txt` files under the explicit two-file-per-day client cap;
  complete historical reconciliation and lifecycle deactivation remain
  separate ingestion gates.
- The canonical `make test-compose-contract` gate was made portable by using
  the repository's UV-managed Python instead of assuming a system `python`
  alias. The target now passes end-to-end, alongside the workflow suite
  (`46/46`) and workstream validation (`30` records).

## 2026-09-17 native-usage mapping admission hardening

- Applied the Alpaca account-usage decision consistently across runtime
  routing, the direct live-probe planner, and manifest preflight. A bootstrap
  contract now requires a non-empty, unique `reconciled_dimensions` list whose
  names identify finite provider pools covered by that native endpoint; mapping
  a concurrency lease or an undeclared pool invalidates the contract and is
  rejected before transport.
- Added regressions for missing/invalid/duplicate mappings and updated the
  coordinator fixture. Focused provider-runtime, quota-contract,
  quota-coordinator, and live-runner coverage passes `253/253` with
  `--no-cov`.

## 2026-09-17 exact-current Alpaca revalidation

- After the final bootstrap-contract validation change, the clean source
  `2d3bd1160147cd48ef481fbce45660264daf863c` passed the bounded credentialed
  Alpaca matrix `7/7` with eight measured requests (including the native usage
  snapshot, equity/crypto history and metadata, latest price, discovery, and
  corporate-action page). The receipt is aggregate-only and committed; this is
  current-source provider evidence, not a claim that the remaining roster-wide
  safety/terms gates are closed.

## 2026-09-17 final Docker backend gate

- The final clean-source Docker-backed combined backend gate reached all
  `2,772` collected unit/integration tests with no failing-test output; the
  generated combined coverage report measured `82.07%` line coverage (above
  the 75% gate). Docker preflight reported ready, and generated coverage files
  were removed after completion. Compose/workstream validation also passes.

## 2026-09-17 discovery pagination loss-prevention correction

- US-universe reconciliation no longer applies an arbitrary local offset/page
  ceiling that could make a valid provider continuation permanently
  undiscoverable. Provider-reported pagination is followed until explicit
  completion, while repeated/non-progressing cursors and contradictory totals
  still fail closed.
- Each raw discovery page is committed before row normalization/lifecycle work
  in both `reconcile_us_universe` and the legacy `seed_universe` path, so a
  worker interruption cannot erase an already-obtained quota-consuming
  response. Failed/incomplete runs remain non-authoritative and their stored
  snapshots remain available for inspection and later reconciliation.
- The focused market-universe and persistence suites pass (`50/50`); the
  large-offset regression proves a continuation beyond the former 2,000,000
  ceiling is retained.
- The full Docker-backed backend gate at commit `3b2b7aee` passes `2,769`
  tests with `82.06%` total coverage; generated coverage artifacts were removed
  and the worktree is clean.

## 2026-09-17 native usage bootstrap dimension correction

- The live preflight now honors each provider's explicit
  `account_usage_bootstrap.reconciled_dimensions` map. A native usage endpoint
  can bootstrap only the pools it actually reports; an unknown second pool is
  never treated as zero or allowed through to a doomed request.
- A bootstrap declaration without that explicit map is now itself fail-closed;
  it cannot implicitly authorize every unknown quota dimension. The regression
  suite covers both the mapped partial-pool case and the missing-map case.
- The configured Twelve Data `/api_usage` probe still passes and reconciles
  `credits_per_minute`. Its separate `credits_per_day` pool has no cumulative
  counter, so the full Twelve Data matrix now stops before transport with an
  explicit daily-baseline blocker. The failed attempt made zero data requests.
- Focused runner/quota/account-usage tests pass (`223/223`), and the latest
  committed-source Twelve Data preflight at `8730fc17b` is recorded in
  `validation.jsonl` as `0/0` with zero data requests and the explicit daily
  baseline blockers. This is fail-closed evidence, not a data-matrix pass.

## 2026-09-17 FMP daily-cap safety-envelope completion

- Applied the Alpaca reset-boundary decision to FMP's exact configured
  250-calls/day pool. Because FMP does not publish a calculable native bucket
  boundary, the provider contract retains `provider_defined` for audit and
  enforces a provider-scoped rolling-24-hour application envelope. A reviewed
  native reset plus evidence may replace it through the existing
  `FMP_REVIEWED_DAILY_RESET` and `FMP_DAILY_QUOTA_EVIDENCE` settings.
- The documented 500 MB trailing-30-day bandwidth pool remains explicit with
  the conservative decimal-byte ceiling; complete per-operation response-byte
  bounds and current bandwidth entitlement evidence remain required. No
  generic fallback was introduced.
- Focused quota/registry/wiring coverage passed `161/161`; the Docker-backed
  full backend gate passed `2,767/2,767` with `89` warnings and `82.05%`
  coverage. Compose/deployment contract validation passed for all 30
  workstream records.
- The committed-source FMP live preflight at `13cb2ca8f` stopped before
  transport with `0/0` cases and zero FMP requests because the local
  environment has no `FMP_OPERATION_BYTE_BOUNDS` map or current bandwidth
  entitlement evidence. The receipt is retained in `validation.jsonl`; this
  confirms fail-closed behavior, not live transport success. Receipt commit:
  `897b076ec`.

## 2026-09-17 Tiingo provider-scoped reset safety completion

- Tiingo's exact 500-unique-symbol/month and 50-request/hour pools now retain
  provider-defined reset labels for audit while enforcing provider-scoped
  rolling 31-day and rolling one-hour application envelopes. The existing
  native reset/evidence settings remain optional overrides and no generic
  limiter is introduced.
- Complete `TIINGO_OPERATION_BYTE_BOUNDS` remains mandatory before routing;
  the documented EST daily request and monthly bandwidth boundaries remain
  explicit. The durable distinct-symbol identity ledger continues to claim
  each provider symbol once per safety window and never discards observations.
- The focused registry/runtime/quota/secret suite is green at `216/216`; no
  Tiingo request was made. The Docker-backed combined backend gate also passes
  `2,767/2,767` with 89 warnings and 82.06% coverage.

## 2026-09-17 FINRA public-byte safety envelope completion

- FINRA's exact public-credential 10 GB allowance now retains the
  provider-defined monthly reset label for audit while enforcing a conservative
  provider-scoped rolling 31-day safety envelope. The provider does not publish
  the reset timezone or byte convention, so the application protects the
  durable byte ledger without inventing a universal cross-provider limit.
- The synchronous 3,000,000-byte reservation bound remains explicit and
  measured response bytes still settle reservations. Async result-byte bounds,
  ORF entitlement, source terms, and current external baseline evidence remain
  separate admission gates; no data is dropped or permanently skipped.
- The focused registry/runtime/quota/secret suite passed `216/216`; the
  Docker-backed combined backend gate passed `2,767/2,767` with 89 warnings and
  82.06% coverage. Compose/workstream/lint/diff checks also passed.
- The committed-source provider preflight at `9919912fb` stopped before
  transport with `0/0` cases and zero provider requests. FINRA remains blocked
  only by unknown external request/byte baselines (plus its separate async,
  ORF, terms, and source gates); Tiingo remains blocked by the required
  operation-byte map. Receipt commit: `validation.jsonl` recorded in the
  follow-up test commit.

## 2026-09-17 EODHD native usage refresh

- The existing EODHD credential completed a dedicated account-usage probe at
  the current source (`1/1`, one request, 304 response bytes). The redacted
  receipt is committed in `validation.jsonl`; no credentials or payloads were
  persisted.
- The snapshot remains observation-only: EODHD's official minute-pool sources
  conflict and the current account/reset evidence does not yet establish an
  admission-safe ordinary minute contract. No EODHD history/profile request
  was admitted or inferred from this usage probe.

## 2026-09-17 owner-scope native baseline refreshes

- Alpaca's current credentialed matrix passed `7/7` after its native account
  usage snapshot established the owner-scope rolling-window baseline. The
  matrix made eight bounded upstream requests and covered equity/crypto
  profiles, history, latest price, assets, and corporate actions. The redacted
  receipt is committed in `validation.jsonl`.
- Twelve Data's native account-usage snapshot passed `1/1` with one request;
  the exact minute-credit pool was reconciled in the owner-scope ledger. Its
  separate daily-credit pool remains explicitly unreconciled because the
  provider exposes no cumulative daily counter. Both receipts contain only
  aggregate telemetry.

## 2026-09-17 owner-scope full safety audit

- The full current-source provider runner stopped before transport at
  `0/0` with zero provider requests. Alpaca and the Twelve Data minute pool
  now have refreshed owner-scope evidence; remaining blockers are surfaced per
  provider for external baselines, conflicting or unbounded quota dimensions,
  legal/terms controls, deferred capability cases, and universe/secret-store
  gates. The aggregate-only receipt is committed in `validation.jsonl`.
- This is a safety audit, not a live acceptance claim. No provider routing or
  shadow activation was enabled by the run.

## 2026-09-17 MarketData.app current trial matrix

- The configured Starter Trial account passed the current-source bounded matrix
  `7/7` with nine upstream requests and 21,135 response bytes. It covered
  account usage, daily/intraday candles, latest price, expirations, option
  chain, historical option quotes, and the intentional no-request guard for
  unbounded response-priced history.
- The redacted receipt is committed in `validation.jsonl`; the configured
  trial expiry and quota remain environment-specific, and paid-plan changes
  still require explicit configuration rather than inference from `/user/`.

## 2026-09-17 Dinari Sandbox replacement-key canary

- The replacement Dinari Sandbox pair passed the isolated canary `1/1` at the
  current source, making 14 bounded upstream requests across catalogue/identity,
  price/quote, all four history windows, news, dividends, splits, and corporate
  actions. The receipt is aggregate-only and committed in `validation.jsonl`.
- This remains Sandbox-only transport/schema evidence. The transient canary
  authorization and request cap were not persisted; synthetic Sandbox data did
  not enter canonical persistence, usage, alerts, or analytics, and normal
  Dinari routing remains disabled.

## 2026-09-17 committed-source safety-preflight replay

- At implementation source `37e616e65`, the focused Alpha Vantage, SEC EDGAR,
  and Finnhub live selection was evaluated against the owner-local durable
  quota ledger. Routing safety passed for all three under their explicit
  provider-scoped rolling envelopes (25/day, 10/second, and independent
  60/minute + 30/second respectively).
- The runner stopped before transport with `0/0` cases and zero provider
  requests because each metered provider/IP baseline was unknown. This is the
  intended fail-closed cross-session behavior: a safety window makes reset
  calculation safe but does not fabricate prior external usage. The redacted
  receipt is recorded in `validation.jsonl`; no credentials or payloads were
  persisted. Receipt-record commit: `49d7c43b2`.

## 2026-09-17 explicit provider-scoped safety envelopes

- Applied the Alpaca reset-boundary decision to the other providers whose
  current evidence gives an exact numeric ceiling but omits a calculable native
  bucket boundary. Massive Stocks Basic (5 calls/minute), Alpha Vantage free
  (25 calls/day), SEC EDGAR fair-access (10 calls/second), and Finnhub's
  independent 60 calls/minute and 30 calls/second pools now each carry an
  explicit provider-scoped rolling application envelope.
- The contract retains the provider-facing reset label (`provider_defined`) for
  audit and terms review; the coordinator uses only the dimension's declared
  `safety_reset` when calculating reservations. There is no generic 60/minute,
  burst, concurrency, or cooldown fallback. Optional reviewed native-reset
  settings remain available per provider and dimension, but blank settings no
  longer make these four documented numeric pools unusable solely because the
  vendor omitted the boundary.
- Alpha Vantage and Finnhub preflight now accept their explicit seed envelopes;
  Massive remains separately terms/use-authority gated. EODHD's conflicting
  limits, FMP/Tiingo byte and pool dimensions, FRED rights, FINRA OTC
  entitlement, and other unresolved provider-specific controls remain
  fail-closed rather than receiving an inferred window.
- Focused quota/registry/routing coverage passes `172/172`; Ruff, compile, and
  diff checks pass. The full Docker-backed gate and a fresh current-source live
  preflight/matrix are the remaining validation steps for this change.

## 2026-09-17 no-loss pagination and evidence retention correction

- Tokenized catalogue refreshes now persist provider/page-size continuation in
  `provider_pagination_state`. A per-invocation fairness budget can pause work,
  but the next numeric page or opaque cursor is resumed on the next invocation;
  repeated cursors fail closed and completed cycles restart from page zero only
  after the prior cycle is marked complete.
- SEC issuer-directory candidate reports are now append-only across completed
  cycles. The prior three-cycle prune was removed so every observed directory
  row remains available for reconciliation and audit.
- SEC IPO-pipeline parsing no longer applies the local `max_events` result cap;
  every matching filing in the retrieved submissions response is normalized and
  persisted. The compatibility argument remains validated, while the provider
  response remains the bounded request unit.
- Added migration `ce5f6a7b8c9d_add_provider_pagination_state.py`, migration
  smoke coverage, and focused regressions. Tokenized/SEC/IBKR focused tests,
  Ruff, and diff checks are green. The exact-source Docker-backed full gate
  passed `2,766/2,766` with `89` warnings and `82.05%` coverage at source
  `0e1492a45`; Docker Server `29.7.2` and repository Postgres/Redis
  testcontainers were active.

## 2026-09-17 IBKR history pagination loss-prevention correction

- The deferred, fixture-covered IBKR adapter no longer applies an estimated
  page-count ceiling (`estimated pages + 10`) to historical reads. It now
  follows every 1,000-bar response page through the requested range until the
  gateway returns a short/empty page or reaches the end.
- Safety remains fail-closed: repeated cursors and non-advancing timestamps
  raise typed provider errors rather than returning a partial series. The
  documented 15-year request and two-year post-expiry-futures limits remain
  provider entitlement bounds, not pagination discard rules.
- IBKR remains user-deferred and non-routable without a live Client Portal
  Gateway session. Focused IBKR coverage passed `14/14`; no provider request,
  credential, frontend file, or ETF adapter changed.

## 2026-09-17 Nasdaq directory first-window bootstrap

- Nasdaq Trader's complete NMS directory refresh is governed by an explicit
  application-owned ceiling of two conditional requests per market day (one
  each for `nasdaqlisted.txt` and `otherlisted.txt`); Nasdaq does not publish a
  numeric quota for these files.
- The durable live ledger now records that distinction explicitly with a
  `baseline_mode: local_zero` contract field. A missing first local window is
  initialized and persisted at zero only for this deployment-scoped pool; no
  external provider allowance or generic zero baseline is inferred.
- Focused coordinator/runner coverage passed `83/83`. The current keyless
  Nasdaq directory pagination probe then passed `1/1`, making exactly two
  official-file requests and measuring `890,361` response bytes. The receipt
  is retained in `validation.jsonl`; later sessions reuse the durable local
  baseline and cap.
- No frontend files, ETF provider adapters, credentials, or provider payloads
  were changed. OTC completeness, SEC materialization policy, target secret
  stores, deferred providers, and the final shadow phase remain separate gates.

## 2026-09-17 current-source backend acceptance replay

- The combined backend unit and Docker-backed integration gate passed
  `2,760/2,760` with `89` warnings and `82.04%` coverage, above the
  repository's 75% threshold. Docker Server `29.7.2` and the repository
  Postgres/Redis testcontainers were available; this corrects the earlier
  sandbox-only Docker-socket failure.
- The gate was replayed after the implementation commit at source
  `9fbc6d986`; the prior `2,757/2,757` and `2,759/2,759` receipts remain
  historical. No
  frontend files, ETF
  provider adapters, credentials, or external payloads were changed.

## 2026-09-17 Alpaca native reset-window correction

- Alpaca's current official market-data documentation publishes a
  200-requests/minute Basic pool and the OpenAPI contract describes
  `X-RateLimit-Reset` as the Unix epoch when the remaining quota changes. It
  does not publish a fixed calendar-minute boundary.
- The quota seed now uses a conservative rolling 60-second safety envelope,
  not an invented fixed-minute reset. The provider-native account-usage
  snapshot is allow-listed as the first control-plane request and seeds the
  durable active baseline only when limit, remaining, and a future reset epoch
  all match the reviewed contract. No daily allowance is inferred.
- Invalid optional reset overrides cannot replace the rolling safety envelope.
  Corporate-action cursor pagination remains independently durable and
  unbounded in retention; `ALPACA_CORPORATE_ACTIONS_MAX_PAGES=0` is now the
  compatibility-only default and cannot discard later pages. The worker may
  still process one page per invocation for fairness, but persisted cursors
  are always requeued until completion.
- Focused quota/account-usage coverage passed `5/5` selected tests. One
  bounded native usage request was made for reset-shape verification; no
  credentials or provider payloads were persisted.
- The exact current-source credentialed Alpaca matrix then passed `7/7` with
  eight upstream requests: native usage bootstrap, daily and five-minute
  history, latest price, equity and crypto profiles, asset/universe discovery,
  and a corporate-action page. No dirty source paths were present. Alpaca's
  remaining acceptance work is terms/redistribution review; the quota,
  baseline, adapter, and bounded live-transport gates are closed.

## 2026-09-17 exact-current configured-provider revalidation

- The exact-current Alpaca receipt was replayed after the pagination-default
  correction at source `22e66317440d6e18212a7af8604593a1178cc3af`: `7/7`
  cases passed with eight measured requests. The follow-up receipt commit only
  records that result; no provider source changed between the tested source and
  receipt commit.
- MarketData.app's configured Starter Trial matrix passed `7/7` at source
  `3d0413b5b48dd70b1580d452e64cc1d8246736d2`, with nine measured requests.
  The response-priced unbounded-history guard made no request, while all
  admission-safe account/candle/latest/options cases passed.
- Dinari's replacement Sandbox pair passed the isolated canary at source
  `49687424a480c73a4f0ee6758de4e589f64e7f57`: `1/1`, 14 requests, under a
  transient 20-request cap. This does not promote Sandbox to ordinary
  routing, and no Sandbox payload entered canonical persistence.

## 2026-09-17 exact-current Binance and OpenFIGI revalidation

- Binance's native fixed-minute request-weight bootstrap and bounded crypto
  matrix passed `3/3` at source `fec91f02921b318e52b0894b0d7d6dee3f56660c`.
  The durable coordinator admitted the native snapshot before discovery,
  latest-price, and history operations; no generic request count was used.
- OpenFIGI's anonymous native-usage, mapping, and profile matrix passed `3/3`
  at the same source. The run proves only the anonymous public-IP contract;
  keyed-mode evidence remains absent because no OpenFIGI API key is configured.

## 2026-09-17 exact-current EODHD and Twelve Data usage refresh

- EODHD's native `/user` account-usage probe passed `1/1` at source
  `bc2db97d257755a0352eb5ff1eaaa051049247c`. Its daily observation remained
  stale and its official minute limits remain conflicting, so the result is
  retained as telemetry without promoting either routing pool.
- Twelve Data's native `/api_usage` probe passed `1/1` at the same source. The
  provider-reported minute pool reconciled into the durable ledger; the
  separate Basic daily allowance remains un-inferred because the response does
  not expose a stable daily cumulative counter.

## 2026-09-17 lossless, resumable provider-event ingestion

- Replaced the Alpaca corporate-action page bound with a durable cursor
  workflow. `InstrumentEventPageSnapshot` retains each raw provider envelope;
  `InstrumentEventFetchState` retains the provider, query fingerprint, page
  number, continuation token, cumulative normalized counts, and completion
  state.
- Event refreshes process one page per provider call, pin incomplete work to
  the provider that issued the cursor, and resume from that cursor on the next
  job. A fresh cache from another provider cannot strand an incomplete page
  chain. Repeated persisted cursors fail closed rather than looping.
- Alpaca requests all documented corporate-action families. Families not yet
  represented by the normalized event enum remain in the immutable raw page
  snapshot. The direct Alpaca compatibility method follows every page.
- Massive split/dividend reads now follow both independently paginated
  endpoints to completion; the old local page-bound setting is compatibility
  only and is no longer a routing gate or a data-retention limit.
- Added migration `cd4e5f6a7b8c_add_resumable_event_pages.py`, with a single
  Alembic head after merging the existing `b0c1d2e3f4a5` and
  `bc2d3e4f5a6b` branches. Focused provider/event/runtime/wiring tests and the
  full unit suite were replayed; live validation now uses one durable Alpaca
  page as the bounded transport case, while the service-level resume path is
  covered by deterministic tests.
- No frontend files, ETF constituent adapters, credentials, or external
  payloads were changed. Deployment migration application and a credentialed
  worker resume probe remain environment gates.
- The current owner-local Alpaca replay before the rolling-window correction
  selected seven credentialed cases, but the durable shared ledger admitted
  only the native usage snapshot; the remaining six calls were correctly
  refused before transport because the old fixed-window contract could not
  reconcile the provider's reset epoch. That historical receipt is retained
  as evidence of the fail-closed behavior, not as current acceptance evidence.
- Host-backed integration validation was subsequently rerun with the running
  Docker daemon (`29.7.2`) and passed `386/386` in `358.18s` using the
  repository's Postgres/Redis testcontainers. The earlier failure was only the
  unprivileged sandbox's inability to open Docker's Unix socket, not a missing
  or stopped Docker installation.

## 2026-09-17 configurable core-refresh throughput

- Added `MARKET_DATA_REFRESH_QUEUE_BATCH_SIZE` to make the durable refresh
  worker's per-15-minute claim size explicit and deployment-configurable.
  The default is `100`, and the queue clamps values to `1..500` so throughput
  tuning cannot bypass the provider quota coordinator.
- Wired the setting through the checked-in environment example and both
  backend/worker services in standard and RPi Compose; deployment guidance
  documents the quota/latency tradeoff.
- Added invalid/low/high configuration regressions. Focused worker and
  wiring coverage passed `81/81`; the authoritative backend unit gate passed
  `2,370/2,370` with 37 warnings and 70.82% coverage. Compose contracts,
  Ruff, and diff checks passed.
- No provider calls, credentials, frontend files, or ETF-provider adapters
  changed. Provider-specific quota/legal/source, universe, target-secret,
  deferred-provider, and final-shadow gates remain unchanged and open.

## 2026-09-17 recurring core-refresh key correction

- Fixed the whole-universe daily D1 scheduler's permanent `d1:<instrument_id>`
  request key. A completed row could otherwise absorb every later daily
  delivery and prevent a new refresh from ever being queued.
- Core refreshes now use `d1:<instrument_id>:<UTC run date>`, preserving
  same-day scheduler idempotency while allowing the next day to create a new
  durable job and retain prior-run history.
- Queue/worker coverage passed `61/61` initially and the focused queue suite
  passed `9/9` after the direct next-day regression was added. Ruff and diff
  checks passed; the authoritative backend unit gate passed `2,367/2,367`
  with 37 warnings and 70.82% coverage.
- No provider calls, credentials, frontend files, or ETF-provider adapters
  changed. Provider quota/legal/source, universe, target-secret, deferred
  provider, and final-shadow gates remain unchanged and open.

## 2026-09-17 manifest-derived usage-only selection

- Removed the duplicate hard-coded `--account-usage-only` provider allowlist.
  The runner now derives accepted providers from the explicit manifest
  `account_usage` cases, so a future provider cannot gain a native bootstrap
  case while remaining rejected by a stale CLI list.
- The focused runner suite passed `44/44`; the full backend unit gate passed
  `2,366/2,366` with 37 warnings and 70.82% coverage, with Ruff and diff
  checks green.
- The committed-source Binance matrix at source
  `1b89693fb7677dd5c4d71f22d8021e7ac7a7b5d6` passed `3/3` with seven HTTP
  requests and no dirty source paths. The receipt is aggregate-only; all
  provider-specific, legal/source, universe, target-secret, deferred-provider,
  and final-shadow gates remain open.

## 2026-09-17 native-usage bootstrap admission correction

- The live runner previously blocked a provider's full matrix whenever its
  fixed-window baseline had naturally expired, even when that provider's
  manifest contained an explicit native `account_usage` snapshot capable of
  re-establishing the current window.
- The preflight now permits that narrowly identified bootstrap provider to
  enter the matrix; the collection hook runs its native usage case first, and
  each subsequent operation still performs an atomic fail-closed reservation.
  Providers without a manifest usage bootstrap remain blocked on an unknown
  baseline, so this is not a generic quota fallback.
- Regression coverage passed `44/44` focused runner tests and Ruff/diff checks
  passed. A current Binance run then passed `3/3` with seven HTTP requests,
  including the native usage snapshot, discovery, latest/history, and price;
  its aggregate receipt records `17,616,811` response bytes and no payloads or
  credentials.
- The initial receipt is marked `not_current_source` because it exercised the
  uncommitted correction. After commit `c2907967c`, the same bounded suite was
  replayed and passed `3/3` with seven requests at source
  `c2907967c8aaedbfa85d520dbaaab0d2baa21f0e`; the receipt has no dirty source
  paths. Full unit, workflow, Compose, diff, and workstream gates are green.
  All other provider-specific, legal/source, universe, target-secret, and
  final-shadow gates remain open.

## 2026-09-17 configured-provider live validation

- With the owner-local quota coordinator running under elevated filesystem
  access, the configured MarketData.app trial passed its focused live suite:
  `7/7` tests and `9` HTTP requests, including account usage, latest price,
  intraday history, option chain/expirations, and option quote history. The
  response-priced history guard correctly made no request because its reviewed
  result/credit ceiling is still absent.
- The configured Dinari credentials passed the explicitly authorized Sandbox
  canary (`1/1` test) under a `24`-request process cap. This is transport and
  schema evidence only; Sandbox quota/commercial terms remain unknown and the
  provider is not promoted to ordinary routing.
- Alpaca's configured paper credentials also passed the account-usage-only live
  case (`1/1`, one request, 125 response bytes). This records the native
  account-usage transport, but the provider's reset boundary and current quota
  evidence remain unresolved, so ordinary Alpaca routing stays fail-closed.
- EODHD, Twelve Data, and Binance each passed their account-usage-only live
  case (`1/1` each). The current OpenFIGI anonymous account-usage probe returned
  a typed upstream `429`; it was recorded without a blind retry, and does not
  replace the earlier bounded anonymous evidence.
- The receipts contain aggregate request/byte telemetry only. No credential,
  response payload, frontend file, or ETF-provider adapter changed.
- Repository workflow/deployment contracts remain green: `46` workflow tests
  passed, and the backend/e2e/RPi Compose configuration assertions passed.
- The final committed-checkout backend unit gate passed `2,364/2,364` with
  37 warnings and 70.82% coverage. This verifies repository-controlled code;
  it does not close external quota, legal/source, target-secret, Docker, or
  shadow-run gates.
- The current-head full live-matrix safety preflight stopped before transport at
  source `481bf244c`, with `0/0` cases and zero provider requests. It reports
  provider-specific quota/baseline/reset, unresolved live-operation, and legal
  or capability-safety blockers; no acceptance or routing-promotion claim was
  made.

## 2026-09-17 EODHD reviewed-entitlement routing correction

- The EODHD quota seed already accepted a positive operator-reviewed native
  minute entitlement, including the configured account's `1,200/minute`
  header, but the routing-control diagnostic retained an obsolete `<=1000`
  check.
- Removed that stale arbitrary cap. A positive reviewed limit now follows the
  same path in both the seed promotion and routing-control diagnostics;
  `EODHD_REVIEWED_MINUTE_RESET` and `EODHD_MINUTE_QUOTA_EVIDENCE` remain
  mandatory, and no provider request was made.
- Focused registry/quota coverage passed `134/134`; the new regression asserts
  that the reviewed 1,200/minute entitlement is not rejected by diagnostics.

## 2026-09-17 FMP trailing-bandwidth contract correction

- The current official FMP pricing page states that the free-plan bandwidth
  allowance is 500 MB over a trailing 30-day window. The seed now records the
  conservative decimal ceiling (`500,000,000` bytes) with the explicit
  provider-specific `rolling_30_days` reset instead of leaving that boundary
  unknown.
- The configured account's reported 512 MB value remains documented as a
  source discrepancy; no higher allowance is inferred. The exact daily
  250-call ceiling uses a provider-scoped rolling-24-hour application safety
  envelope because the native bucket boundary is not documented. A reviewed
  native reset and evidence may replace that envelope through
  `FMP_REVIEWED_DAILY_RESET` and `FMP_DAILY_QUOTA_EVIDENCE`; they are not
  required for the default safety path.
- `FMP_REVIEWED_BANDWIDTH_RESET` remains available as an optional validated
  override for a future plan. Complete operation-byte bounds and current
  bandwidth entitlement evidence remain mandatory before routing; the
  documented rolling-30-day boundary is used when that override is blank.
- Focused quota/registry/wiring coverage passes 161/161; the Docker-backed
  complete backend gate passes 2,767/2,767 with 89 warnings and 82.05%
  coverage. No provider request is required for these checks.

## 2026-09-17 Bybit live-preflight diagnostic correction

- Commit `a3ce59d2` fixes the `LIVE_PREFLIGHT_ROUTING_CONTROLS` alias for
  `bybit_xstocks`. The runner now resolves the actual `bybit_xstocks` status
  and reports the precise terms/jurisdiction controls when they are missing,
  rather than emitting a generic missing-status diagnostic.
- Secret-wiring coverage passed `25/25`, live-runner coverage `42/42`, and the
  complete backend unit gate passed `2,363/2,363` with 70.82% coverage and 37
  warnings. Ruff, diff checks, and workstream validation passed.
- No provider calls, credentials, frontend files, or ETF-provider adapters
  were changed by this correction.
- Added a general regression invariant requiring every
  `LIVE_PREFLIGHT_ROUTING_CONTROLS` alias to resolve to a status emitted by
  `routing_safety_preflight`; focused secret-wiring coverage now passes `26/26`.
- The current-source Bybit-specific preflight now reports the concrete missing
  terms/jurisdiction controls and stops before network access (`0/0` cases,
  zero provider requests), while separately retaining the unknown native
  five-second baseline blocker.

## 2026-09-17 Exact-source OpenFIGI anonymous matrix

- The first current-source OpenFIGI native-usage attempt returned HTTP 429 and
  was retained as a typed provider-rate-limit failure with aggregate `429`
  telemetry; no retry loop or guessed reset was used.
- After one provider-window delay, exactly one retry was made at source
  `a76955954f0cf84dc87f0d37a447faf3ae200d7f`. The native usage bootstrap
  passed `1/1`, then the anonymous bounded mapping/profile/account matrix
  passed `3/3` with three requests and 87,895 response bytes.
- This is anonymous-mode transport/header evidence only. Keyed-mode limits
  remain unproven because no OpenFIGI key is configured; receipts contain no
  credentials or payloads.

## 2026-09-17 Current-source Twelve Data and EODHD usage snapshots

- The exact committed source `6047a59858e34b41122c511f30987f6b27fee64d`
  passed the bounded Twelve Data native account-usage case (`1/1`, one
  upstream request, 132 response bytes) using the owner-only durable local
  quota ledger.
- The same source passed the bounded EODHD native account-usage case (`1/1`,
  one upstream request, 304 response bytes). This only observes the provider's
  account endpoint; EODHD history/profile/quote/discovery routing remains
  fail-closed until the conflicting minute-pool limit/reset and evidence are
  reviewed.
- Both receipts are aggregate-only and redacted in `validation.jsonl`; no
  credentials or provider payloads were persisted.

## 2026-09-17 Exact-source MarketData.app and Binance replay

- MarketData.app passed its bounded matrix `7/7` at exact source
  `ac34754e16d8fb49a486cba27ed63c3e676cf706`, with nine upstream requests and
  20,960 response bytes. The response-priced unbounded-history guard made no
  request.
- Binance's native request-weight bootstrap passed `1/1` at that same source,
  followed immediately by its bounded matrix `3/3` with seven upstream
  requests and 17,616,639 response bytes. The first replay after a stale
  fixed-window observation was correctly stopped before transport; the
  successful retry refreshed the native 6,000-weight/minute baseline at the
  next boundary and then exercised discovery, latest/history, current price,
  and usage accounting.
- Receipts are aggregate-only and redacted in `validation.jsonl`; no
  credentials or provider payloads were persisted.

## 2026-09-17 Current-SHA full safety preflight

- The complete manifest preflight at source
  `0de1e9f9e50565cd88f4637897c6037dc3f4eba3` stopped before network access
  with `0/0` cases and zero provider requests. It reports the current
  provider-specific quota/baseline, capability-disposition, legal/source,
  complete-universe, and target secret-store blockers.
- This confirms fail-closed behavior only; it is not live acceptance and does
  not authorize routing promotion, deployment, deferred-provider activation,
  or the final shadow run.

## 2026-09-17 Binance fixed-window live-ordering correction

- The first current-window Binance replay exposed a real boundary race: a
  separately run native usage bootstrap rolled over before the matrix's first
  metered operation, producing a typed coordinator admission failure rather
  than an unsafe request. The failed receipt remains in `validation.jsonl`.
- Commit `f9172617a` adds a manifest-runner-only pytest collection hook that
  executes all native `account_usage` snapshots before metered live cases, plus
  a regression test. Ordinary unit/integration collection is unchanged.
- After a fresh current-window snapshot, the exact committed source passed the
  Binance matrix `3/3`, with seven requests and 17,616,639 response bytes
  across latest/history, current price, discovery, and native weight usage.
  No credentials or payloads were persisted.

## 2026-09-17 Current-source OpenFIGI keyless matrix

- After a fresh native rate-limit observation (`1/1`, one request, 8,812
  response bytes), the exact current source `690b1bfdf4a950cb1e060a3e72c140f55ec87ee5`
  passed the bounded OpenFIGI keyless matrix (`3/3`, three requests, 87,895
  response bytes) for stable-identifier mapping, profile resolution, and
  account usage.
- The receipts are redacted in `validation.jsonl`; no provider payloads or
  credentials were persisted. This proves anonymous-mode transport and
  native-header accounting only; keyed-mode limits remain separately
  unproven because no OpenFIGI key is configured.

## 2026-09-17 Current-source Dinari Sandbox canary

- The exact current source `67dc4e3736caceb3464f6f42de75a38e5933e813`
  passed the isolated Dinari Sandbox canary (`1/1`) with the transient
  application cap of 32 requests. It made 14 bounded upstream requests and
  recorded 187,388 response bytes across catalogue/identity, price, quote,
  DAY/WEEK/MONTH/YEAR history, news, dividends, splits, and corporate actions.
- The canary receipt is marked `dinari_sandbox`, records only aggregate
  telemetry, and does not enter canonical persistence or ordinary routing.
  Dinari's numeric Sandbox quota/reset and commercial/redistribution terms
  remain deliberately non-routable.

## 2026-09-17 Current-source MarketData.app bounded matrix

- The exact current source `37a95bcc161ccf11a0435438bc7f730a589bd5eb`
  passed all seven selected MarketData.app cases. The run made nine bounded
  upstream requests and recorded 20,960 response bytes across account usage,
  daily/five-minute candles, latest price, option expirations, current option
  chain, and bounded historical option quotes.
- The response-priced unbounded-history guard passed without making a request.
  The receipt is redacted in `validation.jsonl`; no credentials or provider
  payloads were persisted. This is exact-source transport evidence for the
  configured trial policy, not a promotion of any other provider or of
  response-priced history.

## 2026-09-17 Current-head full-matrix safety preflight

- The complete manifest preflight at source `8a0bac156fdc3e7bf399ac44065703c50223a9c5`
  stopped before network access with `0/0` cases and zero provider requests.
  It reported the expected provider-specific quota/baseline/reset, legal and
  source, capability-disposition, complete-universe, and target secret-store
  blockers. This confirms fail-closed behavior; it is not live acceptance.

## 2026-09-17 Current-source native usage refresh

- The exact current committed source `79b87e71dfc5cf001362e1d87985dc04d089b60b`
  passed the bounded MarketData.app account-usage case (`1/1`, one request,
  135 response bytes) using the owner-local configured Starter Trial policy.
- The same source passed the bounded Alpaca account-usage case (`1/1`, one
  request, 125 response bytes) using the owner-local paper credentials.
- Both receipts are redacted and durable in `validation.jsonl`; no provider
  payloads or credentials were persisted. These are native usage observations,
  not ordinary routing promotion: Alpaca's reset semantics remain unresolved,
  while MarketData.app remains admitted only under its explicitly configured
  plan/limit/expiry policy.

## 2026-09-17 Migration compatibility against staging base

- The explicit `INTEGRATION_BASE_SHA=8b885a2f...` migration gate passed all
  `31` changed provider-platform migration files. The previous-release schema
  reached head `fe4f5a6b7c8d`, the checked-out schema upgraded successfully,
  and the previous application returned `/health 200` against the expanded
  schema. Temporary Docker/worktree resources were cleaned; no provider calls
  or credentials were used.

## 2026-09-17 Compose and workflow contract validation

- `make test-compose-contract` passed for the main and RPi Compose files,
  including the egress-deny/E2E network assertions and provider environment
  wiring. `make test-workflow` passed all `46` workflow tests using the
  isolated UV cache. The initial default-cache attempt was only an environment
  permission failure; no code or provider state was changed.
- These checks verify static deployment/CI contracts, not the presence of
  GitHub/RPi/production secret values or permission to deploy. Those target
  secret-store and deployment gates remain owner-controlled.

## 2026-09-17 PostgreSQL/Redis integration validation

- The Docker-backed `make test-int` gate passed `386` integration tests in
  `354.16s` against isolated PostgreSQL/Redis testcontainers at source
  `5fd3544b6`. Repository cleanup removed the branch-scoped test session
  without host-wide pruning; no provider live calls or credentials were used.
- This validates the finalized EODHD coordinator change through the
  database-backed integration boundary in addition to the `2,362/2,362` unit
  gate. It does not promote provider routing or close the remaining
  owner-controlled quota, legal/source, universe, secret-store, deployment,
  or shadow gates.

## 2026-09-16 EODHD bounded bootstrap live verification

- Commits `d190251d1` and `b97533bf8` close the planner gap identified by the first safety
  preflight: the explicitly allow-listed EODHD `/user` account-usage operation
  can reserve only its reviewed daily/concurrency dimensions while the
  unresolved minute pool is excluded; ordinary EODHD operations remain
  fail-closed.
- The committed-source bounded live case passed `1/1` with exactly one
  authenticated upstream request and 304 response bytes. The receipt is
  current at source `b97533bf8` in `validation.jsonl`; no history, quote,
  profile, or discovery request was admitted.
- The complete backend unit gate passed `2,362/2,362` with 70.82% coverage and
  37 warnings; focused coordinator/runtime coverage passed `92/92`; Ruff,
  compileall, and diff checks passed. The remaining owner gate is current
  evidence for the exact EODHD minute limit/reset, after which ordinary routing
  may be reviewed for promotion.

## 2026-09-16 EODHD conflicting minute-pool admission control

- EODHD's 20/minute Free Starter publication conflicts with the official
  general 1,000/minute statement. The seed now records that conflict and an
  unresolved provider-defined minute reset; the lower value is audit metadata,
  not a runtime entitlement.
- Ordinary EODHD history/profile/quote/discovery routing requires the
  provider-specific `EODHD_REVIEWED_MINUTE_LIMIT`,
  `EODHD_REVIEWED_MINUTE_RESET`, and `EODHD_MINUTE_QUOTA_EVIDENCE` controls.
  The native `/user` account-usage operation remains a bounded bootstrap for
  the independent daily pool; only the named unresolved minute dimensions are
  allowed during that control-plane read.
- Controls are wired through settings, registry diagnostics, local/RPi Compose,
  GitHub live workflow, live safety diagnostics, examples, and documentation.
  Focused provider/quota/runtime/wiring coverage passed `214/214`; Ruff,
  compileall, and `git diff --check` passed. No external provider request was
  made by these checks.
- The remaining owner gate is current EODHD account/provider evidence for the
  minute limit/reset. Populate the three non-secret controls per environment,
  rerun the committed-source EODHD live matrix, and reconcile the daily native
  baseline when `/user` reports the current UTC date. This does not promote
  routing, deployment, or the deferred shadow run.

## 2026-09-16 Native account-usage baseline refresh

- Re-ran the bounded account-usage-only live cases from the committed source
  for Alpaca, EODHD, Twelve Data, and MarketData.app. Each passed `1/1` with
  exactly one upstream request; aggregate-only receipts are durable in
  `validation.jsonl` and no broader market-data operation was spent.
- Re-ran MarketData.app's complete reviewed Starter-trial matrix from the same
  committed source: `7/7` focused cases passed, including daily/five-minute
  candles, latest price, expirations, option chain, bounded option history,
  and the deliberate no-request guard for unbounded response-priced history.
- This refresh improves current usage evidence only. It does not promote a
  provider whose reset, legal-use, byte/cost, entitlement, or plan controls
  remain unresolved, and it does not activate routing or shadow mode.

## 2026-09-16 Alpaca independent reset-boundary admission control

- Alpaca's documented 200-requests/minute account pool remains
  `provider_defined` by default because the current plan documentation does
  not establish a fixed or rolling initial reset boundary. The implementation
  adds provider-specific `ALPACA_REVIEWED_RESET` and
  `ALPACA_QUOTA_EVIDENCE` controls and only promotes the quota contract when
  both are admission-safe/evidenced; no generic rate-limit fallback was added.
- `fetch_account_usage` is deliberately exempt from the reset pair because it
  is the explicit one-request bootstrap path that observes native
  `X-RateLimit-*` headers. Ordinary history/latest/metadata/discovery routes
  still fail closed until the reviewed pair is configured. Corporate-actions
  pagination separately requires the positive
  `ALPACA_CORPORATE_ACTIONS_MAX_PAGES` bound.
- Controls are wired through local and backend examples, Docker Compose, RPi
  Compose, the manual GitHub workflow, registry diagnostics, and the live
  safety preflight. Documentation records the independent controls and keeps
  Alpaca UUIDs provider-native rather than treating them as canonical FIGI/CIK.
- Focused coverage passed `424/424`; the complete backend unit gate passed
  `2,356/2,356` with 37 warnings and 70.76% coverage. Ruff and
  `git diff --check` passed. The committed-source focused live case passed
  `1/1` with one authenticated request and 125 response bytes; the redacted
  receipt is durable in `validation.jsonl`.
- The current gate remains open: obtain current reset-boundary evidence,
  populate the pair in each authorized environment, run the bounded live
  Alpaca matrix, and reconcile the native observations before any routing or
  shadow activation. This feature branch still does not modify frontend or
  ETF constituent adapters.

## 2026-09-16 Finnhub independent reset-boundary admission control

- Finnhub's observed free-account ceilings remain two distinct dimensions:
  60 calls/minute and a 30 calls/second hard cap. Commit
  `dd60e653237ccd4b8c24566fa4d5917fc6239971` adds independent reviewed reset
  and evidence controls for both dimensions instead of applying one generic
  window. The default contract remains unresolved and non-routable.
- `FINNHUB_REVIEWED_MINUTE_RESET`, `FINNHUB_REVIEWED_SECOND_RESET`,
  `FINNHUB_MINUTE_QUOTA_EVIDENCE`, and `FINNHUB_SECOND_QUOTA_EVIDENCE` are
  wired through local/RPi Compose, the manual GitHub workflow, diagnostics,
  live preflight, and environment examples. Promotion requires both
  admission-safe reset labels and non-empty dimension-specific evidence;
  otherwise the original provider-defined contract is retained.
- Focused registry/quota/wiring coverage passed `153/153`; the complete backend
  unit gate passed `2,354/2,354` with 37 warnings and 70.75% coverage. Ruff
  and `git diff --check` passed. No provider request or credential was used.
- A Finnhub live case remains blocked before transport until current reset
  evidence is supplied; this change does not promote routing or shadow mode.

## 2026-09-16 Alpha Vantage reset-boundary admission control

- Alpha Vantage's documented free-key allowance remains 25 requests/day, but
  the provider does not publish a reset boundary/timezone. Production defaults
  therefore remain explicitly fail-closed (`provider_defined` plus
  `requests_per_day_reset_boundary`) rather than inventing a rolling window.
- Commit `2f72ad2d6635750032a5f9cdd3aacf4e71bd62a1` adds the provider-specific
  `ALPHA_VANTAGE_REVIEWED_RESET` and `ALPHA_VANTAGE_QUOTA_EVIDENCE` controls,
  wires them through local/RPi Compose and the manual GitHub workflow, exposes
  the missing controls in diagnostics/live preflight, and promotes the seed
  only when the reset label is admission-safe and evidence is non-empty. This
  is configuration-only for future plan changes; no provider quota is guessed.
- Focused registry/quota/wiring coverage passed `152/152`; the complete backend
  unit gate passed `2,353/2,353` with 37 warnings and 70.73% coverage; Ruff and
  `git diff --check` passed. Tests made no external provider requests.
- The Alpha credentialed live case remains blocked before transport until an
  operator supplies current reset-boundary evidence; the workstream remains
  `ready_for_human_review`, not accepted for routing or shadow activation.

## 2026-09-16 Alpha Vantage weekly/monthly history coverage

- The Alpha Vantage adapter now uses the documented raw
  `TIME_SERIES_DAILY`, `TIME_SERIES_WEEKLY`, and `TIME_SERIES_MONTHLY`
  payloads. Daily requests retain the free `compact` 100-point completeness
  guard; weekly/monthly requests parse their native long-history series. All
  three reject adjusted requests before transport because the adjusted daily
  endpoint is premium-only.
- Implementation source `a6d430629` is the exact committed checkpoint for this
  change. The explicit Alpha Vantage usage profile continues to reserve one provider
  query for each history operation; no generic cost or quota was introduced.
  Provider fixture coverage passed `262/262`; the complete unit gate passed
  `2,352/2,352` with 37 warnings, and no provider request or credential was
  used. A bounded weekly/monthly live case remains a separate
  gate because the 25-requests/day reset boundary is still unpublished.

## 2026-09-16 exact-current full live preflight after Tiingo correction

- The current-source full provider runner at `feff096d8` completed its
  owner-ledger lock/health checks and stopped before transport with exit `2`,
  `0/0` cases, and zero provider requests. The redacted receipt is appended to
  `validation.jsonl`.
- Tiingo's daily/monthly reset correction is reflected in the preflight, but
  its unresolved unique-symbol/hourly boundaries and missing byte map still
  block its operations. Existing Alpaca, EODHD, Twelve Data, OpenFIGI,
  Binance, legal/source, deferred-provider, deployment-secret, universe, and
  shadow blockers remain explicit; no routing or shadow activation was implied.

## 2026-09-16 Tiingo reset-semantics correction

- Rechecked Tiingo's current primary documentation. The general API page
  explicitly states that hourly requests reset every hour, daily requests
  reset at midnight EST, and monthly bandwidth resets on the first day of each
  month at midnight EST. The pricing page confirms the Starter magnitudes:
  500 unique symbols/month, 50 requests/hour, 1,000/day, and 1 GB/month.
- The quota seed now uses `calendar_day_est` for the daily request pool and
  `calendar_month_est` for bandwidth. The unique-symbol monthly anchor and
  the hourly timezone/boundary remain explicitly unknown; no rolling window
  was inferred, so Tiingo remains non-routable until those two dimensions and
  the reviewed per-operation byte map are supplied.
- Focused provider quota coverage passed `102/102`; the fresh full backend unit
  replay at source `98002b309` passed `2,346/2,346` with 37 warnings. No
  provider request or credential was used. Sources:
  `https://www.tiingo.com/documentation/general` and
  `https://www.tiingo.com/about/pricing`.

## 2026-09-16 GitHub target-secret-store verification recheck

- `gh auth status` was rechecked from the feature worktree. The only installed
  GitHub session is `jagnelo-symbiotech`, and its token is invalid; the desired
  `jagnelo` owner session is not available to inspect the protected
  `provider-live-staging`/`provider-live-master` environments.
- No GitHub secret, variable, workflow, or repository state was mutated. The
  static workflow wiring remains validated locally, but target-store presence
  and values are still unverified until the owner authenticates `gh` as
  `jagnelo` (or supplies equivalent owner-authorized access).

## 2026-09-16 MarketData.app trial configuration verification

- The owner-managed local environment at `~/.config/charting-platform/app.env`
  contains the exact non-secret policy controls selected for the current key:
  `starter_trial`, `10000` daily credits, and the timezone-aware expiry
  `2026-10-11T18:09:00+01:00` (30 days from the supplied key-email time).
  `backend/.env.dev` remains a symlink to that external file; no secret values
  or environment contents were copied into Git.
- The provider-specific runtime contract was rechecked at the expiry boundary:
  the active trial reserves 10,000 credits/day, and at/after expiry the
  entitlement and quota reseed to Free Forever/100 credits/day. Paid-plan
  changes remain an explicit plan/limit configuration change and still require
  the separate paid-routing control.
- Focused quota/registry/coordinator coverage passed `163/163` with `--no-cov`,
  the workstream validator passed all 30 records, and `git diff --check`
  passed. This verifies the selected configuration and fallback contract; it
  does not promote unrelated providers or close the remaining legal, universe,
  target-secret-store, deployment, and shadow gates.
- A fresh backend unit replay at this documentation-only head passed
  `2,346/2,346` tests with 37 warnings. No external provider requests were
  made by that replay.

## 2026-09-16 exact-current native usage live evidence

- Alpaca's bounded credentialed `fetch_account_usage` manifest case passed
  `1/1` at current source `419e57c3c`, with one authenticated request. The
  response was parsed for the documented limit, remaining, and Unix reset
  headers and recorded in the redacted durable receipt.
- OpenFIGI's bounded keyless `fetch_account_usage` manifest case passed `1/1`
  at the same current source, with one mapping request. Its exact
  `ratelimit-limit`, `ratelimit-remaining`, and response-relative
  `ratelimit-reset` headers were reconciled to the anonymous mapping window.
- These are provider-specific transport and usage observations, not full
  routing admission: Alpaca's reset-window semantics remain unresolved and
  keyed OpenFIGI evidence still requires an API key. The broader provider,
  legal/source, universe, deployment-secret, and final shadow gates remain
  open. The complete backend replay for this commit passed `2,778` tests with
  `473` expected skips.

## 2026-09-16 native usage refresh at current source

- The existing provider-native usage paths for EODHD, Twelve Data,
  MarketData.app, and Binance each passed their exact focused manifest case
  `1/1` at source `7e96bc9a8` with one bounded request per provider. Redacted
  receipts are appended to `validation.jsonl`; no payloads or credentials were
  persisted.
- These observations refresh durable cross-session usage state only. EODHD's
  conflicting published minute limits and stale/current-date daily semantics,
  Twelve Data's separate daily pool, MarketData.app's configured trial expiry,
  and Binance's provider-specific weight window remain governed by their
  existing contracts; no new generic quota was inferred.

## 2026-09-16 current-head admission audit

- The current-head full-matrix preflight at source `221b1e2a` stopped before
  transport with `0/0` cases and zero provider requests. It continues to fail
  closed on provider-specific quota/baseline/reset contracts, unresolved live
  operation dispositions, legal/source controls (including Massive, Coinbase,
  FRED, xStocks, Bybit, Dinari, and FINRA OTC), byte/cost bounds, and the
  deployment/secret/universe/shadow gates.
- This receipt is safety evidence only. Passing the bounded native usage cases
  does not promote any provider beyond the exact dimensions they proved.

## 2026-09-16 Binance short-window live matrix

- A fresh native Binance weight snapshot was taken immediately before the
  provider matrix, then the bounded current-price/discovery/history cases ran
  successfully: `3/3` manifest cases passed at source `e511c15b7`.
- The matrix used four requests for the keyless ordinary history case, two for
  the reviewed 30-day daily case, and one native usage request. The result is
  current transport and weight-accounting evidence only; the one-minute native
  baseline is intentionally allowed to expire and must be refreshed before a
  later run.

## 2026-09-16 OpenFIGI short-window live matrix

- A fresh anonymous native mapping snapshot followed immediately by the
  bounded OpenFIGI matrix passed `3/3` at source `0b9accd5`: stable-identifier
  mapping, profile resolution, and account usage all completed successfully.
- The matrix stayed within the anonymous provider window and recorded only
  redacted request/usage evidence. Keyed-mode behavior remains separately
  fixture-covered and requires an operator-supplied OpenFIGI key for live
  evidence; no keyed limit is inferred from the anonymous run.

## 2026-09-16 MarketData.app current trial matrix

- The configured Starter Trial account's bounded provider matrix passed `7/7`
  at source `6dc03d90`: account usage, daily/five-minute candles, latest
  price, option expirations/chain, bounded historical option quotes, and the
  deliberate zero-request guard for unbounded response-priced history.
- The receipt recorded the provider's actual request/credit telemetry without
  persisting credentials or payloads. The trial expiry and Free Forever
  fallback remain configuration-driven; paid-plan changes still require an
  explicit plan/limit update.

## 2026-09-16 OpenFIGI native usage reconciliation

- OpenFIGI now exposes a bounded `fetch_account_usage` observation that uses
  one mapping job and requires the documented `ratelimit-limit`,
  `ratelimit-remaining`, and response-relative `ratelimit-reset` headers.
  Anonymous and keyed environments retain their distinct 25/minute versus
  25/6-second dimensions and job limits; no generic rate is inferred.
- The native observation is wired through the account-usage capability chain,
  durable baseline reconciliation, live manifest, and provider documentation.
  Missing/malformed headers fail closed, and the mapping request is charged as
  one OpenFIGI request.
- Focused OpenFIGI, quota-contract, and live-usage unit coverage passed
  `204/204`; the exact current-source keyless manifest account-usage run is
  recorded above, and the full backend replay passed `2,778` tests with `473`
  expected skips.

## 2026-09-16 documented FINRA ORF complete-source path

- The FINRA OTC adapter now supports the documented ORF complete-source pair:
  `EQUITYMASTERAC` (active issues) and `EQUITYMASTERIN` (inactive issues).
  ORF mode is selected explicitly with `FINRA_OTC_SOURCE_KIND=finra_orf_security_master`;
  it requires both HTTPS URLs on FINRA's `apidownload.finratrags.org` host with
  the exact `action=DOWNLOAD`, `facility=ORF`, and expected file query values.
- The adapter authenticates through the shared FINRA OAuth token cache, fetches
  both pipe-delimited files, validates required identifiers/statuses, preserves
  suffix/CUSIP/effective/inactive fields, rejects malformed rows and duplicate
  symbol/suffix keys, and returns both source URLs as completeness provenance.
  Legacy DAPI/OTC Markets parsers remain available only as separately reviewed
  source kinds; an active-only ORF file can never be treated as complete.
- Added explicit inactive URL/review settings and local/GitHub/RPi/Compose
  wiring, plus fixture coverage for the pair and fail-closed missing-pair/
  credential paths. Focused FINRA/registry/secret-wiring tests passed `71/71`
  (coverage instrumentation on a focused subset reports below the repository's
  55% global threshold; this is not the full-suite result); provider-runtime
  `54/54` and provider-admin/quota-contract `110` tests were replayed, with the
  quota expectation updated to the ORF-specific unknown entitlement/reset
  dimensions.
- No FINRA ORF request was made. The supplied public OAuth pair is not treated
  as proof of an ORF Web Access Agreement, product entitlement, or MFA. Routing
  remains fail-closed until those provider/terms/redistribution decisions and
  the two-file operation-cost/reset contract are explicitly configured.
- The current full live-matrix safety preflight stopped before transport with
  `0/0` cases and zero provider requests; its redacted receipt is appended to
  `validation.jsonl`. The remaining provider-specific quota/baseline, legal,
  live-operation, deployment-secret, and final shadow gates are unchanged.

## 2026-09-16 Alpaca native reset-header hardening and MarketData.app live proof

- Alpaca native quota observations now require a positive, parseable
  `X-RateLimit-Reset` epoch in addition to an exact reviewed limit and a
  valid remaining counter. Missing, malformed, or non-positive reset headers
  remain observation-only; this does not promote Alpaca's unresolved reset
  contract to routable status.
- Focused Alpaca reconciliation coverage passed `1/1`; Ruff and `git
  diff --check` passed. The complete backend unit suite passed `2,329/2,329`
  with 37 warnings and 70.69% coverage.
- The manifest-enforced MarketData.app focused live matrix passed `7/7`
  cases with `9` HTTP requests and `18,489` response bytes using the
  configured Starter Trial account (`10,000` daily credits through the
  configured 2026-10-11 expiry). Account usage, daily/five-minute candles,
  options, bounded option history, latest price, and the deliberate
  response-priced no-request guard all passed. The redacted receipt is in
  `validation.jsonl`; credentials and provider payloads were not persisted.
- An unqualified full pytest invocation was stopped after Testcontainers
  failed to access the local Docker socket (`PermissionError`). This is an
  environment blocker for the Docker-backed integration gate, not a unit or
  provider-live failure.

## 2026-09-16 exact-current preflight after Alpaca reset-header hardening

- At committed source `994114f3a`, the manifest full-matrix preflight exited
  `2` before transport with `0/0` cases and zero provider requests. It
  preserved the current provider-specific quota/cost/baseline blockers, the
  required legal/source/safety blockers, and the unresolved capability live
  dispositions. The owner-local durable ledger lock/health path passed.
- MarketData.app remains the only relevant provider with its reviewed account
  plan and option-chain controls currently routable; the full matrix remains
  intentionally fail-closed and the 30-day shadow phase remains disabled.

## 2026-09-16 native account-usage snapshots

- Dedicated manifest-enforced account-usage probes passed for Twelve Data,
  EODHD, and Binance (one request each; redacted receipts are in
  `validation.jsonl`). Twelve Data and EODHD observations were retained but
  did not widen routing because their other chargeable pools still lack an
  exact current baseline/reset proof. Binance's native weight observation
  successfully removed its prior active request-weight baseline blockers from
  the subsequent full preflight.
- The subsequent exact full preflight again stopped before ordinary provider
  transport with zero data-operation requests. This confirms that passing a
  native usage endpoint is not being misrepresented as complete provider
  acceptance; only the exact eligible Binance dimension changed state.

## 2026-09-16 Binance direct-range live coverage

- Added a manifest-backed direct `fetch_ohlcv` case for a bounded 30-day
  daily BTC-USD range. The case reserves exactly one Binance request weight
  for that one-page range and does not become a runtime cost default for
  arbitrary history windows.
- The Binance operation is now a required live operation rather than an
  unresolved full-range disposition. The first live execution showed the
  exact 30-day interval uses two pages, so the reviewed test bound is two
  request weights rather than one. Focused runner unit coverage passed
  `37/37`. After a just-in-time native one-minute baseline refresh, the
  corrected current-source live matrix passed `3/3` (keyless history,
  bounded daily history, and native account usage); the receipt is redacted
  and records the two-request bound without widening arbitrary-history costs.

## 2026-09-16 complete backend unit validation after Binance coverage

- The exact feature checkout passed the complete backend unit suite:
  `2,329 passed`, `37 warnings`, `70.69%` total coverage, in `191.53s`.
  This includes the live-runner manifest and Binance bounded-history
  regressions. No provider calls were made by the unit suite and no
  credentials or payloads entered Git.
- The unqualified integration suite remains environment-blocked when its
  Testcontainers setup cannot access the local Docker socket; this unit result
  does not claim Docker-backed or full-provider acceptance. Provider-specific
  quota/baseline, legal/source, universe, deployment-secret, and shadow gates
  remain open.

## 2026-09-16 Alpaca credentialed preflight

- The configured Alpaca paper credential was checked through the protected
  live runner with the owner-managed durable quota ledger. The run stopped
  before network access (`0/0` cases) because the reviewed provider contract
  still lacks admission-safe quota/baseline evidence for universe discovery,
  instrument events, OHLCV history, latest price, and profile operations.
- No Alpaca request or shared-key quota was consumed. The receipt is redacted
  in `validation.jsonl`; this is a confirmed fail-closed blocker, not a live
  transport failure. The implementation must not infer a 200/minute allowance
  from documentation alone without the required current reset/baseline proof.

## 2026-09-16 Dinari sandbox preflight

- The replacement Dinari sandbox key pair is recognized by the live runner,
  but all nine Dinari operations stopped before network access (`0/0` cases).
  Dinari publishes no numeric Sandbox request quota/reset or reviewed canary
  admission, so quota routing remains fail-closed; no request or sandbox
  allowance was consumed.
- The redacted receipt records both the unreviewed reset semantics and the
  missing canary admission. This is an explicit provider-specific blocker,
  not an integration-success claim.

## 2026-09-16 workflow validation note

- The repository `make branch-validate` wrapper could not start because this
  macOS host has not accepted the Xcode/Apple SDK license (`xcodebuild`
  exit `69`). The underlying workstream validator was run directly with the
  feature checkout's Python environment and passed: `30` workstream records
  validated. Ruff, compilation, and `git diff --check` also passed.

## 2026-09-16 Alpaca native usage bootstrap

- Alpaca now exposes a provider-native `fetch_account_usage` observation using
  one bounded latest-bar request and the exact `X-RateLimit-Limit`,
  `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers. The application
  permits this observation through an explicit bootstrap-only concurrency
  lease; ordinary Alpaca data operations remain non-routable while the
  provider-defined reset boundary is unresolved.
- Focused unit/runtime/live-runner coverage passed (`484` focused unit tests
  before the final full-suite replay). The first live attempt correctly
  rejected a response whose reset epoch elapsed during transport; the parser
  now validates against request start time. The corrected protected live run
  passed `1/1`, one request and 118 response bytes. The redacted receipt is in
  `validation.jsonl`; no credentials or payloads entered Git.
- The native header snapshot is intentionally observation-only and was not
  reconciled into a durable ordinary-routing baseline. This preserves the
  fail-closed policy until Alpaca's reset-window semantics are explicitly
  reviewed.

- At committed source `4d1ed8622`, the just-in-time native usage refresh and
  expanded Binance matrix both passed. The matrix covered latest history,
  direct 30-day daily history, current price, universe discovery, and native
  request-weight usage (`3/3` cases; the receipt is in `validation.jsonl`).
  The direct range consumed two measured HTTP pages, matching the reviewed
  bound; no arbitrary-range cost was inferred.

## 2026-09-16 exact-current preflight after Alpaca history contract

- At committed source `0220ae07e`, the owner-local durable-ledger preflight
  stopped before transport with exit `2`, `0/0` cases, and zero provider
  requests. The coordinator health/locking path passed; the receipt is
  appended to `validation.jsonl`.
- The report remains `94` provider-specific quota/cost/baseline blockers,
  `7` required live capability-safety blockers, and `22` unresolved
  capability dispositions. The new Alpaca fixed history start changes only
  bounded history admission; it does not bypass the unresolved quota baseline
  or legal/terms controls.
- This is current fail-closed safety evidence only, not provider transport
  acceptance, routing activation, deployment authorization, or shadow-run
  authorization.

## 2026-09-16 Alpaca fixed historical-start contract

- Alpaca's official Basic market-data plan publishes US stock/ETF historical
  data since 2016. The entitlement now records the fixed
  `earliest_date=2016-01-01` bound, and both normal history routing and
  epoch-style bulk hydration use the shared parser. The implementation does
  not convert that published calendar start into a drifting relative-years
  approximation.
- Missing, malformed, future, mixed, and ambiguous bound forms remain
  fail-closed. Focused routing/bulk coverage passed `43/43` and Ruff passed.
  No provider calls or credentials were used; Alpaca quota-reset/baseline,
  entitlement/terms, and exact-source transport gates remain open.

## 2026-09-16 exact-current preflight after `per_dimension` hardening

- At committed source `620b96701`, the owner-local durable-ledger
  preflight stopped before transport with exit `2`, `0/0` cases, and zero
  provider requests. The receipt is appended to `validation.jsonl`; the
  coordinator health/locking path passed.
- The report contains `94` provider-specific quota/cost/baseline blockers,
  `7` required live capability-safety blockers, and `22` unresolved
  capability dispositions. `per_dimension` is now explicitly reported as an
  unresolved reset when a chargeable dimension lacks its own boundary, while
  the intentional account-usage bootstrap exclusion remains zero-cost.
- This is current fail-closed safety evidence only. It does not establish
  provider transport acceptance, legal/source admission, deployment-secret
  verification, routing activation, or shadow-run authorization.

## 2026-09-16 `per_dimension` reset admission and preflight classification

- A `per_dimension` root reset is now treated as a meta-label, not as a
  calculable rolling or epoch window. Each chargeable dimension must provide
  its own explicit admission-safe reset; otherwise runtime and direct live
  reservations fail closed. Account-usage bootstrap may still explicitly
  exclude an unknown pool as zero-cost, without inventing a window.
- The live-runner preflight now converts unresolved reset errors into a
  provider-specific blocker and preserves the before-network stop, so missing
  credentials and quota-contract gaps are reported together rather than
  escaping as an exception.
- Focused quota/runner tests and Ruff pass. The complete backend unit gate
  passes `2,326/2,326` with 70.68% coverage and 37 warnings. No provider calls
  or credentials were used. A new exact-source safety preflight remains
  required after this source is committed.

## 2026-09-16 exact-current preflight after unresolved-reset hardening

- At committed source `92ee86fd1`, the owner-ledger lock-protected full
  provider runner stopped before transport with exit `2`, `0/0` cases, and
  zero provider requests. The coordinator health/locking path passed; the
  exact receipt is appended to `validation.jsonl`.
- The report contains `94` provider-specific quota/cost/baseline blockers,
  `7` required live capability-safety blockers, and `22` unresolved capability
  dispositions. Finnhub now reports its unresolved minute reset boundary
  explicitly rather than treating a usage baseline as sufficient.
- MarketData.app account-plan and option-chain controls remain the only
  relevant routing controls reported routable. This is fail-closed safety
  evidence, not transport acceptance, deployment authorization, routing
  activation, or shadow-run authorization.

## 2026-09-16 unresolved reset labels now fail closed in every reservation path

- The quota contract now distinguishes an auditable `provider_defined` label
  from an admission-safe calculable reset. Unresolved provider-defined,
  provider-defined-daily, composed provider-defined, and rolling-or-provider-
  defined labels cannot become rolling or epoch buckets in either runtime
  reservations or direct live-probe reservations.
- Explicit dimension-level calendar/fixed/rolling resets remain usable even
  when a parent contract is `per_dimension` or provider-defined. Admins may
  still store unresolved contracts as unverified review state, but routing and
  live transport remain fail-closed and diagnostics retain their dimensions.
- Focused quota coverage passed `101/101`; the full backend unit gate passed
  `2,324/2,324` with 70.68% coverage and 37 warnings. Ruff, diff, and
  workstream validation passed. No provider calls or credentials were used.

## 2026-09-16 exact-current safety preflight after quota-reset documentation correction

- At committed source `da65066bc`, the owner-ledger lock-protected full
  provider runner stopped before transport with exit `2` and zero provider
  requests. The coordinator health/locking path passed, and the receipt is
  appended to `validation.jsonl`.
- The report contains `99` provider-specific quota/cost/baseline blockers,
  `7` required live capability-safety blockers, and `22` unresolved capability
  dispositions. FINRA, Tiingo, and FMP now consistently describe unresolved
  provider-defined reset dimensions instead of local rolling substitutes.
- MarketData.app account-plan and option-chain controls remain the only
  relevant routing controls reported routable. This is current fail-closed
  safety evidence, not provider transport acceptance, deployment authorization,
  routing activation, or shadow-run authorization.

## 2026-09-16 exact-source safety preflight after reset correction

- At committed source `427579521`, the owner-ledger lock-protected full
  provider runner stopped before transport with exit `2` and zero provider
  requests. The receipt is appended to `validation.jsonl`; coordinator
  health/locking passed.
- The current report contains `99` provider-specific quota/cost/baseline
  blockers, `7` required live capability-safety blockers, and `22` unresolved
  capability dispositions. FINRA now fails explicitly on its unknown monthly
  byte reset boundary rather than being admitted under a rolling approximation;
  Tiingo remains blocked on its explicit reset dimensions and byte map.
- MarketData.app account-plan/option-chain controls remain the only relevant
  routing controls reported routable in this full preflight. This is current
  fail-closed safety evidence, not transport acceptance or routing/shadow
  activation.

## 2026-09-16 provider-defined reset correction for FINRA and Tiingo

- FINRA's public credential allowance is documented as 10 GB/month and the
  credential is disabled until the first day of the following month, but the
  provider does not publish the reset timezone or byte convention. The quota
  contract now records `provider_defined` plus an explicit
  `download_bytes_month_reset_boundary` unknown dimension; the prior rolling
  31-day approximation is removed.
- Tiingo's daily request and monthly bandwidth pools now record the exact
  `calendar_day_est`/`calendar_month_est` boundaries stated by its general API
  documentation. Its distinct-symbol monthly anchor and hourly
  timezone/boundary remain explicitly unknown; the durable identity ledger
  does not present a guessed rolling 31-day symbol window or estimated hourly
  boundary.
- Production routing remains fail-closed for these dimensions. Focused quota
  coverage passed `100/100`; focused runtime/registry coverage passed
  `76/76`; Ruff, diff, and workstream validation passed. The complete
  isolated backend unit gate passed `2,324/2,324` with 70.66% coverage and 37
  warnings at the dirty implementation source.
- Runtime settlement tests use an explicit reviewed UTC test fixture only to
  exercise monthly byte accounting; this does not alter the production seed
  or promote FINRA/Tiingo routing.

## 2026-09-16 exact-source full-matrix safety preflight after Alpha correction

- At committed source `6e9df43bb`, the lock-protected full provider runner
  stopped before transport with exit `2`: `0/0` cases and zero provider
  requests. Owner-local durable-ledger health/locking succeeded; the receipt
  is appended to `validation.jsonl`.
- The current report contains 101 provider-specific quota/cost/baseline
  blockers, 7 required live capability-safety blockers, and 22 unresolved
  capability dispositions. It also preserves the three user-deferred
  providers and the MarketData.app-specific routable account-plan control.
- The Alpha Vantage reset-boundary correction is now reflected in this
  current-source report. This is fail-closed safety evidence only; it does
  not promote routing, authorize deployment, or start shadow monitoring.

## 2026-09-16 exact-source Alpha Vantage/unit validation

- The complete isolated backend unit suite passed `2,324/2,324` at exact
  source `ee10f89dd`, with 70.67% total coverage against the configured 55%
  threshold and 37 warnings in 134.48 seconds.
- The run includes the stricter Alpha Vantage reset-boundary contract and its
  reviewed-fixture runtime regression: production remains fail-closed when
  the provider's daily reset boundary is unpublished, while the test fixture
  explicitly supplies a reviewed reset only to exercise the raw-vs-adjusted
  capability filter.
- This is application/unit evidence only. It does not provide provider
  transport acceptance, active quota baselines, source/legal/universe
  admission, target secret-store verification, or permission to integrate,
  deploy, activate routing, or start the final shadow phase.

## 2026-09-16 Alpha Vantage reset-boundary correction

- Alpha Vantage publishes the free-key 25-requests/day allowance but does not
  publish a reset timezone/boundary. The quota seed now records
  `reset=provider_defined` plus the explicit
  `requests_per_day_reset_boundary` unknown dimension instead of presenting a
  local rolling 24-hour window as provider truth.
- This is deliberately stricter: the existing typed daily-capacity response
  handling remains intact, but Alpha Vantage daily-capacity routing stays
  fail-closed until a current reset-bearing observation or provider-confirmed
  boundary is recorded.

## 2026-09-16 exact-current OpenFIGI/full-matrix preflight

- The lock-protected full provider runner at source `467b755dd` exited `2`
  before transport with zero provider requests. The owner-local durable
  ledger health/lock/write path passed, then the runner preserved the current
  provider-specific baseline, capability, legal/source, byte, and deferred
  provider blockers. The new OpenFIGI contract is therefore represented in
  current diagnostics without spending the anonymous pool.
- Routing safety still reports the configured MarketData.app account-plan and
  option-chain controls as routable; all other unresolved controls remain
  fail-closed. This receipt is safety evidence, not live acceptance or
  routing/shadow activation.

## 2026-09-16 OpenFIGI keyed/anonymous quota contract audit

- Current official [OpenFIGI documentation](https://www.openfigi.com/api/documentation) distinguishes anonymous and keyed
  mapping traffic: anonymous is limited to 25 requests/minute and five
  jobs/request; keyed mapping is 25 requests/6 seconds and 100 jobs/request.
  Native `ratelimit-limit`, `ratelimit-remaining`, and `ratelimit-reset`
  headers are preserved, and HTTP 429 denotes an exhausted window.
- The runtime seed now selects the exact anonymous IP-scoped contract when
  `OPENFIGI_API_KEY` is empty and the exact API-key-scoped six-second contract
  when it is configured. The keyed path intentionally does not synthesize a
  legacy per-minute token bucket; durable reservations enforce the published
  six-second window. Focused contract coverage verifies both paths.
- No OpenFIGI credential was added or exposed; the existing bounded keyless
  live matrix remains the only external transport evidence.
- At exact committed source `b0eab25e1`, the complete isolated backend unit
  gate passed `2,324/2,324` with 70.67% coverage and 37 warnings. This
  validates the keyed/anonymous contract change but does not create
  credentialed OpenFIGI evidence or close the broader live, legal, universe,
  deployment-secret, and shadow gates.

## 2026-09-16 exact-current coordinator-backed safety preflight

- At source `13585d253`, the live runner was replayed with owner-local access
  to the durable quota ledger. The coordinator health/lock/write check passed;
  the earlier sandbox-only `readonly database` result was environmental and
  is not provider evidence.
- The runner then stopped before transport with exit `2` and zero provider
  requests. It preserved the current provider-specific baseline/contract
  blockers, unresolved capability dispositions, and legal/source/byte gates;
  MarketData.app account-plan/option-chain controls were the only relevant
  routing controls reported routable. The full matrix remains incomplete and
  no provider routing or shadow phase is activated.

## 2026-09-16 Tiingo account-usage endpoint verification

- Tiingo's current official general/pricing documentation confirms the Starter
  request and bandwidth pools but does not document a machine-readable usage
  response. The older provider blog mentions `/account/usage`; a bounded
  authenticated probe at the current source time returned `301` to
  `https://www.tiingo.com/account/usage`, then `404 Not Found` after following
  the redirect.
- No data endpoint was called and no usage counter was inferred. The adapter
  therefore remains unchanged: Tiingo's daily and monthly-bandwidth reset
  anchors are now represented from the current documentation, while the
  500-unique-symbol pool and hourly boundary still have no current native
  account snapshot or confirmed reset anchor and remain fail-closed. This is a
  negative live-validation result, not acceptance evidence.

## 2026-09-16 Marketstack usage-semantics audit

- Current official Marketstack pricing/FAQ/overage sources still do not state
  the monthly reset timestamp, so the 100-request/month seed remains
  fail-closed with `monthly_cap_reset_boundary` unknown. No live request was
  made and no routing admission was widened.
- The quota contract now records the provider-specific semantics that must not
  be reduced to a generic request counter: a multi-symbol request consumes one
  request per ticker, API errors are not counted, notifications occur at 75%,
  90%, and 100%, and the account may permit a 5% overdraft/120% disable rule
  when overage billing is not enabled. These are audit metadata only; the
  account's overage setting and reset boundary remain operator/provider review
  gates.
- Focused quota-contract tests passed `99/99`; the complete backend unit gate
  then passed `2,322/2,322` with 70.65% coverage, Ruff passed, and the
  workstream validator passed. No frontend or ETF provider adapter file
  changed. This is documentation/contract evidence only and does not promote
  Marketstack routing.

## 2026-09-16 CoinGecko exact-source preflight

- At source `40801db55`, the selected CoinGecko live runner stopped before
  network access with exit `2`. The corrected contract was accepted; the only
  provider-specific blockers were the two exact active Demo-key baselines
  (`calls_per_minute` and `calls_per_month`). No provider request or shared
  quota was consumed. The redacted receipt is appended to
  `validation.jsonl` and confirms the remaining gap is account evidence, not
  an invented reset boundary.

## 2026-09-16 CoinGecko monthly reset contract correction

- Current official CoinGecko pricing/support documentation explicitly states
  that monthly call credits reset on the first day of each month, regardless
  of billing date. The contract now records `calendar_month_utc` for the
  10,000-call Demo pool and no longer marks that reset dimension unknown.
- The official `/key` usage endpoint remains Pro-only; the earlier bounded Demo
  request returned HTTP 401 error `10005`. Therefore the monthly reset contract
  is now exact, but the active Demo account baseline is still required before
  routing and no usage counter is inferred.
- Quota-contract regression coverage passed `99/99`; no provider request was
  made for this documentation-driven correction and no frontend or ETF adapter
  file changed.

## 2026-09-16 current-source native usage refresh

- The four supported native account-usage probes were replayed separately at
  exact source `ea42ce3dcade07fb0744e9a176dc0d2924857b6a`: MarketData.app,
  Twelve Data, EODHD, and Binance each passed `1/1` through the normal lock,
  reservation, telemetry, and redacted receipt path. Four provider requests
  were made; no payloads or secrets entered Git.
- The durable owner-local ledger now has fresh reconciled observations for
  MarketData.app (`credits_per_day`, limit 10,000, used 0), Twelve Data
  (`credits_per_minute`, limit 8, used 1), and Binance
  (`request_weight_per_minute`, limit 6,000, used 1). EODHD still reports a
  stale daily usage date, so its daily pool remains observation-only rather
  than being fabricated as current.
- These focused receipts establish provider-native usage evidence only; they
  do not activate the other provider capabilities. The broader matrix still
  requires the remaining exact baselines, safety/legal/source controls,
  universe reconciliation, secret-store verification, and final shadow gate.

## 2026-09-16 current full-matrix fail-closed preflight

- At exact committed source `f52bfd9e0`, the lock-protected full provider
  runner exited `2` before transport. It recorded the fresh Binance native
  account-usage baseline as expired by the time the broader matrix began;
  this is the intended fixed-minute behavior, not a fabricated zero-usage
  assumption. The focused Binance snapshot remains the only valid baseline
  proof for that short active window.
- The preflight also preserved the existing provider-specific blockers:
  unknown active pools for Alpaca, Alpha Vantage, Bybit, Coinbase, EDGAR,
  EODHD, Finnhub, FINRA, Kraken, OpenFIGI, Nasdaq, Twelve Data, xStocks and
  others; unresolved capability dispositions; and legal/source/byte controls
  for Massive, FRED, Coinbase, tokenized venues, FINRA OTC, Tiingo and FMP.
  It made zero provider requests and consumed no shared-key quota. The
  redacted receipt is appended to `validation.jsonl`.

## 2026-09-16 Binance native account-usage completion

- Binance now has a provider-specific `fetch_account_usage` adapter using the
  documented public `/api/v3/time` probe and native `X-MBX-USED-WEIGHT-1M`
  telemetry. The adapter validates the counter, rejects missing or malformed
  capacity state, maps the fixed UTC-minute reset, and preserves typed 418/429
  capacity failures; it never invents a request allowance from an empty local
  ledger.
- The reviewed `request_weight_per_minute=6000` contract and a separate
  deployment-scoped serialized bootstrap slot are wired through config,
  reservations, routing diagnostics, and the native-baseline allow-list. The
  successful snapshot reconciles the durable owner-local ledger as
  `limit=6000`, `used=1`, `remaining=5999` at 2026-09-16 13:25 UTC.
- The corrected exact-source focused runner passed Binance account usage
  `1/1` at source `f031e8e1f`; it made one public request, persisted one
  redacted ledger receipt, and skipped unrelated deferred OHLCV disposition
  checks by explicit `--account-usage-only` scope. The earlier source
  `e68d8e424` receipt remains recorded as an intentionally superseded runner
  pre-fix `missing_live_evidence` result, not as acceptance evidence.
- Full backend units pass `2,322/2,322` with 70.66% coverage and 37 warnings;
  no frontend or ETF-provider adapter file changed. This closes Binance's
  account-usage-baseline gap only. The full provider matrix, other
  provider-specific quota/legal/source gates, universe reconciliation,
  target-owned secret stores, and final shadow phase remain open.

## 2026-09-16 direct live account-usage baseline handoff

- Closed a validation/accounting gap in the direct live-test path. The
  MarketData.app and Twelve Data account-usage cases now pass their exact
  provider-native snapshots through the production `_native_baseline_candidate`
  allow-list and durable `reconcile_provider_quota_baseline` coordinator after
  the live reservation settles. A successful usage read therefore survives the
  process and can admit the next run; it does not rely on the external JSONL
  receipt as quota authority.
- The EODHD case uses the same handoff but remains observation-only when
  `apiRequestsDate` is stale, so no current daily window is fabricated. Unit
  coverage verifies both the exact reconciliation and the stale/unproven path.
- Focused live checks with the configured local credentials passed: MarketData.app
  account usage `1/1` and Twelve Data account usage `1/1`. The durable
  coordinator now reports MarketData.app's active Starter Trial `10,000`
  credits/day baseline and Twelve Data's reviewed `8` credits/minute baseline.
  These are focused provider-account proofs, not full-matrix acceptance; the
  current worktree was dirty during those runs, so exact-source receipts must
  be replayed after commit.

## 2026-09-16 committed-source account-usage revalidation

- At committed source `8176e820ae11013409602aa2a2ec1f0045d3157b`, the focused
  MarketData.app, Twelve Data, and EODHD account-usage cases each passed `1/1`
  through the normal live runner, local exclusive lock, durable coordinator,
  and redacted external usage ledger. MarketData.app and Twelve Data exercised
  the new durable native-baseline handoff; EODHD exercised the stale-date
  observation-only branch. No provider payloads or secrets entered Git.
- These are exact-source focused proofs only. The full matrix remains blocked
  before transport by unresolved provider-specific quota baselines/contracts,
  legal/source controls, deferred providers, and response-byte maps recorded in
  the plan; this run does not promote routing or authorize deployment/shadow.

## 2026-09-16 current full-matrix safety preflight

- At committed source `c6b7b42de`, the normal lock-protected full provider
  runner stopped before transport with exit `2`. It preserved the exact
  provider-by-provider blockers instead of spending credentials under unknown
  active-window, byte, cost, source, or legal controls. No provider request was
  issued by this run.
- The durable receipt records the three intentional user deferrals (Tradier,
  IBKR, and Ondo), unresolved finite-pool baselines (including EODHD's stale
  daily account date and Twelve Data's naturally expired minute window), and
  the remaining source/terms/jurisdiction controls for FINRA OTC, FRED,
  Massive, Coinbase, xStocks, Bybit, and tokenized venues. This is current
  fail-closed evidence, not a provider failure or acceptance result.

## 2026-09-16 current isolated backend unit replay

- At branch source `64c81f3be`, the complete isolated backend unit suite passed
  `2,319/2,319` in 181.62 seconds, with 70.66% total coverage against the
  configured 55% threshold and 37 warnings. This replays the application code
  after the usage-accounting changes; it is not PostgreSQL/Redis integration,
  external-provider acceptance, deployment, or shadow-run evidence.

## 2026-09-16 current native account-usage refresh

- At source `cf934faa6`, the bounded EODHD and Twelve Data account-usage cases
  each passed `1/1` through the normal runner and durable coordinator. The
  Twelve Data snapshot reconciled a fresh `credits_per_minute=8` baseline
  (`used=1`) for the current fixed-minute window. EODHD returned a valid
  observation but still did not reconcile its daily pool because the provider
  date remains stale; no daily limit was fabricated.
- These runs made two authenticated requests total and recorded only redacted
  receipts. The full matrix remains separately blocked by unresolved
  provider-specific controls.

## 2026-09-16 current isolated unit gate

- The complete backend unit suite passed `2,317/2,317` at source
  `9171f39e6a6c9945273663fa5430a3ada4dabc54` in 2m49s, with 37 warnings
  and 70.66% total coverage (the configured 55% threshold was met). This
  revalidates the current branch after the provider-policy, live-evidence,
  and documentation checkpoints; it is not PostgreSQL/Redis integration or
  external-provider acceptance evidence.

## 2026-09-16 EODHD current account-usage recheck

- The focused native EODHD account-usage case passed `1/1` at source
  `a9a8ea7f8de464cb3d0b4ae11f79eacd25613031`; the redacted receipt records one
  request and 304 response bytes. A same-time bounded `/api/user` inspection
  returned `subscriptionType=free`, `apiRequests=3`,
  `apiRequestsDate=2026-09-15`, and `dailyRateLimit=20`. The date is still
  stale relative to the current UTC date, so the runtime correctly keeps the
  daily baseline observation-only and does not seed a current `calls_per_day`
  window. No provider limit was widened and no extra history request was made.

## 2026-09-16 current-source credentialed revalidation

- MarketData.app passed its bounded current-source matrix `7/7` at source
  `a2ff6293ad082c8b6e91ca480bf08379d9521d17`, including account usage,
  latest price, intraday candles, option expirations/chain, historical option
  quote data, and the explicit no-request response-priced-history policy. The
  redacted receipt records nine upstream HTTP requests and 17,241 response
  bytes; no provider payload or secret entered Git. This is transport and
  usage evidence only; the existing plan/terms and paid-routing controls stay
  separate.
- The same-source Alpaca and SEC EDGAR runs correctly stopped before network
  access because the durable provider-specific active-window baselines are
  unknown; the Dinari Sandbox run stopped before network access because its
  provider-defined quota/reset and canary admission are not established. The
  receipts preserve these as explicit safety preflights, not passing data
  reads and not reasons to invent a rate limit.

## 2026-09-16 CoinGecko Demo usage-endpoint audit

- The official CoinGecko `/key` account-usage endpoint was probed once with
  the owner-managed Demo credential. It returned the provider's documented
  HTTP 401 / error code `10005` because the endpoint is restricted to Pro
  subscribers. No monthly usage baseline or reset timestamp can therefore be
  obtained from this Demo key; no fabricated counter, reset, or routing quota
  was added. The checked-in contract continues to record 100 calls/minute and
  10,000 calls/month with an unknown monthly reset boundary, so the monthly
  pool remains fail-closed. This is one bounded transport/policy observation,
  not routing activation or acceptance evidence; no frontend or ETF-provider
  adapter file changed.

## 2026-09-16 Alpha Vantage compact-history completeness guard

- Alpha Vantage's free `TIME_SERIES_DAILY` `compact` response is capped at the
  latest 100 daily observations. The adapter now parses the returned dates
  before normalization and raises a typed provider error when a full-size
  compact response does not reach the requested start. This prevents a
  bounded history read from silently persisting a partial range; routing may
  fall back to another eligible provider or surface the explicit gap.
- Focused Alpha Vantage provider coverage passed `29/29`. The change does not
  alter the reviewed 25-requests/day contract, adjusted-history restriction,
  or any provider routing entitlement. No live request was made and no
  frontend or ETF-provider adapter file changed. The complete isolated backend
  unit suite passed `2,317/2,317`; the live runner then blocked before network
  because Alpha Vantage's current daily usage baseline is not known.

## 2026-09-16 account-usage focused live validation

- The orchestrated clean-source focused EODHD account-usage case passed `1/1`
  at source `7aedd03aa98f959719a507aa5c2be7acaddeaf42`; one HTTP request and
  304 response bytes were recorded in the redacted durable receipt. The
  provider's stale daily date remains observation-only, so no current daily
  baseline was fabricated.
- The equivalent Twelve Data case passed `1/1` at source
  `3c890905113f9c3d29f3e84e1c25f34e30030bd4`; one HTTP request was recorded.
  The live response returned valid minute-credit headers but omitted the
  optional plan body field; the adapter preserves that as `None` rather than
  guessing the plan.
- Both runs used `--account-usage-only` through the normal runner, with the
  durable coordinator, exclusive live lock, configured credentials, same-run
  evidence correlation, and redaction controls. These are focused native
  usage proofs, not full provider capability or routing-activation evidence.

## 2026-09-16 provider-native account-usage bootstrap hardening

- Twelve Data and EODHD account snapshots now have an explicit,
  provider-declared bootstrap path. If a finite provider pool has no active
  durable baseline, the first `fetch_account_usage` reservation excludes only
  that unknown pool and reserves a deployment-scoped serialized probe slot;
  it never treats the unknown provider allowance as zero or invents a rate.
- Operation-scoped quota dimensions are now supported throughout runtime,
  application reservations, and direct live-probe reservations. Once a native
  snapshot reconciles a pool, subsequent account snapshots charge the normal
  reviewed provider cost. Malformed, stale, or unavailable baseline state
  remains fail-closed.
- Added regression coverage for both providers, direct live preflight plans,
  operation-scoped dimensions, and normal-read exclusion. The complete
  isolated backend unit suite passed `2,316/2,316`; focused quota/runtime
  coverage passed `198/198`; Ruff, compile, and diff checks passed.
- Updated `docs/data-providers.md` and `docs/provider-live-validation.md` to
  distinguish the local bootstrap safety slot from provider entitlement and to
  explain the native-baseline handoff. No provider request, deployment,
  routing activation, frontend change, or ETF-provider adapter change was made
  in this checkpoint.
- Added the runner's `--account-usage-only --provider <marketdata_app|twelve_data|eodhd>`
  mode so a safe native snapshot can be live-validated without preflighting
  unrelated provider operations that are still baseline-gated. The mode is
  explicitly focused and cannot produce a full-matrix receipt; runner tests
  pass `37/37`.

## 2026-09-16 exact-source receipts after reset hardening

- Replayed the bounded MarketData.app suite at source
  `fb8fc4a6737eb257a6f9766d1e3a0c433bf183dc`; all `7/7` selected cases passed
  and the runner settled usage through the shared durable local coordinator.
- Replayed the EODHD selected-provider preflight at the same source; it exited
  `2` before transport because both EODHD active pools still lack exact current
  baselines. The redacted receipt also preserves the unrelated safety gates.
- These receipts supersede earlier non-current-source live evidence. No
  additional EODHD request was made by the preflight, and no deployment,
  routing activation, frontend, or ETF-adapter change occurred.

## 2026-09-16 provider reset-boundary hardening

- Alpaca and Massive now retain their published per-minute ceilings (200 and
  5 respectively) but no longer encode `rolling_or_provider_defined`, which
  the runtime could interpret as rolling. Each contract records its unresolved
  reset boundary explicitly and remains non-routable until exact active-window
  evidence is admitted. Alpaca's response-header reconciliation remains
  available; this change does not invent a reset or alter provider adapters.
- Provider catalog rows now state the unresolved reset semantics and the
  resulting routing gate. Added regression coverage for both contracts and
  updated the Alpaca live-evidence test to ensure transport success cannot
  override the unresolved contract.
- Focused quota/runtime tests passed `150/150`; the complete isolated backend
  unit suite passed `2,312/2,312` with 37 warnings. No provider request,
  deployment, frontend change, or ETF-provider adapter change occurred.

## 2026-09-16 current-source MarketData.app live receipt

- The bounded credentialed MarketData.app matrix passed `7/7` at source
  `b022e8762180d0dcb4f46ead3f75de17dcf897f7` using the shared owner-managed
  environment and durable local quota ledger. The run covered account usage,
  latest price, intraday candles, option expirations/chain, historical option
  quote data, and the explicit no-request response-priced-history policy.
- The runner recorded the redacted reservation-linked receipt and measured
  transport usage. The provider's response-priced historical option path
  remains intentionally non-routable without a reviewed hard result/credit
  ceiling. No other provider was selected, and no frontend, ETF adapter,
  deployment, or routing activation changed.

## 2026-09-16 exact-source EODHD preflight receipt

- Replayed `scripts/run-live-provider-probes.py --provider eodhd` at source
  `9d407fc40825d85562c79d12de3e410763aa1dd9` with the pinned backend
  virtualenv and owner-managed environment. It exited `2` before transport;
  the receipt records all ten EODHD cases blocked on the two unknown active
  pools (`requests_per_minute` and `calls_per_day`). No additional provider
  request was made by the runner.
- The same receipt preserves unrelated routing-safety blockers (FINRA/FRED/
  Coinbase/tokenized terms, response-byte maps, and deferred provider controls)
  rather than misclassifying them as EODHD failures. The redacted JSONL receipt
  is committed with this checkpoint.

## 2026-09-16 EODHD native-usage observation

- Performed one bounded credentialed `GET /api/user` call using the existing
  owner-managed key. The redacted response was HTTP 200 with
  `subscriptionType=free`, `apiRequests=3`, `apiRequestsDate=2026-09-15`,
  `dailyRateLimit=20`, and headers `X-RateLimit-Limit=1200`,
  `X-RateLimit-Remaining=1199`.
- The daily usage date is stale relative to the current UTC date, so the
  runtime correctly refused to seed a current `calls_per_day` baseline. The
  observed 1,200/minute header also does not widen the reviewed 20/minute
  contract while official plan documentation conflicts. EODHD therefore
  remains baseline-gated and no subsequent EODHD live operation was attempted.
- Updated the operator procedure to accurately list EODHD daily and Twelve
  Data minute native-baseline reconciliation alongside MarketData.app. The
  provider call was not persisted as a quota baseline or treated as a live
  pass; no secret or raw payload was recorded.

## 2026-09-16 EODHD conflict-scope correction and unit replay

- Narrowed the EODHD conflict handling after the first full unit replay showed
  that a provider-level `unknown_dimensions` marker would incorrectly disable
  the separately reviewed daily/history paths. The contract now records the
  source conflict and retains the documented Free Starter 20/minute ceiling as
  the conservative reviewed value; it does not admit the broader 1,000/minute
  claim or invent a replacement limit.
- Focused regression coverage passed `100/100`; the complete isolated backend
  unit suite passed `2,311/2,311` with 37 warnings. Ruff, compilation, and diff
  checks passed. The default integration-enabled pytest command could not
  start its Redis/Testcontainers fixtures because the local Docker socket is
  unavailable to this sandbox; the previously recorded Docker-backed gate is
  unchanged and remains the authoritative integration evidence.
- No provider request, routing activation, deployment, frontend change, or ETF
  provider-adapter change occurred.

## 2026-09-16 EODHD published-limit conflict hardening

- Recorded the official EODHD conflict directly in the provider quota contract:
  the historical-plan page publishes 20 requests/minute while the general
  limits page claims 1,000 requests/minute for every plan.
- The runtime keeps the lower 20/minute value as the conservative reviewed
  ceiling and records both source URLs and the conflicting claim. The daily
  20-call GMT-reset pool remains separately represented and is not affected by
  this minute conflict; the broader 1,000/minute claim is not admitted.
- Updated the provider-live-validation procedure and contract regression
  assertions. Focused quota-contract tests passed `98/98`; Ruff, compilation,
  and diff checks passed. Commit: `bf3235c2d`.
- No provider request, routing activation, deployment, frontend change, or ETF
  provider-adapter change occurred.

## 2026-09-16 EODHD account-usage integration checkpoint

- Added the documented EODHD `/user` account-usage adapter. It retains the
  daily `apiRequests`/`dailyRateLimit` counters as a named `calls_per_day`
  dimension, records matching `X-RateLimit-Limit`/`Remaining` headers as a
  separate minute dimension when present, and never invents a reset timestamp
  for a stale reported usage date.
- EODHD is now included in the explicit `account_usage` capability chain; the
  operation remains opt-in and baseline-gated, so merely configuring the key
  cannot cause an unreviewed usage poll or data route.
- Native daily baseline reconciliation is allow-listed only when the returned
  date is the current UTC date, the next-midnight-GMT reset is explicit, and
  the limit matches the reviewed contract. The unresolved official 20 versus
  1,000 requests/minute conflict remains conservative and fail-closed.
- Focused adapter, account-usage, quota-contract, live-manifest, secret-wiring,
  and runner checks passed (`196` tests total); Ruff and diff checks pass. The
  new live case is manifest-covered but was not executed because the current
  EODHD account baseline remains unavailable. No frontend, ETF adapter,
  deployment, or routing activation changed.

## 2026-09-16 exact-source MarketData.app live checkpoint

- The bounded credentialed MarketData.app matrix was rerun at commit
  `ffa81f991e24c5054312789229f8002a888d3a21` using the owner-managed local
  API key and the durable `local-dev-reset-audit` quota scope. All `7/7`
  selected cases passed (`9` upstream requests and `17,241` response bytes),
  including account usage, latest price, intraday candles, option surface,
  option quote history, and the explicit no-request policy case.
- The run created a reservation-linked receipt and settled native usage
  telemetry without exposing credentials. The response-priced option-history
  path remains intentionally non-routable because no reviewed hard result/
  credit ceiling exists.
- This is exact-source transport and accounting evidence for MarketData.app
  only. The full matrix remains fail-closed for unresolved provider-account
  baselines, legal/source controls, capability budgets, and deployment stores;
  no routing activation, deployment, or shadow run occurred.

## 2026-09-16 provider reset-anchor audit checkpoint

- Removed four unsafe reset interpretations from the provider contract: the
  CoinGecko monthly Demo pool, Tiingo distinct-symbol pool, Marketstack monthly
  pool, and FMP daily/bandwidth pools now expose explicit unresolved reset
  dimensions. Their published limits remain visible, but routing fails closed
  until provider/account evidence establishes the actual reset boundary.
- The coordinator no longer receives a provider-defined label as permission to
  invent a rolling window for these pools. This preserves exact units and
  prevents cross-session usage accounting from underestimating a shared key's
  active-window consumption.
- Documentation, seed-contract assertions, and workstream plan records were
  updated. Focused contract/runtime checks passed `149/149`; the complete
  backend unit suite passed `2,308/2,308` with 37 warnings. No provider
  request, deployment, or routing activation occurred.

## 2026-09-16 OTC Markets validation-file integrity checkpoint

- Added a pure parser for the official OTC Markets Overnight Security Master
  companion validation file. When supplied with a snapshot, it requires the
  documented data-file name, source, timestamp, and positive record-count
  fields, requires the source to be `OTC Markets Group`, and rejects any
  record-count mismatch before the snapshot can be consumed.
- This is parser/fixture capability only. The source remains a candidate: no
  SFTP delivery, entitlement, complete-coverage admission, redistribution
  authorization, or OTC routing was enabled. The parser intentionally does
  not infer a companion URL from the currently configured FINRA-shaped source.
- The focused OTC provider suite passed `20/20` tests (pytest coverage
  threshold is not meaningful for a narrow slice); Ruff and diff checks pass.
  No provider request was made and no frontend or ETF-provider adapter files
  changed.

## 2026-09-16 named provider-usage dimensions and Twelve Data account usage

- Commit `c5e27dca5` adds named `ProviderAccountUsageDimension` values and
  persists one durable observation row per provider pool, with account-plan
  metadata. Existing MarketData.app rows migrate to the explicit
  `credits_per_day` dimension; legacy top-level usage objects remain
  compatible.
- Twelve Data now exposes the documented `/api_usage` endpoint through the
  `account_usage` capability. Its `api-credits-used`/`api-credits-left`
  headers are retained as a named `credits_per_minute` observation with a
  fixed-minute reset, and the returned plan is persisted. The separate Basic
  daily pool is not fabricated from minute headers. The endpoint's one-credit
  cost is declared against both reviewed Twelve Data dimensions.
- Fixture, service, migration, registry, quota-profile, and live-manifest
  coverage passed. The complete backend unit suite passed `2,299/2,299` with
  37 warnings; migration compatibility passed across 31 changed migration
  files. The clean-source live runner at `c5e27dca5` exited before provider
  transport because account baselines and other existing legal/source gates
  remain unresolved; no quota was spent.

## 2026-09-16 MarketData.app trial configuration confirmation

- The owner-approved external configuration is present outside Git in the
  owner-managed `~/.config/charting-platform/app.env`: the MarketData.app key
  is configured with the provider-specific `starter_trial` plan, an exact
  10,000-credit daily pool, and the timezone-aware expiry
  `2026-10-11T18:09:00+01:00` (30 days from the key-email timestamp supplied by
  the owner). The key value was not printed or persisted by this checkpoint.
- Runtime evaluation against that external configuration returned the active
  effective plan `starter_trial` and daily limit `10,000`. At or after expiry,
  the existing provider policy returns `free_forever`/`100`; a later paid
  upgrade remains an explicit plan/limit configuration change and still needs
  `ALLOW_PAID_PROVIDER_ROUTING=true`.
- Focused regression coverage passed `6/6` quota-contract cases and `5/5`
  provider runtime cases. This confirms the active-boundary, expiry-boundary,
  missing-expiry fail-closed, and environment-wiring behavior without making
  a provider request.

## 2026-09-16 migration and workflow-enforcement checkpoint

- Migration compatibility was replayed against the recorded staging parent
  `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`: previous-release schema smoke
  passed (`/health` 200), checked-out schema was the current branch, and all
  `30` changed migration files passed compatibility validation.
- Workflow helper tests passed `46/46`. No provider calls, deployment, or
  protected-branch mutation occurred.

## 2026-09-16 full-stack and local secret-contract checkpoint

- The exact committed implementation passed the Docker-backed combined backend
  unit/integration gate: `2,680` tests passed, total coverage `81.94%`, with
  89 warnings. The isolated testcontainer session was cleaned without a
  host-wide prune and generated coverage artifacts were removed.
- Compose and RPi deployment contract checks passed. They validate routing
  disabled-by-default, egress isolation, secret-boundary wiring, and the
  branch-scoped RPi configuration without deploying or contacting providers.
- The local owner-managed environment file is present with mode `0600` and
  owner `jagnelo`; all required configured provider variable names were found
  without printing values. GitHub and remote deployment secret stores remain
  unverified because they are separate owner-controlled environments.

## 2026-09-16 clean checkpoint and exact-source gate

- The validated implementation was committed on the isolated feature branch at
  `5116a329b3c9ef346c784e1dc86aa4121b9da248`. This commit does not integrate,
  deploy, activate routing, or start the shadow run.
- The full backend unit suite was replayed against that exact clean source:
  `2,294/2,294` passed with 37 warnings in 84.70 seconds. The generated
  coverage XML was removed; no generated coverage artifact remains.
- The lock-protected full live runner was then invoked against the same SHA.
  It made zero provider calls and exited `2` during safety preflight. The
  durable receipt enumerates the remaining provider-account baselines,
  capability budgets, legal/source controls, and deferred-provider decisions;
  it is exact-source evidence that the runner fails closed, not a transport
  failure.
- MarketData.app remains the only currently fully admitted local provider for
  the bounded credentialed subset. The existing 7/7 transport receipt remains
  useful quota-settlement evidence but is not a substitute for the clean-SHA
  full matrix.

## 2026-09-16 MarketData.app account-introspection accounting checkpoint

- Corrected the provider-specific `/user/` account-usage path: it retains a
  positive explicit operation entry and the account-wide concurrency lease, but
  its `credits_per_day` dimension map is explicitly empty because the native
  `x-api-ratelimit-consumed` observation shows that account introspection does
  not spend daily data credits. This avoids overcounting the durable
  cross-session ledger and permits a first snapshot before a credit baseline
  exists; actual market-data/options operations remain baseline-gated.
- Added regression coverage for the exact dimension reservation and fresh
  coordinator bootstrap. Focused checks passed `5/5`; the complete backend
  unit suite passed `2,294/2,294` with 37 warnings. No provider calls were
  made by this change. The source remains dirty and no integration,
  deployment, routing activation, or shadow run was performed.
- Re-ran the credentialed bounded MarketData.app matrix after the correction:
  `7/7` cases passed (`9` requests, `17,241` response bytes), including the
  `/user/` account snapshot. The reservation ledger shows that account-usage
  call held only the concurrency lease and settled zero daily-credit units.
  Receipt run `8ba09662-b60c-4a3d-91d4-df2dea206c76` is correctly marked
  `not_current_source` because this worktree is dirty; it is transport and
  quota-settlement evidence, not exact-candidate acceptance.

## 2026-09-16 live-preflight accounting checkpoint

- The safety-only preflight was rerun after the native-account refresh work. It
  remains correctly blocked before provider transport: provider baselines are
  absent for the configured accounts, Coinbase use authority and several
  source/legal controls are unresolved, and Tiingo/FMP byte maps remain empty.
  No provider quota was consumed.
- Fixed a coordinator defect where an explicitly reviewed empty per-dimension
  cost map was treated as an unknown cost. Empty maps now mean “this operation
  does not consume this dimension”; non-empty maps that omit an operation still
  fail closed. Added exact manifest-only reservation bounds for the bounded
  Binance/Coinbase/Kraken latest-candle, Massive 30-day daily-history, and
  Marketstack five-day daily-history cases. These are live-test bounds, not
  provider-wide defaults.
- Focused quota/live-runner regression passed `71/71` without coverage. The
  complete backend unit suite then passed `2,292/2,292` with 37 warnings;
  targeted Ruff, compile, workstream validation, and `git diff --check` all
  passed. The pinned formatter still reports existing whole-file baseline
  reformatting and no broad formatting sweep was applied.
- The MarketData.app owner configuration remains outside Git and is confirmed as
  `starter_trial` / 10,000 daily credits through `2026-10-11T18:09:00+01:00`,
  then Free Forever / 100. Its scheduled native-usage refresh is opt-in and
  disabled by default.

## 2026-09-16 opt-in native-usage refresh checkpoint

- Added a disabled-by-default daily worker path for provider-native account
  snapshots. A deployment must explicitly set
  `PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED=true` and provide a JSON provider
  list; an empty list never fans out to all providers. The worker polls at
  15:00 UTC and still routes each named provider through its own credential,
  quota, entitlement, and circuit-breaker gates. Compose/RPi, GitHub workflow,
  and environment examples are wired; no external call was made by this
  change.
- Focused provider wiring and worker validation passed `78/78`; Ruff checks,
  compilation, and diff checks passed. The full current-source live matrix,
  provider baselines, legal/source gates, target-owned secret stores, and final
  shadow phase remain open.
- The complete backend unit suite was rerun after this wiring change: `2,290`
  passed with 37 warnings. This is current dirty-worktree evidence, not exact
  staged-candidate or live-provider acceptance.

## 2026-09-16 exact native-account reconciliation checkpoint

- Provider-native account usage is now reconciled into the durable quota
  coordinator only for an explicit exact mapping: MarketData.app's
  `credits_per_day` pool when `/user/` returns the reviewed limit, a current
  reset timestamp, and valid consumed (or exact `limit - remaining`) usage.
  The reconciliation is labelled `provider_account_observation`; plan/limit/
  window/reset mismatches remain observation-only and fail closed. Focused
  quota/account/live-runner regression coverage passed `192/192` without
  coverage instrumentation. This is dirty-worktree evidence and does not
  promote the full live matrix.

## 2026-09-16 continuation validation checkpoint

- The current implementation remains in the assigned dirty feature worktree;
  no commit, integration, deployment, routing activation, or shadow run was
  performed. The live-operation inventory now includes the OpenFIGI profile
  and Bybit cursor cases, explicit `fetch_latest_ohlcv`/service aliases, and
  a structural check over concrete provider public methods. Pytest execution
  no longer writes synthetic live receipts to the durable validation ledger
  unless `PROVIDER_LIVE_VALIDATION_WRITE=1` is explicitly set.
- Complete backend unit validation passed `2,284/2,284` with 37 warnings. The
  authoritative combined Docker-backed unit/integration coverage gate passed
  `2,670/2,670` at `81.90%` with 89 warnings, using isolated testcontainer
  session `0e43d634-917d-4871-ab21-b0b096fad67a`; cleanup removed only this
  workstream's resources. Compose/RPi contract checks passed, workflow tests
  passed `46/46`, Ruff check and diff checks passed, and workstream validation
  passed for 30 records.
- Stack-backed research-runner isolation probes passed: the sandbox denied the
  expected namespace, mount, ptrace, network, subprocess, and host-write
  escapes, and the configured resource ceilings/identity were observed. The
  full browser suite completed with `150 passed`, `109 skipped`, and one
  unrelated frontend-only failure in `F8r-python-library-narrow`; no
  market-data/provider backend E2E failure was reported. The temporary
  branch-scoped stack and volumes were then torn down without a host-wide
  prune. These results are recorded as current dirty-worktree evidence, not
  exact-candidate acceptance.
- The repository-wide `make validate-integration` target was attempted and
  stopped at its existing Ruff-format stage: the pinned formatter reports 94
  baseline files that would be reformatted, including files outside this
  provider change. No broad unrelated formatting rewrite was applied. This is
  a validation limitation, not a provider-test failure.
- The exact current-source full live matrix remains intentionally unrun for
  acceptance: its staged-candidate preflight still requires all provider
  baselines, byte/legal/source controls, SEC/NMS/OTC gates, target-owned
  secret/coordinator verification, and deferred-provider decisions. The
  existing MarketData.app focused receipt remains `not_current_source` and is
  not relabeled. ETF constituent adapter ownership remains with the parallel
  `feat/etf-holdings-constituents` branch; this branch only supplies the shared
  canonical identity/provider contract.
- A fresh full-matrix safety-only runner invocation using the owner-managed
  local environment stopped before network access with exit `2`. It reported
  the expected unknown provider-account baselines, unresolved byte/weighted
  operation costs, legal/source controls, and capability dispositions; no
  provider quota was consumed. This is current dirty-worktree preflight
  evidence, not a failed transport test and not exact-candidate acceptance.
- Current official-source review further confirms the OTC blocker: OTC Markets'
  FAQ says it does not offer market-data APIs, while the FINRA-backed public
  Symbol Directory is a search interface rather than a documented complete
  bulk security-master feed. The candidate FINRA OTC adapter therefore remains
  disabled; no source or completeness claim was inferred from the interface.
- The focused quota/coordinator/live-runner regression suite was rerun without
  coverage instrumentation: `186 passed` in 3.79 seconds. This verifies the
  provider-specific accounting and live-preflight changes after the current
  documentation/source reconciliation.

## 2026-09-16 resumed implementation checkpoint

- The active session resumed the approved corrective plan in the exact branch
  worktree. The owner-managed MarketData.app configuration is provider-specific
  and remains outside Git: `starter_trial` / 10,000 credits per reset-day until
  `2026-10-11T18:09:00+01:00`, then `free_forever` / 100 credits per reset-day.
  The exact expiry boundary is covered at one second before, the instant, and
  one second after; runtime reseeds the quota/entitlement to Free Forever after
  expiry. Paid-plan changes remain configurable by plan/limit/expiry and require
  `ALLOW_PAID_PROVIDER_ROUTING`; `/user/` headers do not infer the plan.
- The bounded MarketData.app live subset passed `5/5` cases against the active
  worktree: small authenticated read, intraday history, option expirations and
  bounded option chain, account usage snapshot, and the response-priced
  historical-option policy guard. The first four operations made a total of
  five upstream HTTP requests and recorded `15,336` response bytes; the
  historical-option guard made zero requests. Same-run operation evidence was
  complete. This subset was protected by the local durable quota coordinator
  and recorded in the owner-managed usage ledger; it is account-usage history,
  not full-matrix or promotion evidence.
- The receipt is honestly `not_current_source`: 50 tracked source paths were
  dirty, so the run proves bounded live behavior for this worktree state only,
  not an exact committed/staged candidate. Preserve the receipt; do not relabel
  it or repeat these calls solely to change its status. The eventual acceptance
  run must use the exact complete staged candidate and full manifest.
- Deployment isolation was tightened alongside that correction: local Compose
  now bind-mounts the owner-managed durable quota ledger into both trusted
  `backend` and `worker` processes, while the network-disabled `research-runner`
  receives neither quota variables nor the ledger mount. RPi keeps the named
  quota volume on backend/worker only. Regression coverage asserts both sides
  of this boundary. RPi preflight also checks core deployment assignments are
  present and non-empty without echoing their values, and still rejects a
  non-PostgreSQL coordinator URL.
- The full live candidate still blocks before network access on unsafe or
  unresolved provider cases, including FRED v1 storage/quota review, Nasdaq
  polling allowance, a documented/authorized complete OTC source, xStocks
  usage/legal eligibility, FINRA async result bounds, Alpaca/Massive action
  page bounds, and Tiingo/FMP byte maps. Other explicit open gates remain the
  SEC staging/materialization cycle, complete NMS/OTC reconciliation,
  environment-owned GitHub/deployment quota and secret stores, deferred
  Tradier/IBKR/Ondo credentials/terms, and the separately authorized final
  30-day shadow phase. Focused live success does not clear these gates.
- Exact next action: finish source and documentation reconciliation, run the
  current focused/unit and authoritative integration gates, then continue
  provider-specific contract/source audits and the complete universe/secret
  store gates. Only after all intended implementation paths and safe live
  controls are settled, stage the complete intended tree and run the required
  full candidate matrix; stop at `ready_for_human_review`, without integration,
  deployment, or shadow activation.

## 2026-09-15 implementation resumption

- The user approved a complete corrective implementation phase. The current
  plan now records all accepted operational decisions in
  `approved_execution_decisions` and adds acceptance gates for provider
  contract discovery, durable cross-session quota state, complete NMS/OTC
  reconciliation, staged SEC/prelisting handling, four isolated credential
  domains, live-validation workflow enforcement, and Dinari Sandbox isolation.
- Confirmed choices: free providers only; aggregate future spend cap 20/month;
  Marketstack stays Free; FINRA Daily List is the known OTC lifecycle source,
  while a complete OTC security-master source remains unresolved; Nasdaq
  Trader files refresh conditionally once per completed market day; three
  complete daily authoritative absences before listing deactivation; FINRA
  async downloads require exact pre-reserved size; prelisting instruments are
  inactive and created only after a clean staged scan on strong evidence;
  Dinari Sandbox is canary-only with no production-data persistence; xStocks is
  eligible for the sole non-US user and its observed 1000/minute rolling
  response-header contract must be enforced; MarketData.app uses the explicitly
  configured 10,000/day Starter Trial quota until 2026-10-11 18:09 Lisbon time,
  then automatically falls back to Free Forever at 100/day. Plan, quota, and
  timezone-aware expiry are provider-specific environment settings; native
  `/user/` data does not identify Starter Trial versus paid Starter.
- Tradier, IBKR, and Ondo are explicitly deferred and remain non-routable.
  Existing keys are local-development-only. Staging/master secrets require
  later owner provisioning; production secrets remain target-owned. The
  30-day shadow run is postponed until all other controllable gates pass and
  is the final separately planned gate before closure/integration.
- Current implementation focus: audit every provider's official contract,
  account endpoints, and bounded live headers; eliminate arbitrary page/byte
  controls and incorrect unknown-quota gates; finish universe reconciliation,
  secret-domain wiring, integration policy enforcement, and current-SHA live
  validation. Do not change frontend or ETF-provider adapter ownership.
- Active session: `1664f75d-6049-4ac2-9753-c2d250b4bc70` (authorized takeover
  from `2d683fe6-c28c-4164-b66e-7dcc57cd03d5`); branch starts at
  synchronized source `da06e560b1aaa0e5399e1e9565f174abe925bda8`.

## 2026-09-15 resumed implementation checkpoint

- The human approved continuing the implementation after the model switch.
  The interrupted worktree claim was transferred using the repository's exact
  takeover guard; the existing active unbounded goal was resumed, not replaced.
- MarketData.app's current key uses `starter_trial` / 10,000 credits per
  provider reset-day, expiring at `2026-10-11T18:09:00+01:00`; this is an
  operator-configured, timezone-aware trial expiry. The integration switches
  to the separately configurable `free_forever` / 100 credits per reset-day
  after expiry. Paid plan upgrades remain a per-environment plan + quota
  configuration; `/user/` does not distinguish trial from paid Starter.
- Latest corrective implementation since the last workstream note closes the
  provider-availability monitor bypass for providers with missing routing
  controls; binds FINRA source approval to the exact credential-free HTTPS
  endpoint; prevents the live test from running without that exact review;
  and hardens the staged full-matrix candidate gate (exact staged tree,
  full-matrix-only, complete credential/source preflight before network,
  secret scanning, captured/redacted output, and no pre-commit ledger writes).
  The historical browser/backend/Compose receipts below remain valid for their
  recorded worktree source, but were taken before these latest changes. The
  focused suite most recently passed 86 tests, targeted Ruff passed, diff
  checks passed, and Compose contract checks exited successfully. The UV
  cache-boundary `agent-context` retry succeeded; an initial normal preflight
  and one initial checkpoint were blocked before product execution/state
  capture. No provider endpoint was called during this resumed session.
- A read-only usage-scope audit confirmed that `ProviderQuotaWindow` is durable
  only when all processes share one application database. Local worktrees use
  separate databases; direct live-suite usage remains an observational JSONL
  ledger settled after test teardown, so it neither reserves quota before a
  call nor constrains runtime admission. GitHub live validation currently has
  one environment and does not reconcile previous receipts before network use;
  deployed hosts have no verified shared direct-probe ledger mount. This leaves
  AC-DURABLE-CROSS-SESSION-USAGE open and requires a provider/account-scoped
  durable admission design plus explicit per-environment credential/storage
  provisioning. No credential values or stores were read.
- The active dirty changeset is still in progress; do not create a commit or
  claim live acceptance until its exact staged candidate passes the complete
  required matrix. Current dirty-path inventory:

  ```text
  .env.example
  .github/workflows/ci.yml
  .github/workflows/provider-live.yml
  Makefile
  backend/.env.example
  backend/app/config.py
  backend/app/providers/edgar.py
  backend/app/providers/finra_otc_directory.py
  backend/app/providers/registry.py
  backend/app/routers/options_exposure.py
  backend/app/services/instrument_events.py
  backend/app/services/market_event_edgar_scan.py
  backend/app/services/provider_availability.py
  backend/app/services/provider_runtime.py
  backend/app/tasks/data_tasks.py
  backend/app/workers/arq_worker.py
  backend/tests/live/test_market_data_providers_live.py
  backend/tests/unit/providers/test_new_providers.py
  backend/tests/unit/routers/test_options_exposure.py
  backend/tests/unit/services/test_instrument_events.py
  backend/tests/unit/services/test_market_event_edgar_scan.py
  backend/tests/unit/services/test_provider_availability.py
  backend/tests/unit/services/test_provider_quota_contract.py
  backend/tests/unit/services/test_provider_registry.py
  backend/tests/unit/services/test_provider_runtime.py
  backend/tests/unit/test_live_provider_runner.py
  backend/tests/unit/test_provider_secret_wiring.py
  backend/tests/unit/workers/test_arq_worker.py
  deploy/rpi/compose.yml
  docker-compose.e2e.yml
  docker-compose.yml
  docs/agent-orchestration.md
  docs/data-providers.md
  docs/deployment.md
  docs/project-todos.md
  docs/provider-live-validation.md
  ops/workstreams/feat-market-data-provider-platform/handoff.md
  ops/workstreams/feat-market-data-provider-platform/session.json
  ops/workstreams/feat-market-data-provider-platform/validation.jsonl
  scripts/run-live-provider-probes.py
  tests/e2e/.env.example
  tests/workflow/test_agent_session.py
  ```
- Exact next action: inspect the provider-specific quota contract and durable
  usage paths with the read-only audit already underway; design and implement
  cross-session reservations/reconciliation without assuming one request equals
  one provider unit. Keep provider calls blocked until pre-call usage and the
  outstanding FINRA source gate can be reconciled. Re-run the authoritative
  backend/browser gates after source changes settle; the full candidate live
  matrix remains acceptance-required and cannot be claimed from focused tests.

## 2026-09-15 changeset context: exact provider configuration and live-gate enforcement

- Scope: make MarketData.app's 30-day Starter Trial and expiry explicit per
  environment, dynamically downgrade its persisted entitlement/quota to Free
  Forever/100 credits per day at expiry, keep all provider quota/usage maps
  environment-configurable, clarify xStocks/Bybit native quota and data-use
  gates, and enforce current-source full live-matrix evidence for provider
  integration changes. User-approved provider deferrals are represented in the
  matrix rather than mislabeled as passes.
- Owned implementation files for this context: `.env.example`,
  `.github/workflows/provider-live.yml`, `README.md`, `backend/.env.example`,
  `backend/app/config.py`, `backend/app/providers/configured.py`,
  `backend/app/providers/registry.py`, `backend/app/services/provider_runtime.py`,
  `backend/tests/unit/services/test_provider_quota_contract.py`,
  `backend/tests/unit/services/test_provider_registry.py`,
  `backend/tests/unit/services/test_provider_runtime.py`,
  `backend/tests/unit/test_provider_secret_wiring.py`,
  `backend/tests/unit/test_live_provider_runner.py`, `docs/agent-orchestration.md`,
  `docs/data-providers.md`, `docs/provider-live-validation.md`,
  `ops/workstreams/feat-market-data-provider-platform/plan.yaml`,
  `scripts/agent-session.py`, `scripts/run-live-provider-probes.py`, and
  `tests/workflow/test_agent_session.py`. No frontend or ETF-adapter path is
  included.
- Validation: focused configuration/runtime/runner/session suite `197 passed`;
  Ruff and workstream validation (`30` records) pass; authoritative Docker-
  backed backend gate `2,533 passed`, 81.75% coverage, 89 warnings. Source
  checkpoint `ffdf26b1a6ca390cced69a36c38613aed947a37a` is pushed and matches
  `origin/feat/market-data-provider-platform`.
- Exact-source live matrix: 46 selected, 43 passed, 3 failed, 0 skipped; three
  approved deferrals (Tradier, IBKR, Ondo) were excluded. All three failures
  were Alpha Vantage IPO/earnings reads returning its documented free-key
  25-requests/day capacity response. The runner incorrectly labeled the receipt
  `not_current_source`: its `.strip()` removed the first leading status byte
  from Git porcelain output, making an `ops/...` path appear as `ps/...`. A
  separate read-only status check confirmed only `session.json` and
  `validation.jsonl` were dirty; the implementation source at the recorded SHA
  was clean. Preserve the append-only original receipt and this correction in
  the handoff; never turn these capacity outcomes into passes or retry them
  before the provider reset.
- Exact next action at that checkpoint: fix and test whitespace-safe
  source-dirty detection in both the live runner and session workflow. That
  runner change invalidates the current live evidence, so do not claim
  acceptance until the full matrix is rerun against the resulting exact SHA
  after quotas permit. Other SEC, provider-contract, universe, secret-store,
  and final shadow gates remain open.
- This separate operational checkpoint updates exactly
  `ops/workstreams/feat-market-data-provider-platform/handoff.md`,
  `ops/workstreams/feat-market-data-provider-platform/session.json`, and
  `ops/workstreams/feat-market-data-provider-platform/validation.jsonl`.
  `agent-session-checkpoint` currently reports that the committed plan changed
  since its last session boundary. This was resolved by committing the approved
  plan, refreshing the plan hash, restoring the active goal, and checkpointing
  the session; the worktree is clean and synchronized at `30ee0fa98ae6`.

## 2026-09-15 corrective changeset context: whitespace-safe status parsing

- Scope: preserve leading Git porcelain status columns in both the live-matrix
  receipt classifier and the agent-session dirty-path classifier. Regression
  tests cover an ops-only first status line followed by a source path, preventing
  false `not_current_source` results and false checkpoint path names.
- Owned files: `scripts/run-live-provider-probes.py`,
  `scripts/agent-session.py`, `backend/tests/unit/test_live_provider_runner.py`,
  `tests/workflow/test_agent_session.py`, and this handoff.
- Validation: focused runner/workflow/secret-wiring tests passed `40/40`; Ruff
  and `git diff --check` pass. The full provider suite is not being repeated
  during the same Alpha Vantage quota window. The previous 43/46 result remains
  a failure (three Alpha Vantage capacity responses, no skips); this code fix
  makes that old source-SHA evidence non-current.
- Exact next action: inspect and commit/push only these five files, then
  continue other controllable provider/universe gates. Run one complete
  lock-protected live matrix only after provider source changes are complete
  and the affected free-tier usage windows have reset.
- Remaining gates are not cleared by this changeset or its unit/backend tests:
  full live matrix (including honest Alpha Vantage capacity outcomes), SEC scan
  bound/materialization execution, complete NMS/OTC reconciliation and source
  terms, provider legal/quota/response-size controls, separate CI/deployment
  secret stores, Dinari sandbox persistence isolation, future non-Strategy
  evaluator coverage, and the separately authorized final 30-day shadow run.

## Active context: SEC directory gate and full-stack provider startup fixes

- Scope: make the SEC ticker-directory scan report read-only candidate counts on
  its initial disabled-materialization cycle; require a completed clean scan,
  an explicitly reviewed cycle number, and an operator-selected `create_missing`
  mode before any new Issuer row can be inserted. Pin a durable cycle to one
  source fingerprint so a changing SEC directory cannot be mislabeled a
  complete snapshot. Keep this source explicitly distinct from Nasdaq/FINRA
  venue-complete security-master reconciliation. Close the full-stack defects
  discovered while validating this context: environment sentinel parsing and
  idempotent, concurrency-safe provider entitlement revision seeding.
- Owned paths: `.env.example`, `backend/.env.example`,
  `.github/workflows/provider-live.yml`, `docker-compose.yml`,
  `deploy/rpi/compose.yml`, `backend/app/config.py`,
  `backend/app/providers/edgar.py`, `backend/app/services/market_event_edgar_scan.py`,
  `backend/app/services/provider_runtime.py`,
  `backend/app/tasks/data_tasks.py`, `backend/tests/live/test_market_data_providers_live.py`,
  `backend/tests/unit/providers/test_new_providers.py`,
  `backend/tests/unit/services/test_market_event_edgar_scan.py`,
  `backend/tests/unit/services/test_provider_runtime.py`,
  `backend/tests/unit/services/test_provider_quota_contract.py`,
  `backend/tests/unit/test_provider_secret_wiring.py`,
  `backend/tests/unit/workers/test_arq_worker.py`, `docs/data-providers.md`,
  `docs/deployment.md`, `docs/provider-live-validation.md`, and this handoff.
  No frontend or ETF-adapter path is included.
- Current evidence/context: SEC's public ticker-association files are search
  aids and explicitly not guaranteed accurate or complete for venue scope; the
  submissions API itself is keyless and SEC publishes an aggregate 10 requests
  per second ceiling. Existing code already defaults the directory scan off
  and has a zero submissions-request budget; do not enable a daily scan or
  invent a request budget during this context. The first full-stack startup also
  exposed that Pydantic Settings 2.2.1 eagerly JSON-decodes the non-JSON
  `__CODE_DEFAULT__` sentinel before its field validator; the environment and
  dotenv sources now pass that exact sentinel through, preserving explicit JSON
  overrides and code defaults. SEC pagination now rejects rows beyond the
  snapshot's remaining total before filing reads or issuer writes.
- Validation so far: focused SEC/provider/config/worker coverage passed
  `332/332`; changed Python files pass Ruff check and format, and an isolated
  app import with all three policy-map sentinels resolves each to a `dict`.
  The combined Docker backend gate passed at `81.78%`. The repaired stack now
  reaches healthy status, but browser E2E failed at test 19/260: two repeated
  `ACCOUNT_USAGE` seed attempts collided at the unique entitlement-revision
  constraint. Logs show the MarketData.app repository seed resets its dynamic
  quota policy on every resolution, incrementing revisions continuously; this
  must be fixed and tested before the browser gate is considered green. One
  OpenFIGI mapping HTTP call also occurred as an E2E side effect; do not claim
  the browser suite was network-isolated or treat its provider usage as a live
  matrix pass. No explicit live-matrix run was made.
- Exact next action: make effective entitlement seeding idempotent, make
  revision snapshot insertion conflict-safe across shared processes, add a
  regression for the configured MarketData.app trial and no-op seed repeats,
  then rerun focused/backend gates and the full branch-scoped stack/browser
  suite. Keep the SEC directory scan disabled and its submissions budget at
  zero; no SEC live cycle or request allowance is authorized by this context.

Created from `staging` at `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`.

- Direct live-provider receipts now retain validated per-operation transport
  breakdowns instead of only provider totals. The merger and application
  reader reject nested operation totals above their provider aggregate,
  preserve legacy rows, and expose `operation_breakdown` in admin usage
  diagnostics. All 49 market-data/tokenized live probes now pass explicit
  operation labels. Focused usage tests passed `32/32`; the final matrix
  collected `49` cases and passed `43/49`, with three typed Alpha Vantage
  capacity responses and the intentionally missing Tradier, IBKR, and Ondo
  credentials as the six honest outcomes. The owner receipt is run
  `5e42d113-3e2a-4b81-a055-35109f365d73` (26 provider rows, 96 HTTP requests,
  78 operations, 23,159,806 bytes, four failed operations). This is transport
  and usage evidence only; provider/legal/deployment/reconciliation/shadow
  gates remain open.

- Final backend source checkpoint: `0b27192eb` (`feat(ops): attribute live
  provider usage by operation`). Direct live-provider receipts now retain a
  bounded operation breakdown alongside provider totals, with validated nested
  counters exposed through usage diagnostics; all 49 market-data/tokenized
  live probes pass explicit adapter operation labels. Focused usage coverage
  passed `32/32`; the authoritative Docker-backed gate passed `2,527/2,527`
  at `81.74%` combined coverage with 89 warnings in `478.02s`, using isolated
  testcontainer session `7f420e71-c14e-45a6-bb7b-1399e71bc390`, cleaned
  without host-wide pruning. No frontend or ETF-provider adapter files
  changed.

- Historical current-head live matrix at `2735f038f` collected 49 manifest cases
  and passed 43/49. Both Alpaca AAPL and BTC-USD profile reads passed; Alpha
  Vantage's three calendar/earnings operations returned typed documented
  free-key capacity responses; Tradier, IBKR, and Ondo remained exact
  missing-credential preflights. Owner-managed receipt run
  `d0f738be-3b3b-4523-9649-86aa9b464ae4` recorded 26 provider rows, 98 HTTP
  requests, 79 operations, 23,237,350 response bytes, and four failed
  operations (three Alpha Vantage capacity responses and one expected EODHD
  non-entitlement observation). The runner returned exit code 2 and makes no
  acceptance or routing-promotion claim; unresolved provider/legal,
  deployment-secret, reconciliation, and shadow gates remain open.

- Latest backend source checkpoint: `a49c5b9f1` (`feat(provider): add Alpaca
  instrument metadata`). Alpaca's authenticated `/v2/assets/{symbol}` surface
  now maps into the common `InstrumentProfile` contract, retains the provider
  asset UUID as `ALPACA_ASSET_ID` without claiming canonical FIGI/CIK identity,
  records listing/exchange/status/tradability metadata and raw payload, and is
  an explicit final fallback in the instrument-metadata chain. The focused
  unit/registry/quota checks passed; its bounded live `AAPL` profile read
  passed against the supplied paper account. The authoritative Docker-backed
  gate passed `2,523/2,523` at `81.74%` combined coverage with 89 warnings in
  `521.07s`, using isolated testcontainer session
  `76f2c666-31bc-4618-8e86-681c69785352`, cleaned without host-wide pruning.
  No frontend or ETF-provider adapter files changed.

- Current-head complete live matrix at `a49c5b9f1` collected 48 manifest cases
  and passed 42/48. The new Alpaca profile case passed; Alpha Vantage's three
  calendar/earnings operations returned typed documented free-key capacity
  responses; Tradier, IBKR, and Ondo remained exact missing-credential
  preflights. Owner-managed receipt run
  `b22ca35b-b3ea-4d20-8c0c-eeb77b30cca8` recorded 26 provider rows, 97 HTTP
  requests, 78 operations, 23,169,232 response bytes, and four failed
  operations (three Alpha Vantage capacity responses and one expected EODHD
  non-entitlement observation). The runner returned exit code 2 and makes no
  acceptance or routing-promotion claim; unresolved provider/legal,
  deployment-secret, reconciliation, and shadow gates remain open.

- Latest backend source checkpoint: `d0662d139` (`fix(provider): type
  unsupported history timeframes`). The required Docker-backed gate passed
  `2,520/2,520` at `81.75%` combined coverage with 89 warnings in `523.12s`
  using isolated testcontainer session
  `46c3894d-e2c3-4e57-a5be-1d34654c5d0c`; focused provider adapter coverage
  passed `343/343` with `--no-cov`, Ruff and diff checks passed, and the branch
  is pushed. Alpaca, Binance, Tiingo, Twelve Data, Tradier, MarketData.app,
  Finnhub, Marketstack, EODHD, and FMP now reject unsupported direct history
  timeframes with typed provider errors before transport rather than returning
  ambiguous empty lists; valid empty ranges and non-crypto Binance symbols are
  unchanged. No frontend or ETF-provider adapter files changed.
  Provider/legal, trusted-secret-store, deferred-credential, NMS/OTC
  reconciliation, and separately approved shadow-run gates remain open.

- Current-HEAD live revalidation on 2026-09-14 collected 47 manifest cases and
  passed 41/47. Alpha Vantage's IPO-calendar and both earnings operations
  returned its typed documented free-key capacity response; Tradier, IBKR, and
  Ondo remained exact missing-credential preflights. The redacted receipt
  `2a14d59d-49fa-4794-b67a-ec8d2c5e1028` recorded 26 provider rows, 96 HTTP
  requests, 77 operations, and 23,167,868 response bytes in the owner-managed
  mode-0600 ledger. Routing safety remained fail-closed for the explicitly
  unreviewed provider controls. This is transport/quota observation only, not
  acceptance or routing-promotion evidence.

- Tokenized historical comments and documentation are now consistent with the
  implemented Dinari/Ondo bridge and its four supported windows (`DAY`,
  `WEEK`, `MONTH`, `YEAR`). Focused tokenized/asset-service/secret-wiring
  coverage passed `122/122`; the authoritative Docker-backed backend gate
  passed `2,488/2,488` at `81.72%` coverage with 89 warnings in `492.85s`,
  using isolated testcontainer session
  `b7dd6e85-27f9-49e0-8747-5220aa720254`. No frontend or ETF-provider adapter
  files changed.

- Current source checkpoint: `d041f80e5` (`docs(provider): align tokenized
  history windows`). The latest authoritative Docker-backed combined backend
  gate passed `2,488/2,488` at `81.72%` coverage with 89 warnings in `492.85s`,
  using isolated testcontainer session
  `b7dd6e85-27f9-49e0-8747-5220aa720254`; the branch remains backend-only and
  no frontend or ETF-provider adapter files changed. Provider/legal,
  deployment-secret, reconciliation, deferred-credential, and shadow-run
  gates remain open as recorded below.

- The current-HEAD authoritative Docker-backed combined backend gate was rerun
  after the configuration-preflight receipt and passed `2,488/2,488` at
  `81.72%` coverage with 89 warnings in `488.89s`, using isolated testcontainer
  session `c10069ff-beec-468f-8efe-e8bc3de455cf`. Cleanup removed only this
  workstream's resources without host-wide pruning. No frontend or ETF-provider
  adapter files changed.

- MarketData.app's current option-chain/rate-limit documentation confirms
  response-priced current chains, historical billing per 1,000 returned
  symbols, and a 50-request concurrency ceiling. The adapter/runtime therefore
  retain response-dependent settlement and the explicit reviewed symbol bound;
  no account plan, OPRA entitlement, or redistribution permission is inferred.

## Human authorization

- Recorded at: 2026-09-04T16:12:23.412849+00:00
- Request: Implement the approved US-first multi-provider market-data platform plan: canonical FIGI-based identity and issuer model; exchange/session calendars; market-series scoped raw/canonical OHLCV with local rollups and adjustments; provider capability/entitlement/quota routing; US universe/lifecycle, events, SEC fundamentals, FINRA short interest, current options with local high-fidelity Greeks, optional futures and crypto providers; backend admin/diagnostic APIs; and disabled 30-day shadow monitoring. Backend/data only; do not modify frontend or ETF constituent provider work.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- The subsequent lock-protected full live matrix on 2026-09-13T17:24:29Z collected 47 cases and passed 41/47. Alpaca, SEC EDGAR, MarketData.app, Dinari Sandbox, and the other configured/keyless providers produced bounded observations. Alpha Vantage returned its typed documented 25-requests/day capacity response for IPO-calendar and both earnings reads; Tradier, IBKR, and Ondo remained exact intentional credential preflights. Aggregate-only usage is recorded under run `50dd90c4-f1d2-49c5-b2cc-3589d4f7e3f2`; the runner returned exit code 2 and made no acceptance claim.
- Follow-up provider-specific live run on 2026-09-13 exercised 11 bounded tests against the owner-managed environment: SEC EDGAR profile/filings/directory (3), Alpaca daily/intraday/latest/assets/corporate actions (4), MarketData.app options/account-usage/intraday (3), and Dinari Sandbox metadata/price/quote/history/news/dividends/splits/corporate actions (1). All 11 test bodies passed; pytest returned non-zero only because this live-only subset cannot satisfy the repository-wide 55% coverage threshold. Aggregate request/byte telemetry remained outside Git, and this remains non-acceptance transport evidence only.
- Follow-up rerun of those same 11 bounded cases completed with `--no-cov` under the owner-managed environment: all 11 passed in 15.39 seconds. This confirms the supplied Alpaca, SEC EDGAR, MarketData.app, and rotated Dinari Sandbox transports after the latest source checkpoint; aggregate request/byte telemetry remains outside Git and this is still non-acceptance evidence.
- Latest-bar history admission now evaluates the requested window against the selected provider's own structured history bound. The latest-price path passes a provider-specific history-start factory through runtime resolution, so documented bounds cannot be bypassed by latest-window reads. Focused market-data/runtime/routing/risk-free coverage passed `103/103`; Ruff, compileall, and diff checks passed. The authoritative Docker-backed combined backend gate passed `2,483/2,483` at `81.71%` coverage with 89 warnings in `490.57s`, using isolated testcontainer session `8226f73b-8e03-4e80-9876-05a521380d20`; cleanup removed only this workstream's resources without host-wide pruning. No frontend or ETF-provider adapter files changed.
- Ondo's documented primary-token daily OHLC endpoint is now bridged into the shared `tokenized_historical_prices` capability. DAY preserves provider rows; WEEK, MONTH, and YEAR are deterministic local rollups with raw source-row provenance, while underlying-market rows remain separate. The provider profile reserves the metadata plus OHLC transport pair, but unknown quota/terms keep routing fail-closed. Focused tokenized/quota coverage passed `167/167`; registry/runtime/tokenized-service/wiring coverage passed `110/110`; Ruff, compileall, and diff checks passed. The authoritative Docker-backed combined backend gate passed `2,484/2,484` at `81.71%` coverage with 89 warnings in `503.83s`, using isolated testcontainer session `419d8b48-86d8-4df9-9cf1-d748fb9a0b6f`; cleanup removed only this workstream's resources without host-wide pruning. No frontend or ETF-provider adapter files changed.
- Deployment defaults now preserve the tokenized historical capability: `.env.example`, `backend/.env.example`, local Compose, and RPi Compose explicitly seed `tokenized_historical_prices` with Dinari and Ondo. This prevents an explicit `PROVIDER_CHAIN_SEEDS` deployment override from silently disabling historical tokenized refresh routing. Provider secret/wiring, registry, and tokenized-service coverage passed `65/65`; Ruff, compileall, Compose YAML parsing, and diff checks passed. The existing source gate remains `2,484/2,484` at `81.71%`; no frontend or ETF-provider adapter files changed.
- MarketData.app account-plan accounting now recognizes the provider's distinct `starter_trial` and `trader_trial` 30-day plans at their documented 10,000/100,000 daily credit pools. Trial identifiers remain separate from paid plans and still require explicit operator review; no native header or trial observation widens routing automatically. Focused quota/runtime/provider coverage passed, and the authoritative backend gate passed `2,454/2,454` at `81.67%` with 89 warnings.
- Trial-plan routing now also requires `MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT` to be a future timezone-aware ISO-8601 value. Missing, naive, or elapsed expiries keep the conservative Free Forever seed and are surfaced as the exact missing routing control; the live preflight enforces the same rule. Focused provider-policy/wiring coverage passed `127/127`, Ruff passed, and the authoritative backend gate passed `2,454/2,454` at `81.68%` with 89 warnings in isolated testcontainer session `878ce18f-56fa-4541-89f7-c07a9db64cae`.
- The expiry setting now accepts the intentionally blank value emitted by Compose/GitHub when no trial review exists, while preserving fail-closed routing. This closes a startup/configuration regression found by an explicit environment-boot test. The focused provider-policy/wiring suite passes `128/128`; the authoritative backend gate passes `2,455/2,455` at `81.68%` with 89 warnings in isolated testcontainer session `31a5a352-2eb8-47b2-b895-1372f2d30b4c`.
- MarketData.app routing diagnostics now report the complete invalid control set when a trial has both an invalid plan/limit pair and an invalid expiry. The runtime registry and live safety preflight distinguish a valid pair missing only its expiry from a trial with multiple invalid controls; focused provider-policy coverage passed `128/128`, Ruff/diff checks passed, and the authoritative backend gate passed `2,455/2,455` at `81.68%` with 89 warnings in isolated testcontainer session `63b3d97b-c227-43b5-a9b1-52cd54bd5011`.
- Planning state: ready; scope, acceptance criteria, branch tests, and the docker-backed full-integration validation profile are recorded in `plan.yaml`.
- Historical checkpoint `43a7d8f091ef` documented the earlier MarketData.app trial-plan and tokenized-history availability work; it is superseded by current source checkpoint `d041f80e5` above. The remaining gates are provider/legal/deployment/shadow, future-evaluator coordination, production NMS/OTC reconciliation, deferred credentials, and coordinator review before promotion.
- Implementation checkpoint: provider-native cumulative usage settlement extends the transport-header work through durable quota windows. Twelve Data `api-credits-used`/`api-credits-left`, Tradier allowed/used/available token-window headers, and Binance one-minute used weight are each reconciled only against their matching reviewed provider contract; malformed or mismatched observations remain telemetry and never lower local totals. Tiingo's documented first-of-month Eastern bandwidth reset, durable distinct-provider-symbol ledger, and FMP's operator-verified rolling 30-day bandwidth reset are represented explicitly; both providers remain fail-closed until operation-specific byte reservations can be justified. Provider-defined or otherwise unspecified reset labels now use conservative rolling windows rather than invented UTC epoch buckets, while explicit calendar/session resets remain provider-specific. The configurable FINRA OTC Security Master path now carries the official synchronous 1,200-requests/minute/IP and 3 MB response contract, and its DAPI pagination follows authoritative totals after payload-capped short pages; FINRA pagination and payload-ceiling headers are durably retained in transport telemetry. Its response-dependent cold refresh now requires an explicit reviewed operation-cost map for both runtime operation families, plus independent source-terms, completeness, redistribution, and positive polling controls; no generic one-request charge is inferred. The earlier checkpoints make calculated Binance operation costs survive the complete execution path, reserve latest-bar lookback pages conservatively, model provider-specific calendar/rolling reset semantics, and durably capture FINRA byte settlement. Tokenized instruments remain distinct from their economic underlyings and only link when the existing symbol match is unambiguous.
- The FINRA asynchronous Query API adapter now requires an explicit positive result-byte bound (configuration or call-site), validates declared and measured payload sizes while streaming chunks, and remains OAuth-free on the presigned download leg. A configured positive bound now feeds the operation-specific durable monthly-byte reservation and measured settlement; the default zero remains fail-closed because the provider does not publish a universal result-size ceiling.
- Robinhood tokenized-price reads now have a finite provider-specific 429 retry budget with `Retry-After` support; repeated throttles remain observable and fail closed instead of creating a retry storm.
- MarketData.app's documented 50-request account-wide concurrency ceiling is now a durable release-only `concurrent_requests` quota dimension. Direct provider calls and queued workload leases reserve it across workers and release it on completion without converting in-flight capacity into historical consumption.
- MarketData.app stock-candle credits are response-dependent, not one-request/one-credit. The runtime now reserves a documentation-backed date-granular upper bound (one credit per 1,000 returned candles, full-day intraday bound) for explicit/latest/bulk history. A missing or unsupported estimate does not fall back to one credit, preserving fail-closed routing.
- Nasdaq Trader directory polling now retains `ETag`/`Last-Modified` validators and conditionally reuses parsed files on `304 Not Modified`; this lowers repeated download load without inventing a numeric polling allowance, so the provider remains discovery-only and non-routable for quota-controlled work.
- Local and RPi Compose now pass `FINRA_ASYNC_MAX_RESULT_BYTES`, `TIINGO_OPERATION_BYTE_BOUNDS`, and `FMP_OPERATION_BYTE_BOUNDS` to backend and worker only; the research-runner remains isolated, and secret-wiring regression coverage protects this boundary.
- `backend/.env.example` now matches the fail-closed deployment contract: the OTC Security Master URL is empty until source/terms approval, FINRA async and Tiingo/FMP byte controls are explicit zero/empty settings, and descriptor-only IBKR/Coinbase/Kraken variables are documented; the safety regression covers this example.
- A registry-wide quota-contract acceptance regression now requires every registered provider to have a complete explicit quota contract or an intentional-unknown classification; it prevents future provider additions from silently inheriting generic limits.
- Tiingo's 500-unique-symbol monthly allowance now uses the additive `provider_quota_identity` migration and durable per-window distinct-symbol claims. Repeated calls are never misrepresented as unique-symbol usage; complete reviewed byte bounds are still required before promotion.
- External quota accounting boundary: durable logs/windows and distinct-identity claims survive restarts and coordinate workers sharing one database, but separate worktrees/CI/deployments using the same provider account are externally shared and locally invisible unless a provider-native cumulative header is safely reconciled. The live suite is quota-consuming and must not be run concurrently on a shared key.
- FRED's v1 error documentation records a 120-requests/minute threshold before HTTP 429 but no enforcement scope; the terms allow provider-adjustable bandwidth/transaction limits plus series-specific copyright/redistribution and non-endorsement requirements. FRED remains non-routable until the scope and terms gates are reviewed.
- FRED's adapter now preserves HTTP 429/418 responses as typed `ProviderRateLimitError` capacity failures, including provider response headers and parsed `Retry-After` timestamps, instead of converting quota rejection into an empty-series/empty-price result; the v1 documented 120-requests/minute threshold is recorded while enforcement scope, adjustable limits, and terms remain unresolved, and the separate v2 2-requests/second rule is not applied to the v1 adapter.
- FRED's v1 quota seed now records the official 120-requests/minute dimension while retaining provider-defined enforcement scope, adjustable-limit behavior, and series-rights gates as unknown by default. Explicit deployment controls (`FRED_REVIEWED_LIMIT_SCOPE`, `FRED_REVIEWED_REQUESTS_PER_MINUTE` bounded to 1..120, and `FRED_SERIES_TERMS_REVIEWED=true`) replace only those dimensions after operator review; absent controls remain fail-closed, and `policy_has_known_quota` still rejects the unresolved seed.
- FRED's reviewed-admission controls are now wired through backend/RPi Compose, the manual GitHub live workflow, both environment examples, provider-policy diagnostics, and the live safety preflight; focused registry/secret-wiring/quota tests pass `73/73` with the default controls still non-routable and the fully reviewed test configuration becoming routable.
- Provider resolution and the admin `routing_eligible` diagnostic now enforce every registered provider's non-secret routing-control set, not merely expose missing names. A configured FINRA OTC source therefore remains excluded until its operation-cost and governance controls are all present.
- The manifest live runner now acquires `~/.config/charting-platform/provider-live.lock` (or `PROVIDER_LIVE_LOCK_FILE`) before any external probe; a second local worktree exits with code 3 without making calls, and the lock metadata contains no credentials. This is local coordination only and does not replace provider-native/account-level usage reconciliation across CI or deployments.
- Direct live probes now aggregate observed operation/request/response-byte counts per provider into the external `~/.config/charting-platform/provider-live-usage.jsonl` ledger (or `PROVIDER_LIVE_USAGE_LEDGER`); it contains no payloads or credentials and supplements, rather than replaces, durable runtime quota windows and provider-native cumulative usage.
- Direct-live receipts now also retain a bounded, allow-listed snapshot of provider-native capacity headers observed by the transport (credits, remaining/reset values, `Retry-After`, FINRA record bounds, and exchange weight state); the backend diagnostic exposes the latest redacted snapshot and the merger rejects non-capacity headers.
- The manifest live runner now requires a printable, bounded `PROVIDER_LIVE_USAGE_SCOPE` label before starting quota-consuming probes. Legacy receipts remain readable as `unspecified`, but new runs cannot create unattributed cross-environment usage.
- The descriptor-only IBKR contract was corrected from the official historical-market-data documentation: 10 requests/second per authenticated session, 50 historical requests/minute, five concurrent history requests, and a 1,000-bar response cap. IBKR remains non-routable until its funded/session-bound adapter and live evidence exist.
- The IBKR adapter now explicitly advertises documented futures historical-data support through its existing generic conid path. It requires `IBKR_READ_ONLY_URL` plus the operator-owned `IBKR_READ_ONLY_SESSION_COOKIE`, never automates interactive login, keeps provider `conid` metadata separate from canonical identity, pages only through a bounded 1,000-point response contract, records raw bars without adjustment claims, and documents IBKR's two-year expired-futures availability limit. Fixture/registry coverage passes; the live manifest remains non-routable without a gateway session. IBKR options methods remain intentionally unimplemented.
- Newly configured Alpaca and MarketData.app credentials were revalidated on 2026-09-13 in seven bounded cases: Alpaca daily/intraday/latest history, assets, and corporate actions plus MarketData.app options, account usage, and intraday history. All passed; aggregate usage telemetry remains outside Git and does not promote unreviewed routing controls.
- Provider availability probes now pass `adjusted=False` for providers whose registry contract is raw-only, including IBKR's generic futures history. Focused availability/IBKR/registry coverage passed `45/45`, and the full Docker-backed gate passed `2,447/2,447` at `81.63%`; no live provider call was made for this source change.
- Tokenized historical persistence now has a non-mocked persistence-boundary test that verifies the raw `24_7` OHLCV bar, canonical scoped series/default, durable observation, and fresh dataset state. The observation upsert uses its declared unique columns rather than a PostgreSQL-only constraint-name target, so the same path is executable in SQLite fixtures and PostgreSQL. Focused tokenized coverage passed `23/23`; the authoritative Docker-backed gate passed `2,448/2,448` at `81.67%` with 89 warnings. No live provider call or credential was used for this source change.
- A fresh bounded credentialed revalidation passed `9/9` using the existing owner-managed environment: SEC EDGAR filings/Company Facts, Alpaca daily/intraday/latest/assets/corporate actions, MarketData.app options/account-usage/intraday, and Dinari Sandbox metadata/price/quote/DAY-WEEK-MONTH-YEAR history/news/dividends/splits/corporate actions. Aggregate request/byte telemetry remained outside Git; this is transport evidence only and does not promote unreviewed routing controls.
- The Dinari live history case now validates every returned aggregate row's provider UUID, requested timespan, timezone-aware timestamp, positive OHLC values and relationships, and raw-payload provenance. The tightened Sandbox case passed `1/1`; Ruff passed, and no credentials or provider payloads entered Git.
- The manifest live runner now has an explicit provider-to-live-test coverage map. A registry-wide wiring regression requires every registered provider to have at least one named bounded live case, or a non-empty reason for an intentional exclusion (internal ETF ingestion, legacy yfinance, or descriptor-only Alpaca tokenization). The new coverage guard passed with the provider secret-wiring suite; this prevents a future adapter from being accepted with fixtures only or an undocumented live-test omission.
- The live-runner change detector now compares the feature branch against its `staging` merge-base (with explicit-base and parent fallbacks), so a trailing metadata or documentation commit cannot incorrectly suppress the provider matrix. A clean-tree regression proves a provider change remains applicable after such a trailing commit; the provider secret-wiring suite passes `19/19`.
- The authoritative Docker-backed combined backend gate after the live-runner fix passed `2,450/2,450` at `81.66%` coverage with 89 warnings; isolated testcontainer session `6dbc9e71-b01e-49e8-8ad3-1bdd7ff49df7` was cleaned without host-wide pruning. No external provider calls or credentials were used by this gate.
- This checkpoint's implementation paths are limited to the read-only IBKR adapter and its provider-runtime, configuration, live-preflight, documentation, and validation wiring: `.env.example`, `.github/workflows/provider-live.yml`, `backend/.env.example`, `backend/app/config.py`, `backend/app/providers/errors.py`, `backend/app/providers/ibkr.py`, `backend/app/providers/registry.py`, `backend/app/services/market_data.py`, `backend/app/services/provider_runtime.py`, `backend/tests/live/test_market_data_providers_live.py`, `backend/tests/unit/providers/test_ibkr.py`, `backend/tests/unit/services/test_provider_quota_contract.py`, `backend/tests/unit/services/test_provider_registry.py`, `backend/tests/unit/test_provider_secret_wiring.py`, `deploy/rpi/compose.yml`, `docker-compose.yml`, `docs/data-providers.md`, `docs/provider-live-validation.md`, `docs/project-todos.md`, `ops/workstreams/feat-market-data-provider-platform/handoff.md`, `ops/workstreams/feat-market-data-provider-platform/plan.yaml`, `scripts/run-live-provider-probes.py`, and this workstream metadata. No frontend or ETF paths are included.
- FRED missing credentials now raise `ProviderNotConfiguredError` rather than returning an empty series/price, so provider fallback can distinguish absent configuration from a valid no-observation result.
- Alpaca missing API/secret credentials now raise `ProviderNotConfiguredError` across history, latest-price, corporate-action, and discovery operations; unsupported symbols/timeframes remain ordinary empty-result cases.
- Alpaca and SEC EDGAR no longer swallow upstream HTTP status failures into empty or synthetic results; they propagate status errors to the runtime's typed capacity/reset handling.
- SEC EDGAR now fails closed when `EDGAR_USER_AGENT` is blank; the descriptive contact value remains a per-environment non-secret deployment requirement.
- Optional REST adapters now reject explicit HTTP-success error envelopes (including Twelve Data, FMP, Finnhub, and MarketData.app shapes) as typed provider failures; rate/quota wording is preserved as a typed capacity failure instead of becoming a false empty observation. Fixture coverage covers representative error and rate-limit envelopes.
- Provider resolution now applies an explicit provider/instrument-class allow-list before invocation. Equity and ETF instruments cannot fall through to crypto-only OHLCV adapters, and unknown provider mappings fail closed. The regression is covered by provider-registry/runtime tests and the two PostgreSQL-backed AAPL OHLCV integration cases that previously exhausted Coinbase/Kraken.

## Current implementation boundary

- Latest source checkpoint: `e8eae7b8` adds `evaluator_preflight.py` and wires
  exact range/freshness preflight into Strategy Lab rules and Radar signal
  replay. Incomplete or stale instruments are withheld before evaluation;
  optional `queue_coverage_repairs` uses only bounded durable refresh jobs and
  never performs provider I/O in an evaluator. Focused preflight coverage is
  `4/4`, the complete Strategy Lab API suite is `20/20`, the complete unit suite
  is `2,018/2,018`, and the authoritative Docker-backed gate is `2,397/2,397`
  at `81.36%` combined coverage with 89 warnings. The new source and docs did
  not touch frontend or ETF-provider adapter ownership.
- Phase: provider-transport usage implementation and credentialed/integration validation (not ready for review yet; three credential domains, GitHub live-environment verification, provider-terms reviews, and complete universe reconciliation remain pending).
- Latest source checkpoint: `3950f477c` adds durable provider-native account-usage observations, the `ACCOUNT_USAGE` capability, MarketData.app account refresh/history admin endpoints, explicit operation accounting, and strict native counter/reset validation. The direct credentialed MarketData.app account probe passed `1/1`; only that provider currently exposes the native account snapshot contract. The reviewed plan/credit pair and response-priced option-chain bound remain fail-closed. Generic migration compatibility is blocked by the repository's pre-existing duplicate Alembic revision and multiple heads; this branch does not reconcile unrelated migration history.
- Latest source checkpoint superseding that account-usage slice: `a4af6f95d` persists refresh-job `started_at`, `finished_at`, and redacted `result_summary` fields; workers record observed-bar counts and empty responses, and retry/defer paths preserve bounded error/reset evidence. The admin refresh-queue diagnostic exposes these fields without lease tokens. Focused queue/worker/migration coverage passed `49/49`, the admin PostgreSQL integration passed `3/3`, and the Docker-backed combined gate passed `2,393/2,393` at `81.35%` coverage. Future breadth/signal evaluator preflight remains open, as does generic migration compatibility because of the pre-existing Alembic graph.
- Delivered in this boundary: additive FIGI/issuer identity, series and session/calendar models, durable multi-dimensional quota/routing/refresh queue primitives, typed durable provider capacity events, SEC facts/FINRA short-interest and OTC Daily List event records, a fail-closed configurable FINRA OTC symbol-directory adapter, QuantLib Greeks, and backend diagnostics; concrete opt-in Tiingo/Twelve Data/Finnhub/Marketstack/EODHD/FMP/Tradier/MarketData.app/Coinbase/Kraken adapters; official Nasdaq Trader directory ingestion; conservative worker-only US universe lifecycle reconciliation; exchange-aware core D1 coverage snapshots; the explicit-quota migration `ff5a6b7c8d9e`; the additive tokenized-asset migration `0b1c2d3e4f5a` with five public tokenized provider adapters and persisted product metadata; the provider transport-usage migration `1c2d3e4f5a6b` with durable byte/header observations and admin usage aggregates; and the distinct-symbol quota migration `2d3e4f5a6b7c`. All registered synchronous adapters now emit transport observations, including OpenFIGI's pooled HTTP client and the previously uncovered Alpaca, Alpha Vantage, CoinGecko, Coinbase/Kraken, EDGAR, Nasdaq Trader, Massive, and configurable FINRA OTC paths. The provider usage diagnostic also exposes the latest filtered header snapshot and active durable quota-window reservations for account/credit/reset inspection, while capacity events retain Binance weight and Bybit V5 provider-native limit/reset state. FINRA's async Query API submit/status/presigned-result flow is implemented with OAuth only on API legs and no Authorization header on the signed download leg; signed result downloads now enforce positive declared/measured byte bounds.
- CIK is retained as issuer evidence rather than a security key. New symbols without a security-level identifier remain provisional/quarantined instead of being silently merged, while provider symbol/listing history and repeated-missing evidence remain durable.
- Provider resolution treats blank or `unreviewed` entitlement plans as non-routable even when paid-provider routing is enabled; the paid switch only admits explicitly reviewed plans.
- Provider resolution also requires a documentation-backed quota contract. Generic 60/minute, 15-burst, 2-concurrency, and 30-second cooldown values have been removed; unknown dimensions remain NULL/unknown and are excluded from routing. Durable reservations now track each provider budget dimension and calendar/reset semantics.
- The live probe wrapper now prints an explicit routing-safety preflight for FINRA's asynchronous result-byte bound and Tiingo/FMP operation byte-bound maps. A successful direct read is not routing admission; missing, invalid, partial, or non-positive controls remain fail-closed and non-routable.
- Bybit V5 response-limit headers are reconciled into durable usage totals only when they confirm the exact reviewed coarse outer contract; endpoint/UID limits remain dynamic and explicitly non-routable until modeled. Gate's official public TradFi stock contract is now static and IP-scoped at 5 qps per public stock endpoint, so the runtime applies a conservative aggregate capability window without inventing a response-header dependency.
- Tokenized live probes now activate transport telemetry and require positive request/response-byte observations for every public tokenized adapter discovery and quote/order-book read, so a normalized record cannot masquerade as an unobserved integration.
- Persisted tokenized products now have an opt-in bounded quote-refresh path. It routes each provider-asset ID through the durable `TOKENIZED_ASSETS` runtime contract, records separate token `LatestPriceSnapshot` rows, and is disabled by default; enabling it requires `TOKENIZED_ASSET_REFRESH_ENABLED` plus a conservative `TOKENIZED_ASSET_REFRESH_MAX_ASSETS` in the backend/worker environment.
- CoinGecko metadata resolution now uses ranked `/search` results for provider-ID lookup rather than the first ambiguous `/coins/list` row. This prevents a ticker such as BTC from resolving to an unrelated token. The runtime reserves two requests for the compound search-plus-profile operation, and the credentialed live probe verified the canonical Bitcoin result with two observed upstream requests.
- Alpaca OHLCV history now estimates and reserves every conservative 1,000-bar page for explicit and latest-range fetches, including bulk backfill, before following `next_page_token`. This prevents long historical requests from being charged as one request against Alpaca's documented account window.
- Coinbase and Kraken crypto OHLCV history now follows the provider page cursors/ceilings (300 and 720 candles respectively) for explicit and latest-range reads; market-data and bulk-fetch paths reserve the calculated page count before execution, and boundary duplicates are deduplicated.
- Twelve Data history now splits ranges at the documented 5,000-point response ceiling using bounded start/end requests; explicit/latest/bulk paths reserve the corresponding credit cost before execution and deduplicate boundary observations.
- Marketstack EOD history now follows the provider's returned pagination metadata rather than treating a response as a single page; progress guards prevent cursor loops, and explicit/latest/bulk paths reserve a conservative calendar-day page count against the monthly request budget.
- Compound discovery accounting is now explicit: Nasdaq reserves two transport calls for its two-file refresh across both discovery and reconciliation operation families, while FINRA OTC's partition plus response-dependent DAPI pages require operator-supplied positive reviewed operation costs for both families and otherwise fail closed instead of being charged as one request.
- Robinhood tokenized quote accounting now reserves four requests for the asset lookup plus the provider-specific three-attempt 429 retry ceiling; successful two-request reads settle observed usage without permitting an unsafe under-reserved retry path.
- FINRA authenticated short-interest and Daily List calls now reserve two
  requests: the cold OAuth token exchange plus the dataset POST. Warm token
  caches may consume one upstream call, but the runtime remains conservative
  and never undercounts a cold process.
- SEC EDGAR profile and filing-event operations now reserve two requests for a
  cold ticker-directory lookup plus submissions read. The keyless live profile
  probe clears its caches and verifies the compound transport observation.
- The manifest-driven market-data live matrix now applies the same positive transport-observation gate to all available keyless and credentialed provider reads. Directory pagination is cache-aware: only the cache-populating HTTP read requires new bytes, while subsequent local pages are still checked for completeness without inventing network activity.
- 429/418/quota responses are typed, reset-aware, circuit-opening capacity failures. HTTP OHLCV routes expose 503 plus `Retry-After`/provider metadata instead of presenting capacity exhaustion as “no data”.
- Optional REST adapters no longer turn missing credentials or upstream HTTP failures into a false empty success; missing configuration is explicit and rate-limit responses remain observable by the runtime.
- Coordination note: `feat/etf-holdings-constituents` is developing in parallel and may provide overlapping ETF identity/discovery evidence. This branch preserves ETF adapter ownership there; any overlap should be reconciled at integration through the canonical identity contract.
- Validation: the latest routing/provider-admin/quota/secret-wiring focused suite passes `105/105`; Ruff lint, compilation, workstream validation, and diff checks pass. The authoritative Docker-backed combined gate passes `1831/1831` with `80.34%` line coverage and 89 warnings against the repository's `75%` gate; isolated PostgreSQL/Redis testcontainer session `f2a9e402-915a-4dd1-a23c-443fa440c6d4` was cleaned successfully without host-wide pruning. The latest forced network-enabled manifest run at `2026-09-09T19:26:35Z` collected 32 cases: 27 passed with positive transport observations, while EDGAR_USER_AGENT plus the exact Alpaca, Tradier, and MarketData.app credential domains failed preflight; the wrapper returned exit code `2` and made no acceptance claim. A prior run with a temporary non-secret EDGAR User-Agent passed 29/32. The Alpha Vantage IPO-calendar case still proves a valid header-only empty CSV response, not a positive event row. The runner now reports FINRA OTC's operation-cost/terms/completeness/redistribution/poll controls as explicit safety gaps, alongside FRED, FINRA async, Nasdaq polling, xStocks, Bybit endpoint/UID state, and Tiingo/FMP byte-bound controls. The resolver and admin status now enforce those controls instead of merely displaying them. The registry-wide contract guard, backend env-example alignment, complete live-matrix transport-observation assertions, typed provider error-envelope assertions, and changed-surface checks remain green.
- Latest security validation adds centralized credential redaction at the typed-error and runtime persistence boundaries. The focused provider-error/persistence suite passed `76/76`; Ruff, compilation, and diff checks passed; the authoritative Docker-backed gate passed `1807/1807` with `80.22%` coverage and 89 warnings, using testcontainer session `bf95b231-3b15-44d6-b58b-55bc4bb6562b`, which was cleaned successfully. This protects durable request logs, health state, capacity events, and live-probe failure text from configured credentials and credential-bearing URL/header values.
- The direct-live usage-ledger boundary is now covered by a focused `9/9` suite and an explicitly disabled `30`-case matrix (`30` skips, no external calls). The first post-change Docker gate encountered one isolated testcontainer outage (`1685` passed, one test failure followed by `125` connection-refused setup errors); the targeted test passed in isolation and the immediate authoritative rerun passed `1810/1810` with `80.22%` coverage and 89 warnings. Testcontainer sessions `8176cb3f-fea3-43ca-b2b4-2c87b719c68d` and `94fd001d-c1b0-42bc-a226-7259a5295b27` were cleaned without a host-wide prune. Direct live probes now retain only measured per-provider operation/request/response-byte totals in the external usage ledger, with no credentials or payloads.
- A documentation-shape audit found and corrected a real Tradier adapter defect: official JSON history/search responses are nested (`history.day|week|month` and `securities.security`) and may collapse singleton arrays into objects. The adapter now normalizes those forms without flattening arbitrary payloads; optional-provider fixtures pass `14/14`, and the authoritative Docker-backed gate passes `1811/1811` with `80.23%` coverage and 89 warnings (testcontainer session `a5538d6b-6506-4ec3-97bd-094337c48f91` cleaned without host-wide prune).
- EODHD's documented EOD period selector is now mapped for daily, weekly, and monthly history (`d`, `w`, `m`) instead of silently limiting the adapter to daily bars. The weekly/monthly request paths are fixture-covered and the configured live probe passed all three bounded reads (daily/weekly/monthly), recording 3 upstream requests and 2,421 response bytes in the external usage ledger; the focused optional-provider suite passes `16/16`, and the authoritative Docker-backed gate passes `1813/1813` with `80.24%` coverage and 89 warnings (testcontainer session `d0e6d629-9842-4720-8e7e-b0f8ceec47f5` cleaned without host-wide prune).
- Tiingo's documented single-object daily metadata response is now parsed directly instead of being passed through the list-only row normalizer. The metadata fixture and configured history-plus-profile live case pass (`2` upstream requests, `1,536` response bytes); the final focused optional-provider suite passes `17/17`, and the authoritative Docker-backed gate passes `1814/1814` with `80.24%` coverage and 89 warnings (testcontainer session `29e337a8-f4cf-4d18-8e1f-78a0e1f508ba` cleaned without host-wide prune).
- Finnhub earnings normalization now honors the documented `actual`/`estimate` fields (while retaining compatibility with explicit EPS aliases), so event records no longer lose provider EPS values. The fixture and configured profile-plus-earnings live case pass (`2` requests, `978` response bytes); the final focused optional-provider suite passes `18/18`, and the authoritative Docker-backed gate passes `1815/1815` with `80.26%` coverage and 89 warnings (testcontainer session `e0aefc5a-9e53-4338-b81b-8645d2701525` cleaned without host-wide prune).
- Twelve Data timestamp handling now follows its documented timezone contract: intraday requests explicitly request UTC, while daily/weekly/monthly timestamps are localized using the response's exchange timezone and converted to canonical UTC. The fixture suite passes `19/19`; the configured live case passed daily plus 5-minute reads (`2` requests, `20,405` response bytes); and the authoritative Docker-backed gate passes `1816/1816` with `80.26%` coverage and 89 warnings (testcontainer session `b11d4dcf-b94a-4971-a098-fc0df4af359d` cleaned without host-wide prune).
- Finnhub's documented forward earnings calendar is now exposed through the provider's `market_events` capability. The adapter normalizes the `earningsCalendar` envelope, preserves the provider's event metadata, applies inclusive date bounds, and the fixture plus configured profile/history/calendar live case pass (`3` requests, `170,868` response bytes); the focused optional-provider suite passes `20/20`, and the authoritative Docker-backed gate passes `1817/1817` with `80.27%` coverage and 89 warnings (testcontainer session `4573fc22-6aa1-4fa2-95f3-063376a1b092` cleaned without host-wide prune).
- Alpha Vantage's existing IPO-calendar adapter is now explicitly capability-covered: the provider registry exposes `market_events`, the CSV event normalization/date-bound behavior has a fixture, and the focused new-provider plus optional-provider suites pass `119/119`. A dedicated live case now validates the current provider response as a 68-byte CSV header with no published IPO rows, preserving an honest empty result rather than fabricating an event; a positive IPO row remains unobserved.
- Optional-provider transport failures now cannot leak credentials through direct/live tracebacks: `_RESTProvider` converts HTTP status and request failures into redacted typed errors, preserves 429/418 headers and parsed retry timestamps, and the scrubber recognizes `api_token` query parameters. EODHD Fundamentals now calls the documented `/api/v1.1` endpoint; its free-plan 403 is tested as an explicit non-entitlement while FMP profile succeeds. The corrected bounded metadata live suite passes `3/3` with successful ledger totals of EODHD `4` requests/`2,522` bytes and FMP `2` requests/`3,860` bytes. The focused optional/error suite passes `23/23`, and the authoritative Docker-backed gate passes `1821/1821` with `80.28%` coverage and 89 warnings (testcontainer session `b52476a2-17c1-4823-b48d-980707fdb20c` cleaned without host-wide prune).
- Bybit's official public rate-limit documentation was rechecked during the tokenized live validation. The bounded xStocks instrument and ticker reads passed with positive transport evidence, but the current unauthenticated public edge emitted none of the documented `X-Bapi-Limit`, `X-Bapi-Limit-Status`, or `X-Bapi-Limit-Reset-Timestamp` headers. The live assertion now accepts only the allow-listed header names when present and records their absence as evidence; no endpoint/UID allowance is inferred, so Bybit remains non-routable until those dynamic dimensions and reliable native state are modeled.
- xStocks' official legal notice was also rechecked: the products are not available in the United States or to U.S. persons. The entitlement seed and provider documentation now record this as a separate jurisdiction/redistribution gate; public observations may be retained for research, but xStocks cannot become an eligible US routing source merely because a quota is later discovered.
- The manifest live-runner safety preflight now reports that xStocks legal gate together with the unknown public quota; focused runner checks pass, and the authoritative Docker-backed gate passes `1821/1821` with `80.28%` coverage.
- Alpha Vantage's usage profile now explicitly reserves one request for each current single-query operation (search, daily/latest history, current price, listing discovery, and IPO events). The quota-contract focused suite passes `47/47`; no generic operation-cost fallback is used for these paths, and any future pagination/compound lookup must update the reviewed profile before routing.
- The quota ledger now also records explicit one-request costs for the corresponding single-request surfaces of Alpaca, Massive, FRED, OpenFIGI, Coinbase, Kraken, Marketstack, Finnhub, FMP, Tiingo, and Tradier. Range/pagination-dependent history operations remain caller-estimated or byte-bound gated rather than being silently charged as one request; the focused quota suite covers this profile set.
- Marketstack discovery now requires the explicit non-secret `MARKETSTACK_DISCOVERY_EXCHANGE` setting and preserves the selected MIC in the request; the former silent `XNYS` default was removed so this supplementary provider cannot be mistaken for complete US venue coverage.
- The manifest runner now reports Marketstack discovery scope separately from the credential preflight, and the manual GitHub workflow passes `MARKETSTACK_DISCOVERY_EXCHANGE` from an environment variable without treating an unset value as a live skip.
- Provider-policy diagnostics now expose each adapter's required and missing environment-variable names without exposing configured values, making credential and non-secret scope gaps directly inspectable by operators.
- Provider-policy diagnostics now separately expose missing routing-safety controls for FINRA async result bytes and Tiingo/FMP operation-byte maps, keeping credential status distinct from quota-admission readiness.
- README provider-routing examples now match the API-first Alpaca/EDGAR/OpenFIGI defaults and explicitly keep yfinance limited to disabled legacy/options compatibility, with a regression assertion preventing documentation drift.
- Massive's legacy `MARKETDATA_API_KEY` alias is represented alongside `MASSIVE_API_KEY`; diagnostics now treat either configured alias as satisfying the requirement rather than reporting a false missing key. The focused provider-admin suite passes 24/24.
- Provider-policy admin edits now reject non-positive concurrency/rate/burst/cooldown values and require an explicit complete replacement `quota_contract` plus `quota_source` provenance whenever numeric limits are changed; focused router tests cover missing and incomplete contracts, and runtime routing remains fail-closed.
- Quota-contract governance now also keeps incomplete operator replacements explicitly unverified: `quota_verified_at` is cleared for unknown/untracked dimensions, while complete contracts retain their verification timestamp. This prevents admin diagnostics from presenting a fail-closed contract as documentation-approved.
- Runtime seeding also repairs stale existing rows by clearing `quota_verified_at` whenever the current contract is incomplete; FRED and Tiingo/FMP bandwidth-gate regressions cover this path.
- Complete quota-contract replacements now require both policy-level `quota_scope` and `quota_source` as well as complete per-dimension fields before verification; focused router coverage rejects missing scope.
- Runtime admission now enforces that same policy-level scope/source provenance, so migrated or externally edited policies cannot bypass the admin contract checks; the focused quota/router/runtime suite passes `99/99`, and unknown/untracked constraints remain visible but non-routable.
- Operator-cleared `quota_scope`/`quota_source` values are now preserved as a quarantine instead of being silently reseeded by a later diagnostics read; provenance-only edits clear `quota_verified_at` immediately and require a fresh complete replacement contract.
- Operator-cleared `quota_contract: null` values are also preserved across diagnostics and runtime seeding; explicit contract removal remains a routing quarantine until a complete, provenance-backed replacement is supplied.
- Optional providers' inherited `latest_price` paths now carry explicit `get_current_price` operation costs; Tiingo/FMP reviewed byte maps must include that bounded latest-history operation, and Marketstack's quote path no longer relies on an implicit one-request charge.
- Deep-history `bulk_fetch:*` calls now have explicit operation costs for EODHD, MarketData.app, Tiingo, and FMP. Tiingo/FMP byte-bound admission additionally requires a reviewed `bulk_fetch` response bound, so the deep-history worker cannot bypass bandwidth accounting or fall back to an uncharged operation.
- Quota admission is now globally fail-closed for unknown operations, including providers with simple request-count contracts; no provider may silently inherit a one-request charge. Alpha Vantage, FRED, Finnhub, and Tradier `bulk_fetch` operations and the FRED `fetch_rfr_ohlcv` path have explicit reviewed costs, while paginated/weighted providers continue to require caller estimates or reviewed byte bounds.
- Validation: the focused quota/runtime/registry suite passed `94/94`, the support/quota/runtime rerun passed `81/81`, Ruff, compilation, and diff checks passed, and the authoritative Docker-backed combined gate passed `1835/1835` with `80.33%` line coverage and 89 warnings. Testcontainer session `bb89a147-2fde-41cf-8141-c7edce0ca476` was cleaned without host-wide pruning.
- Operation-cost validation now rejects malformed, non-positive, boolean, and non-finite reviewed values and caller overrides instead of coercing them to one unit. The final focused suite passed `98/98`; the final Docker-backed combined gate passed `1835/1835` with `80.33%` line coverage and 89 warnings. Testcontainer session `b38e41ed-b547-41f1-a1b1-093780a898a9` was cleaned without host-wide pruning.
- The post-change forced live matrix at `2026-09-09T22:55:11Z` collected 32 cases: 29 passed with positive transport observations and exactly three failed credential preflight (`ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, `MARKETDATA_APP_API_KEY`). The wrapper returned exit code `2` and made no acceptance claim; known FINRA/FRED/Nasdaq/xStocks/Bybit/Tiingo/FMP governance controls remain explicitly fail-closed, and the measured usage receipt was appended only to the operator-owned external ledger.
- A fresh forced live matrix at `2026-09-09T22:04:20Z` again collected 32 cases: 29 passed with positive transport observations and the exact Alpaca, Tradier, and MarketData.app credential domains failed preflight. The wrapper returned exit code `2` and made no acceptance claim; the run used only existing configured keys plus temporary non-secret `EDGAR_USER_AGENT` and `MARKETSTACK_DISCOVERY_EXCHANGE=XNAS` overrides. Its external usage receipt was appended to the operator-owned ledger without credentials or payloads. The routing-safety gates remain explicit for FINRA async bytes, FINRA OTC controls, FRED controls, Nasdaq polling, xStocks quota/legal eligibility, Bybit endpoint/UID state, and Tiingo/FMP operation-byte maps.
- A fresh forced live matrix at `2026-09-09T21:38:58Z` again collected 32 cases: 29 passed with positive transport observations and the exact Alpaca, Tradier, and MarketData.app credential domains failed preflight. The wrapper returned exit code `2` and made no acceptance claim; the run used only the existing configured keys plus temporary non-secret `EDGAR_USER_AGENT` and `MARKETSTACK_DISCOVERY_EXCHANGE=XNAS` overrides. Its external usage receipt was appended to the operator-owned ledger without credentials or payloads.
- The latest forced live matrix at `2026-09-09T19:56:03Z` used the existing external keys plus temporary non-secret `EDGAR_USER_AGENT` and `MARKETSTACK_DISCOVERY_EXCHANGE=XNAS` overrides: 29 of 32 collected cases passed, while the exact Alpaca, Tradier, and MarketData.app credential domains were absent. The wrapper returned exit code `2` and made no acceptance claim. Next: restore owner authentication for the `jagnelo` GitHub account and verify/populate the environment-scoped live secrets and safety variables, provide the missing credential domains through the external secret store, configure a deployment-owned non-secret EDGAR User-Agent, and resolve any provider-specific failures. FRED's controls should be published only after review. FINRA OTC now additionally requires complete positive reviewed operation costs for both runtime operation families plus source terms, completeness, redistribution, and polling controls. Nasdaq polling, xStocks quota and legal eligibility, Bybit xStocks endpoint/UID header state, complete reviewed Tiingo/FMP byte maps, complete production NMS/OTC reconciliation, and shadow activation remain gates. If Tiingo/FMP are to be promoted, operations must supply complete provider-reviewed operation byte-bound maps in the deployment secret/config store; empty/partial maps are intentionally safe and non-routable. The NMS/SEC directory adapters and bounded public evidence are implemented; FINRA Daily List supplies documented OTC lifecycle deltas, and the OTC Security Master adapter proves the current public snapshot end-to-end with its official synchronous quota contract but remains intentionally non-routable until its source terms/configuration/review controls are approved. Only then may this workstream move to `ready_for_human_review`; deployment and the separately approved 30-day shadow activation remain out of scope.
- The root worktree has unrelated user changes in `docs/etf-provider-universe.md`; they are intentionally preserved and out of scope.
- The workflow session record `ops/workstreams/feat-market-data-provider-platform/session.json` is intentionally updated by session lifecycle commands and may be dirty at checkpoint time.
- This operational checkpoint owns `docs/provider-live-validation.md`, `ops/workstreams/feat-market-data-provider-platform/handoff.md`, `ops/workstreams/feat-market-data-provider-platform/validation.jsonl`, and `ops/workstreams/feat-market-data-provider-platform/session.json`; no frontend or ETF-worktree files are part of this context.

- Strict operation-cost execution hardening: `_usage_cost_for_operation` now accepts a caller override only through the same positive finite numeric validator used by admission, and `execute_provider_call` no longer converts an override or missing map to a post-admission one-unit fallback. Unknown or malformed costs therefore raise `ProviderQuotaUnknownError` before reservation. Focused quota/runtime/registry/support tests pass `98/98`; the authoritative Docker-backed gate passes `1835/1835` with `80.34%` line coverage and 89 warnings, using testcontainer session `70860336-c753-4b11-bdbf-72e643772e40`, cleaned without host-wide pruning. The live matrix remains blocked at the exact 29/32 result recorded above; no acceptance claim is made.

- Dimension-bound execution hardening: required non-request quota dimensions now require positive integral reviewed bounds during both admission and reservation. Malformed, fractional, boolean, zero, negative, or missing byte/credit/record bounds cannot be admitted and cannot be coerced to a default unit during reservation. The focused quota/runtime/registry/support suite passes `98/98`; Ruff, compilation, and diff checks pass; the authoritative Docker-backed gate passes `1835/1835` with `80.33%` line coverage and 89 warnings using testcontainer session `afffe209-75ec-4338-b6df-92529fddc5f0`, cleaned without host-wide pruning. Live credential and provider-governance blockers remain unchanged and no acceptance claim is made.

- Tiingo/FMP byte-bound diagnostics are now sourced from the same complete operation set used by `provider_rate_limit_seed`: `fetch_ohlcv`, `fetch_latest_ohlcv`, `get_current_price`, `bulk_fetch`, plus each provider's discovery/profile operation. A partial map therefore remains visibly missing at the provider-admin boundary instead of being reported complete while runtime promotion still rejects it. The focused quota/runtime/registry/support suite passes `98/98`; the authoritative Docker-backed gate passes `1835/1835` with `80.33%` line coverage and 89 warnings using testcontainer session `fed69565-180c-4121-b1da-083621617313`, cleaned without host-wide pruning. Live credential and governance blockers remain unchanged.

- Malformed byte-bound controls now fail closed across all three promotion surfaces: JSON booleans and other non-integral values are rejected by settings parsing, provider-admin routing diagnostics, and the manifest live-preflight check instead of being coerced to `1`. The focused provider secret/registry/quota/runtime/support suite passes `105/105`; Ruff, compilation, and diff checks pass; the authoritative Docker-backed combined gate passes `1835/1835` with `80.33%` line coverage and 89 warnings using testcontainer session `e88c0ea3-1c1e-4746-ad8b-38658f706f4f`, cleaned without host-wide pruning. Live credential and governance blockers remain unchanged, and no acceptance claim is made.

- Strict positive-integer validation now covers the remaining provider-specific admission controls: FINRA async result-byte bounds, FINRA OTC polling intervals, and FRED reviewed requests/minute. Booleans and non-integral values are rejected in routing diagnostics and profile promotion rather than coerced; the focused registry/quota/secret suite passes `79/79`, Ruff/compilation/diff checks pass, and the authoritative Docker-backed combined gate passes `1836/1836` with `80.34%` line coverage and 89 warnings using testcontainer session `8d2f1c1b-b568-49d3-9c42-6906d00ba07e`, cleaned without host-wide pruning. Live credential and governance blockers remain unchanged; no acceptance claim is made.

- Reviewed provider terms flags now require actual boolean `true` values in both quota seeding and routing diagnostics. Truthy strings cannot satisfy FINRA OTC or FRED review gates. The focused registry/quota/secret suite passes `80/80`; Ruff, compilation, and diff checks pass; the authoritative Docker-backed combined gate passes `1837/1837` with `80.34%` line coverage and 89 warnings using testcontainer session `12ddd0df-d4ab-4ec5-bc05-59f85bd92c0c`, cleaned without host-wide pruning. Live credential and governance blockers remain unchanged; no acceptance claim is made.

Update this handoff at each coherent boundary.

- Generic reusable breadth now participates in the shared evaluator preflight.
  The route derives the minimum local history from the declared condition tree,
  assesses the already-loaded adjusted/raw bars with no provider I/O, withholds
  members that are missing, stale, or below the required history, and returns a
  serialized `coverage_preflight` report. The focused preflight unit suite is
  `5/5`; focused workspace breadth integration is `2/2`; Ruff, compilation, and
  diff checks pass. Source checkpoint: `b975c68a`. Benchmark-family breadth,
  future non-Strategy signal engines, and separate evaluator run-status
  persistence remain open. No frontend or ETF-provider adapter files changed.

- The complete Docker-backed backend gate after the generic breadth change
  passed `2,398/2,398` with `81.37%` coverage and 89 known warnings. Isolated
  testcontainer session `3073c921-11a6-4eb6-baf8-82475c0faf84` was cleaned
  without host-wide pruning. This validates the source checkpoint only; the
  provider-governance, migration-graph, deployment-secret, and shadow gates
  remain open.

- Benchmark-family breadth now performs per-metric cached-bar preflight and a
  separate cap-benchmark preflight. This preserves valid short-history metrics
  while deferring only metrics whose own lookback is unavailable. The focused
  integration case passes `1/1`; the complete Docker-backed gate passes
  `2,398/2,398` with `81.38%` coverage and 89 warnings. Testcontainer session
  `8cbf54f3-d84e-4730-b169-b1ab0eeb5b75` was cleaned without host-wide pruning.
  Source checkpoint: `f9a2081e`; future non-Strategy signal engines and
  separate evaluator run-status persistence remain open. No frontend or ETF
  provider-adapter files changed.

- Tokenized corporate-action persistence is now a separate backend-only path. xStocks history and upcoming feeds, plus Robinhood's combined feed, run through the exact durable `fetch_tokenized_corporate_actions` runtime operation and persist provisional canonical `MarketEvent` rows with raw payloads. Linkage requires an explicit provider asset ID or a unique stored token symbol; unresolved actions remain visible and later upsert can attach a newly resolved instrument. Bybit, Gate, and Kraken adapters without an action endpoint are reported as unsupported and never invoked. A disabled-by-default 15-minute worker schedule is controlled independently by `TOKENIZED_EVENT_REFRESH_ENABLED`, `TOKENIZED_EVENT_REFRESH_MAX_PROVIDERS`, and `TOKENIZED_EVENT_REFRESH_PAGE_SIZE`, propagated to local and RPi backend/worker Compose environments.

- Focused tokenized service/worker tests passed `31/31`; Ruff, compilation, and diff checks passed. The authoritative Docker-backed combined backend gate initially lost its isolated PostgreSQL test container after `1739` passes and produced only connection/setup errors; after cleanup, the clean retry passed `1853/1853` with `80.37%` line coverage and 89 warnings using testcontainer session `17d83520-7442-4bf0-85fe-b51613bed5d7`, cleaned without host-wide pruning. This successful retry is the acceptance evidence; the transient failed attempt is retained in `validation.jsonl`.

- Files changed in this boundary are `backend/app/config.py`, `backend/app/services/market_data_persistence.py`, `backend/app/services/tokenized_assets.py`, `backend/app/tasks/data_tasks.py`, `backend/app/workers/arq_worker.py`, `backend/tests/unit/services/test_tokenized_assets.py`, `backend/tests/unit/workers/test_arq_worker.py`, `deploy/rpi/compose.yml`, `docker-compose.yml`, `docs/data-providers.md`, `docs/deployment.md`, and `ops/workstreams/feat-market-data-provider-platform/plan.yaml`; no frontend or ETF worktree files were touched. Environment examples and validation/session metadata are also updated without storing credentials.

- FMP now exposes the stable `earnings-calendar` endpoint through the `market_events` capability. The adapter preserves provider EPS/revenue fields in raw provenance, applies inclusive date bounds, and has fixture plus quota/byte-bound coverage. The configured live profile/history/calendar probe passed with 3 upstream requests and 9,444 response bytes; Ruff, compilation, and diff checks passed; the authoritative Docker-backed combined gate passed `1839/1839` with 80.35% line coverage and 89 warnings using isolated PostgreSQL/Redis testcontainer session `c2dc85cf-f806-4840-89a7-bbded5c76194`, cleaned without host-wide pruning. FMP remains non-routable until the operator supplies a complete reviewed per-operation byte-bound map; analyst-estimate/price-target surfaces remain unimplemented pending entitlement review.

- The refreshed complete live matrix at 2026-09-10T00:32:38Z collected 32 cases: 29 passed with positive transport observations, including the new FMP earnings-calendar path, and exactly three failed credential preflight for `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`. The wrapper returned exit code 2 and made no acceptance claim. Routing safety remains fail-closed for the documented FINRA, FRED, Nasdaq, xStocks, Bybit, and Tiingo/FMP review controls; the non-secret EDGAR User-Agent and Marketstack discovery scope were supplied only as temporary live-run overrides.

- Massive now exposes the documented `reference/ipos` endpoint through the shared `market_events` capability. The adapter keeps one request per call, applies inclusive date bounds locally, supports `ipo_status` filtering and explicit cursor-page continuation, preserves raw provider rows/status semantics, and charges an explicit one-request operation cost. Focused provider/quota tests passed `159/159`; the authoritative Docker-backed combined backend gate passed `1841/1841` with `80.34%` line coverage and 89 warnings using isolated PostgreSQL/Redis testcontainer session `8b95f582-5c08-4236-b100-0d1b8fdd5fe7`, cleaned without host-wide pruning. The configured Massive search plus bounded IPO-calendar live case passed `1/1`; the test permits a valid empty calendar window and does not fabricate an IPO row. Massive remains supplementary until the broader market-event persistence/reconciliation path and routing review are complete.

- The post-change complete live matrix rerun collected 32 cases with 29 passes, including the updated Massive search plus IPO-calendar path, and the same three exact credential preflight failures for `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`. It returned exit code 2 and made no acceptance claim. Provider-safety blockers remain explicit for FINRA async/OTC, FRED, Nasdaq, xStocks, Bybit, and Tiingo/FMP; temporary EDGAR contact and Marketstack venue scope were supplied only as non-secret live overrides.

- Massive now also exposes the documented `marketstatus/upcoming` feed as normalized `market_holiday` events, preserving exchange, status, open/close, date, and raw payload fields. Its separate one-request operation cost prevents an IPO read from silently becoming a compound quota charge. Focused provider/quota tests passed `160/160`; the authoritative Docker-backed combined backend gate passed `1842/1842` with `80.34%` line coverage and 89 warnings using isolated PostgreSQL/Redis testcontainer session `1a301187-3a65-453a-ae26-145137da0825`, cleaned without host-wide pruning. The configured Massive reference, IPO, and market-holiday live case passed `1/1`; valid empty forward windows remain acceptable and no event is fabricated.

- The post-holiday-change complete live matrix rerun collected 32 cases with 29 passes, including all three Massive reads, and exactly the same three credential preflight failures for `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`. It returned exit code 2 and made no acceptance claim; provider-safety blockers remain explicit and unchanged.

- Tokenized provider transport is now fail-closed and typed at the shared adapter boundary: network failures and non-429 HTTP/JSON failures become redacted `ProviderResponseError` instances, HTTP 418/429 responses become redacted `ProviderRateLimitError` instances with only allow-listed provider headers and parsed `Retry-After` metadata, and the finite Robinhood retry consumes only that typed 429 path. The tokenized unit suite passed `12/12`; Ruff, compilation, and diff checks passed. The authoritative Docker-backed combined backend gate passed `1844/1844` with `80.33%` line coverage against the 75% threshold, and the isolated PostgreSQL/Redis testcontainer session was cleaned without host-wide pruning.

- The final transport regression boundary adds explicit 503 and malformed-JSON coverage: the tokenized unit suite passes `14/14`, Ruff, compilation, and diff checks pass, and the authoritative Docker-backed combined backend gate passes `1846/1846` with `80.34%` line coverage and 89 warnings against the 75% threshold. Testcontainer session `f65314d8-3cfd-4e8b-a707-7a8616026f97` was cleaned without host-wide pruning.

- Retry metadata now also rejects non-finite provider `Retry-After` values rather than constructing an invalid delay. The final tokenized unit suite passes `15/15`; the authoritative Docker-backed combined backend gate passes `1847/1847` with `80.34%` line coverage and 89 warnings, using isolated testcontainer session `c44aa43d-23c6-4690-9853-63e3d5703bc5`, cleaned without host-wide pruning. Ruff, compilation, and diff checks pass.

- The credentialed tokenized live suite passed all `5/5` public probes after this transport change. The refreshed complete manifest matrix at `2026-09-10T01:04:34Z` collected 32 cases: 29 passed with positive transport observations, while exactly three failed credential preflight for `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`; the wrapper returned exit code 2 and made no acceptance claim. FINRA/FRED/Nasdaq/xStocks/Bybit/Tiingo/FMP governance controls remain explicitly fail-closed, and no secret values or payloads were persisted.

- Tokenized event coverage is now included in the live boundary: xStocks and Robinhood corporate-action reads both pass with positive transport observations, and malformed Robinhood event rows are filtered before optional symbol matching. Focused tokenized tests pass `17/17`, the expanded tokenized live suite passes `7/7`, Ruff/compilation/diff checks pass, and the authoritative Docker-backed combined backend gate passes `1849/1849` with `80.36%` line coverage and 89 warnings using isolated testcontainer session `520cd031-234e-4ef9-8917-7204c50e683e`, cleaned without host-wide pruning.

- The refreshed complete manifest matrix at `2026-09-10T01:52:55Z` collected 34 cases: 31 passed, including all seven tokenized probes and both tokenized corporate-action endpoints. Exactly three cases failed credential preflight for `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`; the wrapper returned exit code 2 and made no acceptance claim. FINRA/FRED/Nasdaq/xStocks/Bybit/Tiingo/FMP governance controls remain explicitly fail-closed, and only redacted usage telemetry was appended externally.

- Tokenized corporate actions now use a dedicated `TOKENIZED_CORPORATE_ACTIONS` capability rather than the broader catalogue/quote capability. The protocol, registry resolver/export, PostgreSQL enum migration `3e4f5a6b7c8d`, default chain seed, service routing, and provider-availability representative probe are aligned; xStocks and Robinhood advertise the capability, while Bybit, Gate, and Kraken remain explicitly unsupported for action feeds. Focused capability/tokenized/availability/registry coverage passed `47/47`, and Ruff, compilation, and diff checks passed.

- The clean authoritative Docker-backed combined backend gate after this capability change passed `1855/1855` with `80.37%` line coverage and 89 warnings; isolated PostgreSQL/Redis testcontainer session `5ba942a1-788a-4f7b-812c-235563a717b0` was cleaned without host-wide pruning. The credentialed tokenized live suite passed `7/7` in `14.20s` using the existing operator-owned environment file, with no credentials or provider payloads printed or persisted. The first full-gate attempt failed only because the new enum was not yet represented in `provider_availability.representative_request`; that gap was fixed before the successful rerun.

- Files changed in this boundary are `.env.example`, `backend/.env.example`, `backend/app/config.py`, `backend/app/models/provider_runtime.py`, `backend/app/providers/__init__.py`, `backend/app/providers/base.py`, `backend/app/providers/registry.py`, `backend/app/services/provider_availability.py`, `backend/app/services/tokenized_assets.py`, `backend/alembic/versions/3e4f5a6b7c8d_add_tokenized_corporate_action_capability.py`, `backend/tests/unit/providers/test_tokenized.py`, `backend/tests/unit/services/test_provider_registry.py`, `backend/tests/unit/services/test_tokenized_assets.py`, `docker-compose.yml`, `docs/data-providers.md`, and this workstream metadata. No frontend or ETF worktree files were touched.

- The complete manifest-driven live matrix after the dedicated-capability commit collected 34 cases: 31 passed and exactly three failed credential preflight for `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`. All seven tokenized probes passed, including both corporate-action reads; the wrapper returned exit code `2` with no acceptance claim. FINRA async/OTC, FRED, Nasdaq, xStocks, Bybit, Tiingo/FMP, GitHub environment, NMS/OTC reconciliation, and shadow-activation gates remain explicitly unresolved and fail-closed.

- At `2026-09-10T03:07:56Z`, the lifecycle status refresh synchronized the branch/session hashes to `d5783ea98520318ad68e3cdb811eaf43584a3deb`. The Docker daemon was not reachable from this worktree (`unix:///Users/jagnelo/.docker/run/docker.sock`), so no new authoritative PostgreSQL/Redis gate was claimed; the prior clean `1855/1855` Docker-backed result remains the latest valid full-gate evidence. Provider routing and the acceptance state remain unchanged and fail-closed.

- Tradier's code-owned options surface is now complete: documented expiration and current-chain calls normalize OCC provider symbols, calls/puts, quote/open-interest fields, and nested ORATS Greeks into `OptionContractRecord`; both operations have explicit one-request production-token costs, fixture coverage is green, and the credentialed live case will exercise them when `TRADIER_API_KEY` is supplied. The adapter does not infer sandbox entitlement or change the existing production-only quota contract.

- This boundary changed only backend/provider and operational documentation surfaces: `backend/app/config.py`, `backend/app/providers/optional_market_data.py`, `backend/tests/live/test_market_data_providers_live.py`, `backend/tests/unit/providers/test_optional_market_data.py`, `backend/tests/unit/services/test_provider_quota_contract.py`, `docs/data-providers.md`, `docs/provider-live-validation.md`, `docs/project-todos.md`, this handoff, and `validation.jsonl`. No frontend or ETF-worktree file changed.

- The post-change external matrix at `2026-09-10T03:16:52Z` again collected 31/34 cases in 38.03s. The exact three missing credential domains remain `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`; therefore the new Tradier option reads were correctly blocked by explicit preflight rather than treated as skipped proof. All available probes passed, the wrapper returned exit code `2`, and no acceptance claim was made. Provider-specific governance controls remain fail-closed as recorded above.

- Corrected the live routing-safety manifest so FMP's reviewed byte-bound requirement includes the stable `fetch_market_events` operation already required by backend policy. A regression test now guards the complete operation set; the focused secret-wiring suite passes `8/8`, Ruff, compilation, and diff checks pass. This changes no routing entitlement: FMP remains fail-closed until the operator supplies a complete reviewed byte-bound map.

- The complete backend unit suite after this correction passes `1486/1486` with 37 warnings. This is unit evidence only; the latest authoritative Docker-backed full gate remains `1855/1855` because the Docker daemon is unavailable in this worktree.

- The Docker runtime became reachable again and the authoritative combined backend unit/integration coverage gate passed `1857/1857` with `80.36%` line coverage and 89 warnings, above the 75% threshold. Isolated testcontainer session `1848ca60-2c47-437f-a9b1-6ae9c50a05c4` was cleaned without host-wide pruning. This supersedes the earlier unavailable-daemon status; no provider routing or acceptance gate was relaxed.

- The post-correction complete external matrix at `2026-09-10T03:36Z` again collected 34 cases: 31 passed with positive transport observations, while exactly three failed credential preflight for `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`. The FMP byte-bound preflight now reports the complete operation set, including `fetch_market_events`; FINRA/FRED/Nasdaq/xStocks/Bybit/Tiingo/FMP controls remain explicitly fail-closed. The wrapper returned exit code `2` and made no acceptance claim; only redacted usage telemetry was written to the operator-owned external ledger.

- The live-runner/runtime-policy consistency regression now covers every configured byte-bound provider, not just FMP. Focused secret-wiring coverage passes `9/9`; the authoritative Docker-backed combined gate passes `1858/1858` with `80.36%` line coverage and 89 warnings, using isolated testcontainer session `a083b56f-103c-4e47-9b23-fdd6ccfe7a31`, cleaned without host-wide pruning.

- The branch remains backend-only and clean after the consistency guard; no frontend or ETF-constituent adapter paths were modified. The current live matrix remains explicitly blocked only by the three absent provider credential domains plus the documented provider-specific safety/legal controls; no generic quota fallback or acceptance bypass was introduced.

- The workstream audit now points to the authoritative `2026-09-10T03:36Z` 34-case matrix (31 passed, three exact credential preflight failures) rather than the earlier 02:55 run. The lifecycle checkpoint at commit `3efe5f2f` records the current plan hash, synchronized remote head, and zero retained Docker resources; no routing entitlement or acceptance state changed.

- The continuation live matrix at `2026-09-10T03:59Z` reproduced the same 34-case result (`31 passed`, `3` exact credential preflight failures) in `36.12s`; the wrapper returned exit `2` and made no acceptance claim. This is the latest live evidence and leaves the provider-specific safety/legal controls fail-closed.

- A session-aware authoritative backend gate completed at `2026-09-10T04:17Z`: `1858 passed`, `89` warnings, `80.36%` coverage in `384.90s`. Testcontainer session `abb23a71-625c-402e-baa2-3efccac456ec` was cleaned without host-wide pruning; this adds no routing entitlement.

- The new optional cross-session live-ledger observability path passed focused service/router/secret-wiring coverage (`21/21`), Compose/RPi contract rendering, Ruff, and the authoritative backend gate at `2026-09-10T04:33Z`: `1860 passed`, `89` warnings, `80.37%` coverage in `544.22s`. Testcontainer session `247cc1c4-05aa-4571-adac-9709ad237562` was cleaned without host-wide pruning. Direct-test totals remain separate from runtime quota reservations and do not alter routing.

- The authenticated provider-usage router test now proves the optional cross-session ledger fields using a temporary redacted row, not only field presence. The session-aware authoritative gate at `2026-09-10T04:53Z` passed `1860/1860` with `89` warnings and `80.37%` line coverage in `399.55s`; testcontainer session `0e80e4ff-024f-4ca1-b8ab-f5c876922c95` was cleaned without host-wide pruning. Direct-test totals remain separate from runtime quota reservations and do not alter routing.

- The continuation complete live matrix at `2026-09-10T04:57Z` collected 34 cases: `31 passed` in `38.13s` and exactly three failed credential preflight for `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`. It returned exit code `2` and made no acceptance claim; FINRA async/OTC, FRED, Nasdaq, xStocks, Bybit, and Tiingo/FMP controls remain fail-closed. Only redacted usage telemetry was appended externally.

- A cross-session ledger readback at `2026-09-10T05:02Z` found the owner-managed ledger `available` with `549` valid rows, `0` invalid rows, `23` providers, and latest observation `2026-09-10T04:57:52Z`. The diagnostic printed aggregate metadata only; it did not expose credentials or provider payloads, and these direct-test totals remain separate from runtime quota reservations.

- The usage-summary regression now proves that a live-ledger row is exposed separately without changing runtime request totals or durable quota-window availability. Focused usage/router/live-ledger tests passed `13/13`; the authoritative gate at `2026-09-10T05:13Z` passed `1860/1860`, `89` warnings, and `80.38%` line coverage in `388.17s`. Testcontainer session `1cf565df-7b9d-468f-acf8-bcb1349dc51b` was cleaned without host-wide pruning.

- The manual GitHub live workflow now writes the aggregate-only ledger to runner temp storage and uploads it with `actions/upload-artifact` for 90 days under `always()`, including blocked/failed probe runs. Focused wiring/usage tests passed `13/13`; the authoritative gate at `2026-09-10T05:23Z` passed `1860/1860`, `89` warnings, and `80.38%` coverage in `393.90s`. Testcontainer session `ed0b76f0-f94e-4dfe-b994-d9a24c67250c` was cleaned without host-wide pruning. No credentials or payloads enter the artifact, and it remains separate from runtime reservations.

- `docs/project-todos.md` now records the CI receipt persistence boundary as complete while retaining operator reconciliation as an explicit account-scope requirement.

- Added `scripts/merge-provider-live-usage.py`, a lock-protected allow-list sanitizer and deduplicating merger for downloaded local/GitHub receipts. Its focused live-usage/secret-wiring tests passed `12/12`; the authoritative gate at `2026-09-10T05:37Z` passed `1862/1862`, `89` warnings, and `80.38%` coverage in `362.83s`. Testcontainer session `54e72aeb-0d83-480f-812a-d6f90866e154` was cleaned without host-wide pruning. The merger remains operator-only and cannot alter provider routing or runtime reservations.
- Hardened both the external live-ledger reader and `scripts/merge-provider-live-usage.py` to accept only non-negative integers or digit strings; booleans, fractions, negatives, and other coercible values are rejected so usage totals cannot be silently altered. The focused strict-parser suite passed `7/7`; the authoritative gate at `2026-09-10T05:48Z` passed `1862/1862`, `89` warnings, and `80.38%` coverage in `394.96s`. Testcontainer session `8ed2d4ef-04a8-47d2-8129-b228e18885a6` was cleaned without host-wide pruning.
- Alpaca, FRED, and SEC EDGAR now convert network transport failures into redacted typed `ProviderResponseError` failures. They no longer report empty history/events or synthesize a minimal SEC profile on outage; focused provider tests passed `106/106`, and the authoritative gate at `2026-09-10T06:02Z` passed `1865/1865`, `89` warnings, and `80.39%` coverage in `365.39s`. Testcontainer session `9aad314f-c0a9-4fd9-b902-83afd574e391` was cleaned without host-wide pruning.
- Alpaca, FRED, and SEC EDGAR now reject malformed or structurally invalid JSON payloads as typed provider-response failures; focused provider tests passed `109/109`, and the authoritative gate at `2026-09-10T06:14Z` passed `1868/1868`, `89` warnings, and `80.35%` coverage in `544.34s`. Testcontainer session `5050159c-29bd-4cba-8846-54785ab4b75a` was cleaned without host-wide pruning.
- Coinbase, Kraken, and OpenFIGI now preserve typed network/JSON/shape failures instead of returning empty market data or identity results; focused crypto/OpenFIGI/provider-transport tests passed `116/116`, and the authoritative gate at `2026-09-10T06:25Z` passed `1872/1872`, `89` warnings, and `80.35%` coverage in `407.49s`. Testcontainer session `02888682-f032-4f0a-8669-efc552fa9fd2` was cleaned without host-wide pruning.
- Alpha Vantage and CoinGecko now preserve typed transport and malformed-JSON failures through shared helpers, including CoinGecko ranked symbol resolution; focused provider/transport tests passed `115/115`, and the authoritative gate at `2026-09-10T06:35Z` passed `1876/1876`, `89` warnings, and `80.36%` coverage in `389.90s`. Testcontainer session `795d0dc3-df37-451b-af3c-62eb6ad3d0ce` was cleaned without host-wide pruning.
- Binance, Nasdaq Trader, FINRA Query API, and the FINRA OTC directory now preserve typed redacted failures for transport, malformed JSON, invalid shapes, and incomplete directory responses; Binance no longer silently drops malformed candle rows, and Nasdaq accepts the official `ACT Symbol` plus approved `Symbol` mirror header variation with identity validation. Focused provider/directory/instrumentation tests passed `138/138`; the corrected authoritative gate at `2026-09-10T06:59Z` passed `1885/1885`, `89` warnings, and `80.37%` coverage in `369.50s`. Testcontainer session `43c93bbd-d914-4259-ad39-21197ad67ed7` was cleaned without host-wide pruning.
- The post-change complete live matrix at `2026-09-10T07:03:12Z` again collected 34 cases: `31 passed` in `40.75s` and exactly three credential preflight failures for `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`. The wrapper returned exit code `2` and made no acceptance claim; FINRA async/OTC, FRED, Nasdaq polling, xStocks, Bybit, and Tiingo/FMP controls remained fail-closed. This rerun supplies current end-to-end evidence for the changed Binance/Nasdaq/FINRA paths and all seven tokenized probes.
- FINRA bounded asynchronous presigned-result downloads now convert stream setup/iteration transport failures into typed redacted provider errors while retaining positive byte-bound enforcement and credential-free signed-download behavior. The focused FINRA suite passed `9/9`; the authoritative gate at `2026-09-10T07:15Z` passed `1886/1886`, `89` warnings, and `80.36%` coverage in `416.19s`. Testcontainer session `0f4c9b7f-f9a2-43e6-a9a6-9a1cfa2fb7bd` was cleaned without host-wide pruning.
- The shared optional-provider REST layer now converts malformed JSON from Twelve Data, Finnhub, FMP, Tiingo, EODHD, Marketstack, Tradier, and MarketData.app into typed redacted failures. The focused optional-provider suite passed `27/27`; the authoritative gate at `2026-09-10T07:27Z` passed `1887/1887`, `89` warnings, and `80.36%` coverage in `522.57s`. Testcontainer session `a9124505-09fa-42a8-825b-60047d50b4af` was cleaned without host-wide pruning.
- Finnhub and MarketData.app parallel candle adapters now reject unknown status, non-array fields, and mismatched array lengths instead of truncating with `zip()` or returning false empty series. The focused optional-provider suite passed `30/30`; the authoritative gate at `2026-09-10T07:38Z` passed `1890/1890`, `89` warnings, and `80.36%` coverage in `395.31s`. Testcontainer session `3b3c3a4b-042f-4161-b40c-5df689a8ee6d` was cleaned without host-wide pruning.
- Tradier nested history and quote wrappers now reject scalar or malformed row containers while preserving valid empty wrappers. Marketstack EOD pagination now rejects missing, malformed, non-progressing, or contradictory metadata instead of truncating history. The focused optional-provider suite passed `32/32`; the authoritative gate at `2026-09-10T07:51Z` passed `1892/1892`, `89` warnings, and `80.36%` coverage in `404.68s`. Testcontainer session `294f910c-3bf6-4c72-8cf3-7d5c66d132da` was cleaned without host-wide pruning.
- All concrete optional-provider documented row-list endpoints now fail closed on missing, scalar, or mixed row containers instead of normalizing malformed responses to empty data; Tradier option-expiration parsing also rejects malformed dates and wrapper shapes. The focused optional-provider suite passed `35/35`; the authoritative gate at `2026-09-10T08:07Z` passed `1895/1895`, `89` warnings, and `80.36%` coverage in `390.66s`. Testcontainer session `3a0e72c2-6f1c-444d-9bc0-71059e0b4ed6` was cleaned without host-wide pruning.
- Tokenized xStocks, Robinhood, Bybit, Gate, and Kraken list, quote, instrument, and corporate-action paths now reject missing, scalar, or mixed response containers instead of filtering malformed rows or creating synthetic records. The focused tokenized suite passed `23/23`; the authoritative gate at `2026-09-10T08:19Z` passed `1900/1900`, `89` warnings, and `80.35%` coverage in `403.85s`. Testcontainer session `8190d6b2-84ee-48fa-a119-cd53f0e10fda` was cleaned without host-wide pruning.
- Coinbase and Kraken crypto candle, ticker, and directory adapters now reject malformed row containers and non-numeric fields instead of skipping observations or returning empty/synthetic results. Focused new-provider tests passed `121/121`; the authoritative gate at `2026-09-10T08:32Z` passed `1904/1904`, `89` warnings, and `80.35%` coverage in `444.39s`. Testcontainer session `291324c7-d107-4007-97ad-496ee703ce08` was cleaned without host-wide pruning.
- OpenFIGI mapping now rejects malformed outer envelopes, missing or mixed mapping rows, response-count mismatches, and non-2xx/429 transport failures with typed provider errors. Focused OpenFIGI tests passed `8/8`; the authoritative gate at `2026-09-10T08:42Z` passed `1907/1907`, `89` warnings, and `80.35%` coverage in `410.96s`. Testcontainer session `fddece92-aebf-488b-a824-68f4068db334` was cleaned without host-wide pruning.
- Alpaca OHLCV and latest-price paths now reject malformed or mixed bar rows, missing required OHLC fields, non-finite numeric values, and invalid pagination tokens instead of skipping observations or leaking generic exceptions. Focused Alpaca tests passed `30/30`; Ruff and diff checks passed. A follow-up authoritative gate at `2026-09-10T08:53:03Z` was blocked before tests by Docker Desktop HTTP 500 from its local API, so no new full-gate acceptance claim is made.
- FINRA short-interest and OTC Daily List adapters now reject mixed or scalar rows, invalid short-interest settlement dates, and malformed or non-finite numeric fields instead of silently dropping records or creating partial observations. Focused FINRA tests passed `13/13`; Ruff and diff checks passed. The authoritative gate remains unverified because Docker preflight is currently unavailable.
- Direct provider calls now fail closed for adjusted history on every raw-only optional REST adapter plus Binance, Coinbase, and Kraken, before any upstream transport. Exchange bars carry explicit `raw`/`provider-native` provenance, and inherited current-price helpers request raw history explicitly. Focused provider tests passed `284/284`, the complete backend unit suite passed `1,794/1,794` with the known 37 warnings, Ruff/compile/diff checks passed, and the bounded keyless Binance/Coinbase/Kraken live probes passed `3/3` under run `51b1b146-7d5b-47ac-86be-5b545bad3b6d`; aggregate usage remains outside Git. The Docker-backed acceptance gate is still unavailable and no acceptance claim is made.
- SEC EDGAR ticker/exchange directories, filing arrays, and Company Facts nested observations now reject malformed rows, table-width mismatches, misaligned arrays, and invalid nested containers instead of truncating or filtering provider data. Focused EDGAR tests passed `21/21`; Ruff and diff checks passed. The authoritative gate remains unverified because Docker preflight is currently unavailable.
- Massive ticker search/discovery, IPO-calendar, and market-holiday adapters now reject invalid result containers, mixed or scalar rows, missing identities or dates, and invalid pagination metadata instead of silently filtering or returning partial reference evidence. Focused Massive tests passed `13/13`; Ruff and diff checks passed. The authoritative gate remains unverified because Docker preflight is currently unavailable.
- Nasdaq Trader directory parsing now rejects inconsistent CSV row widths, missing symbol/name values, and malformed official or approved mirror rows while preserving intentional test-issue exclusion and ACT Symbol/Symbol compatibility. Focused Nasdaq tests passed `11/11`; Ruff and diff checks passed. The authoritative gate remains unverified because Docker preflight is currently unavailable.
- FRED history/latest-price paths now preserve typed non-rate-limit HTTP failures and reject invalid observation containers, mixed rows, invalid dates, and non-finite values while retaining the documented `.` missing-data marker. Focused FRED tests passed `31/31`; Ruff and diff checks passed. The authoritative gate remains unverified because Docker preflight is currently unavailable.
- Alpha Vantage JSON and CSV adapters now reject invalid containers, malformed search/history rows, incomplete listing or IPO rows, invalid dates/numbers, and non-rate-limit HTTP failures while preserving documented rate-limit/error handling. Focused Alpha Vantage tests passed `16/16`; Ruff and diff checks passed. The authoritative gate remains unverified because Docker preflight is currently unavailable.
- CoinGecko HTTP, search, ranked symbol resolution, profile, and market-discovery paths now reject invalid containers, malformed or mixed rows, incomplete identities, malformed nested metadata, and non-rate-limit HTTP failures while preserving typed capacity errors. Focused CoinGecko tests passed `17/17`; Ruff and diff checks passed. The authoritative gate remains unverified because Docker preflight is currently unavailable.
- Binance OHLCV, ticker, and exchange-info paths now reject malformed row containers, short or non-finite numeric rows, non-increasing pagination, malformed symbol metadata, and non-rate-limit HTTP failures. Binance 429/418 responses are typed capacity errors retaining provider headers. Focused Binance tests passed `26/26`; Ruff and diff checks passed. The authoritative gate recorded at `2026-09-10T09:45Z` passed `1959/1959`, with `89` warnings and `80.45%` coverage, using isolated PostgreSQL/Redis testcontainer session `160eaf86-b011-484f-b3cc-a5259f212c26`, cleaned without host-wide pruning.
- The bounded keyless Binance live probe passed `1/1` in `1.46s` against the public `/klines` endpoint with positive transport telemetry. This is additive live evidence alongside the authoritative full-gate receipt.
- Alpha Vantage CSV `Information`/quota responses now become typed `ProviderRateLimitError` values before CSV row parsing, preserving the observed documented 25-requests/day capacity signal. Focused Alpha Vantage coverage passes `18/18`; Gate order-book handling accepts documented null empty books, validates finite decimal quote rows, and rejects malformed rows, with focused tokenized coverage `26/26` and a bounded Gate live probe `1/1`.
- The complete live matrix at `2026-09-10T09:58:46Z` collected 34 cases: `29 passed` and `5 failed` in `36.15s`. Failures are missing `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, and `MARKETDATA_APP_API_KEY`, plus typed Alpha Vantage capacity failures for daily history and IPO-calendar reads. The direct pytest run returned exit code `1`; no acceptance claim is made and no synthetic IPO event is created.
- The latest authoritative Docker-backed gate passed `1963/1963`, with `89` warnings and `80.48%` coverage in `458.04s`, using isolated PostgreSQL/Redis testcontainer session `e6ae1ca0-d42b-473d-a83a-90751305ae08`, cleaned without host-wide pruning. No credentials/provider payloads were persisted and no frontend or ETF-constituent files changed.
- Alpha Vantage's explicit daily-capacity responses now carry a provider-specific rolling 24-hour retry timestamp, including the observed CSV `Information` response; other informational messages receive no guessed delay. Focused Alpha Vantage tests pass `18/18`.
- The latest authoritative Docker-backed gate passed `1964/1964`, with `89` warnings and `80.49%` coverage in `421.20s`, using isolated PostgreSQL/Redis testcontainer session `26146598-40dc-4c1a-b5cc-100ad6ed6d3b`, cleaned without host-wide pruning. No credentials/provider payloads were persisted and no frontend or ETF-constituent files changed.
- Alpha Vantage body-level capacity failures now retain response headers for allow-listed runtime capacity evidence. Focused coverage remains `18/18`; the follow-up authoritative gate passed `1964/1964`, with `89` warnings and `80.49%` coverage in `396.81s`, using isolated PostgreSQL/Redis testcontainer session `343bdfb7-6f4d-41e8-99a0-d1a9802f5db2`, cleaned without host-wide pruning.
- Shared provider JSON error-envelope handling now retains only allow-listed capacity headers and provider-declared retry/reset timestamps across registered adapters. A safe response-header extractor prevents lightweight test doubles or malformed header objects from masking the intended typed provider failure. Focused provider/error coverage passed `247/247`; Ruff, compilation, and diff checks passed. The authoritative Docker-backed gate passed `1966/1966`, with `89` warnings and `80.50%` coverage in `406.22s`, using isolated PostgreSQL/Redis testcontainer session `8219560c-3015-42a7-9b59-eeae4342330a`, cleaned without host-wide pruning.
- The post-change complete manifest live matrix at `2026-09-10T11:15Z` collected 34 cases: `27 passed` in `38.20s`; seven outcomes remained explicit blockers (missing `EDGAR_USER_AGENT`, `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, `MARKETDATA_APP_API_KEY`, and Alpha Vantage's documented 25-requests/day capacity for daily history and IPO-calendar). The wrapper made no acceptance claim, all seven tokenized probes remained green, and aggregate usage was recorded outside Git without credentials or payloads.
- Final post-fix evidence: the focused provider/runtime/error suite passed `327/327` in `5.85s` with Ruff and diff checks clean; the final authoritative Docker-backed gate passed `1966/1966`, with `89` warnings and `80.52%` coverage in `412.11s`, using isolated PostgreSQL/Redis testcontainer session `bc90810e-baba-4963-84c1-ef58081f42ce`, cleaned without host-wide pruning. Live/governance blockers remain unchanged and the branch is not ready for human review.
- Latest live evidence: a complete matrix rerun at `2026-09-10T11:24Z` with a temporary non-secret SEC User-Agent and reviewed `XNAS` scope passed `29/34`; five outcomes remained the exact Alpaca, Tradier, and MarketData.app credential preflights plus Alpha Vantage's two typed daily-capacity responses. Tokenized probes remained green, and the isolated Finnhub credentialed case passed `1/1`. This improves evidence freshness but does not satisfy deployment-owned secret or governance gates.
- The live preflight and live-test helper now reject the documented placeholder SEC contact value before calling external services. Focused secret-wiring tests pass `10/10`; the authoritative Docker-backed gate passes `1967/1967`, with `89` warnings and `80.52%` coverage in `437.64s`, using isolated PostgreSQL/Redis testcontainer session `aca39e7f-8836-4d71-b130-9d92033cafee`, cleaned without host-wide pruning. The branch remains blocked by real credential, governance, reconciliation, deployment-contact, and shadow gates.
- SEC User-Agent validation is now shared across the adapter, registry, live preflight, and live-test helper and rejects empty values plus `contact@example.com`, `your.email@example.com`, and any `example.com` placeholder. Focused SEC/secret-wiring tests pass `32/32`; the authoritative Docker-backed gate passes `1968/1968`, with `89` warnings and `80.51%` coverage using isolated PostgreSQL/Redis testcontainer session `59baf5db-b0e7-42fe-8ef9-221e13084cec`, cleaned without host-wide pruning. The branch remains blocked by real credential, governance, reconciliation, deployment-contact, and shadow gates.
- SEC placeholder handling now rejects `myemail@` and angle-bracket documentation values as well; root/backend env examples are blank and the provider guide labels its angle-bracket sample documentation-only. Focused SEC/secret-wiring tests remain `32/32`; the authoritative Docker-backed gate passes `1968/1968`, with `89` warnings and `80.52%` coverage using isolated PostgreSQL/Redis testcontainer session `4ac59081-aebf-41f3-b579-a0784fcaf418`, cleaned without host-wide pruning. The branch remains blocked by real credential, governance, reconciliation, deployment-contact, and shadow gates.
- The backend `/shadow` report now includes eligible core-session D1 coverage with explicit 99% `pass`/`fail`/`insufficient_evidence` status, quota-capacity event totals, and open anomaly counts by severity. Focused monitoring tests pass `5/5`; the authoritative Docker-backed gate passes `1969/1969`, with `89` warnings and `80.53%` coverage using isolated PostgreSQL/Redis testcontainer session `2f99f994-7fc5-4944-b43c-6b3308512d79`, cleaned without host-wide pruning. This remains observational; the branch is still blocked by credential, governance, reconciliation, deployment-contact, and 30-day shadow gates.
- Direct live-usage receipts now carry non-secret `PROVIDER_LIVE_USAGE_SCOPE` labels; API aggregation, CI/Compose wiring, and receipt merger deduplication preserve same run/provider IDs across distinct environments, while legacy rows normalize to `unspecified`. Focused ledger/usage/router/wiring tests pass `26/26`; the authoritative Docker-backed gate passes `1970/1970`, with `89` warnings and `80.53%` coverage using isolated PostgreSQL/Redis testcontainer session `ce2882bf-eb46-4cc4-82b7-947dc03324b6`, cleaned without host-wide pruning. External credential, governance, reconciliation, deployment-contact, and 30-day shadow gates remain open.

- Dinari and Ondo Global Markets are no longer descriptor-only: their exact authenticated settings, registry entries, unknown-quota fail-closed contracts, local/RPi/GitHub secret wiring, operation-cost profiles, and fixture tests are now present. Dinari preserves Stock UUID/CAIP-10/FIGI-CIK-CUSIP identity and exposes fair price, bid/ask, aggregate history, news, dividends, and splits; Ondo preserves chain/ISIN metadata and exposes latest indicative price plus validated primary/underlying OHLC. New credentialed live cases fail explicitly when `DINARI_API_KEY_ID`/`DINARI_API_SECRET_KEY` or `ONDO_GLOBAL_MARKETS_API_KEY` is absent. Account quota/cache/commercial/US redistribution review and live evidence remain open; no provider is admitted to routing.

- Focused Dinari/Ondo adapter, registry, quota-profile, secret-wiring, and tokenized regression coverage passed `122/122`; Ruff, compilation, and diff checks passed. The post-change manifest attempt collected 37 live tests: Dinari/Ondo stopped at exact credential preflight with no upstream calls, while the available providers produced 23 aggregate ledger rows (57 requests, 11,625,293 response bytes) outside Git. The authoritative Docker-backed combined backend gate passed `1994/1994`, with 89 warnings and `80.50%` coverage in `521.76s`, using isolated PostgreSQL/Redis session `3f19adca-0e0a-4f86-97b3-04e03a7c45d3`, cleaned without host-wide pruning. The branch remains blocked by missing credentialed live evidence and provider-specific quota/legal, reconciliation, deployment-contact, and shadow gates.

- Ondo's documentation-backed per-asset market-summary endpoint is now normalized separately from latest price and OHLC. The adapter preserves primary-token price changes, 24-hour price-history points, holder/multiplier/session metadata, underlying company metrics, timestamps, and raw payload provenance; omitted optional values remain absent. The operation profile charges the metadata lookup plus market read as two requests, fixture coverage includes malformed-field rejection, and the credentialed live case now exercises this endpoint. Live evidence remains blocked until `ONDO_GLOBAL_MARKETS_API_KEY` is provisioned.

- `backend/tests/live/test_tokenized_providers_live.py` now names and exercises the Ondo market-summary path. Its bounded credentialed attempt at `2026-09-10T15:10Z` failed only the exact missing-key preflight before any upstream request; no skip or acceptance claim was recorded.

- Resume validation at `2026-09-10T15:16Z` ran the complete backend live test collection directly with the existing operator-owned environment. `30` live cases passed and `10` failed honestly: missing `EDGAR_USER_AGENT`, `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, `MARKETDATA_APP_API_KEY`, `IBKR_READ_ONLY_URL`/`IBKR_READ_ONLY_SESSION_COOKIE`, `DINARI_API_KEY_ID`/`DINARI_API_SECRET_KEY`, and `ONDO_GLOBAL_MARKETS_API_KEY`, plus the configured Alpha Vantage key's documented 25-requests/day capacity response on daily history and IPO-calendar reads. No acceptance claim was made. Alpha Vantage's CSV capacity envelope was corrected to emit a concise typed message rather than the provider CSV header/fields; focused coverage passes `18/18`, Ruff and diff checks pass. No frontend or ETF-owned files changed.

- The FINRA OTC legacy pipe-delimited directory path now fails closed on non-text responses, missing required headers, malformed/mixed-width rows, missing symbols, and incomplete required values. Legacy and DAPI HTTP 4xx/5xx responses are converted to typed redacted provider failures; 418/429 responses preserve allow-listed capacity headers, retry metadata, and the IP scope. Focused FINRA OTC/transport coverage passes `13/13`; Ruff, compilation, and diff checks pass. No source terms or routing entitlements were inferred.

- FINRA Query API authenticated submission, polling, synchronous datasets, OAuth, and bounded asynchronous downloads now convert HTTP 418/429/non-2xx responses to typed redacted provider failures with allow-listed capacity headers, provider retry metadata, and explicit IP scope. US-universe reconciliation now fails closed on malformed discovery pages/rows instead of silently filtering them. Focused FINRA, Alpaca, provider, and universe coverage passes `71/71`; Ruff, compilation, and diff checks pass.

- The post-change authoritative Docker-backed backend gate completed at `2026-09-10T15:46Z`: `2013 passed`, `89` warnings, `80.56%` coverage in `485.84s`. Testcontainer session `d18835a7-d0e1-4351-810a-e2fe66c412d0` was cleaned without host-wide pruning; no credentials or provider payloads were persisted. The unprivileged retry was blocked by Docker-socket permissions before tests, so this receipt used the approved elevated execution path.

- FINRA's two credentialed live probes (short interest and OTC Daily List) passed `2/2` at `2026-09-10T15:47Z` with positive transport observations using the existing operator-owned credentials. The initial unprivileged attempt was blocked by sandbox DNS before any request and was not counted; the elevated retry completed successfully. The live usage receipt remains outside Git.
- Tokenized xStocks, Robinhood, Bybit, Gate, and Kraken record builders now fail closed on missing provider identity, malformed deployment/ticker containers, and malformed or non-finite quote/multiplier values. Focused tokenized plus optional-provider integrity coverage passed `104/104`, with Ruff, compilation, and diff checks clean. No frontend or ETF-owned files changed.
- The elevated complete live matrix at `2026-09-10T16:06Z` passed `29/37`; eight outcomes remained exact missing Alpaca, Tradier, MarketData.app, IBKR, Dinari, and Ondo credentials plus Alpha Vantage's typed 25-requests/day capacity responses for daily history and IPO-calendar. All public tokenized probes passed. xStocks returned observed `x-ratelimit-limit=1000`, `x-ratelimit-remaining=996`, and a reset timestamp; these provider-native observations remain supplemental and are not treated as a contractual quota. The aggregate receipt is outside Git and contains no secrets or payloads.
- The post-change authoritative Docker-backed combined backend gate passed `2045/2045`, with `89` warnings and `80.61%` line coverage in `481.80s`. Isolated PostgreSQL/Redis testcontainer session `55312b72-cd9c-464a-8efb-05ad263654e1` was cleaned without host-wide pruning; no credentials or provider payloads were persisted.
- Crypto provider integrity hardening now rejects non-finite and out-of-range candle values/timestamps, unsupported timeframes, incomplete Coinbase/Kraken discovery identities, malformed pagination rows, and non-2xx HTTP responses as typed failures. Capacity responses retain only allow-listed headers and provider reset metadata. Focused crypto coverage passes `181/181`; the all-provider unit suite passes `353/353`; Ruff, compilation, and diff checks are clean.
- The optional REST error path now filters response headers before constructing typed capacity failures, excluding authorization and other sensitive headers. Boolean numeric/timestamp inputs fail closed. The focused optional-provider integrity tests remain green; no generic quota fallback was added or restored.
- An elevated complete live rerun at `2026-09-10T16:30Z` collected all `37` manifest cases and passed `29`. The eight honest outcomes remain missing `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, `TRADIER_API_KEY`, `MARKETDATA_APP_API_KEY`, `IBKR_READ_ONLY_URL`/`IBKR_READ_ONLY_SESSION_COOKIE`, `DINARI_API_KEY_ID`/`DINARI_API_SECRET_KEY`, and `ONDO_GLOBAL_MARKETS_API_KEY`, plus the configured Alpha Vantage key's typed documented `25 requests/day` capacity response for daily history and IPO-calendar. All public tokenized probes passed, including xStocks/Robinhood/Bybit/Gate/Kraken; xStocks' observed native limit headers remain supplemental only. Aggregate usage was written to `/private/tmp/charting-provider-live-usage-resume.jsonl` outside Git; no credentials or payloads were persisted and no acceptance claim was made.
- The post-hardening authoritative Docker-backed combined backend gate passed `2054/2054`, with `89` warnings and `80.61%` line coverage in `499.43s`. Isolated PostgreSQL/Redis testcontainer session `93403b50-fcbd-46c2-b359-bd4c76020339` was cleaned without host-wide pruning; no credentials or provider payloads were persisted.
- Quota contract admission now rejects boolean, fractional, and string-valued provider dimension limits/windows instead of coercing them through `int()`. Marketstack EOD pagination likewise requires strict integer counters and rejects contradictory totals, preventing malformed provider metadata from widening or truncating a request budget. Focused quota/Marketstack/tokenized coverage passes `115/115`; the full Docker-backed gate is still required for this revision.
- The external live-usage ledger now reports rolling 30-day operation/request/byte totals and selects response-capacity headers by observation timestamp rather than file order. This makes rolling bandwidth usage visible across sessions and merged CI receipts without treating calendar-reset totals as inferred provider truth.
- On 2026-09-11, the supplied local credentials produced passing EDGAR and Alpaca live probes (2/2) and a passing MarketData.app probe after fixing its required trailing-slash candle URL. Dinari reached the sandbox endpoint but returned typed HTTP 401, so no success or quota entitlement was inferred. Tradier, Ondo, and IBKR remain intentionally deferred per the human decision.
- The replacement Dinari Sandbox pair was validated on 2026-09-11. The first 401 was caused by the operator-only base URL still targeting Dinari's live sbt host; after switching to the documented Sandbox host, the bounded Dinari credentialed stock metadata, fair-price/quote, history, news, dividend, and split probe passed 1/1 with positive transport observations. Tradier, Ondo, and IBKR remain intentionally deferred per the human decision; account quota, terms, and routing-admission gates remain separate.
- The complete 37-case manifest rerun at 2026-09-11T17:43:45Z passed 33/37. The four honest outcomes were Alpha Vantage's documented 25-requests/day IPO-calendar capacity response plus exact credential preflights for the intentionally deferred Tradier, IBKR, and Ondo providers. Aggregate request/response-byte telemetry remained outside Git and no credential or provider payload was persisted.
- On 2026-09-12, the focused core refresh passed 4/4 checks: EDGAR profile and complete directory pagination, Alpaca paper-account history, and MarketData.app daily candles. A separate Dinari Sandbox refresh passed 1/1 for metadata, quote/history, news, dividend, and split reads. The operator-owned environment was used; only aggregate transport telemetry was retained outside Git.
- On 2026-09-12, the MarketData.app adapter gained documentation-faithful option-expiration and parallel-array current-chain normalization with strict field-shape validation. A bounded credentialed live probe covering MarketData.app expirations/chain plus Alpaca latest price passed 2/2. Expirations are explicitly one credit per call; response-dependent chain/quote charging is not guessed, so those operations remain fail-closed for routing until a reviewed maximum reservation bound exists. No credentials or payloads were persisted.
- The complete post-options live matrix on 2026-09-12 collected 39 cases and passed 35 with positive transport observations. The four honest outcomes were Alpha Vantage's documented 25-requests/day IPO-calendar capacity response and exact credential preflights for intentionally deferred Tradier, IBKR, and Ondo. xStocks returned an explicit null quote while the selected token reported a closed trading period; the live assertion records that state without fabricating a price. The wrapper made no acceptance claim, and only aggregate usage telemetry was retained outside Git.
- The authoritative Docker-backed combined backend gate after the adapter and live-test changes passed 2067/2067 with 89 warnings and 80.67% line coverage in 452.20 seconds, using isolated PostgreSQL/Redis testcontainer session `c05cce66-44c3-48d4-910d-42060d5f6667`, cleaned without host-wide pruning. No credentials or provider payloads were persisted and no frontend or ETF-owned files changed.
- MarketData.app now also implements the documented single-contract current/historical option-quotes endpoint as `OptionQuotePointRecord` history. Parallel arrays, required OCC symbol/timestamp, optional numeric fields, timezone conversion, historical null Greeks, and requested-window filtering are validated without silent truncation. Its response-dependent credit charge remains intentionally absent from the operation-cost map, so routing stays fail-closed until a reviewed bound exists.
- The credentialed MarketData.app options live case passed 1/1 on 2026-09-12, exercising expirations, current chain, and historical option quote reads. The complete 39-case matrix again passed 35 with the same four honest outcomes (Alpha Vantage daily capacity plus deferred Tradier, IBKR, and Ondo credential preflights). The final Docker-backed combined gate passed 2069/2069 with 89 warnings and 80.67% coverage in 538.03 seconds, using isolated PostgreSQL/Redis session `190609a8-baa3-4a56-aac8-09ca99908cc7`, cleaned without host-wide pruning.
- MarketData.app provider-native credit accounting is now captured and settled: `X-Api-Ratelimit-Limit`, `Remaining`, `Reset`, and per-response `Consumed` headers are allow-listed, actual response charges replace the reservation when valid, and cumulative usage is reconciled only when the provider limit matches the reviewed 100-credit contract. Current option chains require `MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS`; the adapter applies `strikeLimit` and rejects larger responses, while zero remains fail-closed. Historical single-contract quote history derives its conservative credit reservation from the documented end-of-day date range. Focused provider/quota/telemetry/options coverage passed `168/168`; Ruff and diff checks passed. The revision-level full gate and live matrix results are recorded in the following bullet.
- The revision's authoritative Docker-backed combined backend gate passed `2073/2073`, with `89` warnings and `80.66%` line coverage in `490.51s`, using isolated PostgreSQL/Redis testcontainer session `8d3b8ff4-4091-4c1f-8536-e5c606cdfc36`, cleaned without host-wide pruning. The complete 39-case credentialed live matrix was rerun and passed `35/39`; the four honest outcomes remain Alpha Vantage's documented 25-requests/day capacity response plus intentional Tradier, IBKR, and Ondo credential preflights. No credentials or provider payloads were persisted; acceptance remains blocked on the documented provider/legal/routing gates and deferred credentials.
- The historical option-quote reservation was tightened after gate review to treat MarketData.app's date range as inclusive: a 1,001-calendar-day request reserves two credits, while equal endpoints reserve one. Focused options/quota/adapter/telemetry coverage passed `138/138`; no provider call or credential was involved in this correction.
- The authoritative Docker-backed combined backend gate after the inclusive-bound correction passed `2074/2074`, with `89` warnings and `80.67%` line coverage in `452.68s`, using isolated PostgreSQL/Redis testcontainer session `b383e6c8-ba85-477b-af0d-66343893d2a0`, cleaned without host-wide pruning.
- The final complete 39-case credentialed live matrix after the inclusive-bound correction passed `35/39`; Alpha Vantage's documented 25-requests/day capacity response and intentional Tradier, IBKR, and Ondo credential preflights remain the four honest blockers. Routing safety continues to fail closed for unreviewed provider entitlements/bounds; aggregate usage remains outside Git with no credentials or payloads persisted.
- The provider-native MarketData.app headers are now preserved consistently through runtime capacity events and the external live-ledger/receipt-merger paths, not only adapter telemetry. Focused runtime/live-ledger/usage/telemetry coverage passed `37/37`; authorization headers remain rejected.
- Native MarketData.app reset handling is complete across both shared error parsing and the optional REST adapter: `X-Api-Ratelimit-Reset` produces a typed retry timestamp, while the four native headers remain allow-listed through durable capacity evidence and cross-session usage summaries. Focused provider/runtime/usage coverage passed `107/107`.
- The authoritative Docker-backed combined backend gate after native-reset propagation passed `2075/2075`, with `89` warnings and `80.68%` line coverage in `424.58s`, using isolated PostgreSQL/Redis testcontainer session `5b5c1410-eefc-4737-a7bf-bca01fc5fae1`, cleaned without host-wide pruning.
- A runtime end-to-end regression now executes a MarketData.app-shaped response through `execute_provider_call`, proving safe native telemetry persistence and durable settlement to the provider-observed cumulative total (`13` used from a `100`-credit window after a `4`-credit response). Focused runtime/adapter/error/usage/ledger coverage passed `39/39`.
- The live MarketData.app key returned the provider-native `X-Api-Ratelimit-Limit=10000`, `Remaining=10000`, `Consumed=0`, and reset epoch on 2026-09-12. Because this is Starter-shaped while the repository seed documents Free Forever 100 credits/day, the runtime now preserves the observation but refuses automatic widening. Operators must explicitly record the exact reviewed `MARKETDATA_APP_REVIEWED_PLAN` / `MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT` pair (`free_forever/100`, `starter/10000`, or `trader/100000`); Quant/Prime remain outside this daily contract.
- The explicit MarketData.app plan/limit gate is wired through provider routing diagnostics, the manual GitHub live workflow, local/RPi Compose, and environment examples. Focused provider/config/registry/secret-wiring coverage passed `204/204`, Ruff and diff checks passed, and the authoritative Docker-backed combined gate passed `2077/2077` with `80.69%` coverage.
- The account-plan entitlement seeding follow-up keeps MarketData.app `unreviewed` until the exact plan/limit pair is supplied, promotes only the documented Free Forever/Starter/Trader pairs, and refreshes seed-owned policies without overwriting operator-pinned contracts. The follow-up authoritative Docker-backed combined gate passed `2078/2078` with `80.69%` coverage using isolated PostgreSQL/Redis session `a45ab140-1275-4102-a92f-5224bee1123b`, cleaned without host-wide pruning.
- Clean bounded live evidence for the newly supplied credentials passed `7/7`: SEC EDGAR profile and complete directory pagination, Alpaca paper history/latest price, MarketData.app candles/options, and the rotated Dinari Sandbox metadata/price/quote/history/news/dividend/split path. The final 39-case matrix passed `35/39`; the four honest outcomes were Alpha Vantage's documented 25-requests/day response plus intentionally deferred Tradier, IBKR, and Ondo credential preflights. The final matrix also reports MarketData.app non-routable until the reviewed plan/limit pair is set; all aggregate receipts remain outside Git.
- Group-snapshot freshness now includes a deduplicated member/benchmark ID set. An expired current benchmark emits a specific `stale_data` exclusion and stale relative cells, while historical `as_of` reads retain their prior semantics. Focused analysis checks pass; the new database-backed regression remains blocked before application startup by Docker Desktop's HTTP 500 readiness failure.
- The reusable current `/breadth` evaluator now excludes stale members, withholds stale direct benchmarks, and records stale derived-reference members. Historical breadth remains unchanged. Focused breadth/analysis coverage passes `48/48`; the new database-backed stale regression remains blocked before application startup by Docker Desktop's HTTP 500 readiness failure.
- The current `/indicator-batch` endpoint now withholds expired OHLCV snapshots and returns per-symbol `stale_data` warnings instead of calculating indicators from stale bars. Focused analysis/breadth coverage remains green; database-backed regression remains blocked by Docker Desktop's HTTP 500 readiness failure.
- Benchmark-family ratios now withhold current ratios when either role or benchmark OHLCV is stale, emit per-ratio `stale_data` warnings, and expose the underlying freshness summary. Historical `as_of` ratios remain unchanged; focused analysis/breadth coverage remains green and database-backed validation remains Docker-readiness blocked.
- Industry-proxy and classified-industry snapshots now withhold expired current proxy/member bars, report partial synthetic-series coverage, and emit explicit stale benchmark-relative cells. Historical `as_of` reads retain their point-in-time behavior; focused analysis/breadth coverage remains green and database-backed validation remains Docker-readiness blocked.
- Benchmark-family breadth now excludes stale current role members, withholds stale cap benchmarks from relative participation, and includes the role/member freshness summary. Historical breadth remains unchanged; focused analysis/breadth coverage remains green and database-backed validation remains Docker-readiness blocked.
- Derived benchmark-family equal-weight series now exclude stale current members while preserving historical `as_of` calculations, with explicit stale exclusions alongside partial-coverage diagnostics. Focused analysis/breadth coverage remains green and database-backed validation remains Docker-readiness blocked.
- Benchmark-family role ranking and cross-family cap ranking now withhold expired current role bars, retain stale warnings, and include deduplicated freshness summaries. Historical ranking remains unchanged; focused analysis/breadth coverage remains green and database-backed validation remains Docker-readiness blocked.
- Current ETF constituent snapshot analysis now withholds expired holding, benchmark, and market-benchmark OHLCV bars, emits explicit `stale_data` warnings, and reports deduplicated freshness accounting while preserving historical `as_of` semantics. Focused route/unit checks are green; the database-backed regression remains blocked by Docker Desktop's HTTP 500 readiness failure. This change is limited to the analysis consumer: `feat/etf-holdings-constituents` retains ETF provider-adapter ownership, and the two contracts must be reconciled at staging.
- Current Market Map calculations now withhold explicitly stale member/reference OHLCV bars, include comparison IDs in freshness accounting, and include stale-state identity in cache keys; explicit `as_of` maps retain historical observations. Focused Market Map/analysis coverage passes `53/53`, and the full backend unit suite passes `1728/1728`; the database-backed regression remains blocked by Docker Desktop's HTTP 500 readiness failure.
- Current benchmark-family role rankings now withhold expired role OHLCV, emit explicit `stale_data` warnings, and preserve historical `as_of` semantics. Focused analysis checks are green; the existing database-backed stale-ranking regression remains blocked by Docker Desktop's HTTP 500 readiness failure.
- Dinari Sandbox configuration is now aligned end-to-end: the adapter fallback, root/backend environment examples, and `Settings` default use the documented `https://api-enterprise.sandbox.dinari.com/api/v2` host. A blank setting is covered by a regression and production deployments must still provide an explicit environment URL; no credential values or provider payloads are persisted. Dinari tokenized-provider unit coverage passes `49/49`, with Ruff, compilation, and diff checks clean.
- Dinari and Ondo authenticated tokenized adapters now fail closed before issuing HTTP when their exact credential settings are absent, rather than sending empty authentication headers. Tokenized-provider coverage passes `51/51`; the full backend unit suite passes `1731/1731` with the existing 37 warnings. No credentials or payloads were persisted.
- Refresh jobs now persist an opaque per-claim lease token. Completion and retry use conditional id/status/token/expiry updates and raise an explicit lease-loss error when a stale worker no longer owns the job; the worker records lease loss without retrying or overwriting another worker's state. Focused queue/worker coverage passes `32/32`; the full backend unit suite passes `1734/1734` with Ruff, compilation, and diff checks clean. The additive migration is `6c7d8e9f0a1b_add_refresh_job_lease_tokens.py`.
- The admin-only `/api/v1/market-data/refresh/queue` diagnostic now exposes bounded status counts and job-level retry/lease-expiry/error state without returning opaque lease tokens. Its integration contract regression is present; PostgreSQL-backed execution remains blocked by the unavailable local Docker socket.
- Refresh-job retry persistence now redacts provider credentials at the queue boundary, and the admin diagnostic redacts again on read. Focused queue/admin coverage passes `8/8`; the full backend unit suite passes `1735/1735` with static checks clean.
- Provider-availability probe and instrument/provider-support persistence now apply the same bounded credential redaction before storing diagnostic errors. Focused provider/queue/admin coverage passes `19/19`; the full backend unit suite passes `1737/1737` with Ruff, compilation, and diff checks clean.
- Instrument-sync and US-universe reconciliation now apply the same bounded credential redaction to durable run errors and provider-failure log messages. A direct regression covers both persistence paths; affected provider/run coverage passes `24/24`, and the full backend unit suite passes `1739/1739` with Ruff, compilation, and diff checks clean.
- Alpaca, Binance, and legacy yfinance transport-exception logs now use the shared credential redactor as well. All provider unit tests pass `369/369`; the full backend unit suite remains `1739/1739` with Ruff, compilation, and diff checks clean.
- Redacted provider transport diagnostics are now bounded to 1,000 characters in those adapters and in instrument-sync/universe log paths. The combined provider/service regression set passes `393/393`; the full backend unit suite remains `1739/1739` with Ruff, compilation, and diff checks clean.
- The shared provider runtime now uses a bounded redaction helper for request-log errors (4,000 characters), health/fallback diagnostics (1,000 characters), capacity events, and availability probes. Focused runtime/error coverage passes `38/38`; the full backend unit suite passes `1741/1741` with Ruff, compilation, and diff checks clean.
- Provider-facing market-data refresh, bulk-history, alert preflight, and background task diagnostics now use the bounded redactor, including the returned bulk-fetch error state. Focused market-data/task/runtime coverage passes `76/76`; the full backend unit suite remains `1741/1741` with Ruff, compilation, and diff checks clean.
- Bulk-history now has an explicit regression for the caller-visible failure state: provider credential-bearing exception text is redacted and bounded before it is returned; focused bulk/provider-runtime/error coverage passes `36/36`, the full backend unit suite passes `1742/1742`, and Ruff, compilation, and diff checks are clean.
- Dinari Sandbox's documented host is now the default in Docker Compose, RPi Compose, and the manual GitHub live workflow; a wiring regression rejects the retired `api-enterprise.sbt.dinari.com` fallback. Focused provider-wiring/tokenized coverage passes `63/63`, the full backend unit suite passes `1743/1743`, and Ruff, compilation, and diff checks are clean.
- Core workstation bootstrap history, ETF bootstrap, and family-history queue error results now use bounded credential redaction; the bootstrap regression exercises credential-bearing provider failure text. Focused bootstrap/error coverage passes `14/14`, the full backend unit suite passes `1743/1743`, and Ruff and diff checks are clean.
- Root and RPi Compose manifests parse successfully after the Dinari Sandbox wiring correction (RPi validated with non-secret deployment placeholders); no service was started or restarted.
- The current official Tiingo pricing page confirms the free Starter contract as 500 unique symbols/month, 50 requests/hour, 1,000 requests/day, and 1 GB/month bandwidth. The operator-observed 2.00 GB value is not treated as authoritative; Tiingo remains fail-closed until operation-specific byte bounds are reviewed.
- Provider usage diagnostics now derive active quota-window expiry from each policy's explicit calendar reset (including Eastern-time month/day and 09:30 ET boundaries), instead of treating every long window as a fixed 31-day duration. Fixed and rolling windows retain their duration semantics, so admin summaries expire at the same boundary used by admission across short months and daylight-saving transitions. The focused usage suite passes `7/7`; the full backend unit suite passes `1745/1745`, with Ruff, compilation, and diff checks clean.
- Alpaca asset discovery now uses an explicit documented paper/live trading host (paper is the safe default), fixing paper-key 401s caused by the former hard-coded live host. Corporate actions now use the current v1 market-data endpoint, honor `payable_date`, and follow `next_page_token` instead of the deprecated v2 announcements route. Focused credentialed live verification passed `3/3` for Alpaca assets/corporate actions, SEC EDGAR filings/Company Facts, and Dinari dividend/split coverage; Alpaca provider unit coverage passed `184/184`, with Ruff, compilation, and diff checks clean. No credentials or provider payloads were persisted.
- The complete deterministic backend unit suite after the Alpaca endpoint correction passed `1748/1748` with 37 existing warnings; no Docker services were started or restarted, and no credentials or provider payloads were persisted.
- The superseding complete manifest run on 2026-09-12 collected `41` cases and passed `37/41`. The four honest outcomes were Alpha Vantage's documented 25-requests/day capacity response plus exact missing credential preflights for intentionally deferred Tradier, IBKR, and Ondo. The new Alpaca/SEC/Dinari cases passed, and routing-safety diagnostics remain fail-closed for the documented unreviewed controls. Aggregate usage stayed outside Git.
- Follow-up accounting audit removed Alpaca's guessed fixed `fetch_instrument_events: 1` usage seed. Corporate-actions routing now requires the reviewed positive `ALPACA_CORPORATE_ACTIONS_MAX_PAGES` control, reserves that worst-case cursor-page cost, and fails before issuing an unreserved page; unrelated Alpaca history/latest/discovery routing remains eligible without the event-only control. The control is wired through config examples, local/RPi Compose, the manual GitHub workflow, provider diagnostics, and live preflight. Focused regressions passed `285/285`, the complete backend unit suite passed `1750/1750`, Ruff/compile/diff and both Compose parses passed, and the changed Alpaca assets/corporate-actions live case passed `1/1` (2 observed HTTP requests; aggregate receipt remains outside Git).
- The successful Alpaca follow-up receipt was merged into `/Users/jagnelo/.config/charting-platform/provider-live-usage.jsonl` through `scripts/merge-provider-live-usage.py` (`accepted=1`, `duplicates=0`, `rejected=0`), preserving cross-session usage accounting without copying credentials or payloads.
- On 2026-09-12, the rotated Dinari Sandbox pair was revalidated independently: its credentialed stock metadata, fair price, quote, aggregate history, news, dividend, and split contract passed `1/1`, with 13 observed upstream requests. The redacted aggregate receipt was accepted into the owner-managed external ledger (`accepted=1`, `duplicates=0`, `rejected=0`).
- On 2026-09-12, bounded Alpaca and MarketData.app credentialed live validation passed `5/5`, covering Alpaca history/latest/assets/corporate actions and MarketData.app daily candles, option expirations/chain, and historical option quotes. Two redacted aggregate receipts were accepted into the owner-managed external ledger (`accepted=2`, `duplicates=0`, `rejected=0`); no credentials or provider payloads were persisted.
- The MarketData.app live option-chain case is now explicitly bounded to 20 contracts through the adapter's `strikeLimit` path. The bounded credentialed option surface passed `1/1` on 2026-09-12 (three HTTP requests, 5,544 response bytes), and its redacted aggregate receipt was accepted into the owner-managed external ledger (`accepted=1`, `duplicates=0`, `rejected=0`). The provider remains non-routable until the same bound and account/redistribution terms are operator-reviewed.
- The Alpaca assets/corporate-actions live probe now applies a test-only two-page cursor bound. The bounded case passed `1/1` on 2026-09-12 (two HTTP requests, 6,460,094 response bytes), and its redacted aggregate receipt was accepted into the owner-managed external ledger (`accepted=1`, `duplicates=0`, `rejected=0`). This does not promote the deployment's still-unreviewed `ALPACA_CORPORATE_ACTIONS_MAX_PAGES` routing control.
- Registry descriptor metadata now matches the concrete transport hosts for FMP (`/stable`), Dinari Sandbox (`/api/v2`), and Ondo Global Markets (`api.gm.ondo.finance`). The registry regression passes `21/21` with Ruff, compilation, and diff checks clean; no credential or entitlement state changed.
- The descriptor audit also corrected Kraken's public host to include `/0/public`; the registry regression now enforces host equality for every optional descriptor and remains green at `21/21`.
- Repository live-probe seeds now record `passed` for Alpaca, MarketData.app, and Dinari after their bounded credentialed probes passed on 2026-09-12. This is transport evidence only: Alpaca's event-page bound, MarketData.app's reviewed plan/option bound, and Dinari's partner quota/terms gates remain independently fail-closed.
- The refreshed complete live matrix at `2026-09-12T07:21:11Z` again collected all `41` cases and passed `37/41` in `79.69s`. The four honest failures were Alpha Vantage's documented 25-requests/day capacity response plus exact missing credential preflights for intentionally deferred Tradier, IBKR, and Ondo. Its redacted 26-provider aggregate receipt was accepted into the owner-managed cross-session ledger; no credentials or payloads entered Git.
- The complete backend unit suite after the evidence-state reconciliation passed `1,751/1,751` in `62.51s` with the repository's known `37` deprecation warnings; no provider calls or services were started.
- The live-runner applicability detector now treats `backend/app/config.py` quota/entitlement changes as provider changes, preventing a configuration-only integration edit from silently bypassing the opt-in matrix; the secret-wiring regression passes `13/13` with Ruff, compilation, and diff checks clean.
- The complete backend unit suite after the live-runner applicability fix passed `1,752/1,752` in `61.31s` with the repository's known `37` deprecation warnings; no provider calls or services were started.
- Non-mutating Compose contract parsing passed for both root and RPi manifests. The migration-compatibility helper ran successfully but correctly skipped because the latest commit contained no migration changes; this is not a fresh-database integration result.
- The explicit staging-to-feature migration compatibility gate was attempted with `--base-sha staging` but Docker's local API returned HTTP 500 during its readiness ping before PostgreSQL startup. Cleanup left no temporary test worktree/container; the migration gate remains unverified rather than being called passed.
- Full provider/runtime lint and compilation passed across adapters, routing, usage, live probes, and their focused tests; `git diff --check` also passed.
- The non-secret Alpaca `ALPACA_DATA_FEED` setting is now explicitly passed
  through the manual GitHub live workflow, matching local/RPi Compose and
  retaining the safe `iex` default. Provider wiring coverage passes `13/13`,
  the complete backend unit suite passes `1,752/1,752` with the known 37
  warnings, and static checks are clean. This only aligns configuration
  propagation; it does not widen feed or corporate-action entitlements.
- The provider TODO ledger now records the superseding 2026-09-12 complete
  matrix evidence (`41` cases, `37/41` passed) rather than leaving the earlier
  `39`-case result as the latest checkpoint. The four non-passes remain the
  documented Alpha Vantage daily-capacity response and intentional deferred
  Tradier/IBKR/Ondo credential preflights; the redacted receipt remains in the
  owner-managed external ledger and no credentials or payloads entered Git.
- Documentation commit `2313d43d8d08d7cdae46ffd2119986bb49464392` is pushed and
  synchronized with `origin/feat/market-data-provider-platform`. This following
  operational checkpoint refreshes `session.json` and records the exact prior
  commit; the checkpoint commit itself must be verified externally rather than
  creating a self-referential hash loop.
- The required full-profile implementation-session bootstrap was retried after
  this commit but remains blocked because `docker info` hangs after the client
  section on the local Docker Desktop API. The branch is clean and pushed;
  `session.json` records the blocked preflight explicitly rather than bypassing
  the Docker gate or claiming new PostgreSQL/Redis evidence.
- The current project TODO ledger now marks the supplied Alpaca, EDGAR,
  MarketData.app, and Dinari credentials/live evidence as complete and keeps
  Tradier/Ondo/IBKR as intentionally deferred operator decisions, avoiding an
  obsolete “missing Alpaca/MarketData key” blocker.
- The tracked root/backend environment examples and Docker Compose defaults now
  match the current backend provider contract: price/latest chains no longer
  carry stale Nasdaq/crypto/macro entries, discovery uses the current US
  directory chain, and refresh/universe/shadow controls plus Nasdaq request
  identity are documented. Static checks and both Compose contract parses pass;
  no services, provider calls, credentials, or payloads were used.
- Compose now passes the market refresh, shadow-report, and US-universe
  reconciliation controls to backend and worker processes in both local and RPi
  manifests, while keeping them out of the research runner. The new wiring
  regression passes 14/14, and Compose contract parsing remains green.
- The complete backend unit suite passes 1,753/1,753 in 61.91s with the
  repository’s existing 37 deprecation warnings after this wiring change; no
  services or provider calls were started.
- Local/RPi deployment defaults now retain Dinari and Ondo in the tokenized
  priority (while their unknown-quota/terms gates remain fail-closed), and the
  wiring suite explicitly guards that visibility. Focused coverage passes
  16/16; no credentials or provider payloads were used.
- The complete backend unit suite passes 1,755/1,755 in 62.07s with the
  repository’s existing 37 deprecation warnings after the complete deployment
  wiring pass; no provider calls or services were started.
- README and provider documentation examples now match the actual US-first
  chains (including the Dinari/Ondo tokenized priority) and explain the new
  deployment control semantics. Workstream and diff validation remain green;
  no provider calls or services were started.
- `backend/.env.example` now documents the same paid-routing, availability,
  retention, and support-TTL controls as the deployment manifests. Focused
  wiring/reference coverage passes 16/16; static checks and both Compose
  contract parses remain green.
- `session.json` now marks the current Docker readiness as unavailable with a
  bounded 90-second wait, matching the latest bootstrap failure and preventing
  stale `ready: true` state from being mistaken for new database/Redis evidence.
- This Docker-state correction is based on the synchronized operational
  checkpoint `5d9db49c387f566b00b0296895b89fc30007599c`; the enclosing
  checkpoint commit will be verified externally after push.
- Marketstack configuration is now operation-scoped: daily history and quote
  routes require only `MARKETSTACK_API_KEY`, while discovery/reconciliation
  continue to require the explicit `MARKETSTACK_DISCOVERY_EXCHANGE` MIC. The
  registry/runtime regression passes `48/48`; the complete backend unit suite
  passes `1,757/1,757` with 37 existing warnings. No live provider calls were
  rerun because this change only affects routing admission.
- The Marketstack routing implementation and its full unit validation are now
  based on synchronized commit `372926faee2bc30031b9883e632ce9a9188969a9`;
  this next operational checkpoint records that prior SHA and will be verified
  externally after its own push.
- The operation-scoped Marketstack implementation was committed and pushed as
  `8299a34eedbec74ba4a265e1cd4d32538022178f`, with local and remote refs
  matching. The session state below records that exact implementation SHA;
  this operational checkpoint remains a separate commit and will be verified
  externally after push.
- The branch validator succeeds when invoked with an isolated writable
  `UV_CACHE_DIR`, and both root and RPi Compose contract manifests parse
  successfully under the same override. This confirms the earlier failure was
  local uv-cache permission state, not a repository or provider contract error.
- Provider availability preflights now delegate to the operation-aware registry
  configuration contract, so Dinari's key-ID/secret, IBKR's gateway URL/session
  cookie, SEC EDGAR's validated User-Agent, and Marketstack's history-versus-
  discovery configuration are checked accurately. Focused availability tests
  pass `8/8`; the complete backend unit suite passes `1,759/1,759` with 37
  known warnings. The implementation is pushed at
  `2f8660155c8a86badeb30efef554689ea6c71cc3`; the accompanying TODO/plan/
  validation checkpoint remains separate.
- The central provider configuration predicate now rejects whitespace-only
  credentials and blank legacy/current key alternatives. Focused registry and
  availability coverage passes `31/31`; the complete backend unit suite passes
  `1,760/1,760` with 37 known warnings. The implementation is pushed at
  `6c8f46f09b642f7c8a781e966df1fe815d897db7`; the durable checkpoint remains
  separate.
- 2026-09-12 quota-accounting correction: durable quota windows and distinct-identity claims now carry an explicit provider-defined `quota_group` separate from the requested capability. MarketData.app's documented account/key-wide daily-credit and concurrent-request dimensions use `account`, and the same explicit grouping is recorded for reviewed account/key/IP/session contracts and promoted byte pools; endpoint/pair-scoped exceptions remain separate. Usage from different capabilities therefore shares one durable budget only where the provider contract says it should. Omitted groups remain capability-scoped for compatibility and blank groups fail closed. The additive migration `7d8e9f0a1b2c` backfills existing rows and replaces the capability-keyed uniqueness/indexes; admin and usage summaries expose the group. Full backend unit coverage passes `1765/1765`; no provider calls were made for this bookkeeping change.
- 2026-09-12 local admission correction: process-local token buckets and semaphores now derive their key from the same explicit short-window `quota_group` used by durable reservations. Shared account/key/IP/session limits therefore cannot multiply once per capability within one worker, while omitted groups stay isolated by capability. Runtime settlement also preserves explicit zero dimension costs for operations that do not use a reviewed dimension. Focused accounting coverage passes `7/7`; the complete backend unit suite passes `1768/1768` with Ruff, compilation, and diff checks clean. Source is pushed at `5c06ab441c35a3e28b96988b372d7a1bd079abb0`; no provider calls or services were started for this change.
- 2026-09-12 fresh credentialed revalidation: the supplied Alpaca paper, SEC EDGAR, MarketData.app, and rotated Dinari Sandbox settings passed all `7/7` bounded selected live cases under run `4f1e9a1c-5d22-4d62-a6b7-3ddf8db41f6a`. Aggregate external usage was recorded outside Git for Alpaca (`4` operations/`4` HTTP requests/`6,460,696` bytes), Dinari (`7`/`13`/`553,750`), EDGAR (`3`/`4`/`4,915,212`), and MarketData.app (`3`/`3`/`5,702`), with only allow-listed capacity headers retained. This is transport evidence only: deferred Tradier/Ondo/IBKR credentials and independent quota/terms/reconciliation gates remain unchanged.
- 2026-09-12 live-ledger identity hardening: direct live-test processes now generate a fresh UUID when `PROVIDER_LIVE_RUN_ID` is absent, avoiding PID reuse or inherited shell values that could merge independent sessions. Explicit wrapper/CI run IDs remain authoritative. Focused ledger coverage passes `6/6`; the complete backend unit suite passes `1769/1769` with the known 37 warnings, Ruff/compile/diff checks clean. Source is pushed at `2ed3f9f30a2e9fce996d6efa03e5569f368705e2`; no provider calls were made for this change.
- 2026-09-12 local concurrency-group admission hardening: process-local semaphores now include explicit concurrent-request quota groups in their keys, while token buckets retain request/credit/weight grouping. Shared account/key/IP/session concurrency limits therefore cannot multiply once per capability inside a worker. Focused accounting coverage passes `7/7`; the complete backend unit suite passes `1769/1769` with the known 37 warnings, Ruff/compile/diff checks clean. Source is pushed at `3f611eaa8160ad4f1efdb2acf665f07bee45ec5f`; no provider calls or services were started.
- 2026-09-12 Alpaca corporate-actions page fidelity: the adapter now requests the documented 1,000-record page maximum while retaining its explicit local pagination budget. Focused corporate-action coverage passes `6/6`, the bounded credentialed assets/actions live case passes `1/1`, and the complete backend unit suite passes `1769/1769`. The live receipt records aggregate Alpaca telemetry only in the external ledger; no credentials or payloads entered Git.
- 2026-09-12 live-ledger writability preflight: live pytest sessions now open the configured aggregate-only ledger before invoking providers and exit with code `2` on a permission/path failure, preventing quota consumption without a durable receipt. Focused ledger coverage passes `8/8`; the complete backend unit suite passes `1771/1771` with the known 37 warnings. No provider calls were made for this change.
- 2026-09-12 live-ledger attribution preflight: direct live pytest sessions now also require a bounded printable `PROVIDER_LIVE_USAGE_SCOPE`, preventing new unattributed `unspecified` receipts. Focused ledger coverage passes `11/11`; the complete backend unit suite passes `1774/1774` with the known 37 warnings. No provider calls were made for this change.
- 2026-09-12 complete configured-provider live revalidation: the fresh 41-case matrix passed `37/41` at 09:36:37Z. Alpha Vantage returned its documented daily-capacity response; Tradier, IBKR, and Ondo failed only their exact intentional credential preflights. The owner ledger recorded 26 aggregate provider rows (`64` operations, `86` HTTP requests, `22,749,358` bytes) under run `d1125f7c-ad38-41bc-81bc-0b65f68c2ca9`; no credentials or payloads entered Git.
- 2026-09-12 live-ledger durability: the owner-managed aggregate-only ledger is permission-hardened to `0600` during preflight and after writes, and each receipt batch is fsync'd before lock release. Focused ledger coverage passes `12/12`; the complete backend unit suite passes `1,775/1,775`. No provider calls were made for this change.
- 2026-09-12 Finnhub earnings capability registration: the already-implemented per-symbol earnings history and forward earnings-calendar methods are now advertised under the explicit `earnings` capability. Focused provider/registry coverage passes `91/91`; no provider calls were made for this registration change.
- 2026-09-12 Finnhub default-event fallback: the live-proven Finnhub earnings adapter is now included after Alpaca and EDGAR in the default `instrument_events` chain; root/backend environment examples, README, and provider documentation are synchronized. No provider calls were made for this configuration change.
- 2026-09-12 Alpha Vantage earnings history: the documented `EARNINGS` endpoint now normalizes annual/quarterly EPS, estimate, and surprise fields with strict dates/decimals; the adapter is explicitly quota-priced, advertised under `earnings`, and placed last in the default instrument-events fallback. Fixture/registry/quota coverage passes, and the bounded credentialed AAPL live earnings case passed `1/1` under run `alpha-earnings-20260912` after the prior capacity response.
- 2026-09-12 complete post-change live matrix: the 42-case provider suite passed `37/42`. Alpha Vantage produced its typed 25-requests/day capacity response for IPO-calendar and earnings after the shared key was exercised; Tradier, IBKR, and Ondo failed only their intentional credential preflights. The external ledger recorded 26 aggregate rows, 65 operations, 87 HTTP requests, and 22,749,557 response bytes under run `3a31e993-4b4c-41af-9688-e3ad8b8c3029`; no acceptance claim was made.
- 2026-09-12 Alpha Vantage adjustment correctness: the free `TIME_SERIES_DAILY` adapter now rejects `adjusted=True` before any provider call because the documented free response is raw and adjusted daily history is premium. Raw bars carry `raw`/`provider-native` provenance, and `get_current_price` explicitly requests raw history. Focused Alpha coverage passed `25/25`; the complete backend unit suite passed `1,781/1,781` with the existing 37 warnings. This prevents a raw response from being stored or reported as an adjusted dataset; no provider calls were made by the focused regression.
- The changed Alpha Vantage raw-history path was then credentialed-live validated on 2026-09-12: the bounded daily case passed `1/1` with `adjusted=False`. A sandboxed first attempt was stopped by the usage-ledger writability guard before transport; the authorized retry used the owner-managed ledger and recorded aggregate usage only outside Git.
- Adjustment-aware routing is now carried from market-data/workload requirements
  through provider resolution. Every currently raw-only history adapter
  (Alpha Vantage, IBKR, optional REST adapters, and keyless exchange feeds) is
  filtered before quota reservation or transport for adjusted requests while
  raw requests remain eligible. Bulk-history jobs now pass the same requirement
  through the resolver as well.
  Registry/resolver/bulk regressions, Ruff, compilation, and the complete
  backend unit suite pass `1,783/1,783`; no provider calls were made for this
  change.
- The registry now exposes `adjusted_price_history` as a separate semantic
  capability for providers admitted to adjusted history (currently Alpaca and
  the explicit legacy yfinance compatibility path). Raw-only adapters do not
  inherit that capability from an OHLCV-shaped method. Focused registry/provider
  coverage passes `261/261`; Ruff, compilation, diff, workstream, and Compose
  contract checks pass. A fresh bounded live revalidation of the newly
  credentialed Alpaca, SEC EDGAR, MarketData.app, and Dinari Sandbox cases
  passed `9/9` under run `9c961135-70dc-49ab-9e01-e456530a2e4f`; aggregate
  provider usage remains outside Git.
- A current read-only Docker readiness check remains blocked: the unprivileged
  socket probe was denied and the authorized check hung without a server
  version, so it was interrupted. No services or containers were started; the
  required Docker-backed acceptance gate remains unverified.
- Canonical OHLCV persistence now retains `market_series_id`, session,
  adjustment basis/version, and provider provenance in both the canonical bar
  upsert and provider-observation write path. Provider observations gained an
  additive `session` column in migration `8e9f0a1b2c3d`; SQLite migration
  coverage and provider/service regressions pass `212/212`, while the complete
  backend unit suite passes `1,797/1,797` with the known 37 warnings. This
  improves AC-SERIES fidelity without adding live provider evidence; the
  Docker-backed migration/full-stack gate remains unverified.
- The post-change bounded live regression for the provenance-bearing adapters
  passed `4/4` (`alpaca_credentialed_history` plus Binance/Coinbase/Kraken
  keyless history) under run
  `canonical-persistence-provenance-20260912`; aggregate usage remains in the
  owner-managed ledger outside Git and no credentials or payloads were
  persisted.
- Alpha Vantage and the shared optional REST raw-history parser now identify
  their provider in each bar provenance envelope, closing the remaining
  provider-attribution gap for persisted raw bars. Focused provider tests pass
  `272/272`, the complete backend unit suite passes `1,797/1,797`, and no new
  provider calls were needed because transport behavior is unchanged.
- Provider refreshes now create/reuse a deterministic `MarketSeries` and attach
  its ID to canonical bars and provider observations. OHLCV conflict identity
  is series/session-aware through `scope_key`, with `legacy:<session>` retained
  for older rows; migration `9f0a1b2c3d4e` backfills existing rows. Focused
  series/migration/service tests pass `19/19`, the complete backend unit suite
  passes `1,799/1,799`, and PostgreSQL migration/full-stack validation remains
  blocked by unavailable Docker.
- Compatibility reads now use a durable `market_series_default` mapping. The
  first admitted canonical series is stable, regular sessions supersede an
  extended-only default, and inactive mappings fall back to an active
  canonical series without mixing alternate feeds or legacy rows. Migration
  `a0b1c2d3e4f5` plus service/read regressions pass `21/21`; the complete
  backend unit suite passes `1,802/1,802`; PostgreSQL/full-stack validation
  remains Docker-gated.
- Cold/latest provider fetches now use the same deterministic `MarketSeries`
  attachment as historical repairs, preventing newly persisted latest bars
  from falling back to legacy `NULL` series rows after a default mapping is
  created. Focused market-data/default-mapping coverage passes `21/21`; the
  complete backend unit suite passes `1,804/1,804`; no provider calls were
  needed and PostgreSQL/full-stack validation remains Docker-gated.
- Bulk historical refreshes and the risk-free-rate history path now apply the
  same series attachment before persistence. Focused bulk/risk-free/market-data
  coverage passes `27/27`; the complete backend unit suite passes `1,805/1,805`;
  no provider calls were needed and PostgreSQL/full-stack validation remains
  Docker-gated.
- Synthetic OHLCV recomputation readback now applies the compatibility selector
  too, preventing alternate or legacy rows from leaking into derived chart
  results. The complete backend unit suite remains green at `1,805/1,805`;
  no provider calls were needed and PostgreSQL/full-stack validation remains
  Docker-gated.
- The selector now requires matching canonical bars before suppressing legacy
  rows. A pre-created or emptied canonical series cannot hide readable legacy
  history. Focused selector coverage passes `22/22`; the complete backend unit
  suite passes `1,806/1,806`; no provider calls were needed and
  PostgreSQL/full-stack validation remains Docker-gated.
- Provider batches containing mixed session/feed/adjustment metadata are now
  partitioned into separate deterministic `MarketSeries` identities before
  persistence. Focused market-data coverage passes `29/29`; the complete
  backend unit suite passes `1,807/1,807`; no provider calls were needed and
  PostgreSQL/full-stack validation remains Docker-gated.
- The complete bounded live matrix was rerun on 2026-09-12 with the
  owner-managed environment after the newly supplied credentials were made
  available. It collected all 42 cases and passed 37: Alpaca paper
  history/latest/assets/corporate-actions, SEC EDGAR profile/filings/Company
  Facts, MarketData.app expirations/option-chain/option-quote history, and the
  rotated Dinari Sandbox metadata/price/quote/history/news/dividend/split
  paths all passed. Alpha Vantage returned its typed documented 25-requests/day
  capacity response for IPO-calendar and earnings after the shared key was
  exercised. Tradier, IBKR, and Ondo remained exact missing-key preflights per
  the operator's explicit deferral. The run wrote aggregate-only usage to the
  external owner-managed ledger; no credentials or provider payloads entered
  Git. Routing remains fail-closed for the unreviewed provider-specific
  controls and deferred providers.
- The complete backend unit suite was rerun after the live validation and
  passed `1,807/1,807` with the repository's known 37 warnings. Ruff,
  compileall, diff, and workstream validation all passed. The required
  Docker-backed PostgreSQL/Redis/full-profile gate remains unverified because
  Docker readiness is unavailable; no services were started.
- Tokenized asset and corporate-action refresh summaries now pass provider
  exceptions through the shared bounded credential redactor before returning
  per-asset/event failure evidence. Focused tokenized-service coverage passed
  `7/7`; the complete backend unit suite passed `1,808/1,808` with the known
  37 warnings; Ruff, compileall, and diff checks passed. Source commit
  `836b4b72145746eb5006c46e9d7a1d1890725c89` is pushed. This was a
  transport-neutral safety fix, so no new live calls were made.
- Typed `ProviderRateLimitError` instances now filter response headers at
  construction time, so direct adapter failures cannot retain Authorization,
  Cookie, or provider-key headers before durable persistence filtering.
  Focused provider-error/quota coverage passed `4/4`; the complete backend unit
  suite passed `1,809/1,809` with the known 37 warnings; Ruff, compileall, and
  diff checks passed. Source commit `bdba91af78d27d55cbb5eac2b365bb39c0bfc606` is pushed. This
  was transport-neutral, so no new live calls were made.
- A fresh bounded credentialed refresh on 2026-09-12 passed `5/5` for the newly
  supplied provider domains: SEC EDGAR filing/Company Facts and complete
  directory reads, Alpaca paper history, MarketData.app option/quote history,
  and Dinari Sandbox metadata/price/quote/history/news/dividend/split. The
  owner-only external ledger recorded four provider rows, 21 upstream
  requests, and 5,834,028 response bytes under run
  `credentialed-refresh-20260912b`; no credentials or payloads entered Git.
  This is bounded transport evidence, not entitlement promotion: the complete
  matrix, provider-specific quota/terms controls, deferred provider
  credentials, and Docker-backed PostgreSQL/Redis gate remain open.
- Dinari's credentialed live case now exercises all four documented aggregate
  history windows (DAY, WEEK, MONTH, YEAR) as well as metadata, fair price,
  bid/ask quote, news, dividend, and split surfaces. The focused tokenized
  fixture/service suite passed `58/58`; the live case passed `1/1` with 19
  observed upstream requests and 860,410 response bytes; the complete backend
  unit suite passed `1,809/1,809`; Ruff, compileall, and diff checks passed.
  Source commit `a4b2fd1f185f00fca29b6c1e6ece1f2af4bbfef7` is pushed. This
  strengthens transport evidence only; Dinari quota, terms, and routing
  admission remain fail-closed.
- Alpaca's credentialed live coverage now includes the free-IEX five-minute
  candle path in addition to daily history, latest price, assets, and corporate
  actions. The new bounded live case passed `1/1` with one upstream request and
  36,274 response bytes; the complete backend unit suite passed `1,809/1,809`,
  and Ruff, compileall, and diff checks passed. Source commit
  `4f4d388b68c88e5d692f57950768c498fe5038f9` is pushed. This is transport
  evidence only; Alpaca corporate-action pagination remains fail-closed until
  its reviewed deployment bound is supplied.
- MarketData.app's credentialed live coverage now includes its documented
  five-minute delayed stock-candle path in addition to daily candles,
  expirations, current option chains, and historical single-contract quote
  reads. The new bounded live case passed `1/1` with one upstream request and
  14,724 response bytes; native rate-limit headers were observed and retained
  only in the redacted external ledger. Source commit
  `47d2920c37895427386d6732e789816ad5579e50` is pushed. The account-plan,
  response-priced chain/quote bound, and redistribution controls remain
  fail-closed.
- The complete 44-case manifest live matrix was rerun on 2026-09-12 after
  adding the Alpaca and MarketData.app five-minute probes. It passed `39/44`:
  all newly credentialed Alpaca, SEC EDGAR, MarketData.app, and Dinari Sandbox
  cases passed; Alpha Vantage returned its typed documented 25-requests/day
  capacity responses; and Tradier, IBKR, and Ondo remained exact intentional
  credential preflights. Generated run
  `e0e58468-df1a-493b-bfc4-f20fdce5a568` recorded 26 aggregate provider rows,
  95 upstream requests, and 23,108,321 response bytes in the owner-only
  external ledger. The wrapper made no acceptance claim; routing and
  provider-governance controls remain fail-closed.
- Direct live usage receipts now distinguish provider-row status from the
  pytest process result. Each provider records `failed_operations` and
  `exit_status`, while `process_exit_status` preserves the overall matrix
  outcome; the backend reader aggregates both views and the merger remains
  backward-compatible with legacy rows. A mixed-result regression proves a
  successful provider is not marked failed when another provider fails.
  Focused usage coverage passed `20/20`, the complete backend unit suite passed
  `1,810/1,810`, and Ruff, compileall, and diff checks passed. Source commit
  `00dad98d` is pushed; no provider calls were needed.
- Receipt-reconciliation coverage now asserts the new fields survive merger
  normalization and rejects impossible `failed_operations` counts. Focused
  live-ledger/usage coverage passed `21/21`, the complete backend unit suite
  passed `1,811/1,811`, and Ruff, compileall, and diff checks passed. Source
  commit `4234b2f2` is pushed; no provider calls were needed.
- The backend live-usage reader now rejects empty, oversized, or non-printable
  provider identifiers before aggregating owner-managed receipts, matching the
  merger's input boundary. Focused usage coverage passed `22/22`, the complete
  backend unit suite passed `1,812/1,812`, and Ruff, compileall, and diff checks
  passed. Source commit `b70ad8bf` is pushed; no provider calls were needed.
- Published FINRA, Tiingo, and FMP bandwidth pools now use conservative
  decimal-byte ceilings where the vendor's GB/MB wording does not declare
  binary units, with an explicit `limit_basis` recorded in each quota contract.
  The quota contract suite passed `71/71`, the complete backend unit suite
  passed `1,813/1,813`, and Ruff, compileall, and diff checks passed. Source
  commit `e055aab8` is pushed; no provider calls were needed.
- The configured external environment was audited without printing values:
  all supplied credential pairs and contact values are available through the
  owner-only environment, the intentionally deferred Tradier/IBKR/Ondo
  settings remain absent, and a tracked-file scan found no configured secret.
  Worktree `.env` and `backend/.env.dev` both resolve to the owner-only
  `/Users/jagnelo/.config/charting-platform/app.env` (mode `0600`).
- A production-seed regression now prevents the retired generic cooldown,
  concurrency, and burst defaults from returning; Coinbase's explicit
  provider-native 10-requests/second plus 15-burst contract remains allowed.
  Quota coverage passed `72/72`, the complete backend unit suite passed
  `1,814/1,814`, and Ruff, compileall, and diff checks passed. Source commit
  `e746b266` is pushed; no provider calls were needed.
- Cross-host OHLCV refresh coalescing now has an explicit opt-in Redis
  coordinator for deployments whose workers do not share one PostgreSQL
  transaction boundary. Canonical and bulk refresh paths use ownership-safe
  tokenized locks with bounded wait/TTL settings; timeout or transport failure
  is fail-closed and the lock remains disabled by default. Focused
  Redis/coalescing coverage passes `16/16`; an independent-client Redis
  contention/release regression is queued for the Docker-backed integration
  gate, which cannot run while the local Docker API is unavailable. No provider
  calls were made for this change. The complete backend unit suite passes
  `1,827/1,827`, Ruff/compile/diff and both Compose parses are clean, and source
  commit `417ce8fd` is pushed.
- Revalidated the configured-provider adapter and governance contract surface
  after the rotated Dinari Sandbox credentials were installed. New-provider,
  tokenized, optional-provider, registry/quota/runtime, and secret-wiring
  regressions pass `463/463`; Ruff, compilation, and `git diff --check` pass.
  This run made no external provider calls and does not replace the existing
  bounded live receipts for Alpaca, EDGAR, MarketData.app, and Dinari.
- The registered ARQ `task_refresh_instrument_data` path now forwards its
  worker Redis client into canonical `fetch_ohlcv`, extending opt-in
  cross-host refresh coordination to the legacy single-instrument worker
  entry point. The related worker/market-data/bulk suite passes `56/56`, with
  Ruff, compilation, and diff checks clean. Source commit `89b5782c` is
  pushed; no provider calls were made.
- The opt-in core workstation bootstrap now also forwards its explicit Redis
  client into canonical OHLCV refreshes (while retaining the no-Redis unit
  path), so both registered bootstrap and single-instrument worker entry
  points participate in the cross-host gate. The bootstrap/worker/market-data/
  bulk regression set passes `57/57`; Ruff, compilation, and diff checks pass.
  Source commit `cfb5e8c6` is pushed; no provider calls were made.
- The complete backend unit suite was re-run after both Redis-forwarding fixes:
  `1,828/1,828` passed with the repository's known 37 warnings. No provider
  calls or services were started; source commit `cfb5e8c6` remains clean under
  the focused static checks.
- Latest-price refreshes now use the same keyed process gate and opt-in
  tokenized Redis coordinator as OHLCV refreshes. The cache is rechecked while
  ownership is held before any provider call, and alert-worker preflight passes
  its ARQ Redis client explicitly. Focused latest-price/alert coverage passes
  `42/42`; the complete backend unit suite passes `1,832/1,832` with the
  repository's known 37 warnings, and Ruff, compileall, and diff checks pass.
  Source commit `f32d93a4` is pushed; no provider calls or services were
  started. The independent-client Redis contention regression remains blocked
  only by unavailable Docker and is not represented as passed evidence.
- Added the backend-only normalized market-event persistence service and an
  opt-in daily ARQ schedule. Providers advertising `market_events` are invoked
  through durable capability/quota routing; observations are idempotent by
  `(source, event_key)`, exact provider-symbol and unique SEC CIK matches link
  canonical targets, ambiguous ticker matches remain unlinked, and provider
  failures are retained per source without discarding successful observations.
  Focused service/worker coverage passes `33/33`; the complete backend unit
  suite passes `1,838/1,838` with the known 37 warnings. Ruff, compileall,
  `git diff --check`, and both Compose contract parses pass. Source commit
  `ea105151` is pushed; no provider calls or services were started. The new
  schedule is disabled by default and does not add frontend changes. Docker
  full-stack validation, cross-provider reconciliation, pre-listing
  materialization, EDGAR/Alpha feed completion, and calendar UX remain open.
- Added Alpha Vantage's documentation-faithful `EARNINGS_CALENDAR` CSV
  adapter with explicit 3/6/12-month horizon validation, inclusive filtering,
  strict row/date checks, and normalized forward-earnings event keys. The
  market-event service invokes it as a separate `fetch_earnings_calendar`
  operation, independently reserving one request against Alpha's documented
  25-requests/day key. The opt-in live suite now contains a bounded Alpha
  calendar case. Provider/service/quota fixtures pass `275/275`, the complete
  backend unit suite passes `1,842/1,842` with 37 known warnings, and live
  collection, Ruff, compileall, and diff checks pass. Source commit
  `d954443e` is pushed; no provider calls or services were started in this
  change. The new live case remains pending execution because the shared Alpha
  key has already returned its documented daily-capacity response; this is not
  represented as live success.
- Added the authenticated backend-only `GET /api/v1/calendar/market-events`
  read path for persisted market-wide events. Inclusive date bounds cover both
  effective-date and timestamp-only records; optional event type, source,
  instrument, issuer, and bounded limit filters preserve provider provenance
  without triggering upstream I/O. Router coverage passes `2/2`, the complete
  backend unit suite passes `1,844/1,844` with the existing 37 warnings, and
  Ruff, compileall, and diff checks pass. No frontend or ETF-provider files
  changed and no services or provider calls were started. Source commit
  `b83fac31` is pushed with the implementation and documentation.
- Added a bounded EDGAR IPO-pipeline detector and persistence service for
  explicitly supplied CIK batches. Recent `S-1`, `S-1/A`, `F-1`, `F-1/A`, and
  `424B*` submissions become provisional `ipo_pipeline` events with
  accession/document provenance; each CIK is routed through the existing
  `market_events` quota policy and per-issuer failures are retained without
  implicit SEC-issuer enumeration. Focused provider/service/quota coverage
  passes `281/281`, the complete backend unit suite passes `1,850/1,850`, the
  EDGAR live case now includes a bounded pipeline read, and Ruff, compileall,
  and diff checks pass. Source commit `a52e47ca` is pushed; live execution
  remains part of the next credentialed matrix.
- The owner-configured live matrix was rerun with the supplied Alpaca paper,
  MarketData.app, rotated Dinari Sandbox, and SEC contact settings. It
  collected 45 cases and passed 39; Alpaca, EDGAR, MarketData.app, and Dinari
  passed their bounded reads. Alpha Vantage returned typed documented
  25-requests/day capacity responses for IPO-calendar and both earnings reads;
  Tradier, IBKR, and Ondo remained exact intentional credential preflights.
  Aggregate-only receipt run `ef7c9f58-f408-4501-b25a-2dcf6ae298fe` is in the
  owner-managed external ledger and is not acceptance evidence.
- Added durable `market_event_consensus_v1` reconciliation. Provider event
  rows and raw payloads remain immutable; only exact event-type plus canonical
  target (instrument, issuer, or explicit venue MIC) plus occurrence-date
  candidates are grouped. Single-source, corroborated, and conflicted states
  are explicit, with field-level conflict values and ungrouped unresolved
  observations. Refresh and EDGAR services run the bounded pass, the calendar
  response exposes consensus metadata, and admin operators can inspect groups
  at `/api/v1/market-data/event-consensus`. Focused coverage passes `16/16`,
  the complete backend unit suite passes `1,857/1,857`, Ruff, compileall, and
  diff checks pass. Source commit `84b949d8` is pushed; Docker-backed migration/full-
  stack validation remains required. Pre-listing materialization and frontend
  calendar surfaces remain out of scope/open, and no ETF-provider files changed.
- Added additive `market_event_prelisting_candidate` storage and a bounded,
  backend-only pre-listing workflow. Future IPO/IPO-pipeline observations are
  deduplicated by consensus, validated symbols create one inactive provisional
  stock instrument with stable-identifier/provider provenance, and conflicted,
  malformed, or taxonomy-missing evidence is quarantined or skipped. Promotion
  requires a unique active FIGI/ISIN/CUSIP match or an exact provider-symbol plus
  exchange-MIC match; ticker-only and ambiguous matches stay pending. The opt-in
  worker schedule and admin evidence path
  `/api/v1/market-data/prelisting-candidates` are wired through local/RPi
  configuration. Focused coverage passes `42/42`; the complete backend unit
  suite passes `1,868/1,868` with the known 37 warnings; Ruff, compileall,
  diff checks, and both Compose parses pass. Source commit `fc127db6` is pushed.
  Docker-backed migration/full-stack validation remains unavailable. Global EDGAR
  candidate enumeration, provider governance/credential gates, production
  reconciliation, 30-day shadow evidence, and frontend calendar surfaces remain
  open; no ETF-provider files changed.
- Documented the separate backend/worker deployment controls for pre-listing
  materialization, including its explicit opt-in, bounded lookahead/event
  limits, quarantine behavior, and prohibition on ticker-only identity merges.
  Source commit `eeb8b36e` is pushed; no runtime/provider calls were made.
- Added a separately disabled durable EDGAR issuer-universe scan. The ARQ
  worker advances through canonical issuer rows with non-null CIKs in bounded
  batches, composes the existing per-CIK pipeline with `commit=False`, and
  commits provider observations and cursor state together. The admin-only
  `/api/v1/market-data/event-scan-state` route exposes cursor, cycle, batch,
  failure, and provenance diagnostics. Focused scan coverage passes `56/56`;
  the complete backend unit suite passes `1,876/1,876` with the known 37
  warnings; Ruff, compileall, diff checks, and both Compose parses pass. Source
  commit `137f1103` is pushed. This is a bounded best-effort scan of known
  canonical issuers, not proof of complete SEC/global candidate coverage;
  Docker-backed migration/full-stack validation remains unavailable and no
  provider calls were made in this change. No frontend or ETF-provider files
  changed.

- Tokenized-security persistence now enforces stable-ID-first linkage for
  economic underlyings. A supplied ISIN is resolved against both the canonical
  instrument field and active ISIN identifier registry; unresolved or
  ambiguous ISIN evidence never falls back to a ticker, while ticker-only
  records still require one active listing. Provenance now records
  `linked_by_isin`, `linked_by_symbol`, or the explicit unresolved status.
  Focused tokenized service coverage passes 10/10 and the complete backend
  unit suite passes 1,879/1,879 with the known 37 warnings. No frontend or
  ETF-constituent adapter files changed. Source commit and metadata checkpoint
  are pending for this continuation; Docker-backed validation remains
  unavailable.

- SEC EDGAR ticker-directory loading now preserves duplicate ticker rows as an
  explicit ambiguous cache entry instead of silently overwriting the earlier
  CIK. Profile, earnings, and issuer-search resolution refuse ambiguous
  ticker-only candidates until venue or security-level evidence is available.
  Focused EDGAR ticker coverage passes 27/27 and the complete backend unit
  suite passes 1,880/1,880 with the known 37 warnings. No provider calls were
  made; source commit `8418c5ed` is pushed and Docker-backed validation remains
  unavailable.

- Tokenized xStocks and Dinari records now retain provider-published underlying
  FIGI, composite FIGI, ISIN, and CUSIP values. The tokenized-asset detail
  model has additive nullable columns with a reversible migration; stable-ID
  lookup checks canonical domain keys and active identifier rows in priority
  order, refuses conflicting or unresolved evidence, and only uses a unique
  ticker when no stable identifier exists. Focused migration/provider/service
  coverage passes 66/66 and the complete backend unit suite passes 1,883/1,883
  with the known 37 warnings. The admin integration contract is covered, but
  Docker-backed execution remains unavailable. Source commit `d235fda8` is
  pushed; no provider calls or credentials were used. Stable identifier values
  are canonicalized with the shared identity normalizer before lookup and
  persistence, while the raw provider payload remains available for audit.

- The affected live adapter checks passed `2/2` on 2026-09-12 after the
  stable-identifier mapping change: xStocks completed 2 operations/3 HTTP
  requests and Dinari Sandbox completed 10 operations/19 HTTP requests.
  Aggregate-only receipts are in the owner-managed external ledger under run
  `tokenized-identifiers-20260912`; no credentials or provider payloads entered
  Git. This is provider transport/parsing evidence, not entitlement or
  redistribution approval.

- Universe discovery now uses normalized ticker, canonical exchange MIC, and
  instrument type as its matching key. A sole venue-less legacy listing may be
  enriched once; known cross-venue collisions, duplicate local keys, and
  ambiguous unqualified candidates are fail-closed for promotion instead of
  silently merged. The regression proves two `DUAL` rows on Nasdaq and NYSE
  create two canonical instruments. Focused seed coverage passes `4/4`; the
  complete backend unit suite passes `1,886/1,886` with the known 37 warnings.
  Changed-file Ruff, format, compileall, and diff checks pass. Source commit
  `5658ffa0` is pushed. Docker-backed migration/full-stack validation remains
  unavailable; no frontend or ETF-provider adapter files changed.

- Corrected the discovery-service scope statement to describe the configured
  chain as US-venue focused, with explicitly configured crypto exceptions,
  rather than implying global-market completeness. Coverage and entitlement
  completeness remain provider-specific observations. Changed-file lint,
  formatting, and the four seed-universe regressions pass; source commit
  `b9bb9b92` is pushed.

- Legacy universe discovery now consumes provider-published FIGI, composite
  FIGI, ISIN, CUSIP, and SEDOL values before applying ticker/venue compatibility
  logic. A unique stable owner is reused across ticker changes and additional
  venue listings; a new stable key is never weakened to ticker-only matching,
  and conflicting stable owners remain fail-closed while the raw discovery
  snapshot is retained. Focused seed coverage passes `7/7`; the complete
  backend unit suite passes `1,889/1,889` with the known 37 warnings. Changed
  files pass Ruff, format, compileall, and diff checks. Source commit
  `58163e11` and validation profile `stable-identifier-universe-reconciliation-20260912`
  are recorded in the workstream; no provider calls, frontend files, or
  ETF-provider adapter files changed.

- Durable `reconcile_us_universe` now applies the same stable-identifier-first
  policy. It reuses one FIGI/composite FIGI/ISIN/CUSIP/SEDOL owner across ticker
  changes, refuses ticker fallback for unresolved stable keys, and quarantines
  alias, cross-owner, type, and ticker/venue conflicts while retaining the
  lifecycle observation. Focused reconciliation coverage passes `14/14`; the
  complete backend unit suite passes `1,893/1,893` with the known 37 warnings.
  Source commits `ffc96fe8` and `495854e8` are pushed; the broader Docker-backed migration,
  provider-governance, and deployment gates remain unchanged.

- SEC EDGAR profile ingestion now validates `tickers` and `exchanges` as
  non-empty string arrays and rejects mismatched lengths instead of iterating
  scalar strings or producing partial listing history. Focused SEC regression
  coverage passes `5/5`; provider/tokenized suites pass `258/258`, and the
  complete backend unit suite passes `1,896/1,896` with the known 37 warnings.
  Ruff, compileall, and diff checks pass. Source commit `853d95f5` is pushed;
  no provider calls, frontend files, or ETF-provider adapter files changed.

- Dinari stock and stock-split catalogue reads now use the current v2 cursor
  contract (`limit`/`order`/`next`) with instance-scoped cursor state. The
  adapter validates `pagination_metadata.next`, rejects missing/malformed or
  repeated cursors, retains an explicit legacy list-response fallback, and
  permits only explicit in-order split-page continuation on the same adapter
  instance. It never follows cursors in an unbounded loop or silently reuses a
  cursor across split feeds. Focused tokenized provider coverage passes `63/63` after
  the continuation addition; no frontend or ETF-provider files changed.

- Fresh credentialed live validation on 2026-09-12 passed all `10/10` selected
  test functions: SEC EDGAR `3/3` (5 operations/6 requests), Alpaca paper `4/4`
  (5/5), MarketData.app `2/2` (4/4), and Dinari Sandbox `1/1` (10 operations/19
  requests) after the cursor transport change. Redacted receipts were merged
  into the owner-managed external ledger (`accepted=4`, `duplicates=0`,
  `rejected=0`). This proves bounded transport/schema behavior only; provider
  quota, legal/redistribution, account-plan, and routing-admission gates remain
  independent and fail-closed.

- Dinari ticker-like metadata lookups now send the documented `symbols[]`
  server-side filter, preventing a valid symbol from being missed after the
  first catalogue page. UUID lookups retain the unfiltered compatibility path,
  and cursor state is isolated by filter. The changed compound Sandbox case
  passed `1/1` (11 measured operations/20 HTTP requests); two aggregate-only
  receipts were merged into the owner ledger (`accepted=2`, `duplicates=0`,
  `rejected=0`). Dinari quota, terms, and routing admission remain fail-closed.

- Dinari now advertises the generic `tokenized_corporate_actions` capability.
  Symbol-scoped reads combine its per-stock dividends and splits; unscoped
  reads are the bounded global split feed, with `upcoming` rejected. Later
  split pages require the preceding page's opaque cursor and are requested
  explicitly; unsupported or missing continuation state fails closed. The
  changed Sandbox live case passed `1/1`
  (12 measured operations/23 HTTP requests), and its aggregate-only receipt was
  merged into the owner-managed ledger. Full backend unit coverage passes
  `1,907/1,907`; source commit `f296a507` is pushed. Dinari quota, terms, and
  routing admission remain fail-closed; no frontend or ETF-provider files changed.

- The shared tokenized event linker now recognizes Dinari's provider-native
  `stock_id`/`stockId` fields. A scheduler regression proves a global split row
  links to the persisted Dinari token identity rather than remaining falsely
  unlinked; full backend unit coverage passes `1,907/1,907`, source commit
  `e332e727` is pushed, and no provider calls or frontend/ETF-provider files
  changed. Dinari quota, terms, and routing admission remain fail-closed.

- Dinari global and per-stock split feeds now retain each documented opaque
  `next` cursor and allow only explicit in-order continuation on the same
  adapter instance. Missing, repeated, or cross-limit cursor state fails
  closed; legacy page-shaped responses remain supported. Focused tokenized
  provider coverage passes `64/64`, the complete backend unit suite passes
  `1,910/1,910`, and the credentialed Sandbox case passes `1/1` with 23 HTTP
  requests and 12 measured operations. Source commit `ba527830` is pushed;
  no frontend or ETF-provider files changed. Dinari quota, terms, and routing
  admission remain fail-closed.

- Dinari UUID metadata lookups now fail closed when the first unfiltered
  catalogue page advertises a continuation but does not contain the requested
  UUID. This prevents a paginated miss from being reported as `None`; every
  lookup still fetches current metadata, with no unreviewed cache. The focused
  tokenized provider suite passes `65/65`, and the complete backend unit suite
  passes `1,911/1,911`. Source commit `51fed55b` is pushed; no frontend or
  ETF-provider files changed. Dinari quota, terms, and routing admission remain
  fail-closed.

- A superseding network-enabled rerun on 2026-09-12 passed all `10/10` selected
  credentialed provider tests after the Dinari UUID correction. SEC EDGAR
  profile, filing/facts, and complete ticker/exchange-directory pagination
  passed `3/3` (5 operations/6 requests); Alpaca paper daily/intraday/latest/
  assets/corporate-actions passed `4/4` (5/5); MarketData.app options and
  five-minute history passed `2/2` (4/4); and Dinari Sandbox metadata, fair
  price, quote, four history windows, news, dividends, and splits passed `1/1`
  (12 operations/23 requests). The successful aggregate-only receipt was merged
  into `/Users/jagnelo/.config/charting-platform/provider-live-usage.jsonl`
  (`accepted=4`, `duplicates=0`, `rejected=0`). The preceding sandbox-DNS
  attempt measured zero requests and was excluded. Provider quota, plan,
  commercial, US-eligibility, redistribution, and response-dependent routing
  gates remain independently fail-closed; no credentials or payloads entered
  Git.

- Added a separate complete SEC issuer-directory path. `EdgarProvider` now
  deduplicates the official cached `company_tickers.json` rows by CIK (including
  ambiguous ticker candidates) and exposes deterministic bounded pages. The
  durable `edgar:ipo_pipeline:sec_directory` scan stores its offset, total,
  cycle, and last batch in `MarketEventScanState.provenance`, routes directory
  discovery through the EDGAR market-events quota policy, and reuses the
  existing bounded per-CIK IPO parser. It records redacted failures, refuses
  non-progressing or duplicate-CIK pages, and the task layer prevents the
  legacy issuer-table scan and directory scan from running together. The new
  worker schedule and configuration are disabled by default and wired through
  local/RPi Compose without secrets or frontend/ETF-provider changes.

- Validation after this change: focused EDGAR/scan/worker/quota coverage passed
  `149/149` (the command was intentionally focused, so pytest reported the
  repository coverage threshold as unmet); the added mutual-exclusion regression
  plus EDGAR/scan slice passed `40/40` with `--no-cov`; changed-file Ruff,
  format, compileall, and diff checks passed. The final complete backend unit
  suite against the pushed source passed `1,923/1,923` with 69.68% coverage and
  the known 37 warnings. The credentialed SEC live directory-completeness probe
  passed `1/1`, verified the declared total and unique 10-digit CIK pagination,
  and emitted one aggregate-only usage row outside Git (the live command's
  process status is `1` solely because single-test coverage is below the global
  threshold). Compose parsing passed with `--no-interpolate` for both root and
  RPi definitions. Docker-backed migration/full-stack validation remains
  blocked by the local Docker API 500.

- The SEC directory scan remains opt-in and non-routable until an operator
  reviews its submissions-request budget and canonical issuer-materialization
  policy. A complete directory cycle means every CIK was attempted; it does not
  claim current tradability or infer listing dates from filing dates. Provider
  quota/legal/redistribution gates, production NMS/OTC reconciliation, CI and
  deployment secret distribution, and the separately approved shadow run remain
  open. The parallel `feat/etf-holdings-constituents` branch remains untouched;
  only the generic issuer/identity surface is shared and must be reconciled at
  staging integration.

- The SEC complete unique-CIK live probe now resets the provider's in-process
  directory cache before measuring its first request, so the case is isolated
  from preceding SEC probes. The bounded credentialed SEC/Alpaca/MarketData.app/
  Dinari selection passed `9/9` after this correction. The complete backend unit
  profile passed `1,923/1,923` with 69.68% coverage; running all tests without
  Docker still produces setup errors only for PostgreSQL/Redis-backed integration
  fixtures because the local Docker API is unavailable. No routing entitlement
  or provider policy changed, and only aggregate usage was written outside Git.

- The SEC probe setup now uses pytest restoration for the cache globals, so the
  test also leaves later live cases isolated. The standalone credentialed probe
  passed `1/1` after this refinement; no provider policy, quota contract, or
  routing entitlement changed.

- The complete manifest-driven live matrix was rerun after the SEC isolation
  refinement with the existing operator-owned environment. It collected 46
  cases and passed `40/46`. The six non-passes were the expected typed Alpha
  Vantage 25-requests/day capacity responses for IPO-calendar and both earnings
  reads plus the exact missing-credential preflights for intentionally deferred
  Tradier, IBKR, and Ondo. The wrapper retained its nonzero/no-acceptance result;
  no unexpected provider failure or routing-policy change occurred.

- Source checkpoint `ed37d583a` adds an explicit fail-closed
  `MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_SUBMISSIONS_REQUESTS` control. The
  SEC directory task refuses to run without a positive reviewed bound, rejects
  bounds above 500 or below the configured directory page size, and the service
  validates and persists the bound in scan-state provenance. This makes the
  directory-page request budget and the per-CIK submissions fan-out budget
  independently visible; it does not activate the scan. Dinari's official
  partner-fees documentation is also recorded: Sandbox is for evaluation,
  while production API access starts at $2,000/month; no numeric quota is
  inferred.

- Validation for this checkpoint: the focused EDGAR scan/worker suite passed
  `46/46`; changed-file Ruff, format, compileall, diff, and root/RPi Compose
  syntax checks passed. No provider calls or credentials were used for this
  safety/documentation change. The prior complete credentialed matrix remains
  `40/46` with only the documented Alpha Vantage capacity responses and the
  intentionally deferred Tradier/IBKR/Ondo preflights; Docker-backed
  PostgreSQL/Redis validation remains unavailable in this environment.

- The complete backend unit suite was rerun after the source change and passed
  `1,925/1,925` in 65.61 seconds with 37 warnings. This is unit evidence only;
  the required PostgreSQL/Redis full-stack gate remains blocked by the local
  Docker API. No additional live provider calls were made.

- Source checkpoint `b072b1e94` adds MarketData.app's documented authenticated
  `/user/` account introspection surface. `ProviderAccountUsage` preserves the
  native credit limit, remaining credits, per-request charge, reset timestamp,
  and options-data entitlement; the unversioned endpoint's documented 404
  no-account response returns no snapshot. The adapter never derives a plan or
  widens routing from this observation; the reviewed plan/credit pair and
  response-priced option-chain bound remain explicit admission controls.

- Validation after this checkpoint: the optional-provider fixture suite passed
  `80/80`, the broader provider/runtime suite passed `530/530`, and the complete
  backend unit suite passed `1,928/1,928` with 37 warnings. Ruff, format,
  compileall, and diff checks passed. One bounded credentialed
  `test_marketdata_app_credentialed_account_usage_snapshot` live test passed
  `1/1` against `https://api.marketdata.app/user/`, recording only aggregate
  telemetry outside Git. No full live matrix rerun was made, so the shared
  provider quotas were not needlessly consumed. Docker-backed migration and
  full-stack validation remains blocked by the local Docker API.

- Source checkpoint `f37ce79e9` adds provider-specific Alpaca market-data
  counter reconciliation. `X-RateLimit-Limit` and `X-RateLimit-Remaining` are
  converted into durable request-window usage only when the response confirms
  the exact reviewed market-data contract; mismatched, malformed, or Broker
  API correspondent headers remain observational. This closes a cross-session
  accounting gap without introducing a generic limit or changing routing.

- Validation for the Alpaca accounting checkpoint: the provider quota/runtime
  suite passed `81/81` and provider fixture coverage plus usage summaries passed
  `81/81`; Ruff, diff, and compilation checks passed. No additional live calls
  were required because the existing credentialed Alpaca receipts already
  contain the native `200`/`199`/reset header snapshot and the new reconciliation
  path is covered against that documented response shape. The Docker-backed
  migration/full-stack gate and the broader provider/legal/deployment gates
  remain open.

- Source checkpoint `1aeb25989` records the bounded MarketData.app account
  snapshot in `docs/provider-live-validation.md`, including the observed native
  10,000-credit daily header and the fact that it remains observational until
  the operator reviews the plan/credit pair and option-chain bound. The guide
  also reiterates that the account probe is quota-aware and does not widen
  routing.

- Source checkpoint `fbf9bd02d` tightens the account snapshot parser to reject
  fractional or otherwise coercible quota counters. Only provider-declared
  integers or signed digit strings are accepted, preventing silent truncation
  of a native usage value. Focused optional-provider coverage passes `82/82`.

- Final unit verification for the latest source checkpoint passed
  `1,931/1,931` in 72.67 seconds with the known 37 warnings. No provider calls
  or credentials were used by this full suite; the Docker-backed migration and
  full-stack gate remains the authoritative unverified check in this
  environment.

- Source checkpoint after the SEC directory policy completion adds an explicit
  `MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ISSUER_MATERIALIZATION_MODE` control.
  The default `disabled` mode performs no issuer writes. The reviewed
  `create_missing` mode validates directory CIK/name/ticker evidence, creates
  only absent canonical `Issuer` rows, records the policy and ticker evidence
  in provenance, and never creates instruments/listings, changes existing
  legal names, or deactivates records. Domain conflicts and malformed names or
  tickers fail closed. Focused SEC directory/service/worker coverage passes
  `50/50`; the full backend unit gate and deployment/full-stack gates remain
  to be rerun/verified after the source checkpoint is committed.

- Source checkpoint `b4f1d614` propagates the SEC issuer-materialization policy
  to both backend/worker Compose services (root and RPi), `.env.example`, the
  deployment runbook, and the manual GitHub live workflow. All paths default to
  `disabled`; no credential or policy value was added to Git.

- Source checkpoint `76642baf` adds a regression proving that
  `create_missing` leaves an existing issuer's legal name unchanged and only
  reports it as already present. The focused SEC directory suite now passes
  `10/10`.

- Final unit verification for source checkpoint `76642baf` passed
  `1,936/1,936` with the known 37 warnings. No provider calls or credentials
  were used; Docker-backed migration/full-stack validation and provider,
  deployment, and shadow gates remain open.

- Source checkpoint `9861703a` adds the backend environment-example and
  secret-wiring regression for the SEC policy setting. Root/RPi Compose and
  GitHub workflow paths are asserted to pass it only to backend/worker trusted
  processes, with `disabled` as the default; the research runner receives no
  provider controls.

- Source checkpoint `d555450b` extends the SEC directory regression to assert
  that `create_missing` is issuer-only: no `Instrument` or `InstrumentListing`
  rows are created. The focused service suite remains `10/10`.

- Source checkpoint `cb7dce9f` removes the last implicit yfinance options
  default. Settings, both environment examples, root/RPi Compose, README,
  provider documentation, and registry tests now consistently select
  `marketdata_app` as the API-first options candidate while preserving the
  reviewed-plan/credit and response-priced-chain fail-closed controls.
  yfinance remains available only through an explicit legacy override. The
  complete backend unit suite passes `1,936/1,936` with 37 warnings; focused
  registry/runtime coverage passes `30/30`; Ruff, compileall, Compose parsing,
  and diff checks pass. No provider calls or credentials were used for this
  configuration correction, and no frontend or ETF-provider files changed.

- Source checkpoint `c7bcc82b` closes the SEC directory configuration
  propagation gap in the manual GitHub live-validation workflow. Enablement,
  issuer/event bounds, submissions-request bound, and issuer-materialization
  mode now arrive as non-secret environment variables with disabled/zero
  defaults. The wiring regression passes `17/17`; workflow YAML parsing, Ruff,
  compileall, and diff checks pass. No provider calls or credentials were used,
  and no frontend or ETF-provider files changed.

- Source checkpoint `24370c37` removes an unsafe local quota fallback. The
  process-local token bucket and policy lookup now reject zero, negative,
  boolean, and non-integer rate/burst limits instead of normalizing them to a
  one-token allowance. Focused runtime coverage passes `11/11`; the complete
  backend unit suite passes `1,943/1,943` with 37 warnings. No provider calls or
  credentials were used, and no frontend or ETF-provider files changed.

- Source checkpoint `5153fde6` extends the same fail-closed behavior to token
  acquisition units: zero, negative, boolean, fractional, string, and null
  values are rejected instead of coerced to one token. Focused runtime
  coverage passes `17/17` selected tests; the complete backend unit suite
  passes `1,949/1,949` with 37 warnings. Ruff, compileall, and diff checks pass.
  No provider calls or credentials were used, and no frontend or ETF-provider
  files changed.

- Source checkpoint `c1c505ee` removes fractional operation-cost rounding.
  Reviewed operation costs and caller overrides must be positive integral
  request/credit/weight units; reservation and settlement no longer apply a
  one-unit fallback. Focused quota coverage passes `93/93` selected cases and
  the complete backend unit suite passes `1,953/1,953` with 37 warnings. Ruff,
  compileall, and diff checks pass. No provider calls or credentials were
  used, and no frontend or ETF-provider files changed.

- Source checkpoint `db8eb16e` hardens durable quota reservation entry points.
  Boolean, fractional, string, negative, zero, and malformed reservation
  values are rejected instead of coerced into provider units. Focused
  routing/quota coverage passes `92/92` selected cases and the complete backend
  unit suite passes `1,967/1,967` with 37 warnings. Ruff, compileall, and diff
  checks pass. No provider calls or credentials were used, and no frontend or
  ETF-provider files changed.

- Source checkpoint `b9435a63` hardens quota settlement. Malformed
  reserved/consumed/observed units and missing transport reservation dimensions
  are rejected rather than converted to zero or one; explicit zero remains
  valid for non-applicable dimensions. Focused settlement coverage passes
  `112/112` selected cases and the complete backend unit suite passes
  `1,971/1,971` with 37 warnings. Ruff, compileall, and diff checks pass. No
  provider calls or credentials were used, and no frontend or ETF-provider
  files changed.

- Source checkpoint `265ec186` hardens the legacy workload-lease settlement
  path. Malformed lease/consumed units, non-boolean success flags, and invalid
  or duplicate durable quota-window IDs now fail closed instead of being
  coerced or redirected to a timestamp compatibility lookup. Focused
  quota/settlement coverage passes `112/112` selected cases and the complete
  backend unit suite passes `1,984/1,984` with 37 warnings. Ruff, compileall,
  and diff checks pass. No provider calls or credentials were used, and no
  frontend or ETF-provider files changed.

- Source checkpoint `a7c01524` closes the typed reset-header propagation edge.
  When an adapter raises `ProviderRateLimitError` with allow-listed reset
  headers but no `retry_at`, the runtime now derives the provider-declared
  retry timestamp. Missing or malformed values remain unknown; no generic
  cooldown is invented. Focused capacity/quota coverage passes `87/87` selected
  cases and the complete backend unit suite passes `1,985/1,985` with 37
  warnings. Ruff, compileall, and diff checks pass; no provider calls or
  credentials were used, and no frontend or ETF-provider files changed.

- Source checkpoint `fe21e6be` closes two pagination-loop safety edges. Alpaca
  history rejects repeated provider page tokens, while universe reconciliation
  rejects malformed or repeated `next_url` cursor metadata before it can loop
  or reprocess the same page. Focused pagination/provider coverage passes
  `60/60`, and the complete backend unit suite passes `1,987/1,987` with 37
  warnings; Ruff, compileall, and diff checks pass. No provider calls or
  credentials were used, and no frontend or ETF-provider files changed.

- Source checkpoint `ba3a721d` closes an unsafe provider-usage diagnostic
  fallback. Malformed durable quota-window durations are no longer coerced to
  one second; such windows are excluded from active utilization and surfaced
  with their ID, dimension, and exact validation reason. Focused usage-window
  coverage passes `10/10`, and the complete backend unit suite passes
  `2,007/2,007` with 37 warnings; Ruff, compileall, and diff checks pass. No
  provider calls or credentials were used, and no frontend or ETF-provider
  files changed.

- Source checkpoint `ac2ce574` removes the last implicit durable reservation
  window. `reserve_provider_quota` now requires each caller to provide the
  provider-reviewed `window_seconds`; the helper cannot silently invent a
  one-minute reset interval. Focused routing/quota coverage passes `112/112`,
  and the complete backend unit suite passes `2,008/2,008` with 37 warnings;
  Ruff, compileall, and diff checks pass. No provider calls or credentials were
  used, and no frontend or ETF-provider files changed.

- Source checkpoint `a8ee8573` restores the Docker-backed backend gate. Two
  branch-owned integration fixtures were aligned with the implemented
  timeframe/freshness semantics (H4 seed spacing and historical watchlist
  membership), after which the complete scoped unit+integration gate passed
  `2,386/2,386` at `81.33%` combined coverage with 89 warnings. The labeled
  test resources were cleaned; no provider calls or credentials were used, and
  no provider adapter, frontend, or ETF-provider files changed.

- Source checkpoint `f6482ed2` closes a third pagination-loop edge in Alpaca
  corporate-action history. The adapter now rejects repeated pagination-token
  cycles instead of relying only on an immediate self-repeat or an optional
  page bound. Focused corporate-action coverage passes `7/7`, and the complete
  backend unit suite passes `1,988/1,988` with 37 warnings; Ruff, compileall,
  and diff checks pass. No provider calls or credentials were used, and no
  frontend or ETF-provider files changed.

- Source checkpoint `acfbfb2a` closes malformed-continuation edges in Massive
  ticker discovery and IPO pages. `next_url` values must be strings containing
  exactly one non-empty cursor; malformed, cursorless, or ambiguous metadata
  now fails closed instead of replaying pages or over-running the safety bound.
  Focused Massive coverage passes `11/11`, and the complete backend unit suite
  passes `1,993/1,993` with 37 warnings; Ruff, compileall, and diff checks
  pass. No provider calls or credentials were used, and no frontend or
  ETF-provider files changed.

- Source checkpoint `3cedc9d6` closes Dinari stock-catalogue and split pagination
  cycle edges. Both cursor chains now reject repeated cursors, and a fresh
  first-page request clears stale chain state before beginning a new run.
  Focused Dinari pagination coverage passes `11/11`, and the complete backend
  unit suite passes `1,996/1,996` with 37 warnings; Ruff, compileall, and diff
  checks pass. No provider calls or credentials were used, and no frontend or
  ETF-provider files changed.

- Source checkpoint `71faddb0` closes malformed `next_offset` handling in
  universe reconciliation. Boolean, non-integer, negative, and non-progressing
  offsets now fail closed instead of being treated as valid Python integers or
  allowing silent completion. Focused universe pagination coverage passes
  `5/5`, and the complete backend unit suite passes `2,000/2,000` with 37
  warnings; Ruff, compileall, and diff checks pass. No provider calls or
  credentials were used, and no frontend or ETF-provider files changed.

- Source checkpoint `3950f477c` persists provider-native account-usage
  observations independently of request logs. The new capability, model/table,
  explicit MarketData.app operation cost, admin history/refresh endpoints, and
  strict unit/counter/reset validation preserve native units, limits, remaining
  values, consumed values, reset timestamps, and options entitlements across
  sessions. Focused account-usage coverage passes `4/4`; the complete backend
  unit suite passes `2,013/2,013`; the Docker-backed combined gate passes
  `2,392/2,392` at `81.34%` combined coverage with 89 warnings; and the bounded
  credentialed MarketData.app account snapshot passes `1/1`. The migration
  compatibility validator is blocked by the repository's pre-existing duplicate
  revision and multiple Alembic heads, so no unrelated migration graph changes
  were made. No frontend or ETF-provider files changed.

- Source checkpoint `a4af6f95d` closes the refresh-job outcome persistence gap.
  Each durable attempt now retains start/finish timestamps and a redacted result
  summary. Successful worker refreshes record requested range, timeframe,
  observed-bar count, and explicit empty responses; retry/defer paths preserve
  bounded error and provider-reset evidence. The admin queue endpoint exposes
  these fields without lease tokens. Focused queue/worker/migration coverage
  passes `49/49`; the PostgreSQL admin integration passes `3/3`; the complete
  Docker-backed backend gate passes `2,393/2,393` at `81.35%` combined coverage
  with 89 warnings and cleaned labeled resources. No frontend or ETF-provider
  files changed. The future breadth/signal preflight migration and generic
  Alembic compatibility graph remain open.

- Source checkpoint `629e310c8` extends the shared OHLCV coverage gate to both
  production and ARQ-compatible indicator-alert execution. Grouped latest-price
  polling and grouped `(instrument, timeframe)` indicator snapshots happen
  before evaluation; the canonical indicator registry supplies explicit history
  floors for composite windows, while anchor timestamps and SAR factors are not
  misread as bar counts. Failed or insufficient-history groups are withheld
  rather than evaluated from partial local data. Focused alert-preflight
  coverage passes `8/8` and indicator history-floor regressions pass `2/2`
  (`39/39` across both focused files); PostgreSQL-backed worker alert checks pass `2/2`; the
  full backend unit suite passes `2,023/2,023` with 37 warnings; and the
  authoritative Docker-backed combined gate passes `2,402/2,402` at `81.37%`
  coverage with 89 warnings. The labeled testcontainer session was cleaned
  without host-wide pruning. No provider calls, credentials, frontend files,
  or ETF-provider adapter files changed. Future non-Strategy evaluator
  coordination, persisted evaluator run status, provider/legal/deployment/
  shadow gates, and generic migration compatibility remain open.

- The lock-protected credentialed live matrix was rerun on 2026-09-13 using the
  existing owner-managed environment and external usage ledger. It collected
  `47` cases and passed `41`; Alpha Vantage's IPO-calendar and two earnings
  operations returned the typed documented 25-requests/day capacity response,
  while Tradier, IBKR, and Ondo remained exact missing-credential preflights.
  The other configured and keyless/tokenized probes passed with bounded
  transport observations. The runner returned exit code `2` and made no
  acceptance claim. No credentials or response payloads entered Git.

- Source checkpoint `becb57299` extends the shared OHLCV coverage preflight to
  synchronous and streaming screeners. Existing grouped local snapshots retain
  raw rows for one preflight per required timeframe; indicator and price-change
  history floors are derived from the condition tree, and insufficient
  primary/D1/W1 coverage is withheld with explicit exclusions and an additive
  preflight summary. Focused screener/preflight coverage passed `36/36`, the
  database-backed screener integration passed `26/26`, the complete unit suite
  passed `2,025/2,025`, and the authoritative Docker-backed gate passed
  `2,404/2,404` at `81.37%` coverage. No provider calls, credentials,
  frontend files, or ETF-provider adapter files changed.

- Source checkpoint `440923ef3fe0` closes the separate evaluator-status gap for
  isolated research runs without creating another migration head. Enqueue,
  cancellation, and result collection now preserve a durable additive
  `resource_usage.evaluation` record; run and batch-result APIs expose
  `evaluation_status` while leaving `ResearchRun.status` as transport state.
  Completed runs with datasets plus exclusions are `partial`; exclusion-only
  runs are `deferred`. Research-job unit coverage passed `5/5`, the
  PostgreSQL-backed research API suite passed `24/24`, the complete backend
  unit suite passed `2,027/2,027`, and the authoritative Docker-backed gate
  passed `2,406/2,406` at `81.38%` coverage with 89 warnings. The labeled
  testcontainer session `8a8d4267-9ae9-4fb7-8863-1aa437fff179` was cleaned
  without host-wide pruning. No provider calls, credentials, frontend files,
  or ETF-provider adapter files changed. Future non-Strategy signal engines
  beyond screeners, provider/legal/deployment/shadow gates, and generic
  migration compatibility remain open.

- Source checkpoint `e1101d4801a2` extends the shared evaluator preflight into
  Market Map. Breadth history floors mirror the deterministic member and
  cross-sectional condition branches; return, RSI, relative-volume, and
  52-week map metrics have explicit local-bar floors. The response now exposes
  `coverage_preflight`, and non-Python colours are withheld when the required
  snapshot is not ready. Focused breadth/Market Map unit coverage passed
  `34/34`, the complete watchlist integration suite passed `49/49`, the
  complete backend unit suite passed `2,029/2,029`, and the authoritative
  Docker-backed gate passed `2,409/2,409` at `81.37%` coverage with 89
  warnings. The labeled testcontainer session
  `e25fae5d-dc9b-464c-a087-eb5b21c28f5a` was cleaned without host-wide
  pruning. No provider, frontend, or ETF-provider adapter files changed.
  Future non-Strategy evaluator engines beyond Market Map, provider/legal/
  deployment/shadow gates, and generic migration compatibility remain open.

- Source checkpoint `3a81d0818` extends the shared evaluator preflight to
  the explicit-symbol indicator batch endpoint. The canonical indicator
  registry supplies the minimum local history floor; the endpoint assesses its
  already loaded bars once without provider I/O, withholds under-sized values,
  and returns an additive serialized `coverage_preflight` report. Focused
  PostgreSQL indicator integration passed `2/2`; the complete backend unit suite
  passed `2,029/2,029`; and the authoritative Docker-backed gate passed
  `2,410/2,410` at `81.37%` combined coverage with 89 warnings. The labeled
  testcontainer session `64de1fe7-1993-4f05-8f8b-6030574fc8b8` was cleaned
  without host-wide pruning. No provider calls, credentials, frontend files,
  or ETF-provider adapter files changed. Future non-Strategy evaluator engines
  beyond the explicit indicator batch and Market Map, provider/legal/deployment/
  shadow gates, and generic migration compatibility remain open.

- Source checkpoint `62787b400` corrects indicator-batch preflight ordering:
  durable stale dataset state is applied to cached bars before the shared
  coverage report is built, so a stale value cannot be reported as ready. The
  focused indicator integration remains `2/2`, the complete unit suite remains
  `2,029/2,029`, changed-file Ruff/compile/diff checks pass, and the
  authoritative Docker-backed gate passes `2,410/2,410` at `81.37%` with 89
  warnings. Testcontainer session `046e1490-f5ae-455d-a040-f5cb701dc5f5` was
  cleaned without host-wide pruning. No provider calls, credentials, frontend
  files, or ETF-provider adapter files changed.

- Source checkpoint `84fee9ff3` extends the shared coverage-preflight contract
  to the local technical snapshot and relative-strength endpoints. Technical
  snapshots report their exact 252-bar full-history requirement while retaining
  metric-specific insufficiency warnings; relative strength reports per-leg
  local coverage while preserving its separate aligned-timestamp overlap
  warning. Focused PostgreSQL point-in-time analysis integration passed `3/3`,
  the complete backend unit suite passed `2,029/2,029`, changed-file Ruff,
  compileall, and diff checks passed, and the authoritative Docker-backed gate
  passed `2,410/2,410` at `81.38%` coverage with 89 warnings. Testcontainer
  session `80f7facd-b2fc-4374-b9a2-94230bca35ab` was cleaned without host-wide
  pruning. No provider calls, credentials, frontend files, or ETF-provider
  adapter files changed; provider/legal/deployment/shadow gates, future
  evaluator coordination, and generic migration compatibility remain open.

- Source checkpoint `11fc65d4d` preserves the technical-snapshot preflight in
  benchmark-family technical responses, per mapped role. Short local histories
  now expose the same deferred 252-bar report instead of silently losing the
  evaluator decision at the family wrapper. Focused PostgreSQL benchmark-family
  technical integration passed `1/1`, the complete backend unit suite passed
  `2,029/2,029`, changed-file Ruff/compileall/diff checks passed, and the
  authoritative Docker-backed gate passed `2,410/2,410` at `81.38%` coverage
  with 89 warnings. Testcontainer session
  `b0655d21-dde0-4d8d-8f51-17b273e6a69c` was cleaned without host-wide pruning.
  No provider calls, credentials, frontend files, or ETF-provider adapter
  files changed; provider/legal/deployment/shadow gates remain open.

- Source checkpoint `2a57aecd4` extends coverage preflight to benchmark-family
  and arbitrary-group relative-rotation responses. The required raw-bar floor
  is derived from `(2 * lookback + 1) * sampling`; existing aligned-overlap,
  stale-data, and metric warnings remain unchanged. Focused PostgreSQL rotation
  integration passed `2/2`, the complete backend unit suite passed `2,029/2,029`,
  changed-file Ruff/compileall/diff checks passed, and the authoritative
  Docker-backed gate passed `2,410/2,410` at `81.38%` coverage with 89 warnings.
  Testcontainer session `76862148-48fb-470c-8007-9dd9aab6371d` was cleaned
  without host-wide pruning. No provider calls, credentials, frontend files, or
  ETF-provider adapter files changed; provider/legal/deployment/shadow gates
  remain open.

- Source checkpoint `6992d1096` adds shared coverage preflight to the general
  group snapshot and current/historical group-breadth responses. Snapshot and
  current breadth report a 252-bar floor; historical breadth reports a 200-bar
  MA200 floor, while existing per-metric and point-in-time behavior remains
  unchanged. Focused PostgreSQL group integration passed `3/3`, the complete
  backend unit suite passed `2,029/2,029`, changed-file Ruff/compileall/diff
  checks passed, and the authoritative Docker-backed gate passed `2,410/2,410`
  at `81.38%` coverage with 89 warnings. Testcontainer session
  `eba83d98-8695-48ad-8dd8-544d8480a609` was cleaned without host-wide pruning.
  No provider calls, credentials, frontend files, or ETF-provider adapter
  files changed; provider/legal/deployment/shadow gates remain open.

- Source checkpoint `7baab8261` extends the shared provider-neutral coverage
  preflight to benchmark-family ratio responses. Every resolved role,
  cap-weighted benchmark, and explicit market benchmark is assessed from the
  already loaded local bars with a one-bar minimum; stale legs are removed
  before readiness is calculated, and a no-mapping batch receives an explicit
  empty report. Existing aligned-close ratio semantics and stale-result
  withholding remain unchanged. Focused PostgreSQL integration passed `1/1`,
  the complete backend unit suite passed `2,029/2,029` with 37 warnings,
  changed-file Ruff/compileall/diff checks passed, and the authoritative
  Docker-backed combined backend gate passed `2,410/2,410` at `81.38%` coverage
  with 89 warnings. Testcontainer session
  `b4d575ed-ec9b-466b-92a6-1ef21d81c579` was cleaned without host-wide
  pruning. No provider calls, credentials, frontend files, or ETF-provider
  adapter files changed. Provider/legal/deployment/shadow gates, future
  evaluator coordination, and generic migration compatibility remain open.

- Source checkpoint `eceada339` extends the shared coverage preflight to
  benchmark-family historical breadth. Each resolved role reports its exact
  local 200-bar floor (the MA200 requirement) after point-in-time membership
  resolution; short histories remain explicitly deferred rather than being
  represented as ready. Focused PostgreSQL integration passed `1/1`, the
  complete backend unit suite passed `2,029/2,029`, and the authoritative
  Docker-backed combined backend gate passed `2,410/2,410` at `81.39%` coverage
  with 89 warnings. Testcontainer session
  `0fed2d3f-4d0f-48c2-9f76-aa9774ea19b4` was cleaned without host-wide pruning.
  No provider calls, credentials, frontend files, or ETF-provider adapter
  files changed. Provider/legal/deployment/shadow gates, future evaluator
  coordination, and generic migration compatibility remain open.

- Source checkpoint `530c483f4` adds the shared OHLCV coverage preflight to the
  point-in-time derived equal-weight family series after membership and
  persisted-staleness filtering. Available members report `full`; cold or
  stale-filtered members remain explicit deferred/partial evidence without
  provider I/O or fabricated bars. Focused PostgreSQL integration passed `1/1`,
  the complete backend unit suite passed `2,029/2,029`, and the authoritative
  Docker-backed combined backend gate passed `2,410/2,410` at `81.39%` coverage
  with 89 warnings. Testcontainer session
  `cec94864-2b27-438f-a4b6-81995b423c2e` was cleaned without host-wide pruning.
  No provider calls, credentials, frontend files, or ETF-provider adapter
  files changed. Provider/legal/deployment/shadow gates, future evaluator
  coordination, and generic migration compatibility remain open.

- Source checkpoint `048f0a013` preserves the shared coverage preflight through
  the benchmark-family overview wrapper. Delegated cap-benchmark calls retain
  their group-snapshot report, while the no-cap path returns an explicit empty
  `benchmark_family_overview` report. Focused PostgreSQL integration passed
  `1/1`; the complete backend unit suite passed `2,029/2,029`; Ruff,
  compileall, and diff checks passed; and the authoritative Docker-backed
  combined backend gate passed `2,410/2,410` at `81.38%` coverage with 89
  warnings. Testcontainer session `84c9ed3d-cbc2-4772-8cd4-4da013fb33f3` was
  cleaned without host-wide pruning. No provider calls, credentials, frontend
  files, or ETF-provider adapter files changed. Provider/legal/deployment/
  shadow gates, future evaluator coordination, and generic migration
  compatibility remain open.

- Source checkpoint `dfded5c9b` extends the shared coverage preflight to the
  benchmark-family ranking response. The required local history is derived
  from the selected rank period (`offset + 1`, with a conservative 253-bar
  YTD floor); stale legs are removed before readiness is assessed, so a mixed
  ready/stale ranking reports `partial` while preserving role-level data
  withholding. Focused PostgreSQL ranking integration passed `1/1`, the
  complete backend unit suite passed `2,029/2,029` with 37 warnings,
  changed-file Ruff/compileall/diff checks passed, and the authoritative
  Docker-backed combined backend gate passed `2,410/2,410` at `81.38%` coverage
  with 89 warnings. Testcontainer session
  `fca9455d-1b53-4136-966e-0b7fc4228bfe` was cleaned without host-wide pruning.
  No provider calls, credentials, frontend files, or ETF-provider adapter
  files changed. Provider/legal/deployment/shadow gates, future evaluator
  coordination, and generic migration compatibility remain open.

- Source checkpoint `854effacc` extends the shared coverage preflight to
  cross-family current and historical ranking responses. Both endpoints use
  the selected rank-period floor (`offset + 1`, or a conservative 253-bar YTD
  floor); current ranking removes stale legs before readiness is assessed.
  Focused PostgreSQL integration passed `2/2`, the complete backend unit suite
  passed `2,029/2,029` with 37 warnings, changed-file Ruff/compileall/diff
  checks passed, and the authoritative Docker-backed combined backend gate
  passed `2,410/2,410` at `81.39%` coverage with 89 warnings. Testcontainer
  session `52efaa59-a591-4f64-aaa1-e93a11e2dd43` was cleaned without host-wide
  pruning. No provider calls, credentials, frontend files, or ETF-provider
  adapter files changed. Provider/legal/deployment/shadow gates, future
  evaluator coordination, and generic migration compatibility remain open.

- Source checkpoint `8d0ed6aa0` extends the shared OHLCV coverage preflight to
  benchmark-family concentration. Each delegated role is assessed after
  membership and persisted stale-ID filtering with the selected rank-period
  floor (`offset + 1`, or a conservative 253-bar YTD/unknown-period floor),
  so cold or short histories are explicitly partial/deferred rather than
  treated as ready. Focused PostgreSQL integration passed `1/1`, the complete
  backend unit suite passed `2,029/2,029`, and the authoritative Docker-backed
  combined backend gate passed `2,410/2,410` at `81.39%` coverage with 89
  warnings. Testcontainer session
  `a6b0769b-8234-4ac8-9212-edec1ebee61b` was cleaned without host-wide
  pruning. No provider calls, credentials, frontend files, or ETF-provider
  adapter files changed. Provider/legal/deployment/shadow gates, future
  evaluator coordination, and generic migration compatibility remain open.

- Source checkpoint `d5e4ab814` extends the shared OHLCV coverage contract to
  historical benchmark-family concentration and the industry proxy/classified
  industry snapshot evaluators. Historical concentration reports role-local and
  aggregate readiness after point-in-time membership resolution; industry
  routes use the exact 252-bar technical floor. Focused PostgreSQL integration
  passed `2/2`, the complete backend unit suite passed `2,029/2,029`, and the
  authoritative Docker-backed combined backend gate passed `2,410/2,410` at
  `81.40%` coverage with 89 warnings. Testcontainer session
  `dfc48281-bcbf-4170-a93c-3d8a43ae855e` was cleaned without host-wide pruning.
  No provider calls, credentials, frontend files, or ETF-provider adapter
  files changed. Provider/legal/deployment/shadow gates, future evaluator
  coordination, and generic migration compatibility remain open.

- Source checkpoint `251e45378` adds the shared OHLCV coverage preflight to the
  direct ETF constituent analysis consumer after point-in-time membership
  selection and stale filtering. The benchmark-family constituent wrapper
  inherits the same report. Focused PostgreSQL ETF/relative-rotation
  integration passed `4/4`, the complete backend unit suite passed
  `2,029/2,029`, and the authoritative Docker-backed combined backend gate
  passed `2,410/2,410` at `81.40%` coverage with 89 warnings. Testcontainer
  session `2f7f31f1-e6bb-42ab-acf8-90db917c0e9b` was cleaned without host-wide
  pruning. No ETF provider adapters, frontend files, credentials, or provider
  payloads changed. The parallel `feat/etf-holdings-constituents` branch still
  owns adapter/provider changes; reconcile this response-field contract at
  staging.

- Source checkpoint `740fa0168` extends the same shared preflight to
  Study Lab/research dataset materialization. Historical gaps and code
  lookback shortfalls are retained as explicit coverage/exclusion evidence;
  ready batch members proceed, incomplete members are withheld, and a
  single-instrument study is deferred before isolated user code executes.
  Focused PostgreSQL research integration passed `4/4`, research-runner/job
  unit coverage passed `110/110`, the complete backend unit suite passed
  `2,030/2,030`, and the authoritative Docker-backed combined gate passed
  `2,412/2,412` at `81.40%` coverage with 89 warnings. Testcontainer session
  `6c87efb7-5bb9-457c-a155-1bb8d47e5d67` was cleaned without host-wide
  pruning. No frontend files, ETF provider adapters, provider calls, or
  credentials changed. Future signal engines beyond the currently covered
  paths remain an explicit follow-up.

- The current source checkpoint `8f895f255` was re-audited after the supplied
  Alpaca, SEC EDGAR, MarketData.app, and replacement Dinari Sandbox
  credentials were present in the owner-managed environment. The revoked
  Dinari pair is absent, no credential is tracked, and the two worktree env
  paths remain symlinks to `~/.config/charting-platform/app.env`. Workstream
  validation, changed-scope Ruff, and diff checks passed; the provider,
  quota-contract, durable account-usage, and secret-wiring regression suite
  passed `548/548` with no provider calls. This is a verification checkpoint,
  not a closure of the still-open provider-terms, GitHub environment,
  credential-preflight, production reconciliation, migration, or 30-day
  shadow gates.

- Source checkpoint `1c87db5c1` extends the shared provider-neutral OHLCV
  coverage preflight to the Radar signal scan. Its exact 80-bar minimum is now
  evaluated before `analyze_instrument`; short or otherwise incomplete local
  histories are withheld from detection, bounded refresh jobs retain an
  `insufficient_history` reason, and the persisted run summary includes the
  per-instrument preflight evidence. Radar unit coverage passed `35/35`, the
  complete PostgreSQL Radar API coverage passed `13/13`, the complete backend
  unit suite passed `2,032/2,032` with 37 warnings, and the authoritative
  Docker-backed combined gate passed `2,415/2,415` at `81.40%` coverage with
  89 warnings. Testcontainer session
  `9fbd238a-6d9a-4f03-86b7-22d1b88bf4c1` was cleaned without host-wide
  pruning. No provider calls, credentials, frontend files, or ETF-provider
  adapter files changed. Provider/legal/deployment/shadow gates, future
  evaluator coordination, and generic migration compatibility remain open.

- Source checkpoint `193092488` persists the bounded Radar repair handoff in
  each run's coverage summary when opt-in repairs are requested. The evidence
  records coalescing request keys, observed queue status, attempt count,
  next-attempt timestamp, capability, timeframe, and coverage reason, while
  omitting lease tokens and provider secrets; the admin queue remains the
  authoritative source for later lifecycle transitions. Radar unit coverage
  passed `35/35`, complete PostgreSQL Radar API coverage passed `13/13`, the
  complete backend unit suite passed `2,032/2,032` with 37 warnings, and the
  authoritative Docker-backed combined gate passed `2,415/2,415` at `81.41%`
  coverage with 89 warnings. Testcontainer session
  `ebd7111d-f864-4acb-a42f-6b76d2272def` was cleaned without host-wide
  pruning. No provider calls, credentials, frontend files, or ETF-provider
  adapter files changed. Provider/legal/deployment/shadow gates, future
  evaluator coordination, and generic migration compatibility remain open.

- Source checkpoint `9e8b520d2` hardens the options integration boundary:
  expiration, current-chain, and historical quote refreshes now fallback only
  for explicit not-configured/no-data outcomes. Provider rate-limit,
  quota-contract, malformed-response, and transport errors remain typed and
  observable to callers/runtime. Options data/exposure unit coverage passed
  `37/37`, PostgreSQL options-exposure integration passed `24/24`, and the
  authoritative Docker-backed combined gate passed `2,418/2,418` at `81.43%`
  coverage with 89 warnings. Testcontainer session
  `59c97157-ce31-4ce8-aabf-255b20da1344` was cleaned without host-wide
  pruning. No provider calls, credentials, frontend files, or ETF-provider
  adapter files changed. Provider/legal/deployment/shadow gates, future
  evaluator coordination, and generic migration compatibility remain open.

- Source checkpoint `ee9bd01db` closes a tokenized-provider secret-safety gap:
  Dinari API key ID/secret and the Ondo Global Markets API key are now included
  in the central typed-provider-error redaction set. Tokenized secret/error and
  provider-wiring coverage passed `28/28`; the authoritative Docker-backed
  combined gate passed `2,421/2,421` at `81.43%` coverage with 89 warnings.
  Testcontainer session `55e597be-a4cb-44b5-a12b-df058f33df61` was cleaned
  without host-wide pruning. No provider calls, frontend files, or ETF-provider
  adapter files changed. Provider/legal/deployment/shadow gates, future
  evaluator coordination, and generic migration compatibility remain open.

- Source checkpoint `a707fe73c` hardens the Dinari Sandbox integration after
  current live validation reproduced intermittent HTTP 500s caused by repeated
  catalogue enumeration. Validated Stock records are cached only within the
  provider instance for downstream UUID reads, preserving fresh metadata across
  instances; Dinari alone retries a 500 at most twice with short linear
  backoff, while rate-limit and other provider failures remain typed/fail-fast.
  Tokenized coverage passed `72/72`, including persistent-500 retry-exhaustion
  coverage; the focused provider/registry/quota/secret slice passed `197/197`,
  and the authoritative Docker-backed combined gate
  passed `2,424/2,424` at `81.44%` using cleaned testcontainer session
  `9b8d2316-064e-48a9-bee5-e3ba27cf8b88`. The refreshed live matrix passed
  `41/47`, including the Dinari compound case; Alpha Vantage capacity responses
  and intentional Tradier/IBKR/Ondo credential preflights remain honest
  non-passes. Aggregate usage only was recorded outside Git. Provider/legal,
  CI/deployment, production reconciliation, migration, future-evaluator, and
  shadow gates remain open; the parallel `feat/etf-holdings-constituents`
  branch still owns ETF provider adapters and must reconcile only at staging.

- The current-source lock-protected provider matrix was rerun after
  `ac114ced3`: 47 cases collected and 41 passed. The three Alpha Vantage
  event/earnings reads returned typed documented capacity responses; Tradier,
  IBKR, and Ondo remained exact missing-credential preflights. Routing safety
  continued to enumerate the specific unreviewed controls for Alpaca
  corporate actions, FINRA async/OTC, FRED, Nasdaq, xStocks, Bybit,
  Marketstack discovery, MarketData.app, Tiingo, and FMP. Exit code 2 made no
  acceptance claim; aggregate usage remained outside Git and no credentials or
  payloads entered Git.

- Source checkpoint `ac114ced3` scopes Dinari's bounded HTTP 500 recovery to
  hosts ending in `.sandbox.dinari.com`; the documented production host now
  fails fast until production-specific evidence supports another policy. The
  production-host regression made exactly one request and preserved the typed
  500 response. Tokenized unit coverage passed `73/73`; the focused
  provider/registry/quota/secret slice passed `198/198`; the complete backend
  unit suite passed `2,043/2,043`; the isolated PostgreSQL integration suite
  passed `383/383`; and the authoritative combined backend gate passed
  `2,426/2,426` at `81.44%` coverage with 89 warnings using cleaned
  testcontainer session `ea357249-d45b-488e-97cf-302ccdfcb7c3`. No provider
  calls, credentials, or payloads entered Git. The live matrix remains
  `41/47`, with Alpha Vantage capacity responses and the intentional
  Tradier/IBKR/Ondo credential preflights still non-passes. Provider/legal,
  CI/deployment, production reconciliation, migration, future-evaluator, and
  shadow gates remain open; the parallel ETF branch still owns ETF provider
  adapters and must reconcile only at staging.

- Source checkpoint `ade1c9431` records the follow-up network-enabled live
  matrix using the configured Alpaca paper, MarketData.app, Dinari Sandbox,
  SEC EDGAR, and other owner-managed credentials. The matrix collected 47
  cases and passed 41. Alpha Vantage's three event/earnings reads returned
  typed documented capacity responses at the supplied free key's reviewed
  25-requests/day and one-request-per-second capacity; Tradier, IBKR, and
  Ondo remained exact intentional missing-credential preflights. The runner
  returned exit code 2 and made no acceptance claim. Routing safety still
  blocks unreviewed quota, legal, redistribution, and response-dependent
  controls; aggregate usage is external-only and no credentials or provider
  payloads entered Git. The feature branch remains ready for human review,
  not ready for integration; the parallel ETF branch still owns ETF provider
  adapters and must reconcile only at staging.

- Source checkpoint `337446aab` closes a universe-reconciliation metadata
  strictness gap: authoritative discovery `total` values must be actual
  integers, so booleans, numeric strings, fractions, and negatives fail closed
  instead of being coerced into a false completeness count. Focused universe
  coverage passed `23/23`; Ruff, compileall, and diff checks passed; and the
  authoritative Docker-backed backend gate passed `2,430/2,430` at `81.45%`
  coverage with 89 warnings using cleaned testcontainer session
  `840f0c25-0cc1-4188-aefd-6dd5c77f8467`. No provider calls, credentials,
  frontend files, or ETF-provider adapter files changed. Complete SEC/OTC
  reconciliation still needs its approved authoritative source and
  terms/polling/redistribution review; the branch remains ready for human
  review, not ready for integration.

- Source checkpoint `236b00840` closes the adjacent universe-integrity gap:
  duplicate listing keys are now rejected across provider pages before counts
  or completeness are accepted. Focused universe coverage passed `24/24`;
  Ruff, compileall, and diff checks passed; and the authoritative Docker-backed
  combined backend gate passed `2,431/2,431` at `81.45%` coverage with 89
  warnings using cleaned testcontainer session
  `e2ec12b5-2754-4fb0-8398-c756ed334c8e`. No provider calls, credentials,
  frontend files, or ETF-provider adapter files changed. Complete SEC/OTC
  reconciliation and its approved source/terms review remain open; the branch
  is still ready for human review, not ready for integration.

- Source checkpoint `d3d916d87` repairs the provider-platform migration graph.
  The duplicate provider revision was renamed to `ab1c2d3e4f5a`, the prelisting
  migration now declares both radar and consensus parents, and the
  schema-neutral `bc2d3e4f5a6b` merge migration restores one Alembic head.
  `alembic heads` reports only `bc2d3e4f5a6b`. The staging-baseline migration
  compatibility gate passed with previous-release `/health` 200 and 25 changed
  migration files; the authoritative Docker-backed backend gate passed
  `2,431/2,431` at `81.45%` coverage with 89 warnings using cleaned session
  `8ee61c02-0fec-430c-a5c8-d68c398e4733`. This is ready for coordinator review;
  it does not authorize integration or promotion.

- Source checkpoint `db3c0eda5` refreshes the current-source live evidence after
  the migration repair. The lock-protected manifest collected 47 cases and
  passed 41; Alpha Vantage's three event/earnings cases returned typed,
  documented free-key capacity responses, while Tradier, IBKR, and Ondo
  remained exact missing-credential preflights. The routing safety report still
  blocks only unreviewed provider-specific quota/legal/redistribution controls.
  Aggregate usage remained external-only; no credentials or provider payloads
  entered Git. This is current evidence, not an acceptance claim.

- Source checkpoint `2e31f99c7` extends the shared OHLCV preflight to generic
  `/analysis/breadth/history`. The route truncates bars at the historical
  `as_of` cutoff, assesses the observed local extent against the condition's
  required history floor, withholds insufficient members, and exposes additive
  `coverage_preflight` evidence. Focused PostgreSQL integration passed `3/3`;
  Ruff, compileall, and diff checks passed; and the authoritative combined
  backend gate passed `2,431/2,431` at `81.45%` coverage with 89 warnings using
  cleaned testcontainer session `838c842f-2dc2-4f52-9d11-f0a0bbe4d306`. No
  provider calls, credentials, frontend files, or ETF-provider adapter files
  changed. Provider/legal, CI/deployment, production reconciliation, shadow,
  and staging coordinator review remain open; the parallel ETF branch still
  owns ETF provider adapters and must reconcile only at staging.

- Source checkpoint `d59731fb7` extends the same shared OHLCV preflight to the
  direct indicator-computation endpoint. Required history is derived from the
  canonical indicator registry and normalized parameters; incomplete local
  history is withheld before computation and additive `coverage_preflight`
  evidence is returned on successful, deferred, and unknown-indicator paths.
  Focused `IndicatorsEndpoint` integration passed `6/6`; Ruff, compileall, and
  diff checks passed; and the authoritative Docker-backed backend gate passed
  `2,432/2,432` at `81.45%` coverage with 89 warnings using cleaned session
  `1e1f994b-6eef-4fb2-b334-8cdc7a4e6d43`. No provider calls, credentials,
  frontend files, or ETF-provider adapter files changed. Provider/legal,
  CI/deployment, production reconciliation, shadow, future-evaluator, and
  staging coordinator review remain open; this branch remains ready for human
  review and is not ready for integration.

- Source checkpoint `572f63e11` makes `/api/v1/instruments/heatmap-data`
  provider-neutral. The endpoint no longer performs one provider-backed latest
  bar fetch per instrument while evaluating a broad heatmap; daily and selected
  timeframe local bars are assessed through the shared preflight, short histories
  are deferred, and rows carry additive daily/sparkline readiness evidence.
  Focused PostgreSQL integration passed `7/7`; Ruff, compileall, and diff checks
  passed; and the authoritative Docker-backed backend gate passed `2,433/2,433`
  at `81.53%` coverage with 89 warnings using cleaned session
  `1f5a3130-296c-4d2b-9610-a7cc42f8448e`. No provider calls, credentials,
  frontend files, or ETF-provider adapter files changed. Provider/legal,
  CI/deployment, production reconciliation, shadow, future-evaluator, and
  staging coordinator review remain open; this branch remains ready for human
  review and is not ready for integration.

- Source checkpoint `7ef9e8ec8` bounds non-daily heatmap sparkline reads with a
  per-instrument SQL row-number window capped at the requested sparkline length.
  This prevents an unbounded historical scan for large universes while keeping
  the endpoint DB-first and provider-neutral. Focused heatmap integration passed
  `1/1`; Ruff, compileall, and diff checks passed; and the authoritative
  Docker-backed backend gate passed `2,433/2,433` at `81.52%` coverage with 89
  warnings using cleaned session `89d870f1-e3b2-4ea5-b254-e87e1a099a98`. No
  provider calls, credentials, frontend files, or ETF-provider adapter files
  changed. Provider/legal, CI/deployment, production reconciliation, shadow,
  future-evaluator, and staging coordinator review remain open; this branch
  remains ready for human review and is not ready for integration.

- Source checkpoint `941863c89` closes the remaining request-triggered OHLCV
  evaluator path in the instruments router. Monthly seasonality now asks the
  canonical local series for bars with provider fetching disabled, applies the
  shared OHLCV preflight against the requested sample length, and returns
  additive readiness evidence while preserving the existing monthly records.
  Focused PostgreSQL integration passed `21/21` with `--no-cov`; the same run
  passed all 21 tests with coverage collection but exits when isolated because
  the repository-wide threshold is not meaningful for a single module. Ruff,
  compileall, and diff checks passed. No provider calls, credentials,
  frontend files, or ETF-provider adapter files changed. Provider/legal,
  CI/deployment, production reconciliation, shadow, future-evaluator, and
  staging coordinator review remain open; this branch remains ready for human
  review and is not ready for integration.

- The authoritative Docker-backed combined backend unit/integration gate after
  checkpoint `941863c89` passed `2,434/2,434` with 89 warnings at `81.58%`
  coverage using cleaned labeled testcontainer session
  `adbeabea-934e-4267-b590-717cb9a78f99`. This confirms the additive seasonality
  response and provider-boundary change across the complete scoped backend
  suite; no provider calls, credentials, frontend files, or ETF-provider
  adapter files changed.

- The authoritative Docker-backed combined backend gate after the Massive
  change passed `2,460/2,460` at `81.68%` combined coverage with 89 warnings in
  `410.51s`, using isolated testcontainer session
  `6fc6e49e-17de-479b-b4f2-b395fb6cabe6`, which was cleaned without host-wide
  pruning. No frontend or ETF-provider adapter files changed.

- Source checkpoint `4f59270b9` closes a tokenized-catalog completeness gap.
  `refresh_tokenized_assets` now marks a bounded provider stream `partial`
  when its final page is full, and returns per-provider
  `pages_fetched`/`truncated`/`complete` evidence plus aggregate completeness
  flags. A short provider page is the only local completion signal. The full
  tokenized service/provider fixture slice passed `90/90`; Ruff, compileall,
  and diff checks passed. No live provider calls, credentials, frontend files,
  or ETF-provider adapter files changed. Tokenized quota, terms, eligibility,
  and routing admission remain external review gates.

- The authoritative Docker-backed combined backend unit/integration gate after
  the bounded tokenized-catalog change passed `2,436/2,436` with 89 warnings at
  `81.60%` combined coverage. Labeled testcontainer session
  `05167e7e-98d4-4817-a500-a5caec09b5f6` was cleaned without host-wide pruning.
  This validates the tokenized completeness contract across the scoped backend
  suite; no provider calls, credentials, frontend files, or ETF-provider
  adapter files changed.

- Source checkpoint `7d94ad60d` hardens tokenized catalog refresh isolation.
  A provider exception or malformed page is now retained as redacted
  provider/page evidence while qualified providers after it continue; an
  all-provider failure is reported as `failed`, while mixed success/failure or
  bounded truncation is reported as `partial`. Tokenized service/provider
  fixtures passed `92/92`; Ruff, compileall, and diff checks passed. No live
  provider calls, credentials, frontend files, or ETF-provider adapter files
  changed.

- The authoritative Docker-backed combined backend unit/integration gate after
  `7d94ad60d` passed `2,438/2,438` with 89 warnings at `81.61%` combined
  coverage. Labeled testcontainer session
  `bcf70b7a-48f3-49d4-9a78-d26499a577f7` was cleaned without host-wide pruning.

- Source checkpoint `008d2e2d3` schedules tokenized listing discovery as a
  separate bounded daily worker at 06:30 UTC. Catalog discovery is disabled by
  default until provider quota/terms are reviewed, has independent page and
  page-size settings, and clamps request bounds at the service boundary;
  quote and corporate-action schedules remain separate. Focused
  scheduler/service/provider/config coverage passed `153/153`; Ruff,
  compileall, YAML parsing, and diff checks passed. No live provider calls,
  credentials, frontend files, or ETF-provider adapter files changed.

- The authoritative Docker-backed combined backend unit/integration gate after
  `008d2e2d3` passed `2,441/2,441` with 89 warnings at `81.61%` combined
  coverage using cleaned labeled testcontainer session
  `824c0c11-8c12-4c6b-9186-ac86dcf5aeb7`. Provider/legal, CI/deployment,
  reconciliation, shadow, future-evaluator, and staging-coordinator gates
  remain open; this branch remains ready for human review and is not ready for
  integration.

- A forced current-source live matrix on `2026-09-13T12:42:40Z` collected
  `47` cases and passed `41`. Alpha Vantage's three event/earnings calls
  returned typed documented free-key capacity responses; Tradier, IBKR, and
  Ondo remained exact missing-credential preflights. The run exited `2` and
  made no acceptance claim or routing-entitlement change. Safety preflight
  still reports unresolved provider-specific controls for Alpaca corporate
  actions, FINRA async/OTC, FRED, Nasdaq, tokenized providers, MarketData.app,
  Tiingo, and FMP.

- Source checkpoint `86c6e04d4` adds bounded tokenized historical aggregate
  persistence and a separate 07:00 UTC worker, disabled by default. Only
  providers exposing `fetch_tokenized_historical_prices` are admitted; the
  current path is Dinari DAY/WEEK/MONTH, routed by provider asset ID and
  persisted through the canonical raw `24_7` OHLCV/MarketSeries path with
  provider provenance and no fabricated volume, VWAP, or adjustment. Local and
  RPi env/Compose examples carry the explicit settings. Focused tests passed
  `84/84`; compileall, Ruff, YAML parsing, and diff checks passed. The full
  Docker-backed backend gate passed `2,445/2,445` with 89 warnings at `81.60%`
  coverage using cleaned testcontainer session
  `91f879b1-f333-416b-9268-7a07f15d1c13`. No live provider call was made for
  this change. Provider quota/terms review and credentialed Dinari historical
  evidence remain required before enabling the worker.

- A targeted credentialed Dinari Sandbox live case was then run against the
  owner-managed environment and passed `1/1` in 9.63 seconds. It exercised
  metadata, price, quote, `DAY`/`WEEK`/`MONTH`/`YEAR` aggregate history, news,
  dividends, splits, and the combined corporate-action surface. Aggregate
  request/byte telemetry was written only to the external usage ledger; no
  credential or provider payload entered Git. This closes the live transport
  evidence gap for the adapter, but does not promote Dinari routing: account
  quota, commercial/US eligibility, caching, and redistribution terms remain
  open and the historical worker stays disabled.

- Source checkpoint `a4f7f8992da4` separates tokenized historical aggregates
  into the `TOKENIZED_HISTORICAL_PRICES` capability. Registry discovery,
  availability probes, provider-chain seeding, the Dinari historical refresh,
  and the PostgreSQL enum migration now use this capability instead of the
  generic tokenized-assets pool. Dinari remains the only adapter advertising
  it and remains fail-closed/worker-disabled pending reviewed quota, commercial,
  eligibility, caching, and redistribution terms. Focused coverage passed
  `172/172`; the authoritative Docker-backed gate passed `2,454/2,454` at
  `81.67%` with 89 warnings. No frontend or ETF-provider adapter files changed.

- Source checkpoint `f45802e82` refines the historical availability probe to
  pass an explicit provider `identifier` rather than a generic ticker-shaped
  `symbol`. Focused availability coverage passed `11/11`, and the final
  Docker-backed gate after this refinement passed `2,454/2,454` at `81.67%`
  with 89 warnings. No provider calls, credentials, frontend, or ETF-provider
  adapter files changed.

- A network-enabled focused live revalidation on `2026-09-13` passed `11/11`
  for the newly configured providers: Alpaca history/intraday/latest/assets and
  corporate actions; SEC EDGAR filings, Company Facts, and complete ticker/issuer
  directory pagination; MarketData.app options, account usage, and intraday
  history; and Dinari Sandbox metadata, price/quote, DAY/WEEK/MONTH/YEAR
  history, news, dividends, splits, and corporate actions. Aggregate telemetry
  was written only to the owner-managed temporary ledger
  `/private/tmp/charting-provider-live-usage-new-providers-20260913.jsonl`;
  no credentials or payloads entered Git. This is transport/schema evidence
  only and does not promote unreviewed routing entitlements.

- MarketData.app account-usage introspection now has a narrow pre-review path:
  the explicit `fetch_account_usage` operation can run with the conservative
  unreviewed seed to discover the authenticated native plan/credit window,
  while all price/history/options operations still require the reviewed plan,
  daily limit, trial expiry, and option-chain bound controls. Focused
  provider registry/runtime/account-usage/API coverage passed `77/77`; the
  authoritative Docker-backed backend gate passed `2,456/2,456` at `81.68%`
  combined coverage with 89 warnings using cleaned testcontainer session
  `01bc8c59-bd41-4ccd-b4e9-876b1fd7a4c5`. No credentials, provider payloads,
  frontend files, or ETF-provider adapter files entered the branch. The
  durable account observation still does not promote routing automatically;
  operator review of the native plan, terms, and redistribution entitlement
  remains required.

- The manual GitHub provider-live workflow now mirrors the backend provider
  configuration surface for OpenFIGI, Nasdaq identity, FINRA endpoint
  overrides, Massive's legacy key alias, Coinbase/Kraken credentials, and
  the existing IBKR/Dinari settings. The provider secret-wiring suite passed
  `19/19`; workflow and local/RPi Compose YAML parsing, compileall, and diff
  checks passed; and the authoritative Docker-backed backend gate passed
  `2,456/2,456` at `81.68%` with 89 warnings using cleaned testcontainer
  session `34e6266f-f3d0-4781-8a7e-d5457d27cb8d`. This verifies source-level
  parity only; GitHub environment secrets/variables still require operator
  verification.

- A fresh network-enabled credentialed verification on 2026-09-13 passed all
  13 selected cases using the owner-managed `~/.config/charting-platform/app.env`:
  Alpaca daily/intraday/latest/assets/corporate actions; SEC EDGAR profile,
  filings/Company Facts, and complete ticker/issuer directory paging;
  MarketData.app options/account usage/intraday history; and Dinari Sandbox
  metadata, price/quote, DAY/WEEK/MONTH/YEAR history, news, dividends, splits,
  and corporate actions. The rotated Dinari pair matched the supplied
  replacement values. Aggregate telemetry was appended only to the durable
  mode-0600 owner ledger; no credentials or provider payloads entered Git.
  This is transport/schema evidence only. MarketData.app entitlement/expiry/
  option-bound review, Dinari commercial/quota/redistribution review, and the
  other provider-specific safety controls remain fail-closed.

- A bounded MarketData.app account-usage read on 2026-09-13 returned the
  non-secret native observation `limit=10000`, `remaining=10000`, `consumed=0`,
  reset `2026-09-14T13:30:00Z`, and `OPRA data delayed 15 minutes`. The
  response did not identify the commercial/trial plan or expiry. This is
  observational evidence only; the conservative plan/expiry/option-chain
  routing gates remain unchanged.

- The authoritative Docker-backed combined backend unit/integration gate was
  rerun against the current checkout on 2026-09-13 and passed `2,456/2,456`
  at `81.68%` coverage with 89 warnings in `565.31s`. Isolated testcontainer
  session `545fa0a6-0105-4d92-94fb-86f418e11b25` was cleaned without host-wide
  pruning. No provider calls, credentials, frontend files, or ETF-provider
  adapter files entered Git.

- A second fresh network-enabled verification from the current checkout on
  2026-09-13 passed all `13/13` selected cases for the newly configured
  providers using the owner-managed environment: Alpaca daily/intraday/latest
  price, assets, and corporate actions; SEC EDGAR profile, filings/Company
  Facts, and complete ticker/issuer directory pagination; MarketData.app
  options, account usage, and intraday history; and Dinari Sandbox metadata,
  price/quote, DAY/WEEK/MONTH/YEAR history, news, dividends, splits, and
  corporate actions. Aggregate request/byte telemetry remained in the
  mode-0600 external usage ledger only; no credentials or provider payloads
  entered Git. This confirms transport/schema behavior but does not promote
  MarketData.app plan/expiry/option-bound or Dinari quota/commercial/
  redistribution entitlements.

- Provider request logs now persist nullable `settled_usage_units` separately
  from the reviewed pre-call `usage_units` reservation. Runtime settlement
  derives a primary amount only from an explicitly matching provider quota
  dimension; ambiguous or unavailable dimensions remain unknown rather than
  falling back to one request. Provider-admin usage summaries expose reserved
  and settled totals plus observation counts for retained, 24-hour, 7-day,
  operation, capability, hourly, and daily views. Focused runtime/usage
  coverage passed `58/58`; migration compatibility passed from previous head
  `cd3e4f5a6b7c`; and the authoritative Docker-backed gate passed
  `2,456/2,456` at `81.69%` with 89 warnings using isolated session
  `df1ea6d8-502c-4ad9-9201-720b971d9f5d`. No frontend or ETF-provider adapter
  files changed.

- Tokenized provider records now retain the economic underlying's SEC CIK as a
  first-class `underlying_cik` and optionally link `underlying_issuer_id` only
  to an already materialized unique Issuer; token instruments remain separate
  and issuer materialization remains fail-closed. Dinari fixture/service
  coverage passed `98/98`; migration compatibility passed from previous head
  `cd3e4f5a6b7c`; and the authoritative Docker-backed gate passed
  `2,457/2,457` at `81.69%` with 89 warnings using isolated session
  `cca368fd-46e3-4651-a631-2affa3739be0`. No frontend or ETF-provider adapter
  files changed.

- The current tokenized-issuer-identity checkpoint was revalidated with network
  access and the owner-managed credentials: the bounded selected provider suite
  passed `13/13` for SEC EDGAR, Alpaca, MarketData.app, and Dinari Sandbox. The
  redacted receipt contained 8 provider rows, 33 upstream requests, and
  13,092,191 response bytes in `/private/tmp` only; no credentials or provider
  payloads entered Git. This is transport/schema evidence only and does not
  promote quota, commercial, redistribution, or routing entitlement.

- Tokenized admin diagnostics now expose the persisted economic `underlying_cik`
  and optional `underlying_issuer_id` without conflating the token instrument
  with its underlying issuer. The targeted Docker-backed admin integration test
  passed `1/1`; Ruff and diff checks passed; and the authoritative Docker-backed
  combined backend gate passed `2,457/2,457` at `81.69%` with 89 warnings in
  `521.82s` using isolated testcontainer session
  `b74ce11b-1f89-4bf6-ad4e-76ac0e520cb8`. No frontend or ETF-provider adapter
  files changed.

- The complete available-provider live matrix was rerun against the current
  checkout with the owner-managed environment: `44` executable cases passed
  `41/44`; the intentionally deferred Tradier, IBKR, and Ondo cases were
  excluded. All configured providers and public tokenized probes passed except
  three Alpha Vantage event/earnings operations that returned its typed
  documented free-key capacity response after the shared daily allowance was
  exhausted. The redacted temporary receipt contained 26 provider rows, 94
  upstream requests, and 23,311,979 response bytes outside Git; this is quota
  evidence and no acceptance claim for those three operations.

- The redacted available-provider live receipt was merged with the repository's
  allow-listed, deduplicating merger into the mode-0600 owner-managed
  provider-live-usage ledger: `accepted=26`, `duplicates=0`, `rejected=0`.
  This preserves cross-session aggregate usage evidence without copying
  credentials or provider payloads.

- Massive historical bars are now implemented for M1/M5/M15/M30/H1/H2/H4/H12/
  D1/W1/MN, with raw or split-adjusted semantics, safe provider cursor
  pagination, strict OHLC/volume/timestamp validation, and a caller-supplied
  50,000-base-aggregate page reservation. Focused provider coverage passed
  `223/223`; Ruff and diff checks passed. The credentialed Massive reference,
  IPO, holiday, and adjusted-history live case passed with four upstream
  requests; its redacted usage receipt was merged with `accepted=1` into the
  owner-managed mode-0600 ledger. The free Stocks Basic five-call/minute and
  two-year history contract is documented, but Massive history remains opt-in
  pending operator plan/redistribution review. No frontend or ETF-provider
  adapter files changed.

- The Massive live case was expanded to exercise both split-adjusted D1 and raw
  M5 intraday aggregate bars. It passed with five upstream requests and
  447,607 response bytes; the redacted receipt merger accepted one provider
  row into the owner-managed ledger. This remains bounded transport/schema
  evidence only and does not promote Massive's free-plan history or
  redistribution entitlement.

- The rotated Dinari Sandbox credentials were revalidated on 2026-09-13 with
  a focused identity assertion. The compound case passed `1/1` (12 operations,
  14 upstream requests): the provider-native Stock UUID parsed as a UUID and
  the first catalogue record exposed at least one stable economic-underlying
  identifier (the live AAPL row exposed composite FIGI and CIK). The redacted
  receipt merger accepted one row into the owner-managed ledger
  (`accepted=1`, `duplicates=0`, `rejected=0`). This strengthens token-to-issuer
  reconciliation evidence only; Dinari commercial, quota, historical-
  aggregate, and redistribution reviews remain required before routing
  admission.

- Massive now exposes the official single-ticker overview as explicit
  `instrument_metadata`: it validates the requested ticker, preserves CIK,
  composite FIGI and share-class FIGI identifiers, normalizes exchange,
  currency, type, active/delisted lifecycle timestamps, and retains provider
  classification/description/branding fields. The metadata operation has an
  explicit one-request usage profile and is supplementary to SEC issuer
  profiles. Focused provider/quota coverage passed `314/314`, Ruff/diff checks
  passed, and the credentialed Massive case passed `1/1` with six upstream
  requests and 448,964 response bytes; the redacted receipt merger accepted
  one row. This is transport/schema evidence only; history and redistribution
terms remain opt-in pending review. No frontend or ETF-provider adapter files
changed.

- The authoritative Docker-backed combined backend gate after the Massive
  metadata implementation passed `2,464/2,464` at `81.68%` coverage with 89
  warnings in `507.76s`, using isolated testcontainer session
  `e92d7385-12e1-4379-a92f-167ce5abe08c`; cleanup removed only that
  workstream's containers. No frontend or ETF-provider adapter files changed.

- Massive now exposes official split and dividend corporate-action reads as
  `instrument_events`/`corporate_actions`, with strict requested-ticker/date/
  ratio/value validation, separate ex-dividend/payable events, trusted cursor
  continuation, and a positive `MASSIVE_CORPORATE_ACTIONS_MAX_PAGES` bound per
  endpoint. The runtime reserves `2 * bound` requests; unset/invalid controls
  remain fail-closed. Focused coverage passed `365/365`; the bounded live case
  passed `1/1` with five upstream requests and 463,329 response bytes, and its
  redacted receipt merged into the owner-managed ledger (`accepted=1`).

- The authoritative Docker-backed combined backend gate after Massive
  corporate-action support passed `2,471/2,471` at `81.67%` coverage with 89
  warnings in `484.43s`, using isolated testcontainer session
  `89491c39-ed3b-4f32-b66f-df9b89a3607a`. Compose, compile, workstream,
  Ruff, and diff checks passed. No frontend or ETF-provider adapter files
  changed.

- The Massive corporate-action tests also cover valid cursor continuation and
  fail-closed rejection of an untrusted host, unexpected endpoint path,
  malformed cursor, or exhausted page bound. The focused provider/registry/
  service/quota/wiring suite passed `369/369` with Ruff and diff checks clean.

- The exact final pushed branch checkpoint `8b8c39131` passed the authoritative
  Docker-backed combined backend gate at `2,475/2,475` with `81.70%` combined
  coverage and 89 warnings in `502.89s`, using isolated testcontainer session
  `88a36955-4150-480c-a75b-5376c5df15d6`; cleanup removed only this
  workstream's containers and did not perform a host-wide prune. No frontend or
  ETF-provider adapter files changed.

- A fresh bounded credentialed live suite passed `11/11` against the current
  pushed checkpoint `49e8095a6`: Alpaca history/intraday/latest/assets and
  corporate actions; SEC EDGAR filings/facts and complete ticker/issuer
  directory pagination; MarketData.app options/account usage/intraday history;
  and Dinari Sandbox metadata, price/quote, DAY/WEEK/MONTH/YEAR history, news,
  dividends, splits, and corporate actions. The redacted receipt recorded four
  provider rows, 30 upstream requests, and 12,926,846 response bytes; its
  aggregate usage merged into the owner-managed ledger (`accepted=4`). This is
  transport/schema evidence only and does not promote unreviewed routing
  controls or entitlements.

- The full current-source lock-protected provider/tokenized matrix at checkpoint
  `aedf1943f` collected `47` cases and passed `41/47`. The six explicit
  non-passes were Alpha Vantage IPO-calendar, earnings-calendar, and
  earnings-history capacity responses at the supplied free key's documented
  allowance, plus missing credential preflights for intentionally deferred
  Tradier, IBKR, and Ondo. Its 26-provider redacted receipt recorded 96
  upstream requests and 23,334,032 response bytes, then merged into the
  owner-managed ledger (`accepted=26`). This remains non-acceptance evidence;
  no routing entitlement was promoted.

- History-depth admission is now provider-specific and machine-readable.
  Massive (two calendar years), Marketstack (one calendar year), EODHD
  (one calendar year), and MarketData.app Free/Trial plans (one calendar year)
  publish structured
  `quota_policy.history_constraints` bounds. Normal bounded OHLCV fetches pass
  their requested start date through provider admission; missing, malformed,
  future, or exceeded bounds fail closed. Epoch-style bulk hydration remains
  adaptive so it can persist the maximum validated range a provider exposes.
  Focused routing/runtime coverage passed `76/76`, Ruff, compileall, and diff
  checks passed, and the authoritative Docker-backed gate passed `2,482/2,482`
  at `81.71%` combined coverage with 89 warnings in isolated session
  `b440cc4a-6923-477b-9255-9af31292fc9f`. No frontend or ETF-provider adapter
  files changed.

- MarketData.app's official Free Forever and trial documentation now has a
  structured one-calendar-year history bound in the entitlement seed. The
  explicit reviewed-plan/expiry gate remains unchanged, so this adds
  provider-specific date admission without promoting the currently unreviewed
  account. Focused routing/runtime coverage remained `76/76`, and the
  authoritative Docker-backed gate passed `2,482/2,482` at `81.71%` combined
  coverage with 89 warnings in isolated session
  `2308b1d1-4024-46b1-8f03-a4469ceab0b2`. No frontend or ETF-provider adapter
  files changed.

- The risk-free-rate historical fallback now passes its 30-day request start
  through the same provider-specific structured history admission as normal
  bounded OHLCV reads. The focused risk-free/runtime/routing suite passed
  `77/77`; Ruff, compileall, and diff checks passed. The authoritative
  Docker-backed backend gate passed `2,482/2,482` at `81.71%` combined
  coverage with 89 warnings in `462.80s`, using isolated testcontainer session
  `bc60fed6-f853-40ef-a8a5-8d1bf8649263`; cleanup removed only this workstream's
  resources and did not perform a host-wide prune. No frontend or ETF-provider
  adapter files changed.

- A fresh bounded credentialed live suite passed `11/11` against current source
  checkpoint `750f02d57` for Alpaca history/intraday/latest/assets/corporate
  actions, SEC EDGAR filings/facts and complete ticker/issuer directory
  pagination, MarketData.app options/account usage/intraday history, and
  Dinari Sandbox metadata/price/quote/DAY-WEEK-MONTH-YEAR history/news/
  dividends/splits/corporate actions. The redacted receipt recorded 5 Alpaca
  requests/6,487,828 bytes, 6 EDGAR requests/6,236,111 bytes, 5 MarketData.app
  requests/20,561 bytes, and 14 Dinari requests/182,346 bytes, all successful;
  its aggregate usage merged into the mode-0600 owner-managed ledger with
  `accepted=4`. This remains transport/schema evidence only and does not
  promote unreviewed routing entitlements. No frontend or ETF-provider adapter
  files changed.

- The exact current pushed HEAD `78715e5b9de2` passed the authoritative
  Docker-backed combined backend gate on 2026-09-14: `2,488` tests passed at
  `81.71%` combined coverage with 89 warnings in `501.69s`. Isolated
  testcontainer session `3cf7d5d5-45dc-4e81-a2c6-9f9d6245dfe2` was cleaned
  without a host-wide prune. No frontend or ETF-provider adapter files
  changed. The branch remains `ready_for_human_review`; provider/legal,
  trusted-secret-store, deferred-credential, NMS/OTC reconciliation, and
  separately approved shadow-run gates remain intentionally open.

- Deployment documentation was corrected to match the implemented Dinari and
  Ondo tokenized historical adapters and all four supported windows (`DAY`,
  `WEEK`, `MONTH`, and `YEAR`). `git diff --check` and `make branch-validate`
  passed (`30` workstream records); no provider calls or credentials were
  used.

- README provider-chain documentation was corrected to include the dedicated
  `tokenized_historical_prices` seed for Dinari and Ondo, matching both
  environment examples. `git diff --check` and `make branch-validate` passed;
  no provider calls or credentials were used.

- The durable plan now distinguishes the current branch checkpoint `d326fb062`
  from the backend-source checkpoint `78715e5b9de2` used by the latest full
  gate. `git diff --check` and `make branch-validate` passed; no provider calls
  or credentials were used.

- A configuration-parity guard now asserts README, root environment, and
  backend environment provider-chain examples match, including the dedicated
  Dinari/Ondo `tokenized_historical_prices` seed. Focused coverage passed
  `20/20`; the authoritative Docker-backed backend gate passed `2,489/2,489`
  at `81.72%` combined coverage with 89 warnings in `494.95s`, using isolated
  session `c96a4b01-3fbc-495b-a704-954c6207c66b`. No frontend or ETF-provider
  adapter files changed.

- Reviewed provider policy seeds are now wired through both standard and RPi
  Compose backend/worker services: `PROVIDER_RATE_LIMIT_SEEDS`,
  `PROVIDER_FRESHNESS_SEEDS`, and `PROVIDER_USAGE_PROFILE_SEEDS` match the
  backend environment example, so deployment overrides for provider-specific
  limits and usage accounting are not silently dropped. Focused coverage passed
  `20/20`; the authoritative Docker-backed backend gate passed `2,489/2,489`
  at `81.72%` combined coverage with 89 warnings in `557.73s`, using isolated
  session `16d8b47d-f8c9-4d3f-a767-71a1f30f0753`. No frontend or ETF-provider
  adapter files changed.

- Compose policy-seed fallbacks now preserve the in-code reviewed maps when the
  external deployment environment omits an override: the explicit
  `__CODE_DEFAULT__` sentinel invokes the Settings field default, while an
  explicit `{}` remains a deliberate empty/quarantine override. The behavior
  is covered for rate-limit, freshness, and usage-profile maps in both
  environment examples and standard/RPi Compose wiring. Focused coverage passed
  `110/110`; the authoritative Docker-backed backend gate passed `2,491/2,491`
  at `81.72%` combined coverage with 89 warnings in `495.11s`, using isolated
  session `fbcfc12b-98b5-438d-80b2-3034b0ac3ec1`. No frontend or ETF-provider
  adapter files changed.

- README provider configuration guidance now documents the explicit
  `__CODE_DEFAULT__` sentinel for omitted policy maps and the separate meaning
  of an explicit `{}` empty override, matching the root and backend environment
  examples. Provider secret-wiring coverage passed `21/21`; Ruff, diff checks,
  and workstream validation passed. No provider call or credential was used.

- The staging-to-feature migration compatibility gate was rerun against
  `staging` after the earlier Docker API failure and passed for 28 changed
  migration files. The previous-release schema reached `fe4f5a6b7c8d`, the
  checked-out schema reached branch HEAD
  `8890d5d880742fb01ee40f175151116c61622bb7`, and the previous application
  smoke-tested `/health` with HTTP 200. The temporary PostgreSQL container and
  detached worktree were cleaned by the gate; no provider calls or credentials
  were used.

- A current registry/live-manifest audit found 32 registered providers: 29 have
  explicit bounded live-manifest entries, while the three remaining entries
  have explicit exclusion rationales for legacy yfinance, internal ETF holdings
  ingestion, and descriptor-only Alpaca ITN. The quota-contract and provider
  secret-wiring suites passed `110/110`; no provider calls or credentials were
  used.

- Focused coverage for the newly credentialed Alpaca/MarketData.app/Dinari
  adapters, optional-provider transports, tokenized-asset persistence,
  provider-native account-usage observations, and live-manifest secret wiring
  passed `448/448` in `2.58s` on source checkpoint `91b0386ed`. This was a
  local fixture/unit run only; it made no provider calls and did not consume
  any configured external quota. The latest credentialed live evidence remains
  the bounded matrix recorded above, with provider-specific routing/legal and
  deployment-secret gates still intentionally open.

- A lock-protected credentialed live subset for the newly supplied providers
  passed `9/9` selected cases (`38` unrelated cases deselected) in `25.63s` on
  2026-09-14. The owner-managed external ledger recorded aggregate-only usage:
  Alpaca `5` requests/operations and `6,487,899` bytes with observed
  `200`/`199` rate-limit headers; MarketData.app `6` requests/operations and
  `17,101` bytes with observed `10,000` credit headers and zero consumed
  credits; Dinari `14` requests/`12` operations and `109,022` bytes with no
  provider capacity headers. This confirms bounded transport/schema behavior
  only; it does not promote routing, infer Dinari limits, or close the wider
  provider/legal/deployment/shadow gates.

- Tokenized aggregate persistence now supports the documented `YEAR` window
  through a real canonical `Timeframe.Y1` value. Calendar-year bucketing, the
  PostgreSQL `timeframe` enum migration, tokenized history mapping, market-data
  freshness fallback, and Radar timeframe ranking are covered without making
  ordinary providers claim annual-native support. Focused coverage passed
  `33/33`; staging-to-feature migration compatibility passed `29` changed
  migrations; and the authoritative backend gate passed `2,495/2,495` at
  `81.72%` coverage with 89 warnings in `587.32s`, using isolated testcontainer
  session `b11f41de-f9c0-48ce-a25e-13e9f06d097c`, cleaned without host-wide
  pruning. No frontend or ETF-provider adapter files changed.

- The committed annual-timeframe checkpoint `6a47f6ed7` independently reran
  staging-to-feature migration compatibility successfully: `29` changed
  migration files, previous-release schema `fe4f5a6b7c8d`, and previous
  application `/health` HTTP 200. Temporary PostgreSQL resources were cleaned.

- Annual timeframe boundary handling is now fail-closed outside the tokenized
  history bridge: Nautilus backtests reject unverified `Y1` bar specifications,
  yfinance rejects `Y1` instead of silently using a daily interval, and
  indicator-alert lookbacks use a calendar-year duration. Focused
  provider/backtest/alert coverage passed `260/260`; Ruff and diff checks
  passed. No provider calls, credentials, frontend, or ETF-provider adapter
  files changed.

- The local owner-only MarketData.app config was verified without reading or
  printing credentials: `starter_trial`, 10,000 credits/day, expiring
  `2026-10-11T18:09:00+01:00` (30 days from the supplied Sep 11 18:09 Lisbon
  email time). The provider-specific settings automatically fall back to the
  configurable Free Forever 100/day contract after expiry; paid plan changes
  require an explicit new plan/limit configuration.

- Full-stack browser validation now runs with both `PROVIDER_ROUTING_ENABLED`
  disabled and a test-only deny-all HTTP(S) proxy on backend/worker. The first
  isolated run exposed a missing `E2E_SEED_MARKET_DATA=true` startup setting;
  after enabling the existing deterministic fixture, the complete Playwright
  suite passed `151/260`, skipped `109` suite-declared cases, and had zero
  failures. The egress proxy log was empty. The branch-scoped browser stack and
  its disposable database/cache volumes were removed after the run.

- Earlier browser validation had unexpectedly reached external services
  before egress isolation was added: telemetry showed 78 SEC and 78 OpenFIGI
  requests and one MarketData.app expiration lookup, for which the ledger
  settled one MarketData.app credit. This incident was disclosed; subsequent
  browser validation ran behind the deny proxy and produced no outbound
  attempts.

- The authoritative Docker-backed backend unit/integration coverage gate
  exited successfully on the current worktree state: `2,550/2,550` collected
  tests passed, combined line coverage `81.79%` (`50,071/61,217` lines). These
  browser/backend receipts describe the uncommitted source state identified
  by HEAD `73d1d1aa6ee41bd82e1f5b1bff57f422d2b610c3`; they are not yet the final
  clean-source provider-live evidence.

- The owner-managed provider-live ledger shows that the latest Sep 15 full
  matrix spent 96 HTTP requests and about 23 MB across the selected roster,
  including approximately 2.97 MB from FINRA. Its receipt recorded `43/46`
  and `not_current_source`; it is preserved as usage history, not acceptance
  evidence for the current uncommitted source. Avoid another broad matrix until
  the exact source is committed and the bounded run plan reconciles provider
  usage first.

- E2E egress isolation is now enforced by keeping application/data services on
  an internal-only Compose network. A separate host-port relay on a second
  network exposes only fixed destinations (`frontend:80`, `backend:8000`) and
  has no provider credentials. The initial internal-network-only setup blocked
  host-published ports, so it was replaced by this fixed relay design. On the
  active stack, a raw backend socket to public HTTPS returned blocked while
  both local host-relayed `/health` probes returned HTTP 200; the focused
  `F8n-crosshair` test passed `1/1`, then the full Playwright suite passed
  `151/260` with zero failures and 109 suite-declared skips. The deny-proxy log
  remained empty. `make test-compose-contract` also passed for the two-network
  design. The branch-scoped browser stack was subsequently stopped and its
  test-only containers, images, volumes, and network were cleaned without
  host-wide pruning.
  These receipts describe the uncommitted source at HEAD
  `73d1d1aa6ee41bd82e1f5b1bff57f422d2b610c3`, not a clean committed source.

- Official-source audit found a critical mismatch in the approved OTC snapshot
  assumption: current FINRA documentation catalogs `otcDailyList` and other
  OTC-market datasets but contains no `otcSecurityMaster` entry, while FINRA's
  current Equity terms cover otcMarket datasets and allow non-commercial
  personal/professional use with attribution/no-charge/no-further-redistribution
  conditions. OTC Markets says it does not provide market-data APIs; its U.S.
  Security Master file specification exists, but no low-cost/free API or
  redistribution-ready route has been confirmed. The local source URL is set to
  `api.finra.org/data/group/otcMarket/name/otcSecurityMaster`, which is not
  enough to establish current documentation/authorization. Do not mark complete
  OTC coverage or enable FINRA-directory routing until the provider confirms
  the endpoint/data rights or an alternative source is authorized and priced.
  Evidence links: [FINRA dataset catalog](https://developer.finra.org/docs),
  [FINRA Equity Data terms](https://developer.finra.org/specific-terms-equity-data),
  [FINRA public credential scope](https://developer.finra.org/fees/public),
  [OTC Markets API FAQ](https://www.otcmarkets.com/learn/faqs),
  [OTC Markets U.S. Security Master specification](https://www.otcmarkets.com/files/US-Security-Master-File-Specification%20-%20v1.0.pdf),
  and [Nasdaq Data Link OTC Markets product](https://data.nasdaq.com/databases/OTCM).

- Implementation follow-up: routing now has two additional explicit FINRA OTC
  admission controls, `FINRA_OTC_SOURCE_REVIEWED` and the non-secret
  `FINRA_OTC_SOURCE_EVIDENCE` reference. Even if the legacy terms,
  completeness, redistribution, cost, and polling fields are all affirmative,
  the candidate remains non-routable until both source controls are valid.
  Compose (local and RPi), the credentialed GitHub workflow, diagnostics,
  examples, and tests carry the new fields. The live probe skips before making
  a request unless this source evidence is present; that skip remains an open
  acceptance gate, not passing live evidence. The parser's prior live result is
  explicitly demoted to historical transport evidence in operator docs. No
  current live FINRA OTC request was made during this change.

- User decision still needed: either keep FINRA OTC non-routable while the
  agent assesses documented alternatives under the approved spend cap, obtain
  written FINRA confirmation for this exact source, or explicitly accept an
  incomplete OTC scope. No option is inferred from the previous selection of
  FINRA as the desired authority because current source documentation does not
  establish the candidate dataset.

- Validation after the source gate: focused provider/runtime/secret-wiring/
  live-runner tests passed `96/96`; Ruff check passed for the changed Python
  paths. The exact FINRA live case was run with its source-review flag false,
  and skipped before any network request (not a live pass). The authoritative
  Docker-backed backend gate passed `2,551/2,551`, `81.79%` line coverage
  (`50,077/61,223` lines); testcontainers were absent afterward. Compose
  standard/E2E/RPi contracts passed, all `45` workflow tests passed, and the
  repository validator accepted all `30` workstream records. Receipts are
  appended at 2026-09-15 in `validation.jsonl`. All are from the uncommitted
  worktree at HEAD `73d1d1aa6ee41bd82e1f5b1bff57f422d2b610c3`; app/test code was
  unchanged during the authoritative backend run, though later workstream
  bookkeeping remains uncommitted.

## 2026-09-16 corrective implementation checkpoint

- Added provider-specific legal-use gates at both routing and direct adapter
  boundaries: Coinbase requires current scoped written authority for internal
  automated persistent non-redistributed use; FRED requires reviewed storage and
  automated-use evidence plus rights evidence for every mapped series. Both
  default fail closed and are wired through examples, Compose/RPi, GitHub live
  workflow, live preflight, and fixture/live tests. No external calls were made
  for Coinbase or FRED during this checkpoint.
- Added durable row-level SEC issuer-directory candidate reports with CIK/name/
  ticker evidence, admission decision/reason, source fingerprint, cycle status,
  and matched issuer. Dry scans remain default and do not create issuers,
  instruments, or listings; `create_missing` still requires the exact clean
  reviewed dry cycle. Reports retain three cycles and are available only to
  admins through `GET /api/v1/market-data/sec-directory-candidates` with
  pagination. Migration `a9b0c1d2e3f4` is the current Alembic head.
- Corrected provider-contract evidence: Nasdaq is bounded by a deployment-local
  two-official-file/calendar-day cap (not a vendor quota), Marketstack uses a
  rolling 30-day 100-request window, FINRA synchronous byte reservations use
  the conservative decimal 3,000,000-byte ceiling, and EODHD's conflicting
  official minute-limit statements are recorded with the stricter 20/minute
  Free Starter enforcement pending provider clarification.
- Focused validation: 412 backend unit tests passed after updating the
  MarketData.app trial-aware quota expectations; SEC scan/admin tests passed;
  provider policy/registry/quota/secret-wiring suites passed; Ruff and
  `git diff --check` passed; workstream validator passed all 30 records.
  `make branch-validate` could not run because the environment's `uv` cache is
  inaccessible, so the repository validator was run directly with the checked-
  in backend virtualenv. No commit, integration, deployment, or new live
  provider request was performed.
- Remaining acceptance gates are unchanged: current full staged live matrix,
  provider-specific legal/entitlement confirmations, complete NMS/OTC source
  reconciliation, SEC policy review/materialization, shared GitHub/RPi/
  deployment secret and quota stores, and the separately authorized final
  shadow phase. The branch remains in progress and is not ready for integration.

## 2026-09-16 live-matrix safety correction

- The manifest now treats the Nasdaq directory as one shared two-request cold
  snapshot; the duplicate cold-read case is no longer selected in the full
  matrix, preventing the deployment-local two-requests/day cap from being
  consumed twice. The full pagination case remains the acceptance case.
- Finnhub's profile, instrument-event, and market-event calls are all required
  operations. A regression test locks that manifest contract.
- Direct `pytest -m live` execution now fails closed unless launched by
  `scripts/run-live-provider-probes.py`; the runner supplies the marker after
  applying credential, legal/routing, approved-deferral, and durable-ledger
  gates. This prevents deferred providers or unmetered legacy tests from
  reaching transport. The redundant unmetered standalone OpenFIGI live test
  was removed; the manifest-backed case remains the sole acceptance path.
- xStocks legal/jurisdiction uncertainty is now a blocking live preflight, and
  Kraken/xStocks shared-IP pacing leaves a documented one-second bucket between
  the generic Kraken and tokenized Kraken cases.
- `LIVE_OPERATION_DISPOSITIONS` records capability operations that are not yet
  live-required (including FINRA async downloads, discovery/search/calendar
  endpoints, full crypto variants, and tokenized direct metadata). These are
  explicit acceptance gaps or policy blocks, not implied coverage.
- Validation after these corrections: 440 focused backend unit tests passed;
  live-runner/secret-wiring tests passed 47/47; Ruff, compilation, diff check,
  and the workstream validator (`30` records) passed. No new provider API
  request, commit, integration, or deployment was performed. The branch
  remains in progress and is not ready for integration.
- The live evidence evaluator now machine-blocks a matrix receipt when any
  selected provider has an unresolved entry in `LIVE_OPERATION_DISPOSITIONS`;
  a passing bounded case therefore cannot be mistaken for capability-complete
  acceptance. Regression coverage passed 25/25 for the live runner after this
  change.
- A current local full-matrix preflight was run with the owner-managed
  environment and stopped before transport (exit `2`): the durable shared
  quota ledger path was unavailable in this sandbox, selected capability
  dispositions remain unresolved, and Coinbase, Dinari, FINRA OTC, FRED,
  xStocks, Tiingo/FMP byte maps, and other reviewed safety controls remain
  non-routable. Nasdaq and MarketData.app controls were recognized as
  routable. The receipt is preflight evidence only; no provider request was
  made.
- Quota-preflight diagnostics now preserve the coordinator's safe typed reason
  (for example, an inaccessible or non-private ledger directory) instead of
  collapsing every local-store failure into one generic message; the diagnostic
  regression test is included in the live-runner suite.
- Full-matrix preflight now stops before acquiring the live-run lock or making
  requests when selected providers still have unresolved capability
  dispositions. Focused provider runs may still collect bounded transport
  evidence, but their receipt remains explicitly incomplete until every
  selected capability is closed.

## 2026-09-16 xStocks runtime admission correction

- xStocks now has the same fail-closed legal/data-use boundary in normal
  application routing that the live preflight already enforced. A public API
  key or a successful public read is not treated as permission for continuous
  automated persistence, partner integration, or deployment from an ineligible
  jurisdiction.
- Added explicit non-secret controls for automation authority, authority
  reference/scope, review timestamp, optional expiry, jurisdiction admission,
  and jurisdiction evidence. They are wired through Settings, the provider
  registry, the direct xStocks adapter boundary, local/backend examples,
  standard/RPi Compose, and the GitHub live workflow. Missing or stale values
  fail closed before `httpx` transport.
- Added regression coverage for the direct no-network guard, routing-control
  diagnostics, preflight routability, and deployment/workflow/example parity.
  The xStocks provider fixture suite and quota-coordinator suite pass; Ruff
  passes. The first combined run exposed one existing process-contention flake
  in the atomic quota test; rerunning the same focused suite passed `161/161`.
- No xStocks or other provider request was made. The full branch remains
  non-routable/not ready for integration until current terms, jurisdiction,
  durable quota-store access, and capability-complete live evidence are
  separately admitted.

## 2026-09-16 quota/live hardening follow-up

- The current-source MarketData.app focused runner invocation completed all five
  bounded cases: account usage, daily and five-minute candles, option
  expirations/chain, and the no-request historical-option safety case. It
  measured five upstream requests and 15,336 response bytes; the receipt is
  transport/usage evidence only because the worktree is intentionally dirty.
- Fixed the live reservation planner's release-only concurrency path so a
  concurrency lease never requires a nonexistent usage baseline. The planner
  now also reserves two credits for the date-granular five-day MarketData.app
  candle cases, covering the inclusive six-calendar-day boundary and preventing
  runner preflight from under-accounting the test estimator.
- Removed the local Compose research-runner's accidental mount of the durable
  provider-quota ledger. Added a wiring regression proving that user-supplied
  research code receives neither the ledger volume nor quota environment
  variables. RPi already had no such mount.
- GitHub's protected provider-live workflow now passes the reviewed
  `PROVIDER_FRESHNESS_SEEDS` override alongside rate-limit and usage-profile
  overrides; deployment docs list the same configuration dimension.
- Validation after this follow-up: full backend unit suite `2,256 passed` with
  37 warnings; workflow tests `46 passed`; Ruff, Python compilation, diff
  check, and workstream validation all passed. No frontend or ETF-provider
  files changed, and no credentials were written to the repository.
- Secret-store audit remains open: GitHub environment inventory/reviewers and
  persistent PostgreSQL coordinator connectivity are not inspectable from this
  session; only MarketData.app has a reconciled provider-native baseline. Other
  finite provider dimensions must remain non-routable until individually
  reconciled, and local/GitHub/RPi stores must not share keys without a
  deliberate account-scope/coordinator decision.

## 2026-09-16 deployment preflight hardening

- RPi preflight now checks for the core deployment setting names
  `SECRET_KEY`, `POSTGRES_PASSWORD`, and `CORS_ORIGINS` without printing their
  values, validates any configured quota-coordinator URL as PostgreSQL, and
  retains the owner-only `shared/app.env` mode check.
- After the new release starts, the deployment transaction opens the durable
  provider-quota coordinator from both backend and worker. A failure to create,
  read, write, or lock the shared ledger aborts the transaction and triggers
  the existing rollback path; no deployment is reported healthy on an
  unverified quota store.
- RPi Compose now passes `PROVIDER_ROUTING_ENABLED` explicitly to backend and
  worker (default `true`, overrideable in the target-owned env). Documentation
  records the new preflight/post-start checks.
- Validation after this change: full backend unit suite `2,257 passed` with 37
  warnings; workflow tests `46 passed`; Ruff, compilation, diff check, and
  workstream validation passed. No provider calls, credentials, frontend, or
  ETF-provider adapter files were touched.

## 2026-09-16 MarketData.app quote-path correction

- A credentialed MarketData.app rerun was intentionally allowed through the
  durable local coordinator. Six of seven bounded cases passed; the latest
  price case returned `None` because the adapter incorrectly derived a current
  price from a one-day candle window, which is empty on a non-session date for
  a delayed/history-only entitlement.
- Replaced that path with the documented delayed stock-quotes endpoint. The
  response parser validates every parallel array, selects the requested symbol,
  and applies the provider's last/mid/bid/ask fallback without fabricating a
  value. Added fixture coverage for the endpoint, midpoint fallback, and
  mismatched arrays.
- The corrected credentialed rerun passed `7/7` selected cases. The receipt is
  current transport/schema evidence only because this worktree remains dirty;
  no credentials or response payloads entered Git. The MarketData.app trial
  plan remains configured outside Git as `starter_trial`/10,000 daily credits
  through `2026-10-11T18:09:00+01:00`, then Free Forever/100.
- Added explicit Alpaca live-test reservation overrides for the bounded
  five-day history (two pages) and two-page corporate-action cases so the
  runner no longer treats those test bounds as unreviewed operation costs.
  Alpaca live execution still correctly stops when its durable account/IP
  baseline is unknown and when the separate corporate-action routing bound is
  absent.
- SEC EDGAR focused execution was also attempted; it stopped before transport
  because the local durable ledger has no current SEC IP-window baseline. No
  SEC request was made by that attempt. This is an operational admission gap,
  not a test pass.

## 2026-09-16 final implementation-gate rerun

- The authoritative Docker-backed backend gate completed successfully after
  all parallel edits settled: `2,652 passed`, `81.90%` combined coverage, and
  89 warnings. The isolated test-container session was cleaned without a
  host-wide prune.
- The backend unit suite is `2,266 passed` with 37 warnings; workflow tests are
  `46 passed`; Ruff, Python compilation, Compose/deployment contracts,
  workstream validation, and `git diff --check` all pass.
- The live runner now has a canonical disposition taxonomy and structural
  manifest validation. Human deferrals, explicit no-request policy cases, and
  documented entitlement denials remain visible in receipts without being
  misreported as successful data reads; unresolved `deferred`/`blocked`
  operations still fail closed. Massive corporate-action pagination is
  explicitly deferred to a separate quota window rather than spending beyond
  the documented Basic five-call/minute allowance. Twelve Data discovery now
  uses bounded, validated pagination.
- Research-runner isolation is verified: it receives neither the durable quota
  ledger volume nor quota environment variables; only trusted backend/worker
  services share the ledger. RPi core secret-name and PostgreSQL coordinator
  preflight checks are covered without printing secret values.
- No frontend files or ETF-provider adapter files changed, and no credential
  values or provider payloads were written to the repository.
- Remaining acceptance gates are unchanged: current provider/account usage
  baselines beyond MarketData.app, provider-specific byte/budget maps, SEC
  issuer-materialization and complete NMS/OTC reconciliation, target-owned
  GitHub/RPi/deployment secret/coordinator verification, unresolved legal/data
  use controls, user-deferred Tradier/IBKR/Ondo, exact staged-source full live
  matrix, and the separately authorized 30-day shadow phase.

## 2026-09-16 current MarketData.app live receipt

- With the hardened runner and settled implementation, the configured
  MarketData.app key passed all seven selected bounded cases again. The runner
  correctly recorded `not_current_source` because the implementation is
  intentionally uncommitted/dirty; this is current transport/schema evidence,
  not staged-candidate acceptance. The same preflight listed the exact
  unresolved provider controls and made no calls to blocked providers.

## 2026-09-16 interrupted implementation checkpoint inventory

This checkpoint intentionally remains an implementation handoff rather than a
closure or integration claim. The current source tree is dirty because the
approved provider-platform implementation and its tests are not committed in
this session. The exact next action is to resume from this handoff, reconcile
the owner-controlled quota/secret/source/legal gates, then rerun the complete
current-SHA provider matrix only after those gates are admitted. Do not merge,
deploy, activate routing, or start the 30-day shadow phase from this checkpoint.

The current validation evidence is: authoritative Docker backend gate `2,652
passed`, `81.90%` combined coverage, 89 warnings; backend unit suite `2,266
passed`, 37 warnings; workflow tests `46 passed`; Ruff, Python compilation,
Compose/deployment contracts, workstream validation, and `git diff --check`
passed; current configured MarketData.app focused live subset `7/7` with
`not_current_source` receipt status. The full current-SHA live matrix is not
accepted because the worktree is dirty and provider/account baselines,
provider-specific bounds, source/legal controls, deployment stores, and
deferred-provider gates remain unresolved.

The exact dirty-path inventory at this checkpoint is:

```text
.env.example
.github/workflows/ci.yml
.github/workflows/provider-live.yml
Makefile
backend/.env.example
backend/app/config.py
backend/app/models/__init__.py
backend/app/models/market_data_foundation.py
backend/app/providers/crypto_market_data.py
backend/app/providers/edgar.py
backend/app/providers/finra_otc_directory.py
backend/app/providers/fred.py
backend/app/providers/optional_market_data.py
backend/app/providers/registry.py
backend/app/providers/tokenized.py
backend/app/routers/market_data_admin.py
backend/app/routers/options_exposure.py
backend/app/services/instrument_events.py
backend/app/services/market_event_edgar_scan.py
backend/app/services/market_universe.py
backend/app/services/options_data.py
backend/app/services/provider_availability.py
backend/app/services/provider_routing.py
backend/app/services/provider_runtime.py
backend/app/services/tokenized_assets.py
backend/app/tasks/data_tasks.py
backend/app/workers/arq_worker.py
backend/tests/conftest.py
backend/tests/live/conftest.py
backend/tests/live/live_usage.py
backend/tests/live/test_market_data_providers_live.py
backend/tests/live/test_openfigi_live.py
backend/tests/live/test_tokenized_providers_live.py
backend/tests/unit/providers/test_direct_transport_instrumentation.py
backend/tests/unit/providers/test_new_providers.py
backend/tests/unit/providers/test_optional_market_data.py
backend/tests/unit/providers/test_tokenized.py
backend/tests/unit/routers/test_market_data_admin_router.py
backend/tests/unit/services/test_instrument_events.py
backend/tests/unit/services/test_market_event_edgar_scan.py
backend/tests/unit/services/test_market_universe.py
backend/tests/unit/services/test_provider_availability.py
backend/tests/unit/services/test_provider_quota_contract.py
backend/tests/unit/services/test_provider_registry.py
backend/tests/unit/services/test_provider_runtime.py
backend/tests/unit/services/test_tokenized_assets.py
backend/tests/unit/test_live_provider_runner.py
backend/tests/unit/test_provider_live_usage.py
backend/tests/unit/test_provider_secret_wiring.py
backend/tests/unit/workers/test_arq_worker.py
deploy/rpi/compose.yml
docker-compose.yml
docs/agent-orchestration.md
docs/data-providers.md
docs/deployment.md
docs/project-todos.md
docs/provider-live-validation.md
ops/workstreams/feat-market-data-provider-platform/handoff.md
ops/workstreams/feat-market-data-provider-platform/plan.yaml
ops/workstreams/feat-market-data-provider-platform/session.json
ops/workstreams/feat-market-data-provider-platform/validation.jsonl
scripts/rpi.py
scripts/run-live-provider-probes.py
scripts/worktree-runtime.py
tests/workflow/test_agent_session.py
tests/workflow/test_staging_workflow.py
backend/alembic/versions/a9b0c1d2e3f4_add_sec_issuer_directory_candidates.py
backend/app/services/provider_quota_coordinator.py
backend/tests/unit/routers/test_options_exposure.py
backend/tests/unit/services/test_provider_quota_coordinator.py
docker-compose.e2e.yml
tests/e2e/
```

## 2026-09-16 SEC/Nasdaq/Finnhub hardening and authoritative gate

- SEC future-listing materialization now requires corroborated, resolved
  multi-provider evidence with exact symbol/company agreement and either a
  shared venue MIC or a shared FIGI/ISIN/CUSIP from at least two sources.
  Single-source, incomplete, conflicting, and unresolved-venue candidates are
  quarantined; later ambiguous evidence can quarantine legacy provisional
  records rather than silently activating them.
- Nasdaq NMS/equity and ETF reconciliation now fails closed on declared-total
  or cursor gaps, wrong quote types, duplicate listing keys, unknown venues,
  and unmappable MICs. Successful reconciliation records deterministic
  expected/observed/missing MIC coverage and per-MIC counts. FINRA OTC remains
  explicitly outside the authoritative Nasdaq absence scope pending its own
  complete source reconciliation.
- Finnhub routing now models both reviewed dimensions: 60 calls/minute and a
  hard 30 calls/second ceiling. Every reviewed operation reserves both
  dimensions, while existing operator overrides remain preserved when config
  promotion refreshes the provider row.
- Validation after these changes: full backend unit suite `2,273/2,273`;
  focused SEC/universe and provider/quota/runtime contracts `313/313`;
  authoritative Docker-backed backend gate `2,659/2,659`, `81.90%` combined
  coverage, 89 warnings, isolated testcontainer session
  `22b7481d-c4a1-4d15-ae69-7900026793f8`; Ruff passed. No provider calls or
  credentials were used by these checks.
- This does not close the branch. The exact current-SHA live matrix is still
  unaccepted while the worktree is dirty and provider-native baselines,
  byte/account/source/legal controls, complete OTC reconciliation, target
  secret-store verification, deferred-provider decisions, and the final shadow
  gate remain owner-controlled. Do not integrate, deploy, activate routing,
  or begin the 30-day shadow run from this checkpoint.

## 2026-09-16 FINRA synchronous-routing correction

- FINRA's `FINRA_ASYNC_MAX_RESULT_BYTES` control is now scoped only to the
  signed `download_async_result` operation. Synchronous short-interest and OTC
  Daily List calls remain independently eligible under the published 3 MB
  synchronous response ceiling and the existing durable monthly byte budget;
  async result downloads remain fail-closed until a positive operator bound is
  supplied.
- Focused FINRA/provider contract and runtime validation passed `182/182`,
  Ruff and `git diff --check` passed, and no provider calls or credentials
  were used. This is source-dirty evidence and is not exact-current-SHA live
  acceptance.

## 2026-09-16 provider-usage-dimension gate checkpoint

- The Docker-backed combined backend unit/integration coverage gate completed
  with exit code `0` in the current feature worktree. Its isolated test
  session was cleaned up without a host-wide prune. The terminal stream was
  truncated after the final test dots, so this checkpoint intentionally does
  not claim a reconstructed test count or coverage percentage.
- Compose/RPi contract validation, workstream validation for all 30 records,
  and `git diff --check` also passed. Existing warnings about preparing the
  private quota-ledger directory are non-fatal; no provider routing was
  activated and no provider calls were made by these gates.
- The implementation now persists provider-native usage dimensions and
  account-plan metadata. Twelve Data's documented minute-credit headers are
  captured as a named `credits_per_minute` dimension; MarketData.app exposes
  the configured `credits_per_day` trial/free-tier dimension. Unknown daily
  Twelve Data semantics remain unrepresented rather than guessed.
- This does not close the branch. The exact current-source full live matrix
  remains blocked by provider-specific baselines, byte/weighted cost maps,
  legal/source controls, universe reconciliation, target secret stores, and
  deferred-provider decisions. The branch remains at
  `ready_for_human_review` until those owner-controlled gates are resolved.

## 2026-09-16 Twelve Data native-baseline reconciliation

- Twelve Data's `/api_usage` observation is now allow-listed for one exact
  coordinator reconciliation: the reviewed `credits_per_minute` dimension
  when the provider returns the documented used/left headers, matching limit,
  and a current fixed-minute reset. The separate 800-credit daily contract
  remains observation-only because the endpoint does not expose a stable
  daily counter shape; no daily usage is fabricated from the minute headers.
- Focused provider/account/quota checks passed `211/211`; the complete backend
  unit suite passed `2,300/2,300` with 37 warnings. Ruff and diff checks passed;
  no external provider calls were made.
- This improves post-bootstrap cross-session reconciliation but does not waive
  the initial-baseline gate: a fresh account still requires an exact operator
  baseline or an explicitly admitted native snapshot path before quota-spending
  live operations. The full live matrix and the other provider/legal/source,
  reconciliation, deployment-secret, and shadow gates remain open.

## 2026-09-16 complete-OTC source audit

- The complete OTC universe gap is now tied to a concrete official candidate:
  OTC Markets publishes Overnight and US Security Master specifications with
  SFTP delivery details. Those documents specify file shape, not access,
  quota, cadence, redistribution rights, or a free-use grant. No adapter or
  live call was added from the specification alone.
- FINRA's public catalog remains lifecycle-only for this purpose: its OTC
  Daily List supports additions, deletions, symbol/name changes, and related
  events, but it does not establish a complete current OTC security master.
  The existing FINRA OTC candidate therefore stays fail-closed until an
  authorized complete source and terms are supplied.

## 2026-09-16 Massive use-scope admission hardening

- Massive's official Stocks Basic terms were reviewed and recorded as a
  provider-specific legal/use control: free access is personal,
  non-business, non-commercial, and non-redistributed. A configured API key
  therefore no longer makes Massive metadata, history, or event routes
  eligible by itself.
- Added explicit non-secret controls for the attestation boolean, authority
  reference, exact use scope, review timestamp, and optional expiry. Registry
  diagnostics and live preflight report the missing controls without exposing
  values; Compose/RPi, environment examples, and GitHub workflow mappings are
  wired with fail-closed defaults. The existing corporate-action page bound
  remains required for event routing.
- Focused registry/wiring tests passed `47/47`; the broader provider/quota/
  runtime/live-runner regression set passed `435/435`; the complete backend
  unit suite passed `2,300/2,300`; Compose contracts, workflow tests, Ruff,
  compilation, workstream validation, and diff checks passed. No provider
  calls or credentials were used.
- This is not a routing promotion or legal authorization. The exact staged
  live matrix, provider baselines, complete OTC source, target-owned secret
  stores, and final shadow gate remain open. No frontend or ETF-provider
  adapter files changed.

## 2026-09-16 exact-source Massive preflight

- After commit `6dab6d08bb2f50809a3ad1d5e0bd5a677741c6b7`, the lock-protected
  full live runner stopped before network access with exit `2`. Its safety
  report showed the owner-configured MarketData.app Starter Trial as routable
  and reported Massive as non-routable for the four missing use-attestation
  fields. Durable quota admission, provider-account baselines, other legal /
  source controls, unresolved capability cases, and the final staged live
  matrix remain blocked as expected.
- This exact-source preflight consumed no provider quota and is not transport
  acceptance. No deployment, routing activation, integration, or shadow run
  occurred.

The same preflight was replayed with approved access to the owner-managed
durable quota ledger. The coordinator health check then passed, and the runner
advanced to the provider-specific admission stage before stopping at exit `2`:
the configured MarketData.app account-plan and option-chain controls were
routable, while provider baselines/cost maps and the remaining legal/source and
capability gates were still unresolved. The generated exact-source receipt is
the authoritative record for this replay; it made zero provider calls.

## 2026-09-16 exact-source MarketData.app live subset

- With the owner-managed quota ledger and current `starter_trial` configuration,
  the bounded MarketData.app subset passed `7/7` against exact source
  `2f6e7384a57eafa9c284c88880d18f402a2c261e` (9 upstream requests,
  17,241 response bytes). It covered authenticated read/latest price,
  intraday history, option expirations/current chain, historical option quote,
  and account usage. The response-priced unbounded historical-option policy
  case passed with zero request as designed.
- The provider receipt is complete and current-source; no other provider was
  contacted. This is bounded transport/schema/quota-settlement evidence only,
  not full-matrix acceptance or routing promotion. The trial expiry remains
  `2026-10-11T18:09:00+01:00`, after which effective capacity falls back to
  Free Forever/100 credits per day.

## 2026-09-16 Massive expiry diagnostics hardening

- Massive's optional use-attestation expiry is now included in the registry's
  advertised routing-control tuple. If an operator supplies an expired or
  malformed expiry, the missing-control diagnostic names
  `MASSIVE_MARKET_DATA_USE_EXPIRES_AT`; an omitted expiry remains valid for a
  non-time-limited review.
- Focused registry, secret-wiring, and live-runner tests passed `84/84`; Ruff
  and diff checks passed. No provider calls or credentials were used by this
  change. The branch remains fail-closed for missing Massive attestation and
  all other unresolved provider gates.
- CI and environment-example assertions now explicitly require the expiry
  mapping as well; the focused wiring/registry suite passes `48/48` after this
  test hardening.

## 2026-09-16 OTC Markets source-contract detail

- The complete-OTC candidate contract now records the official OTC Markets
  delivery specifics: pipe-delimited security-master plus validation file,
  approximately 5 MB, 5:20 PM and 7:20 PM ET trading-session deliveries via
  `sftp.otcmarkets.com`, CUSIP and no-CUSIP variants, and the specification's
  separate CUSIP redistribution-license warning.
- This strengthens source-contract evidence without pretending access or
  entitlement. No SFTP credentials, adapter routing, or live request was
  added; the candidate remains non-routable until delivery access, quota,
  completeness, and redistribution rights are authorized.

- The candidate parser now recognizes the official OTC Markets pipe-delimited
  security-master shape in addition to the existing FINRA/DAPI and generic
  mirror shapes. It preserves SecID, CompID, CUSIP, tier, status, reference
  price, overnight-eligibility, and the raw row; duplicate symbols, unknown
  status codes, and incomplete rows fail closed. Provider/parser regression
  coverage passed `266/266`; no provider calls or credentials were used.
- The complete backend unit suite then passed `2,304/2,304` with 37 warnings;
  no external provider calls were made.

- The exact-source full live runner at `4899dfbfa92cd51379f5e97bdfe60012a459d3d1`
  stopped before network access with exit `2`. It reported the expected
  unresolved provider baselines/cost maps and legal/source gates, including
  FINRA OTC source admission; the new parser did not widen routing. Zero
  provider calls and zero shared-key quota were consumed.

## 2026-09-16 provider-plan operations checkpoint

- Added a concrete, secret-free operator procedure to
  `docs/provider-live-validation.md` for changing provider plans, recording
  exact active-window baselines, and inspecting remaining headroom. The
  procedure keeps MarketData.app's Starter Trial/10,000 daily credits and
  timezone-aware expiry provider-specific, documents the automatic
  Free-Forever/100 fallback after expiry, and requires separate attestations
  for calls, credits, bytes, and other dimensions.
- The local owner-managed environment already contains the non-secret
  MarketData.app settings `starter_trial`, `10000`, and
  `2026-10-11T18:09:00+01:00`; no secret values were printed or added to Git.
- Focused quota/admin tests passed `104/104` with `--no-cov`; the default
  focused invocation also passed all tests but returned the repository's
  expected global coverage-threshold exit because it intentionally ran only
  the focused subset. Workstream validation and `git diff --check` passed.

## 2026-09-16 current unit validation

- The complete backend unit suite passed `2,311/2,311` with 37 warnings in
  `103.71s` using the exact feature checkout. The unqualified integration
  suite was not accepted as a failure signal because its Testcontainers setup
  could not access the local Docker socket (`PermissionError`); the earlier
  Docker-backed authoritative gate remains the relevant integration evidence.

## 2026-09-16 MarketData.app effective-expiry diagnostics

- The effective MarketData.app `credits_per_day` contract now exposes the
  active trial's non-secret `account_plan_expires_at` metadata to provider
  policy/admin diagnostics. Expired trials still emit only the effective
  Free Forever plan and 100-credit limit; no expired timestamp is retained as
  an active entitlement. Focused quota/runtime coverage passed `149/149`,
  Ruff, compileall, diff checks, and workstream validation passed. No
  provider calls or secret values were used.

- The complete backend unit suite was replayed against this implementation and
  passed `2,311/2,311` with 37 warnings in `103.55s`. The exact-source live
  preflight remained fail-closed and made zero provider calls.

## 2026-09-16 current-source MarketData.app live validation

- With the owner-managed durable quota ledger and configured trial settings,
  the exact current-source focused MarketData.app matrix passed `7/7` cases
  (`9` HTTP requests, `17,241` response bytes) at source
  `a9d7db8dc27351bd56ee5d6d1bf09f0616d15f58`. It exercised the account-usage,
  latest-price, intraday-candle, option-surface, and bounded option-history
  paths; the response exposed the reviewed `10,000` daily-credit limit and
  the unbounded response-priced option-history guard made no request. The
  redacted receipt is committed in `validation.jsonl`; no secret or payload
  entered Git.
- Reading the same durable coordinator with the owner-managed environment
  resolved the active `credits_per_day` dimension as verified: `10,000` limit,
  `260` locally settled credits since the provider observation, and `9,740`
  remaining. This is ledger/accounting evidence, not a claim that other
  uncoordinated clients cannot have spent the provider allowance.
- The owner-only `app.env` now persists the durable quota-ledger path, live
  usage-ledger path, and local live-run scope so future worktrees reuse the
  same cross-session account accounting. The file remains outside Git with
  mode `0600`.
- A focused OpenFIGI attempt was correctly blocked before network access
  because its active public-IP `mapping_requests_per_minute` baseline is
  unknown. Its redacted zero-request preflight receipt is also committed;
  no generic limit or zero-usage assumption was introduced.
- After the handoff receipts were committed, the same MarketData.app matrix
  was rerun using only the persisted owner configuration and again passed
  `7/7` (`9` requests, `17,241` bytes). The receipt records source
  `430e01ae7d8d37e5d39e1432fecfb7466ff195f1`; it is transport/quota evidence
  for that tested source, not a claim that the receipt-commit SHA itself has
  undergone the full matrix.

## 2026-09-16 current full-matrix preflight

- The complete manifest preflight was rerun at source
  `3bac98639261651a3cee99b966d601a70e730f4c` and exited `2` before network
  access. It recorded the exact three blocker groups: provider-specific
  quota/cost/baseline admission, required legal/source/safety controls, and
  unresolved capability live dispositions. The redacted receipt is committed
  in `validation.jsonl`; this run made zero provider requests and does not
  claim a partial full-matrix pass.
- After the current-source MarketData.app replay, the durable coordinator
  reports `289` locally settled trial credits and `9,711` remaining from the
  configured `10,000` daily limit. The native observation remains the same
  provider snapshot; these additional units are local reservations settled by
  the live tests and are intentionally not treated as a global provider-account
  total for uncoordinated clients.

## 2026-09-16 Marketstack quota-source conflict hardening

- Marketstack's current pricing page says `100` requests/month while its FAQ
  still says `1,000` requests/month. The quota contract now records both URLs,
  marks `published_monthly_limit_conflict` and the reset boundary as unknown,
  and retains `100` only as a conservative reservation ceiling. Routing stays
  fail-closed; no published value is presented as confirmed. Quota-contract
  coverage passed `98/98`, Ruff, compile, diff, and workstream checks passed.

## 2026-09-16 full backend unit replay after Alpaca usage bootstrap

- The complete backend unit suite passed `2,333/2,333` with 37 warnings in
  `136.83s` against the exact feature checkout. Total coverage was `70.70%`,
  above the configured `55%` threshold. This validates the native Alpaca
  account-usage bootstrap, its fail-closed normal-routing boundary, and all
  existing backend/provider regressions together.
- The direct workstream validator passed all `30` workstream records. The
  host-level `make branch-validate` Xcode-license blocker remains unchanged;
  this direct validator result is the repository/workstream evidence and does
  not substitute for the Docker-backed full-stack gate.

- Three bounded Alpaca header probes (one request each, no payload persisted)
  returned the reviewed `200` limit and `199` remaining, but
  `X-RateLimit-Reset` tracked the current/near-current Unix second rather than
  proving a stable minute boundary. The implementation therefore correctly
  keeps ordinary Alpaca routing fail-closed and treats the native snapshot as
  observation-only; no fixed-window assumption was introduced.

## 2026-09-16 Dinari Sandbox canary admission hardening

- Dinari Sandbox now has a separate, explicit runner mode:
  `--dinari-sandbox-canary --provider dinari`. It requires the non-secret
  owner controls `DINARI_SANDBOX_CANARY_AUTHORIZED=true`,
  `DINARI_SANDBOX_CANARY_AUTHORITY_REFERENCE`, and a positive
  `DINARI_SANDBOX_CANARY_MAX_REQUESTS`. The cap is an application safety budget,
  not an inferred Dinari entitlement; normal Dinari routing remains blocked by
  the provider's unpublished Sandbox quota/terms.
- The canary cap is consumed by the HTTPX pre-send guard for every actual
  request, including adapter fan-out and failed requests. The run uses the
  existing exclusive live-run lock, records only aggregate redacted telemetry,
  marks its usage receipt `admission_mode=dinari_sandbox_canary`, and never
  persists Dinari Sandbox payloads or calls the durable provider reservation
  path. Normal Dinari live selection is still rejected before the run lock.
- The local canary preflight was exercised with the rotated owner key present;
  it stopped before network because the three explicit canary controls are not
  configured. No Dinari request was made by that preflight. GitHub's manual
  provider-live workflow now exposes a separate boolean canary input and reads
  the same controls from environment variables; it remains off by default.
- The exact current-source preflight after commit `c6895c83f` reproduced the
  same fail-closed result (`0/0` cases, zero provider requests) and is recorded
  in `validation.jsonl` with the three missing control names; no generic Dinari
  quota was inferred.
- After the follow-up pre-transport admission-error fix (`fc9ca215b`), the
  exact-current canary preflight again stopped before network (`0/0`, zero
  provider requests) and recorded the same three missing controls at that
  source. The focused canary/runner/ledger suite remains `65/65`.
- Focused canary/runner/ledger coverage passed `65/65`; Ruff, compile, workflow
  YAML parsing, and diff checks passed. The complete backend suite passed
  `2,727/2,727` executable tests with `464` expected skips and `89` warnings;
  coverage was `81.98%`. The host Xcode-license blocker and the remaining
  provider/legal/source/universe/deployment-secret/Docker/shadow gates are
  unchanged.

## 2026-09-16 Twelve Data native usage snapshot

- The exact current-source focused Twelve Data account-usage run passed `1/1`
  at source `2fab722e5d67d8bbfbcbf379013095c1ba2de14a`. It made one bounded
  `/api_usage` request and observed the native Basic-plan minute pool (`8`
  credits total, `7` remaining after the probe); the provider-native
  `credits_per_minute` baseline reconciled into the durable coordinator.
- Twelve Data's documented Basic-plan `800` credits/day UTC pool remains
  represented explicitly in the contract, but `/api_usage` does not expose a
  stable cumulative daily counter. The live snapshot therefore does not invent
  daily usage or widen routing: every normal operation remains blocked until
  the daily baseline is independently reconciled or an explicit reviewed
  account-scope policy permits safe reset accounting.
- The redacted provider-live receipt records one request and 131 response bytes;
  no credential or response payload was persisted. The existing exact-source
  unit/live accounting and cross-session ledger behavior remain unchanged.

## 2026-09-16 EODHD native usage snapshot

- The exact current-source focused EODHD account-usage case passed `1/1` at
  source `c885b9d5b31730f7af8d7e312ddc24f1f52c652e`. It made one bounded
  `/user` request, observed the provider's daily usage payload and native
  `x-ratelimit-limit=1200`/`remaining=1199` headers, and wrote 304 bytes of
  aggregate telemetry.
- EODHD reported a previous active usage date rather than the current UTC date,
  so the adapter correctly kept `calls_per_day` observation-only and did not
  fabricate a reset timestamp or reconcile a stale daily baseline. The
  provider's published 20/day versus 1,000/min source conflict remains
  conservatively represented and normal EODHD routing stays fail-closed until
  a current-day native baseline or provider clarification exists.
- No credential or response payload was persisted; the receipt and ledger row
  are committed as transport/accounting evidence only.

## 2026-09-16 current backend suite replay

- The complete backend suite was replayed against the current checkout after
  the live-admission fixes and provider-usage evidence updates. It passed
  `2,727/2,727` executable tests with `464` expected skips and `89` warnings in
  `624.49s`; total coverage was `81.98%`, above the configured `55%` threshold.
- Live-provider tests remained intentionally skipped by the normal unit
  command; the bounded current-source Twelve Data and EODHD account probes are
  recorded separately in `validation.jsonl`. This suite result does not close
  the provider-native baseline, source/legal, deployment-secret, Docker, or
  final shadow gates.

## 2026-09-16 Dinari Sandbox canary validation

- The explicit Dinari Sandbox canary was rerun against implementation source
  `d80aa10d3b55ba4f2e6a669b525953b8c96d17dd` (the following commits only
  record evidence) with transient owner controls
  and a per-process cap of `32` requests. The manifest compound case passed
  `1/1`, making `14` bounded upstream requests and recording `160,813` response
  bytes across catalogue discovery, UUID/symbol resolution, price, quote,
  DAY/WEEK/MONTH/YEAR aggregate history, news, dividends, splits, and
  corporate actions.
- The first trial with a one-request cap stopped before the second operation,
  proving that the cap is enforced at the actual HTTP transport boundary. The
  successful run used no persistent canary authorization, wrote no sandbox
  payload into canonical data, and retained only redacted aggregate telemetry
  in `validation.jsonl` and the owner-managed local ledger.
- This closes the implementation/live-schema evidence for the isolated Sandbox
  canary path only. Dinari's numeric Sandbox quota/reset, commercial terms,
  redistribution rights, and production routing remain intentionally
  non-routable and require provider/owner evidence.

## 2026-09-16 current-source admission audit

- The no-network provider admission audit at source `0a6a92070de9bf8e22ca74b3db99e70dd31970f6` found `marketdata_app` as the only provider with every currently required operation dimension admission-safe; the remaining registered operations have `95` provider-specific quota, baseline, byte-cost, entitlement, or reset blockers.
- This audit made no provider requests and is not live acceptance. It confirms that the successful Dinari Sandbox canary is intentionally outside ordinary routing admission, while the normal market-data chain remains fail-closed for every provider whose account-wide usage or provider contract is not independently reconciled.

## 2026-09-16 current-source MarketData.app live matrix replay

- The configured MarketData.app Starter Trial account was revalidated at source
  `898e3e97cff453c7c958b78316ffb2cc25db24a`. The focused manifest matrix
  passed `7/7`, with `9` upstream requests and `19,618` response bytes.
- Successful operations covered account usage, daily/five-minute OHLCV,
  latest price, option expirations, current option chain, and bounded
  historical option quotes. The deliberate response-priced unbounded-history
  guard also passed without making a request.
- The redacted receipt is in `validation.jsonl`; no credentials or provider
  payloads were persisted. This confirms current transport/schema and local
  accounting only; paid-plan changes still require explicit configuration.

## 2026-09-16 Binance native usage and bounded crypto matrix

- Binance's account-usage-only bootstrap passed `1/1` at source
  `1d54845c4af8aabff2e16e876f81d3473f5b90c5`, observing the native
  request-weight window before any data read. A subsequent bounded Binance
  matrix passed `3/3`, making `7` upstream requests and recording `17,616,646`
  response bytes across universe discovery, latest/current price, ordinary
  crypto history, bounded 30-day daily history, and the usage snapshot.
- The first full-provider attempt was correctly stopped before transport while
  the active weight baseline was unknown. The explicit usage bootstrap then
  reconciled the durable local window, allowing the bounded matrix to run
  without a guessed limit or request-count substitution.
- A follow-up no-network audit now reports Binance and MarketData.app as the
  only currently admission-safe providers, with `91` provider-operation
  blockers remaining. This changes routing eligibility only for the observed
  Binance request-weight window; other Binance contract, universe, or future
  windows remain subject to the same fail-closed controls.

## 2026-09-17 current implementation validation

- The current committed checkout passed the complete backend unit gate:
  `2,364/2,364` tests, `37` warnings, and `70.82%` coverage. The focused
  live-runner, provider-secret-wiring, quota-contract, and quota-coordinator
  suites also passed (`215/215`); the focused invocation's repository-wide
  coverage threshold was intentionally not used as an acceptance gate because
  it does not exercise the full unit surface. Ruff and `git diff --check`
  passed, and `make branch-validate` validated all `30` workstream records.
- The exact current-source Bybit xStocks safety preflight at
  `8b7fe85b00a905b5184893649ec757c4e6d159c0` stopped before network access
  (`0/0` cases, zero provider requests). It now reports the concrete missing
  Bybit automated-use/egress-jurisdiction controls and the unknown native
  five-second usage baseline; no provider quota or legal entitlement was
  inferred. The receipt is appended to `validation.jsonl`.
- Current static deployment validation also passed: `make
  test-compose-contract` validated the main and RPi Compose files, and `make
  test-workflow` passed `46/46` workflow tests. These checks verify wiring and
  isolation contracts only; they do not prove the owner-controlled GitHub,
  RPi, or production secret stores contain the required values.
- MarketData.app remains configured as the owner-approved Starter Trial
  (`10,000` credits/day) through `2026-10-11T18:09:00+01:00`, then falls back
  automatically to the configurable Free Forever (`100` credits/day) pool.
  This provider-specific plan/limit/expiry path is covered by exact-boundary
  tests and the current-source bounded live matrix; paid-plan changes remain
  explicit environment configuration plus the separate paid-routing gate.
- The branch remains incomplete for provider-owned quota/reset attestations,
  legal/source and redistribution approvals, complete NMS/OTC reconciliation,
  environment secret-store verification, and the separately authorized final
  shadow phase. No routing promotion, deployment, or ETF-adapter change was
  made.

## 2026-09-17 EODHD account-specific quota evidence

- The configured EODHD key's credentialed `/user` snapshot reports a native
  daily allowance of `20` calls and an `X-RateLimit-Limit` of `1,200`
  requests/minute. The durable current observation records `3` daily calls and
  `2` minute requests; no reset timestamp was returned, so no reset boundary
  was inferred.
- The EODHD seed now accepts any positive operator-reviewed provider-native
  minute entitlement, including `1,200`, without an arbitrary upper ceiling.
  Ordinary routing remains fail-closed until
  `EODHD_REVIEWED_MINUTE_LIMIT`, `EODHD_REVIEWED_MINUTE_RESET`, and
  `EODHD_MINUTE_QUOTA_EVIDENCE` are configured with admission-safe reset and
  current evidence.
- Focused quota/registry coverage passed `134/134`; the complete backend unit
  gate passed `2,364/2,364` with `37` warnings and `70.82%` coverage. The
  exact-current-source bounded live account-usage replay at `cfe08fde0` also
  passed `1/1` with one request and 304 response bytes. The redacted receipt is
  retained in `validation.jsonl`; no secret or provider payload was persisted.

## 2026-09-17 Tiingo reset-contract clarification

- The current official Tiingo general API documentation states that hourly
  requests reset every hour, daily requests reset at midnight Eastern time,
  and monthly bandwidth resets on the first of each month at midnight Eastern
  time. The repository now cites that source for the hourly dimension instead
  of describing the hourly reset as entirely undocumented.
- The hourly boundary model (fixed/calendar versus rolling) and the 500
  unique-symbol monthly anchor remain unspecified by Tiingo. The contract
  therefore remains fail-closed and requires explicit
  `TIINGO_REVIEWED_HOURLY_RESET`, `TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET`, and
  evidence controls; no rolling hourly or 31-day symbol window is inferred.
- The focused quota/registry suite passed `134/134`. No provider request was
  made for this documentation/contract correction.
- The current-source full backend unit replay at `0fd92bdc1` passed
  `2,364/2,364` with `37` warnings and `70.82%` coverage. This is automated
  regression evidence only; provider live, legal/source, universe,
  deployment-secret, and final-shadow gates remain separate.

## 2026-09-17 FMP quota-source citation correction

- The FMP bandwidth quota seed now cites the current official pricing document
  (`/developer/docs/pricing`), which states the Basic allowance of 250 calls/day
  and the free-plan 500 MB trailing-30-day bandwidth pool. The previous legacy
  `/pricing-plans` citation was removed. This entry is superseded by the
  later trailing-bandwidth contract correction above: the documented bandwidth
  window is now represented as `rolling_30_days` by default, while the daily
  reset and current entitlement evidence remain review gates.
- Focused quota-contract coverage for the citation correction passed `110/110`;
  no provider request was made.
## 2026-09-17 current-head live preflight after refresh-queue fixes

- The exact current source `ba3893314` was checked with the full provider
  matrix. It stopped before transport (`0/0` cases, zero provider requests).
- The receipt records the durable quota-coordinator availability blocker plus
  the existing provider-specific quota/reset, legal/use, capability-coverage,
  and unresolved-operation blockers. No credentials or provider payloads were
  consumed; the receipt is appended to `validation.jsonl`.
- The queue fixes remain repository-controlled and fully validated separately:
  the backend unit gate, workflow tests, Compose contracts, Ruff, and
  workstream validation are green.

The same preflight was then rerun with elevated access to the owner-only
quota ledger at source `94b72c17b`. The ledger health path passed, but the
matrix still stopped before transport (`0/0`, zero provider requests) on the
provider-specific reset/baseline/cost blockers, unresolved live-operation
dispositions, and legal/use controls listed in the receipt. This supersedes
the sandbox-only “quota coordinator unavailable” diagnostic above.

Commit `247718a6f` adds a requirement-by-requirement acceptance audit to
`docs/provider-live-validation.md`. It records which platform areas are
verified by repository evidence and which remain external/provider,
deployment-secret, universe, or final-shadow gates; it does not promote any
provider or start the shadow run.
## 2026-09-25 SEC issuer-directory source evidence retention

- Commit `27f3cc34a` adds immutable `source_payload` evidence to every
  `SecIssuerDirectoryCandidate` row. Normalized CIK/name/ticker/admission
  fields remain unchanged; the exact provider-adapter row is now retained and
  returned by the admin candidate report.
- Migration `e7f8a9b0c1d2` is additive and refuses downgrade while non-empty
  SEC source evidence exists. Focused scan/migration tests pass `18/18`, Ruff
  is clean, migration compatibility passes, Alembic reports one head, and
  workstream validation accepts all 30 records.
- This closes an in-scope evidence-loss path only. It does not make the SEC
  directory a complete US security master, change the staged materialization
  policy, promote routing, or close the remaining provider quota/legal,
  complete NMS/OTC reconciliation, external secret-store, deferred-provider,
  publication, or final shadow gates.
