# Provider integration checkpoint review packet

## Superseding current Provider-owned continuation status — 2026-10-16 18:38Z

The local worktree is a dirty candidate based on synchronized `ba06bdc6` and
adds Provider-wide recurring-subscription cost governance. Focused admin-router,
service, and migration tests pass `22/22`; the isolated PostgreSQL test passes
`1/1`, including concurrent first-budget configuration, near-ceiling admission,
and fresh-session durability. The exact
fresh-install/existing-database migration gate passed against base `ba06bdc6`:
cost schemas (columns, nullability, named constraints/indexes) match, existing
fail-closed provider quota data is preserved, and the previous application
health check returned 200. The gate now makes its legacy quota fixture depend
on the previous schema and compares the additive cost schema; intermediate
fixture/comparison failures were repaired without relaxing the assertions.
After changing audit revision foreign keys to `RESTRICT`, the migration gate
was rerun at 18:38Z and passed again: provider quota schema/fail-closed data,
recurring-cost schema on fresh and upgrade paths, and previous-release `/health`
200. This remains dirty-candidate migration evidence, not exact-source CI.

Cost governance is full-roadmap continuation, not a prerequisite or substitute
for the free-only ICP2 checkpoint: the budget has no implicit configured row,
unknown costs/currencies fail closed, and cost admission never authorizes paid
provider activation. Concurrent budget configuration and commitment admission
now share a transaction-scoped PostgreSQL advisory lock; test account
environment names normalize case to avoid duplicate commitments. The reviewed
budget currency/equivalence policy still requires operator configuration; no
FX rate is inferred. No admin budget was configured and no subscription or
provider was activated. The dirty candidate has not been committed or hosted-CI
validated. Base commit `ba06bdc6` now has exact Actions run `38943410344`
terminal green: Backend, Frontend Unit, Branch-declared, and E2E all succeeded;
E2E was 151 passed/109 skipped with zero retries/flakes/failures, while
Exhaustive was skipped under branch policy. This base CI does not validate the
dirty candidate. The GET status, PUT budget, and POST commitment producer contract
and ETF/TC/Strategy ownership remainder are reflected in the plan; no sibling
consumer wiring was performed.

The Provider full browser result at `1236a367` remains red (256 passed, 2
expected live skips, F9e/F8s failed; 104 visuals passed). TC owns those fixes.
No Provider browser rerun is allowed until the coordinator releases a
synchronized staging repair. No provider HTTP/quota spend, staging or sibling
mutation, data reset, paid/trial activation, deployment, or cleanup occurred.

This candidate is not yet a full ICP2/ICP6 acceptance packet: exact-source CI,
the normal full local profile, current live-operation dispositions, and final
source-bound verification remain open.

## Superseding current-source status — 2026-10-16 16:00Z

Provider source is `1236a367a1d81fba69bb85496e12a56ec22c9f56` and exact-source
CI run `38902818604` passed required standard jobs; Exhaustive was skipped.
This is not checkpoint acceptance. The seeded 260-case Playwright selection
completed with 256 passed, 2 failed (`F9e-easyscan-builder-keyboard` and
`F8s-family-matrix`), and 2 expected live-canonical skips
(`F8e.live-membership`, `F8e.live-sector-drilldown`). All 104 strict visual
cases passed at the unchanged 0.5% tolerance. Both failed cases then passed a
focused 2-case rerun with no retries, provider egress denied, and no provider
HTTP/quota spend; this is diagnostic evidence only and does not erase the full
selection's red result.

At 16:29Z the same two focused tests were rerun in the preserved isolated
stack: 2/2 passed, zero retries/skips, 39.1 seconds, zero provider HTTP/quota
spend. The TC owner has both browser fixes; its exact run `38930779878` had
Branch-declared, Frontend Unit, and Backend green while Playwright E2E remained
in progress at the latest coordinator update. Do not rerun the Provider matrix
until that run is terminal and the coordinator releases a synchronized staging
repair.

The F8s test-fixture overlap is confirmed: the later broad market-group route
matches the `us-benchmarks` path and its `route.continue()` miss reaches the
local backend instead of the earlier intended fixture. Its failure observed a
Russell 1000 selector while the latest intercepted POST still carried SP1500,
indicating an uncorrelated/stale request observation, not a product identity
failure. F9e's final snapshot retained the Add tool menu with no EasyScan panel;
the readiness/active-tab gate and non-awaited async click are plausible timing
factors, but the artifact does not prove the internal guard state. Both items
are TC/frontend-owned; no frontend source was changed. See the dated handoff
for exact artifacts and a test-only repair direction. The browser runner and
isolated test stack remain preserved; no container/data cleanup occurred.
Continue Provider ICP2/ICP6 work and keep all held/unknown/paid/trial provider
operations disabled. Full Provider checkpoint acceptance remains open.

## Superseding current-source status — 2026-10-16 12:45Z

This section supersedes earlier “current” summaries below; older entries are
historical receipts and remain source-bound. The explicitly released common
staging repair `0145b65992b8692ce69f82f804f83f6c8e551fea` was merged into this
Provider branch as `ca86eaf147f391829fb9f060b43633b1bb8b79b2`. The five-file
Provider receipt packet was committed as `837273587f865111ef5b7834571d86b4a8791bda`;
the exact merge and its bounded-check record were then committed and pushed as
`081fd6dff82cc27862a6a86d8c59ff0fcb25aefe`. The worktree is clean and the
local branch matches `origin/feat/market-data-provider-platform`.

Bounded tests on merge source `ca86eaf` passed: research runner 106/106 with
numerical-library threads capped at one, staging workflow 64/64, inherited
popup/flaky-policy frontend units 10/10, Provider live-runner unit tests
144/144, and all 34 workstream records. `git diff --check` passed. These are
not the required full local profile or current-source live acceptance. No
provider HTTP requests or quota spend occurred. The uncapped research-runner
attempt terminated during statsmodels OLS without a pytest summary; cause is
unknown. The unchanged full test file passed with thread caps and no assertion,
test, or product behavior was weakened.

Exact-source GitHub CI run
[`38902425042`](https://github.com/jagnelo/charting-platform/actions/runs/38902425042)
for pushed source `081fd6d` was pending at 12:42Z. Prior CI `38901742165` is
bound to `8372735`, not this tip. After CI, run a no-transport durable quota
preflight and inspect only operations currently admitted with safe headroom;
do not refresh or replay held calls. Continue ICP2 aggregate cost-governance
and ICP6 consumer contract evidence. Full local profile, admitted current-tip
live evidence, complete producer/consumer packet, and coordinator's conditional
technical acceptance remain open. No paid/trial activation, deployment,
promotion, cleanup, or feature acceptance is authorized or implied. The full
roadmap remains intact.

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
`0145b659...`. The coordinator directly released this exact green common-repair
baseline for owner-branch reconciliation; it does not accept any product
checkpoint. Provider first pushed its five-file receipt packet as
`837273587f865111ef5b7834571d86b4a8791bda`, then merged only this staging SHA
as `ca86eaf147f391829fb9f060b43633b1bb8b79b2`. Do not import the fix branch
directly.

### Current Provider source after staging reconciliation — 2026-10-16 12:40Z

The current local Provider tip is merge commit
`ca86eaf147f391829fb9f060b43633b1bb8b79b2`; its parent feature tip is the
pushed receipt commit `837273587f865111ef5b7834571d86b4a8791bda`, and its
staging parent is the released `0145b65992b8692ce69f82f804f83f6c8e551fea`.
The merge completed without textual conflicts across four shared paths and
their behavior was inspected. The worktree is clean; the merge commit has not
yet been pushed. On this exact local tree, focused checks passed: the complete
research-runner file 106/106 using one numerical-library thread, staging
workflow tests 64/64, inherited popup/flaky-policy frontend unit tests 10/10,
and the Provider real-main live-runner admission module 144/144. No provider
HTTP requests or quota use occurred. The uncapped research-runner test process
terminated during the statsmodels OLS case with no pytest summary; its cause is
unknown. The unchanged full file passed with `OPENBLAS_NUM_THREADS=1
OMP_NUM_THREADS=1`; this constrains numerical parallelism only and preserves
all test/resource guards. The first frontend unit command used the wrong cwd
and failed on a relative source path; rerun from `frontend/` passed 10/10.

Exact-source hosted CI, the normal full local profile and current-source live
acceptance remain pending on this merged candidate. Earlier exact CI
`38886062018` was red at pre-reconciliation SHA `03bafd6f...` on F8u; it is not
evidence about the current tip. The staged repair's green run is evidence for
staging SHA `0145b659...`, not for this combined Provider tip. After pushing
this merge, inspect its exact branch CI, run the admitted no-transport quota
preflight, then perform only operations whose current durable usage admission
is safe. Continue the free-only boundary, aggregate cost-governance remainder,
and producer/consumer map. Do not refresh data or spend quotas merely for
freshness; all held/paid/trial/unknown operations remain excluded. Provider
checkpoint acceptance and full-roadmap completion remain pending.

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
| ICP2 — provider governance | Shared capability, entitlement, routing and durable multidimensional quota contracts are tested. `PROVIDER_FREE_ONLY_CHECKPOINT=true` denies reviewed paid market-data routes regardless of `ALLOW_PAID_PROVIDER_ROUTING`; trials are denied. Unreviewed market-data routes are denied except the exact reviewed-safe EODHD `/api/user` bootstrap: HTTPS evidence, exact `fetch_account_usage` operation, reconciled `calls_per_day`, explicit zero daily-credit operation cost; `requests_per_minute` is still reserved. Candidate selection exposes only this operation to strict admission. FMP/Tiingo legacy seed labels now refresh to the configured account plan; a genuine API-patched revision is preserved, and plan/config mismatches fail closed. Execution-level tests prove no transport callback under either paid-toggle state. MarketData.app `/user/` is not exempt. | Shared cost admission now has a Provider-owned DB model/service and admin API, but is full-roadmap work—not an ICP2 free-only checkpoint prerequisite and not paid-route authorization. It requires explicit reviewed budget/evidence configuration; same-currency only, no invented FX. Exact-source PostgreSQL concurrency/restart and full migration-equivalence tests remain. ETF owns post-staging consumer bridge and real request/page/retry accounting; no ETF-only ledger. |
| ICP3 — series, coverage and refresh | Series/provenance, gap planning, session-aware freshness, refresh coalescing/leases, and explicit partial coverage are exercised by backend unit/integration and Strategy Lab tests. Full local backend gate and exact-source hosted backend job passed. | After Provider staging, consumers verify stale, partial, missing, and unavailable states remain distinct and do not trigger hidden provider requests. Downstream owners: ETF, TC2000, Strategy Lab. |
| ICP4 — provider operations | Fresh durable no-transport preflight admitted 23 manifests; exact staged-tree slices passed 62/62 cases, 151 requests, and 64,552,569 response bytes. The verifier confirms those 23 against tree `592261aa...` and reports `live_acceptance=false` because four held providers have no successful manifest receipt. | Keep Alpha Vantage, Dinari, Marketstack and Tiingo held with their exact reasons below. No quota was spent on these four. Their preflight and existing zero-call tests are separate from successful live evidence. Historical 20/27 evidence stays bound to `1afb896...`; it is not rebound. |
| ICP5 — migrations, startup and secrets | The dirty candidate adds `c5d6e7f8a9b0` for recurring-cost governance. Its PostgreSQL migration-compatibility gate passed against exact base `ba06bdc6`: new cost table schema/index/constraint equivalence, existing fail-closed quota state, and previous-release `/health 200`. SQLite migration smoke also passes. This gate is worktree-candidate evidence, not yet clean exact-source CI. | Run the full normal local profile and exact-source CI after freezing a clean candidate. GitHub/RPi/deployment secret stores remain target onboarding requirements before those targets are used, not pre-Provider integration prerequisites. No deployment readiness is claimed. |
| ICP6 — consumers | Producer success/unavailable behavior and callable contract are tested. `execute_provider_call(...)` is async but its `invoke(provider, provider_symbol)` argument must be synchronous; the runtime offloads it to a worker thread with copied telemetry context and returns `ProviderExecutionResult(provider_name, data_source, policy, health, result, response_payloads)`. It does not await async callbacks. Unknown/exhausted quota is denied before `invoke`; no usable provider data raises `ProviderNoDataError`. `GET /api/v1/ohlcv/{symbol}/D1?local_only=true` returns retained local bars or `200 []` when none exist, without provider hydration; this preserves the collection endpoint's existing response shape. A non-local provider request that exhausts usable data has the separately tested `404` `detail` response. | Producer success shape, no-data behavior, and exact local-only empty-result semantics are now explicit in `plan.yaml` and runtime/router tests. Before Provider staging, name downstream owners/remainders only; actual ETF/TC2000/Strategy adapter wiring and consumer-specific reconciliation happen after Provider is green in staging. ETF owns holdings bridge; TC2000 and Strategy own their consumer wiring. |
| ICP7 — reviewable source | Last clean pushed source is `ba06bdc6`; its exact run `38943410344` has Backend, Frontend Unit and Branch-declared green, Exhaustive skipped, and E2E still in progress at this update. These results predate the dirty cost-governance candidate. | Commit/push a clean coherent candidate, then require exact-source CI and normal full local profile. The Provider full browser result remains red at `1236a367` (TC-owned F9e/F8s; 104 visual cases passed). No product checkpoint is accepted; do not edit frontend or self-integrate. |

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

## 2026-10-16 16:47Z — current coordinator state and ICP2/ICP6 audit

- Provider source remains `1236a367a1d81fba69bb85496e12a56ec22c9f56`, with
  dirty, owner-scoped test/workstream follow-up. Exact hosted run `38902818604`
  passed required standard CI jobs but skipped Exhaustive; it is not checkpoint
  acceptance. The exact seeded local 260-case browser result remains red at
  256 passed, F9e and F8s failed, and 2 expected live skips; 104/104 visuals
  passed. Focused reruns are diagnostic only and do not clear those failures.
- TC owns both browser fixes. Exact TC run `38930779878` on source
  `0c7bc1b8ce76a9761e4c20d02b4bb59d1591920f` is terminal success for
  Branch-declared, Frontend Unit, Backend, and Playwright E2E; Exhaustive was
  skipped. The staging ref remains `0145b65992b8692ce69f82f804f83f6c8e551fea`
  and no synchronized repair release was found. Do not rerun Provider browser
  validation until the coordinator releases the synchronized repair.
- ICP2 audit: current `ProviderEntitlement`/revision lacks provider-account
  identity, recurring amount/currency/interval, and known post-trial price;
  `DataSource` is provider-scoped. Existing durable request/credit/byte/symbol
  usage accounting cannot safely enforce aggregate recurring subscription
  cost. The approved aggregate ceiling remains Provider-owned full-roadmap
  work requiring durable account-scoped commitments, auditable evidence,
  atomic admission, explicit monthly normalization, and reviewed FX policy
  (mixed currency denies absent one). No partial in-memory cost admission or
  invented conversion was added; this is distinct from the verified-free-only
  checkpoint boundary.
- ICP6 producer contract: success returns `ProviderExecutionResult` with
  provider, source, policy, health, value, and retained payloads; unknown or
  exhausted quota denies before the transport callback. Local-only empty
  OHLCV remains the tested `200 []` collection shape and proves no hydration;
  provider-backed `ProviderNoDataError` separately returns tested `404` detail.
  ETF owns its post-staging holdings bridge and request/page/retry accounting;
  TC2000 and Strategy Lab own their consumer wiring/reconciliation after
  Provider staging. No sibling adapter is claimed as wired here.
- The complete `backend/tests/unit/services/test_provider_runtime.py` module
  passed `79/79` on the dirty candidate in 107.67s. The two focused OHLCV router
  contract tests also passed; the earlier focused run covered these together
  with the strengthened runtime result-shape assertion. This is unit evidence,
  not the full local profile or checkpoint acceptance. The combined routing and
  provider policy/status API suites passed `43/43` in 17.50s. All 34 workstream
  records validate. The complete quota-contract unit module then passed
  `135/135` in 6.90s, covering provider-specific limits, reset semantics, and
  operation cost contracts. The durable quota coordinator module passed
  `64/64` in 6.74s, including restart/process-shared reservations, atomic
  multidimensional admission, baseline reconciliation, and retained quota
  evidence. The complete OHLCV router test module now passes `7/7`, including a
  newly added retained-bar success-shape assertion for consumers; `local_only`
  explicitly passes `allow_provider_fetch=false`. No provider HTTP/quota,
  browser run, staging/sibling edit,
  paid/trial activation, deployment, or data cleanup occurred. Full Provider
  checkpoint and all broader roadmap criteria remain open.

## 2026-10-16 17:00Z — consumer success and coverage-state fixtures strengthened

- ICP6 now names and tests both successful local consumer contracts: the
  retained OHLCV collection returns timestamp/OHLCV/VWAP/adjustment fields, and
  the coverage endpoint returns `status=ready`, exact covered bounds, zero
  missing slices, and `canonical_local_database` provenance for a fully
  retained range. `local_only=true` is asserted to disable provider hydration.
- At 17:00Z, read-only external recheck still showed TC run `38930779878`
  successful for required standard jobs (Exhaustive skipped), while staging
  remained `0145b65992b8692ce69f82f804f83f6c8e551fea`; no synchronized repair
  release was present. Provider browser remains held.
- The existing empty local `200 []`, partial range coverage, and provider-
  backed no-data `404` cases remain intact. Combined OHLCV/coverage router
  tests pass `12/12` on the dirty candidate. These are provider-neutral producer
  contracts, not provider live success, full-profile acceptance, or downstream
  feature wiring. No quota or external request was used.

## 2026-10-16 17:03Z — missing-coverage consumer contract completed

- Added a provider-neutral `status=missing` coverage response test for a range
  with no retained bars. It verifies the exact requested range is returned as
  one missing slice, with zero bars, null covered bounds, canonical-local
  provenance, and no provider field or provider routing.
- The complete coverage and OHLCV router test files pass `13/13` on the dirty
  candidate (9.55s); Ruff check and format pass. Together with the already
  tested `ready` and `partial` responses, this distinguishes ready, partial,
  and missing local-coverage states. The separate OHLCV contract preserves the
  retained-bar response shape and proves `local_only=true` disables hydration;
  empty local-only remains `200 []`, while provider-backed no-data remains
  `404`.
- This closes the Provider-owned producer-example gap for local OHLCV/coverage
  success and unavailable states. It does not claim live provider success or
  downstream adapter wiring: ETF, TC2000, and Strategy Lab retain the named
  post-staging consumer reconciliation and test ownership.
- ICP2 remains distinct: no aggregate recurring-subscription commitment model
  or admission interface has been implemented. The continuation must be
  account/environment scoped and durable; record plan, provider-account scope,
  exact recurring amount/currency/interval, effective state, evidence source
  and observation time, and known post-trial price. Unknown price, currency,
  interval, account scope, or stale/missing evidence must deny admission.
  Convert to a monthly equivalent only for explicitly supported intervals;
  mixed-currency totals remain denied absent a reviewed, timestamped FX policy.
  Atomic admission must include both existing active and proposed commitments,
  be separate from request-quota counters and the free-only checkpoint toggle,
  and must never itself authorize paid activation. No budget model or FX rate
  is inferred by this test-only continuation.
- No provider HTTP, quota spend, browser/full-stack run, staging/sibling edit,
  paid/trial activation, deployment, or data cleanup occurred.

## 2026-10-16 17:06Z — recurring-cost requirement promoted to roadmap criterion

- Added `AC-RECURRING-COST` to the preserved full-roadmap acceptance criteria
  and its disposition table. It explicitly requires durable monthly ceiling
  admission across active/proposed commitments, same-account cross-key
  deduplication, verified price/period/post-trial evidence, fail-closed
  unknowns and mixed currencies, atomic concurrent admission, restart
  durability, migration equivalence, and separation from paid-activation
  authority.
- Its current status is `not_started`: the free-only checkpoint route gate
  does not meet aggregate subscription-cost admission. This makes the gap
  visible to future workstream validation and prevents it being treated as
  delivered merely because quota accounting or free-only admission exists.
- `make branch-validate` passed all 34 records after this plan change. Only
  roadmap/workstream documentation changed; no provider runtime, browser,
  transport, quota, staging, sibling, or deployment state changed.

## 2026-10-16 17:11Z — exact pushed source contract suite

- Commit `51ebc7d45aa34d2e8790988778ee5e6eec14bdd7` is pushed to
  `origin/feat/market-data-provider-platform`; the local and remote-tracking
  refs were synchronized at this check. GitHub's combined commit-status API
  returned no legacy status entries, which is not evidence that Actions passed;
  exact Actions run status remains unverified.
- Against that exact committed source, the complete Provider runtime and
  coverage/OHLCV router selection passed `92/92` in 110.78s, with five
  third-party deprecation warnings. No provider HTTP, quota spend, browser, or
  Docker-backed test was part of this command.
- This confirms the bounded producer/runtime regressions on the published
  candidate. The prior full seeded browser result remains red at source
  `1236a367`; no full browser rerun is allowed until the coordinator publishes
  a synchronized repair baseline. The checkpoint remains unaccepted.

## 2026-10-16 17:15Z — exact-source routing and quota unit suites

- On exact pushed source `51ebc7d45aa34d2e8790988778ee5e6eec14bdd7`, the
  provider routing, provider status API, quota-contract, and durable quota
  coordinator unit suites passed `242/242` in 27.89s, with five dependency
  deprecation warnings. Combined with the earlier exact-source runtime and
  coverage/OHLCV selection, the bounded ICP2/ICP6 unit evidence on this SHA is
  `334/334`; these are separate successful invocations, not a full backend or
  integration profile.
- A read-only Docker inspection confirmed the assigned Provider validation
  stacks and TC stacks are still running. No heavy local full-stack/browser
  profile was started, and no containers or datasets were stopped or cleaned.
- GitHub commit-status lookup had no legacy status entries and the Actions run
  remains unverified. Do not treat these local unit suites as exact hosted CI,
  live-provider acceptance, or checkpoint acceptance. No provider calls or
  quota spend occurred.

- The `provider_execution` contract map now points to exact producer tests:
  transport success with `ProviderExecutionResult`, quota denial before the
  callback, unreviewed entitlement exclusion, and provider-backed no-data `404`.
  These tests all passed within the exact-source `334/334` bounded unit runs.

## 2026-10-16 17:27Z — current ICP2/ICP6 record and exact CI progress

- Provider branch HEAD and origin are synchronized at
  `51ebc7d45aa34d2e8790988778ee5e6eec14bdd7`. Exact Actions run
  `38937321525` has Backend, Frontend Unit, and Branch-declared jobs successful;
  E2E is still running while its stack starts, and Exhaustive is skipped by the
  feature-push workflow. This is not a terminal all-required-jobs result.
- TC's exact run `38930779878` is now terminal-success for Backend, Frontend
  Unit, Branch-declared, and Playwright E2E; Exhaustive was skipped. The
  coordinator's current staging ref remains
  `0145b65992b8692ce69f82f804f83f6c8e551fea`, so no synchronized TC repair has
  been released into staging. Provider's prior full seeded browser result
  stays red at `1236a367` (256 passed, 2 failed F9e/F8s, 2 expected live
  skips; strict visuals 104/104 passed). Do not rerun Provider browser tests
  until the coordinator releases synchronized staging repair; do not edit or
  duplicate TC-owned fixes.
- ICP6 contract examples now include the exact tested `ready` and `missing`
  coverage payload fields and the provider-backed no-data `404` shape. They are
  linked to `test_exposes_fully_covered_range_without_provider_routing`,
  `test_exposes_missing_range_without_provider_routing`, and
  `test_no_provider_data_returns_404`. These provider-neutral producer
  examples do not claim current-source provider HTTP success or downstream
  feature wiring; ETF owns its later holdings bridge, while TC2000 and Strategy
  Lab own their post-staging consumer reconciliation.
- Validation: `make branch-validate` passed all 34 records and
  `git diff --check` passed after the contract-example edit; plan SHA-256 is
  `593facb51ab0d34f8ecf6c025cf1d536bbfbdde956af5a2567624a49c77aa46b`.
  The exact-source bounded test evidence remains 334/334 on `51ebc7d`; no
  duplicate tests or browser/full-stack run were launched here.
- ICP2 recurring aggregate subscription-cost admission remains unimplemented
  and explicitly `not_started` in the full roadmap. Its accepted continuation
  contract still requires durable opaque account/environment scope,
  cross-key/account-level deduplication, verified recurring and post-trial
  prices, supported interval normalization, fail-closed unknown/mixed currency,
  atomic active-plus-proposed admission, restart/concurrency/migration tests,
  and no implied paid activation. The verified-free checkpoint route gate and
  quota ledger are not substitutes for this feature.
- No provider HTTP, quota spend, retained-data change, Docker/browser run,
  staging/sibling mutation, paid/trial activation, deployment, or cleanup
  occurred.

## 2026-10-16 17:31Z — exact-source quota-admission preflight

- The full-matrix `--preflight-only` run on Provider source
  `51ebc7d45aa34d2e8790988778ee5e6eec14bdd7` completed at 17:30:57Z. It
  evaluated all 27 configured manifest providers, reported no missing
  credential names, and made zero provider HTTP requests with no quota spend.
- It did **not** admit live use: durable quota coordinator validation failed
  because the private SQLite ledger is read-only to this sandbox. Therefore no
  operation had an actual fresh quota reservation/admission. Twenty-four
  providers passed policy-level checks; Dinari Sandbox remains quarantined for
  missing reviewed quota/reset/operation-cost profile, Marketstack discovery
  for unresolved venue/page-cost/MIC bounds, and Tiingo for unreviewed plan.
  The complete append-only receipt contains the exact blockers and operation
  inventory. Never substitute a temporary empty SQLite ledger, which would
  sever cross-session usage continuity.
- Provider CI `38937321525` remains non-terminal: Backend, Frontend Unit and
  Branch-declared are green; Playwright E2E is still running; Exhaustive is
  skipped. TC CI `38930779878` is terminal-success for standard jobs including
  E2E, but staging remains `0145b65992b8692ce69f82f804f83f6c8e551fea`; no
  synchronized repair release has been published. Provider's historical full
  browser red is unchanged and must not be rerun before that release.
- This preflight did not refresh provider-account usage dashboards/baselines
  or exercise provider integrations. It is neither live success nor checkpoint
  acceptance. Current provider transport remains blocked until the configured
  persistent shared coordinator can safely reserve across sessions.

## 2026-10-16 17:37Z — persistent coordinator preflight supersedes shell-only failure

- The previous 17:30Z host-shell preflight failed its ledger write check due to
  workspace sandbox permissions. A read-only inspection then confirmed the
  assigned Provider backend container mounts the same private persistent
  ledger, runs as root, and had zero unreconciled live-receipt reservations.
  Running the documented no-transport preflight through that existing backend
  environment at 17:35:14Z passed the coordinator's read/write health check.
- The successful preflight found 21 providers with capability/entitlement and
  combined full-manifest quota headroom; it quarantined six groups: CTA Plan,
  EODHD and Nasdaq for directory headroom, Dinari for missing reviewed
  Sandbox quota/reset/cost contract, Marketstack for monthly OHLCV headroom and
  unresolved discovery bounds, and Tiingo for unreviewed plan plus unknown
  hour/day baselines. It recorded zero provider HTTP requests and no quota
  spend. No request reservation was created, so this is not live admission or
  success evidence. The 17:30 sandbox-only failure remains historical and is
  superseded only for coordinator availability, not erased.
- At 17:37Z exact Provider Actions `38937321525` still has Backend, Frontend
  Unit and Branch-declared green, E2E running, and Exhaustive skipped. TC's
  `38930779878` is terminal-success including E2E; staging remains
  `0145b65992b8692ce69f82f804f83f6c8e551fea`, with no synchronized repair
  release. The no-provider-HTTP instruction remains in force; do not spend
  quota or start another browser profile.

## 2026-10-16 17:43Z — exact-source CI E2E terminal; ICP2/ICP6 continuation

- Exact Provider Actions run `38937321525` on synchronized source
  `51ebc7d45aa34d2e8790988778ee5e6eec14bdd7` is terminal for required jobs:
  Backend, Frontend Unit, Branch-declared, and Playwright E2E succeeded;
  Exhaustive was skipped by the feature-push workflow. E2E selected all 260
  cases: 151 passed and 109 skipped. Log review found no failed test,
  Playwright retry, or flaky marker. This does not erase the earlier
  source-qualified full Provider browser red at `1236a367`, does not replace
  the required local full profile, and is not checkpoint acceptance.
- TC owns the F9e Add Tool readiness and F8s benchmark fixture corrections.
  Its run `38930779878` is terminal success, but no synchronized coordinator
  staging repair has been released. Do not edit TC code or rerun the Provider
  browser matrix until that release. Do not start a local full-stack/browser
  profile while the assigned Provider and TC Compose stacks are active.
- ICP2 work remains split: durable quota/free-only routing is implemented and
  its bounded exact-source tests are green; aggregate recurring-subscription
  cost admission is a separate full-roadmap criterion (`AC-RECURRING-COST`,
  `not_started`). No subscription commitment ledger, price evidence, or
  atomic ceiling admission is implemented. Continue its Provider-owned
  contract/design work without activating paid or trial routes.
- ICP6 producer examples/tests cover retained success, ready/partial/missing
  coverage, local-only empty `200 []` without hydration, quota/unreviewed
  denial before callback, and provider-backed no-data `404`. Downstream ETF,
  TC2000, and Strategy wiring remains explicitly owned by those branches
  after Provider green staging; no sibling edits were made.
- No provider HTTP, quota spend, browser rerun, staging/sibling mutation,
  deployment, paid/trial activation, or data cleanup occurred.

## 2026-10-16 17:49Z — shared repair CI still awaiting E2E

- Read-only GitHub Actions inspection of repair run `38940886651` on repair
  source `c9127042fa25aaed687dc59787bff607e68338f4` shows Backend, Frontend
  Unit, and Branch-declared jobs successful; Playwright E2E remains in
  progress; Exhaustive is skipped. This is not a synchronized repair release.
- Read-only GitHub branch API confirms `staging` remains at
  `0145b65992b8692ce69f82f804f83f6c8e551fea`. Provider browser validation
  therefore remains held; no repair code was imported and no local browser
  profile was started.
- Provider Actions `38937321525` remains exact-source standard-CI green at
  `51ebc7d45aa34d2e8790988778ee5e6eec14bdd7`; E2E is 151 passed/109 skipped,
  with no test failures, retries, or flaky markers. The prior full local
  browser red remains unchanged.
- No provider HTTP or quota spend, staging/other-worktree mutation, deployment,
  paid/trial activation, or data cleanup occurred.

## 2026-10-16 17:52Z — ICP6 HTTP examples now have full-payload assertions

- Audited the documented coverage and OHLCV examples against the live router,
  Pydantic response model, and unit tests. The prior tests asserted selected
  fields, leaving accidental changes to requested range, covered bounds,
  explanation, and response extras insufficiently guarded.
- Strengthened Provider tests to compare the complete serialized response for
  ready, partial, and missing local coverage and the provider-backed no-data
  404. This preserves the distinctions among retained-local coverage,
  provider-backed absence, and local-only empty 200 []; no frontend or
  production runtime changed.
- After formatting, both focused router modules passed 13/13. Ruff check,
  Ruff format check, and git diff --check also pass. This remains dirty-
  worktree evidence at base HEAD 51ebc7d; exact-source CI is still required.
  No provider HTTP or quota was used.

## 2026-10-16 17:55Z — ICP6 contract-test commit pushed

- Committed and pushed the complete-payload consumer tests and their current
  workstream evidence as Provider commit
  ba06bdc6b525c8f007fd6917bd3df2603aa8f093
  (test(provider): lock consumer response contracts). Local HEAD and
  origin/feat/market-data-provider-platform are synchronized at this SHA.
- Its exact GitHub Actions run 38943410344 was triggered by push at 17:55:35Z
  and is in progress; its eventual result is required before this commit can
  be called CI-validated. The 13/13 focused test, Ruff, and branch-workstream
  results remain bounded evidence only.
- No production runtime/frontend change, provider HTTP/quota spend, staging
  integration, or sibling mutation occurred.

## 2026-10-16 18:01Z — shared repair CI is green; staging not yet released

- Exact repair Actions run 38940886651 on
  c9127042fa25aaed687dc59787bff607e68338f4 is terminal-success for Backend,
  Frontend Unit, Branch-declared, and Playwright E2E; Exhaustive was skipped
  under the feature-push workflow. This is repair-branch CI, not a synchronized
  staging release or permission to rerun Provider's full local browser matrix.
- Read-only GitHub branch lookup confirms staging still points to
  0145b65992b8692ce69f82f804f83f6c8e551fea. Provider run 38943410344 for
  ba06bdc6b525c8f007fd6917bd3df2603aa8f093 remains in progress at Backend;
  Frontend Unit has succeeded. Do not call the current Provider commit CI-green
  yet.
- Keep the earlier Provider full browser failure source-bound and unchanged.
  No repair source was imported, no Provider browser rerun was started, and no
  provider HTTP/quota spend occurred.
