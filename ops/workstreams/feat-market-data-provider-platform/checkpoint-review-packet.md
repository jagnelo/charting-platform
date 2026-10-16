# Provider integration checkpoint review packet

## Current source state and latest evidence — 2026-10-16

The coordinator's initial closure run [`38892600336`](https://github.com/jagnelo/charting-platform/actions/runs/38892600336)
was cancelled during E2E at case 82/260 when newer same-ref CI superseded it.
Replacement run [`38894083319`](https://github.com/jagnelo/charting-platform/actions/runs/38894083319)
passed standard CI on repair source `88032c10e7f4caf9351272f92155f9d0fe25b985`:
backend, frontend-unit, branch-declared, and Playwright E2E passed; 260 cases
were collected (151 passed, 109 skipped), with no failure/retry/flaky entry.
Exhaustive was skipped by feature-push conditions. The coordinator then merged
the approved repair into staging at
`0145b65992b8692ce69f82f804f83f6c8e551fea`. Its exact CI
[`38896729111`](https://github.com/jagnelo/charting-platform/actions/runs/38896729111)
completed successfully at 12:30Z. Backend job `116958868106`, Playwright E2E
job `116961537100`, and Exhaustive Integration Gate `116961536915` all
succeeded; Branch-declared Tests was skipped under this staging-run condition.
E2E collected all 260 cases (151 passed, 109 expected skips, zero failures or
test retries); CI keeps `failOnFlakyTests=true`. GitHub reports `staging` at
`0145b659...`. The coordinator has directly released this exact green
common-repair baseline for owner-branch reconciliation; it does not accept any
product checkpoint. Provider may merge only this released staging SHA after
finishing and pushing its current five-file receipt packet. Do not import the
fix branch directly or start another heavy profile before reconciliation.

Provider's real-main MarketData.app/Tiingo plan-admission correction is in
`d9104b3`; the entire `test_live_provider_runner.py` module passed 144/144 on
Provider HEAD at 11:56:22Z, including both paid-toggle settings and all
supported runner scopes with transport/lock negatives. No provider request or
quota spend occurred. Provider's own docs-tip CI `38886062018` remains red on
the separate F8u assertion; no Provider frontend edits are authorized.

Coordinator repair CI subsequently completed on
`fix/staging-popup-validation` commit `19a15268d2eae2c0bd60ead6ca1bca72a3d762d7`:
run [`38888544505`](https://github.com/jagnelo/charting-platform/actions/runs/38888544505)
has Backend, Frontend Unit, Branch-declared, and standard Playwright jobs all
successful; Playwright ran 260 selected cases with 151 passed and 109 skipped;
the F8u drag passed at case 128/260 and the next F8v case started at 129, with
no F8u retry. Exhaustive was skipped. This is not a
common staging release or Provider acceptance: GitHub still reports
`staging` at quality-held `5768bec4ae12fb06ecc37f06cf656387751eadaa`. Wait
for the coordinator's exact green staging release and do not import the repair
branch directly.

The coordinator's read-only host Docker run `df96f7324bb0` has since ended.
Its retained `/tmp/popup-full-profile.y0mPle/full-browser.sh` verifies the
browser-relevant app/frontend trees against pin
`d0fc689c91f2dedf8dcf42a17a802abda37883d3`, then runs the full functional
selection followed by `tc2000_visual.spec.ts` with `--retries=0`, one worker.
Both retained Playwright `.last-run.json` files say `status: passed` and list
no failed tests; the current repair worktree's app/frontend trees remain
identical to that pin. The container and owned stack are gone. The outer
driver's terminal exit code and exact passed/skipped case counts are not
preserved in the inspected files, so these are source-qualified Playwright
component passes, not a complete local-profile receipt or a common staging
release. The staging ref remains `5768bec4...`; Provider did not launch a
competing run.

The current clean, pushed documentation tip is `03bafd6f24b8d3d9d26c5d00d85cb4c92c01d1f3`, atop runner implementation `91164b355bf95da326063ce19caa33ed26003960`. Exact-source CI
[`38886062018`](https://github.com/jagnelo/charting-platform/actions/runs/38886062018)
is terminal but **not green**: backend, frontend-unit and branch-declared jobs
passed; standard E2E failed F8u after its retry (150 passed, 109 expected
skips, one failed); Exhaustive was skipped by the feature-push condition. F8u
(`frontend/tests/e2e/flows.spec.ts:4418`) drags an RSI plot into the Major US
benchmarks watchlist, then fails because the RSI header is not present
(`:4444`). This is a separate plot-to-watchlist behavior failure, not the
popup-close F8j cleanup race. No Provider frontend source changed. It is not
waived, and the earlier green runner-code CI `38881637606` does not replace
this failed exact-current-source CI.

The current seeded Noble strict visual component receipt remains 104/104 with
zero retries from `/tmp/provider-browser-20261016.gbn28D/visual-final-artifacts`.
It is an independently completed component run, not proof that the full local
profile passed; the associated functional run was red on F8j. At the
coordinator's 10:24Z review, its separate full profile had failed F8u before
the visual stage, staging `5768bec4...` remained quality-held, and the
coordinator owned the only heavy local validation slot. Do not launch another
full profile until the coordinator explicitly releases a repaired green common
staging baseline. The current branch has no fresh exact-source full-profile
pass, no current-source live receipt, and no Provider checkpoint acceptance.

The real-main MarketData.app/Tiingo runner correction is complete and
published: runner tests pass 145/145 including the established diagnostic
regression, both paid-toggle states, and no-lock/no-subprocess denials; no
provider HTTP or quota was used. The correction is at `91164b3`; hosted
run `38881637606` passed backend, frontend-unit, branch-declared and standard
E2E, with Exhaustive skipped. Its later docs tip's F8u result above is kept
separate. Existing operation holds and retained provider-response/quota data
are unchanged.

The coordinator's requested visual-run/slot handoff is already recorded in
the central review: the 104-check visual run terminated successfully and the
Provider slot was acknowledged as released at 09:23Z. No local browser process
is visible in this checkout now. Do not send another slot-release claim or
start a competing heavy run.

### Current coordination update — 2026-10-16 12:30Z

The staging Actions API now confirms run `38896729111` is terminal `success`
for exact staging SHA `0145b65992b8692ce69f82f804f83f6c8e551fea`; its
Exhaustive Integration Gate completed successfully. This resolves the CI-wait
condition, but not the coordinator-owned exact-baseline release. The fix branch
has not been imported into Provider. Provider remains at `03bafd6f...`; its
exact-source run `38886062018` is still red on F8u, separate from the popup
cleanup race. The published `91164b3` runner correction and the complete
`test_live_provider_runner.py` module remain green (144/144 on that exact tip);
the diagnostic compatibility regression was also included in the separate
145/145 composite focused run. No provider requests or quota use occurred.
Continue to preserve the 104/104 terminal visual component receipt. After the
coordinator releases `0145b659...`, reconcile only that exact staging source
into this branch, resolve the four shared-path semantics, and then rerun the
required exact-source full profile and hosted CI. Current-source live evidence
and complete review/acceptance remain outstanding.

### Historical runner-candidate evidence (not current full-profile acceptance)

The runner candidate first published as `d9104b369b421e80aa41281386bcdd275ae9a1d2`
had one exact-string compatibility assertion fail in CI `38880394731` (2,813
passed, 1 failed); backend admission behavior itself was correct. Restoring the
established diagnostic text produced pushed candidate
`91164b355bf95da326063ce19caa33ed26003960`, whose exact CI
[`38881637606`](https://github.com/jagnelo/charting-platform/actions/runs/38881637606)
completed successfully: backend, frontend-unit, branch-declared and standard
E2E jobs passed; Exhaustive skipped by the normal feature-push condition. The
affected regression plus the complete runner file also pass 145/145, and
Ruff/format/diff/workstream validation pass. This is code/CI evidence, not the
final checkpoint gate. No additional heavy local profile is running.

The shared staging baseline `5768bec4...` remains on QUALITY HOLD: its
Exhaustive test retried and then passed the F8j popup-close cleanup case. The
central coordinator owns the narrow repair on `fix/staging-popup-validation`
(`47e81ae5...`, clean metadata tip `0e68c021...`). Provider must not import
that unmerged branch or edit frontend.

Provider's runner change now evaluates MarketData.app and Tiingo effective-plan
admission in every supported actual `main()` selection path, before lock,
subprocess or transport. The actual runner unit file passed 144/144; both
`ALLOW_PAID_PROVIDER_ROUTING` values were covered. MarketData.app Free Forever
and expired-trial fallback, and Tiingo Starter, are positive plan controls;
paid/current-trial/unknown or unreviewed plans fail closed in the free-only
checkpoint. The EODHD exact zero-credit account-usage exception is unchanged.
Ruff, format and diff checks passed before hosted CI exposed the diagnostic
text expectation. After restoring the established text, the existing
diagnostic regression plus complete runner test file passed 145/145. These are
no-provider-transport tests, not live receipts.

The correctly seeded Playwright 1.62.1/Noble functional matrix ended
153passed/106expected-skipped/1failed, zero retries. The failure is the actual
F8j popup-close cleanup race (test declared at `flows.spec.ts:1465`, failing
cleanup click at line1490); do not waive it or confuse it with the separately
reported earlier F8n cursor assertion. All three
deterministic market-data fixture tests ran. The separate strict visual run
passed 104/104, zero retries, using the established read-only DejaVu mount and
unchanged references/tolerance. Functional, visual and earlier invalid-run
artifacts are retained under `/tmp/provider-browser-20261016.gbn28D/`; the
invalid upstream-mode attempt is not counted as evidence. Browser processes
are terminal and the heavy local validation slot is released to the
coordinator. Wait for its repaired green common staging baseline before any
new full profile. No provider requests or quota consumption occurred.

### Current provider-operation admission/disposition

- No operation gained new live authorization from this change. Current-source
  live receipts remain **none**; the 23-provider/62-case/151-request receipt
  set below remains bound only to its historical candidate and must not be
  rebound. Ordinary execution remains conditional on provider-specific
  capability, credential, account-plan, terms, fresh quota/cost/baseline and
  durable-ledger admission.
- MarketData.app is plan-routable only for the reviewed Free Forever tier (an
  expired configured trial resolves to its 100-credits/day tier). Active
  trial, paid Starter/Trader in this free-only checkpoint, mismatched plan and
  unknown plan are denied before external transport. Historical bounded free
  reads are not a new current-source live receipt. Unbounded response-priced
  option-history queries remain disabled because no finite request cost was
  admitted.
- Tiingo's reviewed Starter plan is plan-routable, but the provider remains
  operationally held pending a fresh account-wide hourly/daily/bandwidth
  baseline and quota admission. Power/paid, custom and unknown plans are
  denied in this checkpoint. This runner change consumed no Tiingo quota.
- Alpha Vantage remains held for insufficient daily headroom; Dinari Sandbox
  remains held for incomplete reviewed reset and per-operation cost evidence;
  Marketstack remains held after its reported monthly quota exhaustion and
  unresolved directory page/MIC/cost contract. No call was made to any held
  provider. These hold reasons are not generalized defaults.
- Prior reviewed-free manifest evidence for other providers remains useful only
  for the exact historical source and operation. Preserve established
  no-route/disabled cases: CoinGecko Demo `/key` (Pro-only), Finnhub free stock
  candles and FMP Basic stock-list discovery (observed entitlement denials),
  FINRA generic asynchronous transport without an admitted dataset consumer,
  restricted Bybit xStocks deployment egress, and user-deferred Tradier, IBKR
  and Ondo. EODHD's `fetch_account_usage` is a narrowly reviewed
  zero-daily-credit bootstrap with the separate request-rate charge; it is not
  a provider-wide paid-plan exception.
- Provider and downstream full-roadmap gaps remain explicit: complete NMS/OTC
  lifecycle reconciliation, aggregate recurring-cost admission, consumer
  adapter wiring, target-specific CI/deployment secret stores, remaining
  provider live manifests, broader options/Greeks and any separately
  authorized operational trial. None is silently marked complete by the
  runner or browser tests.

Status as of 2026-10-16 07:12Z: exact candidate `0111cc698ad8c03220b60725bdc2df68195d96e8`
is clean and pushed. Its current-source full local profile passed workstream,
dependency/lock, migration-head, lint/type, backend (2,796 unit plus 395
PostgreSQL/Redis integration tests; 82% combined coverage), frontend-unit/build,
Compose, research-runner, and isolated stack-health stages. Migration
compatibility correctly skipped because no migration files changed. The stock
host E2E wrapper then stopped before assertions on EACCES in existing
Docker-owned Playwright report directories. The same functional 260-case suite
was run with output redirected to `/tmp`: 151 passed, 109 skipped, zero failed
or retried. The pinned Playwright 1.62.1/Noble strict visual suite passed
101/104; the three Study Lab failures are unchanged from prior candidates
(~1.0% versus the 0.5% threshold). Exact-source GitHub CI run
[`38857046752`](https://github.com/jagnelo/charting-platform/actions/runs/38857046752)
completed successfully on this SHA: backend, frontend-unit, branch-declared,
and E2E jobs passed; the Exhaustive Integration Gate was skipped for a feature
branch push. Therefore this packet is not yet ready for conditional acceptance
while strict visual parity remains red. The new runtime correction passes the
complete provider-runtime unit file (78/78) and FMP runner admission cases
(13/13), with zero provider HTTP calls. Twenty-three individually admitted
provider manifests passed 62/62 cases on earlier staged tree
`592261aaef97a9ba2d3b3d6c818720eadd630abc`, with 151 requests and 64,552,569
measured response bytes. Do not rebind those receipts to the new code tree or
claim full 27-provider live acceptance. Provider-owned frontend files remain
unchanged. Conditional acceptance is coordinator-owned after required
contracts and tests pass. The declared current-source full-stack profile has
now run; its standard wrapper stopped at the known artifact-permission issue,
then the functional suite was run directly and the strict pinned visual suite
completed with three existing Study Lab failures. Exact-source CI is green as
listed above. The released common-repair baseline `82d881e76be8de538abb6ec5c454d96afe0ee56a`
is already an ancestor of this branch. This packet does not authorize provider activation,
paid routing, deployment, the 30-day operational trial, or feature-agent
staging integration. The complete roadmap remains open.

The human's conditional checkpoint-acceptance delegation (timestamp supplied
as `22:55Z`) is recorded in `plan.yaml` and `handoff.md`: “Yes—approve that
initial scope and handle checkpoint acceptance.” The coordinator may accept
and merge the four checkpoints only after required cross-feature contracts and
full tests pass, using verified free operations and keeping held, unreviewed,
paid/trial and unsafe operations disabled. This is not acceptance of this exact
source and does not waive validation, authorize this feature agent to
integrate, permit deployment/paid/trial activation, or allow cleanup.

## Exact-source evidence boundary

The detailed records below are historical and remain bound to their named
candidate SHAs. The current runner code is at `91164b355bf95da326063ce19caa33ed26003960`,
and current packet/docs tip is `03bafd6f24b8d3d9d26c5d00d85cb4c92c01d1f3`.
The 2026-10-16 10:57Z exact-current-source CI disposition above supersedes any
older wording below that called a different SHA current. Provider-owned
frontend files remain unchanged.
- On the current candidate, the full local profile passed dependency/lock checks,
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
  configured 260-case Playwright matrix was run on this source against the
  isolated branch stack, with provider egress denied and artifacts under
  `/tmp/provider-playwright-0111cc`: 151 passed, 109 expected skips, zero
  failed, zero retries. This is the current-source run; earlier counts below
  are historical only.
- The full profile's separate strict visual-parity stage was run on this source
  with its normal 104 cases and strict board-parity flag:
  `/tmp/provider-visual-pinned.EV7ZKJ/results-seeded`; 101 passed, 3 failed,
  zero retries. Failures are `Study Lab structured-result gap` at 1080p/100%
  (1.0% pixel difference, above the 0.5% limit), and `Study Lab sandbox-error
  gap` at 1080p/100% and 1080p/125% (about 1.0% each). Other viewport cases
  passed. These are frontend snapshot failures outside Provider ownership; no
  frontend source or snapshots were changed.
- The first standard-profile attempt's cleanup removed four newly created,
  branch-scoped test volumes and four project-scoped test images. It did not
  target persistent application volumes, provider quota ledgers, response
  archives, or external data. A second isolated test stack was recreated and
  stopped without `down -v`; its four fresh test volumes and browser artifacts
  remain. Provider egress was denied throughout; no provider HTTP requests
  were made. This cleanup incident and recovery are recorded in the handoff.
- Exact-source feature-branch CI run `38857046752` is green for
  `0111cc698ad8c03220b60725bdc2df68195d96e8`; its required jobs passed and the
  Exhaustive Integration Gate was skipped by the feature-push workflow
  condition. Older source-bound runs are historical only.
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
| ICP2 — provider governance | Shared capability, entitlement, routing and durable multidimensional quota contracts are tested. `PROVIDER_FREE_ONLY_CHECKPOINT=true` denies reviewed paid market-data routes regardless of `ALLOW_PAID_PROVIDER_ROUTING`; trials are denied. Unreviewed market-data routes are denied except the exact reviewed-safe EODHD `/api/user` bootstrap: HTTPS evidence, exact `fetch_account_usage` operation, reconciled `calls_per_day`, explicit zero daily-credit operation cost; `requests_per_minute` is still reserved. Candidate selection exposes only this operation to strict admission. FMP/Tiingo legacy seed labels now refresh to the configured account plan; a genuine API-patched revision is preserved, and plan/config mismatches fail closed. Execution-level tests prove no transport callback under either paid-toggle state. MarketData.app `/user/` is not exempt. | The aggregate 20 EUR/USD-equivalent recurring-cost ceiling is not implemented; it remains Provider roadmap work and is not needed for this free-only checkpoint. ETF owns its consumer bridge and real request/page/retry accounting after Provider staging. No invented FX or ETF-only ledger. |
| ICP3 — series, coverage and refresh | Series/provenance, gap planning, session-aware freshness, refresh coalescing/leases, and explicit partial coverage are exercised by backend unit/integration and Strategy Lab tests. Full local backend gate and exact-source hosted backend job passed. | After Provider staging, consumers verify stale, partial, missing, and unavailable states remain distinct and do not trigger hidden provider requests. Downstream owners: ETF, TC2000, Strategy Lab. |
| ICP4 — provider operations | Fresh durable no-transport preflight admitted 23 manifests; exact staged-tree slices passed 62/62 cases, 151 requests, and 64,552,569 response bytes. The verifier confirms those 23 against tree `592261aa...` and reports `live_acceptance=false` because four held providers have no successful manifest receipt. | Keep Alpha Vantage, Dinari, Marketstack and Tiingo held with their exact reasons below. No quota was spent on these four. Their preflight and existing zero-call tests are separate from successful live evidence. Historical 20/27 evidence stays bound to `1afb896...`; it is not rebound. |
| ICP5 — migrations, startup and secrets | Local secret/config boundary and trusted backend/worker wiring have tests. Current source changes no migrations; migration-compatibility correctly skipped relative to `32e9109`. Prior reported 50-migration fresh-install/existing-database equivalence and health check remain historical, not a new receipt bound to `0111cc6`. Exact-source backend and branch CI are green. | GitHub/RPi/deployment secret stores are target onboarding requirements before those targets are used, not pre-Provider integration requirements. No deployment readiness is claimed. |
| ICP6 — consumers | Producer success/unavailable behavior and callable contract are tested. ETF can call `app.services.provider_runtime.execute_provider_call(db, capability, operation, *, provider_name, operation_cost_overrides, invoke, ...)`; denied admission prevents `invoke`. `provider_entitlement_admission(entitlement)` returns `allowed`, `reason_code`, `configured_plan`, `is_free`, `checkpoint_free_only`, and `basis`; provider status exposes this as `entitlement_admission`. This is routing eligibility, not aggregate subscription-cost admission. Success/unavailable examples exist in ETF coverage and Strategy evaluation/coverage tests. | Before Provider staging, deliver the producer contract and named owners only; actual ETF/TC2000/Strategy adapter wiring and consumer-specific reconciliation happen after Provider is green in staging. ETF owns holdings adapter/bridge plus page/retry accounting; TC2000 and Strategy own their consumer wiring. |
| ICP7 — reviewable source | Clean pushed source `0111cc6`; focused regressions 78/78 provider-runtime and 13/13 FMP runner admission; local backend 2,796 unit + 395 integration, 82%; exact-source CI `38857046752` success for all required jobs including E2E; functional browser 151 passed/109 skipped/0 failed/0 retries. Released common-repair staging `82d881e7` is already in ancestry. | The stock full-profile E2E wrapper stopped before assertions due existing report-directory permissions; manual equivalent ran successfully. Strict pinned visual is 101/104 with three Study Lab snapshot mismatches (~1% vs 0.5%), so the declared profile is not fully green. The coordinator has not accepted this source; this branch must not edit frontend. |

### Coordinator ICP2 review correction (hosted CI validated; local full-profile follow-up remains)

The coordinator identified an unsafe inference: an affirmative `is_free` flag
plus an arbitrary non-empty plan label was not sufficient evidence that the
provider plan had been reviewed. The current correction requires either an
exact current provider/capability seed-plan match with matching free/paid
classification, or an explicit reviewed label. It adds status, resolver, and
executor no-transport tests for `unknown`, `unknown-plan`, `mystery-plan`, and
`unreviewed` with `is_free=True`, both `ALLOW_PAID_PROVIDER_ROUTING` values,
and a reviewed-free positive control. The narrow EODHD zero-credit account
usage exception remains separately tested. The full provider-runtime unit file
passed 79/79 locally. Exact fix source
`9a0738b138786bdcf74f7efe6485ac784bf8843b` passed hosted CI
[`38870197964`](https://github.com/jagnelo/charting-platform/actions/runs/38870197964):
backend, frontend-unit, branch-declared, and E2E succeeded; Exhaustive
Integration Gate was skipped for a feature push. This closes the ICP2
correction's code/CI evidence, not the broader checkpoint's full local-profile
or strict visual gate. No provider HTTP call or quota use occurred.

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

## Current routing inventory (code posture, not a live receipt)

“Eligible” means existing routing/admission rules permit an operation only
when its reviewed free entitlement and current durable quota admission pass.
It does not mean a current-source live request was made; none was. Historical
success is shown separately below and remains bound to its recorded source.

| Current disposition | Provider operations / limits |
|---|---|
| Eligible under verified-free admission, subject to per-operation quota and entitlement checks | Alpaca, Binance, Bybit xStocks, Coinbase, CoinGecko, CTA Plan, SEC EDGAR, EODHD, Finnhub, FINRA, FINRA OTC Directory, FMP, FRED, Gate TradFi, Kraken, Kraken xStocks, MarketData.app, Massive, Nasdaq, OpenFIGI, Robinhood Tokens, Twelve Data, and xStocks; only registered capabilities/operations may route. Historical per-provider tested operation summaries are in the following table. |
| Operation-only reviewed-safe exception | EODHD `fetch_account_usage` at `/api/user`, strictly to observe `calls_per_day` when HTTPS response evidence is valid and declared operation cost for daily credits is explicitly zero. Requests-per-minute remains reserved and charged. This does not review or imply a free EODHD subscription plan and does not enable other unreviewed EODHD operations. |
| Held before transport by current known quota or baseline | Alpha Vantage full manifest (`discover_universe_page` reservation exceeds remaining daily headroom); Marketstack OHLCV (reported monthly quota exhausted / insufficient reservation headroom); Tiingo OHLCV, current price, profile, and search (fresh current daily/hourly usage baseline required). No call is authorized while held. |
| Non-routable pending complete account/cost contract | Dinari Sandbox tokenized asset, price/quote/history, corporate action, dividend, split, and news operations; complete reviewed reset/quota profile and worst-case per-operation cost map are absent. |
| Non-routable pending unresolved discovery bounds | Marketstack directory discovery: venue/MIC, full page count/cost, and operation cost are unresolved. |
| Explicitly unavailable or deferred | CoinGecko Demo `/key` usage endpoint (Pro-only); Finnhub free stock candles (historical entitlement denial); FMP Basic `stable/stock-list` discovery (historical entitlement denial); FINRA async result download (not admitted until full streamed persistence and measured-byte admission are proven); Tradier, IBKR, and Ondo (user-deferred). |
| Always denied by this checkpoint scope | Paid or trial subscription routing, any provider entitlement whose plan/cost review is unknown, and any operation with unknown quota/cost/reset semantics. `ALLOW_PAID_PROVIDER_ROUTING` cannot override `PROVIDER_FREE_ONLY_CHECKPOINT=true`. |

This inventory describes code policy, not a statement that every eligible
operation succeeded live on candidate `0111cc6`. Any newer quota observation or
source change requires fresh admission and a newly source-bound receipt; held
usage was not reset or spent to make this packet green.

## Previously tested operation inventory (historical exact-source receipts)

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

1. Keep the 23 receipts bound to staged tree `592261aa...`; they are historical
   proof for their 23 provider manifests, not live results for the current
   source. The separate historical `1afb896...` receipt also remains bound to
   its source. No request was repeated for this correction.
2. Resolve the three existing strict Study Lab visual mismatches with their
   frontend owner; do not edit frontend or sibling-owned files here. Rerun the
   declared full profile after that owner publishes an eligible repair or the
   coordinator confirms the accepted disposition.
3. Refresh this packet and validation journal after any source change; run
   exact-source CI for the resulting candidate. Current CI is green, but the
   full local profile remains red due the three visual mismatches.
4. Publish the explicit enabled-operation versus disabled/held inventory for
   final review. Keep EODHD's tested zero-billing operation-level exception
   distinct from any unreviewed subscription plan; do not infer that a provider
   account plan is free merely because one endpoint is non-billing.
5. Submit the exact clean source and evidence to the coordinator for delegated
   conditional acceptance. The coordinator owns acceptance and staging
   integration; this branch must not self-integrate.
6. Preserve the remaining roadmap: aggregate recurring-cost admission,
   complete US universe/lifecycle reconciliation, downstream consumer wiring,
   environment-specific secret-store onboarding, outstanding provider live
   manifests, expanded options/Greeks, and the separately authorized 30-day
   operational trial.

## Current-source operation disposition

- No provider HTTP request or quota spend occurred during the FMP/Tiingo plan
  correction. The current source has no live success receipt for a provider
  operation; the 23-provider results above stay bound to staged tree `592261aa`.
- The 23 providers previously admitted by exact quota/entitlement preflight
  remain eligible only within their reviewed-free operation contracts. Their
  recorded manifest results and individual operation caveats are listed above;
  they are not a claim that every provider capability is usable.
- Continue to hold Alpha Vantage (insufficient daily reservation headroom),
  Dinari Sandbox (account-reviewed quota/reset and per-operation cost profile
  incomplete), Marketstack OHLCV (monthly allowance exhausted / insufficient
  headroom; directory MIC/page/cost unresolved), and Tiingo (fresh external
  daily/hourly usage baseline required before transport). No calls are
  authorized by this packet to those four.
- Within otherwise admitted providers, preserve the recorded no-route
  dispositions: CoinGecko Demo `/key` is Pro-only; Finnhub free stock candles
  and FMP Basic stock-list discovery returned entitlement denials; unbounded
  response-priced MarketData.app option history remains zero-request; FINRA's
  generic async dataset transport is not an admitted operation; restricted
  Bybit xStocks deployment egress remains no-request pending its separate
  evidence. Tradier, IBKR and Ondo remain explicit user deferrals.
- The EODHD `/api/user` account-usage bootstrap is a separately reviewed
  zero-billing operation, not an unreviewed subscription-plan admission. Only
  the exact `fetch_account_usage` operation with HTTPS evidence, reconciled
  `calls_per_day`, explicit zero daily-credit cost and the separately reserved
  request-rate cost can be considered for that bootstrap. Positive behavior is
  stub-tested; paid, unknown and trial cases are denied before callback under
  both paid-routing flag states. This correction adds no provider HTTP calls.
