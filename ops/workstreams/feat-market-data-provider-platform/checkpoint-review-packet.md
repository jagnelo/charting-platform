# Provider integration checkpoint review packet

Status as of 2026-10-16 05:10Z: not yet ready for conditional coordinator
acceptance. The required functional browser matrix completed (154 passed, 106
expected skips, zero failures/retries), but strict visual parity remains red on
three Study Lab snapshots (~1.0% pixel difference against the 0.5% threshold).
Exact-source CI run `38853327766` for `f614621778521743e5cc8bdce29a61501025ef08`
is in progress; the final packet commit will need its own exact-source CI.
Twenty-three individually admitted provider manifests passed 62/62 cases on
staged candidate tree `592261aaef97a9ba2d3b3d6c818720eadd630abc` (parent
`f614621778521743e5cc8bdce29a61501025ef08`), with 151 provider requests and
64,552,569 measured response bytes. The full 27-provider verifier correctly
remains incomplete for four held providers; this is not full provider live
acceptance. Provider-owned frontend files remain unchanged. Conditional
acceptance is coordinator-owned after required contracts and tests pass. This
packet does not authorize provider activation, paid routing, deployment, the
30-day operational trial, or feature-agent staging integration. The complete
roadmap remains open.

The human's conditional checkpoint-acceptance delegation (timestamp supplied
as `22:55Z`) is recorded in `plan.yaml` and `handoff.md`: “Yes—approve that
initial scope and handle checkpoint acceptance.” The coordinator may accept
and merge the four checkpoints only after required cross-feature contracts and
full tests pass, using verified free operations and keeping held, unreviewed,
paid/trial and unsafe operations disabled. This is not acceptance of this exact
source and does not waive validation, authorize this feature agent to
integrate, permit deployment/paid/trial activation, or allow cleanup.

## Exact-source evidence boundary

- Commit `f614621778521743e5cc8bdce29a61501025ef08` contains the FMP plan
  admission correction, combined backend coverage enforcement in CI, and
  checkpoint-plan refresh. It is pushed to the Provider branch; exact-source
  CI run `38853327766` is in progress. The branch contains released common-repair staging
  `82d881e76be8de538abb6ec5c454d96afe0ee56a` through merge
  `2845817d37296fae8728d72cd22a95082d67081f`; this is common repair only, not
  Provider acceptance. Provider-owned frontend files remain unchanged.
- Full local profile on this candidate passed dependency/lock checks,
  migration-head check (migration compatibility skipped because no migrations
  changed since the released baseline), npm install, Ruff, formatting,
  TypeScript, backend coverage, frontend unit tests/build, Compose contract,
  research-runner probes, and isolated stack health. Docker backend tests passed
  2,792 unit tests in 56 shards and 395 PostgreSQL/Redis integration tests.
- The `make validate-integration` process exited red at `e2e-functional`
  before assertions because existing ignored `frontend/test-results` and
  `frontend/playwright-report` directories are owned by `nobody` and are not
  writable by the host test process. The original artifacts were preserved;
  the host could not change ownership under the workspace filesystem policy.
  To verify the actual browser suite without overwriting those artifacts, the
  same configured 260-case Playwright matrix was run on this source against the
  isolated branch stack, with provider egress denied and new artifacts under
  `/tmp`: 154 passed, 106 expected skips, zero failed, zero retries. The
  earlier `host.docker.internal` attempt was invalid because it broke secure
  browser APIs and was interrupted; it is not counted as test evidence.
- The full profile's separate strict visual-parity stage was run on this source
  with its normal 104 cases and strict board-parity flag: 101 passed, 3 failed,
  zero retries. Failures are `Study Lab structured-result gap` at 1080p/100%
  (1.0% pixel difference, above the 0.5% limit), and `Study Lab sandbox-error
  gap` at 1080p/100% and 1080p/125% (about 1.0% each). Other viewport cases
  passed. These are frontend snapshot failures outside Provider ownership; no
  frontend source or snapshots were changed. Strict visual artifacts are
  retained in `/tmp/provider-e2e-host.563kL7/visual`.
- The isolated browser stack was stopped without `docker compose down -v`;
  its generated volumes and artifacts remain preserved. Provider egress was
  denied during both browser runs; no provider HTTP requests were made.
- Prior feature-branch CI run `38842402319` is green for its then-exact source
  `8f7f7609d61ad7f6337df050a84fa111913b94e6`; it predates candidate
  `56e309b`. Exact-source hosted CI for `56e309b` is outstanding.
- Published commit `b09ebb1` also contains the already-completed broad Ruff
  formatting normalization (73 files identified by the formatter check)
  alongside the account-usage fix/tests. This formatting context is classified
  as complete and published; its history will not be rewritten. This
  continuation adds no broad formatting edits.
- Two fresh no-transport preflights on `f614621` admitted 23 manifests and
  selected-provider admission with zero HTTP calls. Those 23 manifests then
  passed 62/62 cases on staged tree `592261aaef97a9ba2d3b3d6c818720eadd630abc`:
  151 requests, 64,552,569 measured response bytes, and `candidate_unchanged`
  true for every slice. These are source-bound provider slices, not full live
  acceptance. The offline verifier confirmed all 23 and correctly reports the
  four held providers as missing, so `live_acceptance=false`. Per-provider
  receipts remain outside Git at
  `/tmp/provider-live-candidate-592261aaef97a9ba2d3b3d6c818720eadd630abc.jsonl`;
  do not rebind them to a later tree.
- The full-profile provider-probe fixture stage is not live acceptance. No
  current-candidate live receipt exists yet. The historical live receipt
  remains bound only to `1afb89658d1d84e801069e1f19d7ee4f985c7e1e`
  (`186ab98a-6971-4a3f-affd-d0a2d8286106`): 20/27 manifests, 56 cases, 136
  HTTP requests and 55,732,001 response bytes. It is incomplete and is not
  rebound to this candidate. Current live execution must follow a fresh
  provider-specific durable quota admission; held operations must remain
  untouched.
- The historical live receipt has no per-run response-archive row count. No
  full scan of the multi-gigabyte private archive was done; retention evidence
  is the operation-level harness check and lack of archive-failure
  dispositions, not an independent archive-wide audit. Payloads and the
  shared quota ledger remain outside Git; nothing was reset, deleted or copied
  into the repository.

## ICP1–ICP7 checkpoint disposition

| Gate | Evidence / delivered checkpoint contract | Remaining work and owner |
|---|---|---|
| ICP1 — identity and lifecycle | Tests cover stable instrument/issuer/listing/provider-symbol identity, provenance and history, ambiguity quarantine, and legacy symbol/API compatibility. See OpenFIGI, instrument-sync, market-data-identity, lifecycle/quarantine migration, and compatibility tests. | Full same-session NMS/OTC/SEC universe reconciliation, all venue mappings, and complete ticker-change/delisting lifecycle remain Provider roadmap work. Partial or stale snapshots must never imply absence or completeness. |
| ICP2 — provider governance | Shared capability, entitlement, routing and durable multidimensional quota contracts are tested. `PROVIDER_FREE_ONLY_CHECKPOINT=true` denies reviewed paid market-data routes regardless of `ALLOW_PAID_PROVIDER_ROUTING`; trials are denied. Unreviewed market-data routes are denied except the exact reviewed-safe EODHD `/api/user` bootstrap: HTTPS evidence, exact `fetch_account_usage` operation, reconciled `calls_per_day`, explicit zero daily-credit operation cost; `requests_per_minute` is still reserved. Candidate selection exposes only this operation to strict admission. Positive stubbed execution uses a genuinely unreviewed `is_free=false` entitlement under both paid-toggle states. Paid, unknown, unknown-plan, and trial negatives prove zero callback execution under both toggle states, including known and bootstrap-unknown quota states. MarketData.app `/user/` is not exempt. Relevant suite: 104/104; exact-source backend CI is green. | The aggregate 20 EUR/USD-equivalent recurring-cost ceiling is not implemented; it remains Provider roadmap work and is not needed for this free-only checkpoint. ETF owns its consumer bridge and real request/page/retry accounting after Provider staging. No invented FX or ETF-only ledger. |
| ICP3 — series, coverage and refresh | Series/provenance, gap planning, session-aware freshness, refresh coalescing/leases, and explicit partial coverage are exercised by backend unit/integration and Strategy Lab tests. Full local backend gate and exact-source hosted backend job passed. | After Provider staging, consumers verify stale, partial, missing, and unavailable states remain distinct and do not trigger hidden provider requests. Downstream owners: ETF, TC2000, Strategy Lab. |
| ICP4 — provider operations | Fresh durable no-transport preflight admitted 23 manifests; exact staged-tree slices passed 62/62 cases, 151 requests, and 64,552,569 response bytes. The verifier confirms those 23 against tree `592261aa...` and reports `live_acceptance=false` because four held providers have no successful manifest receipt. | Keep Alpha Vantage, Dinari, Marketstack and Tiingo held with their exact reasons below. No quota was spent on these four. Their preflight and existing zero-call tests are separate from successful live evidence. Historical 20/27 evidence stays bound to `1afb896...`; it is not rebound. |
| ICP5 — migrations, startup and secrets | Local secret/config boundary and trusted backend/worker wiring have tests. Reported 50-migration fresh-install/existing-database equivalence and prior-release health check are historical dirty-candidate evidence, not a clean receipt bound to `b09ebb1`. Exact-source backend and branch-declared CI jobs are green; hosted Playwright remains pending. | Rebind migration equivalence if the branch gate requires final-source proof. GitHub/RPi/deployment secret stores are target onboarding requirements before those targets are used, not pre-Provider integration requirements. No deployment readiness is claimed. |
| ICP6 — consumers | Producer success/unavailable behavior and callable contract are tested. ETF can call `app.services.provider_runtime.execute_provider_call(db, capability, operation, *, provider_name, operation_cost_overrides, invoke, ...)`; denied admission prevents `invoke`. `provider_entitlement_admission(entitlement)` returns `allowed`, `reason_code`, `configured_plan`, `is_free`, `checkpoint_free_only`, and `basis`; provider status exposes this as `entitlement_admission`. This is routing eligibility, not aggregate subscription-cost admission. Success/unavailable examples exist in ETF coverage and Strategy evaluation/coverage tests. | Before Provider staging, deliver the producer contract and named owners only; actual ETF/TC2000/Strategy adapter wiring and consumer-specific reconciliation happen after Provider is green in staging. ETF owns holdings adapter/bridge plus page/retry accounting; TC2000 and Strategy own their consumer wiring. |
| ICP7 — reviewable source | `f614621...` is pushed; exact-source CI `38853327766` is in progress. Full Docker backend passed 2,792 unit + 395 integration tests. Functional browser matrix passed 154, with 106 expected skips, zero failures/retries. Twenty-three provider slices passed on exact staged tree `592261aa...`. | Strict visual parity remains red: 101/104 passed; three Study Lab snapshots differ by about 1.0% against 0.5%. The host wrapper also stopped before E2E assertions because existing ignored report directories are not writable; the same browser matrix was run in the version-matched container. Provider must not edit frontend. Final packet source still needs exact-source CI, and the coordinator has not accepted it. |

## Most recent no-transport operation holds

At 2026-10-16 04:48:53Z, exact-source preflight of `f614621` made zero requests.
The durable coordinator was ready; 23 full provider manifests were admitted.
The following four provider areas were quarantined before transport:

| Provider / operation area | Current safe disposition |
|---|---|
| Alpha Vantage manifest operations | Held before transport: daily request headroom is below the nine-request manifest reservation; no current-source request was made. Re-admit only after a fresh durable baseline can cover the full reservation. |
| Dinari Sandbox tokenized data operations | All nine operations remain non-routable because the complete account-reviewed quota/reset profile and worst-case per-operation cost map are missing. No canary or data request was made. |
| Marketstack OHLCV | Held before transport: monthly headroom was below the two-request reservation. Directory discovery is separately non-routable because MIC, complete page cost and operation cost are unresolved. |
| Tiingo OHLCV, current price, profile and search | Held before transport: daily and rolling-hour account usage baselines were unknown at preflight. No current-source data request or account refresh was made. |

CTA Plan and Nasdaq directory operations were admitted by this preflight; their
prior shortfall is no longer current. FMP is configured as Basic/free and passed
the new selected-plan admission control. A second exact 23-provider selection
preflight at 04:51:14Z reported all manifest credentials present, clear
independent admission, zero provider HTTP requests, and no provider-selected
blocker. Its exact selection was Alpaca, Binance, Bybit xStocks, Coinbase,
CoinGecko, CTA Plan, SEC EDGAR, EODHD, Finnhub, FINRA, FINRA OTC Directory,
FMP, FRED, Gate TradFi, Kraken, Kraken xStocks, MarketData.app, Massive,
Nasdaq, OpenFIGI, Robinhood Tokens, Twelve Data, and xStocks. This confirms
that the four excluded providers do not prevent testing the other 23; it is
still preflight rather than evidence of successful data requests. Each
manifest's eventual pass/fail/skip, case, request/byte count, and exact staged
candidate receipt must be recorded after the bounded live run. Do not spend
quota on the four quarantined providers.

These are present operational holds, not accepted permanent omissions. Other
historical operation outcomes remain in `validation.jsonl` bound to their exact
source. For context: CoinGecko Demo `/key`, Finnhub free stock candles, and FMP
Basic `stable/stock-list` returned expected entitlement denials during their
historical probes. Tradier, IBKR and Ondo remain explicit user deferrals. FINRA
async result download remains unavailable until complete streamed persistence
and measured-byte admission are proven; rows must never be truncated or
discarded. No provider has been activated or routed through paid credentials.

## Current live operation inventory

The 23 manifests admitted by preflight completed against staged tree
`592261aa...`; detailed case results, request/byte counts, run IDs, and
operation dispositions remain in the external redacted receipt file. “Passed”
means valid data was returned or an expected denial was asserted; it does not
mean every provider capability is available.

| Provider | Cases | HTTP requests | Tested result / caveat |
|---|---:|---:|---|
| Alpaca | 7 | 8 | History, usage, profile and corporate actions passed. |
| Binance | 3 | 6 | Passed. |
| Bybit xStocks | 2 | 5 | Public tokenized reads passed; restricted deployment-egress policy remains no-request pending separate evidence. |
| Coinbase | 2 | 4 | Passed. |
| CoinGecko | 3 | 4 | Passed; `/key` usage is Pro-only, so Demo usage is tracked in the durable app ledger. |
| CTA Plan | 1 | 2 | Complete daily file read passed. |
| SEC EDGAR | 5 | 8 | Issuer/profile/facts/events reads passed. |
| EODHD | 4 | 8 | Passed; profile returned expected 403 entitlement denial. |
| Finnhub | 2 | 8 | Passed; stock candles returned expected 403 and remain unavailable. |
| FINRA | 2 | 3 | Short-interest and Daily List passed; generic async dataset transport is not used by an admitted service. |
| FINRA OTC Directory | 1 | 6 | Official directory pagination passed. |
| FMP | 3 | 8 | Other reads passed; stock-list discovery returned expected 402 and remains disabled pending entitlement confirmation. |
| FRED | 2 | 2 | Current value and series reads passed. |
| Gate TradFi | 1 | 13 | Tokenized asset/order-book/price reads passed. |
| Kraken | 1 | 4 | Passed. |
| Kraken xStocks | 1 | 3 | Passed. |
| MarketData.app | 7 | 9 | Free Forever reads passed; unbounded response-priced option history was verified zero-request disabled. |
| Massive | 4 | 28 | Reference, corporate action, IPO pagination, and all 19 OTC pages passed; raw pages were persisted before advancing. |
| Nasdaq | 1 | 2 | Full bounded official-file pagination passed. |
| OpenFIGI | 3 | 3 | Identifier mapping/profile resolution passed. |
| Robinhood Tokens | 2 | 5 | Public asset, price and corporate-action reads passed. |
| Twelve Data | 2 | 6 | Usage/history/search/current-price reads passed. |
| xStocks | 3 | 6 | Asset, price, corporate-action and usage reads passed. |

Combined: 62/62 cases, 151 provider HTTP requests and 64,552,569 measured
response bytes. Offline verification made zero provider requests and correctly
returned incomplete because the four held providers have no successful
manifest receipts. The Marketstack monthly quota was reported exhausted in the
latest owner snapshot; no call was made. Quota ledgers, response archives and
generated browser artifacts were not reset or removed.

## Next gates

1. Keep the 23 receipts bound to staged tree `592261aa...`; do not rebind the
   historical `1afb896...` receipt or claim all 27 manifests passed. Do not
   call the four held providers until fresh quota/entitlement admission.
2. Await CI `38853327766` for `f614621...`; run and record exact-source CI on
   the final packet commit afterward.
3. Coordinate the three strict Study Lab screenshot failures with their
   frontend owner; this Provider branch must not edit frontend or sibling-owned
   files. The full functional browser matrix passed, but the full local profile
   is not green until the strict visual gate passes or its owner resolves it.
4. After required gates, submit the exact source to the coordinator for
   conditional acceptance. The coordinator owns acceptance and staging
   integration; this branch must not self-integrate.
5. Preserve the remaining roadmap: aggregate recurring-cost admission,
   complete US universe/lifecycle reconciliation, downstream consumer wiring,
   environment-specific secret-store onboarding, outstanding provider live
   manifests, expanded options/Greeks, and the separately authorized 30-day
   operational trial.
