# feat/strategy-lab-v2

Created from `staging` at `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`.

## Current authority policy - scope-qualified Nautilus v2

Exact-pinned stable or release-candidate Nautilus v2 builds may publish local
backtests after the four backtest conformance checks pass and the result binds
the exact release channel, source/wheel/image digests, conformance evidence,
execution scope, and plan fingerprint. RC authority is restricted to local
backtests unless the full five-check gate is met; either an exact-pinned stable
or release-candidate v2 build can qualify for broker-free full/forward shadow
after event-tape parity passes. Stable release labeling is not a gate. No
prerelease may connect to a broker or control real capital.

This removes an upstream stable-release date from backtest completion. Docker
Buildx still gates only final Compose/browser validation; provider, ETF, and
TC2000 shared paths remain gated only until their approved work reaches
staging.

## 2026-10-04 - Scope-qualified Nautilus RC backtest authority

Commit `0b3e2277ffc11128b52c493e14242c3387e0e02b` removes the wait-for-stable
release dependency from authoritative local backtests. An exact-pinned stable
or release-candidate v2 build can publish a local backtest when all four
backtest checks pass and the output binds its release channel, exact source,
wheel and image digests, conformance evidence, execution scope, and plan. RC
authority is limited to local backtests until the full five-check gate passes;
then either an exact-pinned stable or release-candidate v2 build may qualify
for broker-free full/forward shadow after event-tape parity. Stable release
labeling is not a gate, and prereleases cannot connect to brokers or control
real capital.

The gate is enforced end to end across conformance capability binding, worker
request/search-preparation construction, engine execution planning, result
provenance/materialization, and result publication. Regression coverage now
proves a pinned RC5 backtest reaches authoritative worker-result publication,
while missing simulator checks, full-scope RC authority, and forward parity
remain fail-closed. This supersedes earlier historical handoff passages that
restricted every prerelease result to compatibility-only status; the durable
branch plan and current policy above are authoritative. The copied goal text in
`session.json` still reflects the older stable-only wording; treat that as
stale execution metadata, not as a release dependency.

Validation at this source: the full Strategy Lab package passed `1,333` tests
with only the sandbox-denied Unix-socket case deselected; that case passed
separately with scoped local-socket permission. Ruff check/format passed for
all 14 changed Python files, targeted MyPy passed for all eight changed
production modules, and `git diff --check` passed. The existing exact RC5
four-check runtime/conformance receipt remains the engine evidence; this
policy-only increment did not rebuild the Nautilus image. Docker Buildx and
socket access remain environment gates for the final Compose/browser profile,
not for continued package-owned implementation.

Next: produce and persist verified native OOS session-close equity intervals
through result materialization. Do not infer closes or cadence from irregular
market-event callbacks. Continue the remaining domain mutation, worker
recovery/scaling, and broker-free forward-shadow acceptance afterward.

## 2026-10-04 - Native OOS absolute drawdown

Metric definition v14 now publishes `maximum_drawdown_amount` in the account
base currency for both fixed-cadence performance metrics and event-aligned
native OOS metrics. It is calculated as the largest observed running-peak
equity minus a later trough; it does not infer a sampling cadence. Event-aligned
OOS output retains the verified native equity-trace evidence and reports a
null reason when there are no post-opening observations. The metric is tested
through the Nautilus OOS metric-set builder as well as the lower-level
calculators.

Implementation commit `f365ae1179468dbfb5ffd35459d9d9c2867a46c7` is published
to `origin/feat/strategy-lab-v2`. Validation at that source: the three focused
metric/materialization files passed 39 tests; the full Strategy Lab package
passed 1,328 tests with only its local-socket test deselected, and that test
passed separately under scoped local-socket permission. Ruff check/format,
targeted MyPy for `metrics.py`, and `git diff --check` passed. This increment
does not change the stable-v2 authority gate or make prerelease results
authoritative.

## 2026-10-04 - Stable-v2 authority gate

The implementation now requires a stable Nautilus v2 release for authoritative
backtest plans and publication, while retaining exact-pinned release candidates
in compatibility scope. Focused conformance, execution, materialization,
publication, and search-preparation tests verify that RC evidence cannot be
upgraded to authority. The current official upstream release list still labels
2.0.0rc5 as a pre-release ([official release list](https://github.com/nautechsystems/nautilus_trader/releases)),
so this authority activation gate is external; it does not block the remaining
owned implementation work.

Implementation commit `d10600e5f` is published to
`origin/feat/strategy-lab-v2`. Validation at that exact code commit: all 1,329
Strategy Lab tests passed (1,328 package tests plus the Unix-socket RPC test
under scoped local-socket permission); Ruff check and format checks passed;
targeted MyPy passed across the 10 changed production modules; `git diff
--check` and all 30 workstream records validated. A broader package MyPy run
still reports five type errors in three unchanged test modules
(`test_nautilus_target_allocation.py`, `test_nautilus_order_routing.py`, and
`test_nautilus_runtime_adapter.py`); that diagnostic does not affect the passing
focused production-module check. The full Compose/browser gate remains pending
Docker Buildx.

## 2026-10-04 - Event-time OOS annualized return and Calmar

Implementation `c0f67e080` advances the native OOS metric definition to
`strategy-lab.metrics.v13`. When exact verified equity-event timestamps are
available, annualized return is now calculated from terminal/opening equity
over the exact elapsed UTC span using the explicit `365.2425` calendar-days-per-
year convention. The convention, elapsed nanoseconds, and timestamp unit are
recorded in the metric definition. Calmar uses that same annualized return and
the observed OOS maximum drawdown. Missing timestamps, zero elapsed time,
non-positive opening equity, and results outside the Decimal numeric range
produce explicit null reasons. Annualized volatility, Sharpe/Sortino, and
historical VaR/expected shortfall remain withheld until an explicit sampling
basis is available; irregular event counts are not treated as fixed periods.

Validation: `45/45` focused metrics, verified-equity-trace, native result
metrics, and result-materialization tests passed. Ruff, format checks,
`git diff --check`, and targeted MyPy for `metrics.py` passed. Implementation
commit `c0f67e080` is published to `origin/feat/strategy-lab-v2`.

Changed source paths: `backend/app/strategy_lab_v2/metrics.py` and
`backend/app/strategy_lab_v2/tests/test_metrics.py`. RC5's exact-pinned
qualification remains compatibility evidence only; stable v2 conformance is
required before authoritative Nautilus results can be published. The separate
Buildx gate still applies only to final Compose/browser validation.

## 2026-10-04 - Event-time OOS drawdown duration

Implementation commit `925be2d1d94c74e78b54a49385e9e54bdcb58ad6` adds
`maximum_drawdown_duration_seconds` to the versioned native OOS metric set
(`strategy-lab.metrics.v12`). It measures elapsed UTC time from the latest
observed account-equity high-water mark through the first observed recovery, or
through the final OOS mark when the account remains below that peak. The prior
event-observation-count metric remains available. Missing timestamps produce an
explicit null reason; supplied event timestamps must be non-negative,
non-decreasing, and one-to-one with the verified equity trace. No sampling
cadence or annualization convention is inferred.

The byte- and frozen-tape-verified Parquet reader now also exposes typed
event-time/equity observations. OOS result materialization streams those exact
observations to the metric builder without retaining the full trace in memory;
the existing marks-only reader remains compatible for its other callers.

Validation: the focused metric/trace/materialization set passed `42/42`. The
full Strategy Lab suite reported `1,323` passing tests; its one Unix-domain
socket case was denied by the default sandbox and then passed separately with
scoped local-socket permission. Ruff, formatting, `git diff --check`, and MyPy
for the four changed production modules passed. A package-wide MyPy diagnostic
reported five errors in three untouched test modules
(`test_nautilus_target_allocation.py`, `test_nautilus_order_routing.py`, and
`test_nautilus_runtime_adapter.py`); the changed production modules are clean.

The exact RC5 runtime rebuild and local conformance qualification passed all
four local backtest checks plus the recorded lifecycle/native probes. Source
digest: `sha256:ca2135151d1bb28a03b2532e438533ba534d1ca15944e612ab9064730e79d635`;
image digest:
`sha256:7929a31f8a2533922533abea9c755992590400d85576868ab46149a77b894fdf`;
receipt digest:
`sha256:584a666ee9082595574f625065abc6f5f4f8901ad7af25d1d5d4b24ab53faed4`;
conformance fingerprint:
`sha256:e7ee4847904fc9530282bde8d781ccc4b05539db639b41961b222fba70eada3b`.
Probe receipts correctly remain `authoritative: false`. Resource cleanup left no
containers, images, volumes, or Testcontainers sessions.

Stable Nautilus v2 remains unnecessary. Exact-pinned `2.0.0rc5` is isolated and
qualified for local backtesting; a later release must pass the applicable
conformance checks independently. The final `full_stack_browser` profile is
still pending Docker Buildx, which does not stop package-owned implementation.
Continue the broader metrics, domain-mutation, worker recovery/scaling, and
persistent forward-shadow acceptance; keep option orders fail-closed until
canonical event-time risk and settlement inputs are supported.

Changed source paths: `backend/app/strategy_lab_v2/metrics.py`,
`backend/app/strategy_lab_v2/nautilus_equity_trace.py`,
`backend/app/strategy_lab_v2/nautilus_result_materialization.py`,
`backend/app/strategy_lab_v2/nautilus_result_metrics.py`, and their focused
tests. Changed workstream paths: `ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-04 - Futures target allocation through native margin admission v1

Implementation `57fd82082e745fbfae62f2dcedc26eca235fdfc2` extends
engine-neutral target sizing to complete, base-currency-settled futures
contracts. Target notional is converted using native mark price multiplied by
contract multiplier, rounded toward zero to whole contracts, then compared to
the attributed native position to create only the delta order. Margin-account
target sizing permits futures only; cash-account futures targets, unsupported
products, and incomplete multiplier/lot/margin terms fail closed. Candidate
orders still go through the combined account order router and the same native
event-aligned initial/maintenance-margin gate before Nautilus submission.

The exact-source RC5 build passed with source digest
`sha256:cca3c58c536a2e8d175980cbbdc88223c005400c2ef72bbb9ac0385730b213fb`,
runtime image digest
`sha256:9f3148585fc4b30111608639f7099993d4488da75c3b9369901908403392a8ce`,
receipt artifact digest
`sha256:9b10357d27cef539dcc68a49eea53c2fc9c81ae8e19e5d8440c776592a548f9c`,
and conformance fingerprint
`sha256:68452501502527594fc0519637fb96c99ed1f187764c2095e798e555d93c907d`.
The newly built image, without source overlays, converted a future target into
one native order/position and approved it through the margin gate. The probe
remains `authoritative: false`; publication still requires the exact
backtest-scope evidence binding.

Validation at the implementation commit: Strategy Lab package suite `1,321
passed`; package Ruff, changed-file formatting, targeted MyPy, and `git diff
--check` passed. The implementation commit is published on
`origin/feat/strategy-lab-v2`.

Stable Nautilus v2 is not a prerequisite. Exact RC5 source/image qualification
continues to pass the four local backtest checks. Pre-releases remain barred
from brokers and real capital; forward-shadow execution separately requires
event-tape parity. Docker Buildx remains the environment limitation for only
the final full Compose/browser profile; package-owned work continues.

Next: continue the broad result-metrics, domain-mutation, worker
recovery/scaling, and persistent forward-shadow acceptance criteria. Options
remain fail-closed pending canonical event-time Greeks/delta and settlement
evidence.

Changed source paths: `backend/app/strategy_lab_v2/nautilus_runtime_adapter_probe.py`,
`backend/app/strategy_lab_v2/nautilus_strategy_bridge.py`,
`backend/app/strategy_lab_v2/nautilus_target_allocation.py`, and
`backend/app/strategy_lab_v2/tests/test_nautilus_target_allocation.py`.
Changed workstream paths: `ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-04 - Native futures margin admission v1

Implementation `3f0ec64916fa184115970bfda7d9fab44365bf94` adds direct listed-
futures order admission on the exact-pinned Nautilus margin account. Before
submission, the bridge binds account currency/equity and native initial and
maintenance requirements to the current event, projects the whole-contract
post-order position through RC5's native calculators, replaces existing
per-instrument futures requirements (rather than double-counting them), and
applies the shared margin-risk gate. Margin valuation uses an adverse
event-aligned ask/trade/bar-high price rounded to the native tick; unsupported
settlement currencies, missing native evidence, and unbounded stop-market
orders fail closed. Equities and crypto spot retain their existing paths;
futures target allocation and option orders remain unsupported.

Exact-source RC5 evidence build passed with source digest
`sha256:bdd1e626c8c45b96d031cbfc4412c637850e17ceb837d03f27a1628969366a78`,
runtime image digest
`sha256:723390861b3e7ac8671ea43d7670fc1a25b54e035186021e1408012958a59851`,
receipt artifact digest
`sha256:74ffacb0706cb75e26935a3ad709b0a2450dcbcc506c6ccb0208f4b8aa8d4009`,
and conformance fingerprint
`sha256:acc25b0f47efa55e36b3c35b66299dd5f37ddefcd790c0724973e894c6b56af5`.
The new isolated image, without source overlays, admitted one `CLZ26.SIM`
contract on a USD margin account and produced one native order/position. The
receipt remains `authoritative: false` by design: it is a probe, not a
scope-bound published backtest result.

Validation at the implementation commit: Strategy Lab package suite `1,317
passed`; package Ruff, changed-file formatting, targeted MyPy, and `git diff
--check` passed. The implementation commit is published on
`origin/feat/strategy-lab-v2`.

Stable Nautilus v2 is not a prerequisite. The exact RC5 build passes all four
local backtest conformance checks; pre-releases remain barred from brokers and
real capital, and forward-shadow execution separately requires event-tape
parity. No external release or upstream dependency blocks package-owned work.
Provider/ETF/TC2000 staging gates apply only when consuming their shared-path
contracts. Docker Buildx remains the sole environment limitation for the final
full Compose/browser profile, not a reason to pause implementation.

Next: extend native futures margin admission to futures target-position
allocation while preserving whole-contract sizing and shared-account risk.
Options remain fail-closed pending canonical event-time Greeks/delta and
settlement evidence; continue the remaining domain mutations, metrics, worker
recovery/scaling, and persistent forward-shadow acceptance.

Changed source paths: `backend/app/strategy_lab_v2/nautilus_order_routing.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_adapter_probe.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_image/Dockerfile`,
`backend/app/strategy_lab_v2/nautilus_strategy_bridge.py`, and
`backend/app/strategy_lab_v2/tests/test_nautilus_order_routing.py`. Changed
workstream paths: `ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-04 - Versioned native listed-derivative definitions v1

Implementation `ee7a98510ab8b88d5ff08d756d99e90777d674f9` adds a strict v7
native-runtime instrument contract for listed futures and vanilla options,
including explicit underlying, expiry, multiplier/lot, option right/strike,
and initial/maintenance margin terms. The adapter continues to accept the
legacy v6 shape for spot instruments and fails closed when a v6 payload tries
to declare a derivative. The isolated runtime bundle carries the new fields.

Focused negative/positive validation covers wire-version shape, incomplete or
inconsistent contract terms, serialization, and native `FuturesContract` and
`OptionContract` construction. The exact pinned RC5 image was exercised with
read-only source overlays: both native instrument types materialized, and the
adapter probe completed with `authoritative: false`. This is runtime
compatibility smoke evidence, not a rebuilt-image/source-digest qualification,
derivative order execution proof, or authoritative result qualification.
Futures/options order routing and target allocation remain explicitly rejected;
this change does not claim those products are tradable.

Validation at this implementation SHA: Strategy Lab package suite `1,312
passed`; package Ruff, changed-file formatting, targeted MyPy, and `git diff
--check` passed. The implementation commit is published on
`origin/feat/strategy-lab-v2`.

Next: implement an event-aligned futures margin/account-capacity bridge from
the pinned native margin account and apply the existing shared margin-risk gate
before engine submission. Keep options order admission closed until
canonical event-time Greeks/delta and settlement semantics are available.
Stable Nautilus v2 is not a prerequisite; exact-pinned pre-release use remains
local-backtest-only and barred from brokers or real capital.

Workstream records updated with this checkpoint: `plan.yaml`, `handoff.md`,
`session.json`, and `validation.jsonl`. The current session refresh reports the
Docker daemon available after the scoped checkpoint check (`29.1.3`); the Docker
CLI has no Buildx plugin (`docker buildx` is unknown), so only the final
full-stack browser profile remains deferred. Package-owned work continues.

## 2026-10-04 - Native component P&L attribution v1

Committed and pushed implementation `11a5753de` (`feat(strategy-lab):
attribute native component P&L`). Result metric materialization now derives
account net P&L from the frozen first/last event-aligned equity marks, adds
complete in-window base-currency native commissions/rebates for portfolio gross
P&L, and attributes only closed OOS position cycles whose native order tags,
fill identities, timestamps, fee currencies, and realized-P&L currency all
agree. Archived position reports prefer retained native trade IDs because the
report assigns snapshots generated position IDs; older report schemas retain a
strict position/order-ID join. Duplicate or overlapping identities, incomplete
fees, and foreign-currency costs fail closed; positions that cannot be proved
component-owned remain in an explicit unallocated residual. Portfolio and
component gross/net values must reconcile exactly before they enter the metric
set. The `__unallocated__` ID is now reserved at the portfolio contract boundary.

This is local adapter coverage, not yet a claim that the exact RC5 report
emission path exposes every field required for attribution. Nautilus' current
reporting guide describes closed-cycle snapshots and retained trade IDs; the
exact pinned runtime report shape still needs a native-output probe before this
path is treated as authoritative evidence: [Positions](https://nautilustrader.io/docs/latest/concepts/positions/),
[Reports](https://nautilustrader.io/docs/latest/concepts/reports/).

Validation: all Strategy Lab package tests passed (`1,285 passed`; local-socket
RPC test separately passed `7 passed` in the prior checkpoint), changed-file
Ruff and formatting checks passed, targeted MyPy passed for five production
modules, and `git diff --check` passed. Full Compose/browser validation remains
pending because Docker Buildx is unavailable. Provider/ETF/TC2000 staging and a
stable Nautilus release are not blockers to continued owned-path implementation.

Next: exercise this attribution against reports emitted by the exact pinned
RC5 runtime, including an archived/reopened cycle and mixed-component/shared
account case; then continue the remaining result-analytics and durable worker /
forward-shadow acceptance. Do not claim global AC-METRICS or AC-NAUTILUS complete
from this slice alone.

Changed source paths: `backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/nautilus_component_pnl.py`,
`backend/app/strategy_lab_v2/nautilus_native_reports.py`,
`backend/app/strategy_lab_v2/nautilus_result_metrics.py`,
`backend/app/strategy_lab_v2/nautilus_result_materialization.py`, and their
focused tests. Changed workstream paths: `ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-04 - RC5 native fill-to-component report linkage

Extended the isolated RC5 priority-contention probe to join its component-tagged
native order to the fill report through `venue_order_id`. The exact-image
receipt verified satellite order `SIM-1-1` produced a fill for 99 `AAPL.SIM`
shares at USD 100.03 with a reported USD 0.00 commission. The strict receipt
parser now requires a declared component, order id, instrument, positive fill
quantity and price, and a currency-matched non-negative commission. This proves
native fill attribution linkage only; it does not yet calculate component P&L or
claim authoritative results.

Exact-source RC5 qualification: source
`sha256:aef2823b2a768eeb3d934d6049c58ec88e6ee4c2e7a2a0c90e7a1947516cbc19`,
image `sha256:bd254e785733c0e6fec5810d60af615010358fef5bab8651a3eb90fcb7dfc7ba`,
receipt `sha256:abd0e135ebc3dc8a96d6890499969bea3602193e1ee7730ee7392f1aa11c9583`,
and conformance fingerprint
`sha256:f1bfce36f2008e0b6e24d4b25356a23f12362f37f2d0757dded6dae591e46a2f`.

Record correction: the preceding contention section mistyped its RC5 receipt
content address. The canonical file under
`.ai/runtime/strategy-lab-v2/nautilus-rc-evidence/` is
`sha256:c3cad9703b8f81004914351350897d4d9eb29ef903e2c0e85438f8b35f3a27b3`;
the source/image/conformance results there are unchanged.

Validation: focused runtime/conformance/execution tests `58 passed`; Strategy
Lab package tests `1,287 passed` with the one local-socket test excluded and
then separately passing (`1 passed` with scoped socket permission); Ruff,
changed-file formatting, targeted MyPy, and diff checks clean. Implementation
commit `9ef96dcc2b980db4d3db32bc4b00668b480b1a8a` is published to
`origin/feat/strategy-lab-v2`. Docker Buildx still limits only the final
Compose/browser validation; no release-label or current upstream dependency
blocks package-owned work.

Next: implement component-level P&L/cost observation construction from the
verified native fill/order/position artifacts and frozen marks. It must use
explicit supported cost-basis/currency semantics, retain an explicit
unallocated residual where native totals do not map to components, and exactly
reconcile to the native portfolio result before entering official metrics.

## 2026-10-04 - RC5 competing-target priority and shared-risk conformance

The stable-v2 release label is not a blocker: `plan.yaml` explicitly permits
an exact-pinned stable or pre-release Nautilus v2 build after the same native
backtest conformance. The exact `2.0.0rc5` path remains isolated to offline
backtests; this evidence is non-authoritative qualification only and does not
authorize broker connections or real capital.

Extended the real RC5 shared-account rebalance probe with competing component
targets (`core` 0.8 versus `satellite` 0.2) and distinct priorities. The native
account selected the higher-priority satellite order, retained its
`strategy-lab-v2:component:satellite` tag, and reconciled to one native order,
one position, and USD 90,097.03 cash. A second probe exceeded the shared gross
risk limit and verified rejection before any native orders or positions were
created. The receipt parser now requires both outcomes, and a stale execution
receipt fixture was updated to the stricter schema. Neither probe claims
authoritative P&L or forward-shadow parity.

Exact-source RC5 qualification for this runtime slice: source
`sha256:8e70f068bbd6cc0d01748984d7731a571f0cff8676bdad011ea6729e69ee13ec`,
image `sha256:b91351ff91970ec2134d2179609e0873de9df3e2bf51a209a093ddb2bb38aa19`,
receipt `sha256:c3cad9703b8f81004914351350897d4d9eb29ef903e2c0e85438f8b35f3a27b3`,
and conformance fingerprint
`sha256:9c7f5f6d454819553fe68bb3f3ed1b5dd3716a6cdc385081f88078cab074ba8a`.

Validation: Strategy Lab package suite `1,286 passed`; the existing Unix-domain
RPC test passed separately with narrowly scoped socket permission (`1 passed`);
focused native/runtime/conformance suite `71 passed`; Ruff and changed-file
format checks clean; MyPy clean across 364 package/runtime sources; diff check
clean. Implementation commit `8f0afef4512f2a6d9594447b16802187b51d70a6` is
published to `origin/feat/strategy-lab-v2`. The checkout's remote-build
environment still lacks Docker Buildx for the final Compose/browser profile;
this does not block package-owned backend work. Provider, ETF, and TC2000
staging remain contract-consumption gates only.

Next: derive component-level P&L and costs from native fill/order evidence,
reconcile them exactly to native account/equity results, and bind those
observations into the existing immutable metric calculation path. Native order
tags and component quantity accounting exist, but fill-level component P&L
attribution remains unproven.

## 2026-10-04 - RC5 multi-component stream boundary and shared-account probe

Confirmed that a stable Nautilus 2.x tag is not a prerequisite: the branch plan
allows the exact-pinned `2.0.0rc5` build for offline backtests after conformance.
The newly exercised catalog-backed callback path exposed two concrete boundary
details, now handled in the owned stream adapter: native `ts_init` values must
be strictly after `ts_event`, and bridge readers need independent logical
cursors when catalog ingestion and callbacks share one seekable event stream.
The serializer/decoder enforce the timestamp rule; independent cursors retain
bounded streaming without duplicating the event tape.

An exact-source hardened RC5 image passed the four existing local backtest
checks and open/close/fail-on-misfire schedule probes. Its additional
multi-component shared-account probe submitted two native orders, reconciled
them to one net position, and left USD 50,185.06 cash from USD 100,000 initial
capital. This is non-authoritative conformance evidence, not a live-capital
qualification. Exact pins: source `sha256:c95d9cf3d4cd4b053e7826ffa5e8efb42b9a8528b1bf65288aaeae437d8f052b`,
image `sha256:74f872392cf902725816dfd6ed85821269e2a5a65069cf41433c3ea540ed6db6`,
receipt `sha256:904b18a38b87a4c63232bda128c3442d275ec76dbf8e8858b6da9a8ffbb0886c`,
and conformance fingerprint
`sha256:814544c9dc36ab80df8758106833390ebd5488953fb165cdccb15ca2f1f957aa`.

Validation: full Strategy Lab package suite `1,286 passed`; focused native
stream/bridge/runtime suite `90 passed`; Ruff clean; MyPy clean across 364
package/runtime sources; all nine changed Python files formatted; diff check
clean. Contention ordering under distinct component targets, shared-risk
rejection, and persisted component attribution remain unproven and are the
next native portfolio conformance work. Provider/ETF/TC2000 staged contracts
remain gates only for consuming those workstreams' owned data and semantics.
Missing Docker Buildx limits only the final Compose/browser profile.

## 2026-10-04 - Exact RC5 native rebalance schedule qualification

Closed the native schedule-probe gap. The RC5 image now exercises open-boundary
rebalance, close-after-complete-event-group rebalance, and fail-on-misfire
through the actual Nautilus bridge. All three outcomes reconciled against the
native account and plan-bound audit: open/close each submitted one order and
created one position; fail-on-misfire submitted none, created no position, and
remained non-authoritative. The initial probe failure was fixture input outside
its declared one-event lookback; the bridge/SDK correctly rejected it. The
probe now supplies only the permitted prior-plus-current events.

Exact evidence: Nautilus `2.0.0rc5`, Python `3.12.4`, Rust `1.98.1`, source
digest `sha256:6bd04ed844d8198f3c7ab1823b43533e3faa55729c0287b8548103df38dab759`,
image digest `sha256:3c0cbaf543e1912cea0afe98e288793f7998cd5a457d814a64803dd3df8a43d6`,
and content-addressed receipt
`sha256:5ad969e9bbc99b94e8654c1e86532f8dbea1015b6d03760f768dbb236bc62a05` at
`.ai/runtime/strategy-lab-v2/nautilus-rc-evidence/`. The isolated probes ran
with networking disabled, read-only root, and capabilities dropped. This
receipt remains non-authoritative runtime qualification evidence, not a
backtest result or real-capital authorization.

Validation: full Strategy Lab package suite `1,284 passed` (the single local
Unix-socket test required the repository's narrow socket-enabled test run);
focused runtime/conformance/engine suite `55 passed`; Ruff clean; MyPy clean
across 358 package sources; six changed Python files formatted; workstream
validator and `git diff --check` clean; exact-source RC5 image build and all
fixture probes passed. Implementation commit
`c0eb70737c34ee4576c8591d7b84c42c58b26e16` is pushed, and local/remote refs
matched at the verified checkpoint. The active-session/Docker checkpoint then
passed at clean synchronized pre-record tip
`855c5abeac8ae1025ec7aa179651a0409d7f4a6a`, with zero assigned containers,
volumes, or Testcontainers sessions. This final operational record commit is
separate; its exact enclosing SHA is verified externally with `git rev-parse`
after publication.
Owned paths:
`backend/app/strategy_lab_v2/nautilus_runtime.py`,
`nautilus_rc_fixture_probe.py`, `nautilus_runtime_adapter_probe.py`, and the
three directly corresponding runtime/conformance/engine tests.

No stable Nautilus 2.x release is required. Provider, ETF, and TC2000 staging
contracts remain gates only for consuming those workstreams' owned data and
semantics; they do not stop package-owned implementation. Missing Docker Buildx
limits only final Compose/browser validation. Next: add exact-RC5 native
multi-component rebalance/allocation coverage for shared-account routing and
contention, then continue remaining metric, provider-snapshot, worker, and
forward-shadow acceptance.

## 2026-10-04 - Durable diagnostics for failed rebalance schedules

Closed the previous failure-audit gap without treating a failed simulation as
a result: when the Nautilus runner reports a failed run with a plan-bound
rebalance audit, the owner-authenticated worker terminal resolver publishes the
audit bytes content-addressably and includes the verified manifest reference in
the persisted terminal error details. It verifies publication identity and
byte integrity. A queue redelivery reuses the exact artifact/reference. Failed
attempts still have no result manifest, metric set, or authoritative result.

Validation: full Strategy Lab package suite `1,284 passed` with scoped
temporary Unix-socket access; worker-terminal suite `5 passed`, including
artifact byte verification and redelivery replay; Ruff clean; MyPy clean across
364 package/runtime sources; changed files formatted and `git diff --check`
clean. Implementation commit `5b19f2931a8e008d5197b3294d7937944410b087` is
pushed to `origin/feat/strategy-lab-v2`. Docker Buildx remains unavailable for
the final Compose/browser profile.

Next: run the exact RC5 runtime bundle through a real fail-on-misfire callback
and terminal publication path, then continue the remaining portfolio/account
conformance, metrics, provider-owned snapshot consumption, search/walk-forward,
worker/Compose, and broker-free forward-shadow criteria. Those are unfinished
feature work, not external blockers to current development. Stable Nautilus 2.x
is not required; the saved goal's older stable-only phrasing is superseded by
the branch plan's exact-pinned stable-or-pre-release rule. Provider, ETF, and
TC2000 owned contracts remain staging-gated, and pre-release builds remain
offline-backtest only.

## 2026-10-04 - Calendar rebalance callbacks and trial-plan compilation

The isolated Nautilus bridge now executes frozen rebalance plans at exact
session boundaries: open callbacks precede events at the same timestamp, close
callbacks wait until the complete same-time event group has been processed,
and target-position intents pass through the existing portfolio allocation and
shared-risk route. Declared misfires are recorded; fail-on-misfire stops further
rebalance applications and makes the result failed and non-authoritative.
Callback outcomes are strictly validated against the complete frozen plan and
bound to the attempt in a content-addressed schedule audit. Successful result
materialization publishes that audit as an artifact.

The trusted market preparation context can now carry an optional immutable
`SessionCalendarSnapshot`. Trial assembly requires both that snapshot and an
explicit evaluation window for a portfolio calendar policy, verifies exact
calendar/policy identity through the planner, filters the frozen plan to the
half-open scoring interval, and binds it into the isolated engine-input bundle.
Missing calendar or evaluation evidence remains fail-closed. This is the first
end-to-end assembly path for rebalance plans; it is not full portfolio-feature
completion.

Validation at implementation commit
`79b0db7753bd381a04b6f0f036f548346f82378f`: full Strategy Lab package suite
`1,283 passed` (including the local Unix-socket test with scoped socket access);
focused runtime/bridge/assembly/materializer suite `72 passed`; Ruff clean;
changed Python files formatted; MyPy clean across 364 package/runtime sources;
`git diff --check` clean. The implementation commit is pushed to
`origin/feat/strategy-lab-v2`. Docker Buildx is unavailable, limiting only the
final Compose/browser profile.

Remaining rebalance evidence gap: when `FAIL_RUN` is triggered, the runner
retains the typed audit and binds its fingerprint into the failure digest, but
the generic failed-worker terminal contract does not publish diagnostic
artifacts. Preserve that boundary and add an explicit authenticated diagnostic
artifact path before describing failed misfire audits as durable. Next, test
the runner-to-worker terminal behavior for misfire failures and implement that
path. Then continue native RC5-backed rebalance integration and the broader
portfolio, metrics, snapshot/provider, search, worker, and broker-free forward
acceptance criteria.

The saved goal objective text still mentions stable Nautilus v2, but the
authoritative branch plan accepts an exact-pinned pre-release for offline
backtesting after the same conformance checks. Stable 2.x is not a gate. Keep
pre-releases barred from broker connections and real capital; forward shadow
remains separately gated on event-tape parity. Provider/ETF/TC2000 contracts
must still be consumed only after their approved branches reach staging.

## 2026-10-04 - Versioned rebalance-plan transport boundary

Added a strict wire codec for frozen rebalance occurrences and carried the
portfolio calendar policy plus plan through Nautilus engine-input v5, runtime
bundle serialization, and adapter validation. The adapter checks exact policy,
calendar, occurrence, and plan fingerprints; Docker input allowlisting includes
the new runtime module. Calendar policies now round-trip through the portfolio
wire contract.

This is transport and identity groundwork only. Trial assembly still rejects
rebalance policies, and the native bridge still rejects non-empty plans because
schedule callbacks, intent caching/routing, misfire handling, and durable audit
outcomes have not yet been implemented. Preserve that fail-closed boundary;
do not represent this commit as executable rebalance support.

Validation at implementation commit
`3bb531e3a5e6550b660e4bf0b32bf0a63e1785ee`: full Strategy Lab package suite
`1,269 passed` (including the local Unix-socket test with scoped socket access);
focused rebalance/runtime suite `79 passed`; Ruff clean; changed Python files
formatted; MyPy clean across 362 package/runtime sources; `git diff --check`
clean. The suite first hit the sandbox's temporary Unix-socket bind restriction,
then passed unchanged with the narrow local socket permission. Docker Buildx
remains unavailable, limiting only final Compose/browser runtime validation.

Next: add a trusted frozen session calendar to the preparation context, compile
the scoring-window schedule, and wire native open/close callbacks with exact
boundary behavior, target-intent caching, declared misfires, shared-risk
routing, and persisted decision evidence. Keep assembly fail-closed until those
callbacks execute the plan. Continue the broader portfolio, metrics, snapshot,
worker, and broker-free forward acceptance afterward. Nautilus stable 2.x is
not a prerequisite; the isolated 2.0.0rc5 scope remains offline backtesting
only, with forward parity separately gated.

Changed implementation paths include:
`backend/app/strategy_lab_v2/rebalance.py`,
`backend/app/strategy_lab_v2/nautilus_rebalance_wire.py`,
`backend/app/strategy_lab_v2/nautilus_engine_input.py`,
`backend/app/strategy_lab_v2/nautilus_portfolio_wire.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_adapter.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_adapter_probe.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_bundle.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_image/Dockerfile`,
`backend/app/strategy_lab_v2/nautilus_strategy_bridge.py`, and their focused
tests. Workstream checkpoint paths:
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-04 - Evaluation-window-bound rebalance planner

Added `schedule_rebalances_for_interval`, which retains exact calendar/policy
validation and filters scheduled occurrences to a trial's half-open UTC
execution interval. Warm-up boundaries before the scoring interval and an
occurrence exactly at the exclusive end are omitted. Naive timestamps and empty
or reversed intervals fail closed.

Validation at implementation commit `e7ddfa52bb5a29ae9fe2098a3f25236a5698f59c`:
18 rebalance-planning/allocation tests passed; Ruff, formatting, targeted MyPy,
and `git diff --check` passed. The exact implementation commit was pushed to
`origin/feat/strategy-lab-v2`.

This is a planning primitive, not yet Nautilus execution support: trial assembly
and engine input still reject rebalance policies. Next, provide a trusted frozen
calendar through the preparation context, compile the exact schedule into the
typed engine input, and implement callback-bound open/close and misfire behavior
with auditable outcomes. Keep assembly fail-closed until the worker actually
executes that plan. Provider canonical metadata/series decoding still await the
provider contract reaching staging; Docker Buildx still limits only final
Compose/browser validation. Stable Nautilus 2.x is not a blocker.

## 2026-10-04 - PostgreSQL owner-hydrated preparation integration

The real PostgreSQL/Testcontainers dispatch test now exercises the package-owned
search-preparation composition end to end. It writes the immutable strategy,
package, portfolio, snapshot, experiment, trial, and attempt resources through
`PostgresStrategyLabV2Adapter`; composes `NautilusTrialDomainHydrator` with the
PostgreSQL resource/worker-state readers, shared local artifact root, package
resolver, frozen-series decoder, runtime materializer, and exact RC conformance
binding; then sends the request through the authenticated Unix-socket service
and PostgreSQL dispatch/outbox adapters. A foreign owner cannot hydrate the
attempt, the context resolver receives the reconstructed persisted graph, and
an exact retry replays the prior response without repeating preparation or
creating duplicate admission/dispatch/payload/outbox rows.

Validation at this worktree tip: the PostgreSQL integration passed (`1 passed in
8.39s`) and the full Strategy Lab package suite passed (`1,261 passed in
26.09s`). Ruff and formatting passed for all nine changed Python files; MyPy
passed across 360 package/runtime sources; Compose configuration, all 30
workstream records, and `git diff --check` passed. The package suite required
scoped socket access because one unit test binds a Unix-domain socket. The
combined PostgreSQL/Redis backend coverage gate was not rerun. Docker Buildx is
still missing, so the full Compose/browser runtime profile remains outstanding.

Stable Nautilus 2.x is not required: the branch-owned plan accepts exact-pinned
stable or pre-release builds. The isolated `2.0.0rc5` build has passed the four
local backtest checks and is bound only to authoritative offline backtests;
broker/real-capital use is prohibited and forward shadow separately requires
event-tape parity. The saved Codex goal text still contains stale “after stable
v2 conformance” wording; follow this branch plan instead and do not wait for a
stable tag. Provider canonical metadata and series decoding remain fail-closed
until their approved contract reaches staging.

Next: the calendar rebalance planner exists, but trial assembly and Nautilus
engine input explicitly reject every rebalance policy. Implement and validate
frozen-calendar-bound schedule semantics through those runtime boundaries,
preserving calendar identity, exact session boundaries, and misfire behavior.
Then continue portfolio, metric, snapshot, worker, and forward acceptance.

Changed source/config/doc paths: `backend/app/strategy_lab_v2/application.py`,
`backend/app/strategy_lab_v2/postgres_result_materialization.py`,
`backend/app/strategy_lab_v2/search_dispatch_rpc.py`,
`backend/app/strategy_lab_v2/search_preparation_composition.py`,
`backend/app/strategy_lab_v2/search_preparation_service.py`,
`backend/app/strategy_lab_v2/tests/test_application.py`,
`backend/app/strategy_lab_v2/tests/test_search_dispatch_rpc.py`,
`backend/app/strategy_lab_v2/tests/test_search_preparation_composition.py`,
`backend/tests/integration/strategy_lab_v2/test_search_dispatch_rpc_postgres.py`,
`docker-compose.yml`, and `docs/strategy-lab-v2.md`. Workstream records are
also updated in this checkpoint.

## 2026-10-04 - Locally composed search-preparation dependencies

Replaced the preparation service's generic evidence-resolver factory with a
narrow `SearchPreparationHostBindings` seam. The service now loads and verifies
the operator-pinned local RC evidence itself, then composes the owner-scoped
PostgreSQL hydrator and worker-state reader, shared content-addressed artifact
store, strategy-package resolver, frozen-series materializer, and dispatch
evidence resolver. The trusted host binding supplies only the runtime ABI,
provider-owned frozen-series decoder, and canonical market/runtime context
resolver. A context cannot substitute a different RC evidence/report, image
digest, or runtime ABI. Provider series decoding and canonical product metadata
remain fail-closed until the shared provider contract is approved in staging.

Validation: all 1,260 Strategy Lab package tests passed, including the real
Unix-socket round trip and new preparation-composition tests; Ruff passed, the
changed-file format check passed, MyPy passed across 360 sources, root
Compose configuration parsed, and `git diff --check` passed. This slice did not
rerun PostgreSQL/Redis integration tests or database-backed dispatch/replay
validation. Docker Buildx remains unavailable, limiting only the exact-tip
Compose/browser runtime gate. The ordinary backend still declares Nautilus
1.226.0; the Strategy Lab simulator is deliberately isolated in the pinned RC5
runtime image, so the legacy/API dependency is not its execution authority and
must remain separate during worker integration.

Next: add database-backed search dispatch/replay validation. Then continue the
remaining portfolio, snapshot/provider, metric, worker, and forward acceptance;
consume provider-owned series and canonical metadata only after the approved
shared contract reaches staging. Do not wait for stable Nautilus 2.x.

Changed paths: `backend/app/strategy_lab_v2/search_preparation_composition.py`,
`backend/app/strategy_lab_v2/search_preparation_service.py`,
`backend/app/strategy_lab_v2/tests/test_search_preparation_composition.py`,
`docker-compose.yml`, `docs/strategy-lab-v2.md`, and the branch workstream
records.

## 2026-10-04 - Isolated search-preparation RPC and Compose boundary

Added the local search-dispatch RPC in `search_dispatch_rpc.py` and the
single-process ASGI service in `search_preparation_service.py`. The public API
sends only a fingerprinted owner identity, experiment/attempt coordinates, and
idempotent dispatch intent through a Unix-domain socket protected by a shared
local bearer token. The preparation process performs owner-scoped hydration,
runtime materialization, and atomic PostgreSQL/outbox dispatch; its result is
decoded through the canonical allowlist and checked against a typed content
fingerprint before the API returns it. Malformed/duplicate fields fail closed,
service failures become typed retryable or terminal API errors, and the service
serializes preparation in its own process. A real temporary Unix-socket test
exercised request authentication, exact owner propagation, resolution round
trip, and socket permissions.

`PostgresStrategyLabV2Adapter` can now reuse an injected shared persistence
bundle, allowing the preparation process's evidence resolver and dispatch
adapter to use the same application-owned PostgreSQL graph. The opt-in
`strategy-lab-v2-preparation` Compose service has a read-only root, bounded
resources, no Docker socket/provider credentials, an internal-only PostgreSQL
network, the shared content-addressed artifact volume, a read-only pinned RC
evidence mount, and a shared Unix-socket volume. The API-side host factory is
explicitly selected with
`STRATEGY_LAB_V2_API_BINDINGS=app.strategy_lab_v2.search_dispatch_rpc:build_api_bindings`.
The preparation service requires an operator-selected
`STRATEGY_LAB_V2_PREPARATION_EVIDENCE_FACTORY=module:factory` which returns the
trusted typed evidence resolver; its context must consume the existing exact
RC evidence source and must not claim provider support absent staging-approved
coverage/market metadata. The new factory seam does not itself imply that this
operator context has been configured or that search dispatch is production
active.

Validation: 1,255 Strategy Lab package tests pass; Ruff passes; MyPy passes for
352 package/runtime sources; the real local Unix-socket RPC test passes; root
Compose configuration parses successfully; and `git diff --check` is clean.
Buildx is not installed, so the final Compose image/browser runtime profile was
not run. The combined backend PostgreSQL/Redis coverage gate was not rerun for
this slice (its prior 2,885-test/83.42% pass remains at `5d2a937`). No provider,
ETF, or TC2000 worktree was accessed. Exact-pinned RC5 remains eligible for
isolated backtests after its four scoped checks, with forward parity separate
and no broker/real-capital authority.

Changed source/config/docs paths: `backend/app/strategy_lab_v2/application.py`,
`backend/app/strategy_lab_v2/postgres_result_materialization.py`,
`backend/app/strategy_lab_v2/search_dispatch_rpc.py`,
`backend/app/strategy_lab_v2/search_preparation_service.py`,
`backend/app/strategy_lab_v2/tests/test_application.py`,
`backend/app/strategy_lab_v2/tests/test_search_dispatch_rpc.py`,
`docker-compose.yml`, and `docs/strategy-lab-v2.md`. Updated branch records:
`ops/workstreams/feat-strategy-lab-v2/plan.yaml`, `handoff.md`,
`validation.jsonl`, and `session.json`.

Next: replace the explicit evidence-factory placeholder with reusable local
composition of the existing PostgreSQL hydrator/worker-state adapters, local
artifact/package resolvers, and operator-pinned RC evidence source; keep
canonical market-context support fail-closed pending the provider workstream's
staging contract. Then add real database-backed dispatch/replay validation and
continue portfolio, metrics, snapshot, worker, and forward acceptance.

## 2026-10-04 - Reproducible local Nautilus RC evidence build and host binding

Stable Nautilus 2.x remains unnecessary. Added
`nautilus_runtime_image/evidence_build.py`, which reconstructs a minimal Docker
context from exact `COPY` inputs, hashes those inputs plus the qualification
script and pinned base/wheel/build versions, writes the source digest into
image labels, checks the resulting image ID and labels, then runs the runtime
lifecycle and four-check simulator fixture with networking disabled, a
read-only root, and dropped Linux capabilities. It publishes evidence only
after strict payload validation and a content-addressed read-back.

The exact current-source qualification passed with Nautilus `2.0.0rc5`, Python
`3.12.4`, and Rust `1.98.1` (the release tag's toolchain pin). The four
backtest checks passed: multi-instrument accounting, native order/fill/cost,
deterministic replay, and engine lifecycle. Forward event-tape parity remains
deferred; the overall release-candidate report is still non-authoritative and
the runtime remains forbidden from broker/real-capital use. The scoped
backtest binding can consume these four checks only when the worker image
matches the exact digest.

Pins: source `sha256:cc3a13652edf026eb0c60eccbdcaca64fa3281065afb7fe0cfe2c824aade6a82`,
image `sha256:5e2c4bb2fa8013578d6761f9a3a504467c31f653c9c0025915b72e36c88df3e7`,
artifact `sha256:aca8b8b50714d13aeb5333fa8d02f310d9ececb95726a44f940e6aa327258b26`,
and conformance resolution `sha256:d5a48fb93cbebe68303f8e42255453e37a7971fa315ad0f155e09fc25ff05984`.
The artifact is currently held at the ignored local path
`.ai/runtime/strategy-lab-v2/nautilus-rc-evidence/`; its exact operator pins
are loaded using `STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_DIRECTORY`,
`STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_ARTIFACT_SHA256`,
`STRATEGY_LAB_V2_NAUTILUS_RC_SOURCE_SHA256`, and
`STRATEGY_LAB_V2_NAUTILUS_RC_IMAGE_SHA256`. Empty configuration disables this
binding; partial configuration fails closed. Search-preparation context now
has a constructor that loads this source and binds the exact image and scoped
backtest conformance together. The actual production API host factory and
dedicated preparation process/client are still not registered/implemented.

Validation: 1,247 Strategy Lab tests passed; package Ruff checks passed,
changed-file formatting passed, and MyPy passed across 349 sources. The new
image was rebuilt from current package sources, both hardened probes passed,
and the emitted artifact loaded through the operator environment configuration.
The broad backend coverage gate remains the previously recorded 2,885 tests at
83.42% on `5d2a937`; it was not rerun for this local evidence/build slice.
Buildx still limits only the final Compose/browser profile. Canonical provider
coverage and instrument metadata remain fail-closed until staging approval.

Next: register these pins/source in the local API host factory, then move
hydration and runtime-input materialization to the dedicated local
search-preparation process with an async API client. Continue remaining
portfolio, metric, snapshot, worker, and forward acceptance; do not wait for a
stable 2.x Nautilus tag.

Changed source paths: `backend/app/strategy_lab_v2/local_conformance_source.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_image/Dockerfile`,
`backend/app/strategy_lab_v2/nautilus_runtime_image/evidence_build.py`,
`backend/app/strategy_lab_v2/search_dispatch_preparation.py`,
`backend/app/strategy_lab_v2/tests/test_conformance_fixtures.py`,
`backend/app/strategy_lab_v2/tests/test_nautilus_runtime_image.py`,
`backend/app/strategy_lab_v2/tests/test_nautilus_runtime_evidence_build.py`,
`backend/app/strategy_lab_v2/tests/test_search_dispatch_preparation.py`,
`ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`,
and `ops/workstreams/feat-strategy-lab-v2/session.json`.

## 2026-10-04 - Content-addressed local Nautilus RC evidence source

Committed and pushed `52c38ce457a5d5c7e7ea5c2bcfaff9d0f4610625`. The new
`LocalNautilusRcConformanceEvidenceSource` reads only a digest-named local
artifact, verifies its raw-byte SHA-256 plus independently configured Nautilus
source and runtime-image pins, bounds file size, refuses symlinks/non-regular
files, rejects duplicate JSON keys, and reconstructs the typed RC5 probe,
fixture receipt, and conformance resolution. It does not create evidence or
grant authority by itself; the configured artifact and pins remain an
operator-controlled trust boundary, and the worker context must still match
the exact image digest.

Nautilus stable 2.x is not a prerequisite. Exact-pinned 2.0.0rc5 can qualify
isolated local backtests after the four backtest checks; forward event-tape
parity remains separate, and the pre-release is barred from broker/real-capital
use. The overall RC report remains non-authoritative when forward parity is
deferred; only the backtest-scoped binding can grant local backtest authority.
The existing local RC5 image passed the four checks but lacks source-build
provenance, so it is runtime-fixture evidence, not a reproducible authoritative
artifact.

At the exact implementation tip, all 1,237 Strategy Lab tests passed; Ruff and
MyPy across 347 sources passed. The combined backend gate remains 2,885 tests
at 83.42% from implementation commit `5d2a937`; it was not rerun for this
reader-only slice. The production host has not yet registered an artifact
publisher/source or dedicated search-preparation process/client. Canonical
provider coverage and instrument metadata remain fail-closed until their
approved staging contract is available. Buildx limits only full
Compose/browser validation.

Next: generate/pin evidence from an exact reproducible RC5 image build, wire
the source through the local host factory, and move hydration/materialization
behind a dedicated local preparation process and async API client. Continue the
remaining backend acceptance areas; do not wait for stable 2.x.

Changed paths: `backend/app/strategy_lab_v2/local_conformance_source.py`,
`backend/app/strategy_lab_v2/tests/test_conformance_fixtures.py`,
`ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-04 - Currency-separated native OOS position metrics

Official Nautilus OOS results now include closed-position win/loss/break-even
counts and rates per native P&L currency, gross winning P&L, gross losing-P&L
magnitude, and per-currency position profit factor. These supplement the
existing sign-only cross-currency quality rates and per-currency net P&L; no
amounts are combined or FX-converted. Currency-level results fail closed when
any OOS-closed position has missing realized P&L or close-time coverage, and a
profit factor without any losing position is explicitly null rather than
misstated as zero or infinity. Every native report metric now records the
34-digit ROUND_HALF_EVEN arithmetic context. The metric definition version is
bumped to v8 so changed formulas cannot collide with v7 result identities.

Implementation commit: `fde37514c4a0c09db17b322d98d220e7a02eef59`.
The implementation and its workstream checkpoint were pushed successfully;
the verified remote branch tip is `fc88256816314ecc74fe968d7db67a973649df5c`.

Validation: all 1,216 Strategy Lab v2 tests passed; package Ruff, format checks
for four changed Python files, MyPy across 350 package/runtime sources, and
`git diff --check` passed. The only `metrics.py` change is the one-line catalog
version bump; unrelated formatter reflows in that pre-existing file were
preserved. The exact-tip Docker probe could not be reached from this session:
`docker info` returned permission denied for `/var/run/docker.sock`. This blocks
only image-backed and full Compose/browser acceptance, not local implementation.
Stable Nautilus 2.x remains unnecessary; exact-pinned RC5 is eligible for local
backtests after its four checks, while forward parity and real-capital/broker
prohibitions remain unchanged.

Changed paths:

- `backend/app/strategy_lab_v2/metrics.py`
- `backend/app/strategy_lab_v2/nautilus_result_metrics.py`
- `backend/app/strategy_lab_v2/tests/test_core.py`
- `backend/app/strategy_lab_v2/tests/test_nautilus_result_metrics.py`
- `backend/app/strategy_lab_v2/tests/test_observations.py`
- `docs/strategy-lab-v2.md`
- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

Next: continue the remaining API, worker, and forward acceptance gaps without
inventing provider, lease, capability, or conformance inputs; finish the
exact-tip Docker/Compose/browser profile when Docker API access is available.

## 2026-10-04 - Native OOS position realized-P&L quality metrics

Official Nautilus OOS metric sets now include position-level realized-P&L
win/loss/break-even counts and rates from closed native position records. The
records are filtered by the half-open OOS close-time window. Sign-based quality
rates remain meaningful across native currencies without summing or converting
amounts, and are withheld when close-time coverage or any OOS-closed position's
realized-P&L value is incomplete. The existing per-currency realized-P&L totals
remain separately reported.

Tests cover OOS boundary exclusion, mixed native currencies, winning/losing/
break-even positions, and fail-closed behavior for missing realized P&L.
Validation: 1,215 Strategy Lab v2 tests passed; the focused native metric tests,
Ruff, formatting, MyPy across 350 package/runtime sources, and `git diff
--check` passed. Stable Nautilus 2.x is not required: exact-pinned RC5 remains
eligible for isolated local backtests after conformance, while pre-releases
remain barred from broker and real-capital use. No external dependency blocks
package-owned implementation; the SSH key issue affects remote publishing
only. The full Docker/Compose/browser profile remains a required completion
gate.

Next: continue the remaining API, worker, and forward acceptance gaps, then
complete the full-stack/browser validation profile at the exact branch tip.

Changed paths:

- `backend/app/strategy_lab_v2/nautilus_result_metrics.py`
- `backend/app/strategy_lab_v2/tests/test_nautilus_result_metrics.py`
- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-10-04 - Owner-scoped typed-resource dependency validation

`PostgresStrategyLabV2Adapter.create_resource()` now verifies the persisted
typed dependency graph through owner-scoped reads before it writes. Package
and portfolio strategy references must resolve for the authenticated owner.
Experiments must resolve their portfolio, strategies, snapshot, and optional
strategy packages; experiment strategy membership must match the portfolio,
and package bindings must match the bound strategy. Trials must resolve their
experiment and snapshot, match the experiment snapshot, and carry the same
preflight fingerprint as the frozen snapshot. Attempts must reference an
existing trial. Metric sets must reference an existing trial and an attempt
belonging to that same trial. Forward instances must reference an existing
portfolio and warm-up snapshot. Missing and foreign-owner fingerprints return
the same fail-closed validation response.

The owner-scoped reader now resolves a run attempt by its stable domain
`attempt_id`, which metric lineage uses instead of an API resource ID. Exercising
persisted trial rehydration also uncovered that normalization writes an
explicit `evaluation_window: null` while the inverse path rejected it; null is
now restored as `None`.

The application boundary test creates and validates a strategy → package →
portfolio → snapshot → experiment → trial → attempt → metric-set graph and a
forward instance, plus a cross-owner package reference rejection. Validation:
all 1,213 Strategy Lab v2 tests passed; package/runtime Ruff, formatting, and
MyPy passed (350 sources); the branch workstream validator and `git diff
--check` passed. Docker is available via the managed runner and this worktree
currently owns no containers or volumes. The full PostgreSQL/Redis/Compose and
browser profile has not yet been run; the repository-wide testcontainers
backend integration suite passed, though it does not directly exercise this
feature's new resource writer path. Nautilus 2.0.0rc5 is the current upstream
2.x release candidate and remains valid for isolated local backtests after
conformance; no stable release is required. The SSH agent API is inaccessible
in this session, so publishing is still an operational hold only.

Next: continue package-owned API, worker, and forward acceptance work, then run
the Docker-backed database/Redis/Compose and full-stack/browser profile at the
exact branch tip. Forward-shadow qualification remains separately gated by
event-tape parity; prereleases remain prohibited from broker/real-capital use.

Changed paths:

- `backend/app/strategy_lab_v2/application.py`
- `backend/app/strategy_lab_v2/postgres_resources.py`
- `backend/app/strategy_lab_v2/resource_domains.py`
- `backend/app/strategy_lab_v2/tests/test_application.py`
- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-10-04 - Owner-authenticated Nautilus OOS terminal publication

The actual worker-completion evidence path now consumes the parent-owned exact
Nautilus conformance evidence and rechecks it against the immutable execution
plan. It hydrates the attempt's domain graph through the authenticated owner,
checks that trial/portfolio/snapshot/attempt lineage matches the executed input,
re-verifies native account-equity and execution-report bytes, builds OOS metrics
and the result manifest, publishes each result artifact with byte-integrity
evidence, and creates the scoped result-publication plan. Deterministic
validation failures are rejected instead of retried forever; transient lookup
or storage failures remain retryable. Terminal result identity is tied to the
process receipt timestamp so callback redelivery cannot change it.

The complete terminal writer is now exercised through success and a later
callback redelivery using in-memory ports backed by the pure runtime,
outcome/progress, result-completion, and worker-settlement contracts. This
exposed a retry mismatch: an artifact's publication action naturally changes
from `create_if_absent` to `reuse_existing` after the first write. Completion
identity now uses the stable manifest/content/length/storage commit key rather
than that transient action; runtime, terminal, release, and completion times
also come from the immutable process receipt, and the returned terminal digest
is based on persisted identities rather than changing replay decisions. The
test confirms both writes complete with the same receipt digest and create only
one completion and settlement record.

The existing terminal writer now receives this evidence through the default
worker callback composition. A successful local RC5-shaped receipt test checks
the published artifacts, official local-backtest provenance, OOS fill/cost
metrics, stable result identity after callback redelivery, and permanent
validation rejection. This is an application-boundary test, not a complete
PostgreSQL/Redis/Compose worker acceptance test. Exact RC5's isolated fixture
has separately passed the four local-backtest checks; stable Nautilus 2.x is not
a prerequisite. Pre-releases remain unable to connect to brokers or control
real capital, and forward-shadow qualification still has its separate
event-tape-parity gate.

Validation: all 1,213 Strategy Lab v2 tests passed; Ruff passed; all 11
changed Python files passed formatting; MyPy found no issues across 350
package/runtime sources; the workstream validator passed; and `git diff
--check` passed. The current environment denies access to `/var/run/docker.sock`,
so image-backed revalidation and the required full-stack/browser profile remain
open. SSH public-key/askpass failure still prevents remote publication only.

No external dependency blocks the next owned coding slice. Remaining work
includes owner-scoped typed-domain relationship validation during resource
creation, other domain-backed mutation and worker-runtime gaps, forward parity,
and final Docker-backed acceptance. Provider/ETF/TC2000 staging gates apply
only to consuming their contracts on shared paths.

Changed paths: worker request conformance binding, native OOS terminal
materialization and publication, worker callback composition, permanent
evidence-failure handling, and their package-owned tests.

Next: validate immutable resource dependencies against the authenticated
principal's persisted domain graph, failing closed without revealing
cross-owner existence; then expand validation to snapshot/trial/attempt/result
relationships and continue remaining owned acceptance gaps. Do not wait for
stable Nautilus 2.x.

## 2026-10-04 - Native OOS reports, metrics, and RC5 qualification probe

The host now streams and verifies the exact content-addressed native Nautilus
account, order, fill, and position reports, combines their OOS-scoped
observations with the verified account-equity trace, and builds a versioned
metric set bound to the same trial, attempt, portfolio, snapshot, tape, and
evaluation window. A Strategy Lab-specific result materializer publishes both
artifact manifests and the metric set through the immutable result path with
retry-safe identity checks. Structured native report values are preserved as
canonical JSON under nesting, value-count, and row-byte bounds. The account
report call is scoped to the configured Nautilus venue, as required by RC5.

The exact-pinned Nautilus `2.0.0rc5` runtime image was built from the pinned
base digest and wheel SHA-256, then run with networking disabled, a read-only
root, dropped capabilities, a non-root UID, bounded memory/CPU/PIDs, and a
worktree ownership label. The native fixtures passed lifecycle, two-instrument
accounting, order/fill/fee evidence, and deterministic replay. The actual native
Parquet report schemas and three OOS equity observations were captured and
host-verified. This is diagnostic conformance evidence only: the fixture
receipt explicitly remains non-authoritative until the exact build and fixture
fingerprints are installed through the formal conformance/provenance/publication
path. Forward event-tape parity is still separate.

Observed report schemas contained 2 account rows, 1 fill, 1 order, and 1 open
position. RC5 columns used for half-open OOS filtering are `fills.ts_event`,
`orders.ts_init`, and `positions.ts_opened`/`ts_closed`; account reports must be
scoped with the configured native venue (`SIM`). Nested position `events`,
order `commissions`, and trade/order ID sequences require structured-value
preservation in the bounded report artifact.

Validation: all 1,208 Strategy Lab v2 package tests passed; Ruff passed; MyPy
reported no issues across 348 package sources; all 19 changed Python files
passed formatting; and `git diff --check` passed. The repository's scoped Docker
cleanup removed the temporary image after the probe and reported no containers,
volumes, or retained resources. The legacy Docker builder transmitted a 2.1 GB
backend build context because buildx is unavailable; this is local build
overhead, not a product gate.

Stable Nautilus 2.x is not a prerequisite. `plan.yaml` accepts the exact-pinned
2.x release candidate after applicable conformance for local backtesting; the
pre-release still cannot connect to brokers or control real capital. No
external dependency blocks the next owned implementation slice. The
previously recorded SSH askpass/public-key failure affects publishing only and
should be rechecked during the next push. Provider/ETF/TC2000 staging gates
apply only to their shared-path consumption.

Changed paths: package-owned `nautilus_native_reports.py`,
`nautilus_result_metrics.py`, `nautilus_result_materialization.py`, the
isolated runtime/adapter wiring and image allowlist, corresponding tests, and
this branch workstream.

Next: wire `materialize_nautilus_oos_run_result` into the actual worker
terminal-evidence callback; turn the passing exact RC5 fixture output into
immutable `EngineConformanceEvidence` bound to source, wheel, image, and
execution-plan digests; then proceed through remaining API/worker/metric
acceptance and the full-stack/browser profile. Keep authoritative backtest
publication, forward parity, and full feature completion distinct gates.

## 2026-10-04 - OOS native-equity metric-set materialization

The verified native OOS account-equity trace now has a bounded-memory metric
calculation and typed `MetricSet` builder. The first scoring-window callback
mark is captured before strategy invocation and is used as the OOS opening
valuation; the original portfolio funding amount is not reused, so warm-up
returns cannot leak into the scoring result. The versioned v7 metric family
emits cumulative net P&L/return and event-mark drawdown, duration, ulcer, and
recovery summaries. Annualized, calendar-dependent, and event-cadence-sensitive
risk statistics remain explicitly null with reasons until an actual sampling
or calendar basis is provided. Every emitted value references the native trace
digest, and the metric set binds the same trial and attempt as its receipt.

Implementation commit: `97ecadaf2a7c1fce49c67f15e2956d2aa87cc30c`.
Validation: all 1,198 Strategy Lab v2 tests passed; Ruff lint passed; MyPy
reported no issues across 339 package sources; all seven changed Python files
passed formatting; `git diff --check` passed. Focused OOS metric/materializer
tests passed alongside the package suite.

This slice produces equity-derived metrics only; it does not yet bind native
order/fill/position/cost reports into the same `MetricSet` or finish
`RunResultManifest` construction at the worker boundary. The current branch
plan allows exact-pinned Nautilus 2.x prereleases for local authoritative
backtests after conformance; stable 2.x is not a prerequisite. I reconciled a
stale `plan.yaml` conformance progress note that had incorrectly required a
published stable release; the AC-NAUTILUS criterion and runtime gate already
allow release candidates with a valid exact isolated pin and complete checks.
The external
Docker socket hold still prevents exact-image/full-stack validation, and SSH
askpass/key authentication still prevents publishing. Neither blocks the next
owned backend implementation slice.
The elevated push attempt for
`1e3a861454f3c77bdac5efbb6957103f56f13238..226d891f08bed910e33dd017459d267916491bfb`
failed because `/usr/bin/ssh-askpass` is absent and GitHub rejected the
configured SSH key with `Permission denied (publickey)`. The cached remote ref
remains `1e3a861454f3c77bdac5efbb6957103f56f13238`; no alternate credential
path was probed.

Next: export and host-verify native orders, fills, positions, and cost evidence;
feed those reports plus the OOS equity series into the official metric-set and
result-manifest path; then run the exact-pinned RC5 probe and full-stack/browser
profile when Docker access is available.

## 2026-10-04 - Native OOS account-equity result artifact

The package-owned Nautilus execution path now captures the native account
equity and cash balance at each canonical market callback into bounded,
compressed Parquet. Warm-up rows are excluded and marks are constrained to the
trial's half-open scoring window. The receipt binds the content digest and row
count to trial, attempt, portfolio, frozen snapshot, source tape, evaluation
window, currency, and initial capital. Before returning a successful result,
the host verifies the receipt, Parquet schema/metadata, exact bytes, OOS scope,
and every mark against the frozen native event stream; any mismatch fails the
run closed. The verified artifact can then be published through the immutable
artifact service. PyArrow is pinned only in the isolated RC runtime image; the
legacy backend environment remains unchanged.

Validation at implementation commit `c59ff66d3c8d671762caa9de4d71111bdb101a42`:
all 1,193 Strategy Lab v2 tests passed; Ruff passed; MyPy reported no issues
across 337 package sources; all 15 changed Python files passed formatting;
`git diff --check` passed; and the workstream validator passed all 30 records.
The exact-pinned image probe and full Compose/browser profile remain unrun:
Docker access is denied at `/var/run/docker.sock`. The ordinary branch
validator additionally hit a read-only lock under `.ai/runtime` outside this
assigned worktree; direct validation of all 30 records passed.

The implementation commit was created locally. Publishing the current branch
failed because `/usr/bin/ssh-askpass` is absent and GitHub rejected the
configured key with `Permission denied (publickey)`; the cached remote-tracking
ref remains `1e3a861454f3c77bdac5efbb6957103f56f13238`, and the live remote could
not be refreshed. No alternate credential path was probed.

Stable Nautilus 2.x is not required: `plan.yaml` permits an exact-pinned
pre-release for local backtests after the applicable conformance checks, while
prohibiting pre-releases from broker or real-capital control. The saved goal's
stable-only phrase is stale; this branch plan remains authoritative. The
remaining code work is to bind native orders/fills/positions/cost evidence and
the OOS equity series into official versioned metrics and the result manifest.
Annualization must use an explicitly declared sampling/calendar basis, never an
assumption about arbitrary event frequency. Provider/ETF/TC2000 shared-path
consumption remains gated on those approved branches reaching staging; that
does not block the owned backend work.

Next: connect verified native result artifacts to official OOS MetricSet and
RunResultManifest construction, then run the exact-pinned windowed
multi-component probe and final full-stack/browser profile when Docker is
accessible.

## 2026-10-04 - Evaluation-window warm-up and OOS execution gate

The package-owned Nautilus trial path now carries the exact immutable
`EvaluationWindow` into engine input v4. Assembly restricts both the native
event tape and strategy-context history to `[warmup_start or start, end)`,
requires at least one event inside the scoring interval, and preserves
streaming/disk-backed operation for frozen tapes. The native callback still
invokes the strategy during warm-up so its local state can initialize, but
removes warm-up intents before native order routing and before invocation
results are emitted. Events outside the authenticated input interval fail
closed. The legacy 1.226.0 backend environment remains untouched.

Changed paths are the engine-neutral window contract and isolated Nautilus
input/bridge, plus their focused tests:

```text
backend/app/strategy_lab_v2/contracts.py
backend/app/strategy_lab_v2/nautilus_engine_input.py
backend/app/strategy_lab_v2/nautilus_runtime_adapter.py
backend/app/strategy_lab_v2/nautilus_runtime_adapter_probe.py
backend/app/strategy_lab_v2/nautilus_runtime_bundle.py
backend/app/strategy_lab_v2/nautilus_strategy_bridge.py
backend/app/strategy_lab_v2/nautilus_trial_assembly.py
backend/app/strategy_lab_v2/tests/test_nautilus_engine_input.py
backend/app/strategy_lab_v2/tests/test_nautilus_runtime_adapter.py
backend/app/strategy_lab_v2/tests/test_nautilus_strategy_bridge.py
backend/app/strategy_lab_v2/tests/test_nautilus_trial_assembly.py
```

Implementation commit: `91e838a20d502de5426bfe8188d5e7fbb47e789b`.
Validation: 1,188 Strategy Lab v2 tests passed; Ruff lint passed; all 11
changed Python files passed formatting; MyPy passed across 341 source files;
and `git diff --check` passed. A broader formatter check over the entire
package was also attempted and reported 188 untouched existing files that
would be reformatted; it did not modify them. The exact-pinned RC5 image probe
could not be rerun because Docker access remains denied at
`/var/run/docker.sock`. That blocks native image-backed validation and the
final Compose/browser profile, not local feature implementation. OOS-native
equity/result extraction and official versioned metrics remain a subsequent
implementation slice; this commit gates simulator events and orders, not the
full metrics acceptance criterion.

No stable Nautilus 2.x release is required: `plan.yaml` permits the exact
2.0.0rc5 pin after applicable conformance and bars prereleases from broker or
real-capital control. Provider, ETF, and TC2000 shared-path use remains gated
until their work reaches staging. The configured GitHub SSH key has also
previously failed with `Permission denied (publickey)`. The elevated,
user-authorized push of the implementation range
`1e3a861454f3c77bdac5efbb6957103f56f13238..91e838a20d502de5426bfe8188d5e7fbb47e789b`
failed. A second elevated push retry covering the current branch range
`1e3a861454f3c77bdac5efbb6957103f56f13238..33828aa99bef3b077176f166098c0268cc458ac1`
also failed because `/usr/bin/ssh-askpass` is missing and GitHub rejected the
configured key. The remote is unchanged; no alternate credential path was
probed. Local commits and implementation remain independent of this transport
issue.

Next: implement native result/equity extraction bound to the same evaluation
window, with OOS-only official metrics; rerun the exact-pinned RC5 windowed,
multi-component callback/fill probe when Docker API access is available.

## 2026-10-04 - Multi-strategy trial materialization

Closed the gap between the multi-component Nautilus callback and host-side
trial assembly. The assembler now accepts one digest-verified package/manifest/
source input per portfolio component, validates every component against the
experiment and shared frozen-tape dependency binding, and emits one ordered,
authenticated component-context artifact. The owner materializer resolves all
component packages, builds a canonical union data-manifest for the shared tape,
and the worker handoff authenticates the complete package/source/dependency set
under one runtime ABI. Single-strategy package/source identities remain
backward-compatible. This does not yet qualify the new assembled bundle against
the pinned RC5 image; that native callback/fill check remains gated by Docker
API access.

Changed files:

```text
backend/app/strategy_lab_v2/nautilus_trial_assembly.py
backend/app/strategy_lab_v2/nautilus_trial_materializer.py
backend/app/strategy_lab_v2/search_worker_handoff.py
backend/app/strategy_lab_v2/tests/test_nautilus_trial_assembly.py
backend/app/strategy_lab_v2/tests/test_nautilus_trial_materializer.py
backend/app/strategy_lab_v2/tests/test_search_worker_handoff.py
```

Implementation commit: `6ccb45332978e13e82242ae588070fb4e684663f`. Validation at
that commit: all 1,184 Strategy Lab v2 tests pass;
Ruff and formatting checks pass; MyPy reports no issues across 341 package and
runtime sources; and `git diff --check` is clean. Push of
`1e3a861454f3c77bdac5efbb6957103f56f13238..6ccb45332978e13e82242ae588070fb4e684663f`
failed: `/usr/bin/ssh-askpass` is missing and GitHub rejected the configured
SSH key (`Permission denied (publickey)`). The remote remains at
`1e3a861454f3c77bdac5efbb6957103f56f13238`; this is a publication hold, not a
package-owned coding blocker. No alternate credential path was probed.

The operational workstream checkpoint was committed locally and its publish
retry for
`1e3a861454f3c77bdac5efbb6957103f56f13238..342fc346e4573588cfd898a4020aa291057c30b5`
failed with the same missing-askpass/`Permission denied (publickey)` error. The
remote remains unchanged. The enclosing workstream-record commit is verified
externally with `git rev-parse`; `session.json` retains the last known product
implementation SHA to avoid a self-referential commit hash.

The Nautilus release-label question is not a blocker: the plan explicitly
permits a pinned pre-release for local backtests after conformance; the current
RC5 receipt covers the four simulator checks, while forward parity remains
separate. The saved Goal description still says “stable v2,” which conflicts
with the branch plan/acceptance contract; follow the branch-owned plan, which
allows exact-pinned pre-releases and does not require waiting for a stable tag.
The latest Docker API check also failed with permission denied at
`/var/run/docker.sock`; the existing RC5 receipt remains valid for its recorded
probe scope, but the new multi-component bundle still needs image-backed
validation when Docker is accessible.

Next: implement evaluation-window warm-up/OOS gating in the package-owned
Nautilus trial path so training history informs state without leaking into OOS
metrics; retry the exact-pinned RC5 multi-component callback/fill probe when
Docker API access is available.

## 2026-10-04 - Exercise the mixed-intent bridge routing seam directly

Extracted the native callback's target conversion and combined order-risk path
into `_route_component_callback_orders(...)`, which is now called by the real
bridge callback and its focused tests. The tests no longer reimplement the
combination sequence: they exercise this production seam for target-plus-raw
gross-limit rejection/approval and for a target-only interim net breach that
is offset by a same-event component short. Standalone target allocation still
rejects the same net breach by default; the callback's combined router is the
only order-submission gate.

Validation: all 1,181 Strategy Lab v2 tests pass; package Ruff, changed-file
formatting, MyPy across 341 sources, and `git diff --check` pass. The current
workstream validator also passes. This remains package-local evidence, not a
native Nautilus probe: Docker API access is still denied, so the exact-pinned
RC5 image-backed callback/fill reconciliation check remains outstanding.
Stable Nautilus 2.x is not required; the plan accepts an exact-pinned
pre-release for local backtests after conformance and forbids it from
broker/real-capital use.

No package-owned coding blocker is recorded. Continue the remaining backend
acceptance gaps without weakening fail-closed handling for products that lack
exact native contract/account risk inputs. Re-run the RC5 multi-component
callback and fill probe when Docker is accessible. The latest successful code
checkpoint is `5f790de06e3055144df73f6a451a76f08a316ef5`.

Files changed in this slice:

```text
backend/app/strategy_lab_v2/nautilus_strategy_bridge.py
backend/app/strategy_lab_v2/tests/test_nautilus_target_allocation.py
ops/workstreams/feat-strategy-lab-v2/handoff.md
ops/workstreams/feat-strategy-lab-v2/session.json
ops/workstreams/feat-strategy-lab-v2/validation.jsonl
```

## 2026-10-04 - Defer mixed-intent risk to the shared order gate

Closed a gap in same-event mixed raw/target execution. The native bridge now
asks target allocation to produce candidate orders without treating that
intermediate target-only portfolio snapshot as the final shared-risk decision;
the combined raw-plus-target order router remains the required fail-closed
gate before any native order submission. Standalone target-allocation callers
still reject shared-risk breaches by default. Regression tests cover (1) a
target batch with a raw order crossing a gross limit, rejected at 20.5% and
accepted at 21%, and (2) a target-only interim net breach that is offset by a
same-event raw short order and accepted by the final combined gate at 40% gross,
zero net exposure.

Validation: all 1,181 Strategy Lab v2 tests pass; package Ruff and changed-file
formatting pass; MyPy reports no issues across 341 package/runtime sources;
`git diff --check` and the workstream validator pass. The exact-pinned Nautilus
2.0.0rc5 image-backed bridge/fill probe remains unrun because the current
sandbox denies Docker API access. Stable Nautilus 2.x is not a release gate:
the plan permits the exact-pinned pre-release for local backtests after
applicable conformance, and prohibits pre-releases from broker/real-capital
use. No package-local implementation is blocked by that validation boundary.

Pushing the exact range
`1e3a861454f3c77bdac5efbb6957103f56f13238..b61956be73e1513e25053eed61efe54cd9a1c28c`
failed because `/usr/bin/ssh-askpass` is missing and the configured SSH key was
rejected (`Permission denied (publickey)`). This does not block local commits
or coding.
Provider, ETF, and TC2000 shared-path integrations still wait for their approved
work to reach staging and semantic reconciliation, but that does not block
owned-path Strategy Lab backend work. Next: continue remaining package-owned
acceptance gaps and run the RC5 mixed-component callback/fill probe when Docker
API access is available. This slice is committed as
`0d1d6e27caa696088521abe9867bc79e6a0b1669`.

Files changed in this slice:

```text
backend/app/strategy_lab_v2/nautilus_strategy_bridge.py
backend/app/strategy_lab_v2/nautilus_target_allocation.py
backend/app/strategy_lab_v2/tests/test_nautilus_target_allocation.py
ops/workstreams/feat-strategy-lab-v2/handoff.md
ops/workstreams/feat-strategy-lab-v2/session.json
ops/workstreams/feat-strategy-lab-v2/validation.jsonl
```

## 2026-10-04 - Multi-component native bridge orchestration

Extended the native bridge to bind every portfolio component to its own
authenticated source/manifest/parameter binding and invocation session. The
component event-tape verifier now validates each rolling history on the shared
native stream, groups callbacks at the same event time, and invokes them in
portfolio-priority order. A callback collects all component results before
submission; any failed result suppresses the entire callback's order batch.
Raw orders and target-position intents from different components are combined
after one target-allocation pass and pass through one shared order-risk decision.
Mixing raw and target intents inside a single component callback remains
fail-closed. Fill events now update component-attributed quantities, with
partial-order tracking and reconciliation against native net positions.

Validation: all 1,179 Strategy Lab v2 tests pass; Ruff, changed-file formatting,
MyPy across 341 package/runtime sources, and `git diff --check` pass. A bridge
regression uses a minimal Nautilus test double to verify two authenticated
component sessions execute on one callback in priority order, including
fail-closed behavior when one strategy result fails. It is not an image-backed
Nautilus compatibility or native fill/economics probe. The current sandbox
still denies Docker API access, so rerunning the exact RC5 runtime against this
new callback path remains a validation task. Existing RC5 receipts establish
only their previously recorded single-strategy probe scope.

Stable Nautilus 2.x is not a prerequisite: the branch plan allows an exact-pinned
pre-release for local backtests after applicable conformance, and excludes
pre-releases from broker/real-capital use. Package-local implementation is not
blocked by the Docker validation boundary. Next: execute a multi-component RC5
probe with mixed raw/target intents, native order/fill callbacks, and component
quantity/exposure reconciliation; adjust only on observed runtime evidence.
Publisher SSH authentication remains an operational hold on the unpublished
branch range, not a development blocker. This implementation slice is committed
locally as `0973cde2f2c12f894458557178d4f87e31164ea4`.

Files changed in this slice:

```text
backend/app/strategy_lab_v2/nautilus_strategy_bridge.py
backend/app/strategy_lab_v2/tests/test_nautilus_strategy_bridge.py
ops/workstreams/feat-strategy-lab-v2/handoff.md
ops/workstreams/feat-strategy-lab-v2/session.json
ops/workstreams/feat-strategy-lab-v2/validation.jsonl
```

## 2026-10-04 - Component context-stream artifact and CLI wiring

Added a bounded, digest-checked component context-stream protocol and immutable
artifact reference, bundle schema v4, and CLI/adapter propagation of per-
component context counts. The native bridge verifies those contexts against
their authenticated strategy binding, but deliberately still accepts only one
portfolio component; this is transport and one-component runtime wiring, not
multi-strategy execution.

Validation: all 1,171 Strategy Lab v2 tests pass; the focused protocol, bundle,
CLI, adapter, and bridge set passes 62 tests; Ruff and formatting pass; MyPy
passes across 341 package/runtime sources; and `git diff --check` is clean.
The current sandbox denies access to the Docker API, so this slice has not had
a new image-backed RC5 run. Prior RC5 checks remain limited to their recorded
probe scope and non-authoritative.

There is no Nautilus release blocker: the plan allows exact-pinned pre-releases
for isolated local backtests, while barring them from broker/real-capital use.
There is also no blocker to continuing package-owned code. The next product gap
is to accept every authenticated component binding in the native bridge,
schedule same-event invocations, route combined raw and target intents through
shared risk, and maintain fill-derived component position attribution. Docker
access will be needed for the recorded final integration profile; provider,
ETF, and TC2000 staging gates apply only to their later shared-path work.
This slice is committed locally as `3eec8f11bd4bde0c6e14ae3fc4d8ac5a01f7eac9`.
The branch is 11 commits ahead of tracking ref
`1e3a861454f3c77bdac5efbb6957103f56f13238`; the authorized
`rtk git push origin feat/strategy-lab-v2` retry failed because `ssh-askpass` is
missing and GitHub rejected the configured SSH key (`Permission denied
(publickey)`). No alternate credential path was attempted. This is a publish
hold only and does not stop further local feature work.

The global session-claim lock and runtime-allocation registry are read-only in
the current sandbox, so the repository-managed context/progress helpers cannot
write their coordination state. The existing session claim remains valid;
branch-owned progress and validation records are being maintained directly in
this workstream without changing global workflow state.

Files changed in this slice:

```text
backend/app/strategy_lab_v2/nautilus_runtime_adapter.py
backend/app/strategy_lab_v2/nautilus_runtime_bundle.py
backend/app/strategy_lab_v2/nautilus_runtime_cli.py
backend/app/strategy_lab_v2/nautilus_runtime_protocol.py
backend/app/strategy_lab_v2/nautilus_strategy_bridge.py
backend/app/strategy_lab_v2/tests/test_nautilus_runtime_cli.py
backend/app/strategy_lab_v2/tests/test_strategy_runtime_protocol.py
backend/app/strategy_lab_v2/tests/test_nautilus_target_allocation.py
backend/strategy_runtime/__init__.py
backend/strategy_runtime/protocol.py
ops/workstreams/feat-strategy-lab-v2/handoff.md
ops/workstreams/feat-strategy-lab-v2/session.json
ops/workstreams/feat-strategy-lab-v2/validation.jsonl
```

## 2026-10-04 - Shared multi-component target allocation

Added `resolve_nautilus_component_target_position_batches(...)` as the shared
target-intent path for simultaneous portfolio components. It constructs one
allocation/risk snapshot, translates approved component targets to lot-sized
orders, preserves output grouping by component, and requires both component
exposure and signed-quantity ledgers to reconcile exactly to the native
account. Priority-policy lower-priority targets remain explicitly rejected by
the allocation result; other target rejections and aggregate risk breaches
fail closed. This is a reusable allocation slice, not end-to-end multi-strategy
execution: trial assembly and the native bridge still accept one strategy and
one context stream, and fill-driven component attribution is still required.

Validation at implementation commit `11215387d09571a8f844e7031883854681d0239b`:
all 1,168 Strategy Lab v2 tests passed; Ruff and format checks passed for the
two changed Python files; MyPy passed for the changed source module; and
`git diff --check` passed. The local commit is clean. Push to
`origin/feat/strategy-lab-v2` failed with `ssh_askpass: exec(/usr/bin/ssh-askpass):
No such file or directory` followed by `Permission denied (publickey)`. This is
a transport/authentication hold only; no alternate HTTPS credentials or
workaround were probed. At the time of the attempt, the feature branch was nine
commits ahead of remote `1e3a861454f3c77bdac5efbb6957103f56f13238`.
The checkpoint helper's dirty-path formatter also dropped the first character
of the handoff path; the workstream record was corrected to the actual `ops/`
path. The generic helper was left unchanged on this feature branch.

Stable Nautilus v2 remains unnecessary for local implementation. The branch
plan explicitly accepts an exact-pinned pre-release after conformance; the
isolated RC5 runtime remains local-only and its receipts remain
non-authoritative pending full execution/publication conformance. There is no
external dependency blocking continued package-owned work. Only 3/18 goal
acceptance areas are currently recorded complete. Provider/ETF/TC2000 staging
gates still apply to their later shared-path integrations, not this isolated
allocation logic.

Next: carry one authenticated context stream per component through the runtime
bundle, CLI, and bridge; schedule same-event callbacks; combine raw and target
orders under one shared decision; then maintain component quantities/exposure
from native fills before enabling multi-component trial assembly.

Files changed in this slice:

```text
backend/app/strategy_lab_v2/nautilus_target_allocation.py
backend/app/strategy_lab_v2/tests/test_nautilus_target_allocation.py
ops/workstreams/feat-strategy-lab-v2/session.json
ops/workstreams/feat-strategy-lab-v2/handoff.md
ops/workstreams/feat-strategy-lab-v2/validation.jsonl
```

## 2026-10-04 - Authenticated component strategy input bindings

Versioned the isolated engine input contract to v3 and added a canonical,
digest-bound strategy binding for every portfolio component: component and
strategy identities, source and manifest digests, entrypoint, parameter digest,
and intent limit. The runtime bundle emits those bindings; strict decoding
requires unique, complete component coverage and verifies the legacy single-
strategy anchor. The runtime-safe binding codec is copied explicitly into the
Nautilus image, avoiding imports of backend-only event-tape assembly code.
Invocation source, manifest, strategy identity, parameters, entrypoint, and
intent limits are checked against the binding before callbacks proceed.

This is the authenticated input seam, not yet multi-strategy execution. The
native bridge still accepts one binding and one invocation stream; a portfolio
with multiple components is deliberately rejected there until each component
has its own serialized context stream and same-event intents can be combined
under one shared allocation/risk decision.

Validation: all 1,164 Strategy Lab v2 tests pass; Ruff and formatting pass;
MyPy passes across 341 package/runtime sources. The exact-pinned Nautilus
`2.0.0rc5` image `sha256:9a09ced47208d2168941414555400b9d513c91d7d1c3abaa9449ff7808acb11e`
passes the authenticated context-stream probe and native deterministic replay,
single/multi-instrument accounting, orders/fills/costs, lifecycle, target
allocation, and raw-order shared-risk probes in a network-disabled, read-only,
unprivileged container. Receipts remain non-authoritative; forward event-tape
parity remains deferred. The temporary validation image was removed after the
probe. Stable Nautilus 2.x is not required: the plan explicitly accepts an
exact-pinned pre-release for isolated local backtests, while barring it from
broker/real-capital use.

No external release or upstream event blocks package-owned work. Provider,
ETF, and TC2000 staging contracts gate only their later shared-path
integrations. Remote publication is separate from implementation: the previous
configured key-only GitHub SSH push failed with `Permission denied (publickey)`,
and the current sandbox cannot query the SSH agent (`Operation not permitted`).
This does not prevent local development or commits.

Next: extend the input artifact and runtime CLI to carry one invocation-context
stream per component, feed them through the deterministic callback scheduler,
then aggregate same-event intent batches into one shared risk decision and
preserve component attribution for native orders, fills, and positions.

Files changed in this slice:

```text
backend/app/strategy_lab_v2/nautilus_engine_input.py
backend/app/strategy_lab_v2/nautilus_runtime_adapter.py
backend/app/strategy_lab_v2/nautilus_runtime_adapter_probe.py
backend/app/strategy_lab_v2/nautilus_runtime_bundle.py
backend/app/strategy_lab_v2/nautilus_strategy_binding.py
backend/app/strategy_lab_v2/nautilus_strategy_bridge.py
backend/app/strategy_lab_v2/nautilus_runtime_image/Dockerfile
backend/app/strategy_lab_v2/tests/test_nautilus_engine_input.py
backend/app/strategy_lab_v2/tests/test_nautilus_runtime_adapter.py
ops/workstreams/feat-strategy-lab-v2/handoff.md
ops/workstreams/feat-strategy-lab-v2/validation.jsonl
```

## 2026-10-04 - Deterministic component callback scheduling

Added a streaming scheduler that merges per-component strategy-context trigger
streams by native event index, groups components due on the same callback, and
orders each group by portfolio priority then component id. It retains at most
one next context per component and rejects duplicate or regressing callback
indices. The existing bridge currently routes its single component through
this scheduler; the authenticated runtime bundle and callback still provide
only one strategy stream, so this is not yet end-to-end multi-strategy
execution.

The real Nautilus adapter context-stream CLI now passes in a hardened,
network-disabled, read-only container with one successful SDK invocation. Its
generic FX/margin strategy was changed to emit no order because the native risk
adapter intentionally supports only cash equity/crypto spot today; the former
probe's FX order correctly failed closed as unsupported. Valid order behavior
continues to be exercised by the separate cash-equity target and raw-order
probes. The exact Nautilus 2.0.0rc5 image digest
`sha256:e39663e985471102fc735f87e43e720421deb8ed23cdd7896c6c2f49a88fd6fd`
also passed deterministic replay, single/multi-instrument accounting, native
order/fill/cost reports, engine lifecycle, 50% target allocation, and shared
raw-order risk. Both receipts remain non-authoritative; forward parity remains
deferred. Worktree-scoped cleanup left no runtime image, container, or volume.

The package suite passes all 1,162 tests, MyPy passes across 340 package/runtime
files, package/runtime Ruff checks pass, changed-file formatting passes, and
`git diff --check` is clean. No release or upstream event blocks package-owned
work. Stable Nautilus 2.x is not required by the current branch plan.

Next: add authenticated strategy bindings and per-component context streams to
the engine input/runtime bundle, validate each stream against the portfolio
component, and feed all streams into this scheduler. Then collect same-event
intent batches for one shared allocation/risk decision and preserve native
order/fill/position attribution.

Files changed in this slice:

```text
backend/app/strategy_lab_v2/nautilus_runtime_adapter_probe.py
backend/app/strategy_lab_v2/nautilus_strategy_bridge.py
backend/app/strategy_lab_v2/tests/test_nautilus_strategy_bridge.py
ops/workstreams/feat-strategy-lab-v2/handoff.md
ops/workstreams/feat-strategy-lab-v2/validation.jsonl
```

## 2026-10-04 - Shared component order-risk contract

Extended the native-evidence order adapter with a multi-component path. It
accepts component-attributed existing positions plus all components' proposed
raw-order batches, verifies the attribution ledger reconciles exactly to the
native account's net instrument exposures, then evaluates the combined orders
against one platform shared-risk decision. Approved SDK intents remain grouped
by component in deterministic order for downstream execution/attribution.
Single-component callers retain their existing API through a compatibility
wrapper.

The bridge still executes one strategy session at a time; this change does not
yet claim end-to-end multi-strategy native execution. It supplies the shared
risk/account boundary that the forthcoming invocation multiplexer must call,
and makes missing or inconsistent position attribution fail closed. Regression
tests show that two component orders at 4% equity each pass a 10% gross limit
but are rejected together under a 5% limit. The Strategy Lab v2 package suite
passes all 1,159 tests, the changed module passes MyPy, Ruff and formatting
checks pass, and `git diff --check` is clean.

Stable Nautilus 2.x is not a blocker: the plan permits exact-pinned pre-releases
for local backtests, and the isolated RC5 fixture already passes its applicable
simulator conformance checks. Separate uncompleted work remains in
multi-strategy runtime invocation/attribution, data capability and freeze
integration, search/walk-forward execution depth, durable workers/API/storage,
metrics, forward event parity, and the branch's final full-stack browser gate.
Provider, ETF, and TC2000 staging only gates the shared-path integrations they
own. Publishing local commits is currently blocked by the configured GitHub
SSH agent having no key identities; this does not block package-local work.

Next: build authenticated per-component invocation inputs and a deterministic
native callback multiplexer that combines same-time orders before one shared
allocation/risk decision, then attribute fills/positions back to components.

Files changed in this slice:

```text
backend/app/strategy_lab_v2/nautilus_order_routing.py
backend/app/strategy_lab_v2/tests/test_nautilus_order_routing.py
ops/workstreams/feat-strategy-lab-v2/handoff.md
ops/workstreams/feat-strategy-lab-v2/validation.jsonl
```

## 2026-10-04 - Native raw-order shared-risk routing

Connected supported raw SDK `OrderIntent` batches to the engine-neutral
`route_order_intents` gate before native submission. The bridge binds
event-aligned Nautilus marks, native cash/equity and open-position exposure,
instrument increments, and an evidence digest; batches are all-or-nothing and
only the risk-approved original intents reach the engine. The initial native
adapter supports base-quoted linear cash equities and crypto spot with unit
multiplier; unsupported product/currency economics fail closed. The explicit
runtime image allow-list now carries the shared `order_routing` and `risk_models`
dependencies.

The exact RC5 image fixture now exercises both native target allocation and
raw-order risk routing. A 100-share AAPL market intent was approved at an
estimated 10,001 USD exposure, then reconciled against one native order, one
position, and 10,002 USD cash deployment. The 50% target probe still reconciles
one order/position and 49,909.98 USD deployment after lot rounding. The four
existing local conformance checks also pass: single/multi-instrument
accounting, native orders/fills/costs, deterministic replay, and lifecycle.
Forward event-tape parity remains deferred; the RC fixture remains
non-authoritative. The scoped Docker cleanup left no labelled images,
containers, or retained volumes.

At this working tree, all 1,156 Strategy Lab v2 tests pass; MyPy passes across
340 package/runtime files; package Ruff and changed-file formatting checks
pass. No external release or upstream dependency blocks package-owned work.
Stable Nautilus 2.x remains unnecessary under the branch plan. A remote-sync
issue is separate: local commit `e78aa616` was rejected by the configured
GitHub SSH path because the session agent has no identities; no alternate
credential path was used. The goal remains active at 3/18 completed acceptance
areas.

Next: remove the one-component/one-strategy execution limitation so multiple
portfolio components can share one native account and allocator/risk decision,
with deterministic strategy ordering and component attribution. Do not broaden
instrument support without exact risk economics.

Files currently changed for this checkpoint:

```text
backend/app/strategy_lab_v2/nautilus_order_routing.py
backend/app/strategy_lab_v2/nautilus_rc_fixture_probe.py
backend/app/strategy_lab_v2/nautilus_runtime.py
backend/app/strategy_lab_v2/nautilus_runtime_adapter_probe.py
backend/app/strategy_lab_v2/nautilus_runtime_image/Dockerfile
backend/app/strategy_lab_v2/nautilus_runtime_image/Dockerfile.dockerignore
backend/app/strategy_lab_v2/nautilus_strategy_bridge.py
backend/app/strategy_lab_v2/tests/test_conformance_fixtures.py
backend/app/strategy_lab_v2/tests/test_engine_execution.py
backend/app/strategy_lab_v2/tests/test_nautilus_order_routing.py
backend/app/strategy_lab_v2/tests/test_nautilus_runtime.py
backend/app/strategy_lab_v2/tests/test_nautilus_runtime_image.py
ops/workstreams/feat-strategy-lab-v2/handoff.md
ops/workstreams/feat-strategy-lab-v2/session.json
ops/workstreams/feat-strategy-lab-v2/validation.jsonl
```

## 2026-10-04 - Native target-position allocation through RC5

Connected `TargetPositionIntent` to the existing component-target allocator and
shared portfolio-risk gate before orders reach the native engine. The bridge
uses Nautilus-native cash/account equity, positions, net exposure, and
event-aligned marks; order sizing currently fails closed unless exact metadata
supports cash-account, base-quoted linear equity or crypto spot with unit
multiplier. It floors to native lots and submits only the approved delta as a
market order. This slice explicitly does not claim multi-component execution,
raw-order shared-risk routing, forward parity, or official result authority.

The image-backed RC5 run exposed and fixed two package issues: the direct
`BacktestEngine.add_venue` path had omitted its explicit base currency, and the
target probe parsed Nautilus' native money summary as a bare decimal instead of
validating its `amount USD` representation. The hardened, network-disabled
fixture now passes: deterministic replay is equal; single- and
multi-instrument native accounting/orders/fills/costs reconcile; the target
probe requested 50%, placed one order, opened one position, and reconciled
100,000 USD starting cash to 50,090.02 USD remaining (49,909.98 USD deployed
after lot rounding). The fixture remains non-authoritative and forward event
parity remains deferred. The worktree-scoped Docker cleanup left no labelled
images, containers, or retained volumes.

At the current working tree, all 1,151 Strategy Lab v2 tests pass; MyPy passes
for 338 package/runtime files; package Ruff checks and formatting checks pass;
`git diff --check` is clean. No external release or upstream dependency blocks
this package-owned work. Stable Nautilus 2.x is not required by the branch plan:
the exact RC5 is usable for isolated local backtests after scoped conformance,
but not broker/real-capital use; forward shadow separately requires event-tape
parity. Provider, ETF, and TC2000 staging contracts gate only their later shared
path integrations. Branch progress remains 3/18 acceptance criteria complete.

Next: route supported raw `OrderIntent` through the platform allocation/risk
boundary and reconcile its projected exposure with native account state; then
extend the single-component bridge toward the plan's shared multi-strategy
portfolio execution contract. Keep unsupported product economics fail-closed.

Files currently changed for this checkpoint:

```text
backend/app/strategy_lab_v2/nautilus_engine_input.py
backend/app/strategy_lab_v2/nautilus_rc_fixture_probe.py
backend/app/strategy_lab_v2/nautilus_runtime.py
backend/app/strategy_lab_v2/nautilus_runtime_adapter.py
backend/app/strategy_lab_v2/nautilus_runtime_adapter_probe.py
backend/app/strategy_lab_v2/nautilus_runtime_bundle.py
backend/app/strategy_lab_v2/nautilus_runtime_image/Dockerfile
backend/app/strategy_lab_v2/nautilus_runtime_image/Dockerfile.dockerignore
backend/app/strategy_lab_v2/nautilus_strategy_bridge.py
backend/app/strategy_lab_v2/nautilus_trial_assembly.py
backend/app/strategy_lab_v2/nautilus_portfolio_wire.py
backend/app/strategy_lab_v2/nautilus_target_allocation.py
backend/app/strategy_lab_v2/tests/test_conformance_fixtures.py
backend/app/strategy_lab_v2/tests/test_engine_execution.py
backend/app/strategy_lab_v2/tests/test_nautilus_engine_input.py
backend/app/strategy_lab_v2/tests/test_nautilus_runtime.py
backend/app/strategy_lab_v2/tests/test_nautilus_runtime_adapter.py
backend/app/strategy_lab_v2/tests/test_nautilus_runtime_cli.py
backend/app/strategy_lab_v2/tests/test_nautilus_runtime_image.py
backend/app/strategy_lab_v2/tests/test_nautilus_target_allocation.py
ops/workstreams/feat-strategy-lab-v2/handoff.md
ops/workstreams/feat-strategy-lab-v2/session.json
ops/workstreams/feat-strategy-lab-v2/validation.jsonl
```

## 2026-10-03 - Production search-dispatch preparation and idempotent replay

Added `NautilusTrialSearchDispatchEvidenceResolver` as the package-owned
preparation boundary for queued backtests. It owner-hydrates and checks the
attempt graph, resolves the pinned strategy package, materializes verified
frozen inputs, reads the persisted worker pool and lease, verifies isolation and
lease identity/activity, binds the exact engine/capability evidence, and
composes the authenticated backtest worker request. This synchronous assembly
belongs in the dedicated local preparation process, not the FastAPI event loop.

PostgreSQL dispatch now confirms the handoff lease against persisted lease state
inside the enqueue transaction. An owner-scoped idempotency lookup can replay or
reject a prior key before expensive evidence resolution; the transaction repeats
that check to cover concurrent requests. Regression tests verify exact replay,
conflicting coordinates, lease/admission drift rejection without partial rows,
and application fast-path replay even when preparation is unavailable.

At pushed source SHA `15bd364c7a1587c44930baac7a30607f3e55129a`, all 1,144
Strategy Lab v2 tests passed; MyPy passed across 335 package/runtime files; Ruff,
all seven changed-file format checks, and `git diff --check` passed.

Nautilus stable 2.x is not a blocker. The exact RC5 image-backed fixture has
already passed the four local backtest checks (validation entry at source SHA
`f102f310499431b0c892483ec15e376f5503319f`). The fixture receipt itself remains
non-authoritative until scoped conformance evidence is used by publication.
RCs remain barred from broker/real-capital use, and forward shadow remains
separately gated by event-tape parity. Provider, ETF, and TC2000 contracts gate
only their later shared-path integration, not package-owned implementation.

Next: wire `TargetPositionIntent` through the existing component allocator and
shared-risk gate into the Nautilus bridge, using adapter-verified native
account/instrument economics and fail-closed handling for unsupported cases.

## 2026-10-03 - Host-composed Nautilus backtest dispatch

Added `build_nautilus_trial_worker_request` as the host-side preparation
composer. It checks authorization against the owner-hydrated materialized trial,
requires a matching isolated backtest worker and active lease, resolves admission,
builds the hardened sandbox and exact Nautilus execution plan from conformance
evidence, and binds the resulting `WorkerExecutionRequest` to the same immutable
runtime input artifact. It accepts only backtest scopes, so forward/live work
cannot accidentally inherit this backtest preparation path.

The application dispatch integration test now obtains its request through this
composer and passes it through `SearchDispatchEvidence` to the atomic dispatch
store. Focused safety tests cover RC5 authoritative local backtests, expired
leases, missing backtest conformance, and rejection of forward scope.

At clean, pushed source SHA
`7c674917cfd6d40f04d806849169bcb39a09b722`, all 1,138 Strategy Lab v2 tests
passed; Ruff passed for the package and runtime SDK; all three changed Python
files passed formatting checks; MyPy passed across 333 files; and
`git diff --check` was clean.

There is no external release or upstream dependency blocking the next owned
slice. Stable Nautilus 2.x is not required: the exact-pinned 2.0.0rc5 build
remains eligible for local authoritative backtests after its four recorded
simulator checks. Its pre-release status still bars broker/live-capital use,
and forward shadow remains gated separately on event-tape parity. The next
internal gap is the production `SearchDispatchEvidenceResolver`/dedicated
preparation boundary that obtains owner-scoped graph and authorization plus
runtime profile, active lease, worker pool, and exact conformance evidence for
real queued candidates before calling the composer. Provider-owned Arrow
decoding and shared router/schema/worker registration await upstream staging
contracts; those gates do not block resolver or other package-owned work.

The saved goal metadata still says “stable v2 conformance.” That wording is
stale and conflicts with this branch's current `plan.yaml`, which permits a
stable or pre-release build after exact-pin conformance. Follow the branch plan.

## 2026-10-03 - Content-bound search worker dispatch

The search HTTP request is now a `SearchDispatchIntent`: clients provide the
attempt, idempotency key, queue, and request time, but no longer claim a digest
for host-generated bytes. `SearchDispatchEvidence` requires a complete typed
`WorkerExecutionRequest` tied to the materialized trial evidence. The
application serializes that exact request as the authenticated worker handoff
and derives `DispatchRequest.payload_digest` from those encoded bytes.

Before any durable write, the PostgreSQL adapter decodes and checks the handoff
against authorization, runtime request/preflight, attempt, trial and package
binding, lease, queue, and execution plan. Inside its transaction it recomputes
admission using locked search/admission/worker state and rejects if either the
handoff admission or reserved pool differs from that atomic result. The new
regression case tampers with admission time and verifies that no admission,
reservation, payload, dispatch, or outbox row is added and the search candidate
remains pending. This resolves the digest-only HTTP/PostgreSQL mismatch noted in
the earlier checkpoint below.

At clean, pushed source SHA
`c2529faa15e6d715ade78b2c11e24d3b80291cba`, all 1,134 Strategy Lab v2 tests
passed; Ruff passed for the package and runtime SDK; all seven changed Python
files passed formatting checks; MyPy passed across 331 files; and
`git diff --check` was clean.

No external dependency blocks the next owned slice. The remaining local gap is
a production host composer that constructs the full `WorkerExecutionRequest`
from materialized trial inputs plus the exact runtime image, conformance,
sandbox, worker-pool, admission, and lease evidence; the evidence resolver now
requires that complete request but does not yet build it. The injected frozen
series decoder remains provider-owned pending its staging contract. Shared
router/schema/worker registration remains gated on provider, ETF, and TC2000
contracts reaching staging. Stable Nautilus 2.x is not a prerequisite: exact
2.0.0rc5 passed the recorded local backtest checks; forward parity remains a
separate forward-shadow gate, and pre-releases remain barred from real capital.

Next: implement and test the host-owned worker-request composer in the
dedicated preparation boundary, then feed its output through the bound evidence
resolver and atomic dispatch path.

## 2026-10-03 - Dispatch evidence bound to hydrated runtime inputs

`SearchDispatchEvidence` now carries the materializer-produced runtime request
and preflight as one typed value. Its constructor verifies the authorization's
attempt, trial, trial preflight, and strategy source against that materialized
graph. The application adapter additionally rejects an experiment or attempt
that differs from the same graph before calling the durable dispatch store.

At clean, pushed source SHA
`cf4a0f63b3053e6f6dd14a2490b36a102c5bbfea`, all 1,133 Strategy Lab v2 tests
passed; Ruff passed for the package and runtime SDK; both changed files passed
format checks; MyPy passed across 331 files; and `git diff --check` was clean.

No external dependency blocks this owned work. The exact pinned `2.0.0rc5`
remains eligible for local backtest execution under the branch plan and its
four recorded simulator checks; stable 2.x is not required. Its pre-release
status still forbids broker/live-capital use, and forward-shadow needs separate
event-tape parity.

The built-in HTTP dispatch path still has an in-scope contract gap: the client
currently supplies a `payload_digest`, but the API passes that same digest-only
body as the payload whose independently computed digest PostgreSQL verifies.
The next slice must build the immutable worker handoff from this bound runtime
evidence, derive the durable payload digest from that encoded handoff, and have
the PostgreSQL transaction verify the worker request against its locked
admission and reservation before writing the outbox. This is implementation
work, not a Nautilus-version or upstream-availability blocker. The later shared
API/schema/worker registration still waits for the owned provider, ETF, and
TC2000 contracts to reach staging.

The saved goal metadata still contains older “stable v2” wording; the current
branch plan explicitly permits stable or pre-release builds after exact-pin
conformance. Follow the branch plan for this workstream.

## 2026-10-03 - Trial-bound runtime evidence and worker lineage

The runtime artifact reference now carries a non-circular immutable binding to
its exact attempt, trial, experiment, portfolio, snapshot, strategy package,
engine input, and invocation input. Trial assembly creates the binding alongside
the content-addressed bundle. `MaterializedNautilusTrialInput` requires that
binding to match its owner-hydrated graph and assembly. A new runtime-evidence
builder derives `StrategyRuntimeRequest` and isolation preflight from that same
materialized input, checks the package/runtime ABI, and takes dependency pins
from the immutable strategy version. It is synchronous and belongs in the
dedicated backtest preparation process, not an API or heartbeat loop.

The authenticated search-worker handoff now requires the runtime request and
artifact bundle digests to agree, requires the persisted trial binding, and
cross-checks its attempt/trial/experiment/portfolio/snapshot/package identities
against the owner-hydrated PostgreSQL graph before allowing execution. The
binding travels inside the serialized worker request, so the existing durable
payload digest covers it. The host's search-dispatch evidence/request builder
still needs to use this new composition; dispatch continues to accept explicit
host evidence and no API event-loop or provider fetch was added.

At clean, pushed source SHA `8a98a0dca8fd3ae180ee28b9ee48a34b96f701a2`, all
1,133 Strategy Lab v2 tests passed; MyPy passed across 331 files; Ruff passed
for the package and runtime SDK; all eight changed Python files passed Ruff
formatting; and `git diff --check HEAD^ HEAD` was clean. The commit is pushed to
`origin/feat/strategy-lab-v2`.

Stable Nautilus 2.x remains unnecessary. Exact-pinned `2.0.0rc5` is qualified
for the four local backtest checks only; forward parity is separate. No
external dependency blocks the next owned composition slice. Full-stack-browser
is still final branch acceptance, not this slice's blocker.

Next: connect the materialized runtime evidence and artifact binding to the
host's pre-dispatch evidence/request builder. Construct admission, engine and
sandbox plans, encode the worker request from the same artifact reference, and
make the PostgreSQL/outbox staging path reject any drift among payload,
authorization, request, preflight, and materialized binding before enqueue.

## 2026-10-03 - Owner-hydrated runtime input materialization

Added a package-owned composition boundary that takes the already
owner-hydrated immutable attempt/trial/experiment/portfolio/snapshot/strategy
graph, canonical instrument/venue context, the exact package resolver and
verified local artifact store, plus an injected provider-owned frozen-series
decoder. It resolves the pinned strategy package and frozen series/event-tape
artifacts, assembles the Nautilus runtime input, and ties the result back to the
graph and exact attempt/experiment/portfolio/snapshot/package identities. It
rejects mismatched stores, package bindings, or instrument sets. It performs no
provider/network acquisition and does not import Nautilus; synchronous assembly
must run in a dedicated backtest preparation process rather than an API or
heartbeat event loop.

At exact clean source SHA `84617e4adaf6b82d2ef796febff67c2631375eb5`, all
1,132 Strategy Lab v2 tests passed; MyPy passed across 331 files; Ruff passed
for the package; the two new Python files passed Ruff formatting; and
`git diff --check` was clean. The implementation commit is pushed to
`origin/feat/strategy-lab-v2`.

This materializes the runtime input in package-owned code, but it is not yet
wired into search dispatch, persisted as an atomic attempt/dispatch binding, or
connected to the provider-owned Arrow decoder implementation. Those are the
next worker-composition and staging-contract integration slices. Stable
Nautilus 2.x is not a prerequisite: the pinned 2.0.0rc5 build remains qualified
for the four local backtest checks only; forward event-tape parity is separate.
The full-stack-browser profile remains final branch acceptance, not a blocker
for the next local implementation slice.

Next: feed this exact materialized input into host pre-dispatch evidence and
request composition, derive preflight/admission and the encoded worker payload
from it, then bind its fingerprint atomically to the attempt and dispatch via
the existing PostgreSQL/outbox path. Keep assembly in the dedicated serial
worker boundary and retain the provider-owned decoder seam until its contract
reaches staging.

## 2026-10-03 - Owner-bound search worker graph handoff

The authenticated search-dispatch worker callback now hydrates the dispatched
attempt using the persisted dispatch owner's scope before returning its worker
request. It verifies that the dispatch experiment matches the hydrated graph
and that the runtime package, strategy source digest, and entrypoint are all
pinned by that experiment. Search-worker composition fails closed when the
owner-scoped domain reader is unavailable. This prevents a correctly signed
queue payload from substituting a different persisted trial or package.

At exact clean source SHA `f515326b5eebe621c7251825e96e87423fc74126`, all
1,129 Strategy Lab v2 tests passed; MyPy passed across 329 files; Ruff passed
for the package; the four changed Python files passed Ruff formatting; and
`git diff --check` was clean. The commit is pushed to
`origin/feat/strategy-lab-v2`.

This verifies and binds the current decoded worker request; it still does not
construct that request's runtime bundle directly from the hydrated graph. The
next owned slice is production worker runtime-input assembly from verified
package and frozen-data artifacts, followed by atomic attempt/dispatch/runtime
provenance. Provider-owned Arrow decoding remains behind its staging contract.
Stable Nautilus v2 availability, forward parity, and the final full-stack
browser acceptance profile are not prerequisites for this implementation slice.

## 2026-10-03 - Owner-scoped trial graph hydration

`PostgresResourceReader` now resolves batches of typed domain records by their
content fingerprints inside the principal's owner scope, rejects ambiguous
owner-local duplicates, and rehydrates each record against its declared domain
fingerprint. `NautilusTrialDomainHydrator` uses that read surface to resolve a
queued/running attempt through its immutable trial, experiment, portfolio,
snapshot, strategy versions, and pinned packages. It rejects missing/foreign
resources and checks every cross-resource fingerprint, preflight, portfolio,
and package binding before returning the immutable graph. This is now the next
input to connect to worker runtime assembly; event/series bytes, instrument and
account adapters, and dispatch binding remain separate work.

At exact source SHA `516c1273a4a1d1df9b3f1e905a6c3d7670d76035`, all 1,127
Strategy Lab v2 tests passed; MyPy passed across 329 files; package Ruff checks
passed; and the four changed files passed Ruff formatting and `git diff --check`.
The package-wide format probe reports 198 untouched files that would be
reformatted, so no repository-wide formatting rewrite was applied. This host-
side change does not alter the pinned Nautilus runtime image or require rebuilding
it. The source commit is pushed to `origin/feat/strategy-lab-v2`.

This advances persisted owner-scoped worker hydration only; it does not yet
construct a worker request directly from the hydrated graph or complete atomic
runtime dispatch. Stable Nautilus v2 availability is not a prerequisite.

## 2026-10-03 - Scoped RC backtest result publication provenance

Nautilus result materialization now carries typed, content-fingerprinted engine
provenance: exact v2 package/release channel, source/wheel/runtime-image pin,
conformance evidence and report, authoritative execution scope, and execution
plan. The new provenance builder recomputes the conformance report and verifies
the ready plan, engine/build/snapshot identity, hardened sandbox plan/image,
scope-required checks, and pre-release restrictions. `plan_result_publication`
independently recomputes conformance, requires exact plan/result/evidence
identity, and permits `BACKTEST_AUTHORITATIVE` publication when its four
simulator checks pass without pretending forward parity passed. PostgreSQL
canonical decoding now recognizes the nested conformance provenance records.

At clean source SHA `f102f310499431b0c892483ec15e376f5503319f`, all 1,121 Strategy Lab v2 tests passed; scoped
MyPy passed across 321 files; Ruff and format checks passed for all 17 changed
Python files. The exact-pinned RC5 image rebuilt as
`sha256:66ace07d47af15aee57b75dcfaffe2a72df720c35355524efe628cd8f7c3d144`.
Its actual native fixture ran with networking disabled, read-only root,
capabilities dropped, no-new-privileges, UID 65532, and bounded CPU, memory,
file size, PIDs, and temporary storage. `NautilusRcFixtureReceipt` accepted the
actual JSON: multi-instrument accounting, native order/fill/cost, deterministic
replay, and lifecycle passed; forward event-tape parity remains explicitly
deferred; the fixture receipt itself remains non-authoritative. Fixture digest:
`sha256:b233d6aa9953894f65628247455f6b349590c21946fac0a84797e3e9a78eee3e`.

This closes the local backtest result-provenance/publication seam, not the full
Strategy Lab goal. At this checkpoint source and native market-event tapes were
still materialized; a later source commit makes verified disk-spooled event-tape
resolution the default. Production worker hydration/dispatch, canonical
account/instrument adapters, target-position allocation/risk, broader
asset/product conformance, forward parity, and final full-stack-browser
validation remain. No stable Nautilus tag or upstream branch blocks continued
implementation. Provider, ETF, and TC2000 contract consumption is only a later
shared-path integration gate.

The source commit is pushed to `origin/feat/strategy-lab-v2`; local `HEAD` and
the tracked remote are both `f102f310499431b0c892483ec15e376f5503319f`.

This checkpoint updates the branch-owned
`ops/workstreams/feat-strategy-lab-v2/plan.yaml`, `handoff.md`,
`validation.jsonl`, and `session.json` only.

Next replace full native event-tape bundle materialization with verified,
content-addressed stream/catalog chunks consumed incrementally by exact-pinned
RC5, preserving same-time ordering and deterministic replay. Then continue
owner-scoped trial hydration and atomic runtime dispatch.

## 2026-10-02 - Bounded Nautilus invocation-result artifact handoff

The invocation-result side of the Nautilus worker handoff is now streamed to a
bounded JSONL sidecar and published as a content-addressed artifact. The native
bridge writes each callback result incrementally; the runtime adapter returns
only a compact descriptor; and the host verifies the exact bytes, digest,
length, count, protocol, trailer, and status before artifact publication.
Output byte limits are enforced inside the isolated worker. Legacy batch
compatibility remains available.

At source SHA `adbf408e19169dd1a40087b69c30f36b74f25678`, all 1,098 Strategy Lab
v2 tests passed; Ruff and format checks for the 19 changed Python files passed;
MyPy passed across 325 source files; and `git diff --check` was clean. The
exact-pinned Nautilus `2.0.0rc5` image
(`sha256:00b866abd2d4f5fa858999ebec6a6d2a7f0e66912561b4f4f570bdffea68f76c`)
ran the real CLI and engine with networking disabled, a read-only root,
capabilities dropped, no-new-privileges, unprivileged UID, and bounded CPU,
memory, file size, PIDs, and temporary storage. It processed two native events,
invoked the SDK once, produced one native order and one open position, verified
the streamed result artifact (one record, 1,016 bytes), and remained
`authoritative=false`. Runtime evidence digest:
`sha256:47ed789b76c6c48293174b08caa4b5b01be7aa3378e8be655c5f750b3963e6a3`.

This closes the bounded invocation-result artifact seam only. Source and native
market-event tapes are still materialized before runtime launch; next replace
the full native-event tape with verified, content-addressed stream/catalog
chunks consumed incrementally by exact-pinned RC5, preserving same-time order
and deterministic replay. RC5 is usable for local testing after conformance;
it remains barred from broker/real-capital use, and full conformance—not a
stable upstream tag—gates authoritative results. No external dependency blocks
the next implementation slice.

The source commit is pushed to `origin/feat/strategy-lab-v2`; local `HEAD` and
the tracked remote are both `adbf408e19169dd1a40087b69c30f36b74f25678`.

## 2026-10-02 - End-to-end pinned context-stream handoff

Trial assembly no longer builds a full SDK context tuple or serialized batch.
It streams `iter_event_tape_contexts` into a content-addressed pinned-input
artifact, and the v2 runtime bundle binds that sidecar's manifest and context
count while preserving the legacy v1 batch format for compatibility. The
worker request and hardened Docker plan require the matching read-only mount
and digest; the host verifies the exact mounted bytes before launch. The
isolated CLI independently authenticates the bundle, attempt, snapshot,
runtime version, sidecar descriptor, and sidecar bytes before passing the
seekable file to the RC5 strategy bridge. Unapproved Docker mounts/environment
options are rejected. The isolated CLI does not import host artifact-store or
backend-only modules.

At clean source SHA `8cb165aab6843c2bd3577b2aab17d59b7584decb`, all 1,093
Strategy Lab v2 tests passed; Ruff and formatting checks passed; MyPy passed
across 325 source files; and `git diff --check` was clean. A freshly built,
wheel-checksum-pinned Nautilus `2.0.0rc5` image
(`sha256:2ed9fb927087c1af483d05e8a24c50f7b656da0161c7a5a240e27eb2a255f436`)
ran the real bundle/sidecar CLI and native engine under network-disabled,
read-only, dropped-capability, no-new-privileges, unprivileged, memory/CPU/file
size/PID-limited settings. It processed two same-time quotes, invoked the SDK
once, produced one native order and one open position, and remained explicitly
non-authoritative.

This closes only the bounded SDK-context side of the runtime handoff. The
frozen source `EventTape` and the native event tape are still fully
materialized; the runtime result and invocation-result list are still
materialized before artifact publication. Next, stream result records directly
to bounded artifacts, then move native market events into verified
content-addressed stream/catalog chunks consumed incrementally by RC5. After
those data-plane seams, continue owner-scoped runtime hydration, instrument /
venue / account adapters, atomic dispatch binding, target-position allocation
and risk routing, and broad native conformance. Exact-pinned prereleases remain
eligible for local testing; full conformance still gates authority, while
stable-tag availability does not block development. Provider / ETF / TC2000
shared-path work remains a later staging reconciliation gate only.

## 2026-10-02 - Streaming Strategy SDK runtime consumer

Connected the context-stream protocol to the engine-neutral runtime CLI. It
validates the complete source/manifest/context stream before invoking strategy
code, then runs one persistent SDK session while pulling one context at a time.
Typed invocation results are written incrementally to a versioned JSONL stream
with contiguous indexes, a record digest/count trailer, and atomic file
publication. The context stream now also carries a trailer so truncation and
record drift are detected. Existing one-event and batch CLI inputs/outputs
remain compatible.

At clean source SHA `1018c65cf5fe8969bf53add492ebe180e88c7eb2`, all 1,083
Strategy Lab v2 tests passed; Ruff and MyPy across 325 source files passed;
all four changed Python files passed formatting checks; and whitespace
validation was clean. The implementation commit is pushed and local `HEAD`
matches `origin/feat/strategy-lab-v2`.

This materially reduces SDK replay serialization/runtime memory, but does not
yet make the Nautilus backtest end-to-end bounded. Trial assembly and the
Nautilus CLI/bridge still use the old in-memory event tape and batch path. Next
bind content-addressed context and native-event stream artifacts into the
compact runtime manifest and worker handoff, verify/mount them read-only, and
consume the native data through exact-pinned RC5 catalog chunks. Preserve
same-time ordering and full conformance as gates for authoritative results.

## 2026-10-02 - Bounded SDK invocation-context stream protocol

Added `iter_event_tape_contexts`, which yields one same-time SDK context at a
time while retaining only declared rolling histories and the current event
batch. Added a versioned JSONL invocation-context protocol that writes and
reads one context record at a time, validates strict chronology and contiguous
record indexes, rejects oversized rows/streams, and preserves the existing
duplicate-field and non-finite JSON protections. The batch APIs remain
available for compatibility.

At clean source SHA `446288c20ecf75af6258a46b573fc49d105824aa`, all 1,079
Strategy Lab v2 tests passed; Ruff and MyPy across 325 source files passed;
the five changed Python files passed format checks; and `git diff --check` was
clean. This source commit is pushed and local `HEAD` matches
`origin/feat/strategy-lab-v2`.

This is a streaming boundary, not yet end-to-end bounded backtesting: trial
assembly still accepts/materializes an in-memory frozen tape, builds the full
native event tape and context batch, and embeds them in the runtime bundle.
The next implementation slice must bind verified event/context stream
artifacts into the runtime input and consume them in the isolated Nautilus
worker through catalog chunks. Exact-pinned RC5 remains eligible for local
research; full platform conformance and event-tape parity remain gates for
authoritative results and broker-free shadow activation. No stable 2.x tag,
parallel worktree, or provider/ETF/TC2000 staging change blocks this work.

## 2026-10-02 - Pinned Nautilus v2 qualification policy

The Strategy Lab does not wait for an upstream stable 2.x tag. An exact-pinned
Nautilus v2 build, including the current `2.0.0rc5`, is eligible for local
backtests after it passes the full platform conformance suite. Results retain
the exact package version/channel and wheel/image digests. A pre-release may
not connect to a broker or control real capital; broker-free forward-shadow
qualification separately requires event-tape parity. This converts the former
stable-tag dependency into a measurable local qualification gate while keeping
the research sandbox local and fail-closed.

Upstream currently documents v2 wheels as release candidates, requires
pre-release installation, and advises against using them in production to
control real capital: [NautilusTrader installation guidance](https://nautilustrader.io/docs/nightly/getting_started/installation/)
and [official releases](https://github.com/nautechsystems/nautilus_trader/releases).
The branch has already built and exercised its digest-pinned RC5 image in the
isolated sandbox. At source SHA
`443a692bfde9113579f35bb60c028e2b9c6d6730`, the exact Strategy Lab v2 suite
passed 1,047 tests, Ruff passed, MyPy passed across 320 source files, all eight
changed Python files passed formatting, and the whitespace check was clean.
The partial RC fixture remains non-authoritative; full multi-instrument,
accounting, reporting, replay, lifecycle, and forward-parity evidence remains
implementation work, not an upstream release wait.

## 2026-10-02 - Fail-closed persisted domain fingerprint validation

The owner-scoped typed resource reader now rejects a present-but-malformed
persisted `domain_fingerprint` instead of treating it as absent and skipping
the identity comparison. The malformed-type regression test is included in the
full package suite. At exact source SHA
`badee4d716345258a8393833969f765de5576bed`, all 1,047 Strategy Lab v2 tests
passed, Ruff passed, MyPy passed across 320 source files, the four changed
Python files passed format checks, and whitespace validation was clean. This
source commit is pushed and the local/remote hashes match.

## 2026-10-02 - Owner-scoped typed resource rehydration

`ResourceDomainNormalization` now retains the typed domain contract it already
constructs while validating strategy, package, portfolio, experiment, attempt,
snapshot, trial, metric-set, and forward-instance resources. The new
`rehydrate_resource_contract` function rebuilds a typed value from the canonical
persisted attributes through the same strict normalizers used at creation and
rejects generic resource types without a typed contract. The PostgreSQL
resource reader exposes `get_domain_contract`, reusing its owner-scoped read and
checking a stored domain fingerprint against rehydrated attributes when that
fingerprint is present. Foreign resources remain indistinguishable from missing
ones; malformed attributes and fingerprint drift fail closed.

At source SHA `462fbb541361a758f8bfdb2c9a0e517a8acbc9e2`, all 1,046
Strategy Lab v2 tests passed, Ruff passed, MyPy passed across 320 source files,
all four changed Python files passed format checks, and whitespace validation
was clean. PostgreSQL reader behavior is unit-tested through the existing
owner-scoped reader with an in-memory aggregate store; a live database
integration run remains part of the broader acceptance gate. The source commit
is pushed and local/remote hashes matched.

The next host-composition work still needs verified local resolvers for
package/source/manifest and frozen event-tape bytes, plus provider-derived
instrument metadata and venue/account construction. The immutable bundle
producer can then consume those values and its artifact reference can be bound
into atomic dispatch. Target-position allocation/risk integration and broad
native product/accounting/report conformance remain later gates. No parallel
provider, ETF, or TC2000 worktree was read or modified.

## 2026-10-02 - Immutable Nautilus trial-input assembly

Added a producer that binds one queued/running attempt to its immutable
scientific trial, experiment, portfolio, snapshot, preflight report, frozen
event tape, strategy package/SDK manifest/source, native instrument catalog,
and venue cash account. It cross-checks their fingerprints and declared
instrument/capital scope, combines strategy defaults with trial parameters,
builds event-aligned SDK contexts and native engine input, then publishes the
serialized bundle to the pinned content-addressed artifact store. Unsupported
multi-component portfolios, rebalances, scenarios, and evaluation windows fail
closed before publication. The producer does not access a database or dispatch
a worker; host rehydration and atomic dispatch binding remain the next seam.

At source SHA `58e2882d6820301db3eb579c712553606145bda9`, all 1,041
Strategy Lab v2 tests passed, Ruff passed, MyPy passed across 320 source files,
and both changed Python files passed the format check. This proves the local
producer and its contracts, not the complete API-to-worker route. Nautilus
2.0.0rc5 remains usable for isolated non-authoritative research runs; its
upstream stable release is not a development blocker and still gates only the
branch's stable-authority acceptance requirements.

The next action is a trusted host resolver that rehydrates the persisted trial
inputs and binds the resulting artifact reference into the existing atomic
dispatch evidence. Target-position intents still need event-aligned
allocation/risk integration, followed by broader native product, accounting,
and report conformance. No provider-platform, ETF, or TC2000 worktree is being
modified; only their eventual shared-contract integration depends on staging.
This source context is committed as `58e2882d6820301db3eb579c712553606145bda9`
and pushed to `origin/feat/strategy-lab-v2`; the verified local and remote
source hashes matched at publication.

## 2026-10-02 - Nautilus same-time event-batch bridge

The isolated Nautilus bridge now consumes the engine-neutral SDK's same-time
event batches as one strategy invocation, bound to the final native callback
for that timestamp so all events in the batch are visible first. Legacy
one-context-per-event worker payloads remain supported. The bridge also now
compares native nanosecond timestamps to SDK timestamps at their shared
microsecond precision; the previous comparison could only pass around the Unix
epoch and rejected normal modern dates. Its RC5 runtime probe now uses two
simultaneous native events at a 2024 timestamp.

At source SHA `4f3cfc4d4f2212841825d696f8f191cf47b59f2c`, the complete
Strategy Lab v2 package passed 1,035 tests, Ruff passed, MyPy passed across 318
source files, changed files passed format checks, and all 30 workstream records
validated. A separately tagged, checksum-pinned Nautilus `2.0.0rc5` image
(`sha256:bc8aa4436f0083382d0ea49a9ebd28d829dcab83cca631085b26910bf5d3f0a9`)
passed the network-disabled, read-only, capability-dropped probe: two native
events, one SDK invocation, one native order, one open position, explicitly
non-authoritative. This is local compatibility evidence, not publication or
conformance authority.

No release wait blocks implementation. The next producer gap remains assembling
persisted trial/snapshot/portfolio inputs into the pinned bundle and binding it
into durable dispatch. Multi-strategy shared-account routing and target-position
allocation/risk integration are still unsupported; stable-v2 conformance still
gates authoritative publication and deployed shadow activation.

## 2026-10-02 - Content-addressed Nautilus runtime-input handoff

Added a typed pinned-input artifact reference that keeps the Nautilus bundle's
semantic input digest distinct from the raw-byte SHA-256 used by the shared
artifact store. Bundle materialization is idempotent; reloading cross-checks
the schema, attempt identity, semantic digest, raw byte integrity, and an
explicit input-size bound. `WorkerExecutionRequest` now carries only this
compact reference, and its canonical durable envelope is versioned as v2.
Before launching Docker, the serial worker verifies the exact mounted regular
file against the artifact manifest, request digest, attempt, and memory-derived
size limit. The isolated CLI continues to recheck the semantic bundle digest.
Bad or drifted inputs are rejected before a container starts.

The complete Strategy Lab v2 package suite passed 1,031 tests; Ruff passed and
MyPy passed across 311 source files. Production assembly of the bundle from
frozen trial/snapshot/portfolio inputs and the dispatch producer remains the
next seam. Nautilus 2.0.0rc5 remains a local non-authoritative compatibility
runtime; stable v2 remains the gate for authority, published rankings, and
deployed shadow activation.

## 2026-09-25 - Account-settling forward-worker pipeline checkpoint

Added `RedisDispatchRuntime.account_settling_forward_worker_service()`, an
explicit composition factory for the complete forward handoff lifecycle. It
nests the reservation/lease authorization gate, canonical-event-bound account
settlement, and atomic capacity release so a host cannot accidentally wire a
worker that acknowledges after only one of those stages. Event/engine
resolution and durable adapters remain host-supplied.

The focused account-worker, capacity-settlement, and Redis runtime composition
suite passed 11 tests. Ruff and MyPy remain green across 293 source files;
whitespace validation is clean.

## 2026-09-25 - Forward-worker capacity settlement checkpoint

Added `ForwardWorkerCapacityReleaseHandler` and the
`RedisDispatchRuntime.settling_forward_worker_service()` factory. A forward
handler must first return a durable completion receipt; only then is a release
observation validated against the authorized worker/lease and passed to the
existing atomic PostgreSQL `release_capacity` boundary. Released and exact
replay outcomes permit acknowledgement; rejected release evidence remains
retryable, preventing capacity loss or premature Redis acknowledgement.

The focused capacity-settlement and Redis runtime suite passed 8 tests. Ruff
and MyPy remain green across 293 source files; whitespace validation is clean.

## 2026-09-25 - Atomic forward-worker authorization load checkpoint

`PostgresWorkerStateAdapter.load_forward_authorization()` now loads the
forward worker profile, reservation, and lease plus its authenticated
observation history in one transaction with row locks. The application bridge
delegates to this method, eliminating the race that separate pool and lease
reads could introduce between authorization and dispatch handling.

The focused PostgreSQL worker-state and application authorization suite passed
8 tests. Ruff and MyPy remain green across 291 source files; whitespace
validation is clean.

## 2026-09-25 - Durable forward-worker authorization bridge checkpoint

The application adapter now exposes
`load_forward_worker_authorization()`, loading an authenticated worker-pool
reservation and lease from the existing PostgreSQL worker-state adapter and
returning the typed authorization consumed by the forward-worker gate. Missing
reservation or lease records return no authorization; no capacity or lease is
invented at the application boundary.

The focused application authorization bridge suite passed 2 tests. Ruff and
MyPy remain green across 291 source files; whitespace validation is clean.

## 2026-09-25 - Forward-worker reservation/lease authorization checkpoint

Added the pure `AuthorizedForwardEventHandler` gate and the
`RedisDispatchRuntime.authorized_forward_worker_service()` factory. A forward
work item now requires a host-loaded `WorkerReservation` of kind `FORWARD` and
an `ExecutionAttemptLease` bound to the same worker and instance. Released,
wrong-kind, cross-instance, or expired evidence cannot reach account/engine
handling; expired leases remain retryable for recovery. Persistence remains
responsible for loading the reservation and lease records.

The focused authorization and Redis runtime suites passed 11 tests. Ruff and
MyPy remain green across 291 source files; whitespace validation is clean.

## 2026-09-25 - Dedicated forward-worker runtime composition checkpoint

`RedisDispatchRuntime` now exposes an explicit `forward_worker_service()`
factory. It binds a dedicated queue scheduler to
`ForwardEventWorkerService`, while preserving the generic backtest/runtime
worker factory as a separate path. The host still supplies authenticated
handoff materialization, canonical-event/account settlement, worker
reservation, and engine callbacks; this seam does not start providers or
Nautilus.

The Redis runtime composition suite passed 6 tests, with Ruff, MyPy, and
whitespace validation green across 289 source files.

## 2026-09-25 - Forward shadow-account API projection checkpoint

Added the authenticated read-only
`GET /api/v1/strategy-lab/v2/forward-instances/{instance_id}/account` route.
It exposes canonical cash, positions, orders, fills, cursor, and applied-event
identities through the same fail-closed adapter boundary as forward admission
state, returning typed not-found and host-not-configured errors without
inventing account data.

The focused API serializer suite passed 2 tests, with Ruff, MyPy, and
whitespace validation green. Full TestClient startup remains restricted by the
existing environment hang; route logic is covered through the package-owned
serializer and adapter seam.

## 2026-09-25 - Shadow-account compare-and-set hardening

Account state updates now include the previously loaded state fingerprint in
their SQL compare-and-set predicate. A concurrent or stale writer therefore
fails closed even though normal reads already lock the account row; exact
replays continue to return the persisted state without a second mutation.
Focused PostgreSQL account and worker-binding coverage passed 6 tests, with
Ruff, MyPy, and whitespace validation still green.

## 2026-09-25 - Forward shadow-account worker settlement checkpoint

Added `ForwardAccountWorkerHandler`, a composable host-worker boundary for
durable shadow-account settlement. The host resolver produces a typed binding
between the canonical stream event and immutable account effects for an
authenticated `ForwardEventWorkItem`; the handler verifies event identity,
sequence, timestamp, and instance fingerprints before applying them through
the owner-scoped account store. Redis is acknowledged only after an `APPLIED`
or exact `REPLAY_EXISTING` account resolution. Missing initialization and
out-of-order effects remain retryable, while identity conflicts and malformed
effects remain pending as fail-closed rejections.

The focused account-worker, forward-worker, ledger, and PostgreSQL account
suite passed 13 tests. Ruff and MyPy remain green across 289 source files;
whitespace validation is clean. Provider event resolution, worker
capacity/authorization, and stable Nautilus execution remain explicit host
gates.

## 2026-09-25 - Forward shadow-account persistence checkpoint

Added `PostgresForwardAccountAdapter` and the additive
`strategy_lab_v2_forward_accounts` table. Account state is stored as
owner-authenticated canonical JSON with a deterministic state fingerprint and
instance-bound primary key. Initialization is idempotent for exact retries and
rejects changed state; loads and event applications preserve typed replay,
conflict, out-of-order, and rejection outcomes from the engine-neutral ledger.
The shared persistence bundle and application adapter now expose
initialize/load/apply account methods, and canonical rehydration accepts the
forward-account event/state contracts without bypassing field validation.

Focused forward-account, worker/handoff/dispatch/application/persistence
coverage passed 29 tests, and the migration suite passed 2 tests. Ruff and
MyPy remain green across 287 source files; whitespace validation is clean. A
package-wide collection was started but did not complete in the restricted
test environment, so this checkpoint relies on the focused suite and static
validation. Event-stream/provider authorization, worker capacity binding, and
stable Nautilus execution remain gated.

## 2026-09-25 - Forward shadow-account ledger checkpoint

Added the engine-neutral `forward_account.py` contract for broker-free shadow
state: immutable accepted orders, authoritative fills, multi-currency cash
balances, positions, and append-only applied-event identities. The pure
transition applies fills deterministically, preserves weighted average prices,
rejects unknown or overfilled orders, rejects out-of-order events, and replays
exact content without rewriting prior decisions. It performs no broker,
provider, persistence, or Nautilus I/O; a PostgreSQL account-state adapter is
the next persistence seam.

Focused forward account plus worker/handoff/dispatch/application/persistence
coverage passed 39 tests. Ruff and MyPy remain green across 285 source files.
Account-state persistence, event-stream activation, worker authorization, and
stable Nautilus execution remain gated.

## 2026-09-25 - Forward worker service checkpoint

Added `ForwardEventWorkerService`, a bounded Redis scheduler composition for
authenticated forward-event work items. It retries materialization or host
handler failures without acknowledging the stream entry and acknowledges only
the handler's entry-bound durable receipt. The handler receives the validated
stream entry plus typed event/replay fingerprints; provider event acquisition,
forward worker reservation, and Nautilus execution remain explicit host-owned
integration seams.

Focused forward worker service, handoff, dispatch, application, and
persistence coverage passed 35 tests. Ruff and MyPy remain green across 283
source files. Event-stream activation, worker authorization/capacity binding,
and stable Nautilus execution remain gated.

## 2026-09-25 - Authenticated forward worker handoff checkpoint

`PostgresForwardEventDispatchAdapter` now exposes an authenticated
`load_by_request_fingerprint` lookup for Redis consumers. The new
`forward_worker_handoff.py` materializer binds a stream entry to that durable
owner/instance/request identity, verifies queue and payload digests, and
returns a typed `ForwardEventWorkItem` containing the event and optional
counterfactual replay fingerprints. Canonical event acquisition remains an
explicit host-owned event-stream seam; no provider or engine is selected by
the transport payload.

Focused forward worker-handoff, dispatch, and persistence coverage passed 10
tests. Ruff and MyPy remain green across 281 source files. Event-stream
registration, worker authorization/capacity activation, and stable Nautilus
execution remain gated.

## 2026-09-25 - Forward-event dispatch persistence checkpoint

Added `PostgresForwardEventDispatchAdapter`, which reuses the authenticated
forward checkpoint/replay transaction and stages canonical event payload bytes,
idempotent forward dispatch identity, and the shared execution outbox together.
The application persistence bundle and adapter now expose this seam, and the
Alembic revision creates its owner/event/request uniqueness boundary. Replayed
events cannot create a second dispatch identity; the pure resolver returns a
typed conflict before persistence.

Focused forward-dispatch, application/persistence, and migration coverage
passed 29 tests. Ruff and MyPy remain green across 279 source files. Worker
authorization/capacity binding, event-stream activation, and stable Nautilus
execution remain gated.

## 2026-09-25 - Search dispatch payload durability checkpoint

The atomic PostgreSQL search-dispatch adapter now canonicalizes and verifies
the application payload against `DispatchRequest.payload_digest`, persists the
payload in the shared dispatch-payload table before enqueue, and rejects
changed bytes on replay. The application evidence path now forwards its
payload into that durable store. Redis workers can therefore resolve the
content-addressed handoff after dispatch without a second, uncoordinated
payload write.

Focused application and PostgreSQL dispatch coverage passed 18 tests. Ruff and
MyPy remain green across the package. Forward-event dispatch persistence and
stable Nautilus execution remain gated.

## 2026-09-25 - Search dispatch migration reconciliation checkpoint

The canonical additive Alembic revision now creates the two tables required by
`PostgresSearchDispatchAdapter`: owner-scoped execution admissions and
idempotent search dispatch identities. Their keys, uniqueness constraints, and
authenticated fields match the adapter schema, so durable search dispatch no
longer depends on undeclared tables. Migration coverage now asserts 41 v2
tables and the focused PostgreSQL search-dispatch/persistence suite passed 10
tests; Ruff and MyPy remain green across the package.

Forward-event dispatch persistence and stable Nautilus execution remain gated.

## 2026-09-25 - Local worker evidence resolver activation checkpoint

The opt-in `strategy-lab-v2-worker` Compose profile now defaults its evidence
resolver to the package-owned authenticated single-output mapper. This lets a
local worker reach callback composition without an unrelated blank environment
setting, while preserving explicit override for host-owned multi-artifact
mapping and the resolver's fail-closed publication checks. Compose validation
passed with the profile enabled; no worker or Docker socket was started.

Stable Nautilus execution, host multi-artifact policy, live runtime activation,
provider reconciliation, and deployment remain gated.

## 2026-09-25 - Search and forward state read API checkpoint

The application adapter now exposes authenticated reads for resumable search
checkpoints and restart-safe forward admission state, preserving owner
normalization and the persistence adapters' integrity checks. The versioned
router adds read-only `GET /experiments/{experiment_id}/search` and
`GET /forward-instances/{instance_id}/state` projections with typed 404/501
failure paths and stable state fingerprints. These reads do not mutate queues,
start workers, or infer provider/engine state.

Focused application coverage passed 15 tests and the read-only serializer
coverage passed 1 test. Ruff passed for the package and MyPy passed across 277
source files. The broader API TestClient rerun remains unavailable because the
restricted runtime hangs during Starlette context startup; stable Nautilus,
worker activation, provider reconciliation, and deployment remain gated.

## 2026-09-25 - Dedicated worker outbox scheduler checkpoint

`RedisDispatchRuntime` now exposes an `outbox_scheduler(...)` factory, and the
dedicated worker entrypoint starts that bounded transactional-outbox scheduler
beside the Redis worker pump whenever the runtime and persistence surfaces are
available. The relay task is cancelled and awaited before worker shutdown, so
Redis publication acknowledgements remain retry-safe without leaking a task.
Runtime doubles without an outbox surface continue to work for isolated tests.

Focused outbox/runtime and worker-entrypoint coverage passed 12 tests. Ruff
passed for the package and MyPy passed across 277 source files. Full production
Redis, migration, stable Nautilus, and deployment activation remain gated.

## 2026-09-25 - Explicit multi-artifact publication mapping checkpoint

The sandbox evidence resolver retains its safe single-file default and now
supports an explicit host-owned path mapping callback for result manifests
with multiple output artifacts. It requires an exact one-to-one mapping by
manifest digest, calls the byte-verifying `publish_file` path for each output,
and fails closed on missing/extra mappings, invalid paths, publisher rejection,
or missing publication plans. Worker payloads never select host paths.

Focused worker evidence coverage passed 14 tests, including the new
multi-artifact mapping and existing single-file rejection paths. Ruff passed
for the package and MyPy passed across 277 source files. Stable Nautilus,
worker activation, event-stream integration, and deployment remain gated.

## 2026-09-25 - Search candidate application lifecycle checkpoint

The application adapter now exposes owner-normalized search candidate
start/retry and terminal-record operations over `PostgresSearchStateAdapter`.
Candidate transition timestamps are normalized to UTC before persistence, and
the typed candidate phase/result boundary is validated before the durable
compare-and-set adapter is called. Search dispatch authorization and worker
transport remain explicit host-owned seams.

Focused application lifecycle coverage passed 2 tests. Ruff passed for the
package and MyPy passed across 277 source files. Search dispatch activation,
stable Nautilus execution, upstream reconciliation, and deployment remain
gated.

## 2026-09-25 - Forward lifecycle application seam checkpoint

`PostgresStrategyLabV2Adapter` now exposes owner-normalized forward lifecycle
operations over the durable forward-state adapter: instance registration,
compare-and-set lifecycle transition, one-time warm-up completion, and atomic
canonical event/correction admission. Transition timestamps are normalized to
UTC before persistence, while event acquisition and worker scheduling remain
explicit host responsibilities.

Focused application forward-lifecycle coverage passed 1 test. Ruff passed for
the package and MyPy passed across 277 source files. Forward event-stream
activation, provider integration, stable Nautilus execution, and deployment
remain gated.

## 2026-09-25 - Worker terminal publication binding checkpoint

`PostgresWorkerTerminalAdapter` now receives the shared result-publication
adapter from `PostgresStrategyLabV2Persistence`. Successful terminal retries
re-register the authenticated publication plan before manifest/completion
persistence; a rejected plan is rejected at the worker boundary, while exact
accepted retries continue through the atomic completion/artifact ledger. This
closes the bypass where a terminal callback could load publication evidence
but invoke completion without re-authenticating the owner-scoped plan.

Focused worker callback, terminal adapter, and persistence coverage passed 18
tests. Ruff passed for the package and MyPy passed across 277 source files.
Stable Nautilus execution, worker activation, publication-byte mapping, and
upstream/deployment gates remain open.

## 2026-09-25 - Application result publication/completion bridge checkpoint

`PostgresStrategyLabV2Adapter.publish_and_complete_result` now provides the
application-owned seam between authenticated host evidence and the durable
result adapters. It normalizes the authenticated principal, registers the
immutable owner-scoped publication plan before terminal completion, records
rejected plans without entering completion, and delegates accepted plans to
the atomic PostgreSQL completion/artifact transaction with UTC-normalized
completion time. This gives worker evidence lookup a durable publication
identity without claiming that publication-plan registration and completion
are one cross-table transaction.

Focused application/result coverage passed 5 tests. Ruff passed for the
changed package files and MyPy passed across 277 source files. The existing
full package rerun limitation remains: Starlette `TestClient` hangs during
context startup in this restricted runtime, while direct ASGI validation is
successful. Worker activation, publication-byte mapping, stable Nautilus v2,
upstream reconciliation, and deployment remain gated.

## 2026-09-25 - PostgreSQL read-model replay identity checkpoint

Persisted metric-set and runtime-request read models now normalize aware
creation/submission timestamps to UTC before durable record fingerprints are
calculated. Offset-equivalent PostgreSQL projections therefore retain one
replay identity while their canonical payload and authentication checks remain
unchanged. Focused adapter/provenance coverage passed 14 tests. Ruff passed for
the package, MyPy passed across 277 source files, 2 schema migration tests
passed, diff validation passed, and workstream validation accepted 30 records.

The branch remains `ready_for_human_review`. Application result-publication
wiring, dedicated worker activation, upstream provider/ETF/TC2000 reconciliation,
stable Nautilus v2 publication, and deployment remain gated.

## 2026-09-25 - Search and legacy replay identity checkpoint

Legacy records/import requests and resumable search candidate/checkpoint state
now normalize aware timestamps to UTC before preservation, monotonicity, and
replay identity. Offset-equivalent legacy observations and search transitions
therefore share one deterministic fingerprint. Focused regression coverage
passed 18 tests. Ruff passed for the package, MyPy passed across 277 source
files, 2 schema migration tests passed, diff validation passed, and workstream
validation accepted 30 records.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated. The previously
recorded restricted-runtime TestClient limitation remains open for full rerun
evidence; direct ASGI route validation remains successful.

## 2026-09-25 - Preflight and cleanup evidence identity checkpoint

Capability requirements/cells, provider coverage attestations, and artifact
cleanup evidence now normalize aware history, series, observation, attestation,
and filesystem timestamps to UTC before matching and fingerprinting. Canonical
serialization now gives `timedelta` an explicit structural representation,
allowing cleanup resolutions with minimum-age policies to fingerprint and replay
deterministically. Focused regression coverage passed 64 tests. Ruff passed for
the package, MyPy passed across 277 source files, the 2 migration tests passed,
diff validation passed, and workstream validation accepted 30 records.

The last complete exact backend gate remains 2,542 tests with 83.81% coverage
from the preceding artifact-lifecycle checkpoint. A fresh broad package rerun
could not complete in this restricted runtime because Starlette's `TestClient`
hangs even for a minimal FastAPI application during context startup; direct
ASGI transport for the Strategy Lab route succeeds. This is recorded as an
environmental validation limitation, not as a passing claim. The branch remains
`ready_for_human_review`; stable Nautilus v2 publication, shared
worker/database reconciliation, host activation, upstream provider/ETF/TC2000
integration, and deployment remain gated.

## 2026-09-25 - Artifact lifecycle identity checkpoint

Artifact commit, lineage, and retention timestamps now normalize aware
acquisition/creation/expiry/release/observation timestamps to UTC before
provenance, retention, and replay identity. Offset-equivalent artifact
lifecycle observations therefore retain one deterministic identity and replay
path. Focused artifact lifecycle coverage passed 20 tests. The complete branch
gate passed 891 package tests, 2 migration tests, Ruff, MyPy across 276 files,
diff validation, and workstream validation. The exact backend coverage gate
passed 2,542 tests with 83.81% total coverage (required threshold: 75%) and 86
warnings; the referenced runtime env file was absent and `.env.dev` supplied
test configuration. The cleanup helper refused Docker inspection in this
restricted session on both passes; the generated backend coverage shard was
removed explicitly after verification.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Transactional outbox identity checkpoint

Transactional outbox messages now normalize aware creation and availability
timestamps to UTC before ordering and state fingerprinting. Offset-equivalent
enqueue schedules therefore preserve one message identity and replay path while
remaining storage- and transport-neutral. Focused outbox coverage passed 15
tests. The complete branch gate passed 888 package tests, 2 migration tests,
Ruff, MyPy across 276 files, diff validation, and workstream validation. The
exact backend coverage gate passed 2,539 tests with 83.81% total coverage
(required threshold: 75%) and 86 warnings; the referenced runtime env file was
absent and `.env.dev` supplied test configuration. Two cleanup passes retained
zero testcontainer sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Result identity checkpoint

Engine result evidence, metric-set creation, and run-result manifest creation
timestamps now normalize aware offsets to UTC before content fingerprinting.
Offset-equivalent engine observations and manifest creation times therefore
retain one reproducible result identity and replay path. Focused result/core
coverage passed 25 tests. The complete branch gate passed 887 package tests,
2 migration tests, Ruff, MyPy across 276 files, diff validation, and workstream
validation. The exact backend coverage gate passed 2,538 tests with 83.81%
total coverage (required threshold: 75%) and 86 warnings; the referenced
runtime env file was absent and `.env.dev` supplied test configuration. Two
cleanup passes retained zero testcontainer sessions, containers, images, or
volumes.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Dispatch and acquisition identity checkpoint

Dispatch requests and provider acquisition requests/receipts now normalize
aware creation, request, and acquisition timestamps to UTC at their contract
boundaries. Offset-equivalent queue and data handoffs therefore preserve one
content identity and replay path. Focused dispatch/acquisition coverage passed
17 tests. The complete branch gate passed 886 package tests, 2 migration tests,
Ruff, MyPy across 276 files, diff validation, and workstream validation. The
exact backend coverage gate passed 2,537 tests with 83.80% total coverage
(required threshold: 75%) and 86 warnings; the referenced runtime env file was
absent and `.env.dev` supplied test configuration. Two cleanup passes retained
zero testcontainer sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Worker lifecycle timestamp checkpoint

Worker reservations, lease observations, and settlement receipts now normalize
aware acquisition, heartbeat, expiry, and release timestamps to UTC at their
contract boundaries. Offset-equivalent worker lifecycle observations therefore
retain one capacity/lease/settlement identity and replay path. Focused worker
lifecycle coverage passed 20 tests. The complete branch gate passed 884 package
tests, 2 migration tests, Ruff, MyPy across 276 files, diff validation, and
workstream validation. The exact backend coverage gate passed 2,535 tests with
83.80% total coverage (required threshold: 75%) and 86 warnings; the
referenced runtime env file was absent and `.env.dev` supplied test
configuration. Two cleanup passes retained zero testcontainer sessions,
containers, images, or volumes.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Conformance evidence gate checkpoint

Conformance evidence construction now fails closed when a fixture suite omits a
required check, while retaining complete suites with failed observations as
explicit compatibility evidence. Conformance test timestamps normalize to UTC,
so offset-equivalent evidence retains one identity. Focused conformance
coverage passed 16 tests. The complete branch gate passed 881 package tests,
2 migration tests, Ruff, MyPy across 276 files, diff validation, and workstream
validation. The exact backend coverage gate passed 2,532 tests with 83.79%
total coverage (required threshold: 75%) and 86 warnings; the referenced
runtime env file was absent and `.env.dev` supplied test configuration. Two
cleanup passes retained zero testcontainer sessions, containers, images, or
volumes.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
shared worker/database reconciliation, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Search candidate dispatch API boundary checkpoint

The versioned API now exposes `POST /experiments/{experiment_id}/search/dispatch`.
It strictly validates the candidate index, attempt identity, content-addressed
payload, queue name, timestamp, and `Idempotency-Key`, then delegates the full
candidate/admission/dispatch decision to an application-owned callback. The
response serializes the candidate state, admission ledger, worker-pool
evidence, and deterministic dispatch envelope. Saturation, conflicts, and
rejections map to typed retryable or fail-closed API errors.

`PostgresStrategyLabV2Adapter` accepts the same optional callback and normalizes
the authenticated owner before delegation. No partial mutation is attempted
when the binding is absent; the route returns a typed 501 precondition failure.
The callback remains deliberately host-owned because authorization, runtime
preflight, worker reservation, PostgreSQL CAS, and outbox staging must be one
transaction. Focused API/application coverage passed 34 tests, including
successful evidence serialization, strict-body rejection, and missing-binding
failure. The next durable slice is the PostgreSQL candidate/admission/outbox
transaction; worker process execution remains gated by stable Nautilus v2
conformance.

## 2026-09-25 - Atomic PostgreSQL search dispatch checkpoint

`postgres_search_dispatch.py` now provides the durable counterpart to the
pure search-dispatch resolver. In one SQLAlchemy transaction it locks the
owner-scoped search state and worker profile/reservations, authenticates the
admission and dispatch ledgers, resolves candidate start plus worker admission
plus idempotent queue intent, and persists the candidate CAS update, worker
reservation, admission receipt, dispatch identity, and shared execution
outbox message together. Saturation, rejection, and conflict resolutions
return before any write. Exact retries replay the existing admission and
dispatch evidence without duplicating rows.

The pure resolver also rejects a second dispatch identity for an already bound
attempt, so a new idempotency key cannot create a duplicate queue message for
the same candidate.

## 2026-09-25 - Durable search dispatch application binding checkpoint

`PostgresStrategyLabV2Adapter` now accepts a typed
`SearchDispatchEvidence` resolver. The host supplies authenticated execution
authorization, runtime request/preflight, reservation identity, and dispatch
time; the application then calls the shared `PostgresSearchDispatchAdapter`
itself, preserving one transaction for search state, worker capacity, admission,
dispatch, and outbox. The older result-returning callback remains available
for registration-neutral hosts, and configuring both forms is rejected as
ambiguous. Focused application coverage passed 10 tests, including normalized
owner propagation, durable-store delegation, and fail-closed missing binding.

## 2026-09-25 - Authenticated worker dispatch lookup checkpoint

`PostgresSearchDispatchAdapter` now exposes owner-scoped lookup by experiment
and candidate, plus an ambiguity-rejecting lookup by the Redis request
fingerprint. Both paths re-authenticate the dispatch request and its stored
fingerprint before returning the attempt/queue identity needed by a worker or
recovery handler; no owner is guessed when a request identity is ambiguous.
Focused lookup coverage passed 3 tests. Dedicated worker handler binding and
stable Nautilus execution remain separate gates.

The shared persistence bundle now exposes this adapter while leaving runtime
authorization, provider entitlement, and Nautilus execution as explicit host
inputs. The additive schema declares only admission and search-dispatch tables;
the existing execution-outbox table remains the authoritative shared outbox.
Focused PostgreSQL/persistence/application coverage passed 17 tests and the
complete package passed 866 tests. Stable Nautilus v2 conformance, host
capability/evidence resolvers, upstream provider/ETF/TC2000 reconciliation,
and migration/application integration remain open gates.

## Human authorization

- Recorded at: 2026-09-15T19:48:24.815519+00:00
- Request: Implement the approved Strategy Lab v2 plan; honor the repository AI-driven workflow rules and active branch boundaries.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: ready; the plan remains at `ready_for_human_review` and the
  session-local goal is held at its plan-ready guard.

## 2026-09-25 - Capability preflight API seam checkpoint

The registration-neutral v2 router now exposes `POST /capabilities/preflight`.
Requests require a canonical JSON object and `Idempotency-Key`; an optional
application-owned `preflight_capability` binding receives the authenticated
principal, request identity, idempotency key, payload, and payload digest, then
returns the typed `CapabilitySummary` without exposing provider or engine
handles. Responses are stable `capability-preflights` documents with report,
binding, request, and payload fingerprints. If the host has not supplied the
binding, the route fails closed with `capability_unsupported`/501 rather than
inventing entitlement or engine capability.

Focused API coverage passed 23 tests, including successful delegation,
canonical identity propagation, malformed-body rejection, and the missing
binding failure. Capability calculation, provider entitlement, engine
registration, and application wiring remain host-owned gates. The authorized
push remains blocked by the environment's rejected GitHub SSH key
(`Permission denied (publickey)`).

## 2026-09-25 - Application capability preflight binding checkpoint

`PostgresStrategyLabV2Adapter` now exposes the optional application-owned
capability resolver behind the registration-neutral route. The resolver receives
the normalized owner, request/idempotency identities, canonical payload, and
payload digest; its typed `CapabilitySummary` is authenticated and registered
through the shared owner-scoped PostgreSQL capability adapter before the API
response is returned. A missing resolver remains an explicit typed 501 rather
than silently treating provider or engine capability as available.

Focused application tests cover owner normalization, durable summary handoff,
route registration, and the missing-binding failure. Provider entitlement,
engine registration, and the resolver's actual calculation remain host-owned
and are not inferred by this branch.

## 2026-09-25 - Durable search queue API checkpoint

The versioned API now exposes durable search lifecycle routes:
`POST /experiments/{experiment_id}/search` strictly accepts a content-addressed
trial-fingerprint list and creates/replays the owner-scoped PostgreSQL search
queue, while `POST /experiments/{experiment_id}/search/cancel` records an
idempotent cancellation request. Responses expose candidate phases, attempt
lineage, cancellation state, and authenticated state fingerprints as a stable
`search-experiments` document. Conflicting definitions, invalid fingerprints,
and missing search persistence fail closed with typed errors; no worker or
engine execution is started by FastAPI.

The application adapter now delegates initialization and cancellation to the
existing CAS-backed `PostgresSearchStateAdapter`. Focused router coverage
passed 25 tests; search dispatch, worker scheduling, and engine execution
remain separate durable-worker gates.

## 2026-09-25 - Result-manifest artifact binding checkpoint

Result completion now accepts the successful manifest's output-artifact
identities as an optional application-supplied evidence set. When supplied,
the pure completion gate rejects omitted, substituted, duplicated, or extra
artifact publication plans before any commit is resolved. The PostgreSQL
completion adapter carries the same evidence through its transaction, and the
worker terminal adapter supplies `RunResultManifest.output_artifacts` so the
host resolver cannot finalize a result against unrelated artifact bytes.

Focused completion/persistence tests passed 10 tests; the complete Strategy Lab
v2 package passed 832 tests. Branch-declared validation passed all six checks
(832 package tests, 2 migration tests, Ruff, MyPy across 270 files, diff, and
workstream validation). The exact backend gate passed 2,483 tests at 83.73%
coverage with 86 warnings; the referenced runtime env file was absent in this
checkout and `.env.dev` supplied test configuration. Compose profile validation
passed, and both required cleanup passes retained zero testcontainer sessions,
containers, images, or volumes. Host application evidence resolution, stable
Nautilus release conformance, upstream contract reconciliation, and full
application integration remain open gates.

## 2026-09-25 - Typed worker terminal evidence resolver checkpoint

`worker_evidence_resolution.py` now deterministically combines the authenticated
owner/attempt lookup, durable submission/outcome/progress state, result
manifest, and accepted publication plan into `WorkerTerminalEvidence`. It
rejects process/attempt drift, missing or conflicting durable evidence,
multiple publication candidates, non-terminal runtime state, and artifact
plans on failed/cancelled runs. Artifact-file mapping remains an explicit host
callback; no worker path or principal is guessed. The persistence bundle now
exposes `worker_terminal_evidence_resolver()` to compose its authenticated
lookup with that callback shape.

Focused resolver/persistence tests passed 7 tests; the complete Strategy Lab v2
package passed 836 tests. Branch-declared validation passed all six checks
(836 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff, and
workstream validation). The exact backend gate passed 2,487 tests at 83.73%
coverage with 86 warnings; the referenced runtime env file was absent in this
checkout and `.env.dev` supplied test configuration. Compose profile validation
passed, and both required cleanup passes retained zero testcontainer sessions,
containers, images, or volumes. Host artifact mapping, stable Nautilus release
conformance, upstream contract reconciliation, and full application
integration remain open gates.

## 2026-09-25 - Artifact publication plan handoff checkpoint

`ArtifactPublicationResolution` now retains the exact verified
`ArtifactPublicationPlan` used for storage and commit finalization. Successful
create and replay resolutions therefore expose the same manifest/content/
retention/action identity that terminal completion must receive, while
rejections cannot carry a plan. This removes a reconstruction gap for the
explicit host artifact-mapping callback and keeps publication policy bound to
the verified bytes that were actually written.

Focused artifact-application tests passed 9 tests; the complete Strategy Lab
v2 package passed 836 tests. Branch-declared validation passed all six checks
(836 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff, and
workstream validation). The exact backend gate passed 2,487 tests at 83.73%
coverage with 86 warnings; the referenced runtime env file was absent in this
checkout and `.env.dev` supplied test configuration. Compose profile validation
passed, and both required cleanup passes retained zero testcontainer sessions,
containers, images, or volumes. Host artifact source mapping, stable Nautilus
release conformance, upstream contract reconciliation, and full application
integration remain open gates.

## 2026-09-25 - Single-output sandbox artifact mapper checkpoint

`create_sandbox_artifact_plan_resolver()` now composes the worker process
evidence with `LocalArtifactPublicationService.publish_sandbox_result()` for
the current one-file `/outputs/result` contract. It returns the exact verified
publication plan retained by the service, so terminal completion can bind its
artifact commit to the bytes observed by the sandbox. Manifests containing
multiple output artifacts fail closed and require an explicit host mapping
callback; failed/cancelled runs produce no artifact plans.

Focused resolver/artifact tests passed 5 tests; the complete Strategy Lab v2
package passed 838 tests. Branch-declared validation passed all six checks
(838 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff, and
workstream validation). The exact backend gate passed 2,489 tests at 83.74%
coverage with 86 warnings; the referenced runtime env file was absent in this
checkout and `.env.dev` supplied test configuration. Compose profile validation
passed, and both required cleanup passes retained zero testcontainer sessions,
containers, images, or volumes. Multi-artifact host mapping, stable Nautilus
release conformance, upstream contract reconciliation, and full application
integration remain open gates.

## 2026-09-25 - Package evidence resolver factory checkpoint

`worker_callbacks.py` now exposes
`default_evidence_resolver_factory(persistence, artifact_root)`. When selected
through the existing namespaced resolver setting, it composes the shared
owner/attempt lookup, the single-output sandbox artifact mapper, and the
durable PostgreSQL terminal writer without a host-specific module. Startup
remains fail-closed when the resolver setting is absent or malformed; the
factory itself still rejects persistence bundles missing explicit artifact or
terminal composition methods.

Focused callback tests passed 5 tests; the complete Strategy Lab v2 package
passed 839 tests. Branch-declared validation passed all six checks (839
package tests, 2 migration tests, Ruff, MyPy across 272 files, diff, and
workstream validation). The exact backend gate passed 2,490 tests at 83.74%
coverage with 86 warnings; the referenced runtime env file was absent in this
checkout and `.env.dev` supplied test configuration. Compose profile validation
passed, and both required cleanup passes retained zero testcontainer sessions,
containers, images, or volumes. Multi-artifact host mapping, deployment
configuration selection, stable Nautilus release conformance, upstream
contract reconciliation, and full application integration remain open gates.

## 2026-09-25 - Mounted result evidence checkpoint

`sandbox.py` now exposes the validated host source for the hardened
`/outputs/result` bind mount, reusing the same mount parser used by plan
validation. `sandbox_execution.py` hashes a successful mounted result file in
bounded streaming chunks and records its content digest and byte length on
`SandboxRunResult`; symlinks, directories, missing files, and files over the
declared output limit produce no valid result-file evidence. The executor does
not publish bytes or choose an application result manifest: those remain
application-owned adapter responsibilities, while stdout/stderr runtime
evidence remains backward compatible.

Focused sandbox tests passed 12 tests, the complete Strategy Lab v2 package
passed 823 tests, and branch-declared validation passed all six checks across
823 package tests, migrations, Ruff, MyPy across 270 files, diff, and
workstream validation. The exact backend gate passed 2,474 tests at 83.73%
coverage with 86 warnings; the referenced runtime env file was absent in this
checkout and `.env.dev` supplied test configuration. Both required cleanup
passes retained zero testcontainer sessions, containers, images, or volumes.
The application-owned evidence resolver, stable Nautilus release, upstream
contract reconciliation, and full application integration remain open gates.

## 2026-09-25 - Streamed local artifact publication checkpoint

`artifacts.py` now verifies digest/byte-length observations independently of
in-memory payloads. `LocalArtifactStore.publish_file()` streams regular local
result files into the same-directory temporary/atomic-link workflow, verifies
the manifest before linking, re-verifies existing/racing/published targets by
streamed digest and length, and never buffers the mounted artifact. The
application publication service exposes `publish_file()` and finalizes the
existing idempotent PostgreSQL commit ledger through the same publication
decision path as byte payloads. Symlinks, directories, digest/length drift,
and malformed target content fail closed.

Focused artifact tests passed 27 tests; the complete Strategy Lab v2 package
passed 828 tests. Branch-declared validation passed all six checks across 828
package tests, migrations, Ruff, MyPy across 270 files, diff, and workstream
validation. The exact backend gate passed 2,479 tests at 83.73% coverage with
86 warnings; the referenced runtime env file was absent in this checkout and
`.env.dev` supplied test configuration. Both required cleanup passes retained
zero testcontainer sessions, containers, images, or volumes. Host application
evidence resolution, stable Nautilus release conformance, upstream contract
reconciliation, and full application integration remain open gates.

## 2026-09-25 - Sandbox-bound artifact publication checkpoint

`LocalArtifactPublicationService.publish_sandbox_result()` now binds artifact
publication to the exact successful `SandboxCommandPlan` and
`SandboxRunResult`. It requires captured mounted-file evidence, verifies the
manifest digest and byte length before any storage or commit operation, derives
the validated `/outputs/result` host source from the plan, and delegates to
streamed file publication. Plan drift, failed executions, missing evidence,
and manifest identity drift fail before the artifact ledger can change.

Focused artifact tests passed 29 tests; the complete Strategy Lab v2 package
passed 830 tests. Branch-declared validation passed all six checks across 830
package tests, migrations, Ruff, MyPy across 270 files, diff, and workstream
validation. The exact backend gate passed 2,481 tests at 83.73% coverage with
86 warnings; the referenced runtime env file was absent in this checkout and
`.env.dev` supplied test configuration. Both required cleanup passes retained
zero testcontainer sessions, containers, images, or volumes. Host application
evidence resolution, stable Nautilus release conformance, upstream contract
reconciliation, and full application integration remain open gates.

## 2026-09-25 - Mounted result identity materialization checkpoint

Successful runtime materialization now uses the validated mounted result-file
digest and byte length as terminal output evidence whenever that file was
captured by the sandbox. Legacy plans without a mounted result continue to use
their bounded stdout evidence. Both the pure runtime adapter and the
owner-scoped PostgreSQL runtime adapter apply the same selection, so retries,
compare-and-set state, and persisted update receipts cannot silently switch
between logs and the produced result artifact.

Focused runtime/sandbox/persistence tests passed 20 tests; the complete
Strategy Lab v2 package passed 824 tests. Branch-declared validation passed
all six checks across 824 package tests, migrations, Ruff, MyPy across 270
files, diff, and workstream validation. The exact backend gate passed 2,475
tests at 83.73% coverage with 86 warnings; the referenced runtime env file was
absent in this checkout and `.env.dev` supplied test configuration. Both
required cleanup passes retained zero testcontainer sessions, containers,
images, or volumes. Host application evidence resolution, stable Nautilus
release conformance, upstream contract reconciliation, and full application
integration remain open gates.

## 2026-09-25 - Typed metric-set rehydration

`postgres_metrics.py` now exposes owner-scoped `load_metric_set()` and
`load_all_metric_sets()` reads that strictly rehydrate authenticated canonical
payloads into `MetricSet` contracts through the shared allowlisted decoder.
Reads require exact canonical bytes and verify metric-set fingerprint, ID,
trial/attempt lineage, definition version, creation timestamp, and compact
value-summary bytes against the persisted projection. Reordered fields or
other payload tampering therefore fails closed before metric data reaches later
result/API adapters.

Focused lint and MyPy checks pass; the focused persistence suite passes 10
tests and the complete Strategy Lab v2 package passes 805 tests. The following
typed-resource integration checkpoint then passed all six branch checks, the
exact backend gate (2,457 tests at 83.69% coverage), two cleanup passes, and
workstream validation. The canonical push remains blocked by the environment's
rejected GitHub SSH key (`Permission denied (publickey)`).

## 2026-09-25 - Typed metric-set resource projection

The application persistence bundle now projects `metric-sets` API resources
from `PostgresMetricsAdapter.load_all_metric_sets()` instead of exposing raw
`PersistedMetricSet` summary rows. Resource IDs and revision metadata are bound
to the typed contract identity, so every API metric-set read passes through
canonical payload, lineage, and value-summary verification first.

Focused lint and MyPy checks pass; the focused persistence/metric suite passes
6 tests and the complete Strategy Lab v2 package passes 806 tests. The exact
backend gate passes 2,457 tests at 83.69% coverage, both cleanup passes retain
zero testcontainer resources, and all branch/workstream checks are recorded in
`validation.jsonl`.

## 2026-09-25 - Typed runtime-preflight rehydration

`postgres_runtime_receipts.py` now exposes
`load_preflight_contract()`, rehydrating the canonical
`StrategyRuntimePreflight` payload through the shared allowlisted decoder.
Reads require exact canonical bytes and verify request/profile/isolation
fingerprints, decision, and rejection-reason projections before admission
evidence is returned. Runtime contract modules are now part of the decoder's
explicit allowlist; unsupported tags and reordered fields fail closed.

Focused lint and MyPy checks pass; the focused runtime/materialization suite
passes 11 tests and the complete Strategy Lab v2 package passes 807 tests.

The exact backend gate then passed 2,458 tests at 83.69% combined coverage
with 86 warnings; both cleanup passes retained zero testcontainer resources.
The branch-declared checks and workstream validator remain green.

## 2026-09-25 - Opt-in worker Compose activation

The root Compose stack now exposes `strategy-lab-v2-worker` under the explicit
`strategy-lab-v2` profile, leaving the general ARQ worker unchanged. The
profile waits for PostgreSQL/Redis health, mounts a dedicated
`strategy_lab_artifacts` volume, runs with a read-only root, dropped
capabilities, no-new-privileges, and bounded `/tmp`, and binds the local Docker
socket only when the configured socket exists. Its namespaced callback factory
is intentionally empty by default, so enabling the profile without application
terminal/result wiring fails closed at startup rather than silently processing
jobs with incomplete evidence.

`docker compose --profile strategy-lab-v2 config --quiet` passes and the
rendered service contains no provider credentials. Stable Nautilus release
conformance and callback implementation remain separate gates.

## 2026-09-25 - Typed worker dispatch handoff

`worker_handoff.py` now defines the versioned
`strategy-lab.worker-execution-request.v1` envelope. It binds canonical
`WorkerExecutionRequest` bytes to the outer `DispatchPayload` digest, fully
rehydrates nested authorization/admission/runtime/sandbox/engine/worker/lease
contracts through the allowlisted decoder, and exposes an async
`materialize_worker_handoff()` callback adapter. Schema drift, reordered
canonical fields, request-fingerprint drift, and outer-envelope drift fail
closed before process execution.

Focused handoff/process checks pass (7 tests); the complete Strategy Lab v2
package passes 810 tests. Terminal/result evidence resolution remains an
application-owned callback gate.

## 2026-09-25 - Resolver-configured worker callbacks

`worker_callbacks.py` now composes `materialize_worker_handoff()` with the
durable `PostgresWorkerTerminalAdapter`. The opt-in worker loads an explicit
`STRATEGY_LAB_V2_EVIDENCE_RESOLVER` module/attribute factory and fails before
opening Redis when it is missing, malformed, or does not return a callable
resolver. A legacy completion path is retained only as a typed retry guard;
terminal evidence cannot be acknowledged without the durable terminal writer.

The callback package is covered by focused composition tests and the full
branch/coverage gates below. The resolver remains intentionally application
owned: this branch supplies the typed composition boundary, not a guessed
resource lookup or transport-derived evidence implementation.

The environment contract now names the package-owned callback composer as the
default and documents the resolver as the only required application setting.
Malformed module/attribute targets are rejected before callback construction;
the focused callback/handoff suite covers missing, malformed, and valid
resolver configuration.

`PostgresSubmissionDispatchAdapter.load_submission()` now provides the
owner-scoped, authenticated attempt lookup that an application evidence
resolver needs to bind terminal context to a durable `SubmissionReceipt`.
Missing attempts return no record; duplicate attempt bindings and row identity
drift fail closed.

`worker_evidence.py` and
`PostgresStrategyLabV2Persistence.load_worker_terminal_evidence_inputs()` now
compose the authenticated submission, execution outcome/progress context,
rehydrated result manifest, and owner-scoped publication plans for an explicit
application resolver. The bundle preserves missing-state signals and requires
all returned records to retain the same attempt identity and deterministic
publication ordering; it does not pretend those independent reads are one
cross-table transaction.

The worker-facing lookup now derives the owner from the unique durable
submission request fingerprint (`load_submission_binding()`), then performs
owner-scoped evidence reads. If the same request/attempt identity is bound to
multiple owners, the adapter rejects it as ambiguous; no tenant is guessed
from Redis or strategy payload bytes.

## 2026-09-24 - Typed result-manifest rehydration

`postgres_result_materialization.py` now exposes owner-scoped
`load_manifest()` and `load_all_manifests()` reads that fully rehydrate the
authenticated canonical payload into the typed `RunResultManifest` contract.
The decoder is allowlisted to the Strategy Lab contracts, capability, and
rebalance modules; it validates every canonical tag, exact dataclass schema,
enum type, and contract constructor, then verifies manifest, attempt, trial,
metric-set, and snapshot identities against the persisted projection. Artifact
reads now use that validated typed manifest, so nested tampering or contract
drift fails closed rather than being projected through a narrow field parser.

Focused lint and MyPy checks pass; the focused materialization suite passes 5
tests and the complete Strategy Lab v2 package passes 803 tests. Branch validation, exact backend
coverage, cleanup, and the checkpoint push remain to be recorded below.

The corrected focused suite passes 5 tests including authenticated nested-tag
tamper rejection. Branch-declared validation passes all 6 checks (803 package
tests, migration checks, Ruff, MyPy, diff, and workstream validation). The exact
backend gate passes 2,452 tests at 83.68% combined coverage with 86 warnings;
both required cleanup passes retain zero testcontainer sessions, containers,
images, or volumes. The implementation checkpoint and canonical branch push
follow this evidence.

The local checkpoint is complete, but the canonical push could not be completed
from this environment: the configured GitHub SSH key is rejected with
`Permission denied (publickey)`, and the HTTPS retry has no available username
credential. The local tracking ref remains at `c5583f5b8`; no remote state is
claimed beyond that checkout-local reference.

## 2026-09-24 - Canonical result-manifest byte enforcement

The typed result-manifest decoder now requires the decoded contract to
re-serialize to the exact stored canonical bytes. Authenticated rows with
reordered dataclass fields or unsupported nested tags are rejected before
lineage or artifact projection, preserving content-addressed identity rather
than merely accepting semantically equivalent JSON.

Focused lint/MyPy/materialization tests pass (6 tests), and the complete
Strategy Lab v2 package passes 804 tests. Branch and exact-gate evidence for
this follow-up is pending.

Branch-declared validation passes all 6 checks (804 package tests, migration
checks, Ruff, MyPy, diff, and workstream validation). The exact backend gate
passes 2,453 tests at 83.68% combined coverage with 86 warnings; both cleanup
passes retain zero testcontainer sessions, containers, images, or volumes.

## 2026-09-24 - API startup migration rollout

The FastAPI lifespan now invokes the existing idempotent
`StrategyLabV2MigrationService` before provider seeding, scheduling, or API
readiness whenever `STRATEGY_LAB_V2_MIGRATIONS_ENABLED` is enabled. It uses the
sync PostgreSQL URL and repository Alembic path, logs only stable failure
digests, and raises a generic startup failure before accepting work. Compose
enables this setting by default while the documented local `.env.example`
default remains opt-in for test/developer environments; the worker entrypoint
continues to own its independent migration gate.

Focused startup migration tests pass (2), branch validation passes all 6
checks, and the exact backend gate passes 2,455 tests at 83.68% coverage with
86 warnings. Both cleanup passes retain zero testcontainer sessions,
containers, images, or volumes.

## 2026-09-17 - Concrete terminal/result persistence adapter

`worker_terminal_adapter.py` now provides the application-owned terminal
writer over the existing runtime, public outcome/progress, result-completion,
summary, and worker-state adapters. A typed `WorkerTerminalEvidence` resolver
supplies only authenticated principal/submission/result/publication evidence;
the coordinator re-materializes the Nautilus runtime result, applies the pure
terminal and worker-settlement gates, persists the public terminal pair,
finalizes successful result/artifact commits, records the execution summary,
retains a settlement receipt, and atomically releases the worker lease and
serial reservation before returning a Redis acknowledgement digest. Process
timeouts and missing evidence remain pending for recovery; rejected or
contradictory evidence is never acknowledged.

`postgres_worker_settlement.py` and additive migration `ff2a3b4c5d6e` retain
owner-scoped immutable settlement receipts. The coordinator handles the
crash window where that receipt exists before capacity release by rebuilding
the deterministic pure proposal and letting the receipt adapter verify exact
identity. `PostgresWorkerStateAdapter.load_lease()` exposes the authenticated
lease history needed by the writer. The persistence bundle now exposes
`worker_terminal_writer(...)` as the explicit callback factory seam; no
FastAPI, general ARQ worker, Compose, provider, ETF, or TC2000 path was
modified.

Focused terminal/settlement tests passed (9 tests) and the full Strategy Lab v2
package passed 769 tests. Compose activation, stable Nautilus conformance,
upstream contract reconciliation, and full repository integration remain open.

Update this handoff at each coherent boundary.

## 2026-09-17 - Durable resource-creation aggregate bridge

`PostgresStrategyLabV2Adapter.create_resource()` now connects the generic
mutable-resource route to the shared compare-and-set aggregate store. The
application seam normalizes the authenticated owner, derives a stable resource
identity, binds storage request identity to owner/resource/idempotency content,
and persists the mutation fingerprint plus accepted timestamp alongside the
resource envelope. Exact retries reconstruct the original receipt (including
its original acceptance time) after a process restart; changed payloads,
resource collisions, and cross-owner access fail closed without projecting the
foreign document. Domain-specific validation, outbox publication, result
policy, migration startup, worker activation, and stable Nautilus execution
remain separate gates.

Focused application/resource/router tests passed (25 tests). The next
checkpoint must include the full Strategy Lab v2 package, exact backend
coverage, branch validation, and branch-scoped resource cleanup.

## 2026-09-17 - Typed strategy resource registration

`resource_domains.py` now owns the first domain-specific mutation decoder. A
`POST /strategy-lab/v2/strategies` envelope is converted into the immutable
`StrategyVersion` contract before aggregate persistence: source and dependency
digests are validated, exact dependency versions are canonicalized, parameter
maps are frozen, unknown fields are rejected, and conflicting `id`/
`resource_id` aliases fail closed. The normalized strategy fingerprint is
retained in resource metadata and the application bridge continues to provide
owner-bound compare-and-set and exact replay.

Other mutable resource types remain registration-neutral until their domain
adapters are implemented. Focused domain/application/API tests passed (29
tests); Compose activation, stable Nautilus conformance, upstream contract
reconciliation, and full repository integration remain open.

## 2026-09-17 - Typed strategy package resource registration

`resource_domains.py` now extends the application-owned typed mutation boundary
to strategy packages. Source archives and wheels are represented by the
immutable `StrategyPackage` contract: the linked strategy fingerprint, archive,
manifest, and dependency-lock digests, positive archive length,
module-entrypoint, SDK version, and runtime ABI are validated and
canonicalized. Unknown fields and conflicting API ID aliases fail closed, and
the package fingerprint is retained in resource metadata through the same
owner-scoped compare-and-set and exact-replay bridge used for strategies.

Focused package/domain/application tests passed (31 tests); the full Strategy
Lab v2 package passed 788 tests, branch-declared validation passed, and Compose
activation, stable Nautilus conformance, upstream contract reconciliation, and
full repository integration remain open.

## 2026-09-17 - Typed portfolio resource registration

`resource_domains.py` now extends typed mutation validation to portfolio
compositions. The application decodes exact decimal initial capital and
component weights, strategy-linked instrument components, shared risk limits
and product risk models, and optional calendar rebalance policy into the
immutable `PortfolioComposition` contract. Nested unknown fields, invalid
digests/enums/decimals, duplicate or overweight components, and conflicting
API ID aliases fail closed; the portfolio fingerprint is retained in resource
metadata through the existing owner-scoped compare-and-set and exact-replay
bridge.

Focused portfolio/domain/application tests passed (13 tests); the full Strategy
Lab v2 package passed 790 tests. Compose activation, stable Nautilus
conformance, upstream contract reconciliation, and full repository integration
remain open.

## 2026-09-17 - Typed experiment resource registration

`resource_domains.py` now extends typed mutation validation to experiment
definitions. The application binds portfolio, strategy-version, snapshot, and
capability-contract digests with an integer seed, metric-definition version,
and frozen engine contract through the immutable `ExperimentDefinition`
contract. Strategy fingerprint order is canonicalized; unknown fields,
malformed digest lists, non-integer seeds, invalid engine contracts, and
conflicting API ID aliases fail closed; the experiment fingerprint is retained
in resource metadata through the existing owner-scoped compare-and-set and
exact-replay bridge.

Focused experiment/domain/application tests passed (15 tests); the full
Strategy Lab v2 package passed 792 tests. Compose activation, stable Nautilus
conformance, upstream contract reconciliation, and full repository integration
remain open.

## 2026-09-17 - Typed run-attempt resource registration

`resource_domains.py` now extends typed mutation validation to run attempts.
Attempt identity, trial linkage, positive ordinal, lifecycle state, and
timezone-aware creation/update timestamps are decoded into the immutable
`RunAttempt` contract; API ID aliases and malformed timestamps/states fail
closed. A stable identity digest excludes mutable timestamps/state while the
normalized lifecycle envelope remains available to the owner-scoped
compare-and-set and exact-replay bridge.

Focused attempt/domain/application tests passed (17 tests); the full Strategy
Lab v2 package passed 794 tests. Compose activation, stable Nautilus
conformance, upstream contract reconciliation, and full repository integration
remain open.

## 2026-09-17 - Typed data snapshot resource registration

`resource_domains.py` now extends typed mutation validation to frozen data
snapshots. Embedded capability requirements, decisions, degradations, and
preflight fingerprints are rehydrated through the existing fail-closed
capability contracts; each series validates event semantics, UTC coverage
intervals, adjustment/corporate-action policy, provider evidence digest,
content digest, and positive row count. The immutable `DataSnapshot` fingerprint
is retained in resource metadata, with unknown fields, tampered preflight
identity, malformed series, and conflicting API ID aliases rejected before
aggregate persistence.

Focused snapshot/preflight tests passed (14 tests); the full Strategy Lab v2
package passed 796 tests. Compose activation, stable Nautilus conformance,
upstream contract reconciliation, and full repository integration remain open.

## 2026-09-17 - Typed trial resource registration

`resource_domains.py` now extends typed mutation validation to scientific
trials. It rehydrates the embedded fail-closed preflight report, freezes
parameter/scenario inputs, preserves explicit or derived `TrialRandomization`
provenance, validates optional UTC evaluation windows, and derives the
canonical `ScientificTrial.trial_id` when omitted. Supplied IDs must match the
immutable identity; malformed randomization, unsupported capability reports,
and conflicting API ID aliases fail closed before aggregate persistence.

Focused trial/domain tests passed (16 tests); the full Strategy Lab v2 package
passed 798 tests. Compose activation, stable Nautilus conformance, upstream
contract reconciliation, and full repository integration remain open.

## 2026-09-17 - Typed metric-set resource registration

`resource_domains.py` now extends typed mutation validation to metric sets.
Metric values validate exact decimal/null semantics, basis, sample size,
annualization and calculation context, nested formula definitions, and
content-addressed evidence references before the immutable `MetricSet`
contract is persisted. Values are canonically ordered by name/basis/unit;
unknown fields, malformed evidence/digests, null values without reasons, and
conflicting API ID aliases fail closed.

Focused metric/domain tests passed (18 tests); the full Strategy Lab v2 package
passed 800 tests. Compose activation, stable Nautilus conformance, upstream
contract reconciliation, and full repository integration remain open.

## 2026-09-17 - Typed forward-instance resource registration

`resource_domains.py` now completes typed mutation validation for the persisted
forward-instance identity. Portfolio and warm-up snapshot digests, carry-in and
lifecycle state, event progress, correction count, timestamp ordering, and
resource ID aliases are validated through the immutable `ForwardInstance`
contract before persistence. Invalid progress, state, timestamps, digests,
unknown fields, and conflicting aliases fail closed; normalized timestamps are
UTC and the domain fingerprint is content-addressed.

Focused metric/domain tests passed (20 tests); the full Strategy Lab v2 package
passed 802 tests. Compose activation, stable Nautilus conformance, upstream
contract reconciliation, and full repository integration remain open.

## 2026-09-17 - Worker terminal metric-set persistence

The dedicated PostgreSQL worker terminal callback now requires the shared
metrics adapter and persists the successful `RunResultManifest.metric_set`
after result completion. The operation is idempotent and retry-safe, so a crash
between completion and final settlement can replay the exact metric-set record;
metric persistence failures leave the transport entry pending for recovery.

Focused terminal/persistence tests passed (3 tests); the branch-declared suite
passed 802 package tests plus migration, Ruff, MyPy, diff, and workstream checks.
The exact combined backend gate passed 2,451 tests with 83.70% coverage (75%
required); both branch-scoped cleanup passes left no testcontainer sessions.

## 2026-09-17 - Worker terminal result-manifest persistence

The dedicated PostgreSQL worker terminal callback now registers the successful
`RunResultManifest` through the shared result-materialization adapter before
result completion. The manifest remains owner-scoped, attempt-bound,
immutable, and replay-safe; persistence failures leave the transport entry
pending and prevent acknowledgement of an unregistered result. Metric-set
persistence remains the post-completion idempotent step.

Focused terminal/persistence tests passed (3 tests); the branch-declared suite
passed 802 package tests plus migration, Ruff, MyPy, diff, and workstream checks.
The exact combined backend gate passed 2,451 tests with 83.70% coverage (75%
required); both branch-scoped cleanup passes left no testcontainer sessions.

## 2026-09-17 - Executable Nautilus conformance harness

`conformance_fixtures.py` now exposes `execute_conformance_suite(...)`, an
engine-neutral executable fixture boundary. It requires an exact expected
digest for every required conformance check, invokes each check in deterministic
order through an injected runner, canonicalizes the observed JSON-shaped
evidence, and reduces runner exceptions to stable failed observations without
leaking exception text into identities. The returned suite, engine evidence,
and conformance report are bound together and preserve the existing rule that
only a complete passing stable release may be authoritative. No Nautilus import,
provider access, or runtime activation is performed by the package harness.

Focused executable-conformance tests passed (9 tests). Compose activation,
stable Nautilus release/conformance against the real engine, upstream contract
reconciliation, and full repository integration remain open.

## 2026-09-17 - Isolated Nautilus release-pin contract

`conformance.py` now exposes `NautilusReleasePin`, binding the exact v2 package
version/tag, source digest, runtime-image digest, Python and Rust versions, and
explicit isolation from the legacy Nautilus runtime. `EngineConformanceEvidence`
retains that pin and `evaluate_engine_conformance()` reports its validity;
complete fixture coverage without a valid isolated pin remains compatible
evidence but cannot be authoritative. Stable labels with prerelease tags,
shared legacy runtimes, missing pins, and engine-version drift fail the
authority gate while release-candidate evidence remains executable but
non-authoritative.

Focused conformance/publication tests passed (23 tests). Compose activation,
stable Nautilus release/conformance against the real engine, upstream contract
reconciliation, and full repository integration remain open.

## 2026-09-17 - Idempotent resource-creation API boundary

`resource_mutations.py` now provides immutable resource-mutation requests,
receipts, and accept/replay/conflict/reject decisions. The registration-neutral
router adds `POST /strategy-lab/v2/{resource}` for mutable resource types with
strict canonical `attributes`, optional relationship identifiers, bounded JSON
payloads, required `Idempotency-Key`, and 202 resource-document responses.
Artifact and metric-set resources remain read-only through this generic route;
the application adapter still owns domain validation, persistence, outbox
staging, and result-publication policy.

Focused resource-mutation/API tests passed (20 tests). Compose activation,
stable Nautilus release/conformance against the real engine, upstream contract
reconciliation, full persistence-backed mutation flows, and full repository
integration remain open.

## 2026-09-17 - Explicit terminal/result completion context

`worker_service.py` now exposes an optional terminal writer that receives an
immutable `WorkerCompletionContext`: the exact Redis entry, the materialized
`WorkerExecutionRequest`, the `WorkerProcessResolution`, and a UTC observation
time. Its typed `WorkerHandleResult` is used as the completion receipt before
the scheduler can acknowledge the stream entry; the legacy two-argument
completion writer remains supported when no terminal writer is configured.
`WorkerServiceCallbacks` and the local entrypoint accept this optional fourth
callback alongside materialization, completion, and lease heartbeat. This is
the explicit seam for binding `materialize_worker_terminal`, result-completion
publication, and atomic capacity release without placing outcome/metric policy
inside Redis transport.

The focused worker-service/entrypoint tests passed (11 tests); branch
validation passed 764 package tests; and the exact backend gate passed 2,413
tests with 83.76% combined coverage (required threshold: 75%). Branch-scoped
Docker resources were cleaned with no retained testcontainer sessions.
Concrete terminal/result adapter implementations, Compose activation, stable
Nautilus conformance, upstream contract reconciliation, and full repository
integration remain deferred.

## 2026-09-17 - Atomic worker lease/capacity settlement

`PostgresWorkerStateAdapter.release_capacity()` now closes the worker-side
release boundary in one locked transaction. It authenticates the profile,
reservation, lease, and release observation identities; applies the ordered
release observation; compare-and-set updates the lease; and releases the
serial reservation before returning. Exact retries replay both the already
released lease and capacity state, while sequence gaps, foreign attempts,
non-release observations, missing rows, and identity drift fail closed without
partial state. This works for both backtest and forward worker profiles and is
available to the entrypoint's injected completion/recovery callbacks.

The focused PostgreSQL worker-state tests passed (7 tests); branch validation
passed 763 package tests; and the exact backend gate passed 2,412 tests with
83.77% combined coverage (required threshold: 75%). Branch-scoped Docker
resources were cleaned with no retained testcontainer sessions. Concrete
terminal/result callback wiring, Compose activation, stable Nautilus
conformance, upstream contract reconciliation, and full repository integration
remain deferred.

## 2026-09-17 - Durable lease-heartbeat integration

`worker_service.py` now accepts an optional durable lease-observation writer.
When enabled, one ordered content-addressed heartbeat is emitted at each
configured interval while the fresh serial process runs; the service advances
only on an `APPLY`/exact replay with the expected sequence and leaves the
stream entry pending if persistence rejects or contradicts a heartbeat. The
entrypoint accepts a two- or three-item callback factory result, passes the
third callback through Redis runtime composition, and exposes namespaced
heartbeat interval/extension configuration. Completion persistence and worker
capacity settlement remain authoritative injected adapters, so a heartbeat
failure cannot be acknowledged as a completed dispatch.

The focused worker-service/entrypoint tests passed (10 tests), package Ruff and
MyPy passed, the branch gate passed 761 package tests, and the exact backend
gate passed 2,410 tests with 83.77% combined coverage (required threshold:
75%). Branch-scoped Docker resources were cleaned with no retained
testcontainer sessions. Forward-capacity settlement integration, Compose
activation, stable Nautilus conformance, upstream contract reconciliation,
and full repository integration remain deferred.

## 2026-09-17 - Explicit local worker entrypoint

`worker_entrypoint.py` now owns the local dedicated-worker lifecycle without
touching FastAPI, the general ARQ worker, Compose, or upstream worktrees. The
validated environment contract selects Redis/PostgreSQL, queue/group/consumer
identity, migration target, artifact root, process limits, and an explicit
callback factory. Startup runs the idempotent Alembic service before opening
Redis; a shared PostgreSQL persistence bundle supplies the durable payload
loader; the Redis runtime composes the bounded scheduler and fresh serial
process service; SIGINT/SIGTERM drive an `asyncio.Event`; and Redis is closed
in `finally`. Callback materialization and completion persistence remain
injected so the entrypoint does not invent engine or result-authority policy.

The focused entrypoint tests cover environment validation, callback loading,
migration fail-closed ordering, runtime closure/signal cleanup, and worker
limit composition. Lease-heartbeat integration, forward-worker reservations,
Compose service activation, stable Nautilus conformance, upstream contract
reconciliation, and full repository integration remain deferred.

## 2026-09-17 - Explicit startup migration service

`migration_startup.py` now provides the application-owned Alembic upgrade
seam. It validates PostgreSQL URLs and absolute script locations, executes the
configured target off the event loop, serializes concurrent callers, replays
the exact in-process result, and exposes only stable exception-type digests on
failure. Importing FastAPI or constructing the v2 router remains side-effect
free; the local deployment entrypoint explicitly decides when to invoke it.

The focused migration tests passed (3 tests), with branch and exact backend
validation recorded below. Dedicated worker service activation, stable
Nautilus release/conformance, upstream contract reconciliation, and full
repository integration remain deferred.

## 2026-09-17 - Dedicated worker service composition

`worker_service.py` now composes the authenticated Redis payload loader,
bounded scheduler, fresh serial worker process, and injected durable
completion writer. Each handoff runs off the event loop, and the transport can
acknowledge an entry only after the writer returns a matching receipt. The
Redis runtime exposes this composition without implicitly starting it; a
concrete process entrypoint, lease-heartbeat integration, and Compose service
activation remain deferred.

The focused worker-service/runtime tests passed (9 tests). The full
Strategy Lab v2 package passed 751 tests with Ruff/MyPy green, and the exact
backend gate passed 2,400 tests with 83.78% combined coverage (required
threshold: 75%); branch-scoped Docker resources were cleaned and no retained
testcontainer sessions remain. Migration startup, worker service activation,
upstream contract reconciliation, stable Nautilus activation, and full
repository integration remain deferred.

## 2026-09-17 - Dedicated serial worker process boundary

`worker_process.py` now provides `SerialWorkerProcessExecutor`, which runs
each immutable execution handoff in a fresh `spawn` child process. A one-way
pipe transfers only the typed request and `WorkerExecutionResolution`; the
parent owns join, timeout, termination, and reaping, and child failures are
reduced to stable exception-type digests. The boundary does not acquire
leases, persist state, or run from FastAPI/the general ARQ worker; a concrete
Redis service entrypoint, lease-heartbeat integration, and Compose activation
remain deferred.

The full Strategy Lab v2 package passed 748 tests with Ruff/MyPy green. The
exact backend gate then passed 2,397 tests with 83.77% combined coverage
(required threshold: 75%); branch-scoped Docker resources were cleaned and no
retained testcontainer sessions remain. Migration startup, worker service
activation, upstream contract reconciliation, stable Nautilus activation,
and full repository integration remain deferred.

## 2026-09-17 - Artifact orphan reconciliation and scheduled cleanup

`LocalArtifactStore.cleanup_uncommitted()` now scans only the store's
sharded content-addressed entries and recognized crash-left publication
temporaries. PostgreSQL commit records are authoritative: digest-verified
uncommitted content and aged temporary files are deleted only after an
explicit minimum-age guard, while committed/fresh/unknown entries remain
untouched. Deletions fsync their shard directory and every result is returned
as deterministic audit evidence.

`LocalArtifactCleanupService` and `ArtifactCleanupScheduler` expose the
application and bounded periodic seams over the same persistence bundle. The
scheduler uses an injected clock/sleep, supports explicit cancellation and a
test cycle cap, and does not start workers or hide cleanup failures.

The full Strategy Lab v2 package passed 744 tests with Ruff/MyPy green. The
exact backend gate then passed 2,393 tests with 83.76% combined coverage
(required threshold: 75%); branch-scoped Docker resources were cleaned and no
retained testcontainer sessions remain. Isolated worker process/runtime
execution, migration startup, upstream contract reconciliation, stable
Nautilus activation, and full repository integration remain deferred.

## 2026-09-17 - Artifact path-integrity regression hardening

`LocalArtifactStore` now rejects broken target symlinks before treating a
content address as missing. The existing fail-closed path and digest checks
therefore cover both live and dangling symlink escapes, with a regression test
at the latest exact branch tip.

The full Strategy Lab v2 package remains at 739 passing tests; the exact
backend gate passed 2,388 tests with 83.75% combined coverage (required
threshold: 75%). Branch-scoped Docker resources were cleaned and no retained
testcontainer sessions remain. Isolated worker process/runtime execution,
migration startup, orphan/scheduled artifact cleanup, upstream contract
reconciliation, and stable Nautilus activation remain deferred.

## 2026-09-17 - Cancellable worker scheduling

`RedisDispatchWorkerScheduler` now runs one bounded Redis worker-pump cycle at
a time until an explicit stop signal or test cycle cap. Interval values are
finite and positive, sleep is injected for deterministic control, and callers
can select the authenticated durable-payload materializer before their
two-argument handler runs. `RedisDispatchRuntime.worker_scheduler()` exposes
the same composition on the application-owned Redis lifecycle; it does not
start a process, claim a lease, invoke Nautilus, or hide handler failures.

The full Strategy Lab v2 package passed 739 tests with Ruff/MyPy green. The
exact backend gate then passed 2,388 tests with 83.75% combined coverage
(required threshold: 75%); branch-scoped Docker resources were cleaned and no
retained testcontainer sessions remain. Isolated worker process/runtime
execution, migration startup, orphan/scheduled artifact cleanup, upstream
contract reconciliation, and stable Nautilus activation remain deferred.

## 2026-09-17 - Retention-authorized artifact byte lifecycle

`artifact_store.py` now exposes a guarded `collect()` operation that verifies
manifest-bound bytes and an authenticated `ArtifactRetentionResolution` before
deleting content. Only `TIER_ELIGIBLE` or `EXPIRE_ELIGIBLE` resolutions may
remove bytes; pinned/permanent/not-yet-eligible content is reported retained,
missing content is idempotent, and digest/path corruption fails closed with a
directory fsync after deletion. `LocalArtifactRetentionService` evaluates the
existing PostgreSQL retention adapter at an explicit instant before collection,
and both the standalone and shared-persistence factories expose this wiring.

Focused artifact/application/persistence tests passed (13 tests), and the full
Strategy Lab v2 package passed 737 tests with Ruff/MyPy green. The exact
backend gate then passed 2,386 tests with 83.75% combined coverage (required
threshold: 75%); branch-scoped Docker resources were cleaned and no retained
testcontainer sessions remain. Orphan discovery, scheduled cleanup, migration
startup, worker process/runtime execution, upstream contract reconciliation,
and stable Nautilus activation remain deferred.

## 2026-09-17 - Durable dispatch-payload materialization

`dispatch_payload.py` now defines immutable canonical payload records with
byte-length and decoded-content authentication. The additive
`ff1a2b3c4d5e` migration creates a content-addressed PostgreSQL payload table;
submission receipt, dispatch intent, payload bytes, and execution outbox are
staged in one transaction, with shared-payload deduplication and tamper
rejection. `PostgresSubmissionDispatchAdapter.load_payload()` is the
worker-facing lookup surface, and `RedisDispatchWorker.handle_materialized_once()`
resolves that record by stream digest before invoking a handler. Missing or
malformed records stay unacknowledged for retry/poison-message policy.

Focused payload/submission/worker/migration tests passed (18 tests), the full
Strategy Lab v2 package passed 734 tests, and Ruff/MyPy were green. The exact
backend gate then passed 2,383 tests with 83.74% combined coverage (required
threshold: 75%); branch-scoped Docker resources were cleaned and no retained
testcontainer sessions remain. Worker process/runtime execution, migration
startup, artifact byte/retention lifecycle, upstream contract reconciliation,
and stable Nautilus activation remain deferred.

## 2026-09-17 - Atomic submission-to-outbox staging

`postgres_submission.py` now binds each accepted API submission to the shared
`strategy_lab_v2_execution_outbox` in the same PostgreSQL transaction as its
owner-scoped receipt and dispatch intent. The outbox request/event identities
are derived from both owner and request content, preventing cross-owner
collisions while preserving idempotent retries. Missing dispatch or outbox rows
are repaired on replay; contradictory durable content fails with a typed
idempotency conflict. The existing Redis relay can therefore observe API
submissions as authoritative pending work.

The full declared branch suite passed 729 Strategy Lab v2 tests plus the
migration structural test, Ruff, MyPy, diff, and workstream validation. The
exact-worktree backend gate passed 2,377 tests with 83.77% combined coverage
(required threshold: 75%), and branch-scoped Docker resources were cleaned
afterward. Worker payload materialization, isolated execution, and stable
Nautilus activation remain deferred.

## 2026-09-17 - Application-owned Redis runtime lifecycle

`redis_application.py` now owns the concrete Redis boundary without leaking a
client dependency into the engine-neutral transport. `RedisDispatchRuntime`
validates explicit `redis://`/`rediss://` URLs, constructs a text-decoding
`redis.asyncio` client, composes outbox-relay and bounded worker-pump factories,
and closes the client idempotently. Connection health checks, process/task
lifecycle, migration startup, and worker execution remain caller-owned.

The full Strategy Lab v2 package passed 729 tests with Ruff and MyPy green. The
exact-worktree backend gate passed 2,377 tests with 83.77% combined coverage
(required threshold: 75%), and branch-scoped Docker resources were cleaned
afterward. Production worker activation and stable Nautilus execution remain
deferred.

## 2026-09-17 - Bounded outbox relay scheduling

`outbox_application.py` now includes `OutboxRelayScheduler`, an application
owned loop that executes bounded relay cycles at an injected clock instant and
stops on an explicit cancellation event. Interval and batch limits are finite
and validated; clock/sleep injection keeps scheduling deterministic in tests,
while the underlying Redis enqueue and PostgreSQL acknowledgement remain
idempotent and authoritative respectively. Redis client construction and
process lifecycle are still caller-owned.

The full Strategy Lab v2 package passed 727 tests with Ruff and MyPy green.
The exact-worktree backend gate passed 2,375 tests with 83.78% combined coverage
(required threshold: 75%), and branch-scoped Docker resources were cleaned
afterward. Production Redis lifecycle, migration startup, worker entrypoints,
isolated execution, and stable Nautilus activation remain deferred.

## 2026-09-17 - Owner-scoped artifact resource projection

`postgres_result_materialization.py` now exposes authenticated artifact
references by narrowly decoding the tagged canonical `output_artifacts` field
from each retained result manifest. The decoder rejects malformed envelopes,
duplicate/missing fields, wrong tags, and non-canonical integers before
rebuilding immutable `ArtifactManifest` values. `persistence.py` projects those
references into deterministic `/artifacts` resources, deduplicating shared
content digests while retaining manifest, attempt, and trial provenance plus
attempt relationships; owner scoping remains inherited from the manifest
adapter.

The focused result-materialization/persistence suite passed 5 tests, the full
Strategy Lab v2 package passed 725 tests, and Ruff/MyPy were green. The exact
worktree backend gate passed 2,373 tests with 83.77% combined coverage (required
threshold: 75%), and branch-scoped Docker resources were cleaned afterward.
Artifact-byte reads, retention/pin projections, migration startup, worker
scheduling, and stable Nautilus execution remain deferred.

## 2026-09-17 - PostgreSQL outbox to Redis relay

`postgres_event_transaction.py` now exposes an authenticated complete-outbox
reader and compare-and-set publication acknowledgement. The new
`outbox_application.py` composes that authoritative persistence surface with
`RedisDispatchTransport`: each bounded relay cycle selects currently available
messages, safely enqueues or replays them by semantic identity, and only then
marks the PostgreSQL row published with its state fingerprint. A crash or lost
acknowledgement leaves the row pending for idempotent retry; Redis remains
transport-only. The shared persistence bundle exposes the relay factory.

The focused outbox/event/persistence tests passed 8 tests; the branch-declared
checks passed 725 Strategy Lab v2 tests plus the migration structural test,
Ruff, MyPy, `git diff --check`, and workstream validation. The exact-worktree
backend gate passed 2,373 tests with 83.80% combined coverage (required
threshold: 75%), and branch-scoped Docker resources were cleaned afterward.
Worker-pump scheduling, production Redis client lifecycle, migration startup,
application activation, isolated workers, and stable Nautilus execution remain
deferred.

## 2026-09-17 - Relational API resource projections

`postgres_resources.py` now supports application-owned projection loaders in
addition to the aggregate store. `persistence.py` registers authenticated
PostgreSQL projections for attempts (latest execution summaries), metric sets,
and forward instances; each is converted into the immutable REST resource
envelope with a canonical revision digest. Projection collections retain
deterministic ordering, duplicate-ID rejection, cursor snapshot binding, and
owner scoping, while strategy/package/portfolio/snapshot/experiment/trial
resources continue through the aggregate projection path. Focused projection,
application, and persistence tests plus the branch and exact coverage gates are
green. Remaining resource projections, migration startup, worker scheduling,
and runtime activation remain deferred.

## 2026-09-17 - Forward-instance collection read surface

`postgres_forward_state.py` now exposes `load_all(principal=...)`, returning
every owner-scoped `ForwardInstance` in stable instance-id order. The query
reuses the checkpoint decoder and authenticates owner, instance, instance
fingerprint, and checkpoint fingerprint for every row before returning it, so
future `/forward-instances` pagination cannot disclose another owner or accept
tampered state. Focused tests cover multiple-instance ordering and owner
isolation; the full branch and exact coverage gates are green. Resource-route
projection, startup migration, worker scheduling, and runtime activation remain
deferred.

## 2026-09-17 - Shared PostgreSQL persistence bundle

`backend/app/strategy_lab_v2/persistence.py` now owns construction of the
complete registration-neutral PostgreSQL v2 adapter graph over one async session
factory. The bundle shares the aggregate store with resource reads and the
execution-state context with command receipts, while exposing acquisition,
coverage, capability, forward/search, runtime/result, artifact, lineage, and
worker-state adapters for subsequent application and worker slices.
`application.py` consumes the bundle for its initial authenticated API seam and
keeps the existing private aliases for compatibility. Artifact publication can
be created from the same graph with an explicit local/NAS-mountable root.
Focused application/persistence tests, Ruff, MyPy, and the complete branch test
collection are green. API projection completion, migration startup, worker
scheduling/activation, and stable Nautilus execution remain deferred.

## 2026-09-17 - Local artifact publication application wiring

`backend/app/strategy_lab_v2/artifact_application.py` now composes the
immutable `LocalArtifactStore` with `PostgresArtifactCommitAdapter`. Publication
verifies the manifest bytes, uses the store's atomic create-if-absent/reuse
behavior, and finalizes the matching commit ledger record with explicit
committed/replayed/rejected evidence. A factory accepts an explicit artifact
root so a later Compose/NAS volume can be selected without a hidden host path.
Focused tests cover first publication, exact replay/deduplication, rejection
before commit, and factory composition. Crash-orphan reconciliation,
retention/pinning coordination, result-completion wiring, worker activation,
and startup configuration remain deferred.

## 2026-09-17 - Initial authenticated API/application wiring

`backend/app/strategy_lab_v2/application.py` now composes the existing
`get_current_user` dependency and `AsyncSessionLocal` with the additive
PostgreSQL resource, submission/dispatch, execution-state, and command
adapters. Integer-backed ORM user IDs are normalized once at the application
boundary to the opaque string owner keys used by the engine-neutral contracts.
`backend/app/main.py` registers the resulting router additively at
`/api/v1/strategy-lab/v2`; the legacy Strategy Lab router remains unchanged.
Focused application tests cover identity normalization, adapter composition,
and the versioned route factory. Remaining resource projections, startup
migration rollout, worker scheduling/activation, and stable Nautilus execution
remain deferred integration gates.

## 2026-09-17 - Additive Strategy Lab v2 schema migration

Alembic revision `ff0a1b2c3d4e_add_strategy_lab_v2_storage.py` now creates the
complete additive schema consumed by the registration-neutral PostgreSQL v2
adapters: aggregate/storage receipts, submissions and dispatch, execution and
audit/outbox state, forward state and replays, runtime/outcome/progress/result
records, search/capability/coverage/acquisition projections, artifact lineage,
retention and commits, legacy imports, and worker profiles/reservations/leases.
It also creates the partial unique index that enforces one active reservation
per worker/attempt. Offline Alembic rendering, migration graph, Python compile,
and Ruff validation are green; legacy Strategy Lab tables are untouched.
Application startup migration execution, authentication, route registration,
worker activation, and stable Nautilus execution remain deferred.

## 2026-09-17 - Restricted strategy invocation runner

The new owned `backend/strategy_runtime/` package executes one strategy event
inside the already-hardened worker boundary. It verifies the source digest
against the immutable SDK manifest, repeats static source preflight, executes
with a restricted builtin/import surface, injects only engine-neutral SDK
symbols, and validates emitted intents against declared instrument scope and
per-event limits. Source/entrypoint/output failures return typed,
content-addressed evidence without exposing exception text. Four focused tests
cover success, digest/static rejection, typed failures, and import restriction;
the full package suite now passes 627 tests with Ruff and MyPy. Docker image,
worker entrypoint, and application wiring remain deferred shared integration
gates.

## 2026-09-17 - Strategy runtime wire protocol and CLI

`backend/strategy_runtime/protocol.py` now defines a canonical, versioned JSON
envelope for mounted invocation requests and typed results. It preserves
Decimal/datetime/date/float and collection values, reconstructs the immutable
engine-neutral SDK records, encodes only typed order/target-position intents,
and verifies the result content fingerprint on decode. The package CLI
(`python -m strategy_runtime --request <absolute-path> --result <absolute-path>`)
invokes one event in the already-isolated process, atomically publishes the
result file, returns `0` for success, `2` for typed rejection/failure, and `1`
for malformed input or output setup without printing strategy exception text.
The focused runtime/protocol suite passes 9 tests; worker image wiring,
container activation, and application scheduling remain deferred shared gates.

## 2026-09-17 - Stateful strategy runtime session checkpoint

`StrategyInvocationSession` now loads one source-bound strategy instance for an
entire worker lifetime instead of rebuilding the strategy for every event. It
revalidates manifest scope for direct typed contexts, preserves state across
monotonically advancing events, pins random-seed and parameter identity, and
turns context drift or a terminal strategy error into deterministic typed
evidence. The existing one-event API remains a compatibility wrapper over a
fresh session, while the mounted CLI continues to execute one request/event.

The complete Strategy Lab v2 package passed 655 tests with Ruff, MyPy,
`git diff --check`, and workstream validation green. The Docker-backed combined
coverage gate passed 2,302 tests with 83.61% total coverage (required threshold:
75%); setup and cleanup completed successfully. Worker image/entrypoint,
application scheduling, and authoritative Nautilus execution remain deferred.

## 2026-09-17 - Deterministic frozen-tape replay checkpoint

`backend/app/strategy_lab_v2/replay.py` now builds one typed SDK context for
each same-time batch in a bound frozen tape. Histories are truncated to each
dependency's declared lookback, optional position snapshots are keyed to batch
sequences, and the replay adapter invokes one stateful strategy session in
chronological order. Snapshot/manifest binding is repeated at the execution
boundary; tape, binding, source, parameters, and typed invocation outcomes are
retained as content-addressed provenance. Replays stop at the first typed
rejection or failure and never apply intents or model fills.

The exact Strategy Lab package gate passes 659 tests with Ruff, MyPy,
`git diff --check`, and workstream validation green. The combined Docker-backed
coverage gate is the remaining validation step for this checkpoint; worker
image/entrypoint, application scheduling, migrations, upstream reconciliation,
and authoritative Nautilus execution remain deferred.

## 2026-09-17 - Stateful batch runtime wire checkpoint

The runtime now exposes `run_strategy_events()` as a reusable primitive that
creates one `StrategyInvocationSession`, invokes a non-empty context sequence,
and stops at the first typed rejection or failure. The versioned protocol adds
strict batch request and result envelopes with typed context reconstruction,
per-invocation fingerprints, duplicate/non-finite JSON rejection, and an
independently verified batch fingerprint. This lets a future isolated worker
retain strategy state over a frozen replay while preserving the existing
single-event CLI contract.

The exact Strategy Lab package gate passes 661 tests with Ruff, MyPy,
`git diff --check`, and workstream validation green. The combined Docker-backed
coverage gate remains the repository-level validation step for this checkpoint;
worker image/entrypoint, application scheduling, migrations, upstream
reconciliation, and authoritative Nautilus execution remain deferred.

## 2026-09-17 - Stateful batch runtime CLI checkpoint

`python -m strategy_runtime` now detects the strict batch request envelope while
retaining the existing single-event path. Batch requests are reconstructed into
typed contexts, executed through one `StrategyInvocationSession`, and published
atomically as a fingerprinted batch-result envelope. A non-successful typed
invocation returns exit status 2; malformed input or output setup remains exit
status 1, and no strategy exception text crosses the process boundary.

The focused CLI/protocol tests pass, with the complete branch gate and
Docker-backed combined coverage gate recorded below after this exact-tip
checkpoint. Worker image/entrypoint, application scheduling, migrations,
upstream reconciliation, and authoritative Nautilus execution remain deferred.

## 2026-09-17 - Manifest-bound runtime result provenance

`StrategyInvocationResult` now carries the SDK manifest fingerprint used during
source loading, context admission, and intent validation. The single and batch
JSON result envelopes preserve and validate this identity, so a host adapter can
bind returned intents to the exact immutable strategy contract rather than
trusting source/context digests alone. Existing single-event and batch callers
remain compatible through the updated typed protocol constructors.

The full Strategy Lab package gate passes 665 tests with Ruff, MyPy,
`git diff --check`, and workstream validation green. The Docker-backed combined
coverage gate passes 2,312 tests with 83.62% total coverage (required threshold:
75%); setup and cleanup completed successfully. Worker image/entrypoint,
application scheduling, migrations, upstream reconciliation, and authoritative
Nautilus execution remain deferred.

## 2026-09-17 - Typed strategy-validation request metadata errors

The registration-neutral strategy-validation route now catches malformed or
overlong `X-Request-ID` values and returns the same typed validation envelope
used by the other v2 routes. Invalid request metadata therefore cannot escape
before raw-body validation and static source preflight, while valid request IDs
and existing 422 body errors remain unchanged.

The focused API-router suite passes 13 tests and the complete Strategy Lab v2
package passes 693 tests with Ruff and MyPy green. The exact-worktree combined
coverage gate passes 2,340 tests with 83.71% total coverage (required
threshold: 75%); Docker services were branch-scoped and cleaned afterward.
Authentication, application registration, and shared persistence remain
deferred behind the existing gates.

## 2026-09-17 - Bounded strategy-runtime wire payloads

The restricted runtime protocol now rejects inbound single, batch, and result
envelopes larger than 16 MiB before JSON decoding. This bounds mounted request
parsing independently of the sandbox's memory and output limits while leaving
valid typed envelopes and the existing atomic CLI publication behavior intact.

The focused runtime protocol suite passes 12 tests and the complete Strategy
Lab v2 package passes 694 tests. The exact-worktree combined coverage gate
passes 2,341 tests with 83.71% total coverage (required threshold: 75%); Docker
services were branch-scoped and cleaned afterward. Worker image activation,
application wiring, and stable Nautilus execution remain deferred.

## 2026-09-17 - Attempt and lease temporal identities

`RunAttempt` creation/transition timestamps and `ExecutionAttemptLease`
acquisition, heartbeat, expiry, and release timestamps now normalize aware
offsets to UTC during immutable construction. Retry lineage and worker-capacity
comparisons therefore remain stable across offset-changing persistence or
transport boundaries. Attempt/lease regression coverage is green and the
complete Strategy Lab v2 package passes 712 tests; persistence migration,
worker activation, application wiring, and stable Nautilus execution remain
deferred.

## 2026-09-17 - Bounded mounted runtime request reads

Both mounted strategy and custom-metric CLIs now read request files through a
bounded binary reader, consuming at most the 16 MiB wire limit plus one byte
before strict UTF-8 decoding. Oversized files therefore fail before an
unbounded `read_text()` allocation can bypass the protocol decoder guard, while
valid single and batch requests retain their existing atomic result publication.
Regression coverage verifies that neither CLI publishes a result for an
oversized request. The focused runtime/custom-metric protocol suite passes 23
tests, and the complete Strategy Lab v2 package passes 696 tests; worker image
activation, application wiring, and stable Nautilus execution remain deferred.

## 2026-09-17 - Deterministic sandbox start-failure evidence

Sandbox process-start failures now publish a versioned digest of the fully
qualified exception type instead of hashing the OS error string. Host-specific
paths and launcher details therefore cannot create divergent run identities or
leak through evidence, while timeout and output-limit evidence remains unchanged.
Regression coverage confirms two different missing launch paths produce the same
typed start-failure digest. The package and exact-worktree coverage gates remain
green; worker activation, application wiring, and stable Nautilus execution
remain deferred.

## 2026-09-17 - Forward observation admission integrity

Forward live admission now validates the shape of every event observation and
recomputes its expected disposition from the persisted cursor before applying
state. Forged accepted observations cannot skip sequence gaps, non-accepted
observations cannot move the cursor, and missing bounds/buffering/replay flags
are checked against their disposition. Buffered event IDs are content-bound on
first receipt, so a changed retry conflicts instead of replacing the buffered
event. Focused forward admission/transaction/dispatch/correction tests pass 27
tests and the complete package gate passes 698 tests; persistence, canonical
event-stream wiring, worker activation, and stable Nautilus execution remain
deferred.

## 2026-09-17 - Bounded runtime wire serialization

The canonical strategy and custom-metric protocol serializers now enforce the
same 16 MiB UTF-8 byte limit used by inbound decoders for single and batch
request/result envelopes. Oversized generated payloads fail before a mounted
artifact is emitted, while canonical ordering and typed fingerprints remain
unchanged. Focused runtime protocol coverage passes 23 tests and the complete
Strategy Lab v2 package passes 700 tests; worker activation, application
wiring, and stable Nautilus execution remain deferred.

## 2026-09-17 - Canonical forward event-time identities

`CanonicalForwardEvent` and `ForwardCursor` now normalize every aware
`event_time`, `arrived_at`, and cursor timestamp to UTC during construction.
Offset-equivalent canonical events therefore compare and fingerprint
identically, preventing false content conflicts and replay divergence at the
forward boundary. Focused forward lifecycle/admission coverage passes 28 tests
and the complete Strategy Lab v2 package passes 701 tests; persistence migration,
event-stream wiring, worker activation, and stable Nautilus execution remain
deferred.

## 2026-09-17 - Forward lifecycle temporal identities

Forward instance `created_at`/`updated_at`, warm-up receipt `completed_at`,
correction command `requested_at`, and counterfactual replay-plan `planned_at`
now normalize aware offsets to UTC during immutable construction. Restart,
warm-up, and correction records therefore retain one identity for equivalent
instants regardless of transport offset formatting. Regression coverage adds
three identity tests; the complete Strategy Lab v2 package passes 704 tests.
Persistence migration, event-stream wiring, worker activation, and stable
Nautilus execution remain deferred.

## 2026-09-17 - Execution lifecycle temporal identities

Asynchronous submission and admission receipts, strategy-runtime requests and
updates, execution outcomes and progress, retry/cancellation commands,
authorization records, and execution-summary projections now normalize aware
timestamps to UTC during immutable construction. Equivalent instants therefore
retain one retry and read-model identity through the complete local execution
handoff. Focused lifecycle coverage passes 50 tests and the complete Strategy
Lab v2 package passes 711 tests; persistence migration, worker activation,
application wiring, and stable Nautilus execution remain deferred.

## 2026-09-17 - Runtime wire source-binding hardening

Single and batch invocation serializers and decoders now verify that the source
bytes match the SDK manifest's declared source digest. Contradictory envelopes
are rejected at the wire boundary, before a mounted bundle or strategy session
can be created. Regression coverage includes both serializer-side mismatch and
tampered single/batch payloads.

The full Strategy Lab package gate passes 665 tests with Ruff, MyPy,
`git diff --check`, and workstream validation green. The Docker-backed combined
coverage gate passes 2,312 tests with 83.62% total coverage (required threshold:
75%); setup and cleanup completed successfully. Worker image/entrypoint,
application scheduling, migrations, upstream reconciliation, and authoritative
Nautilus execution remain deferred.

## 2026-09-17 - Deterministic runtime identity hardening

The strategy runtime wire protocol now normalizes every timezone-aware
timestamp to UTC before serialization and after decoding. Equivalent instants
therefore produce byte-identical single and batch envelopes even when callers
use different source offsets. Failure evidence is now bound to a versioned,
fully-qualified exception type only; private exception text, strategy data, and
process-specific object representations cannot change the published digest.

The focused runtime/protocol tests pass, with the complete branch gate and
Docker-backed combined coverage gate recorded below after this exact-tip
checkpoint. Worker image/entrypoint, application scheduling, migrations,
upstream reconciliation, and authoritative Nautilus execution remain deferred.

## 2026-09-17 - Strict strategy-runtime batch chronology

Batch invocation envelopes and the direct `run_strategy_events()` primitive now
preflight strict `(event_time, event_sequence)` ordering before a strategy
session can execute. Duplicate or out-of-order contexts therefore fail as a
typed malformed batch at the serializer/decoder or direct-call boundary instead
of partially invoking a stateful strategy and returning a late monotonic
rejection. The existing single-event API and valid chronological batches are
unchanged.

The focused runtime/protocol suite passes 18 tests and the complete Strategy
Lab v2 package passes 692 tests with Ruff and MyPy green. The Docker-backed
combined coverage gate passes 2,339 tests with 83.71% total coverage (required
threshold: 75%) when run directly from this exact worktree; the first Makefile
wrapper attempt incorrectly collected the provider-platform checkout and is
recorded as a non-authoritative cross-worktree failure. Worker image/entrypoint,
application scheduling, migrations, upstream reconciliation, and authoritative
Nautilus execution remain deferred.

## 2026-09-17 - Replay-safe wall-clock preflight hardening

Static strategy validation now rejects wall-clock method references at the
attribute-access site as well as direct calls. This closes the aliasing escape
where a strategy could bind `datetime.now`/`date.today`/`utcnow` first and call
the alias later, preserving deterministic replay requirements. A regression
test covers the aliased method form; the exact package suite passes 633 tests,
with Ruff, MyPy, branch checks, and Docker-backed combined coverage also green.

## 2026-09-17 - Canonical runtime JSON integrity hardening

Runtime envelope decoding now rejects duplicate JSON object fields and
non-standard `NaN`/`Infinity` constants before any manifest, context, or result
record is reconstructed. This keeps serialized identities unambiguous and
preserves the finite-number guarantees of the engine-neutral SDK. Five focused
protocol tests cover canonical round trips, fingerprint tampering, unknown
fields/versions, duplicate fields, and non-finite constants; the exact package
suite remains green at 633 tests and the Docker-backed gate remains green at
2,280 tests with 83.54% coverage.

## 2026-09-17 - Module-introspection preflight hardening

The restricted source preflight now rejects module-introspection attributes
such as `sys`, `modules`, `environ`, and `builtins`, along with private
attributes generally. This closes the public-attribute escape exposed by
allowed modules such as `typing` (`typing.sys`) while preserving the intended
engine-neutral SDK surface. A regression test covers the allowed-module case;
the exact package suite passes 634 tests and the Docker-backed gate passes
2,281 tests with 83.54% coverage.

## 2026-09-17 - Private import-form hardening

Import validation now applies the same private/introspection policy to every
syntax form: dotted imports, `from ... import ...`, aliases, and star imports.
This prevents allowed-module private bindings such as `from collections import
_sys` (or direct `sys` bindings from an allowed module) from bypassing the
attribute checks. The exact package suite passes 635 tests; the Docker-backed
gate passes 2,282 tests with 83.55% coverage.

## 2026-09-17 - Engine-neutral SDK boundary hardening

`sdk.py` now validates public input types before dereferencing them: manifests
must contain typed strategy/dependency records, market events and context maps
are immutable typed mappings, positions require finite Decimal values, and order
intents require the declared enum types. The context builder repeats event
shape checks before applying dependency lookback/field rules, preventing
malformed values from crossing into strategy code. Eight focused malformed-input
assertions were added; the package suite passes 623 tests with Ruff and MyPy.
This remains package-only and does not alter the shared runtime, router,
migration, worker, provider, ETF, TC2000, Compose, or Nautilus paths.

## 2026-09-17 - Paired-inference scope reconciliation

The durable plan and documentation now distinguish the implemented bounded
exact paired sign-flip inference from intentionally out-of-scope
approximate/bootstrap inference and inferential ranking. The canonical feature
ref `origin/feat/strategy-lab-v2` is synchronized at the session checkpoint;
an accidental duplicate hyphenated remote ref was removed. No shared provider,
ETF, TC2000, migration, router, worker, Compose, or Nautilus path was changed.

## 2026-09-17 - Trusted paired-inference checkpoint

`paired_inference.py` now provides a bounded, deterministic exact two-sided
sign-flip test for the mean of aligned metric deltas. It requires the existing
verified keyed-stream pairing receipt, sorts and content-addresses observation
keys, records the exact tail/permutation counts and statistical assumptions,
and exposes a versioned `calculate_paired_inference_metrics()` projection.
Requests above the configured 20-observation exact-enumeration bound return
typed unavailable evidence rather than silently using an approximate or
unseeded method. This is statistical evidence only and does not issue a
profitability verdict; migrations, API wiring, workers, and stable Nautilus
execution remain separate gates.

The focused inference suite passes 4 tests; the full package suite passes 622
tests with Ruff and MyPy. Combined coverage is 2,269 backend tests at 83.51%,
and all five exact-tip branch checks pass.

## 2026-09-17 - Durable metric-set checkpoint

`postgres_metrics.py` now retains immutable `MetricSet` summaries as
owner-scoped canonical projections. Full metric-set payloads and compact value
summaries are content-addressed; one attempt cannot silently replace a prior
metric set, exact retries replay, and payload/record tampering is detected
before metric data can be read by later result/API adapters. Metric calculation,
artifact bytes, migrations, authorization, and application wiring remain
separate integration gates.

The focused metric persistence suite passes 3 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable runtime-receipts checkpoint

`postgres_runtime_receipts.py` now retains immutable strategy-runtime request
and isolation-preflight evidence as owner-scoped canonical projections. Request
and preflight payloads carry independent content-addressed identities; exact
retries replay, changed content conflicts against the same attempt/request, and
rejected preflight reasons remain inspectable without exposing secrets or
starting a process. The adapter is registration-neutral and does not mutate
runtime execution state; process execution, migrations, authorization, and
application wiring remain open gates.

The focused runtime-receipts suite passes 4 tests. Package/static and combined
coverage evidence will be recorded after this boundary is committed and rerun;
upstream reconciliation and stable Nautilus execution remain open gates.

## 2026-09-17 - Durable result-manifest checkpoint

`postgres_result_materialization.py` now retains immutable `RunResultManifest`
values as owner-scoped canonical JSON projections. Pure manifest validation is
run before registration; one attempt binds to one manifest identity, exact
retries replay, changed candidates conflict, and payload plus record
fingerprints are authenticated on every read. The adapter exposes the compact
identity projection for later API reads without attempting nested contract
decoding, and does not write artifact bytes or publish official results.

The focused result-manifest persistence suite passes 4 tests; the exact package
suite passes 611 tests with Ruff and MyPy, all 5 branch-declared checks pass,
and the Docker-backed combined gate passes 2,258 backend tests at 83.44%
coverage. Upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable runtime-execution checkpoint

`postgres_runtime_execution.py` now maps accepted `RuntimeExecutionState`
values and immutable `RuntimeExecutionUpdate` receipts to owner-scoped additive
PostgreSQL tables. Initialization is idempotent, every update is resolved by
the pure monotonic runtime contract and committed with a compare-and-set state
write, and exact sequence/fingerprint retries replay while conflicting content
is rejected. Sandbox result materialization verifies request/plan evidence and
commits running plus terminal receipts atomically, preserving bounded output or
typed failure identity for restart recovery. Process execution, artifact bytes,
migrations, authorization, and official result publication remain separate
integration gates.

The focused runtime persistence suite passes 5 tests in addition to the
existing runtime contract coverage; its exact package suite passed 607 tests,
all 5 branch-declared checks passed, and the Docker-backed combined gate passed
2,254 backend tests at 83.42% coverage. Upstream reconciliation and stable
Nautilus execution remain open gates.

## 2026-09-17 - Durable result-publication checkpoint

`postgres_result_publication.py` now maps immutable publish/replay/reject
`ResultPublicationPlan` values to an owner-scoped additive PostgreSQL evidence
table. Plan fingerprints, attempt/result/reproduction/build identities, and
deterministic rejection reasons are authenticated on reads; exact retries
replay while changed decisions remain separate immutable audit evidence. The
adapter does not publish bytes, coordinate completion, apply migrations, or
register authorization and routes.

The focused result-publication-adapter suite passes 4 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable result-completion checkpoint

`postgres_result_completion.py` now maps terminal result completion and the
shared content-addressed artifact commit ledger to one additive PostgreSQL
transaction. It locks and authenticates both ledgers, delegates terminal
runtime/outcome/progress/publication and artifact-plan validation to
`finalize_execution_result()`, then inserts all new artifact commits and the
owner-scoped completion receipt atomically. Exact retries replay the stored
completion; artifact conflicts or rejected terminal evidence leave both ledgers
unchanged. Artifact bytes, migrations, authorization, and worker/application
wiring remain outside this registration-neutral adapter.

The focused result-completion-adapter suite passes 4 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable execution-summary checkpoint

`postgres_execution_summary.py` now maps immutable `ExecutionSummary`
projections to an owner-scoped additive PostgreSQL read model. Each
submission/attempt outcome-progress state identity is append-only and
fingerprint-authenticated; exact retries replay, changed content for an
existing checkpoint conflicts, and latest-attempt reads retain deterministic
history without overwriting prior status. Error payloads and timezone-aware
timestamps are encoded and revalidated on every read. Submission/outcome
state wiring, result publication, migrations, authorization, API registration,
and worker integration remain outside this adapter.

The focused execution-summary-adapter suite passes 4 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable snapshot-coverage checkpoint

`postgres_snapshot_coverage.py` now maps snapshot-level verified/rejected
coverage resolutions to an owner-scoped additive PostgreSQL table. Per-series
reports, missing/unexpected series digests, rejection reasons, and the complete
resolution fingerprint are authenticated on reads; exact retries replay while
changed resolutions conflict. Provider fetch/repair, attestation lookup,
snapshot creation, execution admission, shared migrations, authorization, and
application wiring remain outside this adapter.

The focused snapshot-coverage-adapter suite passed 4 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable acquisition-receipt checkpoint

`postgres_acquisition.py` now maps provider-produced acquisition receipts to an
owner-scoped additive PostgreSQL handoff registry keyed by the preflight request
identity. Snapshot, provider-snapshot, coverage-resolution, and opaque provider
receipt digests are authenticated before reuse; exact retries replay while
changed handoffs conflict. Provider fetching/repair, snapshot creation,
execution admission, shared migrations, authorization, and application wiring
remain outside this adapter.

The focused acquisition-adapter suite passed 4 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable capability-summary checkpoint

`postgres_capability.py` now maps immutable data/engine capability summaries to
an owner-scoped additive PostgreSQL read model keyed by report and binding
identity. Gaps, degradations, executable/ranking flags, and authoritative
publication eligibility are serialized and re-authenticated; exact retries
replay while a changed projection for the same preflight identities conflicts.
Capability calculation, provider entitlements, engine registration, shared
migrations, authorization, and API wiring remain outside this adapter.

The focused capability-adapter suite passed 4 tests. Package/static and
combined coverage evidence will be recorded after this boundary is committed
and rerun; upstream reconciliation and stable Nautilus execution remain open
gates.

## 2026-09-17 - Durable coverage-attestation checkpoint

`postgres_coverage.py` now maps provider-supplied coverage attestations to an
owner-scoped additive PostgreSQL evidence registry. Series/evidence digests,
interval, row-count, adjustment/session/feed semantics, and attestation
fingerprints are authenticated on reads; exact registration retries replay,
changed series content conflicts, and deterministic owner listings support the
later snapshot-coverage admission flow. Provider fetching/repair, snapshot
admission, shared migrations, authorization, and application wiring remain
outside this registration-neutral adapter.

The focused coverage-adapter suite passed 4 tests. The complete Strategy Lab v2
package and combined coverage gate will be recorded after this boundary is
committed and rerun; shared migrations, API/worker wiring, upstream
reconciliation, and stable Nautilus execution remain open gates.

## 2026-09-17 - Durable legacy-import checkpoint

`postgres_legacy.py` now maps digest-only legacy import records and their exact
compatibility assessments to an owner-scoped additive PostgreSQL registry.
Original metadata, mapping evidence, and record fingerprints are authenticated
on every read. Supported and unsupported imports are both preserved; exact
retries replay, changed payload or mapping content returns an explicit conflict,
and the adapter never reads legacy payload bytes or claims replay equivalence.

The focused legacy-adapter suite passed 4 tests. The complete Strategy Lab v2
package passed 574 tests with Ruff, MyPy, and `git diff --check` clean. Shared
migrations, authorization, API/worker wiring, upstream reconciliation, and
stable Nautilus execution remain open gates.

## 2026-09-17 - Durable forward-state checkpoint

`postgres_forward_state.py` now maps owner-scoped forward instances, immutable
checkpoint event-id sets, one-time historical warm-up receipts, and
content-addressed seen-event identities to additive PostgreSQL tables. Lifecycle
transitions, warm-up activation, and live-event admission lock state and use
authenticated compare-and-set updates. Exact retries replay; duplicate, gap,
out-of-order, and correction observations remain represented in restart-safe
checkpoint state. The adapter is registration-neutral: it does not consume
providers, submit broker orders, start workers, apply migrations, or register
application routes.

The same adapter now exposes an atomic event-transaction path that stores a
correction's counterfactual replay plan beside the admitted event checkpoint.
Correction retries return the original replay identity and cannot leave a live
correction admitted without replay evidence.

The focused forward-state adapter suite passed 4 tests. The complete
Strategy Lab v2 package passed 565 tests with Ruff, MyPy, and `git diff --check`
clean. All five declared branch checks passed, and the Docker-backed combined
gate passed 2,213 tests with 83.24% total coverage (required threshold: 75%),
with setup and cleanup successful. Cross-record cursor/checkpoint integrity was
also revalidated after the initial adapter checkpoint. Schema migration,
event-stream/worker
wiring, application authorization, upstream reconciliation, and stable Nautilus
execution remain open shared-path gates.

## 2026-09-17 - Durable search-state checkpoint

`postgres_search_state.py` now maps immutable experiment queues and candidate
checkpoints to additive PostgreSQL tables. Candidate starts/retries, terminal
receipts, and cancellation requests delegate to the pure search state machine,
then update candidate and experiment fingerprints through one owner-scoped
compare-and-set transaction. Exact retries replay, while missing, foreign,
malformed, or tampered candidate rows fail closed; dispatch transport, worker
execution, migrations, and application wiring remain outside this adapter.

The focused search-state adapter suite passed 4 tests. The complete Strategy
Lab v2 package passed 570 tests with Ruff, MyPy, and `git diff --check` clean.
All five declared branch checks passed, and the Docker-backed combined gate
passed 2,217 tests with 83.26% total coverage (required threshold: 75%), with
setup and cleanup successful. Shared migrations, API/worker integration,
upstream reconciliation, and stable Nautilus execution remain open gates.

## 2026-09-17 - Durable artifact-lineage checkpoint

`postgres_lineage.py` now maps owner-scoped immutable artifact-lineage edges to
an additive PostgreSQL table. Semantic keys provide exact replay and changed
edge conflicts; rows are locked, fingerprint-authenticated, and ordered
deterministically before the pure lineage index is returned. The adapter does
not certify manifest existence, create foreign-key migrations, authorize
owners, or publish artifact bytes.

The focused lineage-adapter suite passed 4 tests. The complete Strategy Lab v2
package passed 561 tests with Ruff, MyPy, and `git diff --check` clean. All five
declared branch checks passed, and the Docker-backed combined gate passed 2,208
tests with 83.22% total coverage (required threshold: 75%), with setup and
cleanup successful. Schema migrations, application wiring, worker entrypoints,
Compose integration, upstream reconciliation, and stable Nautilus execution
remain open shared-path gates.

## 2026-09-17 - Durable artifact-commit checkpoint

`postgres_artifact_commit.py` now maps immutable artifact-publication commit
records to an additive PostgreSQL ledger. It locks and authenticates the
complete commit set, preserves create-if-absent and exact-replay semantics,
and protects storage-key uniqueness so a different manifest cannot reuse an
immutable address. The adapter only stages commit evidence; artifact-byte
publication, manifest validation, retention policy, migration application, and
application wiring remain outside this package-local boundary.

The focused artifact-commit suite passed 4 tests. The complete Strategy Lab v2
package passed 557 tests with Ruff, MyPy, and `git diff --check` clean. All
five declared branch checks passed, and the Docker-backed combined gate passed
2,204 tests with 83.20% total coverage (required threshold: 75%), with setup
and cleanup successful. Schema migrations, application wiring, worker
entrypoints, Compose integration, upstream reconciliation, and stable Nautilus
execution remain open shared-path gates.

## 2026-09-17 - Durable artifact-retention checkpoint

`postgres_artifact_retention.py` now maps manifest-bound retention state and
owner-scoped immutable pins to additive PostgreSQL rows. Initial state and pin
rows are authenticated by canonical fingerprints; pin add/release updates the
pin and state identity atomically with compare-and-set, and exact retries
replay without rewriting immutable bytes. Retention eligibility is resolved at
an explicit observation instant, preserving pinned, tiered, ephemeral, and
permanent decisions without a wall clock or deletion side effect. Malformed,
foreign, tampered, and uniqueness-racing rows fail closed; migration
application, authorization, artifact storage lifecycle, and runtime wiring
remain shared gates.

The focused retention-adapter suite passed 4 tests. The complete Strategy Lab
v2 package passed 553 tests with Ruff, MyPy, and `git diff --check` clean. All
five declared branch checks passed, and the Docker-backed combined gate passed
2,200 tests with 83.18% total coverage (required threshold: 75%), with setup
and cleanup successful. Schema migrations, application wiring, worker
entrypoints, Compose integration, upstream reconciliation, and stable Nautilus
execution remain open shared-path gates.

## 2026-09-17 - Durable worker and lease state checkpoint

`postgres_worker_state.py` now maps immutable worker profiles, serial
reservation capacity, execution-attempt leases, and ordered heartbeat/release
observations to additive PostgreSQL schema statements. Profile, reservation,
lease, and observation bytes are re-authenticated by canonical fingerprints;
active worker/attempt uniqueness is guarded by a partial unique index; release
and lease-observation updates use compare-and-set inside one async transaction.
Exact retries replay, while saturation, gaps, stale sequences, identity drift,
tampering, and uniqueness races fail closed. No process scheduling, engine
disposal, queue publication, migration application, or shared runtime wiring is
performed by this package-local adapter.

The focused worker-state suite passed 5 tests. The complete Strategy Lab v2
package passed 549 tests with Ruff, MyPy, and `git diff --check` clean. All five
declared branch checks passed, and the Docker-backed combined gate passed 2,196
tests with 83.16% total coverage (required threshold: 75%), with setup and
cleanup successful. Schema migrations, application wiring, worker entrypoints,
Compose integration, upstream reconciliation, and stable Nautilus execution
remain open shared-path gates.

## 2026-09-17 - Durable execution-state checkpoint

`postgres_execution_state.py` now maps owner-scoped execution outcomes and
progress checkpoints to additive PostgreSQL rows. It locks both records for an
attempt, validates their shared identity and stored fingerprints, preserves
monotonic outcome transitions, retains every applied progress-update digest
for restart-safe replay, and applies combined outcome/progress/cancellation
observations atomically. `read_context` returns the authenticated pair needed
by the command adapter. Partial/tampered state, gaps, illegal transitions,
cross-owner reads, and compare-and-set races fail closed; no queue, worker, or
broker effect is performed.

The focused state-adapter suite passed 4 tests; the full Strategy Lab v2
package passed 544 tests with Ruff, MyPy, and `git diff --check` clean. All
five declared branch checks passed. The Docker-backed combined gate passed
2,191 tests with 83.12% total coverage (required threshold: 75%), with setup
and cleanup successful.

## 2026-09-16 - Atomic execution-event transaction staging checkpoint

`postgres_event_transaction.py` now maps the canonical execution-event,
append-only audit, transactional-outbox, and stream-cursor contracts to one
SQLAlchemy async transaction. It locks the attempt stream, re-authenticates
stored event/audit/outbox/cursor fingerprints, enforces contiguous sequence
and cursor identity, persists all linked rows atomically, and supports exact
replay plus an optional caller cursor compare-and-set witness. Malformed state,
sequence gaps, stale cursors, and uniqueness races fail closed; Redis
publication and worker effects remain outside this adapter. The explicit DDL
is additive and registration-neutral, so migrations and application wiring
remain gated behind upstream reconciliation.

The focused adapter suite passed 4 tests; the full Strategy Lab v2 package
passed 540 tests with Ruff, MyPy, and `git diff --check` clean. All five
declared branch checks passed. The Docker-backed combined gate passed 2,187
tests with 83.13% total coverage (required threshold: 75%), with setup and
cleanup successful.

## 2026-09-16 - Durable command-receipt staging checkpoint

`postgres_commands.py` now maps retry/cancellation intents to an owner-scoped
PostgreSQL command ledger. The adapter locks the attempt ledger inside one
transaction, resolves the latest injected outcome/progress context through the
engine-neutral command state machine, persists accepted receipts, replays exact
idempotent requests without writes, and returns typed conflict/precondition/not-
found errors. Receipt fingerprints are stored and revalidated so tampered rows
fail closed. The adapter deliberately performs no worker cancellation/retry
effect; schema migration, application wiring, Redis/outbox dispatch, and worker
integration remain gated.

The focused command-adapter suite passed 5 tests; the full Strategy Lab v2
package passed 536 tests with Ruff, MyPy, and `git diff --check` clean. All
five declared branch checks passed. The Docker-backed combined gate passed
2,183 tests with 83.12% total coverage (required threshold: 75%), with setup
and cleanup successful.

## 2026-09-16 - Durable submission/dispatch staging checkpoint

`postgres_submission.py` now maps owner-scoped idempotent submission receipts
and dispatch intents to one async PostgreSQL transaction. It authenticates
canonical payload digests, revalidates stored request/dispatch fingerprints,
replays exact retries without writes, repairs a missing dispatch from an
existing receipt, isolates principals by owner key, and returns typed API
conflicts for content drift. The adapter only stages a durable dispatch intent;
Redis publication, worker effects, migrations, application wiring, and route
registration remain outside this package-owned slice. The API router now passes
the generated request ID into submission and command adapters for error lineage.

The focused submission adapter suite passed 5 tests; the full Strategy Lab v2
package passed 531 tests with Ruff, MyPy, and `git diff --check` clean. All five
declared branch checks passed. The Docker-backed combined gate passed 2,178
tests with 83.09% total coverage (required threshold: 75%), with setup and
cleanup successful. Shared migrations/application wiring, worker entrypoints,
Compose, upstream reconciliation, and stable Nautilus execution remain open.

## 2026-09-16 - Persisted revision-bound resource identity checkpoint

Resource projection now derives a missing API `revision_digest` from the
authenticated aggregate state fingerprint. Every projected document therefore
identifies the exact canonical persisted state, while explicitly supplied
revision digests remain format-validated. This is still a read-only,
registration-neutral adapter; no migrations, model registration, auth wiring,
worker dispatch, or shared provider paths were changed.

Focused route/read validation passed 13 tests, the full Strategy Lab v2 package
passed 526 tests, and Ruff, MyPy, and `git diff --check` were clean. All five
declared branch checks passed. The Docker-backed combined gate passed 2,173
tests with 83.06% total coverage (required threshold: 75%), with setup and
cleanup successful. Durable submission/command adapters, schema migrations,
application wiring, worker entrypoints, Compose, upstream reconciliation, and
stable Nautilus execution remain open.

## 2026-09-16 - Request-correlated API collection checkpoint

The registration-neutral router now passes its generated request identity into
collection adapters and rejects a collection envelope that returns a different
identity. This closes a response-lineage gap between the API request and the
PostgreSQL resource reader, while retaining the existing owner, cursor, and
snapshot checks. No application registration, authentication dependency,
migration, worker, or shared provider path was changed.

The focused route/read set passed 13 tests; the complete Strategy Lab v2
package passed 526 tests with Ruff, MyPy, and `git diff --check` clean. All five
declared branch checks passed. The Docker-backed combined gate passed 2,173
tests with 83.06% total coverage (required threshold: 75%), including setup
and cleanup. The change is committed and published; durable submission/command
adapters, schema migrations, application wiring, worker entrypoints, Compose,
upstream reconciliation, and stable Nautilus execution remain open.

## 2026-09-16 - PostgreSQL resource-read adapter checkpoint

`postgres_storage.py` now exposes read-only `get` and deterministic `list_type`
aggregate snapshots. Rows are decoded through the canonical JSON codec and
their state fingerprints are re-authenticated before being returned.
`postgres_resources.py` projects those snapshots into immutable API resource
documents scoped to the authenticated principal. Collection pages sort by a
stable `(sort_value, id)` key and bind opaque cursors to the complete visible
resource-set digest; foreign rows, malformed owner/resource/relationship state,
duplicate identities, and snapshot drift fail closed. The adapter is structural
and registration-neutral, so it does not add migrations, route registration,
authentication dependencies, worker effects, or writes.

Focused validation passed 11 persistence/read-adapter tests; the package tree
passed 525 Strategy Lab v2 tests with Ruff, MyPy, and `git diff --check` clean.
The declared branch checks passed all five checks. The Docker-backed combined
backend gate passed 2,172 tests with 83.05% total coverage (required threshold:
75%), including successful setup and cleanup. This slice is committed and
published; schema migrations, application wiring, router/auth registration,
worker entrypoints, Compose services, upstream reconciliation, and stable
Nautilus execution remain open behind the shared-path gates.

## 2026-09-16 - PostgreSQL resource-read adapter context (in progress)

This changeset owns only the package-local PostgreSQL aggregate read helpers,
the owner-scoped resource projection adapter, focused tests, and the related
documentation/workstream receipts. It must not add migrations, register models
or routes, change authentication, alter existing Strategy Lab services, enqueue
work, or touch provider/ETF/TC2000/frontend paths. The adapter will fail closed
on malformed state, owner mismatch, cursor snapshot drift, and ambiguous
resource identity; writes and state-changing API operations remain behind the
existing compare-and-set and staging gates.

## 2026-09-16 - Registration-neutral API boundary context (in progress)

This changeset owns only the new package-local API adapter/router and its
focused tests, plus the Strategy Lab v2 documentation and workstream receipts.
It will expose deterministic resource/error serialization, cursor-bound reads,
static strategy validation, idempotent asynchronous submissions, and
retry/cancellation command intents through an injected adapter. It must not
register a router in `backend/app/main.py`, touch existing Strategy Lab routes,
models, migrations, authentication dependencies, worker entrypoints, Compose,
provider/ETF/TC2000 paths, or frontend code. The adapter remains responsible for
authorization, persistence, atomic compare-and-set, dispatch, and execution.

## 2026-09-16 - Registration-neutral API boundary checkpoint

`api_router.py` now provides a package-local `create_strategy_lab_router()`
factory. The router exposes cursor-bound resource collection/read endpoints,
static strategy-source validation, idempotent asynchronous submission, and
retry/cancellation command intents. It serializes frozen resource envelopes,
Decimal/timestamp values, submission/command receipts, and stable typed errors;
all state-changing behavior is delegated to an injected adapter scoped by the
authenticated principal. Invalid cursors, resource types, bodies, source size,
missing idempotency keys, and adapter conflicts fail closed. The router is
deliberately not registered in `main.py`, so no shared application/auth/model
path was changed.

Focused validation passed 7 API-router tests. The exact package tree passed 519
Strategy Lab v2 tests, Ruff, MyPy, and `git diff --check`; the declared branch
checks passed all five checks. The Docker-backed combined backend gate passed
2,166 tests with 83.04% total coverage (required threshold: 75%), including
successful setup and cleanup. This remains an adapter boundary: durable
PostgreSQL/API wiring, authentication dependency selection, Redis dispatch,
worker effects, router registration, and full upstream reconciliation remain
open behind the existing gates.

The implementation context is complete. The next action is to reconcile the
provider-platform, ETF, and TC2000 shared contracts after their branches reach
staging, then register this router and add additive persistence/API/worker
integration without changing the engine-neutral contracts. No other worktree
or shared path was modified.

## 2026-09-15 - Approved implementation plan

The human explicitly activated implementation of the agreed Strategy Lab v2
plan. The assigned worktree is `feat/strategy-lab-v2`, created through the
repository's guarded workflow from synchronized `staging` at
`8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`. Bootstrap commit
`52a67c6cc74e4b8e4efe95e9d608bce821b8bd02` is published and synchronized.

The initial implementation is limited to new engine-neutral backend package
paths and package-co-located focused tests. A read-only ownership audit found
that the active provider workstream owns `backend/tests/`; v2 tests therefore
stay under `backend/app/strategy_lab_v2/tests/` and are run by explicit pytest
path. The package may define contracts for later adapters but must not
modify provider-platform, ETF, or TC2000 worktrees; current Strategy Lab routes
and services; shared models, migrations, application registration, worker/task
entrypoints, global dependencies, Compose, or frontend until the three parallel
branches reach staging and every overlap is semantically reconciled. The next
phase consumes their staged capability, point-in-time membership, and immutable
CodeVersion/Study Lab contracts without duplicating their ownership.

Nautilus v2 remains the sole authoritative engine target, gated on stable
publication and the branch conformance suite. Current official release evidence
still identifies the v2 line as release candidates; no candidate is eligible
for production enablement. The engine-neutral core can progress independently.
The eventual runtime uses a separate isolated worker environment and a Rust
adapter for canonical forward events. Backtests and persistent broker-free
shadow instances have separate worker capacity. The frontend remains a later
TC2000-native dockable suite in a separately authorized branch.

The branch-owned plan records the architecture, all final acceptance criteria,
the current parallel-safe boundary, deferred shared-path gates, and
`full_stack_browser` completion profile. Initial focused package work can use
unit checks; the complete branch must pass the repository's full backend,
database/Redis, migration, Compose, worker, API, browser, and exact-tip gates.
`make branch-validate` currently validates all workstream records. The
session-local goal is active.

Session `603da09c-b640-4018-9f40-c62f4564b074` owns this worktree. Do not edit
another worktree, even if dependency work advances in parallel; reconcile its
staged changes here only after an authorized staging update.

## 2026-09-15 - Engine-neutral core checkpoint

The initial engine-neutral implementation is committed locally as
`4f265239c1b736e50ba7bf514f0986ca663eebc9`; a separate focused documentation
correction is `1d934e578cb3a75f37d31ec30b6d551d004452b5`. Both commits are in the
assigned worktree. They add only `backend/app/strategy_lab_v2/` and
`docs/strategy-lab-v2.md`. No active provider, ETF, TC2000, model, migration,
router, worker, dependency, Compose, or frontend path was changed.

Focused evidence on the code checkpoint: `cd backend && rtk uv run pytest
app/strategy_lab_v2/tests -q --override-ini addopts=` passed (9 tests),
`rtk uv run ruff check app/strategy_lab_v2` passed, and
`rtk uv run mypy app/strategy_lab_v2` passed. The focused pytest override avoids
applying the repository-wide coverage threshold to this package-only slice; it
does not satisfy the final full-suite gate.

The core now includes typed immutable domain and strategy-package contracts,
canonical content fingerprints, preflight classification and degradation,
semantic snapshot-to-requirement matching, SDK input/intent contracts,
deterministic search and walk-forward planning, Decimal baseline metrics,
attempt/forward-event lifecycle helpers, and result provenance binding trial,
successful attempt, package/strategy, portfolio, snapshot, metric, engine/build,
dependency, assumptions, seed, and output artifact identities.

Important trust boundary: `DataSeriesManifest` binds an upstream
`coverage_evidence_digest`, but the engine-neutral package cannot resolve or
validate that evidence document. `DataSnapshot` checks manifest semantics and
range continuity only; it trusts the upstream attestation reference. Before any
execution path exists, the provider-platform adapter must validate the attested
series content, range, row count, calendar, and semantic dimensions. Host-side
portfolio allocation/shared-risk execution, complete metrics, persistence, API,
isolated strategy runtime, workers, local Compose services, and authoritative
Nautilus execution remain unfinished. Do not treat this checkpoint as a usable
simulator or sandbox.

Publication hold: after the implementation commit, the exact command
`rtk git push origin feat/strategy-lab-v2` was denied by the elevated execution
approval reviewer. Its stated issue was that the transcript did not establish
the private `origin` destination as a trusted organization-owned repository or
contain explicit authorization for that destination. The pre-operational local
implementation/doc tip is `1d934e578cb3a75f37d31ec30b6d551d004452b5`; after
this workstream-record checkpoint, verify its enclosing commit externally with
`rtk git rev-parse HEAD`. The remote `origin/feat/strategy-lab-v2` remains
`d2497f43084d52d3e66b40a91be25dd2678620be`. Do not retry through another shell,
API, plugin, or indirect route. Continue independent local work; ask the human
to explicitly authorize this exact remote destination before attempting normal
publication again.

## 2026-09-15 - Shared-account allocation and metrics checkpoint

The second parallel-safe implementation slice is committed locally as
`6def980311f7c5aef05ffcc13646d9beeae5c5aa`. It adds event-aligned component
target resolution, deterministic conflict policies, cash-equity-only signed
notional risk checks, all-or-nothing shared limits, explicit flat targets, and
34-digit deterministic Decimal arithmetic. Product classes without a registered
and policy-allowed risk model fail closed. Raw order sizing and engine routing
remain unsupported.

Metrics v2 now adds explicit-currency account P&L/return, drawdown duration,
Ulcer, annualized return/volatility, Sharpe/Sortino/Calmar, monetary recovery
factor, empirical nearest-rank VaR/expected shortfall, and trade-quality/streak
summaries. Each value records its calculation and basis conventions. Equity
curves currently mean equally spaced post-start marks; timestamps and
irregular-time annualization remain unsupported. Exposure/capital, execution
cost, attribution, rolling, distribution, sensitivity, calendar metrics,
persistence, APIs, workers, isolated execution, and Nautilus integration remain
open.

Validation on the exact implementation tree: focused package pytest passed 30
tests; Ruff and mypy passed; `git diff --check` passed. `make branch-validate`
is rerun after this operational checkpoint. The package-only checks do not
satisfy the planned full-stack completion profile.

Publication remains a transport hold, not a product blocker. The current
implementation tip is `6def980311f7c5aef05ffcc13646d9beeae5c5aa`; the recorded
remote tip is `d2497f43084d52d3e66b40a91be25dd2678620be`, so the local branch is
four commits ahead after this implementation commit. The previous elevated
push for an earlier payload was rejected by the private-repository egress
review. No push of the current range has been attempted. Do not retry
`rtk git push origin feat/strategy-lab-v2` until the human explicitly authorizes
the exact current destination and range; continue independently scoped local
work and never claim synchronization.

The prior next-action context has been completed at the checkpoint below. Keep
shared integration deferred until provider, ETF, and TC2000 reach staging and
their exact contracts are reconciled. Maintain `in_progress`; closure,
integration, promotion, and deployment are not authorized.

## 2026-09-15 - Run-scoped observations and result metrics checkpoint

The next engine-neutral result slice is committed locally as
`82749796ac520a227288e7fa54dfed3a589a3983`. It adds normalized event-time and
sequence points, account exposure snapshots, fill cost observations, and
component P&L observations. All run observations carry a run-attempt identity;
component P&L is bound to one common result bundle and reconciles exactly to
portfolio gross/net P&L, including an explicit unallocated residual when needed.

Metrics v3 now provides event-sampled cash-equity notional/equity and cash/equity
ratios, run-scoped fill-cost summaries, and reconciled component P&L
contributions. Exposure measures are sample-weighted, not time-weighted or
margin utilization. Cost totals and bps are null unless every fill has an
explicit complete cost report; partial/unavailable reports are counted and
reported category values are labelled as observed rather than complete. FX,
slippage, cost models, and attribution methods require adapter-provided evidence;
the core infers none of them. Stable canonical observation digests travel with
metric calculation bases. Independent review found no remaining actionable
P0-P2 findings after the run-identity and incomplete-cost fixes.

Exact-tip package validation at the implementation commit passed: focused
package pytest (39 tests), Ruff, mypy (16 files), and `git diff --check`. This is
not the planned full-stack validation profile. Existing deferred gaps include
calendar-aware rebalance semantics, irregular-time/rolling/distribution/
sensitivity/calendar metrics, product-specific risk models beyond cash
equities, verified provider coverage evidence, persistence, APIs, workers,
isolated strategy execution, Compose services, and authoritative Nautilus v2
execution/conformance.

The branch remains local and is six commits ahead of recorded remote
`d2497f43084d52d3e66b40a91be25dd2678620be`; no push of this current range was
attempted. The previous private-repository egress hold remains unchanged. Do not
publish through another route; continue local work under this session. Next:
define and test immutable calendar-versioned rebalance policy and schedule
semantics in package-owned paths. Keep provider, ETF, TC2000, shared runtime,
migration, API registration, Compose, and frontend ownership boundaries intact.

## 2026-09-15 - Calendar-aware rebalance scheduling checkpoint

The next engine-neutral slice is committed locally as
`32019aa8518114f1ca658d2b9e9f24c8c2f53083`. `PortfolioComposition` now binds an
optional typed, versioned `CalendarRebalancePolicy`. The new `rebalance.py`
contract pins that policy to an immutable content-addressed session calendar
with explicit trading/closed dates, timezone/tzdb versions, source evidence,
venue-assigned session labels, and UTC session segments (including split
sessions, overnight trading dates, DST, and early closes).

The pure planner supports each-session, ISO-weekly, monthly, quarterly, and
yearly cadence, first/last actual session selection, open-before-events or
close-after-events decision boundaries, and explicit misfire policy. Weekly and
larger cadences require complete calendar period coverage; requested ranges use
inclusive venue session labels. No calendar is fetched or inferred. The planner
does not map boundaries to engine event sequences, apply component capital
weights, emit orders, or imply fills at open/close prices; those remain adapter
and execution work.

Exact-tip package validation passed: focused pytest (48 tests), Ruff, mypy (18
files), and `git diff --check`. Independent review found no remaining actionable
P0-P2 findings after correcting the stale rebalancing documentation. This is
still package-only validation, not the planned full-stack browser/DB/Redis/
worker/Compose gate.

The local branch is eight commits ahead of recorded remote
`d2497f43084d52d3e66b40a91be25dd2678620be`; no push of this current range was
attempted, and the previous private-repository egress hold is unchanged. Next
bounded work: add run-attempt-scoped timestamped account-equity observations
and rigorous calendar-period metric inputs, explicitly preserving irregular
event timing and rejecting unsupported external-cash-flow assumptions. Keep
all parallel provider, ETF, TC2000, shared runtime, migration, API, Compose, and
frontend boundaries unchanged. Maintain `in_progress`; closure, integration,
promotion, and deployment remain unauthorized.

This operational checkpoint updates only the following branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/plan.yaml`
- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-09-16 - Replicate seed and sensitivity evidence checkpoints

The seed-provenance implementation is committed locally as
`6ec5074e696a4333dd9fe5b59ec0f693fb0477f9`, with its separate ops record at
`cefa6c468501c990676587f0e39287f9976bc56b`. It adds deterministic replicate
seed schedules while preserving the default single-trial identity and legacy
seed path. Focused validation passed 60 package tests, Ruff, MyPy (18 source
files), and `git diff --check`.

The sensitivity-evidence implementation is committed locally as
`69faca1941157ff1597e209ce6d2679af08fcd70`, with its separate ops record at
`f19db3e634b822f1cf27257e18d7ea33b3332137`. It distinguishes unpaired runs,
shared-seed provenance, and unverified keyed-stream pairing claims; it does not
assert statistical independence or calculate numeric deltas. Focused validation
passed 60 package tests, Ruff, MyPy (18 source files), and `git diff --check`;
the workstream validator passed all 30 records after the checkpoint update.

The recorded origin remains
`d2497f43084d52d3e66b40a91be25dd2678620be`. The private-origin publication
hold remains unchanged: no push was attempted for these exact ranges and no
alternate publication route is authorized.

## Scope recorded - stable metric calculation identity and run evidence

This bounded engine-neutral context owns only
`backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/metrics.py`,
`backend/app/strategy_lab_v2/tests/test_metrics.py`,
`backend/app/strategy_lab_v2/tests/test_observations.py`, and
`docs/strategy-lab-v2.md`. It introduces a versioned structured
calculation definition and typed evidence references on calculated metrics.
The stable calculation fingerprint excludes observed values, sample sizes,
display strings, and run evidence; per-family effective parameters are recorded
where they change calculation semantics. Formula version v6 remains unchanged.
No metric deltas, statistical inference, comparator, API, persistence, worker,
runtime, Compose, frontend, provider, ETF, TC2000, or shared path is included.

Exact focused checks pass: 62 Strategy Lab v2 tests (`--no-cov` to avoid the
repository-wide coverage threshold on this focused selection), Ruff, MyPy (18
source files), and `git diff --check`. Independent read-only review initially
found an overbroad annualization parameter on cadence-independent metrics; it
was narrowed to annualized/risk-adjusted metrics and re-reviewed with no
remaining P0-P2 issue. The formula compatibility test now confirms that changing
`periods_per_year` preserves total-return identity while changing annualized
return identity.

The five product files listed above were committed locally in
`f34fb2564d62c8721f1b518ca093876271f3e3ca`; the later checkpoint below records
that completed changeset. Keep the existing publication hold; do not push
without exact-payload authorization. The enclosing operational checkpoint SHA
will be verified externally with `git rev-parse` rather than written into
itself.

## Completed context - Trial seed-sharing and replicate provenance

This implementation context owned only
`backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/experiments.py`,
`backend/app/strategy_lab_v2/tests/test_core.py`, and
`docs/strategy-lab-v2.md`. Preserve the existing per-candidate seed output as
the default, and add an explicit shared-seed-per-scenario-and-replicate policy
plus typed trial randomization provenance (master seed, effective seed,
replicate index, seed-group fingerprint, derivation version). This is a seed
assignment contract only: equal initial seeds do not prove event-level paired
randomness or statistical comparability when an engine consumes sequential or
otherwise unkeyed random streams. One-factor paired sensitivity, engine RNG
attestation, API/persistence, workers, and runtime integration remain deferred.
Keep provider, ETF, TC2000, shared runtime, migration, route, Compose, and
frontend ownership unchanged.

Compatibility review: preserve the old `ScientificTrial.trial_id` for the
default per-candidate, single-replicate, unscoped schedule. Its typed assignment
retains master/effective seed, seed-group fingerprint, and derivation version,
but excludes the legacy schedule metadata from trial identity. Explicit shared,
scoped, or replicated schedules bind the group provenance and replicate count
into trial identity. The regression compares builder output with the prior
explicit-effective-seed construction. A subsequent independent review also
found that callers could pair a valid digest with the wrong effective seed; the
contract now checks derived seeds against supported versioned digests and
rejects unknown derivation versions. Explicit-seed records are separately
validated and cannot claim generated schedule provenance.

The implementation is committed locally as
`6ec5074e696a4333dd9fe5b59ec0f693fb0477f9`. It preserves legacy default seed
values and trial IDs, adds deterministic shared-per-scenario/replicate seed
assignments, carries replicate count and seed-group provenance, validates the
effective seed against the supported digest version, and rejects unsupported or
inconsistent assignments. Equal initial seeds still do not claim paired draws.

Exact focused validation passed: 60 package tests, Ruff, MyPy (18 source files),
`git diff --check`, and `make branch-validate` (30 workstream records).
Independent review found no remaining P0-P2 issue. This is package-level
evidence only; the full-stack/DB/Redis/API/worker/Compose/Nautilus completion
gates remain outstanding.

Publication state is `committed_locally_pending_push`. At the implementation
commit boundary, `HEAD` is `6ec5074e696a4333dd9fe5b59ec0f693fb0477f9` and
`origin/feat/strategy-lab-v2` is
`d2497f43084d52d3e66b40a91be25dd2678620be`; the exact range is
`d2497f43084d52d3e66b40a91be25dd2678620be..6ec5074e696a4333dd9fe5b59ec0f693fb0477f9`.
No push of this range was attempted because exact-payload authorization for the
private origin is unavailable. Do not use an alternate transport. The separate
ops checkpoint for this seed-provenance slice was committed locally before the
next sensitivity-evidence implementation recorded below. Do not treat this
implementation-only range as a new authorization to publish the full branch.

## 2026-09-16 - Sensitivity randomization-evidence checkpoint

The implementation is committed locally as
`69faca1941157ff1597e209ce6d2679af08fcd70`. It adds an engine-neutral
`SensitivityComparisonEvidence` contract that requires successful results to
share their fixed execution context and distinguishes `unpaired`,
`shared_seed_only`, and `pairing_claim_unverified`. An equal integer seed alone
does not establish a common randomization group; matched scenario/replicate seed
provenance is required for the shared-seed-only label. A structurally complete
keyed-stream claim binds both attempts, the engine build, trace artifacts, and a
matched-draw artifact, but the contract deliberately cannot authenticate these
artifacts or prove engine conformance. No verified paired-stream or statistical
independence classification is emitted until a trusted verifier/registration
receipt exists. Retries of one scientific trial are not treated as sensitivity
replicates. This contract classifies randomization provenance only; it does not
compare metric semantics, calculate metric deltas, or perform paired inference.

Independent review initially identified overclaims around independence and
unverified paired evidence, plus an invalid exact comparison of run-dependent
metric calculation-basis strings. The implementation now uses neutral
`unpaired` and unverified-claim levels, and separates provenance classification
from metric compatibility. Re-review found no remaining P0-P2 issue.

Exact implementation-commit validation passed: 60 package tests, Ruff, MyPy
(18 source files), and `git diff --check`. `make branch-validate` passed all 30
records on an elevated retry after the default sandbox denied UV cache metadata
access; this was the repository validator only. These focused checks do not
satisfy the DB/Redis/API/worker/Compose/Nautilus/security/full-stack acceptance
gates.

At this implementation boundary, local HEAD is
`69faca1941157ff1597e209ce6d2679af08fcd70`, 18 commits ahead of recorded
`origin/feat/strategy-lab-v2`
(`d2497f43084d52d3e66b40a91be25dd2678620be`). No push was attempted because
exact-payload authorization for the private origin is unavailable; do not
publish through another route. The separate ops checkpoint will be committed
after these implementation results are recorded.

The next bounded slice in that handoff, separating stable calculation identity
from run-specific evidence, was implemented in
`f34fb2564d62c8721f1b518ca093876271f3e3ca` and is recorded below. Numeric
one-factor descriptive sensitivity deltas remain the next metric slice. Keep
paired statistical inference deferred until the worker has a trusted keyed-
stream verifier and aligned per-observation outputs. Preserve all provider,
ETF, TC2000, shared runtime, persistence, API, worker, Compose, and frontend
boundaries.

This checkpoint updates only these branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-09-16 - Metric calculation identity and evidence checkpoint

The implementation changeset is committed locally as
`f34fb2564d62c8721f1b518ca093876271f3e3ca`. It adds a versioned structured
calculation definition and typed evidence references to metric values. Stable
fingerprints bind metric identity, units, basis, formula version, and only
effective calculation parameters; observed values, sample sizes, display text,
null state, and run-specific evidence do not alter that calculation identity.
All eight current metric families emit stable formula IDs, Decimal context,
effective parameters where semantically relevant, and typed input/calendar/fill/
attribution evidence. The catalog remains v6 because estimator formulas did
not change. This is an identity primitive, not a metric comparator.

Exact focused validation passed: 62 package tests with `--no-cov`, Ruff, MyPy
(18 source files), and `git diff --check`. The initial focused pytest invocation
ran under the repository-wide coverage threshold and exited nonzero at 7.24%
coverage versus the required 55%; it was rerun successfully with `--no-cov`.
`make branch-validate` passed all 30 workstream records on the documented
elevated retry after the default sandbox blocked UV cache metadata access.
Independent review caught an overbroad `periods_per_year` parameter on
cadence-independent metrics; the implementation was narrowed and re-reviewed
with no remaining P0-P2 issue. This package-only evidence does not satisfy the
full-stack/DB/Redis/API/worker/Compose/Nautilus acceptance gates.

The local branch is 20 commits ahead of recorded
`origin/feat/strategy-lab-v2` at
`d2497f43084d52d3e66b40a91be25dd2678620be`. The exact pending range ends at
`f34fb2564d62c8721f1b518ca093876271f3e3ca`. No push was attempted: exact-payload
authorization for the private origin remains unavailable, and no alternate
transport is authorized. The default sandbox denied UV cache metadata access
for repository workflow commands; the exact session-status command succeeded
on the documented narrow elevated retry. No sandbox setting was changed, and
no other worktree or shared/provider/frontend path was touched.

Next bounded implementation context: add run-scoped descriptive one-factor
metric deltas using `MetricValue.calculation_fingerprint` to require compatible
calculation semantics. Preserve unpaired/shared-seed provenance labels; do not
claim statistical significance or paired inference without trusted keyed-stream
verification and aligned per-observation outputs. Only the three branch-owned
workstream records below remain in this checkpoint; stop this session after
the ops checkpoint per the repository soft-stop rule.

This checkpoint updates only these branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

The soft-stop `agent-session-checkpoint` completed under the existing session
claim. Its `dirty_paths` capture dropped the leading `b` from the first modified
path (`backend/...` appeared as `ackend/...`), because the helper strips leading
status whitespace before removing the porcelain prefix. Raw `git status` confirms
the correct path. I corrected only this workstream's `session.json`; the helper
implementation is outside this branch's owned scope and was not changed.

## 2026-09-15 - Calendar-period equity metrics checkpoint

The next engine-neutral slice is committed locally as
`5a5177ea28d5a1b50d225aaa5b400d46f4a411aa`. It adds immutable,
run-attempt-scoped account-equity intervals bound to a versioned session
calendar. Calendar metrics reconcile account equity deltas less explicit
external cash flows and support each-session, ISO-weekly, monthly, quarterly,
and yearly buckets. Period completeness requires the prior actual session
close through the period's final actual session close; returns are null for
incomplete coverage or external flows (time-weighted returns are not inferred).

Independent review identified and resolved one P2 comparison risk: a partial
window could otherwise emit a value named as a full calendar-period return.
The partial-period test now asserts the null and its explicit reason. Exact-tip
focused validation passed: 51 package tests, Ruff, mypy (18 source files), and
`git diff --check`. `ruff format --check` would reformat ten package files,
including existing code, so broad formatter churn was not applied. The focused
checks do not satisfy the planned database/Redis, API, worker, Compose, Nautilus,
security, or full-stack validation gates.

The branch is ten commits ahead of recorded remote
`d2497f43084d52d3e66b40a91be25dd2678620be`; this slice has not been pushed and
the prior private-repository publication hold remains unchanged. No shared or
parallel branch was touched. Next bounded engine-neutral slice: implement
run-scoped rolling return/risk series with explicit session sampling, complete
window coverage, and minimum-observation rules. Keep provider, ETF, TC2000,
shared runtime, persistence, API, worker, Compose, and frontend boundaries
unchanged. Maintain `in_progress`; closure, integration, promotion, and
deployment remain unauthorized.

This checkpoint updates only these dirty branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-09-15 - Rolling and calendar-period equity metrics checkpoint

The implementation changeset is committed locally as
`2d9d8865bc69292dcd1c48719fa6ab803686af3f`. It adds typed rolling session-close
metric points, exact session-window coverage, explicit annualization and
risk-free assumptions, and rolling P&L/return/volatility/Sharpe/Sortino/drawdown/
duration/Ulcer metrics. Calendar-period and rolling aggregators now require
complete external-flow reports for adjusted net P&L and explicit flow-occurrence
evidence for return/risk eligibility. Independent review found and resolved the
zero-net offsetting-flow case; a zero net amount with any flow event now withholds
return and equity-path risk metrics. An intermediate focused run also exposed an
unavailable-flow test fixture that retained stale occurrence evidence; the
fixture was corrected to omit both amount and occurrence, and the final exact-tip
checks pass.

Exact-tip focused validation passed: 56 package tests, Ruff, MyPy (18 source
files), and `git diff --check`. Independent review found no remaining concrete
defect. This is package-only evidence, not the planned full-stack/DB/Redis/API/
worker/Compose/Nautilus completion gates.

The implementation commit remains pending publication at
`2d9d8865bc69292dcd1c48719fa6ab803686af3f`; the separate ops checkpoint is
being committed on top of it. The recorded remote tip is
`d2497f43084d52d3e66b40a91be25dd2678620be`. No push of the current range was
attempted because the prior private-repository egress review rejected a payload
and the exact current range has not been authorized. Do not retry through an
alternate route. Verify the enclosing ops commit with `git rev-parse` after
commit rather than creating a self-referential hash update. No parallel worktree
or shared/provider/frontend path was modified.

Next bounded slice: run-scoped session-return distribution metrics over the
validated account-equity intervals and exact session calendar. Keep sensitivity
analysis deferred until common-random-seed/matched-trial semantics are defined.
Continue to preserve provider, ETF, TC2000, shared runtime, migration, API,
worker, Compose, and frontend boundaries. Maintain `in_progress`; closure,
integration, promotion, and deployment remain unauthorized.

This checkpoint updates only these branch-owned records:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## Scope recorded before implementation - Run-scoped session-return distributions

The implementation context owned only
`backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/metrics.py`,
`backend/app/strategy_lab_v2/tests/test_core.py`,
`backend/app/strategy_lab_v2/tests/test_observations.py`, and
`docs/strategy-lab-v2.md`. It added typed, run-scoped close-to-close return
quantiles and empirical VaR/expected-shortfall outputs, using explicit inclusive
session-label bounds, exact calendar adjacency and predecessor-close evidence,
minimum sample rules, and the current external-flow fail-closed contract. The
global metric catalog advanced to v6 without changing the v5 equity-curve
estimator semantics. No histogram bins, sensitivity ranking, APIs, persistence,
workers, runtime, Compose, frontend, provider, ETF, TC2000, or shared paths are
in scope. The prior private-repository egress hold remains: continue locally
from the verified clean boundary; do not publish without exact-payload
authorization.

## 2026-09-16 - Run-scoped session-return distribution checkpoint

The implementation is committed locally as
`444193415f0236536767892d6f28effaec39d4ec`. It adds a typed, run-scoped
distribution summary and exact-calendar-bounded close-to-close session-return
quantiles, empirical VaR, and expected shortfall. Inclusive trading-session
bounds require every actual session observation and its preceding actual
session-close mark. Nearest-rank calculations record their effective ranks/tail
counts and use exact integer-rational ceiling arithmetic so high-precision
probabilities cannot move a rank at a Decimal rounding boundary. Incomplete
coverage, incomplete flow reports, or any flow event (including zero-net
offsetting flows) withholds the entire distribution. The catalog is v6; existing
equity-curve estimator semantics are unchanged. Histogram bins and sensitivity
analysis remain out of scope for this slice.

Exact implementation-commit validation passed: focused package pytest (59
tests), Ruff, MyPy (18 source files), and `git diff --check`. Independent
read-only review found no remaining concrete defect. `make branch-validate`
passed all 30 records on an elevated retry after the default sandbox denied UV
cache metadata access; the retry ran only that repository validator. These
package checks do not satisfy the final full-stack/DB/Redis/API/worker/Compose/
Nautilus acceptance gates.

Publication remains a transport hold. Local HEAD is
`444193415f0236536767892d6f28effaec39d4ec`; recorded
`origin/feat/strategy-lab-v2` remains
`d2497f43084d52d3e66b40a91be25dd2678620be`, so this branch is 14 commits ahead.
No push of this exact current range was attempted. The earlier private-repository
egress review rejected a prior payload, and the current remote/range does not
have exact-payload authorization; do not publish through another route.

Next bounded context: define and test deterministic common-random-seed and
replicate semantics for matched one-factor sensitivity analysis. Only after
those semantics are pinned should the comparison contract be added; do not
silently compare trials with independently derived seeds. Keep all active
provider, ETF, TC2000, shared runtime, persistence, API, worker, Compose, and
frontend ownership boundaries unchanged. This separate checkpoint updates only
the branch-owned handoff, session state, and validation journal below.

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

## 2026-09-16 - Descriptive one-factor metric delta (in progress)

The bounded implementation context owns only
`backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/sensitivity.py`,
`backend/app/strategy_lab_v2/tests/test_core.py`,
`backend/app/strategy_lab_v2/tests/test_sensitivity.py`, and
`docs/strategy-lab-v2.md`. It adds a run-scoped descriptive delta that requires
exactly one canonical parameter change, a matching structured metric
calculation fingerprint, and identical projected measurement-scope identities.
The scope binds the frozen snapshot and its referenced coverage claims,
experiment/scenario, portfolio currency, execution context, formula identity,
and applicable session-calendar evidence. It does not authenticate upstream
coverage claims. Null/incompatible cases are explicit unavailable outcomes;
sample sizes and the existing unpaired/shared-seed/unverified-pairing labels
are preserved. This context makes no significance, ranking, replicate-aggregate,
or paired-inference claim.

The product changeset is committed locally as
`9da8d667e327aca619cc93bd8d22eac123e688a5`. Post-commit focused validation
passed at this exact SHA: 75 Strategy Lab v2 tests, Ruff, focused Ruff formatting
checks for the new comparator/test files, MyPy (20 source files), and
`git diff --check`. Independent read-only review found two missing contract
invariants; both were fixed with direct-construction tests, and the re-review
found no remaining concrete issue. This is package-level evidence, not the final
database/Redis/API/worker/Compose/Nautilus/full-stack acceptance gates.

The ordinary sandbox denied creation of the worktree `.git/index.lock` on the
first commit attempt. Read-only checks found the worktree index owned by the
current user and no stale lock. The repository's narrow elevated Git retry then
committed the already-reviewed staged changeset successfully. No sandbox setting
was changed. This is the documented workflow recovery, not a product blocker.

The required schema-4 session checkpoint initially needed the repository
`agent-session-goal-state` helper to move the takeover marker from
`resumed_after_takeover` to `active`, matching the still-active thread goal.
The checkpoint then passed on the narrow elevated retry after default UV cache
metadata access was denied. Its known dirty-path helper bug removed the leading
`o` from the first path; raw `git status` showed the exact three branch-owned ops
files, and `session.json` was corrected manually. No other path is dirty.

The local branch was 22 commits ahead of
`origin/feat/strategy-lab-v2` at `d2497f43084d52d3e66b40a91be25dd2678620be`
after the product commit. No push was attempted: the private-origin exact-payload
authorization hold remains, and this agent will not use an alternate transport.
The separate ops checkpoint will add one commit above the last recorded
pre-checkpoint SHA; verify the enclosing final SHA externally with `git
rev-parse` rather than chasing a self-referential session hash.

`make branch-validate` passed all 30 workstream records on the narrow elevated
retry after the default sandbox denied UV cache metadata access, including a
final pass after the checkpoint refresh, exact dirty-path correction, and
validation-journal update. The required schema-4 session checkpoint is current
for the product SHA, with the active goal recorded. Exact next action: stage and
review only the three branch-owned ops files, commit the separate checkpoint,
then verify clean status and the exact final `HEAD`/remote hashes externally.
Do not publish the branch while the exact-payload hold remains.

Next bounded action after this ops checkpoint: from a verified clean local
boundary, inspect remaining parallel-safe Strategy Lab v2 core gaps and choose
the next backend-owned slice. Keep paired inference/profitability ranking
deferred until trusted aligned observations exist. This ops checkpoint updates
only these branch-owned files:

- `ops/workstreams/feat-strategy-lab-v2/handoff.md`
- `ops/workstreams/feat-strategy-lab-v2/session.json`
- `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`

Do not mutate another worktree or provider, ETF, TC2000, shared runtime, API,
persistence, Compose, or frontend path.

## 2026-09-16 - Descriptive one-factor replicate summaries (in progress)

The next bounded implementation context owns only
`backend/app/strategy_lab_v2/sensitivity.py`,
`backend/app/strategy_lab_v2/tests/test_sensitivity.py`, and
`docs/strategy-lab-v2.md`. It adds a deterministic descriptive comparison over
complete baseline and variant replicate groups of successful
`RunResultManifest` values. The groups must differ in exactly one canonical
parameter, contain one result for each distinct scientific trial, and cover
every planned replicate index exactly once. Fixed experiment, scenario,
snapshot, capability, portfolio, engine/build, dependency, assumption, metric
calculation, and measurement-calendar scopes must agree. Missing, duplicate,
null, or incompatible replicates fail closed rather than silently shrinking the
sample. Results retain the per-arm randomization provenance and report
descriptive per-arm summaries plus the difference of sample means. Equal
replicate indices or seeds are not treated as verified paired draws; no
significance, confidence interval, candidate ranking, or independence claim is
made.

Read-only gap audit confirmed that the current v6 package already has account
performance, trade-quality, cash-equity exposure, fill-cost, component
attribution, calendar/rolling, session-return-distribution, and one-run metric
delta calculators. This replicate-level summary is the next parallel-safe
metric gap. Time-weighted returns requiring external-flow boundary valuations,
irregular-time annualization, true margin/capital utilization, financing outside
fill reports, and trusted paired inference remain deferred. Provider, ETF,
TC2000, persistence, API, worker, runtime, migration, Compose, and frontend work
remain outside this context.

The preceding one-factor delta product commit is
`9da8d667e327aca619cc93bd8d22eac123e688a5`; its separate ops checkpoint is
`dfe93ae7014074be066ef677a3c7b985a500956e`. External verification after that
checkpoint found local `HEAD` at `dfe93ae7014074be066ef677a3c7b985a500956e`,
`origin/feat/strategy-lab-v2` at
`d2497f43084d52d3e66b40a91be25dd2678620be`, and a clean worktree (23 commits
ahead). The private-origin exact-payload export hold remains; no push of this
current range was attempted, and no alternate transport is authorized. Continue
from the clean local boundary without claiming remote synchronization.

This scope-selection checkpoint updates only this branch's `plan.yaml`,
`handoff.md`, `session.json`, and `validation.jsonl`. Validate and commit those
records separately before changing the three implementation-context paths
listed above. The session checkpoint helper rejects a changed plan until
`agent-session-plan-ready` runs; the repository helper requires the plan update
to be committed and the local branch head to match its remote before it can mark
the plan ready. Because the exact private-origin range is still under its
authorization hold, the replicate implementation must not start until that
plan-ready gate is satisfied. After this scope checkpoint is locally committed,
the next action is to obtain exact-payload authorization for the resulting
`origin/feat-strategy-lab-v2..HEAD` range, publish only through the approved Git
path, verify synchronized hashes, then run the required plan-ready/session-state
reconciliation. Do not bypass the gate or use another transport.

## 2026-09-16 - Synchronization and plan-ready reconciliation

The human explicitly authorized the exact current export after the prior
private-origin safeguard. The approved elevated command
`rtk git push origin feat/strategy-lab-v2` succeeded for
`d2497f43084d52d3e66b40a91be25dd2678620be..0f0d85c214de6828d8e15b6d03d60adcb1551c2a`.
Post-push verification found a clean worktree and matching local/remote HEAD at
`0f0d85c214de6828d8e15b6d03d60adcb1551c2a`.

`make agent-session-plan-ready SESSION_ID=e2731935-179c-4c35-b5d2-aadf7b4857f7`
passed after synchronization. The resumed session goal was recorded as active
with `make agent-session-goal-state ... STATE=active`, and the required
`make agent-session-checkpoint SESSION_ID=e2731935-179c-4c35-b5d2-aadf7b4857f7`
passed through the approved elevated UV path. The session record now reflects
the synchronized publication state. This operational reconciliation is being
committed separately; verify its enclosing commit externally with
`git rev-parse` rather than writing a self-referential SHA into the record.

The next bounded implementation action is the already scoped descriptive
one-factor replicate summary in the engine-neutral package. Keep the strict
complete-replicate, fixed-context, no-ranking/no-inference boundary and all
provider, ETF, TC2000, persistence, API, worker, runtime, migration, Compose,
and frontend ownership gates intact.

## 2026-09-16 - Descriptive replicate-summary implementation checkpoint

The scoped engine-neutral metric slice is complete in product commit
`3767730ec32ee7cf19b0e4d44fac7caf664f8baf`. It adds immutable typed
`ReplicateRandomizationSummary`, `NearestRankStatistic`,
`ReplicateMetricStatistics`, `OneFactorReplicateMetricSummary`, and explicit
`ReplicateMetricSummaryUnavailable` outcomes in `sensitivity.py`, plus the
`summarize_one_factor_metric_replicates()` API and compatibility alias
`compare_one_factor_metric_replicates()`.

The summary requires successful results covering every planned replicate index
exactly once on each arm, rejects duplicate trials/attempts and inconsistent
arm parameters, enforces exactly one canonical parameter change, and binds one
fixed execution and metric-measurement scope. It preserves each arm's realized
observation sample sizes and full seed provenance, computes Decimal means,
nearest-rank median/minimum/maximum and configured quantiles, and exposes only
the signed difference of arm means. It never ranks candidates or claims
significance, independence, or verified pairing. Focused sensitivity tests now
cover deterministic ordering/statistics, shared-seed-only labeling, incomplete
groups, and null values.

Validation on the exact implementation tree passed 18 focused sensitivity
tests, 80 package tests, Ruff for the changed package files, MyPy for the
changed source and tests, and `git diff --check`. A package-wide Ruff format
check still reports seven pre-existing formatting differences in unrelated
files; no unrelated formatting was changed.

The implementation commit was pushed once through the approved elevated Git
path, but the private-origin safeguard rejected the newer payload before Git
because exact authorization for `0f0d85c214de6828d8e15b6d03d60adcb1551c2a..3767730ec32ee7cf19b0e4d44fac7caf664f8baf` was not established. No alternate
transport or retry was used. The current clean local boundary is
`3767730ec32ee7cf19b0e4d44fac7caf664f8baf`; the remote remains
`0f0d85c214de6828d8e15b6d03d60adcb1551c2a`. The operational record below is
being committed separately; derive the full pending range externally before
any authorized retry.

Next action is blocked only on exact authorization to publish the current
range, followed by plan-ready/session reconciliation for the changed plan. Do
not begin another implementation context, integrate, promote, deploy, or
touch provider, ETF, TC2000, shared runtime, persistence, API, worker, Compose,
or frontend paths while this synchronization gate is unresolved.

## 2026-09-16 - Standing authorization and synchronized implementation boundary

The human granted standing authorization to publish the current Strategy Lab
v2 implementation and its branch-owned operational records. The approved
elevated `rtk git push origin feat/strategy-lab-v2` succeeded for the full
pending range `37a293bc691325460fe75eac4ff9138438da1a54..6b8b6b68a6fd41abcca28f3ca6c9a5e3fbe16669`.
Post-push verification found a clean worktree and matching local/remote HEAD
at `6b8b6b68a6fd41abcca28f3ca6c9a5e3fbe16669`.

The required `agent-session-plan-ready`, `agent-session-goal-state ...
STATE=active`, and `agent-session-checkpoint` workflow gates all passed under
the authorized elevated path. Session metadata now records the synchronized
boundary and an active goal. The next bounded action is to inspect and
implement the next engine-neutral metric slice; no provider, ETF, TC2000,
persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths are opened by this authorization.

## 2026-09-16 - Flow-adjusted return implementation checkpoint

The next package-owned metric slice is complete in product commit
`ec670600a3eda08eea7ee40ea05b61becb45ed83`. It adds the immutable
`ExternalCashFlowBoundaryObservation` and binds ordered interior pre-flow and
post-flow marks to each `AccountEquityIntervalObservation`. Boundary amounts
must reconcile the parent interval's reported flow; zero and offsetting flows
remain observable rather than being collapsed into a false no-flow claim.

`calculate_time_weighted_return_metrics()` now geometrically links the
subperiod factors around every explicit flow, withholds results when native flow
reports are incomplete or boundary evidence is missing, and emits an explicit
elapsed-UTC annualized return using a caller-supplied days-per-year convention.
Existing calendar, rolling, and distribution aggregators remain intentionally
unchanged and fail closed for flow-bearing inputs until they consume this
boundary evidence directly.

Validation on the exact implementation tree passed all 83 Strategy Lab v2
package tests, Ruff checks for the changed files, MyPy for the package, and
`git diff --check`. No provider, ETF, TC2000, persistence, API, worker,
Compose, Nautilus, frontend, integration, promotion, or deployment paths were
changed. The next bounded slice is the boundary-aware wiring for those existing
calendar/rolling/distribution aggregators.

## 2026-09-16 - Calendar-period boundary wiring checkpoint

Product commit `88cc14dda12aa43f49a18e5199248ec25e05283e` wires the explicit
flow-boundary path into `calculate_calendar_period_metrics()`. Complete
flow-bearing periods now report the geometrically linked return when all
pre/post marks are present; missing boundary evidence remains an explicit null
reason. Net P&L continues to reconcile the reported flow independently.

The exact package tree still passes all 83 tests, Ruff, and MyPy. The remaining
boundary-aware metric work is limited to rolling-window and session-distribution
aggregators; no shared provider, ETF, TC2000, persistence, API, worker,
Compose, Nautilus, frontend, integration, promotion, or deployment paths were
changed.

## 2026-09-16 - Rolling and distribution boundary wiring checkpoint

Product commit `f7bb6383bcdafb3695c07061b313fc7c71f6e9b5` completes the
boundary-aware metric wiring. Rolling windows now use geometrically linked
flow-adjusted returns and normalized wealth marks for volatility, Sharpe,
Sortino, drawdown, duration, and Ulcer calculations. Session-return
distributions use the same per-session factors and retain
`returns_flow_adjusted` provenance on the typed summary contract.

The exact implementation tree passed all 83 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`; the consolidated range was published under
the explicit destination authorization and local/remote HEAD match at
`f7bb6383bcdafb3695c07061b313fc7c71f6e9b5`. The next bounded engine-neutral
metric slice is capital/margin utilization or financing evidence. No provider,
ETF, TC2000, persistence, API, worker, Compose, Nautilus, frontend,
integration, promotion, or deployment paths were changed.

## 2026-09-16 - Engine-reported capital and margin utilization checkpoint

The next package-owned metric slice adds immutable
`AccountCapitalMarginObservation` records and
`calculate_capital_margin_utilization_metrics()`. Each observation binds a
portfolio version, run attempt, ordered engine point, positive account equity,
initial and maintenance requirements, supplied capacities, base currency, and
valuation evidence. The calculator emits equally sample-weighted means and
observed maxima for requirement-to-capacity and requirement-to-equity ratios.
It accepts ratios above one as diagnostics and never infers margin, leverage,
or buying power from notional exposure.

The exact implementation tree passed 85 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Financing evidence outside fill reports and
trusted paired inference remain open metric gaps. No provider, ETF, TC2000,
persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths were changed.

## 2026-09-16 - Trial-bound evaluation-window checkpoint

The metric-scope slice adds immutable `EvaluationWindow` records with explicit
evaluation start/end, purpose, and optional warm-up start. The window is bound
into `ScientificTrial` identity and projected into `SensitivityMetricScope`;
`SensitivityComparisonEvidence` now rejects variants that use different
evaluation or warm-up windows. Offset-aware timestamps normalize to UTC and
invalid ranges fail closed.

The exact implementation tree passed 94 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Additional risk evidence and all persistence,
API, worker, and runtime gates remain open. No provider, ETF, TC2000,
persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths were changed.

## 2026-09-16 - Explicit stress-scenario evidence checkpoint

The next engine-neutral risk slice adds `StressScenarioObservation` and
`calculate_stress_scenario_metrics()`. Adapter-supplied initial/stressed equity
and P&L must reconcile exactly and bind a shock-definition digest plus engine
evidence. The calculator emits descriptive scenario/loss counts, average and
worst stressed returns and P&L, and minimum stressed equity. It does not
construct shocks, extrapolate outcomes, or issue a solvency/risk verdict.

The exact implementation tree passed 94 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Metric-scope completeness and all persistence,
API, worker, and runtime gates remain open. No provider, ETF, TC2000,
persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths were changed.

## 2026-09-16 - Explicit financing-cost evidence checkpoint

The next package-owned metric slice adds immutable
`FinancingCostObservation` events and bounded `FinancingCostReport` records.
`calculate_financing_cost_metrics()` keeps financing outside fill-cost reports,
tracks complete/partial/unavailable coverage explicitly, and publishes the
signed reported cash effect for all supplied events. It publishes derived net
financing cost only when every supplied report is complete; incomplete coverage
cannot be interpreted as zero financing. Report and event digests, model
identity, base currency, ordered points, and scope are bound to the metrics.

The exact implementation tree passed 88 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Trusted paired-stream inference remains the next
metric gap. No provider, ETF, TC2000, persistence, API, worker, Compose,
Nautilus, frontend, integration, promotion, or deployment paths were changed.

## 2026-09-16 - Aligned paired-observation metrics checkpoint

The next metric slice adds `PairedMetricObservation` and
`calculate_paired_metric_metrics()`. A verified keyed-stream receipt is
required; observations are keyed, deduplicated, canonically ordered, and
validated as finite Decimal baseline/variant values. The calculator emits
descriptive baseline/variant means, signed mean delta, nearest-rank median,
minimum/maximum delta, and sample standard deviation with receipt and input
digests. It intentionally does not rank candidates, estimate significance, or
claim an inferential model.

The exact implementation tree passed 91 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Metric-scope completeness, risk/stress evidence,
and all persistence/API/worker/runtime gates remain open. No provider, ETF,
TC2000, persistence, API, worker, Compose, Nautilus, frontend, integration,
promotion, or deployment paths were changed.

## 2026-09-16 - Keyed common-random stream verification checkpoint

The next engine-neutral slice adds `pairing.py` with typed
`KeyedRandomDraw` inputs and `verify_keyed_random_stream_pairing()`. The
verifier requires registered engine-build/conformance and stream-contract
digests, rejects empty, duplicate, unmatched, or value-mismatched draws, and
emits a deterministic `KeyedRandomStreamPairingReceipt`. Sensitivity evidence
can bind that receipt and is classified as `verified_paired`; the downstream
comparison remains descriptive and makes no significance or ranking claim.

The exact implementation tree passed 90 Strategy Lab v2 package tests, Ruff,
MyPy, and `git diff --check`. Aligned per-observation inferential metrics,
ranking, significance, and all shared persistence/API/worker/runtime gates
remain open. No provider, ETF, TC2000, persistence, API, worker, Compose,
Nautilus, frontend, integration, promotion, or deployment paths were changed.

## 2026-09-16 - Static strategy-source preflight checkpoint

Product commit `ddac66de4` adds `strategy_validation.py`, a deterministic AST
preflight that binds every result to the exact source digest and rejects
disallowed or relative imports, filesystem/network roots, dynamic-code calls,
aliases of dangerous builtins, and private-object introspection. A forbidden
root remains rejected even when a caller attempts to broaden the allowlist. The
preflight is intentionally an early rejection layer, not the runtime security
boundary: isolated execution, no-network/read-only filesystem enforcement,
resource limits, secret exclusion, and adversarial container tests remain open.

The exact implementation tree passed all 100 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`; the product commit is published at the
authorized `origin/feat-strategy-lab-v2` destination. Persistence, API, worker,
artifact, Compose, Nautilus, frontend, integration, promotion, and deployment
paths remain unchanged. The next bounded slice is an engine-neutral
artifact/result-integrity contract while preserving this static-preflight and
runtime-isolation boundary.

## 2026-09-16 - Artifact payload integrity checkpoint

The next engine-neutral slice adds `artifacts.py` with raw-byte SHA-256 content
addressing and `ArtifactIntegrityReceipt`. `verify_artifact_payload()` compares
an already-read payload to its immutable manifest's digest and exact byte
length, returning deterministic `digest_mismatch` and/or
`byte_length_mismatch` evidence without retaining bytes or performing storage
I/O. Invalid payload types fail fast; retrieval, atomic publication, retention,
and worker/storage ownership remain deferred.

The exact implementation tree passed all 104 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Static source preflight remains an early
rejection layer rather than the runtime security boundary. Persistence, API,
worker, artifact-store, Compose, Nautilus, frontend, integration, promotion,
and deployment paths remain unchanged.

## 2026-09-16 - Artifact publication-plan checkpoint

`artifact_publication.py` adds a storage-neutral publication decision that can
only be produced from a verified `ArtifactIntegrityReceipt`. It requires
immutable create-if-absent semantics, reuses an already-present content
address without overwriting it, and exposes pin requirements from the manifest
retention class. It performs no storage I/O and does not claim atomicity until a
future adapter implements and tests that operation.

The exact implementation tree passed all 107 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Runtime artifact storage, retention
enforcement, persistence, API, worker, Compose, Nautilus, frontend,
integration, promotion, and deployment paths remain unchanged.

## 2026-09-16 - Result artifact integrity checkpoint

`result_integrity.py` adds a pure result-level verification contract for
successful `RunResultManifest` records. It requires one unique, verified
payload receipt for every referenced output artifact, reports missing,
unexpected, foreign, or unverified digests deterministically, and binds the
coverage result to the full manifest fingerprint. It performs no storage I/O
and does not certify engine semantics or publication atomicity.

The exact implementation tree passed all 107 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Execution-attempt lifecycle, persistence,
API, worker, artifact-store, Compose, Nautilus, frontend, integration,
promotion, and deployment paths remain unchanged.

## 2026-09-16 - Execution-attempt lease checkpoint

`lifecycle.py` now includes typed `ExecutionAttemptLease` records and
`acquire_attempt_lease()`. Leases can be acquired only by running attempts,
renew only while active with monotonic timestamps, and transition explicitly to
released or expired states. The pure contract supplies worker-side lease
evidence without persistence, scheduling, or automatic clock access; result
publication must still be guarded by a live lease in the future worker.

The exact implementation tree passed all 110 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Capability execution preflight, persistence,
API, worker, artifact-store, Compose, Nautilus, frontend, integration,
promotion, and deployment paths remain unchanged.

## 2026-09-16 - Engine capability-binding checkpoint

`execution_capabilities.py` adds a typed binding between the strict/degraded
data preflight and a registered engine build/conformance identity. Product,
execution-model, and account-model gaps fail closed; a non-authoritative engine
can provide compatibility evidence but cannot publish authoritative results.
The binding is engine-neutral and performs no runtime loading or execution.

The exact implementation tree passed all 113 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Forward-event/result-state handling,
persistence, API, worker, artifact-store, Compose, Nautilus, frontend,
integration, promotion, and deployment paths remain unchanged.

## 2026-09-16 - Forward event-state application checkpoint

`apply_forward_event_observation()` now applies classified canonical events to a
`ForwardInstance` without implicit replay or state loss. Contiguous accepted
events advance the stored event identity/sequence; gaps, duplicates, and
out-of-order events preserve the cursor; corrections increment an append-only
counter and retain the prior decision cursor. Event arrival timestamps remain
monotonic, and the function performs no persistence or external event I/O.

The exact implementation tree passed all 113 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Forward-state persistence/idempotency,
database/API, workers, artifact-store, Compose, Nautilus, frontend,
integration, promotion, and deployment paths remain unchanged.

## 2026-09-16 - Execution authorization-gate checkpoint

`execution.py` adds `authorize_execution()`, which composes accepted static
source validation, trial-bound capability evidence, matching running-attempt
identity, and an active worker lease into one immutable authorization record.
The gate fails closed on unsupported capability, mismatched trial/lease, bad
source, non-running attempts, expired leases, or non-monotonic timestamps. It
does not import or invoke an engine, access storage, or carry secrets.

The exact implementation tree passed all 116 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Forward-state persistence/idempotency,
database/API, workers, artifact-store, Compose, Nautilus, frontend,
integration, promotion, and deployment paths remain unchanged.

## 2026-09-16 - Forward checkpoint idempotency checkpoint

`forward_state.py` adds immutable, fingerprinted `ForwardStateCheckpoint`
records containing the `ForwardInstance`, processed/buffered/correction event
sets, and duplicate/out-of-order counters. `apply_checkpoint_observation()`
replays accepted, gap, and correction records idempotently, removes buffered
events only after contiguous acceptance, and never rewrites the decision
cursor for anomalies or corrections. It performs no persistence or event I/O.

The exact implementation tree passed all 120 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Worker dispatch/idempotency, database/API,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Worker dispatch idempotency checkpoint

`dispatch.py` adds immutable `DispatchRequest` and content-addressed
`DispatchEnvelope` records plus `resolve_idempotent_dispatch()`. Identical
idempotency keys replay the same attempt/payload/queue request; differing
payload or queue content returns an explicit conflict, and contradictory prior
records fail closed. The contract performs no Redis, outbox, or worker I/O;
atomic compare-and-set remains an adapter responsibility.

The exact implementation tree passed all 125 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Progress/cancellation, database/API,
workers, artifact-store, Compose, Nautilus, frontend, integration, promotion,
and deployment paths remain unchanged.

## 2026-09-16 - Progress and cancellation checkpoint

`progress.py` adds typed ordered worker progress updates, idempotent
`CancellationRequest` records, and `ExecutionProgressState`. Progress totals
and completed units are monotonic, terminal states cannot be updated, and a
requested cancellation can only finish with an explicit cancelled terminal
update. These are storage-neutral control semantics for future resumable
workers; Redis, database persistence, and process interruption remain open.

The exact implementation tree passed all 129 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Retry/recovery, database/API, worker,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Attempt recovery and retry checkpoint

`recovery.py` adds a storage-neutral `RetryPolicy` and
`plan_attempt_recovery()` decision contract. Recovery validates one contiguous
terminal attempt chain, distinguishes retry/no-op/terminal outcomes, allows
only explicitly retryable infrastructure causes, caps deterministic exponential
backoff, content-addresses the resulting plan for idempotent scheduling, and
fails closed on active attempts, malformed chains, stale
timestamps, cancellation retries, or exhausted limits. A retry plan can
materialize a queued `RunAttempt` against the same immutable scientific trial;
durable scheduling, compare-and-set, worker restart, and engine disposal remain
adapter responsibilities.

The exact implementation tree passed all 133 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API, durable worker recovery,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Canonical execution event-stream checkpoint

`events.py` adds content-addressed `ExecutionEvent` envelopes, typed
`EventStreamCursor` records, and `resolve_event_append()`. Exact prior events
are replayable; a new event must be the next contiguous sequence, while gaps,
stale sequences, foreign streams, and identity conflicts fail closed or return
an explicit decision. The contract is storage- and transport-neutral so future
PostgreSQL/outbox/Redis adapters can perform atomic compare-and-set without
altering trial identity or invoking an engine.

The exact implementation tree passed all 137 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - API cursor and typed-error checkpoint

`api_contracts.py` adds snapshot-bound `ApiCursor` tokens, consistent
`CursorPage` envelopes, and immutable `ApiError` values. Cursor tokens are
deterministic URL-safe JSON envelopes with a content checksum and strict field
validation; pages cannot claim continuation without a matching cursor, and
errors expose stable codes, HTTP status, retryability, request identity, and
frozen details. These are router/persistence-neutral boundary contracts; the
checksum is not an authorization mechanism.

The exact implementation tree passed all 142 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Asynchronous submission/idempotency checkpoint

`submissions.py` adds immutable `SubmissionRequest`, `SubmissionReceipt`, and
`SubmissionResolution` contracts. Request fingerprints bind operation, attempt,
idempotency key, and payload digest while excluding submission timestamps, so a
transport retry replays the same accepted request. Resolution distinguishes
202 acceptance/replay from 409 idempotency conflict and fails closed when prior
receipts disagree; durable compare-and-set and dispatch remain adapter work.

The exact implementation tree passed all 147 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Asynchronous outcome/idempotency checkpoint

`outcomes.py` adds ordered `OutcomeUpdate` and `ExecutionOutcome` values for
accepted, running, succeeded, failed, and cancelled execution states. Updates
are bound to the original submission and attempt; successful outcomes require
an immutable result digest, failures carry a typed API error, and exact repeats
replay while stale, foreign, regressive, or conflicting updates fail closed.
The state transition helper performs no persistence or engine I/O.

The exact implementation tree passed all 151 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Artifact lineage/idempotency checkpoint

`lineage.py` adds immutable `ArtifactLineageEntry` edges and owner-scoped
`ArtifactLineageIndex` records. Semantic keys bind owner, role, parent, and
manifest identity while excluding recording time; exact edges replay, changed
metadata returns an explicit conflict, duplicate semantic keys are rejected,
and index ordering/fingerprints are deterministic. Persistence adapters remain
responsible for manifest foreign keys and atomic writes.

The exact implementation tree passed all 155 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Runtime-isolation preflight checkpoint

`runtime.py` adds pinned `RuntimeIsolationProfile` and execution-request
contracts plus `preflight_runtime_isolation()`. The preflight requires a
content-addressed runtime image, exact dependency pins, disabled network and
secrets, read-only root, dropped capabilities, and positive resource limits;
requested network/filesystem/secret access or unvetted dependencies produce
explicit rejection evidence. No container is started and no OS enforcement is
claimed; those remain isolated worker/runtime adapter responsibilities.

The exact implementation tree passed all 159 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus, frontend, integration, promotion, and
deployment paths remain unchanged.

## 2026-09-16 - Engine conformance and authoritative-release checkpoint

`conformance.py` adds `EngineConformanceEvidence` and
`EngineConformanceReport` with explicit required checks for multi-instrument
accounting, native order/fill/cost behavior, deterministic replay, lifecycle,
and forward event-tape parity. Missing checks fail closed; a complete release
candidate is compatible evidence only, while `authoritative` is true only for
a complete stable release. No engine is imported or started by this contract.

The exact implementation tree passed all 163 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus runtime, frontend, integration, promotion,
and deployment paths remain unchanged.

## 2026-09-16 - Authoritative result-publication checkpoint

`result_publication.py` adds `plan_result_publication()`, composing stable
engine conformance, runtime isolation, exact result-manifest artifact coverage,
and engine-build identity. A valid plan publishes or replays an immutable
manifest; candidate/non-authoritative builds, mismatched evidence, failed
runtime isolation, and incomplete artifact receipts reject with explicit
reasons. No artifact store, database, queue, or engine is invoked.

The exact implementation tree passed all 166 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus runtime, frontend, integration, promotion,
and deployment paths remain unchanged.

## 2026-09-16 - Restart-safe progress checkpoint

`progress_checkpoint.py` adds `ProgressCheckpoint` and
`apply_progress_checkpoint()`. Applied progress update identities are retained
for exact replay; only the next contiguous sequence advances the state, while
gaps and stale/conflicting updates return explicit decisions without mutation.
Terminal and cancellation semantics continue to be enforced by the existing
progress state machine, and persistence/transport remain adapter-owned.

The exact implementation tree passed all 170 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. API routes, durable persistence, workers,
artifact-store, Compose, Nautilus runtime, frontend, integration, promotion,
and deployment paths remain unchanged.

## 2026-09-16 - Worker lifecycle and serial-capacity checkpoint

`workers.py` adds immutable `WorkerProfile`, `WorkerReservation`, and
`WorkerPoolState` records for separately typed backtest and forward workers.
Each process is constrained to one concurrent engine node and must declare
runtime isolation and engine disposal. `reserve_worker_slot()` returns explicit
accept/replay/saturated/reject decisions with content-addressed reservation
identities; `release_worker_slot()` is idempotent and deterministically reopens
capacity. Unsafe profiles, reused identities, foreign reservations, and invalid
timestamps fail closed. Scheduling, durable compare-and-set, heartbeats,
restart recovery, process interruption, and actual engine disposal remain
adapter-owned.

The exact implementation tree passed all 174 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is
artifact retention/pinning semantics; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Artifact retention and pinning checkpoint

`artifact_retention.py` adds immutable `ArtifactRetentionPin` and
`ArtifactRetentionState` records bound to the exact artifact manifest. Pin
creation and release have explicit add/replay/conflict and idempotent-release
semantics. `resolve_artifact_retention()` evaluates permanent, pinned, tiered,
and ephemeral classes at a caller-supplied timestamp: pinned classes fail
closed without an active pin, active pins override expiry, and tier/expiry
eligibility is observable without deleting or moving bytes. Pin identities and
state ordering are deterministic; foreign manifests and invalid deadlines are
rejected.

The exact implementation tree passed all 182 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
worker heartbeat/lease-observation contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Worker lease-observation checkpoint

`lease_observations.py` adds ordered `LeaseObservation` envelopes for worker
heartbeats and releases plus `LeaseObservationState` and
`apply_lease_observation()`. Per-lease sequences apply only contiguously; exact
observation retries replay, reused identities conflict, and gaps/stale records
return explicit non-mutating decisions. Heartbeats fail closed after expiry or
release, release is terminal and replay-safe, and state validates monotonic
timestamps plus lease/heartbeat identity. Durable compare-and-set, process
clocks, scheduling, and persistence remain adapter-owned.

The exact implementation tree passed all 190 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
forward warm-up/replay handoff contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Forward warm-up handoff checkpoint

`forward_warmup.py` adds immutable `ForwardWarmupReceipt` values and
`resolve_forward_warmup()`. Receipts bind the forward instance, frozen warm-up
snapshot, declared carry-in mode, completion timestamp, and engine-state
fingerprint. A receipt can complete only a `WARMING_UP` instance once and seeds
the historical cursor; an exact existing receipt replays without rewriting
live state. Snapshot/mode mismatches, stale completion, existing cursor
overwrite, invalid final sequence identity, and changed receipt content fail
closed. No engine, storage, or event transport is invoked.

The exact implementation tree passed all 198 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
forward live-event admission/replay contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Forward live-event admission checkpoint

`forward_admission.py` adds `ForwardLiveAdmissionState`, content-addressed
`ForwardSeenEvent` identities, and `admit_forward_event()`. Live admission is
allowed only for an active post-warm-up instance and seeds its checkpoint from
the exact warm-up receipt. Newly observed events are retained by identity so
exact retries replay and changed content conflicts; contiguous events advance,
gaps buffer and later reconcile, and duplicate/out-of-order/correction
outcomes remain observable without rewriting prior decisions.

The exact implementation tree passed all 204 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
result-artifact commit/finalization contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Result-artifact commit/finalization checkpoint

`artifact_commit.py` adds immutable `ArtifactCommitRecord` and
`ArtifactCommitLedger` records plus `finalize_artifact_commit()`. A verified
create-if-absent plan commits one content-addressed storage key; the same
manifest/content retries replay the committed record independent of timestamp.
Storage-key collisions with another manifest conflict, and a reuse-existing
plan fails closed until a committed record is present. Ledger ordering and
commit keys are deterministic; no bytes, storage metadata, or retention state
are mutated by the pure contract.

The exact implementation tree passed all 209 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
execution-summary/read-model contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Execution summary/read-model checkpoint

`execution_summary.py` adds `ExecutionSummary` and
`build_execution_summary()`, projecting a submission receipt, typed outcome,
progress checkpoint, and optional authoritative publication plan into one
immutable machine-facing view. Submission/attempt identities and
outcome/progress phases must agree; successful summaries require a published or
replayed result whose digest matches the outcome, while failed/cancelled
summaries require matching terminal progress and never expose a result. The
summary exposes ready/in-progress/terminal decisions and a deterministic
fingerprint without mutable engine handles.

The exact implementation tree passed all 217 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
retry/cancellation command contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Retry and cancellation command checkpoint

`commands.py` adds content-addressed `ExecutionCommand` intents,
`ExecutionCommandReceipt` records, and an idempotent command ledger. A cancel
command is accepted only for a non-terminal execution, while a retry command
requires failed outcome and progress. Exact command retries replay, changed
content conflicts, terminal/non-failed preconditions and identity mismatches
reject, and accepted receipts describe a requested effect without claiming
that cancellation, scheduling, or worker interruption has occurred.

The exact implementation tree passed all 224 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
capability/report projection contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Capability/report projection checkpoint

`capability_summary.py` adds `CapabilitySummary` and
`build_capability_summary()`, composing the existing data `PreflightReport`
with `ExecutionCapabilityPreflight`. Instrument-scoped data gaps and engine
model gaps remain separate, degradation evidence is retained, and executable,
ranking-eligible, and authoritative-publication flags are derived only from
the underlying fail-closed decisions. Report identity mismatches reject before
projection; no providers or engines are invoked.

The exact implementation tree passed all 229 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
forward correction/replay command contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Forward counterfactual-replay checkpoint

`forward_corrections.py` adds `ForwardCorrectionCommand`,
`CounterfactualReplayPlan`, and `resolve_forward_correction()`. Only an
admitted correction event can produce a plan; the command binds the original
and correction identities, warm-up receipt, and an immutable pre-correction
checkpoint fingerprint. Exact existing plans replay, changed identities
conflict, and unadmitted, mismatched, or non-correction observations reject.
The live admission state is never rewritten and no replay engine is invoked.

The exact implementation tree passed all 235 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
execution-audit/event-journal contract; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Execution audit journal checkpoint

`audit.py` adds immutable aggregate-scoped `AuditEntry` and `AuditJournal`
records plus `append_audit_entry()`. Entries bind typed audit kinds, payload
digests, actor/correlation identity, timestamps, and contiguous sequence
numbers. Exact entries replay idempotently; missing sequence numbers produce a
gap, same-sequence content conflicts remain explicit, and foreign aggregates
or timestamp regressions reject without changing the journal. The contract is
storage/outbox neutral and does not claim that an audit record was durably
written or transported.

The exact implementation tree passed all 242 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable-adapter boundary for this journal; preserve all shared-path and
execution-authorization gates.

## 2026-09-16 - Transactional outbox checkpoint

`outbox.py` adds immutable `OutboxMessage` and `OutboxState` records plus pure
enqueue and acknowledgement resolutions. Request identities conflict when
their semantic payload changes, identical content deduplicates even across
request retries, pending messages have deterministic availability ordering,
and publish acknowledgements are idempotent. Scheduling timestamps are retained
in the record but excluded from content identity. Unknown acknowledgements and
invalid state are rejected without mutation; PostgreSQL transactionality and
Redis transport remain future adapter responsibilities.

The exact implementation tree passed all 250 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable-adapter boundary over the journal/outbox contracts; preserve all
shared-path and execution-authorization gates.

## 2026-09-16 - Atomic audit/outbox staging checkpoint

`audit_outbox.py` adds `stage_audit_outbox()`, linking one audit entry to its
content-addressed outbox envelope. The event identity must match exactly;
append/enqueue gaps, conflicts, and rejects return the original journal and
outbox states so a future database adapter cannot commit only one side. Safe
append/enqueue combinations produce a single pair of states for one database
transaction, and exact retries replay without mutation. No persistence,
transport, or delivery claim is made here.

The exact implementation tree passed all 256 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable adapter implementation only after upstream shared-path reconciliation;
preserve all execution-authorization and ownership gates.

## 2026-09-16 - Legacy preservation/import checkpoint

`legacy.py` adds digest-only `LegacyRecord` preservation, explicit import
requests, adapter-supplied compatibility assessments, an immutable import
registry, and `LegacyImportReport` results. Supported definitions/results retain
the original record and expose a converted identity; unsupported records remain
inspectable with explicit notes. Exact retries replay, changed payload or
mapping content conflicts, preservation cannot be disabled, and reports reject
any replay-equivalence claim. The contract never replays legacy strategies or
reads legacy storage.

The exact implementation tree passed all 263 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable adapter implementation only after upstream shared-path reconciliation;
preserve all execution-authorization and ownership gates.

## 2026-09-16 - Resumable search-candidate checkpoint

`search_state.py` adds immutable `SearchCandidateState` and
`SearchExecutionState` records plus start, terminal-receipt, and cancellation
resolutions. Candidate scientific trial identities remain fixed while failed
infrastructure attempts can retry with incremented attempt lineage. Active
attempt and terminal-receipt conflicts reject, exact repeats replay, and
monotonic timestamps are enforced. Cancellation is idempotent, blocks new
starts, and requires workers to publish explicit cancelled receipts; it does
not rank candidates or issue profitability claims.

The exact implementation tree passed all 270 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable adapter implementation only after upstream shared-path reconciliation;
preserve all execution-authorization and ownership gates.

## 2026-09-16 - Coverage attestation verification checkpoint

`coverage.py` adds immutable `CoverageAttestation` and
`CoverageVerificationReport` records plus `verify_coverage_attestation()`.
Provider-adapter claims are compared against every frozen series identity:
evidence/content digests, instrument and event semantics, interval, row count,
session/feed, adjustment and corporate-action policy, completeness, and gap
status. Any mismatch or incomplete/gapped claim rejects with stable reasons;
matching evidence verifies deterministically. No provider, repair, calendar, or
execution I/O is performed, and a report is not an execution authorization by
itself.

The exact implementation tree passed all 288 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
strategy-runtime contract only within the package-owned boundary; preserve all
execution-authorization and ownership gates.

## 2026-09-16 - Strategy-runtime request/receipt checkpoint

`runtime_execution.py` adds immutable `StrategyRuntimeRequest`,
`StrategyRuntimePreflight`, `RuntimeExecutionState`, and ordered update
receipts. Requests bind package/source/input digests, declared entrypoint,
attempt, and isolation profile; preflight reuses the fail-closed isolation
report and rejects profile identity drift. Runtime states require an allowed
preflight, replay exact updates, reject sequence/time/identity conflicts, and
enforce the output-byte budget before a success can be recorded. This is an
engine-neutral protocol only: container limits, process lifecycle, and engine
execution remain future isolated-worker adapter responsibilities.

The exact implementation tree passed all 295 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable adapter implementation only after upstream shared-path reconciliation;
preserve all execution-authorization and ownership gates.

## 2026-09-16 - Conformance fixture evidence checkpoint

`conformance_fixtures.py` adds typed expected/observed digest observations and a
deterministically ordered fixture suite for all required engine checks. Passed
checks require matching identities, failed checks require differing identities,
duplicate/partial suites fail closed, and complete suites build the existing
`EngineConformanceEvidence` with a suite-bound fingerprint. This strengthens the
Nautilus stable-release gate without importing, starting, or enabling an engine.

The exact implementation tree passed all 301 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is a
durable adapter implementation only after upstream shared-path reconciliation;
preserve all execution-authorization and ownership gates.

## 2026-09-16 - Execution admission checkpoint

`admission.py` adds an immutable admission intent, receipt, ledger, and
resolution that compose the existing execution authorization, accepted strategy
runtime preflight, and serial worker-capacity contracts. An admission binds one
attempt to one worker profile and reservation, preserves authoritative-result
eligibility, and returns ledger/pool states together for an adapter-side atomic
write. Exact retries replay only when the matching reservation remains active;
capacity saturation, profile or worker drift, conflicting attempt content, an
unaccepted runtime, and a reservation without a receipt fail closed. No queue,
persistence, process, or engine I/O is performed.

The exact implementation tree passed all 306 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic search-dispatch checkpoint

`search_dispatch.py` adds a storage-neutral composition of candidate start,
execution admission, serial worker capacity, and dispatch idempotency. The
resolution returns the original search, admission, and worker states whenever a
later gate rejects, saturates, or conflicts, so adapters cannot persist an
orphaned running candidate or worker reservation. Exact retries replay all
three layers; a newly admitted attempt cannot reuse an existing queue message
without an admission receipt. Queue/database publication remains outside this
package.

The exact implementation tree passed all 310 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Worker recovery checkpoint

`worker_recovery.py` adds a pure composition of admission evidence, lease
identity/status, serial worker reservation release, and the existing bounded
retry planner. Crash, expiry, transient, and artifact-publication failures
release the worker slot and can materialize a new queued attempt linked to the
same scientific trial. Successful attempts become no-ops; cancellation and
exhausted/non-retryable failures become terminal without retry. Missing
admission/worker evidence, invalid lease-expiry claims, and absent retry
identities fail closed. Attempt persistence, scheduling, and engine lifecycle
remain adapter responsibilities.

The exact implementation tree passed all 314 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic result-completion checkpoint

`result_completion.py` adds terminal completion evidence for a backtest attempt
and its output artifacts. It requires successful runtime, outcome, and complete
progress states plus an accepted publication plan; it then resolves every
content-addressed artifact commit against a working ledger while returning the
original ledger on any conflict or rejection. Completion receipts bind the
attempt, result, runtime/outcome/progress identities, publication, and commit
keys; exact retries replay only when all referenced commits are still present,
and publication replay without a completion receipt fails closed. No bytes,
database rows, queues, processes, or engines are touched.

The exact implementation tree passed all 318 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic forward-event transaction checkpoint

`forward_event_transaction.py` adds an all-or-nothing live-event boundary over
the existing forward admission and counterfactual-correction contracts.
Accepted, gap, duplicate, and out-of-order events retain their explicit
decisions. A correction event requires a matching replay command and a
content-addressed replay plan; command/event conflicts, missing evidence, and
invalid non-correction replay input return the original live checkpoint. Exact
correction retries replay the plan without incrementing correction state again.
This remains broker-free and storage/engine neutral.

The exact implementation tree passed all 323 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Forward event dispatch checkpoint

`forward_event_dispatch.py` composes the forward event/correction transaction
with content-bound worker dispatch. Accepted events and buffered gaps enqueue
worker envelopes; duplicates and out-of-order observations remain
non-dispatching. Correction envelopes bind the separately identified replay
plan, and payload drift or queue idempotency conflicts return the original live
checkpoint rather than publishing an orphaned message. Exact retries replay the
dispatch evidence. Queue transport and persistence remain adapter-owned.

The exact implementation tree passed all 327 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic execution-event transaction checkpoint

`execution_event_transaction.py` links canonical execution-event append
resolution with the append-only audit journal and transactional outbox. The
contract enforces event-to-audit correlation and audit-to-outbox identity,
returns the original cursor/journal/outbox on any gap, conflict, or rejection,
and exposes exact all-stream replay only when every linked record is already
present. It remains an immutable adapter boundary: compare-and-set persistence,
outbox transport, worker entrypoints, and engine execution are not performed.

The exact implementation tree passed all 334 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Typed API resource envelope checkpoint

`api_resources.py` adds immutable public resource identifiers/documents and
snapshot-bound collection envelopes over the existing cursor and typed-error
contracts. Resource types, item identities, relationship targets, opaque
cursor resource, and snapshot digest must agree; mutable JSON fields are
recursively frozen and every envelope has a deterministic content identity.
The module remains route- and persistence-neutral, so no shared router or
frontend path was modified.

The exact implementation tree passed all 339 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Compare-and-set storage contract checkpoint

`storage.py` adds the persistence-facing boundary for versioned aggregate
snapshots. Mutations carry create or compare-and-set preconditions, transaction
requests are content-addressed and deterministically ordered, and receipts make
retries idempotent. Missing aggregates, version/state drift, create collisions,
and contradictory historical receipts fail closed while preserving the
original aggregate set. A future PostgreSQL adapter can map this plan to one
transaction; no database, Redis, or filesystem I/O occurs here.

The exact implementation tree passed all 346 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, artifact-store, Compose, Nautilus runtime, frontend, integration,
promotion, and deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Local content-addressed artifact store checkpoint

`artifact_store.py` adds the local filesystem adapter for immutable raw-byte
artifacts. It verifies the requested manifest before writing, publishes through
same-directory temporary files and atomic hard-links without replacing an
existing digest, deduplicates races, sets published files read-only, and
re-verifies bytes on every read. Corrupt, non-regular, symlinked, or escaping
paths fail closed; manifest/commit metadata remains the responsibility of the
existing pure contracts.

The exact implementation tree passed all 352 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Hardened sandbox command-plan checkpoint

`sandbox.py` adds the worker-facing Docker invocation plan after the existing
runtime isolation preflight. It pins the image digest and emits argv without a
shell, disables networking, makes the root read-only, drops all capabilities,
blocks privilege escalation and secrets, runs unprivileged, mounts input
read-only, and applies memory/CPU/file/PID/output limits. Host timeout handling
and process execution remain explicit adapter responsibilities; no container is
started by this module.

The exact implementation tree passed all 356 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Bounded sandbox execution adapter checkpoint

`sandbox_execution.py` closes the worker-side process boundary after sandbox
command planning. It executes only argv with `shell=False`, starts a separate
process group, passes a minimal environment without inherited secrets, caps
captured stdout/stderr, kills the group on output overflow or wall timeout, and
returns typed content-addressed run evidence for success, failure, timeout,
overflow, or start errors. Docker invocation and engine lifecycle remain
adapter-owned; no Nautilus process is started by the tests.

The exact implementation tree passed all 361 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Nautilus execution-gating checkpoint

`engine_execution.py` adds the final pre-invocation gate for the authoritative
simulator. It binds execution authorization, accepted runtime isolation,
content-matched sandbox argv, data-snapshot identity, and complete engine
conformance evidence. Non-Nautilus engines, failed/incomplete conformance,
runtime or sandbox drift, and non-authoritative stable-release attempts fail
closed; compatible release candidates may run only when explicitly requested as
non-authoritative. The contract does not start an engine.

The exact implementation tree passed all 366 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic Redis dispatch transport checkpoint

`redis_transport.py` adds the transport-side Redis Streams adapter for dispatch
envelopes. A Lua compare-and-set script binds each idempotency key to the exact
envelope content and appends one stream entry atomically; retries replay,
changed content conflicts, and failed stream writes roll back their marker.
Redis carries transport evidence only—the authoritative outbox and aggregate
state remain PostgreSQL adapter responsibilities.

The exact implementation tree passed all 372 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Redis consumer-group transport checkpoint

`redis_transport.py` now completes the Redis-side worker transport contract
around the atomic publisher. Consumer groups are created idempotently (including
`BUSYGROUP` replay), new entries are decoded into typed content-addressed
records, idle pending entries can be reclaimed after restart or lease expiry,
and acknowledgements return typed success/failure evidence. Redis remains
transport-only; PostgreSQL persistence and the transactional outbox remain the
authoritative state boundary.

The exact implementation tree passed all 375 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Outbox-to-Redis relay checkpoint

`outbox_relay.py` binds the authoritative outbox contract to the Redis Streams
publisher. It derives a deterministic transport envelope from an outbox
message's semantic identity, publishes through the existing atomic enqueue
adapter, and proposes the outbox `published_message_ids` update only after an
enqueue or exact replay. If Redis rejects or conflicts, the original pending
outbox state is returned unchanged; if a worker crashes after Redis publication
but before the database compare-and-set, the next relay observes a replay and
can safely stage the acknowledgement.

The exact implementation tree passed all 383 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Bounded Redis worker-pump checkpoint

`worker_consumer.py` adds the bounded consumer-side orchestration around the
Redis group/relay contracts. Each poll ensures the group, reclaims idle pending
entries before reading new work, and caps the batch. Each handler must return a
content-matched receipt; only a completed receipt is acknowledged. Retry,
rejection, handler-content drift, and acknowledgement failures preserve the
pending delivery and return typed evidence, leaving authoritative state and
isolated engine execution to the handler/worker adapter.

The exact implementation tree passed all 389 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - PostgreSQL compare-and-set adapter checkpoint

`postgres_storage.py` maps the package-owned aggregate transaction contract to
one SQLAlchemy async transaction. It locks requested aggregate and receipt rows,
round-trips canonical state (including tuples and `None`) without changing its
content identity, uses guarded inserts/updates and idempotent receipts, and
rolls back when a concurrent write wins. The module exposes the future additive
schema contract but never creates tables or registers shared ORM models; schema
migrations and application wiring remain explicitly deferred gates.

The exact implementation tree passed all 394 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Gated Nautilus runner checkpoint

`nautilus_runner.py` closes the process handoff after `plan_nautilus_execution`
and before a future isolated Nautilus worker. It refuses rejected plans,
non-Nautilus identities, and sandbox-plan drift without spawning; ready plans
delegate exclusively to the bounded sandbox adapter. Sandbox success/failure,
timeouts, output limits, and start errors remain content-bound, and the
authoritative flag is preserved only for a successful plan already cleared by
the stable-conformance gate.

The exact implementation tree passed all 399 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Runtime-result materialization checkpoint

`runtime_result_adapter.py` materializes one bounded sandbox terminal result into
the existing monotonic runtime state. It verifies command-plan and runtime-
request identity, records bounded stdout digest/size for success or typed error
identity for failure, transitions through running to terminal state, replays
exact terminal evidence, and rejects conflicting terminal evidence. This
remains runtime evidence only; official result artifacts still require result
publication gates.

The exact implementation tree passed all 403 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Execution-handoff orchestration checkpoint

`execution_orchestration.py` binds authorization, worker admission, runtime
preflight/state, sandbox planning, and the gated Nautilus plan into one
immutable worker handoff. The plan verifies every cross-contract identity,
requires an accepted sequence-zero runtime state, keeps the declared output
limit unchanged, and preserves authoritative eligibility only when admission
and the engine gate agree. Identity drift, an already-started runtime,
unauthorized authority, and rejected engine plans fail closed before a process
or queue adapter is invoked.

The exact implementation tree passed all 407 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Nautilus-result runtime bridge checkpoint

`runtime_result_adapter.py` now accepts an executed `NautilusRunResult` only
after verifying the execution-plan and sandbox-plan identities, matching the
runner and sandbox statuses, and checking the authoritative flag against the
gated plan. Rejected pre-process Nautilus plans are refused without a synthetic
runtime failure; executed evidence then follows the existing bounded,
idempotent sandbox-to-runtime materialization path.

The exact implementation tree passed all 409 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Engine-result materialization checkpoint

`result_materialization.py` adds an engine-neutral result adapter that binds
typed engine evidence to the immutable `RunResultManifest` required by the
publication and completion gates. It verifies trial/attempt, metric, snapshot,
strategy-package, and output-artifact identities, preserves engine/build and
dependency provenance, replays an exact existing manifest, and conflicts on
changed content. It performs no artifact writes or publication and does not
claim engine authority by itself.

The exact implementation tree passed all 413 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Canonical result-evidence ordering checkpoint

Result materialization now canonicalizes strategy-package and output-artifact
ordering before provenance comparison, matching the manifest's deterministic
ordering. A regression test confirms artifact evidence is order-independent
while preserving content identity and conflict detection.

The exact implementation tree passed all 414 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Terminal outcome/progress materialization checkpoint

`execution_terminal.py` projects one terminal `RuntimeExecutionState` into the
public `ExecutionOutcome` and `ExecutionProgressState` streams as an atomic
storage-neutral proposal. Successful runtimes require an attempt-bound
`RunResultManifest`; failures require a typed `ApiError`; cancellation requires
the persisted cancellation request. Matching terminal evidence replays without
rewriting state, while half-terminal, contradictory, stale, or cross-attempt
records fail closed.

The exact implementation tree passed all 418 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Worker-handoff execution checkpoint

`worker_execution.py` composes the immutable execution handoff with the gated
Nautilus runner and runtime-result bridge. It revalidates every handoff
identity immediately before process creation, refuses stale or rejected plans
without spawning, and returns typed Nautilus plus runtime evidence for a future
compare-and-set transaction. Process failures become runtime failures; no queue,
database, result publication, or engine bypass is introduced.

The exact implementation tree passed all 422 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice is an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Worker-capacity settlement checkpoint

`worker_settlement.py` closes one admitted worker reservation after a bounded
worker handoff. It binds the execution evidence to the admission and
orchestration plan, checks the worker profile and reservation identity, and
returns an immutable pool plus append-only settlement ledger proposal. Both
successful process results and pre-process handoff rejections release capacity,
while exact retries replay only when the reservation is already released with
matching evidence. Changed release evidence, a missing or mismatched
reservation, an active pool alongside an existing receipt, and release times
before acquisition are rejected without partial state changes.

The exact implementation tree passed all 426 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Active worker reservation launch gate checkpoint

`worker_execution.py` now requires the current `WorkerPoolState` at the process
boundary. Immediately before the gated Nautilus runner is invoked it verifies
the admission's worker id, kind, runtime profile, and active reservation, and
rejects released, missing, mismatched, or not-yet-acquired capacity without
spawning a process. This keeps serial capacity a launch-time invariant rather
than relying only on an earlier admission receipt; settlement remains the
storage-neutral release path after the handoff completes.

The exact implementation tree passed all 427 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

The worker resolution contract also now rejects a contradictory terminal
decision/runtime-result pair, so a forged success/failure label cannot reach
capacity settlement or later result publication.

## 2026-09-16 - Atomic lease-release settlement checkpoint

Worker settlement now also applies a deterministic ordered
`LeaseObservationKind.RELEASE` to the supplied `LeaseObservationState` and
returns that state alongside the released pool and settlement ledger. Exact
retries require both the pool reservation and lease observation to be already
released with matching evidence. Expired or already-released leases are
rejected and left for the existing recovery path, preventing a late process
from presenting itself as an authoritative normal completion.

The exact implementation tree passed all 428 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Launch-time lease gate checkpoint

`execute_worker_handoff` now accepts an explicit start instant and
`LeaseObservationState`. It verifies the lease is active at process creation,
rejects observations that precede the start, and refuses to materialize process
evidence after lease expiry; late results retain process evidence for explicit
recovery instead of becoming normal runtime success/failure. Worker pool,
reservation, and lease identities remain checked together immediately before
the runner call.

The exact implementation tree passed all 429 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Lease-expiry completion rejection checkpoint

When a bounded Nautilus process returns after its lease has expired,
`execute_worker_handoff` preserves the process evidence but returns a typed
rejection without materializing runtime state. This keeps late output available
to the explicit crash/expiry recovery path while preventing an expired lease
from publishing normal success or failure. Launch-time and completion-time
lease checks are both exercised without starting any process for stale launch
inputs.

The exact implementation tree passed all 430 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic worker-terminal settlement checkpoint

`worker_terminal.py` composes terminal outcome/progress materialization with
worker pool and lease settlement. It returns one committed storage-neutral
proposal only when both sides accept, preserving every original state when a
result is missing, a lease has expired, capacity conflicts, or the handoff has
no runtime terminal evidence. Exact retries replay only when the terminal
public states and worker settlement receipts both match; pre-process worker
rejections remain owned by recovery.

The exact implementation tree passed all 433 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Lease-aware idempotent recovery checkpoint

The recovery ledger now binds an ordered lease-release observation as well as
the worker reservation release. Recovery returns the updated lease state, so
crash, expiry, transient, cancellation, and successful/no-op paths cannot leave
capacity and lease records split. Exact retries replay against the released
pool and matching observation; changed recovery content or an active/missing
lease observation is rejected. Expired leases remain eligible only for the
explicit recovery reason and never become normal successful completions.

The exact implementation tree passed all 428 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Idempotent recovery ledger checkpoint

`worker_recovery.py` now accepts an append-only `WorkerRecoveryLedger` and
records the recovery plan, reservation release, retry identity, and observation
time as one content-addressed receipt. An exact repeated crash/expiry/transient
resolution replays the existing released pool and queued retry; changed plan,
reason, retry identity, or release evidence returns a conflict, and a receipt
cannot replay against a still-active pool reservation. Recovery remains
infrastructure-only and never transitions attempts, schedules queues, or starts
an engine.

The exact implementation tree passed all 428 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Worker-terminal release ordering checkpoint

`materialize_worker_terminal` now rejects a first-time worker release whose
timestamp precedes terminal evidence, preventing capacity and lease state from
appearing released before process completion was observed. Existing terminal
and settlement receipts remain replayable when a later retry arrives, while
changed release evidence still follows the settlement conflict path.

The exact implementation tree passed all 434 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Atomic submission-dispatch staging checkpoint

`submission_dispatch.py` now composes asynchronous submission idempotency with
the matching worker dispatch envelope. It requires the same attempt,
idempotency key, and payload identity on both sides; a receipt retry can repair
a dispatch lost after receipt persistence, while a dispatch without a tracked
submission is rejected. The immutable receipt ledger and dispatch proposal are
returned together for one future compare-and-set transaction; no route, queue,
or database I/O is performed by the package contract.

The exact implementation tree passed all 439 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Snapshot coverage verification checkpoint

`snapshot_coverage.py` now composes per-series coverage attestation checks into
one snapshot-bound admission result. It requires exactly one attestation for
each frozen series, rejects missing, duplicate, unexpected, incomplete, or
semantically mismatched evidence, and preserves deterministic report and
attestation identities. Provider acquisition and execution adapters still own
fetching the evidence and enforcing this receipt before a run starts.

The exact implementation tree passed all 443 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral orchestration contract within the package-owned boundary;
preserve the execution-admission and ownership gates.

## 2026-09-16 - Cash-equity order sizing and routing checkpoint

`order_routing.py` now accepts explicit `OrderIntent` values only after an
adapter supplies digest-bound instrument economics. It validates base/quote
currency, lot and tick alignment, minimum quantity, supported product risk
model, snapshot/economics identity, and declared component scope, then computes
an auditable estimated signed base notional. The pre-order exposure is combined
with all order deltas and passed through the shared all-or-nothing gross, net,
concentration, leverage, open-instrument, and short-position gate. A risk
breach withholds every routed order; approved values remain engine-neutral
estimates and never imply a fill or submit an order. Only the registered
cash-equity market-value model is supported; futures, options, FX, crypto, and
other product models remain explicitly rejected pending their own semantics.

The exact implementation tree passed all 451 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Registered product-risk valuation checkpoint

`contracts.py` now publishes exact content-addressed risk-model definitions for
cash equity, crypto spot, futures contract notional, option delta-adjusted
underlying notional, and FX pair notional. `risk_models.py` applies those
versioned formulas only to adapter-verified economics and emits a signed
base-notional receipt; option exposure explicitly binds underlying mark and
delta, while all formulas remain estimates rather than fills or margin/liquidity
claims. Allocation and order routing accept only these exact registered models
and the policy/snapshot binding must agree, so arbitrary digests and other
products still fail closed.

The exact implementation tree passed all 458 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Adapter-supplied margin-capacity gate checkpoint

`margin_risk.py` now layers a deterministic margin gate over a routed order
decision. An adapter supplies event-aligned initial/maintenance requirements and
capacities with a valuation-evidence digest; the contract computes both
utilization ratios, records capacity and policy breaches, and withholds every
order when the upstream order-risk or margin gate fails. Snapshot, portfolio,
event, and policy identities must match exactly. The gate deliberately does not
infer margin from notional exposure and does not issue a solvency, liquidity, or
profitability verdict.

The exact implementation tree passed all 463 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Descriptive result-ranking checkpoint

`ranking.py` now provides a deterministic analysis view over completed
`RunResultManifest` values. It anchors one experiment and compatible snapshot,
portfolio, engine, allocation, metric-set, unit, and structured calculation
context; ties use immutable trial identities. Degraded preflight results remain
excluded by default, and missing, null, unversioned, incompatible, and duplicate
scientific-trial results are retained as explicit exclusions. The output is a
descriptive ordering only and makes no profitability, significance, or paired-
inference claim.

The exact implementation tree passed all 468 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Adapter-supplied stress-risk gate checkpoint

`stress_risk.py` now layers an explicit stressed-equity gate over the margin and
order-routing decisions. Each scenario binds a shock-definition digest,
base/stressed equity values, and valuation evidence at the same event boundary;
loss-fraction and minimum-equity ceilings are evaluated deterministically, and
any breach withholds every routed order. Upstream margin/order rejection is
preserved without fabricating stress evidence. Shock construction, liquidity,
settlement, and solvency/profitability verdicts remain outside this contract.

The exact implementation tree passed all 473 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Adapter-supplied liquidity gate checkpoint

`liquidity_risk.py` now layers an explicit liquidity gate over stress, margin,
and order routing. Each instrument capacity binds available quantity, available
base notional, estimated slippage, and valuation evidence. The gate aggregates
the full routed batch per instrument, rejects missing capacity, and withholds
every order on participation or slippage breaches while preserving upstream
rejections. It does not infer volume, construct fills, or promise execution
quality.

The exact implementation tree passed all 478 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Adapter-supplied settlement-cash gate checkpoint

`settlement_risk.py` now layers an explicit settlement gate over liquidity,
stress, margin, and order routing. Adapters bind each exact routed order to a
signed settlement cash delta, currency, settlement time, and valuation evidence,
alongside per-currency free-cash capacity. The gate withholds the complete
batch on missing estimates/capacity, gross debit exhaustion, or a configured
minimum remaining-cash buffer while preserving upstream rejection. It does not
infer product cash flows, conversions, or settlement behavior.

The exact implementation tree passed all 484 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Deterministic shock-definition checkpoint

`shock_construction.py` now expands caller-supplied typed shock dimensions into
stable Cartesian-product definitions. Every scenario and leg is immutable and
content-addressed, duplicate or ambiguous dimensions are rejected, and matrix
size is bounded explicitly. The package does not apply shocks to prices or
positions, infer cross-asset effects, or calculate stressed equity; adapters
must use these identities when producing stress observations.

The exact implementation tree passed all 489 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Composed pre-engine risk-admission checkpoint

`risk_pipeline.py` now evaluates the fixed routing, margin, stress, liquidity,
and settlement sequence and verifies each decision's content-addressed parent.
The resulting immutable `TradeRiskAdmission` exposes every layer for audit but
only releases the complete routed batch when all gates approve; no partial order
approval, engine submission, or fill claim is possible.

The exact implementation tree passed all 493 Strategy Lab v2 package tests,
Ruff, MyPy, and `git diff --check`. Database/API routes, durable worker
entrypoints, Compose, Nautilus runtime, frontend, integration, promotion, and
deployment paths remain unchanged. The next bounded slice remains an
engine-neutral contract within the package-owned boundary; preserve the
execution-admission and ownership gates.

## 2026-09-16 - Combined backend coverage audit

`make test-backend-coverage` completed all 1,647 unit/integration tests, but the
repository's required 75% combined coverage gate failed at 58.77%. The new
`app/strategy_lab_v2` tests are deliberately kept in their package-owned test
tree and are not collected by the existing `tests/unit` plus `tests/integration`
target, so the v2 package is reported as uncovered by that command. This is a
real shared-gate reconciliation item; no coverage exclusion or product-code
change was made to conceal it. The focused v2 evidence remains 493 passing tests
with Ruff, MyPy, and diff checks green.

The next implementation context must reconcile how package-owned v2 tests enter
the full backend coverage gate without violating provider/ETF/TC2000 ownership
or changing the required coverage meaning. Until then, the branch remains
ready-for-human-review only, not full-integration green.

## 2026-09-16 - Combined backend coverage gate reconciled

The shared `Makefile` `test-backend-coverage` target now includes the
package-owned `app/strategy_lab_v2/tests` path alongside `tests/unit` and
`tests/integration`. This is a collection-only change: it preserves the
repository's 75% threshold, adds no exclusions, and leaves provider/ETF/TC2000
test ownership unchanged.

The exact target completed 2,140 tests with 86 warnings and total coverage of
82.98%, exceeding the required 75% gate. Docker-backed setup and cleanup both
completed successfully. Focused package tests, Ruff, MyPy, and diff checks remain
green. This closes the collection gap but does not claim full integration:
schema/API/worker/Compose wiring, stable Nautilus activation, upstream
reconciliation, frontend work, promotion, and deployment remain deferred.

The next bounded slice remains inside the engine-neutral package-owned boundary;
the Makefile change is shared-path material that must be reconciled line by line
when this branch enters staging.

## 2026-09-16 - Branch-declared test runner repaired

The workstream `branch_tests` entries were previously prose descriptions, but
`scripts/run-branch-tests.py` executes each entry as a shell command. That made
the branch CI test stage fail before reaching any Strategy Lab checks. The plan
now declares only executable checks for the implemented scope: the 493-test v2
package suite, Ruff, MyPy, `git diff --check`, and workstream validation. The
deferred database/migration, API, worker, Nautilus, Compose, and full exact-tip
integration requirements remain documented as gates rather than pretending to
be runnable branch commands.

`make branch-tests INTEGRATION_BRANCH=feat/strategy-lab-v2` now passes all five
checks. This repair changes only the branch-owned plan metadata; no provider,
ETF, TC2000, or runtime source paths were modified.

## 2026-09-16 - Engine-neutral core review boundary

The package-owned implementation context is green and the workstream is now
`ready_for_human_review`. The branch contains the immutable engine-neutral
domain/SDK, deterministic search and walk-forward contracts, provenance-bound
metrics and artifacts, forward-state semantics, execution isolation/admission,
worker/retry/outbox contracts, and the composed pre-engine risk pipeline. The
combined backend coverage and executable branch-test gates are green at the
exact synchronized tip.

This status is a review boundary, not a claim that the production backend is
complete. Additive schema/API registration, provider acquisition wiring,
durable worker entrypoints, Compose services, isolated runtime deployment, and
stable Nautilus v2 execution remain open. They must begin only after the
provider-platform, ETF, and TC2000 branches reach staging and their shared
paths are reconciled line by line.

## 2026-09-16 - Provider-neutral acquisition handoff checkpoint

`data_acquisition.py` now defines the package-owned handoff between a typed
capability preflight and a provider-produced frozen snapshot. A receipt binds
the request, snapshot IDs/fingerprint, snapshot-level coverage verification,
opaque provider evidence, and acquisition time. Verification fails closed on
unsupported preflight, preflight/snapshot drift, incomplete or misaligned
coverage, receipt identity drift, and stale acquisition evidence, returning
stable reason codes without performing I/O or mutating any input.

The exact package tree passed 503 focused Strategy Lab v2 tests, Ruff, MyPy,
and `git diff --check`. This remains an engine-neutral adapter boundary: the
provider-platform branch still owns data fetching, repair, and evidence
retrieval, while schema migrations, application/API wiring, workers, Compose,
stable Nautilus execution, frontend integration, promotion, and deployment stay
deferred behind their existing gates.

## 2026-09-16 - Acquisition checkpoint combined-gate evidence

The exact synchronized acquisition checkpoint passed all five executable branch
checks and the repository-wide Docker-backed coverage gate. The focused suite
now contains 503 passing tests; the combined backend suite completed 2,150
tests with 83.00% total coverage (required threshold: 75%), and Docker setup
and cleanup completed successfully. Ruff, MyPy, `git diff --check`, and
workstream validation also passed. No shared provider, ETF, TC2000, runtime,
migration, API, worker, Compose, or frontend path was changed.

## 2026-09-16 - Data-bound execution admission checkpoint

`execution_data_admission.py` now composes the verified acquisition handoff
with a scientific trial, frozen snapshot, and ready Nautilus execution plan.
It rejects unverified coverage, request/snapshot drift, trial or plan snapshot
drift, and non-ready engine plans before a worker can consume the plan. The
result is immutable, content-addressed evidence and does not start a process or
perform persistence/network I/O.

The exact package tree passed 509 focused Strategy Lab v2 tests, Ruff, MyPy,
and `git diff --check`. Provider fetching/repair, schema/API registration,
workers, Compose, stable Nautilus execution, frontend integration, promotion,
and deployment remain deferred behind the existing staging and release gates.

The exact data-bound execution checkpoint also passed the repository-wide
Docker-backed coverage gate: 2,156 tests completed with 83.02% total coverage
(required threshold: 75%), with Docker setup and cleanup successful. The branch
checks and workstream validation remain green.

## 2026-09-16 - Deterministic strategy wall-clock preflight checkpoint

Static strategy-source validation now rejects calls to `now`, `today`, and
`utcnow`, including aliased receivers, while continuing to allow typed datetime
values as declared inputs. The violation is content-addressed and deterministic;
this closes a replay-integrity loophole without treating static analysis as the
runtime sandbox boundary.

The exact package tree passed 510 focused Strategy Lab v2 tests, Ruff, MyPy,
and `git diff --check`. The subsequent Docker-backed combined coverage gate
completed successfully and reports 83.03% total coverage (required threshold:
75%), with the existing setup/cleanup path intact. Provider/API/database/worker/
Compose integration and stable Nautilus execution remain deferred behind the
existing gates.

## 2026-09-16 - Hardened sandbox argv execution checkpoint

`SandboxCommandPlan` values are now revalidated at the execution boundary,
not only when built by the convenience factory. The validator requires the
complete network-disabled, read-only, capability-dropped, unprivileged,
resource-bounded invocation shape, pinned image/input identities, and explicit
read-only input plus writable output mounts. A manually forged plan therefore
cannot introduce privileged Docker flags or bypass the declared output limit.

The focused isolation/worker regression set passed 35 tests, and the complete
Strategy Lab v2 package passed 511 tests with Ruff, MyPy, and `git diff --check`.
The Docker-backed combined gate then completed 2,158 tests with 83.02% total
coverage (required threshold: 75%), with setup and cleanup successful.
Schema/API/worker/Compose integration and stable Nautilus execution remain
deferred behind the existing gates.

## 2026-09-17 - Execution and audit event-time canonicalization checkpoint

`events.py` and `audit.py` now normalize every aware occurrence timestamp to
UTC at immutable-contract construction. This closes an identity/replay edge
case where the same instant arriving with a different offset compared unequal
to the already persisted record and could be reported as a content collision.
The append and journal monotonicity semantics remain unchanged; persistence,
outbox/Redis transport, and application wiring remain deferred behind the
existing shared-path gates.

Regression coverage verifies equality, content-address identity, and exact
replay for offset-equivalent execution and audit records. Focused validation
passed 13 tests, Ruff, and MyPy for the changed modules. The branch remains
`ready_for_human_review`; provider/API/database/worker/Compose integration,
stable Nautilus execution, frontend work, promotion, and deployment remain
deferred.

## 2026-09-17 - Restricted custom-metric boundary checkpoint

`custom_metrics.py` now provides a source-bound, process-local custom-metric
runner for result analysis. It accepts only recursively frozen finite Decimal
observations and canonical JSON parameters, validates source identity and
static restrictions, requires a finite Decimal scalar output, and emits a
versioned `MetricValue` with source/input evidence. Static violations, source
drift, malformed outputs, and runtime exceptions return typed rejection/failure
evidence without exception text. The containing worker still must use the
hardened no-network sandbox; container activation, persistence, and API wiring
remain deferred behind the existing shared-path gates.

The focused custom-metric suite passed 4 tests with Ruff and MyPy green. The
exact pushed tip passed the branch gate: 681 package tests, Ruff, MyPy across
237 source files, diff check, and workstream validation. The same tip then
passed the Docker-backed combined coverage gate: 2,328 tests with 83.68% total
coverage, above the required 75% threshold; setup and cleanup completed
successfully. The branch remains `ready_for_human_review`.

## 2026-09-17 - Custom-metric wire protocol and CLI checkpoint

`custom_metric_protocol.py` now provides a strict tagged-JSON request/result
boundary for isolated custom-metric workers. It preserves Decimal and other
typed values through the existing runtime codec, rejects duplicate fields and
non-finite JSON constants, binds source and definition identity, and verifies
the content-addressed result fingerprint. `custom_metric_runner.py` reads a
mounted request, runs the restricted metric boundary, and atomically publishes
the typed result with status-based exit codes; it does not start Docker or
weaken the containing no-network sandbox. Worker image activation, persistence,
API wiring, and scheduling remain deferred behind the existing shared-path
gates.

Focused protocol/CLI coverage passed 4 tests with Ruff and MyPy green. The
exact pushed tip passed the branch gate and combined coverage gate recorded
above; no worker image, persistence, API, or scheduling gate was opened.

## 2026-09-17 - Custom-metric entrypoint and export hardening checkpoint

Custom-metric definitions now reject non-string entrypoints explicitly and the
restricted loader resolves the declared dotted callable path instead of only
top-level names. The `strategy_runtime` package exposes its custom-metric wire
helpers lazily, preserving the earlier import-cycle fix while retaining a
convenient public API. Focused coverage passed 10 tests with Ruff and MyPy
green. The exact pushed tip passed the branch gate: 683 package tests, Ruff,
MyPy across 237 source files, diff check, and workstream validation. The same
tip passed the Docker-backed combined coverage gate: 2,330 tests with 83.68%
total coverage, above the required 75% threshold; setup and cleanup completed
successfully.

## 2026-09-17 - Custom-metric batch runtime checkpoint

Custom metrics now have an immutable `CustomMetricInvocation` record and an
ordered `run_custom_metrics()` batch primitive. Duplicate invocation identities
are rejected, inputs are frozen at the boundary, and each typed result retains
its own source/definition/input evidence. The strict wire protocol adds a
content-addressed batch request/result envelope, while the mounted-file CLI
supports `--batch` with all-or-nothing success status and atomic publication.
This is intended for exhaustive local metric sweeps; the containing no-network
worker and durable application scheduling remain deferred.

Focused batch coverage passed 13 tests with Ruff and MyPy green. The exact
pushed tip passed the branch gate: 686 package tests, Ruff, MyPy across 237
source files, diff check, and workstream validation. The same tip passed the
Docker-backed combined coverage gate: 2,333 tests with 83.69% total coverage,
above the required 75% threshold; setup and cleanup completed successfully.

## 2026-09-17 - Strict REST cursor decoding checkpoint

`ApiCursor.from_token()` now parses its base64 JSON envelope with duplicate-field
rejection and non-finite-number rejection before checksum and snapshot validation.
This keeps cursor identity deterministic under hostile or ambiguous transport
payloads while preserving the existing boundary that checksums are integrity
signals, not authorization. Route ownership and persistence integration remain
deferred behind the shared-path gates.

The focused API contract suite passed 6 tests with Ruff and MyPy green. The
exact pushed tip passed the branch gate: 687 package tests, Ruff, MyPy across
237 source files, diff check, and workstream validation. The same tip passed
the Docker-backed combined coverage gate: 2,334 tests with 83.69% total
coverage, above the required 75% threshold; setup and cleanup completed
successfully.

## 2026-09-17 - Strict REST JSON serialization checkpoint

The registration-neutral API serializer now emits date values as ISO strings,
normalizes aware timestamps to UTC, preserves finite floats and exact Decimal
values, and rejects non-finite or unsupported scalar values before a response
can be published. This prevents JSONResponse from silently accepting ambiguous
numeric values or leaking an application object representation; router
registration, authentication, and persistence remain deferred behind the
shared-path gates.

Focused REST serialization coverage passed 15 tests with Ruff and MyPy green.
The exact pushed tip passed the branch gate: 688 package tests, Ruff, MyPy across
237 source files, diff check, and workstream validation. The same tip passed the
Docker-backed combined coverage gate: 2,335 tests with 83.70% total coverage,
above the required 75% threshold; setup and cleanup completed successfully.

## 2026-09-17 - Strict REST request metadata checkpoint

The registration-neutral API boundary now rejects control characters in
`X-Request-ID` and `Idempotency-Key` values before they can reach response
headers, adapter calls, or durable idempotency fingerprints. Header values are
trimmed and bounded consistently across submissions and retry/cancellation
commands; authentication and persistence ownership remain unchanged.

Focused request-metadata coverage passed 10 tests with Ruff and MyPy green. The
exact pushed tip passed the branch gate: 689 package tests, Ruff, MyPy across
237 source files, diff check, and workstream validation. The same tip passed the
Docker-backed combined coverage gate: 2,336 tests with 83.70% total coverage,
above the required 75% threshold; setup and cleanup completed successfully.

## 2026-09-17 - Strict REST JSON request-body checkpoint

The POST routes now reparse raw request bytes with duplicate-object-field and
non-finite-constant rejection before FastAPI-normalized bodies reach strategy
validation, submission idempotency, or command dispatch. This preserves one
canonical request identity even when a transport parser would otherwise silently
collapse ambiguous JSON. Shared router registration, authentication, and
persistence remain deferred behind the existing gates.

Focused raw-body coverage passed 11 tests with Ruff and MyPy green. The exact
pushed tip passed the branch gate: 690 package tests, Ruff, MyPy across 237
source files, diff check, and workstream validation. The same tip passed the
Docker-backed combined coverage gate: 2,337 tests with 83.70% total coverage,
above the required 75% threshold; setup and cleanup completed successfully.

## 2026-09-17 - Snapshot-bound REST pagination checkpoint

Cursor-paginated collection responses now reject an adapter page whose visible
snapshot digest differs from the incoming cursor's snapshot. This prevents a
continuation token from silently traversing a different result set between
requests; the existing resource/type/request identity checks remain in force.
Persistence-backed reads and application registration remain deferred behind
the shared-path gates.

Focused pagination coverage passed 12 tests with Ruff and MyPy green. The exact
pushed tip passed the branch gate: 691 package tests, Ruff, MyPy across 237
source files, diff check, and workstream validation. The same tip passed the
Docker-backed combined coverage gate: 2,338 tests with 83.71% total coverage,
above the required 75% threshold; setup and cleanup completed successfully.

## 2026-09-17 - Combined backend coverage revalidation

The exact pushed checkpoint tip passed the Docker-backed combined coverage gate:
2,318 tests passed with 83.65% total coverage, above the required 75% threshold.
PostgreSQL/Redis setup and cleanup completed successfully, and the run produced
the combined coverage reports. This supersedes the earlier transient connection
refusal record; no product or shared-path integration gates were changed.

## 2026-09-17 - Artifact manifest and integrity hardening checkpoint

`ArtifactManifest` now rejects boolean/non-integer byte lengths and untyped
retention classes. `ArtifactIntegrityReceipt` validates all digest and length
fields, canonicalizes failure reasons, and rejects a forged receipt that claims
verification while observed bytes differ from the manifest. Publication and
local-store adapters therefore receive only typed, content-consistent evidence;
durable byte lifecycle, migrations, authorization, and application wiring
remain deferred behind the existing shared-path gates.

The focused artifact/core regression set passed 31 tests with Ruff and MyPy
green. The exact pushed tip then passed the Docker-backed combined coverage
gate: 2,320 tests with 83.66% total coverage, above the required 75% threshold;
setup and cleanup completed successfully. The branch remains
`ready_for_human_review`; provider/API/database/worker/Compose integration,
stable Nautilus execution, frontend work, promotion, and deployment remain
deferred.

## 2026-09-17 - SDK UTC event-time normalization checkpoint

`MarketEvent` and `StrategyContext` now normalize every aware event time to
UTC at construction while retaining strict rejection of naive datetimes. This
keeps direct SDK callers aligned with the runtime wire protocol: event/context
scope checks, frozen-tape replay, and content fingerprints all operate on one
canonical instant representation. The focused Strategy Lab package passed 666
tests with Ruff, MyPy, `git diff --check`, and workstream validation green.

The repository-level Docker-backed coverage attempt reached the integration
suite but could not start the configured PostgreSQL test service on port 52440;
it ended with 2,087 passed, 1 failed (a worker contract test that passes in
isolation), and 226 setup errors from connection refusal. The integration
environment failure is independent of this SDK change and Docker cleanup
completed. Provider/API/database/worker/Compose integration and stable Nautilus
execution remain deferred behind the existing ownership and release gates.

## 2026-09-17 - SDK manifest identity canonicalization checkpoint

`StrategySdkManifest` now canonicalizes data dependencies by dependency ID,
model dependencies by distribution/version/artifact identity, and each data
dependency's declared fields lexically. Equivalent declarations therefore
produce the same immutable manifest fingerprint regardless of caller input
ordering, while duplicate IDs/fields remain rejected. The complete Strategy
Lab v2 package passed 667 tests with Ruff, MyPy, `git diff --check`, and
workstream validation green. Worker image/entrypoint, application scheduling,
migrations, upstream reconciliation, and authoritative Nautilus execution
remain deferred behind the existing gates.

## 2026-09-17 - Scientific identity canonicalization checkpoint

`StrategyVersion` now validates and canonically orders exact dependency
artifacts. `ExperimentDefinition` now rejects duplicate strategy identities and
orders the strategy collection by fingerprint. Equivalent scientific
declarations therefore produce one stable identity before trial expansion,
seed derivation, and result provenance. The complete Strategy Lab v2 package
passed 668 tests with Ruff, MyPy, `git diff --check`, and workstream validation
green. Worker image/entrypoint, application scheduling, migrations, upstream
reconciliation, and authoritative Nautilus execution remain deferred behind
the existing gates.

## 2026-09-17 - Metric-set identity canonicalization checkpoint

`MetricSet` now requires typed `MetricValue` records, validates that every
value uses the declared metric-set definition version, and canonically orders
records by metric identity. Equivalent result payloads therefore produce the
same metric-set fingerprint regardless of calculation order, while duplicate
`(name, basis)` values remain rejected. The complete Strategy Lab v2 package
passed 669 tests with Ruff, MyPy, `git diff --check`, and workstream validation
green. Worker image/entrypoint, application scheduling, migrations, upstream
reconciliation, and authoritative Nautilus execution remain deferred behind
the existing gates.

## 2026-09-17 - Snapshot-bound event-tape/SDK binding checkpoint

`bind_event_tape()` now verifies that a frozen replay tape belongs to the exact
`DataSnapshot` and `StrategySdkManifest` it is about to drive. It checks the
snapshot's preflight decisions and explicit degradations, matches effective
series semantics and effective dependency intervals, requires declared
instruments and exact event fields, rejects missing/unsupported dependencies, and emits a
content-addressed `EventTapeBinding` with deterministic per-dependency counts.
The SDK's `build_strategy_context()` applies the same declared-history interval
boundary for direct callers, so a context cannot bypass replay scope merely by
avoiding the binder. This keeps provider acquisition, coverage attestation,
strategy execution, order routing, and fills behind their existing adapter/
runtime gates.

The focused event-tape suite and complete Strategy Lab v2 package passed 653
tests with Ruff, MyPy, `git diff --check`, and workstream validation green. The
Docker-backed combined coverage gate passed 2,300 tests with 83.60% total
coverage (required threshold: 75%); setup and cleanup completed successfully.
Provider/API/database/worker/Compose integration and stable Nautilus execution
remain deferred behind the existing shared-path and release gates.

## 2026-09-17 - Schedule-gated target allocation checkpoint

`rebalance_allocation.py` now composes the immutable calendar schedule with
the engine-neutral target allocator. It validates the portfolio policy,
calendar, trigger, misfire-policy, and canonical occurrence identities,
normalizes only typed strategy intents, and applies them through the existing
all-or-nothing allocation/risk checks only when the exposure snapshot is at the
exact scheduled UTC boundary. Events before the boundary return an explicit
`not_due` decision. Events after it return either `misfired` or `skipped`
according to the occurrence's declared policy; no later-event catch-up or
implicit fill assumption is possible. Each decision is content-addressed and
retains the allocation fingerprint chain when applied.

The focused rebalance-gate suite passed 7 tests; the full package suite passed
642 tests with Ruff, MyPy, `git diff --check`, and workstream validation green.
The combined Docker-backed coverage gate passed 2,289 tests with 83.57% total
coverage (required threshold: 75%); Docker setup and cleanup completed
successfully.
Provider/API/database/worker/Compose integration, stable Nautilus execution,
frontend work, promotion, and deployment remain deferred behind the existing
ownership and release gates.

## 2026-09-17 - Frozen deterministic event-tape checkpoint

`event_tape.py` now provides a content-addressed, snapshot-bound replay tape
for later backtest and forward adapters. It canonicalizes cross-series event
ordering, groups same-time events into stable batches, exposes explicit
non-interpolating boundary slices, rejects duplicate event identities, prevents
one dependency from switching instruments, and requires each dependency's
sequence and event time to advance monotonically. Empty tapes remain explicit
inputs rather than being mistaken for complete coverage; provider acquisition,
coverage attestation, strategy execution, order routing, and fills remain
outside this contract.

The focused event-tape suite passed 7 tests; the full package suite passed 649
tests with Ruff, MyPy, `git diff --check`, and workstream validation green. The
Docker-backed combined coverage gate passed 2,296 tests with 83.59% total
coverage (required threshold: 75%), and setup/cleanup completed successfully.
The provider/API/database/worker/Compose integration and stable Nautilus
execution gates remain deferred.

## 2026-09-16 - Sandbox-gated planner checkpoint

The engine and worker orchestration gates now validate the hardened sandbox
argv before returning a ready plan. A manually constructed plan with missing
isolation controls is rejected during planning and cannot be persisted or
dispatched as ready; the executor retains its independent last-mile check.

The focused gate/worker regression set passed 26 tests, and the complete
Strategy Lab v2 package passed 512 tests with Ruff, MyPy, and `git diff --check`.
The Docker-backed combined gate completed 2,159 tests with 83.03% total
coverage (required threshold: 75%), and Docker setup/cleanup succeeded.
Schema/API/worker/Compose integration and stable Nautilus execution remain
deferred behind the existing gates.

## 2026-09-25 - Failed worker runtime evidence checkpoint

`worker_evidence_resolution.py` now maps a failed runtime receipt that has not
yet received a durable API error projection to a deterministic typed
`ApiError`. The fallback carries only the persisted runtime `error_digest`,
uses the request fingerprint as its stable request identity, and never
reconstructs exception text or filesystem paths. Existing application-owned
errors still take precedence; successful and cancelled runtime evidence retain
their strict manifest/error rules.

The focused resolver suite passed 7 tests. The exact branch validation passed
841 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff
validation, and workstream validation. The Docker-backed combined coverage
gate passed 2,492 tests with 83.75% total coverage (required threshold: 75%);
the referenced runtime env file was absent in this checkout and `.env.dev`
supplied test configuration. Two cleanup passes retained zero testcontainer
sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Authenticated search worker materializer checkpoint

`search_worker_handoff.py` now provides an explicit worker materializer for
search-dispatch queues. Before decoding a Redis payload, it resolves the
request fingerprint through the owner-agnostic PostgreSQL search-dispatch
lookup and verifies request, attempt, payload, and queue identities. It then
validates the decoded immutable worker request's attempt binding and all
orchestration component fingerprints, failing closed on drift or missing
records.

`worker_callbacks.create_search_dispatch()` exposes this binding as an
explicit callback-factory choice using the worker's existing
`STRATEGY_LAB_V2_QUEUE` setting. The ordinary submission-backed callback
factory remains unchanged; no queue is treated as search-dispatch-backed by
default. Focused coverage passed 10 tests, and the complete branch gate passed
874 package tests, 2 migration tests, Ruff, MyPy across 276 files, diff
validation, and workstream validation. The exact backend coverage gate passed
2,525 tests with 83.78% total coverage (required threshold: 75%) and 86
warnings; the referenced runtime env file was absent in this checkout and
`.env.dev` supplied test configuration. Two cleanup passes retained zero
testcontainer sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Enabling this callback in the
actual dedicated worker entrypoint still requires host configuration,
migration/schema reconciliation, stable Nautilus release conformance,
upstream provider/ETF/TC2000 reconciliation, and full shared-path integration.

## 2026-09-25 - Dispatch-identity terminal evidence checkpoint

Worker terminal evidence now resolves the Redis `DispatchRequest` fingerprint
from `WorkerCompletionContext.entry`, rather than incorrectly using the
separately content-addressed `WorkerExecutionRequest` fingerprint. The
submission adapter joins dispatch and submission rows by owner/idempotency key,
authenticates both identities, and rejects ambiguous or drifted bindings.

Search-dispatch workers now have a durable fallback: the authenticated search
dispatch record is projected into the existing typed submission receipt
contract, preserving owner, attempt, payload, queue, and candidate identity
without inventing a principal or requiring a duplicate submission row. Focused
coverage passed 25 tests, and the complete branch gate passed 875 package
tests, 2 migration tests, Ruff, MyPy across 276 files, diff validation, and
workstream validation. The exact backend coverage gate passed 2,526 tests with
83.78% total coverage (required threshold: 75%) and 86 warnings; the referenced
runtime env file was absent in this checkout and `.env.dev` supplied test
configuration. Two cleanup passes retained zero testcontainer sessions,
containers, images, or volumes.

The branch remains `ready_for_human_review`. Dedicated worker activation,
shared migration/application reconciliation, stable Nautilus v2 conformance,
and upstream provider/ETF/TC2000 integration remain gated.

## 2026-09-25 - Explicit search terminal binding correction

The search-dispatch terminal-evidence path now fails closed unless the host
supplies an explicit resolver from the durable `SearchDispatchRecord` to the
authoritative `WorkerSubmissionBinding`. The resolver is checked for owner and
attempt consistency before evidence loads, and the persistence bundle threads
it through the worker terminal resolver. No synthetic `SubmissionReceipt` is
constructed from queue metadata, so `ExecutionOutcome.submission_id` remains
the authoritative submission identity for settlement.

Focused persistence and worker-evidence coverage passed 20 tests. The complete
branch and exact backend coverage gates remain the next validation step for
this correction; the branch stays `ready_for_human_review` pending host
callback registration, shared-path reconciliation, stable Nautilus v2
conformance, and upstream provider/ETF/TC2000 integration.

## 2026-09-25 - Search terminal binding callback registration

The dedicated search callback factory now carries the authoritative terminal
binding seam all the way through application composition. It resolves a
`SearchDispatchRecord` owner/attempt via the persisted submission adapter and
passes that callback to the configured evidence resolver factory. A search
resolver that does not accept the explicit callback is rejected; ordinary
submission-backed workers retain their existing two-argument factory path.
Missing submissions return `None`, preserving the persistence layer's
fail-closed terminal retry behavior and keeping `ExecutionOutcome.submission_id`
authoritative. Focused callback coverage passed 9 tests; the complete branch
gate passed 876 package tests, 2 migration tests, Ruff, MyPy across 276 files,
diff validation, and workstream validation. The exact backend coverage gate
passed 2,527 tests with 83.78% total coverage and 86 warnings; the referenced
runtime env file was absent and `.env.dev` supplied test configuration. Two
cleanup passes retained zero testcontainer resources.

The branch remains `ready_for_human_review`. Host callback activation, shared
migration/application reconciliation, stable Nautilus v2 conformance, and
upstream provider/ETF/TC2000 integration remain gated.

## 2026-09-25 - Authoritative Nautilus image binding checkpoint

The final Nautilus execution gate now extracts the validated sandbox image
digest and compares it with the stable release pin's runtime-image digest
before producing an authoritative execution plan. A mismatched, unreadable,
or absent pinned image is rejected without process creation; compatibility-only
release-candidate plans retain their non-authoritative path. Focused sandbox
and engine-gate coverage passed 11 tests. The complete branch gate passed 878
package tests, 2 migration tests, Ruff, MyPy across 276 files, diff validation,
and workstream validation. The exact backend coverage gate passed 2,529 tests
with 83.79% total coverage and 86 warnings; the referenced runtime env file
was absent and `.env.dev` supplied test configuration. Two cleanup passes
retained zero testcontainer resources.

The branch remains `ready_for_human_review`. Stable Nautilus v2 publication,
isolated runtime activation, shared worker/database reconciliation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Recovery timestamp identity checkpoint

Recovery retry plans and worker-release receipts now normalize all aware
observation, retry, and release timestamps to UTC at their contract boundaries.
Offset-equivalent observations therefore produce identical retry/release
identities, and replay comparisons no longer reject equivalent instants.
Focused recovery coverage passed 10 tests. The complete branch gate passed 880
package tests, 2 migration tests, Ruff, MyPy across 276 files, diff validation,
and workstream validation. The exact backend coverage gate passed 2,531 tests
with 83.79% total coverage (required threshold: 75%) and 86 warnings; the
referenced runtime env file was absent and `.env.dev` supplied test
configuration. Two cleanup passes retained zero testcontainer sessions,
containers, images, or volumes.

The branch remains `ready_for_human_review`. Shared worker/database
reconciliation, stable Nautilus v2 publication, host activation, upstream
provider/ETF/TC2000 integration, and deployment remain gated.

## 2026-09-25 - Legacy import inspection checkpoint

Preserved digest-only legacy records are now exposed through the read-only
`legacy-imports` API resource in addition to `POST /legacy/imports`. The shared
PostgreSQL persistence bundle loads and authenticates the owner-scoped registry,
projects stable record fingerprints, and explicitly retains
`replay_equivalent: false`; payload bytes are never returned.

The focused API/persistence suite passed 26 tests and the full package suite
passed 853 tests. Exact branch validation passed 853 package tests, 2 migration
tests, Ruff, MyPy across 272 files, diff validation, and workstream validation.
The Docker-backed combined coverage gate passed 2,504 tests with 83.78% total
coverage (required threshold: 75%) and 86 warnings; the referenced runtime env
file was absent in this checkout and `.env.dev` supplied test configuration.
Two cleanup passes retained zero testcontainer sessions, containers, images, or
volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Capability-summary API projection checkpoint

Persisted capability summaries are now exposed as the read-only
`capability-summaries` resource in the registration-neutral v2 API. The shared
PostgreSQL persistence bundle projects authenticated summaries with stable
fingerprint identities and preserves data/execution gaps, degradations,
ranking eligibility, executability, and authoritative-publication eligibility.
No provider entitlement or engine registration is inferred by this projection;
preflight calculation remains owned by its existing adapters.

The focused API/resource/persistence suite passed 35 tests and the full package
suite passed 851 tests. Exact branch validation passed 851 package tests, 2
migration tests, Ruff, MyPy across 272 files, diff validation, and workstream
validation. The Docker-backed combined coverage gate passed 2,502 tests with
83.77% total coverage (required threshold: 75%) and 86 warnings; the referenced
runtime env file was absent in this checkout and `.env.dev` supplied test
configuration. Two cleanup passes retained zero testcontainer sessions,
containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Legacy import API checkpoint

The registration-neutral Strategy Lab v2 router now exposes strict
`POST /legacy/imports` handling. Requests require an idempotency key, preserve
only digest-backed legacy metadata, validate mapping/support evidence, and
return a typed compatibility report that permanently carries
`replay_equivalent: false`. Conflicting legacy identities return a typed
conflict rather than overwriting prior evidence. The application adapter now
delegates the route to the existing owner-scoped PostgreSQL legacy registry;
legacy payload bytes remain outside this boundary.

The focused API/legacy/application suite passed 34 tests and the full package
suite passed 849 tests. Exact branch validation passed 849 package tests, 2
migration tests, Ruff, MyPy across 272 files, diff validation, and workstream
validation. The Docker-backed combined coverage gate passed 2,500 tests with
83.76% total coverage (required threshold: 75%) and 86 warnings; the referenced
runtime env file was absent in this checkout and `.env.dev` supplied test
configuration. Two cleanup passes retained zero testcontainer sessions,
containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Request-bound host failure evidence checkpoint

Injected host runtime-error classification is now bound to the immutable worker
request fingerprint. A custom failure factory that returns an `ApiError` for a
different request is rejected before terminal evidence can be persisted,
preventing application policy from detaching failure state from the execution
attempt being settled. The digest-only fallback and existing durable-error
precedence remain unchanged.

The focused resolver/persistence suite passed 17 tests. Exact branch validation
passed 847 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff
validation, and workstream validation. The Docker-backed combined coverage gate
passed 2,498 tests with 83.76% total coverage (required threshold: 75%) and 86
warnings; the referenced runtime env file was absent in this checkout and
`.env.dev` supplied test configuration. Two cleanup passes retained zero
testcontainer sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Complete multi-artifact mapping coverage checkpoint

The resolver coverage now includes a positive two-artifact host mapping in
addition to the fail-closed cases. A complete host-supplied plan set is
accepted only when both output artifact identities, byte digests, lengths, and
retention classes match the immutable result manifest; the package still does
not guess mounted paths or publish bytes on the host's behalf.

The focused resolver suite passed 12 tests. The exact branch validation passed
846 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff
validation, and workstream validation. The Docker-backed combined coverage
gate passed 2,497 tests with 83.76% total coverage (required threshold: 75%);
the referenced runtime env file was absent in this checkout and `.env.dev`
supplied test configuration. Two cleanup passes retained zero testcontainer
sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Exact artifact-plan coverage checkpoint

Successful `WorkerTerminalEvidence` now validates publication plans against the
complete `RunResultManifest.output_artifacts` set before terminal persistence.
Every output artifact must have exactly one plan with matching manifest
fingerprint, content digest, storage key, byte length, and retention class;
unknown, duplicate, substituted, or missing plans fail closed. The host still
owns mapping mounted files to plans, and the existing single-output mapper
continues to reject multi-artifact manifests unless an explicit host mapper is
provided.

The focused resolver suite passed 11 tests. The exact branch validation passed
845 package tests, 2 migration tests, Ruff, MyPy across 272 files, diff
validation, and workstream validation. The Docker-backed combined coverage
gate passed 2,496 tests with 83.76% total coverage (required threshold: 75%);
the referenced runtime env file was absent in this checkout and `.env.dev`
supplied test configuration. Two cleanup passes retained zero testcontainer
sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.

## 2026-09-25 - Injectable worker failure policy checkpoint

The package-owned worker evidence resolver now accepts an optional host
`runtime_error_factory` through both the resolver callback and
`PostgresStrategyLabV2Persistence.worker_terminal_evidence_resolver()`. This
keeps retryability and typed failure classification application-owned while
retaining the deterministic digest-only `ApiError` fallback when no policy is
provided. The factory is invoked only for failed runtime evidence that lacks a
durable projected error; authenticated lookup and artifact mapping remain
separate seams.

The focused resolver/persistence set passed 13 tests. The exact branch
validation passed 843 package tests, 2 migration tests, Ruff, MyPy across 272
files, diff validation, and workstream validation. The Docker-backed combined
coverage gate passed 2,494 tests with 83.75% total coverage (required
threshold: 75%); the referenced runtime env file was absent in this checkout
and `.env.dev` supplied test configuration. Two cleanup passes retained zero
testcontainer sessions, containers, images, or volumes.

The branch remains `ready_for_human_review`. Host application resolver
configuration, explicit multi-artifact mapping, stable Nautilus release
conformance, upstream provider/ETF/TC2000 reconciliation, and full shared-path
integration remain deferred behind their existing gates.
## 2026-09-25 - Forward-event admission API checkpoint

The versioned Strategy Lab API now exposes `POST /forward-instances/{instance_id}/events` as a strict, application-owned admission boundary. The route reparses raw JSON with duplicate/non-finite rejection, reconstructs canonical forward events, cursors, observations, and optional correction commands, then delegates atomic event/counterfactual-replay persistence to the application adapter. Responses retain the authenticated state and replay-plan fingerprints, and missing host persistence fails closed. API JSON conversion now serializes checkpoint sets deterministically. Focused parser/serializer and forward-state regression validation passed (21 tests); Ruff, MyPy (293 source files), and whitespace validation passed. This remains a host/provider event-ingestion seam; it does not activate provider acquisition or Nautilus execution.
## 2026-09-25 - Forward-event dispatch API checkpoint

The versioned Strategy Lab API now exposes `POST /forward-instances/{instance_id}/events/dispatch`, reconstructing strict canonical event/observation/correction inputs plus a typed `DispatchRequest` and bounded payload. It delegates atomic admission, content-addressed payload staging, idempotent dispatch, and transactional-outbox evidence to the application adapter, returning typed dispatch/envelope/replay fingerprints and failing closed when host persistence is absent. Four focused API/parser/serializer tests pass for this slice; Ruff, MyPy (293 source files), and whitespace validation pass. Provider acquisition, live event resolution, Redis activation, and Nautilus execution remain explicit host/upstream gates.
## 2026-09-25 - Forward warm-up API checkpoint

The versioned Strategy Lab API now exposes `POST /forward-instances/{instance_id}/warmup`. It strictly reconstructs the immutable warm-up receipt, verifies route/receipt instance identity and carry-in mode, delegates the one-time durable warm-up boundary, and serializes receipt/instance fingerprints. This keeps activation evidence separate from live event admission and does not fetch provider data or start Nautilus. Five focused forward API/parser/serializer tests pass in the current slice; Ruff, MyPy (293 source files), and whitespace validation pass.
## 2026-09-25 - Forward lifecycle API checkpoint

The versioned Strategy Lab API now exposes `POST /forward-instances/{instance_id}/lifecycle`, strictly parses a target state and timezone-aware transition timestamp, delegates owner-scoped compare-and-set persistence, and serializes applied/replay/conflict evidence. This completes the API-side lifecycle seam around the already durable forward-state adapter; provider event acquisition, worker activation, and Nautilus execution remain gated. Six focused forward API/parser/serializer tests pass in the current slice; Ruff, MyPy (293 source files), and whitespace validation pass.
## 2026-09-25 - Forward API ASGI route evidence

The warm-up endpoint now has executable ASGI-level coverage using an in-process HTTP transport, proving request parsing, dependency injection, application delegation, typed serialization, and the 202 response at the registered route. The focused forward/API suite now passes 25 tests; Ruff, MyPy (293 source files), and whitespace validation remain green.
## 2026-09-25 - Forward dispatch/lifecycle ASGI evidence

ASGI-level route coverage now exercises the atomic forward dispatch/outbox and lifecycle compare-and-set endpoints in addition to warm-up. The focused forward/API suite passes 27 tests, proving the registered HTTP boundaries delegate typed requests through the application seams and return typed 202 responses. Ruff, MyPy (293 source files), and whitespace validation remain green.
## 2026-09-25 - Counterfactual replay observability checkpoint

Persisted forward correction replay plans now have an authenticated owner-scoped read bridge and `GET /forward-instances/{instance_id}/replays` projection. The adapter returns `404` for unknown instances, verifies deterministic replay ordering, and the API exposes immutable plan identities without changing live state. ASGI route, serializer, and forward-state tests pass; the focused suite now passes 29 tests with Ruff, MyPy (293 source files), and whitespace validation green.
## 2026-09-25 - Durable replay read-back evidence

The replay observability slice now includes direct PostgreSQL-adapter coverage: persisted correction plans load deterministically for the owning principal, while another owner receives no instance evidence. The focused forward/API suite remains at 29 passing tests with Ruff, MyPy (293 source files), and whitespace validation green.

## 2026-09-25 - Replay instance-binding hardening

Replay serialization now rejects any persisted plan whose instance identity does
not match the route resource being projected. This closes a local resource
binding gap while preserving deterministic replay ordering and immutable plan
identity. The focused forward/API suite passes 30 tests, with Ruff, MyPy (293
source files), and whitespace validation green.

## 2026-09-25 - Forward projection identity hardening

Forward event-transaction serialization now rejects counterfactual replay plans
bound to a different instance than the projected checkpoint. Warm-up projection
also rejects receipts whose instance, snapshot, or carry-in mode differs from
the resolved forward instance. These checks keep host adapter output fail
closed at the API boundary rather than trusting a malformed resolution. The
focused forward/API suite passes 32 tests; Ruff, MyPy (293 source files), and
whitespace validation remain green.

## 2026-09-25 - Forward dispatch projection hardening

Dispatch responses now verify that their nested event transaction carries the
same state fingerprint as the outer dispatch resolution and that any nested
counterfactual replay plan belongs to that state's forward instance. This
prevents a malformed host resolution from publishing mixed-instance dispatch
evidence. The focused forward/API suite passes 33 tests; Ruff, MyPy (293
source files), and whitespace validation remain green.

## 2026-09-25 - Async dedicated-worker spawn checkpoint

Dedicated worker services now use an asynchronous process-executor path that
starts the fresh spawn child on the worker event-loop thread and cooperatively
polls it, preserving lease-heartbeat scheduling without invoking Python spawn
from `asyncio.to_thread` (which stalled in this runtime). The synchronous
executor remains available for direct callers. The API test helper now uses a
synchronous facade over `httpx.ASGITransport`, removing the hanging Starlette
`TestClient` portal while retaining the same route assertions.

The complete Strategy Lab v2 package suite passes 949 tests, including 124
PostgreSQL adapter tests and 3 migration-startup tests. Ruff, MyPy (293 source
files), and whitespace validation remain green.

The repository-authoritative Docker-backed combined backend coverage gate also
passes at the exact implementation tip: 2,600 tests, 83.76% total coverage
(required threshold 75%), and 86 warnings. Integration containers were cleaned
up after the run; no containers, images, or volumes were retained.

## 2026-09-25 - Worker timeout escalation checkpoint

Both synchronous and asynchronous dedicated-worker execution now escalate a
timed-out child from `terminate()` to `kill()` when necessary, then reap the
process handle before returning typed timeout evidence. This closes the last
local orphan-process path in the serial Nautilus worker boundary. The full
Strategy Lab package suite passes 949 tests, and the exact-tip Docker-backed
combined gate passes 2,600 tests with 83.76% coverage (threshold 75%).

## 2026-09-25 - Async worker timeout regression evidence

The serial worker process suite now directly covers the asynchronous timeout
path in addition to synchronous timeout handling. A real spawned child that
outlives the deadline is escalated, reaped, and returned as typed timeout
evidence without leaving the event loop blocked. The complete Strategy Lab v2
package suite passes 950 tests; focused worker coverage passes 12 tests.

The repository-authoritative Docker-backed combined gate also passes at the
current exact tip: 2,601 tests, 83.76% total coverage (required threshold
75%), and 86 warnings. Cleanup removed the test containers, images, and
volumes.

## 2026-09-25 - Cooperative async timeout cleanup

Async timed-out worker cleanup now performs terminate/kill escalation with
cooperative zero-time joins and event-loop yields. A stubborn child therefore
cannot block lease-heartbeat scheduling while the parent waits for cleanup.
The focused worker suite passes 13 tests, including a fake stubborn-process
regression that proves kill escalation and event-loop progress.

## 2026-09-25 - Cancellation-safe async worker cleanup

Cancelling an in-flight asynchronous worker handoff now terminates and reaps
the spawned child before propagating cancellation, preventing orphaned
simulation processes during worker shutdown or lease cancellation. The focused
worker suite passes 14 tests and the complete Strategy Lab v2 package suite
passes 952 tests.

The repository-authoritative Docker-backed combined gate passes at this exact
implementation tip: 2,603 tests, 83.78% total coverage (required threshold
75%), and 86 warnings. Cleanup removed the test containers, images, and
volumes.

## 2026-09-25 - Heartbeat-failure execution cancellation

Dedicated worker services now monitor the process handoff and lease-heartbeat
task together. A rejected or failed heartbeat immediately cancels the
simulation task, which invokes the cancellation-safe process reaper before the
entry is returned for retry. Focused worker coverage passes 15 tests and the
complete Strategy Lab v2 package suite passes 953 tests.

The repository-authoritative Docker-backed combined gate passes at this exact
implementation tip: 2,604 tests, 83.78% total coverage (required threshold
75%), and 86 warnings. Cleanup removed the test containers, images, and
volumes.

## 2026-09-25 - Service-shutdown execution cancellation

Cancelling the dedicated worker service handler itself now cancels its
separately scheduled execution task and awaits its cleanup, so shutdown cannot
leave a running simulation child behind. Focused worker coverage passes 16
tests and the complete Strategy Lab v2 package suite passes 954 tests.

The repository-authoritative Docker-backed combined gate passes at this exact
implementation tip: 2,605 tests, 83.78% total coverage (required threshold
75%), and 86 warnings. Cleanup removed the test containers, images, and
volumes.

## 2026-10-02 - Resumed session and transport synchronization audit

The assigned implementation session was resumed after the previous blocked
audit. The required UV-managed `agent-context` and session bootstrap completed
through the repository-approved elevated execution path; the initial
unprivileged attempt was blocked only by the shared read-only UV cache. The
existing local implementation range was pushed successfully to
`origin/feat/strategy-lab-v2`: remote `6dbb206a4` now matches implementation
tip `a6a98b122`.

The provider-platform, ETF, and TC2000 branches have advanced since the prior
checkpoint, but `staging` remains `8b885a2ff` and none of those dependency refs
is an ancestor of staging. Their overlapping provider/migration/application
paths remain outside this feature branch's ownership. The next product action
remains gated on approved staging promotion, stable Nautilus v2 release and
conformance evidence, and host runtime evidence configuration; no
cross-worktree integration was performed.

The active operational context owns the following pending record files until
the checkpoint commit closes them: `ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## Active context - forward worker Compose entrypoint

Intent: add the explicit opt-in local forward-worker entrypoint and Compose
service, keeping host event/materializer and account/engine callbacks required
and fail-closed. Add the forward payload-loader seam needed by that entrypoint.
Owned paths: `backend/app/strategy_lab_v2/forward_worker_entrypoint.py`,
`backend/app/strategy_lab_v2/postgres_forward_dispatch.py`, their focused tests,
`docker-compose.yml`, and this handoff/validation record.

## 2026-10-02 - Dedicated forward worker Compose boundary

The local forward-testing boundary is now explicit and opt-in. The new
`forward_worker_entrypoint` performs startup migration, builds the persistence
adapter, loads a host-supplied materializer/handler callback factory, consumes
the dedicated `forward-events` Redis queue, rehydrates payloads through the
PostgreSQL forward-dispatch adapter, and shuts down the runtime and scheduler
cleanly. Callback configuration is mandatory at runtime and fails closed; the
entrypoint does not select a provider, broker, or Nautilus implementation.

`docker-compose.yml` now declares a separate `strategy-lab-v2-forward-worker`
service under the existing `strategy-lab-v2` profile with a read-only root,
dropped capabilities, no-new-privileges, bounded temporary storage, an
artifact volume, and PostgreSQL/Redis health dependencies. This is a local
execution boundary only; host event resolution, account semantics, and engine
callbacks remain an explicit deployment concern. `PostgresForwardDispatch` now
exposes the content-addressed payload loader consumed by the worker.

Validation for this slice: focused forward-entrypoint/dispatch/service/compose
tests passed (17 tests); the complete Strategy Lab v2 package suite passed
(960 tests); targeted Ruff, Ruff format checks, MyPy, and `make
test-compose-contract` passed. `UV_CACHE_DIR=/tmp/strategy-lab-v2-uv-cache make
validate-integration` reached the repository lint stage but stopped because
the branch baseline reports 232 files requiring `ruff format --check`,
including untouched files; no mass formatting was applied. This is a
repository-wide validation baseline issue, not a failure in the focused slice.

The implementation remains gated from authoritative activation by stable
Nautilus v2 release/conformance evidence, host callback/event configuration,
approved provider/ETF/TC2000 promotion to staging, and shared migration and
application-path reconciliation. No other worktree was changed.

## 2026-10-02 - Exact external blocker audit after forward-worker push

At the post-push audit, `origin/staging` is still `8b885a2ffd9c`, while the
current dependency refs are market-data `366fdd4f4276`, ETF
`52814f95bd0e`, and TC2000 `63d64bfe95c9`; none is an ancestor of staging.
Therefore shared provider, ETF, frontend, migration, and application-path
reconciliation is not yet admissible under AC-UPSTREAM.

The checked-out backend still pins `nautilus-trader==1.226.0`, while the
Strategy Lab v2 conformance contract rejects release pins that do not start
with `2.`. A stable Nautilus v2 package/build plus the required multi-account,
native order/fill/cost, deterministic replay, lifecycle, and backtest/forward
event-tape evidence is therefore still missing. The worker Compose boundary
is intentionally unable to claim authoritative activation without that
evidence. The remaining runtime-specific dependency is an explicitly
configured host callback factory that resolves admitted canonical events and
account/engine semantics; an empty Compose value fails closed by design.

## 2026-10-02 - Forward worker configuration isolation hardening

The forward Compose service now uses the namespaced
`STRATEGY_LAB_V2_FORWARD_DATABASE_URL_SYNC` variable rather than inheriting
the generic worker database key, and its contract test asserts that the
forward service has no Docker socket. Namespaced configuration keeps the
forward boundary explicit and the absence of a Docker socket prevents a
forward-event worker from acquiring backtest sandbox authority. Focused
entrypoint/Compose coverage passes 5 tests and `make test-compose-contract`
passes.

## 2026-10-02 - Backtest worker configuration boundary hardening

The isolated backtest worker now uses the namespaced
`STRATEGY_LAB_V2_DATABASE_URL_SYNC` key, matching its explicit worker
configuration contract rather than inheriting the generic database variable.
The new Compose contract test verifies that the backtest worker remains
profile-gated, read-only, capability-dropped, health-gated on PostgreSQL and
Redis, and artifact-volume-backed, while retaining its intentionally explicit
Docker socket because sandbox execution launches separately pinned runtime
containers. Focused backtest/forward entrypoint and Compose coverage passes 12
tests; `make test-compose-contract` passes.

## 2026-10-02 - Current dependency and runtime-boundary audit

The current remote refs are market-data `1b51877881ce`, ETF
`52814f95bd0e`, and TC2000 `63d64bfe95c9`; `origin/staging` remains
`8b885a2ffd9c`, and none of those dependency refs is a staging ancestor.
The implementation therefore remains prohibited from shared provider, ETF,
TC2000, migration, or application-path reconciliation. The backtest and
forward worker boundaries are now both documented and tested locally, but
authoritative activation still requires the stable Nautilus v2 release and
host callback evidence described above.

The complete Strategy Lab v2 package suite was rerun at the current exact
implementation tip and passes 961 tests. This includes the package-owned
backtest and forward worker entrypoint/Compose contracts; it does not claim
provider-backed acquisition, stable Nautilus execution, or full repository
integration.

## 2026-10-02 - Nautilus v2 release-candidate compatibility track

The absence of a stable Nautilus v2 release no longer blocks all engine work.
The branch now treats the exact `2.0.0rc5` package/tag as an isolated
compatibility track. Complete RC conformance evidence may run local backtest,
replay, and forward event-tape compatibility checks, but the resulting plan is
always non-authoritative and cannot publish official results, participate in
official rankings, or activate a deployed shadow instance. Stable v2 remains
mandatory for those authority boundaries.

The conformance gate now requires a valid isolated v2 release pin for every
actual Nautilus process, including RC execution; an unpinned or shared-runtime
build is rejected before sandbox invocation. The current backend
`nautilus-trader==1.226.0` dependency remains untouched for the legacy runtime.
The RC runtime must be a separate exact-pinned Python/Rust/runtime-image
environment and must not use the backend's v1 environment.

Current blockers are therefore narrower and concrete: the provider-platform,
ETF, and TC2000 refs are still not staging ancestors; host canonical-event,
account, and engine callback evidence is not configured for forward execution;
shared migration/application reconciliation is not admissible; and the
repository-wide formatter baseline still prevents the full integration gate.
None of these blocks pure contracts, RC conformance fixtures, or isolated
compatibility-run plumbing. Stable Nautilus remains only the blocker for
authoritative publication/live shadow, not for continued implementation.

## 2026-10-02 - Exact RC runtime declaration

`nautilus_runtime.py` now provides the immutable
`NautilusRcCompatibilityRuntime` adapter contract. It hard-codes the current
`2.0.0rc5` package/tag, requires source and runtime-image SHA-256 digests,
records Python/Rust versions, rejects any attempt to share the legacy runtime,
and produces the `NautilusReleasePin` consumed by conformance evidence. It
does not import Nautilus or install/discover packages.

The focused runtime/conformance/engine suite passes 21 tests, and Ruff plus
MyPy pass for the new adapter and probe. The exact x86_64 CPython 3.12 wheel
was verified against PyPI's published SHA-256
`eab45fafd2312deda1236554c49a9798bfc76bc8465af864878e2f70189ebebe`; the
probe then constructed and disposed a real `BacktestEngine` from
`2.0.0rc5`, yielding `engine_lifecycle=passed`. The complete package suite
passes 970 tests at this checkpoint. The exact isolated runtime image was then
built from `python:3.12.4-slim@sha256:a3e58f9399353be051735f09be0316bfdeab571a5c6a24fd78b92df85bcb2d85`
with the verified x86_64 wheel and published checksum, producing image digest
`sha256:94d1bedef43b8b627b68ae8d4f43a79e47be635c7cd61fa9ddf8508d3b89b22e`.
The image probe passed with network disabled, read-only root, all Linux
capabilities dropped, `no-new-privileges`, and bounded tmpfs mounts; it emitted
`engine_lifecycle=passed` for Python 3.12.4 / Nautilus `2.0.0rc5`. This proves
isolated RC compatibility only; it does not grant authoritative publication or
live-shadow status.

The probe receipt is now parsed by `NautilusRuntimeProbeEvidence`, which binds
the exact package/Python fields and image digest back to the immutable runtime
fingerprint and rejects extra fields, version drift, failed lifecycle output,
or any attempt to treat the RC receipt as authoritative. The focused runtime,
probe, and fixture suite passes 16 tests with Ruff, MyPy, and diff validation
green.

## 2026-10-02 - RC probe/conformance identity binding

`require_runtime_probe_binding(...)` now joins a complete executable fixture
resolution to the exact `NautilusRuntimeProbeEvidence` receipt. It requires
Nautilus identity, the RC package/channel, the exact release pin, matching image
digest, and execution-eligible fixture evidence, while explicitly rejecting
authority claims. This is an identity/reproducibility gate around the injected
fixture harness; it does not claim that synthetic fixtures are real Nautilus
multi-instrument or event-tape conformance.

The full Strategy Lab v2 package suite passes 976 tests, with Ruff, targeted
formatting, MyPy across 302 files, and diff validation green.

## 2026-10-02 - Image-backed RC deterministic engine fixtures

The isolated image was rebuilt with `nautilus_rc_fixture_probe.py`, producing
digest `sha256:1e8a1c33b58ac216027b777dc025e833f5bc5c93bf10e9b550985e0024847c3f`.
Under network-disabled, read-only, capability-dropped, no-new-privileges
execution, the real Nautilus `2.0.0rc5` engine completed deterministic
synthetic fixtures: one instrument produced one native order and position with
account total `98899.78 USD`; two instruments produced two orders and two
positions with account total `97799.56 USD`; two identical runs matched exactly.
The fixture explicitly reports `forward_event_tape_parity` as
`deferred_authoritative_fixture`, because the canonical event adapter and host
forward callback are not yet available. This is genuine RC compatibility
evidence, not stable authority or a live-shadow claim.

The resulting JSON was parsed through `NautilusRcFixtureReceipt` with source
digest `sha256:dd30e7817784d1a9eec556c15b846f93040a7a4e8694cab4771d0ba0c24c6c06`,
image digest above, and fixture digest
`sha256:8432ac13ee7e24b526ca8efeadf3d20370eb3aadf362fa947e2f7ab4579d7540`.
The typed receipt records passed checks for engine lifecycle, native
order/fill/cost, multi-instrument accounting, and deterministic replay, with
only `forward_event_tape_parity` deferred. It remains compatible evidence and
is explicitly non-authoritative.

## 2026-10-02 - Provider-neutral canonical-event materialization boundary

Added `nautilus_event_adapter.py` and focused tests for the next safe slice of
the RC compatibility track. `NautilusEventRecord` converts validated
engine-neutral `MarketEvent` values into an immutable wire record with exact
UTC nanosecond timestamps, required OHLCV/quote/trade fields, and content
fingerprints. `NautilusEventTape` preserves the source frozen-tape identity,
canonicalizes deterministic replay order, and rejects duplicate identities.
`materialize_nautilus_event_tape(...)` reuses the existing snapshot/manifest
binding before materializing records, so no provider fetch, inference, or
Nautilus import is introduced. This is the host/Rust adapter contract only;
forward event-tape parity, account callbacks, stable-release authority, and
shared-path integration remain explicitly gated.

The focused adapter suite passes 6 tests with package-local Ruff, formatting,
MyPy, and diff checks as the next validation receipt; the complete package
suite and repository integration checks are rerun at the checkpoint commit.

## 2026-10-02 - Canonical event-tape parity receipt

Extended `nautilus_event_adapter.py` with a strict observed-wire schema and
`verify_nautilus_event_tape_parity(...)`. The verifier canonicalizes event
order, rejects duplicate or malformed records, and returns content-addressed
field-level mismatch evidence. `NautilusEventParityReceipt` is explicitly
compatible-only and non-authoritative, so it can become the forward-parity
conformance input once a real host/Rust callback is available without making a
synthetic adapter claim stable Nautilus authority.

The focused adapter suite now passes 9 tests; package-wide validation follows
after the documentation and workstream receipt are committed.

## 2026-10-02 - Event parity conformance projection

`build_event_tape_parity_observation(...)` now converts a
`NautilusEventParityReceipt` into the existing
`FORWARD_EVENT_TAPE_PARITY` conformance observation. Successful receipts use
their content fingerprint; failed receipts receive a distinct failure digest,
so an expected-digest configuration cannot manufacture a pass. This keeps the
future real host/Rust callback on the same conformance path as the other engine
checks without claiming that the current RC fixture is authoritative.

The complete package suite passes 987 tests, with package Ruff, targeted
formatting, MyPy, diff, and workstream validation green.

## 2026-10-02 - Effective event-type substitution binding

`materialize_nautilus_event_tape(...)` now resolves each dependency's effective
event type from the snapshot's verified preflight decision, including explicit
degraded substitutions. The adapter therefore cannot silently label a
materialized record with the requested event type when the bound snapshot used
another supported type. A focused regression covers the degraded substitution
path and the complete package suite passes 988 tests.

## 2026-10-02 - Forward canonical-event envelope

Added `NautilusForwardEventEnvelope` and
`materialize_nautilus_forward_event(...)`. The envelope binds the admitted
`CanonicalForwardEvent` stream identity to the payload-bearing `MarketEvent`
and resulting Nautilus wire record, rejecting event-ID, sequence, or timestamp
drift before a host/Rust live adapter can invoke the engine. This closes the
identity seam without inventing provider/account callbacks or claiming RC
forward parity.

The focused adapter suite passes 12 tests with Ruff, formatting, and MyPy
green; package-wide validation is rerun for the checkpoint.

## 2026-10-02 - Feature-ref/session receipt alignment

The checkout's Git upstream metadata was pointing at the legacy hyphenated
`origin/feat-strategy-lab-v2` ref instead of the actual slash-named
`origin/feat/strategy-lab-v2` feature ref. This made a synchronized checkout
appear 297 commits ahead and left the session receipt at the prior
implementation tip. Upstream tracking now resolves to the slash-named feature
ref, the branch is exactly synchronized, and the session checkpoint records
the current forward-envelope checkpoint. This was workflow metadata drift, not
a Strategy Lab product or Nautilus dependency failure.

## 2026-10-02 - Non-authoritative result provenance and ranking boundary

`RunResultManifest` and `EngineResultEvidence` now carry an explicit
`engine_authoritative` bit, included in reproduction identity and propagated
through result materialization. Publication rejects manifests that are not
bound to authoritative conformance evidence or whose authority bit disagrees
with that evidence. Descriptive ranking excludes non-authoritative engine
output by default with a typed exclusion reason; an explicit exploratory
`include_non_authoritative=True` opt-in is available for RC compatibility
analysis without confusing it with official ranking.

Focused provenance/ranking/publication/materialization coverage passed 52
tests. Package-wide validation passed 991 tests, Ruff, MyPy across 305 source
files, diff validation, and workstream validation. This makes the existing
RC policy enforceable in result data rather than relying only on runtime
documentation or the publication gate.

The elevated combined backend gate subsequently passed 2,642 tests with
83.77% total coverage against the repository's 75% threshold, and the backend
and RPI Compose configuration contracts rendered successfully. This removes
the earlier sandbox-only runtime-registry diagnostic from the validation
picture; it was an execution-environment boundary, not a product failure.

## 2026-10-02 - RC fixture receipt/conformance binding

`require_rc_fixture_binding(...)` now joins the parsed real-image
`NautilusRcFixtureReceipt` to the exact runtime probe, release pin, and partial
conformance suite. It requires passed and deferred check sets to match exactly
and rejects image/version/channel drift or any authority claim. This lets the
current `2.0.0rc5` fixture evidence feed compatibility analysis without
silently satisfying the stable or forward-parity authority gates.

The focused RC fixture/probe suite passes 22 tests; the complete package suite
passes 993 tests, Ruff, MyPy across 305 source files, diff validation, and
workstream validation.

## 2026-10-02 - Forward event-tape batch callback boundary

`NautilusForwardEventTape` and `materialize_nautilus_forward_tape(...)` now
bind an instance-scoped batch of admitted `CanonicalForwardEvent` values to
their payload-bearing `MarketEvent` records. The boundary canonicalizes
sequence order, rejects duplicate identities or sequences, requires an exact
dependency-to-event-type map, and remains provider- and Nautilus-free. It is
the batch seam a future host/Rust callback can consume; it does not claim that
the callback or forward parity implementation exists.

The focused event-adapter suite passes 14 tests; the complete package suite
passes 995 tests, Ruff, MyPy across 305 source files, diff validation, and
workstream validation.

## 2026-10-02 - Forward event-tape parity receipt

`NautilusForwardEventParityReceipt` and
`verify_nautilus_forward_event_tape_parity(...)` now verify the strict wire
records emitted for an admitted forward batch against the instance-scoped
canonical-event envelopes. The receipt preserves the forward-tape identity,
canonicalizes callback order, reports field-level drift, and remains explicitly
non-authoritative. It is the evidence seam a future host/Rust callback can
produce without importing Nautilus or acquiring provider data.

The focused event-adapter suite passes 17 tests; the complete package suite
passes 998 tests, Ruff, MyPy, diff validation, and workstream validation.

## 2026-10-02 - Forward parity conformance projection

`build_event_tape_parity_observation(...)` now accepts both the existing
historical `NautilusEventParityReceipt` and the instance-scoped
`NautilusForwardEventParityReceipt`. Forward callback evidence can therefore
feed the existing `FORWARD_EVENT_TAPE_PARITY` conformance check with the same
fail-closed digest and pass-bit rules; no authority is inferred from a parity
receipt.

The focused conformance/event-adapter suites pass 33 tests; the complete
package suite passes 999 tests, Ruff, MyPy across 305 source files, diff
validation, and workstream validation.

The exact-tip Docker-backed combined backend gate then passed 2,650 tests with
83.77% total coverage against the 75% threshold, and the backend/RPI Compose
contract rendered successfully. The gate emitted 86 dependency warnings but no
test failures; resources were cleaned after completion.

The durable plan next action now reflects that the implementation-side tape,
parity, and conformance projection seams are complete. The remaining action is
to invoke them from the real host/Rust canonical-event callback once that
callback and approved staging contracts exist; worker activation, publication,
and live shadow remain fail-closed until their independent gates pass.

## 2026-10-02 - Upstream gate refresh after parity completion

Remote refs were refreshed after the forward-parity implementation. `origin/staging`
remains `8b885a2ffd9c`; market-data `f9be6bfdb71d`, ETF `1a256e78d0d1`, and
TC2000 `63d64bfe95c9` are still not staging ancestors. No shared-path
reconciliation is admissible yet, and no parallel worktree was changed.

The official Nautilus release list was also rechecked on 2026-10-02: the 2.x
line still exposes `2.0.0rc5` as a pre-release and no stable 2.x release. The
RC compatibility track therefore remains the correct local path; stable release
authority is still fail-closed rather than inferred.

## 2026-10-02 - RC backtest execution scope

`NautilusExecutionScope` now distinguishes full, forward-compatibility, and
backtest-compatibility process gates. A non-authoritative exact-pinned RC
backtest/replay plan may proceed when multi-instrument accounting, native
order/fill/cost, deterministic replay, and lifecycle checks pass while forward
event-tape parity remains explicitly deferred. Forward compatibility and every
authoritative plan still require the complete check set; no authority is gained
from selecting the narrower scope.

The focused engine-execution suite passes 10 tests; the complete Strategy Lab v2
package suite passes 1,001 tests, Ruff, MyPy across 305 source files, and diff
validation.

## 2026-10-02 - RC receipt-to-execution evidence bridge

`resolve_nautilus_rc_conformance(...)` now turns the parsed exact-image RC
fixture receipt plus runtime probe into the ordinary engine evidence/report
pair consumed by the execution gate. The resolver authenticates runtime,
probe, image, package, release-pin, build, and fixture identities, preserves
the four passed checks and deferred forward-parity check, and cannot emit
authoritative evidence. The focused conformance-fixture and engine-gate suites
pass 29 tests; the complete Strategy Lab v2 package suite passes 1,004 tests,
Ruff, MyPy across 305 source files, and diff validation. The engine-gate test
now consumes the resolver output directly through the backtest-compatible
execution scope.

## 2026-10-02 - Forward parity adapter resolution

`resolve_nautilus_forward_parity(...)` now composes strict forward-wire
verification with the existing conformance projection. It returns a typed
resolution binding the instance-scoped tape, parity receipt, and
`FORWARD_EVENT_TAPE_PARITY` observation, while preserving mismatch evidence
and the non-authoritative boundary for the eventual host/Rust callback.
The focused conformance-fixture suite passes 18 tests and the complete
Strategy Lab v2 package suite passes 1,004 tests, Ruff, MyPy, and diff
validation.

## 2026-10-02 - Nautilus sandbox engine binding

Added an explicit Nautilus sandbox builder that binds
`STRATEGY_ENGINE_ID=nautilus` into the hardened Docker argv. The final
`run_nautilus_plan` process boundary now validates that marker and rejects
missing or non-Nautilus engine identities before invoking Docker, closing the
gap where a plan could claim Nautilus evidence while carrying a generic runtime
command. Generic sandbox plans remain available to engine-neutral runtime
paths. Focused sandbox/runner coverage passes 11 tests; the complete Strategy
Lab v2 package suite passes 1,006 tests, Ruff, MyPy, and diff validation.

## 2026-10-02 - Nautilus engine-input catalog boundary

Added `nautilus_engine_input.py`, an engine-neutral immutable input contract
for the eventual Nautilus runtime adapter. It binds an already materialized
event tape to provider-supplied instrument precision/increment/lifecycle
metadata, one shared venue/account model with initial cash, and the strategy
source/manifest/parameter identities. It rejects missing instruments,
cross-venue events, duplicate definitions, invalid cash/base currency, and
malformed entrypoints before native engine construction. The focused engine
input/event-adapter suite passes 22 tests; the complete Strategy Lab v2 package
suite passes 1,011 tests, Ruff, MyPy, and diff validation.

## 2026-10-02 - Isolated Nautilus engine-input runtime adapter

Added the image-local `nautilus_runtime_data.py` materializers and
`nautilus_runtime_adapter.py`. The adapter consumes a strict serialized
`NautilusEngineInput`, validates digest/catalog/tape identities before native
imports, constructs RC5-native instruments, venue/account balances, and quote,
trade, or OHLCV values, then invokes `BacktestEngine` and emits scalar
digest-bound execution evidence. The evidence is explicitly non-authoritative;
the forward event-tape parity field remains deferred and no worker/publication
authority is enabled.

The hardened exact `2.0.0rc5` image built successfully and the adapter probe
ran network-disabled, read-only, capability-dropped, and no-new-privileges.
Its two native quote events produced two iterations, one native order, one
open position, and deterministic scalar account/cost evidence. The existing
RC lifecycle and fixture probes remain green. Focused adapter/image tests pass
6 tests; Ruff, MyPy, and diff validation pass. The next slice is to bind this
runtime adapter to the worker's serialized strategy invocation/result protocol
without changing the generic Compose worker or claiming RC authority.

## 2026-10-02 - RC5 serialized strategy invocation bridge

The isolated adapter now consumes the existing serialized strategy invocation
batch instead of an in-process strategy factory. `nautilus_strategy_bridge.py`
authenticates the batch source/manifest/entrypoint/parameters/seed against the
engine input, binds each SDK context to exactly one canonical tape event, and
invokes the existing `StrategyInvocationSession` from native quote/trade/bar
callbacks. Position snapshots come from the native portfolio; supported
`OrderIntent` values are converted to native orders, and the typed batch result
is returned with input/result digests and invocation count. Missing and
source-mismatched batches fail before native engine imports. Target-position
intents deliberately fail closed until the platform allocator/risk bridge is
connected.

The exact pinned RC5 image (`sha256:725c63134aa77fd53d58ac73153ab9bf93377cd0b9c0e550b152c6578782ec88`)
was rebuilt from this source and passed the hardened no-network, read-only,
capability-dropped probe. Two quote events invoked two SDK contexts and
produced two successful serialized results, one native order, and one open
position. The receipt remains `authoritative: false`; forward parity remains
deferred. Focused runtime/image tests pass 9 tests, the complete package suite
passes 1,018 tests, Ruff and MyPy across 312 source files pass, and the
workstream validator accepts all 30 records.

Stable Nautilus v2 is not blocking further isolated implementation. The live
release line is still pre-release `2.0.0rc5`; stable conformance remains an
authority gate. The next local seam is to connect the validated worker handoff
and result/artifact lifecycle to this adapter, then route target-position
intents through allocation/risk and broaden product/accounting/report tests.
Provider, ETF, and TC2000 contracts remain gated only for their respective
shared-path integrations until those branches reach staging.

Session progress and exact command receipts are recorded in
`ops/workstreams/feat-strategy-lab-v2/session.json` and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-02 - RC worker CLI and result-artifact path

Stable Nautilus v2 is not a prerequisite for this implementation. The isolated
RC5 compatibility path now has a fixed `nautilus_runtime_cli` command, built
through `build_nautilus_runtime_sandbox_command`. The runner rejects arbitrary
commands and binds the attempt, exact engine version, frozen snapshot, and
memory-derived input bound to the immutable execution/sandbox plans. The CLI
checks the mounted bundle's canonical digest, attempt, snapshot, exact installed
package version, strict JSON shape, and bounded input before invoking the
serialized engine-neutral SDK strategy batch. It writes deterministic native
execution evidence into the already-mounted result file; the existing sandbox
adapter captured its file digest/length for the artifact publication path.

The RC image now defaults to the CLI's non-authoritative version probe while
remaining command-overridable for actual backtests. Its small wire-protocol
module is separated from host-only typed bundle contracts so the image does not
load legacy backend contract modules. The Nautilus sandbox builder uses the
image's packaged working directory. The Docker output bind mount now uses
Docker's valid read-write default rather than an unsupported `rw` mount token.

An end-to-end run through the real host builder/`run_nautilus_plan` and the
locally built digest-pinned RC5 image succeeded with networking disabled,
read-only root, all capabilities dropped, `no-new-privileges`, an unprivileged
UID, 512 MiB memory, and bounded CPU/output. Two frozen quote events produced
two serialized SDK invocations, one native order, and one open position. The
captured 3,016-byte result file had digest
`sha256:27995118ac75efa6b8c60c3663ee43e0e28cc9e77c15cb523b88fa155bf87c3d`;
its internal execution-evidence digest verified and its authority bit remained
false. The exact local RC5 image was rebuilt as
`sha256:89ec7792a4b6c15aae6752f2cd9d5c503df23e8e48f876a0bdbdf80a96ab9203`.

The Strategy Lab v2 package suite passes 1,026 tests, Ruff passes, and MyPy
passes across 316 source files. The current host has no Docker BuildKit/buildx
plugin, so the image was built with the established legacy-builder fallback
and a temporary package-only `.dockerignore`; that temporary file was removed.
The current code path proves CLI and result capture, but production worker
request assembly/materialization of `NautilusRuntimeBundle` is still open, as
are target-position allocation/risk routing and broader native product,
accounting, report, and stable-authority conformance. RC results remain
non-authoritative. Provider, ETF, and TC2000 staging boundaries remain scoped
to those shared-contract integrations and do not block this isolated work.

Files changed in this slice: `backend/app/strategy_lab_v2/nautilus_runner.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_bundle.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_cli.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_protocol.py`,
`backend/app/strategy_lab_v2/sandbox.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_image/Dockerfile`,
`backend/app/strategy_lab_v2/nautilus_runtime_image/Dockerfile.dockerignore`,
and the focused tests `test_engine_execution.py`, `test_execution_orchestration.py`,
`test_nautilus_runner.py`, `test_nautilus_runtime_cli.py`,
`test_nautilus_runtime_image.py`, `test_sandbox.py`, and
`test_sandbox_execution.py` under `backend/app/strategy_lab_v2/tests/`.

## 2026-10-02 - Verified local strategy-package resolution

The implementation no longer waits for a stable Nautilus v2 tag. Exact-pinned
v2 prereleases are eligible for authoritative local backtests only after the
complete platform conformance suite; prereleases remain barred from broker
connections and real-capital control. Forward shadow additionally requires
backtest/forward event-tape parity. RC5's current compatibility probe alone is
still non-authoritative.

Added the v1 source-archive contract and `StrategyPackageArtifactResolver`.
Source packages are bounded ZIPs containing exactly the versioned SDK manifest,
canonical exact dependency lock, and the entrypoint module. Resolution checks
the raw archive/manifest/lock digests and declared lengths, strategy and SDK
identity, exact worker runtime ABI, source digest, archive member types and
compression limits, then applies static strategy validation. It never extracts
files or installs dependencies; wheel packages fail closed until the isolated
runtime supports them. A verified package result can now feed the existing
Nautilus trial-input assembler, and both package and runtime artifacts must use
the same content-addressed store.

`LocalArtifactStore.read_manifest` now optionally enforces its bound during a
no-follow regular-file read, preventing oversized or special-file inputs from
being buffered before integrity checks. The full Strategy Lab v2 package passed
1,057 tests; Ruff passed across `app/strategy_lab_v2` and `strategy_runtime`;
MyPy passed across 323 source files. This validation was run against source
commit `f3d6077752733ce73be7b1d16359b3ce9897ba8e`.

Next: define the frozen event-tape artifact boundary using the platform's
content-addressed Parquet/Arrow artifacts, then hydrate owner-scoped trial
resources and inject canonical instrument/venue/account adapters before binding
the assembled runtime reference into worker evidence and atomic dispatch.
Target-position allocation/risk and broad native product/accounting/report
conformance remain open. No external release or upstream branch blocks this
isolated implementation. Fresh status through the authorized workflow reports
Docker available and ready. The required `full_stack_browser` profile has not
yet been run; it remains a final validation gate, not a current development
blocker. No parallel worktree was accessed or changed.

## 2026-10-02 - Verified frozen event-tape artifact boundary

Added `LocalArtifactStore.open_verified` for seekable streaming access to
content-addressed artifacts. It opens a no-follow regular-file descriptor,
checks the digest before decoding, enforces an optional byte bound, and checks
the same descriptor again after consumption so the resolver does not need to
buffer an entire Parquet/Arrow artifact before integrity verification.

Added `FrozenEventTapeArtifactResolver` and a typed decoder boundary. It selects
series using the same effective preflight semantics as `bind_event_tape`, checks
decoded row counts and series time bounds, projects only strategy-declared
fields, and binds the final immutable tape to the snapshot and SDK manifest.
The decoder is injected deliberately: the provider workstream owns the actual
Parquet/Arrow schema, and this branch does not add a second market-data format
or fetch path. Missing/corrupt artifacts and malformed decoded rows fail
closed.

The Strategy Lab v2 package passes 1,066 tests; Ruff passes and MyPy passes
across 325 source files. The full-stack browser profile has not yet been run;
fresh workflow status says Docker is ready, so this is pending final acceptance
validation rather than an environment blocker. Next is owner-scoped trial
resource hydration, canonical instrument/account adapter injection, runtime
reference binding into worker evidence and atomic dispatch, then portfolio risk
and full Nautilus v2 conformance. Exact-pinned 2.0.0rc5 remains eligible after
that conformance; no stable release wait is required.

Scale boundary still open: `FrozenEventTapeArtifactResolver` currently retains
decoded rows and constructs an in-memory `FrozenEventTape`; the existing
Nautilus runtime bundle serializes that tape into a single JSON input. Verified
artifact reads are chunked, but end-to-end replay is not yet bounded-memory for
very long histories. The next implementation slice must replace this with a
chunked content-addressed runtime data-plane handoff before claiming broad
history-scale readiness.

## 2026-10-02 - Immutable experiment package binding

Experiments now optionally bind each declared strategy-version fingerprint to
one exact immutable `StrategyPackage` fingerprint. The binding is part of the
experiment fingerprint and is preserved by resource normalization/rehydration.
Trial runtime assembly rejects packages that are missing from the experiment
binding or differ from the pinned package, preventing a retry from silently
changing source archives or dependency locks. Draft experiments may remain
unbound; execution fails closed until each strategy version is package-bound.

Validation at source commit `0a257187ae4ae86619257c3c99cf16ed586e5eba`:
1,069 Strategy Lab v2 tests passed, Ruff passed, MyPy passed across 325 source
files, formatting checks passed for the touched files that are formatter-clean,
and `git diff --check` passed. The workstream validator passed before the
implementation commit; it is rerun with this checkpoint.

Nautilus v2 does not require waiting for a stable tag. The exact isolated
`2.0.0rc5` wheel/runtime image and a basic native-engine probe already pass, but
that probe is not the complete platform conformance suite and cannot authorize
authoritative results yet. Prerelease builds remain prohibited from broker
connections and real-capital control. The legacy backend pin remains 1.226.0;
the v2 runtime stays isolated rather than changing that global dependency.

There is no external release blocker to isolated implementation. Provider,
ETF, and TC2000 branch tips are still not ancestors of staging, so consuming
their shared contracts remains gated; this does not block parallel-safe core
work. Docker is ready, while `full_stack_browser` remains a final acceptance
gate. Next implementation context: replace full event-tape and JSON-bundle
materialization with a bounded, chunked content-addressed replay data plane,
then continue owner-scoped resource hydration and runtime dispatch assembly.

## 2026-10-02 - Disk-spooled frozen event-tape stream

Added `FrozenEventTapeArtifactResolver.resolve_streaming(...)`. It verifies
provider-owned source artifacts while decoding rows individually, uses a
bounded-cache SQLite sort spool with unique event identity and canonical event
ordering, then writes ordered canonical NDJSON to a pinned content-addressed
artifact. Event-line size, temporary disk use, and SQLite page cache are
bounded/configurable. The generated `tape_fingerprint` matches the existing
`FrozenEventTape.fingerprint` byte-for-byte; the verifier checks raw artifact
integrity, event ordering, sequence monotonicity, per-dependency counts, and
semantic tape identity before a second pass yields events.

Added `iter_materialized_nautilus_event_records(...)` to feed that verified
stream into the existing engine-neutral Nautilus event adapter one record at a
time, preserving effective event-type, instrument, field, interval, and
snapshot-coverage checks without constructing a `NautilusEventTape` tuple.
This is not yet the end-to-end runtime path: `NautilusTrialAssembly`, the JSON
runtime bundle, worker mount contract, runtime CLI, and strategy-context batch
still materialize complete inputs. Do not claim long-history bounded-memory
readiness until those consumers use the stream directly and exact RC5 replay
parity is demonstrated.

Validation at source commit `df28ac88e9bd2f58915404d76ad4b9c6ca128543`:
1,075 Strategy Lab v2 tests passed; Ruff passed; MyPy passed across 325 source
files; formatter checks passed for the new streaming module and its tests; and
`git diff --check` passed.

No stable Nautilus release is required. Exact-pinned RC5 remains eligible after
the complete platform conformance suite, and prereleases remain barred from
broker connections and real-capital control. Shared provider/ETF/TC2000
contract consumption remains staged behind those branches reaching staging;
it does not block this independent data-plane work. Docker is ready and
`full_stack_browser` remains a final acceptance gate.

Next: extend the content-addressed stream reference through trial assembly and
the isolated worker mount/CLI, then run it through Nautilus's catalog-backed
chunked path while streaming SDK contexts/results. Preserve same-time event
ordering; verify it against exact RC5 before any authoritative activation.

## 2026-10-02 - RC5 streamed strategy contexts on native callbacks

`build_native_strategy_bridge(...)` and the isolated runtime adapter now accept
either the existing serialized invocation batch or a seekable v2 context
stream. Stream bytes are fingerprinted with bounded reads. Before importing
Nautilus, the bridge exhausts a validation pass that authenticates event IDs,
history membership, chronology, same-time coverage, parameter/seed binding,
and canonical native event order. The callback path then reopens the verified
stream and advances one timestamp group at a time, invoking batched contexts
only on the last native callback in that group. Native callbacks are checked
against the exact frozen tape order; the legacy batch input and output
contracts remain available.

The exact isolated Nautilus 2.0.0rc5 image, built with the pinned wheel
`sha256:eab45fafd2312deda1236554c49a9798bfc76bc8465af864878e2f70189ebebe`,
ran the streamed-context path by immutable image ID under no-network,
read-only, capability-dropped, no-new-privileges, and unprivileged-UID
restrictions. Two same-time native quote events yielded one SDK invocation, one
native order, and one open position. The evidence recorded engine version
`2.0.0rc5`, input protocol `context-stream`, and `authoritative: false`; the
execution evidence digest was
`sha256:f72bd113a8d6d2b903a29d0f96a39bdde691d1c2bdae3bb39de2e50f5eb5d14e`.
The immutable local image ID was
`sha256:e7d704d5e7b54f685b3a01ebe4a774285a21572016f97a41a083e3ed8d8c7f14`.

Validation at source commit `bfa77138f00bcd571bcfacbd17132ba14d7c432c`:
1,089 Strategy Lab v2 tests passed; Ruff passed; all four changed Python files
passed format checks; MyPy passed across 325 source files; `git diff --check`
passed; and the RC5 streamed-context probe passed. The source commit was pushed
to `origin/feat/strategy-lab-v2`.

This is an adapter seam, not yet the full bounded-memory runtime: the worker
request and CLI still carry a JSON batch, frozen event/native-event inputs
remain materialized, and native invocation results remain accumulated for the
legacy wire response. Continue by binding the context stream as a verified
content-addressed sidecar through trial assembly, worker mount, and CLI, then
stream results into the artifact path and convert native events to RC5 catalog
chunks. Stable Nautilus v2 is not a blocker; full platform conformance still
gates authoritative results, and prereleases remain barred from broker/live
real-capital control.

## 2026-10-02 - RC5 native-event sidecar and chunked catalog replay

Completed the bounded handoff from frozen event tapes into the isolated runtime.
Trial assembly now emits verified content-addressed strategy-context and native
event sidecars; the worker plan binds and mounts the native sidecar read-only,
and the CLI checks its regular-file type, exact length, and SHA-256 before
streaming it to the adapter. The native sidecar has canonical event ordering,
monotonic native init timestamps for deterministic same-time ordering, bounded
row/stream sizes, record-count validation, and a records digest. The RC adapter
converts records into bounded 10,000-event batches in Nautilus's Parquet catalog
and executes them through `BacktestNode` with configurable replay chunking.
Strategy contexts and invocation results remain streamed; callback context
indexes are replayed from the authenticated rolling histories so two readers do
not race on one file cursor.

The exact pinned Nautilus 2.0.0rc5 image passed the hardened no-network runtime
probe for 10,005 events across the 10,000-record input boundary and 1,000-event
replay chunks. All 10,004 strategy invocation results succeeded. It also passed
the two-event same-time baseline. Both results remain `authoritative: false`;
the probe image ID was
`sha256:775cb0b38fac096bd2058312e4194434f734ab9aa98080d1b0d93821f4491d98`,
built with wheel digest
`sha256:eab45fafd2312deda1236554c49a9798bfc76bc8465af864878e2f70189ebebe`.

Validation at source commit `295262626a280604675ccf2d83f3c30d6013c784`:
1,109 Strategy Lab v2 tests passed; Ruff passed; all 17 changed Python files
passed format checks; MyPy passed across 327 source files; `git diff --check`
passed; and both exact-image RC5 probes passed. Commits `52e7605` and
`2952626` are synchronized with `origin/feat/strategy-lab-v2`.

No external dependency blocks further implementation, and stable Nautilus v2
is not required. AC-NAUTILUS conformance remains incomplete and therefore still
gates authoritative result publication: expand checks for multi-instrument
accounting, native order/fill/cost/report behavior, deterministic replay, and
engine lifecycle. The full-stack-browser profile is a final acceptance gate.
Provider-platform, ETF, and TC2000 contract consumption remains gated on their
approved work reaching staging, but does not block the owned Strategy Lab
runtime work. Pre-release builds remain forbidden from broker connections or
real-capital control.

Next: extend the RC5 conformance matrix and mixed quote/trade/bar catalog probes,
preserving the same isolated, non-authoritative status until the full suite
passes.

## 2026-10-02 - Backtest authority separated from forward parity

The execution gate now has an explicit `BACKTEST_AUTHORITATIVE` scope. It
requires multi-instrument accounting, native order/fill/cost, deterministic
replay, and lifecycle checks, exact isolated v2 pin validation, authorization,
and a sandbox image digest matching the pinned image. It does not wait for
`FORWARD_EVENT_TAPE_PARITY`; `FULL` and `FORWARD_COMPATIBILITY` still require
all checks. Development builds remain ineligible, and release candidates remain
local-only with no broker connection or real-capital control.

The planner now recomputes the conformance report from its evidence before
accepting it, preventing a caller-supplied report from overstating passed
checks. Regression coverage verifies that a parsed RC5 four-check receipt may
feed the backtest-authoritative scope while the global full-suite report remains
incomplete, that a missing simulator check still rejects, that forward scope
still requires parity, and that a forged report is rejected. This changes only
the scope policy; runtime execution evidence remains non-authoritative until the
actual simulator conformance and publication gates pass.

Validation at source commit `881a77e3d4800c2c34ddec2598003fde6eaea7e8`:
1,112 Strategy Lab v2 tests passed; Ruff passed; both changed Python files
passed format checks; MyPy passed across 327 source files; and `git diff --check`
passed. The source commit is pushed to `origin/feat/strategy-lab-v2`.

No external release or workstream dependency blocks continued implementation.
The remaining engine gate is evidence quality: the current image fixture proves
multi-instrument replay and order/account changes but does not yet inspect native
fills, explicit commission/slippage models, and reports with enough detail for
the accepted four-check suite. Forward parity remains a separate forward-only
gate; provider-platform, ETF, and TC2000 contracts remain staging-gated.

Next: strengthen the exact-RC5 native fill/cost/report fixture and bind its
durable receipt to the backtest authority and result-publication path.

## 2026-10-03 - RC5 native fill, cost, and report conformance

The pinned Nautilus `2.0.0rc5` image now exercises the native `OneTickSlippageFillModel`
and `FixedFeeModel`, then reads Nautilus order/fill reports. The isolated image
contains an exactly pinned pandas reporting stack instead of inheriting optional
packages from the legacy backend. Its final image is
`sha256:5b6c4d268f38337b50ec813906f6bbc8fd41895a6ea8b561f601e44e4308a9b8`,
built from the `nautilus_trader-2.0.0rc5` wheel pinned at
`sha256:eab45fafd2312deda1236554c49a9798bfc76bc8465af864878e2f70189ebebe`.

Under a network-disabled, read-only, unprivileged container, both repeated
single-instrument runs reported one order and one fill, filled all 1,000 units,
executed one tick above the `1.10020` ask at `1.10021`, charged the configured
`2.00 USD` fee, and reconciled the cash account to `98,897.79 USD`. The shared
two-instrument account reported two distinct instruments, two complete fills,
`4.00 USD` total fees, and a reconciled balance of `97,795.58 USD`. Deterministic
replay matched, and the engine lifecycle passed.

The actual JSON output was consumed by `NautilusRcFixtureReceipt`; its digest is
`sha256:b233d6aa9953894f65628247455f6b349590c21946fac0a84797e3e9a78eee3e`.
The receipt records four passed simulator checks (multi-instrument accounting,
native order/fill/cost, deterministic replay, and lifecycle), explicitly defers
forward event-tape parity, and remains non-authoritative itself. The scoped
backtest planner can separately authorize local backtests from those four
checks; prereleases remain unable to connect to a broker or control real
capital.

Validation at source commit `f9f646f873149959ecfbba9b51e0f0c2285fb924`:
1,118 Strategy Lab v2 tests passed; Ruff and format checks passed; MyPy passed
across 327 files; and `git diff --check` passed. The implementation commit is
pushed to `origin/feat/strategy-lab-v2`.

Stable Nautilus 2.0 is not a prerequisite, and no external release or workstream
dependency blocks continued implementation. The remaining immediate internal
gate is publication integration: `plan_result_publication()` still requires
the global conformance report itself to be authoritative, so it rejects a
backtest-authoritative scope whose only missing check is forward parity. Result
materialization/publication must also retain exact release channel, wheel/image
digests, conformance identity, and authority scope. Forward parity remains a
separate forward-only check; provider-platform, ETF, and TC2000 contract use
remains gated on those approved workstreams reaching staging. Full-stack-browser
remains the final branch acceptance gate.

Next: bind the backtest-authoritative execution plan and exact engine provenance
through result materialization/publication without weakening the independent
forward parity gate.

## 2026-10-04 - Persist native OOS result manifests

Stable Nautilus 2.x remains unnecessary for local backtesting. The branch-owned
acceptance rule permits an exact-pinned stable or pre-release v2 build after
scope-specific conformance; RC5 has passed the four backtest-authoritative
checks in the isolated runtime. Pre-release builds remain prohibited from
broker connections and real-capital control.

The PostgreSQL result materialization adapter now exposes
`materialize_nautilus_oos()`. It verifies the native account-equity and
execution-report Parquet artifacts, derives the OOS metric set, binds both
artifacts into the result manifest, persists through the existing owner-scoped
attempt key, and distinguishes exact replays from changed-content conflicts.
The adapter regression covers manifest round-trip persistence and replay.

Validation at source commit `d6c9e721069f157ac3b1202a15316d70abdc8056`: all
1,209 Strategy Lab v2 tests passed; Ruff passed; both changed Python files are
formatted; MyPy passed across 342 package sources; and `git diff --check`
passed. Docker conformance was not
rerun for this persistence-only change; the prior isolated RC5 fixture and
native report probe remain the latest engine evidence.

No external release or workstream dependency blocks further implementation.
The current internal integration gap is that the worker terminal evidence
resolver still expects an already-persisted result manifest/publication, while
the OOS materializer is not yet invoked from that completion path. The
authenticated terminal callback also needs a trusted source for the typed
trial/package/portfolio/snapshot graph and exact conformance/provenance inputs;
these are code-owned interfaces to build, not reasons to wait for stable v2.
The full-stack-browser acceptance profile is still outstanding. GitHub push is
not currently possible because the configured SSH key is rejected and
`ssh-askpass` is unavailable; local feature work is unaffected.

Next: connect verified Nautilus terminal files to the owner-authenticated
result context, construct and persist the OOS manifest plus publication plan,
and preserve prerelease/local-only safety boundaries.

## 2026-10-04 - Native OOS average position outcomes (v9)

The native OOS metrics now include currency-scoped mean realized P&L per closed
position, mean winning-position P&L, mean losing-position P&L, and the mean-win
to absolute-mean-loss ratio. Calculations use the same deterministic Decimal
context as the existing native report metrics, include explicit formula/sample
metadata, and withhold values when any OOS-closed position lacks reported P&L.
No average or ratio combines unlike currencies. The metric definition is now
v9, so persisted metric-set identities cannot silently alias the v8 contract.

This checkpoint also reconciles the older OOS-manifest note above with the
current implementation: `create_nautilus_oos_worker_terminal_evidence_resolver`
materializes the verified native result, publishes the output artifacts, and
builds publication evidence; `PostgresWorkerTerminalAdapter` persists the
publication, result manifest, metric set, and terminal completion. The package
suite's terminal success/redelivery coverage exercises that path. The remaining
production composition gap is the API's trusted capability/search-preparation
binding, not terminal result materialization.

Validation at source commit `2aed7030cebf0289494e713cb0fb472cef9dd483`:
all 1,216 Strategy Lab v2 tests passed; Ruff and changed-file formatting passed;
MyPy passed across 344 Strategy Lab sources. The combined backend unit,
integration, and Strategy Lab coverage gate passed 2,867 tests at 83.39%
coverage. Frontend validation passed 923 Vitest tests, the 48-file uPlot
renderer contract, and all 26 visual-acceptance policy assertions.

The Docker Engine and Compose are available (server 29.1.3, Compose 2.40.3),
and the assigned worktree's resource inventory is empty after cleanup. The host
does not have the Docker Buildx CLI plugin: the standard stack-up target fails
at `docker buildx create`, and a local legacy-builder attempt cannot resolve
the frontend Dockerfile's `$BUILDPLATFORM`. Therefore the exact-tip Compose
stack and Playwright browser run remain unverified. The backend/frontend test
stages passed independently; no Strategy Lab code failure was observed. The
unit-only `make test-platform` stage also has a coverage-threshold mismatch
(1,282 unit tests pass, but coverage is 40.57% versus its standalone 55%
threshold); the combined coverage gate above passes the repository's 75%
threshold with the Strategy Lab package tests included.

Exact-pinned Nautilus 2.0.0rc5 remains eligible for local backtesting after its
existing scope-specific conformance; no stable release wait is required, and
pre-release builds remain barred from broker/real-capital control.

Next: compose trusted capability and search-preparation inputs behind the
production API while preserving the isolated preparation boundary and
fail-closed behavior for missing provider, runtime, or conformance evidence.

At the v9 checkpoint, changed workstream records were
`ops/workstreams/feat-strategy-lab-v2/plan.yaml`, `handoff.md`, `session.json`,
and `validation.jsonl`. Its product source commit was
`2aed7030cebf0289494e713cb0fb472cef9dd483`; the v9 checkpoint was subsequently
published and is superseded by the v10 source checkpoint below.

## 2026-10-04 - Native OOS position holding-duration metrics (v10)

Native OOS position results now include reported-duration count and coverage,
mean elapsed holding duration, and median elapsed holding duration. Positions
are selected by `ts_closed` in the half-open OOS scoring window, while the
duration measures their complete `ts_closed - ts_opened` lifecycle, including
positions opened before OOS. Native nanoseconds convert deterministically to
seconds; the median uses the middle observation or the arithmetic mean of the
two middle observations for even samples. Missing opening times remain visible
in coverage and withhold aggregate durations; a null close timestamp is treated
as an open position, and reversed open/close timestamps fail closed. Metric
identity advanced to v10 so stored metric sets cannot alias the prior contract.

Validation at source commit `82bbe659570a058759525ae3c47230247619a415`:
all 1,219 Strategy Lab v2 tests passed; all 11 native-result-metric tests
passed; Ruff passed; the changed result-metrics implementation and test files
passed format-check; MyPy passed across all 344 Strategy Lab sources. The
combined backend unit, integration, and Strategy Lab coverage gate passed
2,870 tests at 83.40% coverage. Post-test Docker accounting found no assigned
containers, images, volumes, or Testcontainers sessions. The full-stack
Compose/browser gate remains separately unverified because this host lacks the
Docker Buildx CLI plugin; this does not block continued backend implementation.

The `metrics.py` edit is only the v10 metric-definition constant. Its current
Ruff formatter diff consists of pre-existing unrelated reflows, which were
preserved; Ruff lint and MyPy both pass for the changed source.

The next product step remains composing the production API's trusted capability
and search-preparation inputs without crossing provider-platform staging
boundaries or accepting client-supplied execution evidence.

## 2026-10-04 - Native OOS position P&L quantiles (v11)

Native closed-position outcomes now include currency-scoped nearest-rank P&L
quantiles p05, p25, p50, p75, and p95. Each quantile sorts only the reported
native realized P&L observations for that currency and records `ceil(p*n)`,
one-based rank, and no interpolation in its formula metadata. No FX conversion
or mixed-currency distribution is performed. If any OOS-closed position lacks
reported realized P&L, the quantiles are null with the same explicit completeness
reason as the related position-outcome aggregates. The metric definition is
v11, giving the persisted metric set a new immutable identity.

Release-policy reconciliation: the current human direction and this branch's
acceptance contract permit the exact-pinned Nautilus 2.x pre-release after
scope-specific conformance; no stable upstream label is required. The saved
Codex goal text still says "after stable v2 conformance" and is stale on this
point. Do not treat that wording as a release dependency: RC5's four local
backtest fixture checks have passed, while formal result provenance and the
separate forward event-tape parity gate remain applicable. Pre-releases remain
barred from broker connections and real-capital control.

At source commit `ca02dcc62a037770e0fb89d6ff93ffac97855d8c`, the complete
Strategy Lab v2 suite passed 1,219 tests, including all 11 native result-metric
tests. Ruff passed, the changed native result-metric and test files passed
format-check, and MyPy passed across 344 Strategy Lab sources. The separate
Docker-backed integration suite passed 369 tests; its subsequent resource audit
found no branch-owned containers, images, volumes, or Testcontainers sessions.

The combined backend coverage target did not complete on this run: pytest exited
152 at 37% without reporting an assertion failure, and the target's cleanup
completed. A separate unit-only diagnostic reached 11% then emitted no further
progress for about three minutes; it was interrupted (exit 130) to avoid leaving
a silent run holding the work. Neither is recorded as a passing full backend
coverage gate. The full Compose/browser gate remains unverified because Docker
Buildx is absent; backend implementation continues independently.

Next: compose trusted production API capability and search-preparation inputs,
then continue the remaining worker and forward acceptance without crossing
provider-platform, ETF, or TC2000 staging boundaries.

Changed source paths: `backend/app/strategy_lab_v2/metrics.py`,
`backend/app/strategy_lab_v2/nautilus_result_metrics.py`, and
`backend/app/strategy_lab_v2/tests/test_nautilus_result_metrics.py`.
Changed workstream paths: `ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`handoff.md`, `session.json`, and `validation.jsonl`.

## 2026-10-04 - Trusted capability-preflight composition (v1)

Added `CapabilityPreflightService` as the typed API-side composition of
capability requests. It strictly parses requested product/data/execution
semantics and explicit degraded substitutions, checks the supplied request
digest, obtains capability cells and the execution binding only from injected
trusted host resolvers, then runs the existing data and engine preflight and
builds the persisted API summary. The request schema rejects cells, engine
build claims, and any other unrecognized evidence fields; missing coverage
remains unsupported, and degraded results remain ineligible for rankings and
authoritative publication. Sync and async host resolvers are both supported.

This advances the production seam without claiming the API is fully live: the
registered default PostgreSQL adapter is still created without the host
capability resolvers and therefore returns the existing fail-closed 501. The
host must still bind the provider-platform-backed coverage resolver and exact
Nautilus conformance binding. Search dispatch likewise still needs its trusted
market/runtime/worker preparation context; none is accepted from the client.
Provider/ETF/TC2000 shared-contract gates remain unchanged, and stable Nautilus
2.x remains unnecessary.

At source commit `7bdddfa64e4d1d1cf641f03eff202e3358037202`, all 1,224 Strategy
Lab v2 tests passed. The combined backend coverage gate passed 2,875 tests at
83.41%; package Ruff passed, the new source/test passed Ruff format-check, and
MyPy passed across all 346 Strategy Lab package/runtime sources. The
post-run resource audit found zero containers, images, volumes, or active
Testcontainers sessions. The full Compose/browser profile remains blocked only
by the missing Docker Buildx CLI plugin; the combined coverage gate is now
green again.

Changed source paths: `backend/app/strategy_lab_v2/capability_preparation.py`,
`backend/app/strategy_lab_v2/tests/test_capability_preparation.py`, and
`docs/strategy-lab-v2.md`.
Changed workstream paths: `ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`handoff.md`, `session.json`, and `validation.jsonl`.

Next: bind these typed resolvers to the local host's canonical coverage and
exact engine-conformance sources, then compose the trusted search-preparation
context without executing preparation inline in the API event loop.

## 2026-10-04 - Registered local API host-binding factory (v1)

Committed and pushed `ce14d39e4bc8d00387ea1466e6437f7ab713d1ff`. The registered
PostgreSQL adapter now accepts `STRATEGY_LAB_V2_API_BINDINGS=module:factory`;
the synchronous factory receives the shared async session factory and the
single persistence bundle, and returns typed asynchronous capability-preflight
and/or search-dispatch bindings. Search dispatch is modeled as a resolver for a
durable dispatch result, so production hosts can proxy preparation to an
isolated local service instead of materializing a trial in FastAPI. An absent
setting preserves the fail-closed 501. This provides the production composition
point but does not claim that canonical provider or engine sources are already
configured.

Validation at this source tree: all 1,229 Strategy Lab v2 tests passed; Ruff,
changed-file format checking, MyPy across 346 package/runtime sources, and
`git diff --check` passed. The combined backend coverage gate had passed 2,880
tests at 83.41% on the same code tree. The subsequent assigned-worktree
resource audit found zero containers, images, volumes, or Testcontainers
sessions. Docker Buildx is still absent, so the exact-tip Compose/browser gate
remains the only environment-limited validation; `docker buildx version`
returns `docker: unknown command: docker buildx`.

Stable Nautilus 2.x is not a prerequisite. The exact-pinned RC5 track remains
eligible after scope-specific conformance; pre-releases remain barred from
broker/real-capital control, and forward shadow separately requires event-tape
parity. The immediate implementation gap is a concrete local host factory
using trusted provider coverage and exact engine/conformance inputs plus an
isolated search-preparation service/client. Keep missing canonical provider
coverage unsupported rather than inventing capability cells, and honor the
provider-platform/ETF/TC2000 staging boundaries.

Next: compose the concrete local host dependencies where their authoritative
contracts exist, keep the API fail-closed for unavailable evidence, and
continue worker/forward acceptance. Run the complete exact-tip Compose/browser
profile once a Buildx-capable Docker CLI is available.

Changed source paths: `backend/app/strategy_lab_v2/application.py`,
`backend/app/strategy_lab_v2/tests/test_application.py`, and
`docs/strategy-lab-v2.md`. Changed workstream paths:
`ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-04 - Native signed fixed-per-fill fee reconciliation

The engine-neutral venue contract now optionally carries a typed, immutable,
fingerprinted fixed-per-fill commission/rebate definition. Its currency must be
funded by the initial account cash, its canonical wire representation is bound
into the runtime bundle digest, and the isolated runtime materializes only this
platform-controlled deterministic fee model (not user-supplied callbacks).
The engine input contract advanced to v6. Nautilus RC5's native `FeeModel`
subclass applies both positive commissions and signed rebates to actual fills.

The exact-source isolated RC5 build and network-disabled fixture suite passed.
Native evidence joined four fills/orders/trade IDs across two closed cycles,
including an archived position snapshot. With USD 1.00 per fill, native gross
P&L was USD 395.00, cost deductions USD 4.00, and net USD 391.00. With a USD
1.00 rebate per fill, gross remained USD 395.00, cost deductions were zero,
rebates USD 4.00, and net USD 399.00; both cases reconciled exactly to native
account P&L. Overall evidence remains `authoritative: false` until the complete
platform authority and data-capability gates pass; RCs remain prohibited from
broker/real-capital control and forward shadow remains separately gated.

Exact RC5 evidence: source `sha256:bfe2ba4911ed05975c702622c99e39858bb485de38b57160b73317f4cb48625a`,
runtime image `sha256:dd746072b14b690d04563ca5b7cbd162eeac2b6cc31554229395fe2f202227fe`,
receipt artifact `sha256:608645a0f7d9d60b0b84012ab32959738f1d79fc0d15475ebcc8c9c422f0603`,
and conformance fingerprint
`sha256:34d6527b28bff9cb34c2ca229c6ddbb1dbace169ee5693d4496be95ca700c307`.
The full Strategy Lab suite passed 1,299 tests, including local-socket RPC
coverage. Ruff passed package checks, all 13 changed Python files passed
format-check, MyPy passed across 359 sources, and `git diff --check` passed.

No stable Nautilus 2.x release is required by the plan: exact-pinned pre-release
builds are eligible after conformance. Docker Buildx remains a host-only gate
for final Compose/browser validation; provider/ETF/TC2000-owned shared contracts
remain staging-gated. Neither blocks continuing package-owned work.

Next: continue broad metric acceptance, any remaining domain-backed mutation
flows, worker recovery/scaling, and persistent broker-free forward-shadow
correctness. Keep data capability fail-closed until canonical upstream
contracts are available, and run the full Compose/browser gate when Buildx is
available.

Changed source paths: `backend/app/strategy_lab_v2/nautilus_engine_input.py`,
`backend/app/strategy_lab_v2/nautilus_rc_fixture_probe.py`,
`backend/app/strategy_lab_v2/nautilus_runtime.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_adapter.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_adapter_probe.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_bundle.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_data.py`, and their focused tests.
Changed workstream paths: `ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-04 - Native component P&L RC5 reconciliation

Completed the in-progress component-attribution slice against the actual
Nautilus `2.0.0rc5` report schema. Position cycles expose their order/trade
identity through retained `OrderFilled` events rather than a top-level
`client_order_ids` field, so attribution now validates event identities against
the native fill/trade reports and rejects incomplete or inconsistent joins.
The exact-image probe exercises two closed cycles, an archived/reopened
position, USD-native P&L, and shared-account equity reconciliation.

The isolated, network-disabled source build passed with source digest
`sha256:972d8fb6811639d0b319963cdaf8bf2884f1c6599279372f34bad2ca3a83331f`,
image digest
`sha256:626b4edfb96240026d65e61794782290fb13021da7cfb90933d9975ba0fcfde8`,
and receipt artifact
`sha256:07f4b67f5a2401cdfcc09ff46fc2e5d6f9296dd342f25458f6eb2351114d956a`.
The component probe recorded two closed cycles, four orders/fills/trade-ID
joins, one archived snapshot whose identity differs from fill position IDs,
and exact account reconciliation at USD 395.00 gross/net. This evidence remains
non-authoritative release-candidate evidence; it does not grant broker or
real-capital control, nor forward-shadow authority.

Validation passed: 1,287 Strategy Lab package tests plus 7 isolated
Unix-socket RPC tests; Ruff, formatting for all eight changed Python files,
MyPy across 365 package/runtime sources, and `git diff --check`. The first
package run exposed stale synthetic fixture schemas and the first native run
exposed a missing initial event-context group; both were corrected and the
complete gates rerun successfully.

No stable Nautilus release is required by this branch plan. The saved goal's
wording still says “after stable v2 conformance,” which is stale relative to
the durable plan's exact-pinned stable-or-pre-release rule; treat that as a
goal-metadata inconsistency, not an implementation blocker. Current blocker is
none. Next: continue broader metric coverage, worker recovery/scaling, and
persistent broker-free forward-shadow acceptance. Docker Buildx remains an
environment limitation only for the final full Compose/browser profile.

Changed source paths: `backend/app/strategy_lab_v2/nautilus_component_pnl.py`,
`backend/app/strategy_lab_v2/nautilus_rc_fixture_probe.py`,
`backend/app/strategy_lab_v2/nautilus_runtime.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_adapter_probe.py`, and their
focused runtime/conformance/execution tests. Changed workstream paths:
`ops/workstreams/feat-strategy-lab-v2/handoff.md` and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-04 - Backtest-scoped Nautilus conformance binding

Committed and pushed `fa0cb4c3d5bf6a7869e1be05d4866d298c384237` and
`5d2a93797ea8240682e0cf5120379628fd99588e`. The first adds a typed binding
from a verified Nautilus conformance resolution to authoritative local
backtests only when the exact isolated v2 release pin and all four simulator
checks pass. The binding still requires the trusted host to declare product,
execution-model, and account-model support; it does not infer those from the
fixtures. The second composes that binding, conformance report/evidence, and
worker runtime through `NautilusTrialPreparationContext`, requiring the
runtime image digest to equal the release pin before search dispatch can be
prepared. RC authority is explicitly limited to `BACKTEST_AUTHORITATIVE`;
forward/full scopes retain their independent gates.

The full Strategy Lab package suite passed 1,234 tests at `5d2a937`; Ruff,
formatting, MyPy across 346 sources, and `git diff --check` passed. The
combined backend coverage gate passed 2,885 tests at 83.42% (above the 75%
threshold). The repository cleanup completed with no assigned containers,
images, or retained volumes. A separate read-only, network-disabled container
run of local image digest `sha256:e39663e985471102fc735f87e43e720421deb8ed23cdd7896c6c2f49a88fd6fd`
passed the RC5 engine fixtures; the output correctly retains
`authoritative: false` for overall conformance and defers forward event-tape
parity. That existing local image has no source-build label, so this run is
runtime evidence only and is not claimed as a reproducible image-build gate.

Stable Nautilus 2.x is not a dependency. The remaining concrete integration
gap is a production local host factory that loads exact conformance evidence
from an operator-controlled pinned source and supplies canonical provider
coverage/market metadata to isolated search preparation. Keep those data
capabilities unsupported until the provider-platform contract reaches its
approved staging boundary; do not invent support. The preparation context
contract now binds the RC evidence safely, but the dedicated local preparation
service/client and production factory are not yet registered. Docker Buildx
still limits only the full Compose/browser profile.

Next: add the local pinned conformance-evidence source and dedicated
preparation-process/client composition, while preserving a fail-closed
capability result until canonical provider coverage and instrument metadata are
available. Then continue through remaining worker, data, portfolio, metrics,
and forward acceptance; do not narrow the goal to this gate.

Changed source paths: `backend/app/strategy_lab_v2/conformance_fixtures.py`,
`backend/app/strategy_lab_v2/tests/test_conformance_fixtures.py`,
`backend/app/strategy_lab_v2/search_dispatch_preparation.py`, and
`backend/app/strategy_lab_v2/tests/test_search_dispatch_preparation.py`.
Changed workstream paths: `ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

The branch session checkpoint passed under the existing claim. Its resource
snapshot was complete and empty (no owned containers, volumes, or active
Testcontainers sessions). The helper's dirty-path formatter dropped the first
character of `ops/.../handoff.md`; the session record was corrected to list the
exact four branch-workstream paths changed in this checkpoint. The enclosing
workstream commit is verified separately from the recorded implementation SHA.

## 2026-10-04 - Host-factory lifecycle validation (v1)

Committed and pushed `9137be084d4c642074f99eae5e164677be309385`. The adapter
now rejects coroutine host factories before calling them and closes a coroutine
returned by a misdeclared synchronous factory before raising, preventing an
un-awaited-coroutine leak during invalid startup configuration. The full
Strategy Lab suite passed 1,231 tests; focused application tests passed 24;
Ruff, formatting, MyPy across 346 package/runtime sources, and `git diff
--check` passed. The combined backend coverage gate was not rerun at this small
follow-up tip; its latest 2,880-test/83.41% pass was at the preceding source
commit `ce14d39e4bc8d00387ea1466e6437f7ab713d1ff`.

The substantive next gap remains a concrete local host composition: trusted
provider coverage cells, exact Nautilus conformance binding, and isolated
search-preparation context/service. The API remains fail-closed until those
inputs are available; no stable Nautilus release is required. Buildx still
limits only the exact-tip Compose/browser profile.

The active session checkpoint passed at 2026-10-04T10:29:09Z; resource
accounting remained complete with zero assigned containers, volumes, or
Testcontainers sessions. The helper's truncated `ps/.../handoff.md` path was
corrected to the actual `ops/.../handoff.md` path in the session record.

Changed source paths: `backend/app/strategy_lab_v2/application.py`,
`backend/app/strategy_lab_v2/tests/test_application.py`, and
`docs/strategy-lab-v2.md`. Changed workstream paths:
`ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-04 - Scope-qualified Nautilus release-candidate authority

The branch plan and execution/publication policy now consistently permit an
exact-pinned stable or release-candidate Nautilus v2 build to publish local
simulation results after the applicable conformance checks pass. Backtests
require the four backtest checks. Broker-free full/forward simulation requires
all five checks, including canonical forward event-tape parity; a stable
release label is not an additional gate. Prereleases remain prohibited from
broker connections and real-capital control. This resolves an old conflict
between the workstream plan and saved goal/session wording; the latter is stale
execution metadata and must not reintroduce a stable-only gate.

The current exact RC5 fixture receipt still defers event-tape parity, so RC5
may qualify for authoritative local backtests but is not yet qualified for
full/forward scope. The new tests exercise both cases and bind full-scope result
publication to the complete five-check report. Implementation commit
`ae9e61752bcbe4391919d42a81ae39d6645f7a83` is pushed to
`origin/feat/strategy-lab-v2`.

Validation: the Strategy Lab package suite passed 1,334 tests with one local
Unix-socket test deselected under the default sandbox; that test separately
passed with scoped socket permission, for 1,335 passing tests total. Ruff,
Ruff format, targeted MyPy over five changed production modules,
`git diff --check`, and the workstream validator (30 records) passed. The
required `full_stack_browser` profile remains environment-limited: `docker
buildx version` reports an unknown command and `docker info` cannot access
`/var/run/docker.sock`. No Docker-backed claim is made.

There is no external release dependency blocking feature work. The immediate
product gap remains producing exact attempt-, portfolio-, OOS-window-, and
calendar-bound session-close equity intervals in ordinary result
materialization. Broader unfinished work includes domain-backed mutation
flows, production local host/search-preparation composition, worker recovery
and scaling, and persistent broker-free forward correctness. Shared provider,
ETF, and TC2000 consumption remains gated only for overlapping paths until
those workstreams reach staging. Options/derivatives admission stays
fail-closed until canonical event-time Greeks/delta and settlement evidence is
available.

Changed source paths: `backend/app/strategy_lab_v2/conformance.py`,
`backend/app/strategy_lab_v2/contracts.py`,
`backend/app/strategy_lab_v2/engine_execution.py`,
`backend/app/strategy_lab_v2/result_materialization.py`,
`backend/app/strategy_lab_v2/result_publication.py`, and their focused tests.
Changed workstream paths: `ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`ops/workstreams/feat-strategy-lab-v2/session.json`,
`ops/workstreams/feat-strategy-lab-v2/handoff.md`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-04 - OOS session-close equity result path (v1)

This is the single implementation context closed by the source commit below.
Exact native OOS
session-close equity observations are now carried from the Nautilus bridge
through the isolated runtime and ordinary result materialization. The runtime
bundle binds the frozen session calendar and explicit annualization basis; the
bridge samples only after the complete same-time event group and records its
final native event index. The owner-side runner revalidates calendar, OOS
bounds, and exact final event index against the authenticated tape. Expected
versus observed close labels are persisted without interpolation or bridge
marks, and missing intervals withhold cadence-sensitive risk metrics. The
generated artifact remains attempt-, portfolio-, OOS-window-, engine-evidence-,
and calendar-bound and is published with the other terminal artifacts.

The implementation context owns these source and test paths:
`backend/app/strategy_lab_v2/nautilus_calendar_wire.py`,
`backend/app/strategy_lab_v2/nautilus_session_equity.py`,
`backend/app/strategy_lab_v2/nautilus_equity_trace.py`,
`backend/app/strategy_lab_v2/nautilus_result_materialization.py`,
`backend/app/strategy_lab_v2/nautilus_result_metrics.py`,
`backend/app/strategy_lab_v2/nautilus_runner.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_adapter.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_bundle.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_cli.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_protocol.py`,
`backend/app/strategy_lab_v2/nautilus_strategy_bridge.py`,
`backend/app/strategy_lab_v2/nautilus_trial_assembly.py`,
`backend/app/strategy_lab_v2/nautilus_trial_materializer.py`,
`backend/app/strategy_lab_v2/nautilus_worker_terminal.py`,
`backend/app/strategy_lab_v2/tests/test_nautilus_runtime_adapter.py`,
`backend/app/strategy_lab_v2/tests/test_nautilus_runtime_cli.py`,
`backend/app/strategy_lab_v2/tests/test_nautilus_session_equity.py`,
`backend/app/strategy_lab_v2/tests/test_nautilus_strategy_bridge.py`,
`backend/app/strategy_lab_v2/tests/test_nautilus_trial_assembly.py`,
`backend/app/strategy_lab_v2/tests/test_nautilus_trial_materializer.py`, and
`backend/app/strategy_lab_v2/tests/test_result_materialization.py`.

Validation on the final source state: 88 focused runtime/materialization tests
passed, and the complete Strategy Lab v2 package suite passed 1,342 tests.
Ruff, Ruff format, MyPy across 14 production modules, and `git diff --check`
passed. The updated branch workstream also validated all 30 records. The final
`full_stack_browser` profile remains unavailable because Docker Buildx is
absent; Docker API access was available only under scoped elevated validation
(the default sandbox denies `/var/run/docker.sock`). No Compose/browser claim
is made. The 2.x release-candidate path
remains valid for local backtests after four checks; RC5 has not passed the
fifth forward event-tape parity check. Stable upstream release labeling is not
a blocker.

Review found and fixed one zero-observation wire edge: a configured calendar
now emits an explicit empty session-close list, allowing the owner to persist
expected/missing close labels instead of rejecting an omitted field. The
runtime-adapter regression test covers configured-empty versus unconfigured.

Operational resume state is also dirty in
`ops/workstreams/feat-strategy-lab-v2/session.json`; this session owns that
checkpoint together with this `ops/workstreams/feat-strategy-lab-v2/handoff.md`
record. The validated source changes are complete in commit
`d86c70bd1d8bab68e6ec5684d3ecc9e8dcfc9e3e`, pushed to
`origin/feat/strategy-lab-v2`; its 21-file source/test boundary is separate
from this operational checkpoint. The source commit is independently verified
against the remote ref. This operational context updates the plan, session
state, handoff, and append-only validation journal with that exact result and
the next action. After its own commit/push, verify a clean synchronized
boundary before starting the next implementation context: owner-authorized
domain mutation flows, then worker recovery/scaling and persistent broker-free
forward-shadow correctness. Options admission remains fail-closed pending
canonical event-time Greeks/delta and settlement evidence; shared
provider/ETF/TC2000 paths remain staging-gated.

The session helper's dirty-path formatter dropped the first character from the
handoff path; the persisted `session.json` list is corrected to exact paths.
Do not modify shared workflow scripts from this feature branch. The session is
now marked active under the resumed claim, and its plan hash, implementation
SHA, remote SHA, blocker, and next action are refreshed. The first checkpoint
passed at `2026-10-04T22:13:40Z` on a clean boundary with
`HEAD=origin/feat/strategy-lab-v2=4ff5d8064be963788117bf266bb3439a5d79623a`.
Docker API access is available under the scoped elevated check (server
29.1.3), but `docker buildx version` still reports an unknown command, so the
full Compose/browser profile remains unrun.

## 2026-10-04 - Owner-scoped typed domain identity reservation

The typed resource-create seam now binds server-generated API resource IDs to
the authenticated owner and atomically reserves each `(owner, resource type,
domain fingerprint)` alongside its immutable resource aggregate. A same-owner
alias create for an already-persisted StrategyVersion is rejected before it
can make fingerprint-based trial-graph hydration ambiguous. Identical domain
content can still be independently owned by another principal; its generated
resource ID and reservation are owner-scoped. Exact idempotent retries include
the identity reservation in the existing aggregate transaction receipt.

This preserves the immutable-domain model: strategy/package/portfolio/etc.
changes create new versioned identities; no generic in-place update route was
added. Mutable lifecycle changes continue to use their dedicated owner-scoped
commands. The source change owns `backend/app/strategy_lab_v2/application.py`,
`backend/app/strategy_lab_v2/tests/test_application.py`, and
`docs/strategy-lab-v2.md`.

Validation: the Strategy Lab v2 package suite completed with 1,341 passing
tests; the only default-sandbox denial was the existing Unix-domain-socket
test, which passed in a scoped rerun (1,342 passing in total). The final
identity/replay application regression passed, the PostgreSQL aggregate-store
suite passed 6 tests, Ruff and MyPy passed, and `git diff --check` was clean.
The code/documentation change is commit
`2d7edd0e657d5fb8264e070045a291ec7cc1c941`, pushed to
`origin/feat/strategy-lab-v2`. The worktree was clean and synchronized before
this separate operational checkpoint.

The current Nautilus release-candidate path is not blocked by stable labeling:
the exact RC5 fixture receipt records the four local-backtest checks as passed;
full broker-free forward scope still needs canonical event-tape parity as its
fifth check. The saved Codex goal's stable-only wording is stale execution
metadata; the branch-owned plan and session objective govern continuation.
Neither that release label nor Docker Buildx blocks further implementation.
Buildx remains an environment hold only for the final Compose/browser profile.
Provider, ETF, and TC2000 dependencies gate reconciliation only on overlapping
shared paths until their branches reach staging.

Next implementation context: assemble the owner-scoped frozen trial graph into
an exact-pinned RC5 worker input and connect isolated execution to authoritative
result publication. Begin in `nautilus_trial_assembly.py`,
`nautilus_trial_materializer.py`, and the dedicated worker composition/tests;
preserve the rule that the simulator never acquires market data. Continue later
with worker recovery/scaling and forward event-tape parity. Do not wait for a
stable Nautilus label or claim Compose/browser validation until Buildx is
available.

## 2026-10-04 - Multi-strategy authorization and OOS conflict contract

The search-dispatch resolver previously materialized every portfolio component
but authorized only `experiment.strategy_fingerprints[0]`. For portfolios with
multiple distinct strategies, the worker runtime request carried the aggregate
`strategy-source-set.v1` digest while `ExecutionAuthorization` carried only the
primary strategy digest; worker-request composition therefore rejected the
trial before dispatch. A regression reproduced that exact failure. Source-set
validation now binds all component strategy fingerprints and source digests,
preserves the prior single-strategy digest, and carries the full accepted
validation result from package resolution through materialization into dispatch
authorization. Commit `c5106e8c7f26c96e469657a4c708474989a97f3e` is pushed to
`origin/feat/strategy-lab-v2`.

The full Strategy Lab package suite then reported 1,344 passing tests; its only
default-sandbox failure was the Unix-domain-socket RPC test, which passed in a
scoped rerun (1,345 total passing). Ruff check/format passed, and focused MyPy
passed for the changed source modules. The branch-wide MyPy command still
reports seven test-annotation errors across five untouched Strategy Lab test
modules; no production-source errors remain after the OOS fix below.

The PostgreSQL OOS-result adapter also returned its wrapper object on the
pre-existing-result conflict path instead of the declared
`ResultMaterializationResolution`. It now returns the wrapped typed resolution;
a conflict-path regression verifies the public result type and rejection
reason. The focused OOS persistence test, focused production-module MyPy, and
Ruff check/format pass. Commit
`cc76aafa8e2bc92132607d2c48546e1536247f7d` is pushed to
`origin/feat/strategy-lab-v2`.

The exact-pinned RC5/stable release policy is unchanged: no stable release tag
is required for authoritative local backtests after the four backtest checks.
Forward parity remains a separate fifth check. Next, continue the
backtest-worker-to-publication acceptance path and close the full MyPy test
annotations; the production frozen-series/context binding must consume the
provider-platform contract only after that approved work reaches staging. The
missing Docker Buildx plugin still limits only the final Compose/browser gate.
This checkpoint updates `ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`, and
`ops/workstreams/feat-strategy-lab-v2/session.json`.

## 2026-10-05 - Multi-strategy identity through persisted search dispatch

The owner-scoped PostgreSQL search-dispatch regression now carries a validated
two-strategy source-set digest through admission and worker handoff, reads back
the exact authenticated worker payload bytes, and verifies idempotent replay
retains the same payload digest. This closes the previously uncovered boundary
between multi-strategy authorization and durable dispatch; it does not yet
exercise graph hydration and terminal publication together in one vertical
test. Commit `4084b1489b76a869d600fb7b21da825f85c05609` is pushed to
`origin/feat/strategy-lab-v2`.

Validation at that code commit: the complete Strategy Lab v2 package passed
`1,345/1,345` tests, including the local Unix-socket worker test under scoped
local-socket permission. The focused dispatch test file passed 5/5; Ruff check,
Ruff format check, focused MyPy for the changed test module, and `git diff
--check` passed. No production code changed in this increment. Branch-wide
MyPy still has seven annotation errors in five untouched test modules; no
production-source errors were reported in the prior complete run.

Current next step: connect the real owner-hydrated immutable multi-component
trial graph through preparation and persisted dispatch to isolated worker
terminal publication and exact replay. Continue recovery/scaling and forward
event-tape parity after that. There is no Nautilus stable-release blocker:
exact-pinned RC5 is qualified for authoritative local backtests after the four
backtest checks. Forward shadow still needs event-tape parity; prereleases may
not connect to brokers or control real capital. Canonical provider context
binding remains staging-gated. The final Compose/browser gate is environment-
limited because Docker Buildx is absent and this session cannot access the
Docker socket. Options orders remain fail-closed pending canonical event-time
Greeks/delta and settlement evidence.

This workstream checkpoint updates the branch-owned
`ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`. The implementation
SHA above is the last code checkpoint; the operational checkpoint commit is
verified from Git after publication.

## 2026-10-05 - Multi-strategy worker-service terminal replay

The owner-hydrated multi-strategy dispatch boundary is now paired with a
terminal-path regression that passes a release-candidate worker result through
`DedicatedStrategyWorkerService` into `PostgresWorkerTerminalAdapter`. A
redelivery with a later service observation time replays the stable terminal
receipt, result completion, artifact plan, and worker settlement. The process
executor and adapter persistence ports are deterministic test doubles; this is
not a Docker/Nautilus process or real PostgreSQL integration run. Commit
`7ac0c924a6e6ba16ea28a4e67d3f31f60c43b12d` is pushed to
`origin/feat/strategy-lab-v2`.

Validation at that code commit: the full Strategy Lab v2 package passed
`1,346/1,346` tests in 42.76 seconds, including the local Unix-socket worker
case under scoped local-socket permission. The multi-strategy terminal replay
test passed directly; Ruff, Ruff format, focused MyPy, and `git diff --check`
passed for the changed test file. The earlier owner-hydrated two-strategy
regression separately proves materialization through PostgreSQL dispatch and
payload replay; its SQL session is a deterministic adapter fake, not a live
database.

Next: compose the production Postgres dispatch-payload loader, authenticated
worker-handoff materializer, isolated process runner, and persistence-bundle
terminal writer into one ACK-after-publication integration path, then exercise
recovery/scaling and forward parity. No Nautilus stable-release blocker exists:
exact-pinned RC5 may publish authoritative local backtests after the four
backtest checks. Forward shadow separately needs event-tape parity, and no
prerelease may connect to brokers or control real capital. Provider-owned
canonical context remains staging-gated. Docker Buildx is absent and the
default session cannot access the Docker socket, so final Compose/browser
acceptance remains environment-limited. Options orders remain fail-closed
without canonical event-time Greeks/delta and settlement evidence.

## 2026-10-05 - Persisted worker path through result publication and ACK

The multi-strategy RC5 worker regression now drives the production
`create_search_dispatch` callback factory. It loads the dispatch record with
`PostgresSearchDispatchAdapter`, loads the serialized worker handoff with
`PostgresSubmissionDispatchAdapter`, authenticates and hydrates the exact
owner-scoped trial graph, and passes the decoded request to the isolated
process-executor seam. `PostgresWorkerTerminalAdapter` then publishes the
authoritative result using deterministic persistence-port doubles. A shared
timeline asserts terminal persistence returns before the Redis `XACK`; the
subsequent redelivery replays the same result/completion/artifact/settlement
identity. The SQL session and process are deterministic fakes, so this does not
claim live PostgreSQL, Redis, or Nautilus-container validation.

Commit `7124ddec9c3a000870cdf41c956d53a07a01786d` contains this regression.
The complete Strategy Lab v2 package passed `1,346/1,346` tests in 48.69
seconds with scoped access for the test that binds a Unix-domain socket under
pytest's temporary directory. Ruff check/format, focused MyPy, and
`git diff --check` passed. The local full-stack preflight confirms Docker
Buildx is not installed and the default session cannot access
`/var/run/docker.sock`; no Compose/browser test is claimed.

Next: extend this worker lifecycle path to cover pending-entry reclaim and
crash/terminal-write failure recovery, ensuring dispatch, capacity settlement,
result publication, artifact finalization, and ACK remain idempotent. There is
no stable Nautilus release blocker: exact-pinned RC5 passed the four local
backtest checks and is permitted by the current branch policy. Forward shadow
still needs event-tape parity; prereleases cannot connect to brokers or control
real capital. Provider/ETF/TC2000 shared contracts remain staging-gated, while
domain-backed mutation flows, metrics, forward correctness, and final
Compose/browser acceptance remain unfinished.

## 2026-10-05 - Reclaim after ambiguous terminal commit

The joined worker acceptance test now injects a lost terminal response after
`PostgresWorkerTerminalAdapter` has committed its result. The first delivery is
left unacknowledged, then Redis `XAUTOCLAIM` reclaims the pending entry. The
worker re-executes the same immutable attempt, terminal persistence returns the
same receipt/result/artifact/settlement identities, and only then does the
transport ACK. A subsequent delivery also replays without duplicating result
or settlement rows. The SQL session, Redis transport, terminal persistence
ports, and process executor remain deterministic fakes; real Docker,
PostgreSQL, Redis, and Nautilus-process evidence is still outstanding.

Commit `552f35616275be64fdb6850a4f7618ac998907f1` contains this regression.
The complete Strategy Lab v2 package passed `1,346/1,346` tests in 25.25
seconds with scoped local Unix-domain-socket access. Ruff, Ruff format, focused
MyPy, and `git diff --check` passed. The next step is to compose this worker
path through `run_strategy_lab_v2_worker` and prove startup/migration gating,
runtime closure, and bounded restart behavior before moving on to the
domain-backed mutation flows. RC5 remains permitted for four-check local
backtests; there is no stable-release wait condition.

## 2026-10-05 - Worker recovery through the production entrypoint

The persisted multi-strategy worker regression now drives three independent
`run_strategy_lab_v2_worker` lifecycles with the production search-dispatch
callback factory and `RedisDispatchRuntime`. The first lifecycle commits the
terminal result but loses its response, so the entry stays pending. The next
startup replays the migration, reclaims the entry, returns the stable terminal
receipt, and only then ACKs it. A third startup/redelivery replays without
duplicating completion or settlement state. Assertions also cover signal
cleanup and runtime closure on every lifecycle. The migration decision is
`APPLIED` once and `REPLAY_EXISTING` on both restarts.

This is a deterministic integration across the production entrypoint,
callback composition, Redis worker/runtime, and terminal persistence adapter;
the SQL, Redis client, terminal persistence ports, and Nautilus process remain
test doubles. It does not claim live PostgreSQL/Redis/container validation.
Commit `163fbecf99da7648a18a9651c5004802b75c3a90` contains the regression.
The focused test passed, the full Strategy Lab v2 package passed `1,346/1,346`
tests in 27.58 seconds, Ruff check/format passed, focused MyPy passed, and
`git diff --check` passed. The implementation commit was pushed to
`origin/feat/strategy-lab-v2`.

Next: audit the package-owned domain mutation/API persistence path against
AC-DOMAIN and AC-API, select an uncovered owner-scoped lifecycle, and implement
it through the existing engine-neutral contract and persistence seams. Keep
router registration and shared backend integration behind the existing staging
reconciliation gates. RC5 remains permitted for four-check local backtests;
forward shadow still needs event-tape parity, and final Compose/browser/live
service acceptance remains environment-limited by missing Docker Buildx/socket
access.

## 2026-10-05 - Durable resource idempotency conflict and race replay

The resource-create application path now maps a persisted idempotency-key
content collision to the API's typed `409 idempotency_conflict`, without
requiring the prior request receipt to be re-exposed. Resource conflict
resolutions therefore support a safe receipt-free error response while replay
resolutions still require their durable receipt. At the PostgreSQL aggregate
boundary, a lost unique-key/CAS write is reconciled in a fresh transaction: an
identical concurrent create replays the winning receipt; a real create/CAS
conflict remains a conflict or rejection and is never retried as a second
mutation.

Commit `c13d51a4c0ca933fe390738244a9c6075eb5e962` contains the implementation
and regressions. The focused storage/resource/API tests passed `14/14`; the full
Strategy Lab v2 package passed `1,348/1,348` tests in 33.35 seconds with scoped
Unix-domain-socket access. Ruff check/format and focused MyPy passed for all
nine changed files, and `git diff --check` passed. The concurrency regression
uses a deterministic SQL-session race double, not a live PostgreSQL service;
the application-level changed-content regression uses the in-memory aggregate
transaction double. The implementation commit is pushed to
`origin/feat/strategy-lab-v2`.

Next: compose `PostgresStrategyLabV2Adapter.create_resource`,
`PostgresAggregateStore`, and `PostgresResourceReader` in one durable-store
regression that reconstructs the adapter between calls and proves accepted
resource reads, exact replay, owner isolation, and typed idempotency conflict.
Then continue remaining domain/API lifecycle gaps. Shared router registration
and schema integration stay behind the existing staging reconciliation gates;
RC5 remains eligible for qualified local backtests, while forward shadow still
requires event-tape parity.

## 2026-10-05 - Durable resource mutation through reconstructed persistence

The resource-mutation regression now composes
`PostgresStrategyLabV2Persistence.build`, `PostgresAggregateStore`,
`PostgresResourceReader`, and `PostgresStrategyLabV2Adapter`. It creates a
domain-backed strategy resource, reads it through the owner-scoped reader,
reconstructs the adapter over the same durable SQL-session state, and verifies
that exact idempotent replay preserves the original receipt and acceptance
time without another write. Reusing the idempotency key with changed content
returns a typed conflict without exposing a receipt; a different owner cannot
read the resource. The SQL session is a deterministic test double, not a live
PostgreSQL service.

Commit `9b677ba55de8ed0cd21a5963ad9e54e858e58f04` contains this regression.
The focused test passed, Ruff check and format check passed, MyPy reported no
issues in the new test, and `git diff --check` passed. The full Strategy Lab
package run executed all `1,349` tests with no test failures; the command's
only nonzero result was the repository-wide 55% coverage floor applied to
this package-only selection (`47.20%` overall `app` coverage), not a failing
test. The implementation commit was pushed to `origin/feat/strategy-lab-v2`.

No blocker prevents continued package-owned development. Shared router/schema,
provider, ETF, and TC2000 integrations remain gated on their owner branches
reaching staging and exact shared-path reconciliation. Full Compose/browser
acceptance remains host-limited by the missing Docker Buildx plugin and denied
Docker socket access. RC5 remains eligible for four-check local backtests;
forward shadow separately requires event-tape parity, and prereleases remain
barred from broker/real-capital use.

Next: continue the remaining domain/API lifecycle audit and add the next
owner-scoped persistence composition regression, prioritizing mutation/read
behavior across other normalized domain resource types before advancing the
remaining metrics and forward-correctness gaps.

## 2026-10-05 - Native session metric intervals reach worker terminal

The native session-interval path is wired through the frozen runtime bundle,
calendar-aware Nautilus callbacks, runner result parsing, OOS materialization,
and worker-terminal artifact publication. A new worker-terminal regression
proves that session intervals are included in the result, published as a
content-addressed artifact, and cited by session-distribution metrics. Its
calendar intentionally has one missing close: resulting session metrics remain
null instead of bridging the gap. The regression uses deterministic native
callback observations; it does not claim a live Nautilus process or Docker
Compose run. This supersedes the older remaining-gap sentence saying the
ordinary result path lacked a native session-interval producer.

Commit `0fb50ddd05cd14f10a0586de4a74830b80ac2140` contains the regression.
All six worker-terminal tests passed; Ruff check/format, focused MyPy, and
`git diff --check` passed. The implementation commit was pushed to
`origin/feat/strategy-lab-v2`.

There is no stable Nautilus 2.x wait gate. As checked on 2026-10-05, the
[official release list](https://github.com/nautechsystems/nautilus_trader/releases)
shows `2.0.0rc5` as the latest 2.x release, and its official
[installation guidance](https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/getting_started/installation.md)
still identifies 2.x as `2.0.0rcN` pre-releases. This branch pins RC5 and its
four backtest checks permit appropriately qualified local backtests; stable
labeling is not required. RC5 cannot connect to a broker or control real
capital, and full forward-shadow authority still requires event-tape parity.
The saved goal description exposed by `get_goal` still contains an older
stable-only clause; the branch-owned `plan.yaml` is the current source of truth
and explicitly permits exact-pinned release candidates after scope conformance.

Remaining hard gates are unchanged: shared provider/ETF/TC2000 paths wait for
their owner branches to reach staging and undergo exact reconciliation, and
the final full Compose/browser profile remains host-limited by absent Docker
Buildx and denied Docker-socket access. Neither prevents continued work in
package-owned paths.

Next: continue domain/API mutation lifecycles and forward-correctness work;
separately retain the final native-image/Compose acceptance gates without
waiting for a stable-release label.

## 2026-10-05 - Durable package resource survives persistence reconstruction

The owner-scoped durable-resource composition regression now follows the
strategy creation with a typed package that references that strategy's
persisted domain fingerprint. After reconstructing the application adapter over
the same PostgreSQL-session state, the test verifies the package resource and
typed `StrategyPackage` rehydration, exact idempotent replay without additional
writes, and owner isolation. This is deterministic SQL-session test evidence,
not a live PostgreSQL integration claim.

Commit `a89b762bb45f54665e5d1d5fd06e202e4edb2d2b` contains the regression. Its
focused test passed, as did Ruff check/format, focused MyPy, and
`git diff --check`; the source commit is pushed to
`origin/feat/strategy-lab-v2`.

There is still no blocker to package-owned development. Exact-pinned Nautilus
RC5 remains qualified for local backtests after its four scope checks; the
stable-only sentence in the saved goal description is stale against the
branch-owned scope and AC-NAUTILUS. Shared provider, ETF, and TC2000 contracts
remain gated on their owner branches reaching staging. The full Compose/browser
profile is currently unavailable because Docker Buildx is absent. The daemon
itself responds as Docker 29.1.3 under scoped host-level execution; the
unprivileged shell cannot access its socket. Event-tape parity gates only full
broker-free forward shadow, not backtests or this ongoing backend work.

Next: extend durable persistence composition coverage across portfolio,
snapshot, experiment, and trial dependencies, then continue forward event-tape
parity and worker correctness. Do not wait for a stable Nautilus label or edit
the upstream-owned shared paths before staging reconciliation.

## 2026-10-05 - Canonical aggregate hydration for persisted trial graphs

The durable persistence composition now exercises a persisted strategy,
package, portfolio, frozen snapshot, experiment, scientific trial, run attempt,
and metric set across adapter reconstruction. It found and fixed a production
read-boundary defect: the `ATTEMPT` API projection is an execution-summary view,
not the typed immutable `RunAttempt` needed for worker hydration. Typed domain
reads now load canonical owner-scoped aggregates independently of API
projections; attempt-by-id validation follows the same canonical path, while
the existing API summary projection remains unchanged. Experiment creation
also fails closed before writes when its capability-contract digest differs
from the frozen snapshot.

The regression reconstructs all typed records and passes the persisted attempt
through `NautilusTrialDomainHydrator`, then verifies stable trial replay and
owner isolation. This is deterministic PostgreSQL-session-double evidence, not
a live database claim. Commit `2c2e7ba0dfb32d8bbb78515e67044feb80bd6024` is
pushed to `origin/feat/strategy-lab-v2`. The full package suite passed
`1,351/1,351` tests, including the local Unix-domain-socket test under scoped
host access. Ruff check passed for the package; changed-file format and MyPy
checks passed. The broader package format check still reports 172 unrelated
files to reformat, and package-wide MyPy reports seven errors in five untouched
test modules; those files were not changed here.

No external gate prevents more package-owned work. Shared provider/ETF/TC2000
integration still waits on owner staging and reconciliation; full Compose build
acceptance still lacks Docker Buildx; forward-shadow authority still requires
event-tape parity. The stable Nautilus label remains explicitly unnecessary.

Next: compose this persisted domain graph and attempt hydration through the
existing search-preparation/runtime materializer into the exact immutable RC5
worker request. Prove the owner, trial, snapshot, package, and execution-plan
bindings survive that boundary, then continue native-process/Compose acceptance
and forward parity.

## 2026-10-05 - Persisted graph to authoritative RC5 worker request

The search-dispatch regression now persists the complete owner-scoped strategy,
package, portfolio, snapshot, experiment, trial, and running-attempt graph,
rehydrates it from the PostgreSQL resource adapter, and passes it through frozen
artifact verification and runtime materialization into an authoritative RC5
worker request. Assertions bind owner isolation and the exact attempt, trial,
experiment, portfolio, snapshot, package-set, and execution-plan identities.
The foreign-owner hydration attempt fails closed. This uses the deterministic
SQL-session fake and local artifact fixture; it is not live PostgreSQL,
Compose, or Nautilus-process evidence.

Implementation commit `53954cdf4795224c020ccd974881b74879fef928` is pushed to
`origin/feat/strategy-lab-v2`. All 1,352 Strategy Lab package tests passed in
33.89 seconds with scoped access for the ephemeral Unix-socket RPC test. The
focused dispatch-preparation module passed all eight tests; Ruff check/format,
focused MyPy, and `git diff --check` passed for the changed test.

There is no release blocker: current branch policy permits exact-pinned RC5 for
authoritative local backtests after its four recorded checks. The fifth
event-tape-parity check remains a distinct gate for broker-free forward shadow.
Full Compose/browser acceptance remains limited by the missing Docker Buildx
plugin and default-sandbox Docker-socket access. Docker Compose 2.40.3 is
installed, and scoped host access reaches the daemon, but `docker buildx`
returns “unknown command.” Provider/ETF/TC2000 shared-contract work remains
staging-gated only when that integration is reached; options admission still
fails closed pending canonical event-time Greeks/delta and settlement evidence.

Next: exercise the persisted authoritative request through the isolated
RC5 process/result-publication path where the local runtime permits; continue
worker recovery/scaling and broker-free event-tape parity, preserving the
Compose/browser host gate separately.

The current human/agent handoff is `ops/workstreams/feat-strategy-lab-v2/handoff.md`;
the session plan hash, active goal state, and exact next action are recorded in
`ops/workstreams/feat-strategy-lab-v2/session.json`; validation evidence remains
append-only in `ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-05 - Persisted RC5 execution, result publication, and safe redelivery

The persisted owner-scoped strategy/package/portfolio/snapshot/experiment/trial/
attempt graph now reaches an exact-pinned Nautilus 2.0.0rc5 worker request,
executes in the isolated container, and passes its successful native result
through the authoritative OOS terminal evidence resolver. The fixture carries
an explicit immutable OOS interval; both native equity and execution-report
artifacts retain that exact evaluation-window fingerprint. The resolver derives
the result manifest and versioned metrics, publishes every output into the
content-addressed local artifact store, and returns an accepted publication
plan. The same immutable worker request executes twice before publication,
covering output-path reuse on queue redelivery.

That retry path exposed a runtime defect: Docker bind mounts require output host
files to exist before the container starts, while a redelivery must safely
replace artifacts from a prior incomplete execution. The sandbox now stages
mode-0666 output sources inside owner-only directories, rejects public parents,
symlinks, non-regular or multiply linked sources, and for Docker retries only
unlinks an existing regular output owned by the host user after verifying its
inode. Deterministic fake executables retain fixture compatibility. Nautilus
assembly fixtures now use a consistent native `AAPL.SIM` instrument/bar
identity, and worker-oriented tests use hermetic output paths rather than a
shared `/tmp` file.

The persisted graph uses the deterministic PostgreSQL-session double; artifact
commit records in this end-to-end proof are also in-memory. This is stronger
than process-exit evidence but is not live PostgreSQL, Compose scaling, or
production-store acceptance. Exact local RC5 image/evidence fingerprints were
verified by the test's environment-bound evidence source. The full Strategy Lab
suite passed `1,354/1,354` with that source enabled, including the isolated RC5
process, retry/redelivery, local result publication, and Unix-socket RPC tests.
Ruff check/format, focused MyPy for sandbox execution and the dispatch
integration, and `git diff --check` passed. The implementation is in commit
`1e699155e93e2767e7f0d5f0d2d2c9e738279cf7`, pushed to
`origin/feat/strategy-lab-v2`.

There is still no stable-release blocker: exact-pinned RC5 remains permitted
for authoritative local backtests after its four scope checks; event-tape parity
is a separate forward-shadow gate. No prerelease may connect to a broker or
control real capital. The saved goal's stable-only sentence remains stale
against the branch-owned scope. The host still lacks Docker Buildx for the full
Compose/browser profile; scoped Docker execution reaches the daemon and the
already-built exact RC5 image, so that limitation does not block package work.

Next: run the actual RC5 completion evidence through the shared
`PostgresWorkerTerminalAdapter`/persistence composition and verify authoritative
result completion, compact metric persistence, capacity settlement, and
idempotent terminal redelivery together. Then continue the remaining
domain-backed resource mutations, worker recovery/scaling, metrics, and
broker-free forward event-tape parity. Keep live PostgreSQL/Compose acceptance
separate from deterministic adapter doubles, and preserve the staging gates on
shared provider/ETF/TC2000 contracts.

## 2026-10-05 - Durable RC5 terminal persistence and replay identity

Added a composition regression that wires the production
`PostgresWorkerTerminalAdapter` to the PostgreSQL runtime-state, execution
state, summary, publication, manifest, result-completion/artifact-commit,
metrics, worker-state, and settlement adapters. Starting from the same
owner-scoped RC5 completion fixture, it persists the runtime result, terminal
outcome/progress, accepted result and metrics, completion, all artifact commits,
worker settlement, and capacity/lease release. Replaying the exact terminal
context returns the same receipt digest and preserves single durable records.
The adapters use their deterministic SQL-session doubles; this is not live
PostgreSQL, a shared cross-table transaction claim, or Compose acceptance.

The composition test exposed a real acknowledgement-idempotency defect:
`PostgresExecutionSummaryAdapter.ensure` returns a `REGISTERED` or
`REPLAY_EXISTING` resolution, and the wrapper had been included in the terminal
receipt digest. The adapter now hashes the immutable `ExecutionSummary` record,
so operational registration state cannot change a redelivery receipt.

Validation: the terminal test module passed `7/7`; the complete Strategy Lab v2
package suite passed `1,355/1,355` in 35.38 seconds with exact RC5 evidence/image
pins and scoped local access for the isolated container and temporary Unix
socket. The suite also includes the actual RC5 process/retry/result-publication
coverage from the preceding checkpoint. Ruff check/format, focused MyPy for the
changed production adapter and integration test, and `git diff --check` passed.
Implementation commit `6cac49899123c44ac887635bf9c261819670c441` is pushed to
`origin/feat/strategy-lab-v2`.

There is no stable-2.x release blocker: branch policy permits exact-pinned RC5
for authoritative local backtests after its four conformance checks. The saved
goal tool's old stable-only sentence is stale; the branch plan is authoritative
and explicitly accepts release candidates. The fifth event-tape-parity check
blocks only broker-free forward shadow. No prerelease can connect to a broker
or control real capital. Full Compose/browser acceptance remains environment-
limited because Docker Buildx is absent and the default sandbox cannot access
the Docker socket; scoped local access is sufficient for the package suite but
does not replace the required Compose/browser profile. Provider/ETF/TC2000
staging reconciliation and canonical options Greeks/settlement remain scoped
future gates, not blockers to this branch's package-owned development.

Next: inject retry/crash points between terminal persistence steps, especially
after the durable settlement receipt but before capacity release, and verify
restart/replay recovery using the production adapters. Continue the outstanding
worker recovery/scaling, domain-backed mutations, remaining metrics, and
forward-shadow parity work without waiting for a stable Nautilus label.

## 2026-10-05 - Terminal persistence crash and restart recovery

Added a production-adapter composition regression that injects interruption at
two durable boundaries: after execution/settlement state but before public
terminal result persistence, and after result/metrics/completion/summary writes
but before worker capacity/lease release. Each retry reconstructs the
PostgresWorkerTerminalAdapter and its production PostgreSQL adapters over the
same deterministic SQL-session state, as a process restart would. The first
failure now returns RETRY instead of escaping when public terminal-state
persistence raises. Recovery completes the terminal receipt, releases capacity,
and exact redelivery leaves one durable result, metric, completion, summary,
settlement, and artifact-commit record set. The fakes prove adapter/replay
behavior, not live PostgreSQL or a cross-table transaction.

Validation passed: terminal adapter module `7/7`; full Strategy Lab v2 package
suite `1,355/1,355` with exact RC5 evidence/image pins and scoped local access;
Ruff check/format, focused MyPy for the changed adapter and test, and
`git diff --check`. The production change and regression were reviewed as the
only staged application paths and committed as
`c7db6f8e748503448e11770dd282db8e2a79663e`; push to
`origin/feat/strategy-lab-v2` succeeded. Code-context closure: owned paths were
`backend/app/strategy_lab_v2/worker_terminal_adapter.py` and
`backend/app/strategy_lab_v2/tests/test_nautilus_worker_terminal.py`; focused
and package validation passed; implementation commit `c7db6f8` is synchronized;
HEAD and origin both equal `c7db6f8e748503448e11770dd282db8e2a79663e`. Only the
branch-owned operational checkpoint is now being updated separately.

There is no stable-Nautilus release blocker: branch scope explicitly accepts
an exact-pinned v2 release candidate for local backtests after the four checks.
The saved goal metadata still contains the superseded stable-only phrase, but
the branch plan and active acceptance criteria say stable release labeling is
not a gate. Forward shadow specifically still needs event-tape parity. Broader
lease-expiry/recovery and worker scaling, remaining domain-backed mutations and
metrics, and forward-shadow correctness are unfinished product criteria. The
required full Compose/browser profile remains environment-limited: Docker
Buildx is absent and default-sandbox Docker socket access is denied. This limits
that acceptance profile but does not block package-owned implementation. Shared
provider/ETF/TC2000 reconciliation applies only if a change overlaps their
contracts; options stay fail-closed pending canonical Greeks/settlement.

Next action: trace the durable worker lease-expiry/recovery path and extend its
production-adapter tests for process restart, expired-lease reclamation, and
idempotent cancellation/terminal replay. Then continue domain-backed mutations,
remaining metrics, and forward event-tape parity.

## 2026-10-05 - Durable worker recovery receipts and restart replay

Added `PostgresWorkerRecoveryAdapter` and an additive Alembic migration
(`ff3a4b5c6d7e`) for owner-scoped recovery receipts. Receipts retain the
recovery reason, plan identity, retry-attempt identity, and exact lease-release
observation fingerprint/sequence. The pure recovery resolution now returns that
deterministic observation and can resume when a receipt committed but worker
capacity release did not; it also replays a completed lease-expiry recovery
when a later callback arrives after the lease was already released. The adapter
stores the receipt first, then uses the existing atomic PostgreSQL
lease-plus-capacity release. The recovery adapter is available through the
normal `PostgresStrategyLabV2Persistence` bundle.

Validation passed: focused recovery/persistence/migration tests `20/20`; full
Strategy Lab package and schema-migration suite `1,362/1,362` with exact RC5
evidence/image pins; a real-PostgreSQL integration test `1/1` covering receipt
commit, simulated process interruption, reconstructed adapters, expiry
recovery, and later-time duplicate replay; Alembic reports
`ff3a4b5c6d7e` as the single head; Ruff check/format, focused MyPy, and
`git diff --check`. Docker-backed runs were followed by worktree-scoped cleanup;
no containers, images, volumes, or Testcontainers sessions remained.

The nine reviewed implementation paths were the recovery resolver/adapter,
persistence bundle, Alembic migration, unit/integration coverage, and migration
contract test. They were the only staged paths, passed staged whitespace checks,
and were committed as `78623a7124fdef1db0721fabd06326f4b0941f8c`; push to
`origin/feat/strategy-lab-v2` succeeded. Code-context closure: focused and full
validation passed; integration against PostgreSQL passed; HEAD and origin both
equal `78623a7124fdef1db0721fabd06326f4b0941f8c`; product-code worktree was clean
at closure. This change makes recovery durable, but `resolution.next_attempt`
is still returned to the application layer and is not yet persisted/enqueued by
the worker lifecycle; automatic expired-lease scanning, Redis/outbox recovery
scheduling, and Compose scaling remain unfinished.

There is still no Nautilus stable-release blocker: exact-pinned RC5 is permitted
for local backtests after the four conformance checks. Forward-shadow authority
separately needs event-tape parity. The full Compose/browser acceptance profile
remains host-limited by missing Docker Buildx and default-sandbox socket access;
that does not prevent the next package-owned integration step. Shared
provider/ETF/TC2000 reconciliation is conditional on overlapping their paths,
and options stay fail-closed pending canonical event-time Greeks/delta and
settlement evidence.

Next action: connect the production recovery adapter to the worker lifecycle and
expired-lease reclamation path; durably create the returned same-trial retry
attempt and schedule dispatch/outbox work idempotently. Test restart boundaries
between retry-attempt persistence, dispatch, and acknowledgement before moving
to broader worker scaling, domain-backed mutations, remaining metrics, and
forward event-tape parity.

## 2026-10-05 - Worker lifecycle retry persistence and scheduling

Connected dedicated-worker process/lease failures to the owner-scoped recovery
application. It authenticates the persisted dispatch and attempt lineage,
replays durable recovery receipts, persists deterministic retry attempts on the
same immutable trial, closes the prior search candidate, and schedules the
replacement through the authenticated local preparation RPC using stable
request/idempotency identities. Retry attempts are now part of the PostgreSQL
dispatch uniqueness identity, and outbox availability respects the retry
attempt creation time. The worker entrypoint composes the recovery writer and
lease-state reader; Compose shares the preparation socket and token with the
dedicated worker. Restart between retry persistence and dispatch scheduling is
covered, along with lease-expiry recovery and active-lease duplicate prevention.

Changed paths: `backend/app/strategy_lab_v2/application.py`,
`backend/app/strategy_lab_v2/persistence.py`,
`backend/app/strategy_lab_v2/postgres_resources.py`,
`backend/app/strategy_lab_v2/postgres_search_dispatch.py`,
`backend/app/strategy_lab_v2/redis_application.py`,
`backend/app/strategy_lab_v2/worker_callbacks.py`,
`backend/app/strategy_lab_v2/worker_entrypoint.py`,
`backend/app/strategy_lab_v2/worker_service.py`,
`backend/app/strategy_lab_v2/worker_recovery_application.py`,
`backend/app/strategy_lab_v2/tests/test_nautilus_worker_terminal.py`,
`backend/app/strategy_lab_v2/tests/test_persistence.py`,
`backend/app/strategy_lab_v2/tests/test_postgres_resources.py`,
`backend/app/strategy_lab_v2/tests/test_trial_hydration.py`,
`backend/app/strategy_lab_v2/tests/test_worker_callbacks.py`,
`backend/app/strategy_lab_v2/tests/test_worker_entrypoint.py`,
`backend/app/strategy_lab_v2/tests/test_worker_service.py`,
`backend/app/strategy_lab_v2/tests/test_worker_recovery_application.py`,
`backend/alembic/versions/ff4a5b6c7d8e_allow_search_candidate_attempt_retries.py`,
`backend/tests/unit/strategy_lab_v2/test_schema_migration.py`, and
`docker-compose.yml`.

Validation passed: Strategy Lab package plus schema-migration suite `1,371/1,371`
with exact RC5 evidence/image pins and scoped local Docker/Unix-socket access;
Ruff, Ruff format, focused MyPy, and `git diff --check`. Without scoped host
access the exact Docker/Unix-socket tests are blocked by the default command
sandbox, not by a Nautilus release requirement. The configured
`full_stack_browser` profile remains unproven: Docker Buildx is absent and the
default sandbox cannot access the Docker socket.

The 20 implementation/test/migration/Compose paths listed above were committed
as `d5cc20f63` (`feat(strategy-lab-v2): wire durable worker retries`) and pushed
successfully to `origin/feat/strategy-lab-v2`. No other worktree or branch was
modified.

There is no stable-Nautilus blocker. `goal_request` and the active acceptance
criteria allow exact-pinned RC5 for local backtests after the four checks, with
stable labeling explicitly not required. The live saved-goal objective still
contains its superseded stable-only wording, and an old `remaining_gaps` summary
in `plan.yaml` repeats it; both conflict with the canonical AC-NAUTILUS text.
The fifth event-tape-parity check remains required for forward shadow only.

The current terminal receipt replay regression isolates the terminal writer's
idempotency path; dedicated recovery tests separately cover expiry and retry
scheduling. The composition case where terminal persistence committed and the
lease was released before Redis acknowledgement still needs an explicit
production recovery/replay reconciliation test. Other unfinished product work
includes broader worker scaling, domain-backed mutations, remaining metrics,
and forward event-tape parity. No provider, ETF, or TC2000 worktree was touched.

Next action: reconcile post-terminal released-lease redelivery through the
production recovery composition without rerunning completed simulation or
scheduling a duplicate retry, then continue the remaining worker scaling,
domain mutation, metrics, forward-parity, and full Compose/browser criteria.

## 2026-10-05 - Successful terminal redelivery reconciliation

Completed the production-composition case where terminal result, settlement,
capacity release, and lease release were durable but the Redis acknowledgement
was lost. The ordinary terminal callback now marks the search candidate
succeeded before acknowledging; a released-lease redelivery verifies the
durable completion/settlement/release chain, records or replays the same
successful search receipt, and ACKs without rerunning Nautilus or creating a
retry. A partial terminal commit without durable capacity/lease release remains
pending and does not schedule a new attempt. The end-to-end worker test covers
the lost-response, reclaim, and subsequent duplicate-delivery sequence.

The focused recovery/callback/terminal tests pass `14/14`; the Strategy Lab
package plus schema-migration suite passes `1,373/1,373` using the exact local
Nautilus `2.0.0rc5` image. Ruff check/format, focused MyPy, and `git diff --check`
pass. The first integrated test run exposed an incoherent fixture clock: its
worker clock preceded the simulated process terminal timestamp. Aligning those
timestamps made the released lease observable at redelivery; no production
lease-policy change was needed.

Nautilus stable 2.x is not a blocker: AC-NAUTILUS permits an exact-pinned stable
or release-candidate v2 build after the four local backtest checks and explicitly
does not require stable labeling. The pre-release channel remains disallowed
from broker connectivity or real-capital control. The remaining material work is
broader recovery/scaling and live PostgreSQL/Redis/Compose validation,
domain-backed mutations, remaining metrics, forward-shadow event-tape parity,
and the required full Compose/browser profile. That profile is presently
environment-limited by missing Docker Buildx and default-sandbox Docker socket
access; these do not block package-owned implementation. Provider/ETF/TC2000
staging gates apply only if this branch changes overlapping contracts or paths.

Next action: expand worker recovery/scaling coverage, then continue
domain-backed mutations, remaining metrics, and forward event-tape parity; keep
options fail-closed pending canonical Greeks/delta and settlement evidence.

## 2026-10-05 - Compose replica scale contract

Made the dedicated backtest worker's scale assumptions explicit and
test-covered. The Compose service has no fixed container name or host-port
binding, retains one Redis consumer group, and relies on the worker entrypoint's
default `HOSTNAME` plus PID consumer identity so separate replicas are distinct
consumers. Added configuration and Compose-contract tests plus the documented
local `docker compose --profile strategy-lab-v2 up --scale
strategy-lab-v2-worker=3` operation.

Validation: worker-entrypoint and Compose tests pass `9/9`; Ruff, format, and
`git diff --check` pass. Docker Compose 2.40.3 resolves the profile and its
three-worker `up --dry-run` plan emits three distinct worker containers. This is
planning evidence only, not a live scaled-worker run. The Docker daemon warns
that Buildx is absent, so image build and runtime scale acceptance remain
unproven.

The next throughput requirement is package-owned fleet profile discovery and
selection: preparation currently receives one `WorkerProfile` from its host
context resolver, and no platform scheduler assigns attempts across multiple
available serial profiles. Add this selection without relaxing the invariant
of one Nautilus node per worker process, then exercise concurrent reservation,
Redis consumption, and crash recovery against local PostgreSQL/Redis. No other
worktree was modified.

Next action: implement and test worker-fleet profile selection and serial-slot
reservation across replicas; afterward continue the remaining domain mutations,
metrics, forward event-tape parity, and full Compose/browser acceptance.

## 2026-10-05 - Platform-owned worker-fleet selection

Commit `6bb87bd3419b127c493467032f5efa11b0eaf05f` removes the single-profile
assignment from backtest preparation. The PostgreSQL worker-state adapter now
discovers authenticated profiles by worker kind and exact runtime fingerprint.
The platform deterministically ranks free serial backtest pools by least-recent
use with attempt-bound tie-breaking, then creates/replays an exact worker-bound
lease and reservation identity. Lease duration is explicit host configuration;
there is still at most one Nautilus node per process. The existing atomic
PostgreSQL dispatch transaction remains the final capacity arbiter under races.
Exact concurrent lease-insert races replay only when the persisted lease bytes
match.

Validation at the implementation commit: fleet/profile, preparation,
PostgreSQL dispatch, composition, and worker-state tests passed `40/40`; the
complete Strategy Lab package plus schema-migration suite passed `1,379` tests.
The one Unix-domain-socket RPC case denied by the default sandbox passed
separately with scoped local-socket access. Ruff check/format, MyPy for the
three changed production modules, and `git diff --check` passed. The source
commit is pushed to `origin/feat/strategy-lab-v2`.

The profile selector and its persisted-dispatch path are now covered, but live
concurrent PostgreSQL/Redis scaling and crash recovery across multiple Redis
consumers remain unproven. Docker Buildx is still absent and default sandbox
access to the Docker socket is denied; these constrain live Compose/browser
acceptance, not continued package-owned work. Stable Nautilus labeling is not a
gate: exact-pinned RC5 is accepted for local backtests after four checks;
forward shadow still needs event-tape parity as the fifth check.

Next action: validate concurrent profile assignment/admission and recovery with
local PostgreSQL/Redis and multiple consumers, then continue domain-backed
mutations, remaining metrics, forward-shadow event-tape parity, and the full
Compose/browser profile. Preserve the one-node-per-process invariant and leave
unsupported option admission fail-closed.

## 2026-10-05 - Local worker-fleet integration evidence

Commit `7f7d8be6f1083159d408a1eff8e9720d4b1e9bf3` closes the stale integration
assumptions exposed by the platform-owned fleet selector and RC5 backtest
authority. The PostgreSQL RPC integration now registers a runtime-matching
serial profile and constructs its preparation context from the exact four-check
RC5 conformance result, instead of reading the removed context-owned worker
profile or asserting the superseded compatibility-only policy.

Added live local-service integration coverage for two race/recovery boundaries:
two concurrent PostgreSQL reservations against one worker profile produce
exactly one accepted reservation and one saturated result, and a second real
Redis consumer reclaims a pending entry abandoned by the first consumer, then
ACKs it only after the durable completion handler succeeds. The existing
PostgreSQL lease-recovery and search-dispatch/RPC tests also pass against the
local service container.

Validation at the source commit: the Strategy Lab integration directory passed
`4/4` using disposable local PostgreSQL/Redis containers; Ruff, formatting, and
`git diff --check` passed. Repository-scoped cleanup left no containers,
volumes, or Testcontainers sessions and removed no images. This proves focused
database/stream adapter behavior, not runtime scaling of the full Compose
application or browser acceptance.

There is no stable-Nautilus blocker and no external dependency blocks continued
implementation. Exact-pinned RC5 remains permitted for local authoritative
backtests after the four backtest checks; event-tape parity remains the fifth
check for broker-free forward shadow, and prereleases cannot connect to brokers
or control real capital. Docker socket access was granted for these focused
local tests; Docker Buildx is still absent and constrains only the final
Compose/browser profile. Remaining product work includes domain-backed
mutation completeness, remaining result metrics, forward event-tape parity,
and live multi-replica/full-stack acceptance.

Next action: continue the branch-owned domain mutation and versioned metric gaps,
then close forward event-tape parity. Keep the final Compose/browser profile
visible as an acceptance gate, not as a reason to pause package implementation.

## 2026-10-05 - Typed metric and forward resources on PostgreSQL

Commit `5ad6de181472b0b57b1e7c56c767727f7ae3bea0` extends the real PostgreSQL
search-dispatch/RPC integration beyond the core strategy graph. The production
resource adapter now creates a typed `MetricSet` tied to the persisted trial and
attempt, and a typed `ForwardInstance` tied to the persisted portfolio and
warm-up snapshot. The test rehydrates both contracts from the owner-scoped
PostgreSQL resource reader, verifies exact idempotent replay returns the original
receipt, and confirms a different owner cannot read either record.

Validation at this source commit: all four Strategy Lab integration tests passed
against disposable local PostgreSQL/Redis services after the extension; Ruff,
formatting, and `git diff --check` passed. Scoped resource cleanup left no
containers, volumes, or Testcontainers sessions and removed no images. This
adds durable typed resource proof only; it does not claim forward event replay,
event-tape parity, live scaled Compose, or browser acceptance.

Stable Nautilus 2.x remains unnecessary for the backtest scope. The exact RC5
pin qualifies after four checks; forward shadow separately requires event-tape
parity, and prereleases cannot connect to brokers or control real capital. No
external dependency blocks further package work. Docker Buildx still limits the
final Compose/browser validation profile, but focused PostgreSQL/Redis tests run
with scoped Docker access.

Next: continue the AC-DOMAIN/AC-API lifecycle audit and any remaining versioned
metric gaps, then implement forward-shadow event-tape parity. Keep full
Compose/browser runtime acceptance open without making it a package-development
gate.

## 2026-10-05 - PostgreSQL-backed resource API round trip

Added `test_resource_api_postgres.py` to exercise the unregistered Strategy Lab
router through its real HTTP boundary and the production PostgreSQL aggregate
store/resource reader. The test creates a typed strategy, reconstructs the
application adapter, and verifies durable exact replay, typed conflict on
changed content under the same idempotency key, owner-scoped detail lookup,
paginated collection reads, and absence for a foreign owner. The create/read
path is now proven end to end rather than only with the in-memory API adapter
and separate persistence tests.

The implementation changeset is commit
`131bf0ce65ba50f412915fb7a53b76fc42d6836d`, pushed to
`origin/feat/strategy-lab-v2`. This operational checkpoint owns the exact
validation record and session progress; its enclosing checkpoint commit is
verified externally after push. Files in this context are
`backend/tests/integration/strategy_lab_v2/test_resource_api_postgres.py` and
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

Validation: the complete Strategy Lab PostgreSQL/Redis integration directory
passed `5/5`, including the new API round-trip test. Ruff check/format and
`git diff --check` passed. Scoped cleanup found no remaining worktree
containers, images, volumes, or Testcontainers sessions and performed no
host-wide prune. This does not prove shared-router registration or the final
Compose/browser profile.

Next: continue the AC-DOMAIN/AC-API lifecycle audit and remaining versioned
metric gaps, then complete forward-shadow event-tape parity. Keep shared-path
integration behind the provider, ETF, and TC2000 staging gates, and keep the
final Compose/browser profile open as acceptance work rather than a blocker to
package implementation.

## 2026-10-05 - Native OOS account cash/equity metrics

Commit `e6d566130412282b7a52299c1c770c3a900ceb35` carries the already
byte-verified `account_cash_balance` column through the typed Nautilus equity
observation and official OOS result materialization. Metric definition v16 now
publishes equal-event average/minimum/maximum account-cash-to-equity ratios,
bound to the verified trace and observation digests. Negative native cash is
preserved; if any sample has zero equity, all three ratios are null with an
explicit reason rather than dropping that event. No margin, leverage, buying
power, liquidity, or profitability is inferred.

Validation at the source commit: 57 focused tests passed; the complete Strategy
Lab package passed 1,378 tests, and the single Unix-socket RPC test denied by
the default sandbox passed separately with scoped local-socket access. Ruff
check/format, targeted MyPy across five production modules, and
`git diff --check` passed. The source commit is pushed to
`origin/feat/strategy-lab-v2`. This does not close the full AC-METRICS catalog
or final Compose/browser acceptance.

No Nautilus stable-release dependency blocks this work: the exact-pinned RC5
runtime remains isolated from legacy Nautilus 1.226.0 and is qualified for
local backtests under the four-check scope. Docker Buildx still limits the final
Compose/browser profile only.

Next: continue the AC-DOMAIN/AC-API owner-scoped resource lifecycle audit and
implement the next concrete typed mutation/lifecycle gap. Then continue broader
exposure metrics and forward-shadow event-tape parity. Options order admission
remains fail-closed pending canonical event-time Greeks/delta and settlement
evidence; shared provider, ETF, and TC2000 paths remain staging-gated only when
an owned change overlaps them.

## 2026-10-05 - Forward lifecycle idempotency

Commit `485e2b1c20c80fcaf62cbe491df2edcaf3a35d3a` is pushed to
`origin/feat/strategy-lab-v2`. The forward lifecycle route now requires
`Idempotency-Key`; PostgreSQL atomically binds its owner/instance/key to the
target, normalized request time, and immutable result snapshot. Exact retries
replay the original instance after later state changes, changed intent returns
a typed conflict, and cross-owner lookup remains indistinguishable from missing.
Rejected transitions and key conflicts now return HTTP 409.

Validation at that exact source commit: 86 focused tests passed; the complete
Strategy Lab and schema-migration suite had 1,386 passes, with its sole default
sandbox Unix-socket denial passing separately under scoped local access. All six
Strategy Lab PostgreSQL/Redis integration tests passed, including the new real
PostgreSQL restart/replay test. Ruff check/format, focused MyPy for three
production modules, additive Alembic-head validation (`ff5a6b7c8d9e` is the
single head), and `git diff --check` passed. Worktree-scoped Docker cleanup
found no retained containers, images, volumes, or Testcontainers sessions.

## 2026-10-05 - Native OOS event exposure metrics v17

Implemented and pushed in `973f9c6e3f0571471c0ef9e7873b710895405388`.
The native account trace is now v2 and records gross and signed-net base
exposure from Nautilus's native portfolio valuation on the same canonical
pre-strategy event mark as equity/cash. A missing exposure pair is preserved as
unavailable; zero equity or any missing mark withholds the complete exposure
metric family with explicit null reasons. Metric definition v17 publishes
event-weighted average/max gross and signed-net exposure-to-equity ratios,
bound to the observation and verified trace digests. No margin, leverage,
buying power, or profitability verdict is inferred.

Owned implementation paths: `backend/app/strategy_lab_v2/nautilus_equity_trace.py`,
`nautilus_strategy_bridge.py`, `observations.py`, `metrics.py`,
`nautilus_result_materialization.py`, and `nautilus_result_metrics.py`; focused
tests `test_nautilus_equity_trace.py`, `test_nautilus_strategy_bridge.py`,
`test_observations.py`, `test_metrics.py`, `test_nautilus_result_metrics.py`,
and `test_result_materialization.py`. The exact RC runtime allowlist was also
reconciled: its image now explicitly includes session-equity and frozen
calendar-wire modules already required by the adapter/CLI. Static image-boundary
tests prevent those dependencies from silently disappearing again. No provider,
ETF, TC2000, shared API registration, or other-worktree paths changed.

Validation: 87 focused trace/metric/materialization tests and 41 bridge/runtime
adapter tests passed; the full Strategy Lab plus schema-migration suite passed
1,391 tests. Ruff check/format, targeted MyPy across six production modules,
and `git diff --check` passed. The exact source-built RC5 runtime and fixture
probes passed all four local backtest conformance checks; source digest
`sha256:2f5ed0747f936adfad8ca85fa691ab2c53d3478270d77e26678c0e5d3fc70d1c`,
image digest
`sha256:c150aa4ed2fd075afe16afb3fcec6f7516cd7a43bc691d4f302091bbcf91f3bf`,
artifact digest
`sha256:6d52cf46897bb4e10a854d60bbb2d979dc99a4e30696bf004cfc862555ef3107`,
and conformance fingerprint
`sha256:ad38b38cd526a24afac9d5f1e1d29c440a38a479cf1ab001bf5e63e2ae7de317`.
The pushed implementation commit is `973f9c6e3f0571471c0ef9e7873b710895405388`.

No external dependency blocks further package-owned work. The current branch is
explicitly allowed to use exact-pinned release-candidate Nautilus v2 for local
backtests after the four checks; stable labeling is not a prerequisite. The
newer upstream RC6 is an optional deliberate requalification, not a reason to
wait or a requirement to replace the currently qualified pin. Forward-shadow
authority still requires event-tape parity. Missing Docker Buildx limits only
final Compose/browser acceptance. Shared provider, ETF, and TC2000 contracts
remain staging-gated at shared paths; options admission remains fail-closed
pending canonical Greeks/delta and settlement evidence.

## 2026-10-05 - Sequence-preserving forward parity

The forward callback parity verifier now uses definition v2 and compares the
callback's records in their received order against the sequence-ordered tape.
The former verifier sorted observed records before comparison, allowing a
reordered callback to pass when it returned the same event set. Regression
coverage now proves exact order passes and reordered records fail with
field-level mismatch evidence. The historical frozen-tape verifier retains its
separate deterministic canonicalization behavior.

The audit confirms that this is only the parity verifier seam: the forward tape
and receipt are not yet produced by a real native callback consuming durable
forward work. The tape currently binds an instance and event envelopes, but not
the persisted warm-up receipt/checkpoint or Redis dispatch identity. The runtime
does not yet join those identities to native event delivery, and the correction
replay path is not yet represented as a separately verified native input. These
are branch-owned parity integration gaps, not external dependencies. Provider
event-source contracts remain staging-gated and are not duplicated here.

Validation: the Nautilus event adapter and conformance-fixture suites passed
45 tests; the full Strategy Lab package plus schema-migration regression passed
1,392 tests. Ruff check/format and `git diff --check` passed. RC5 local
backtest qualification is unchanged; the new v2 receipt does not claim forward
conformance or authorize a shadow run.

Next: connect forward parity evidence to the actual native callback boundary,
binding each batch to the persisted warm-up receipt/checkpoint and accepted
dispatch identity. Keep corrections on an explicitly identified
counterfactual-replay path, then qualify all five forward checks against the
exact runtime artifact. Preserve this feature worktree boundary and stop at
`ready_for_human_review`; do not integrate, promote, deploy, activate a live
shadow, or modify another worktree.

Checkpoint records updated with this slice: `ops/workstreams/feat-strategy-lab-v2/plan.yaml`,
`ops/workstreams/feat-strategy-lab-v2/session.json`,
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`, and this handoff.

## 2026-10-05 - Durable native forward-delivery context

Forward dispatch admission now persists the pre-event checkpoint fingerprint,
warm-up receipt fingerprint, and admission decision alongside the request and
event identities. The dispatch-record fingerprint covers those fields, so
worker rehydration detects context drift. Alembic revision
`ff6a7b8c9d0e` adds nullable, legacy-compatible columns with an all-or-none
constraint; legacy rows remain inspectable but cannot be upgraded to native
inputs because they lack the required context.

Forward tape definition v2 now requires one delivery binding per event. Each
binding includes the exact Redis stream entry, durable dispatch record/request,
pre-event checkpoint, warm-up receipt, and canonical event fingerprints. A
live tape accepts only `enqueue` decisions; buffered events and corrections
fail closed. Corrections have a separate typed replay input that verifies the
replay-plan fingerprint, original event target, checkpoint, and warm-up receipt.
The callback parity receipt inherits these identities through the tape
fingerprint. This is now an authenticated handoff contract, but a concrete
native callback factory/runtime is still absent; no forward shadow is yet
authoritative.

Validation: 56 focused adapter, conformance, dispatch, and migration tests
passed; the full Strategy Lab plus schema-migration suite passed 1,395 tests.
The new migration ran against a disposable PostgreSQL container, accepted both
legacy-null and complete new rows, rejected partial admission evidence, and
successfully downgraded. Ruff check/format, targeted MyPy across three
production modules, and `git diff --check` passed. The disposable PostgreSQL
container exited with its test fixture; the other worktree's Compose containers
were not targeted.

The next code-owned gap is a concrete local callback factory and isolated
Nautilus forward runtime that rehydrates only accepted content-addressed market
events, uses the persisted strategy/data identities, and persists outputs
before acknowledging Redis. Provider-owned event-source contracts remain
staging-gated; no other worktree was changed. Stable release labeling remains
unnecessary after exact scope-specific conformance. Preserve this feature
worktree boundary and stop at `ready_for_human_review`.

## 2026-10-05 - Exact-RC5 persistent streaming-session probe

The isolated Nautilus RC5 fixture now exercises one `BacktestEngine` and one
strategy across two separately supplied one-event batches. It verifies that
the strategy's one-time order decision, native fill/order/position, and account
balance persist across batches, then repeats the run and compares the complete
receipt for deterministic replay. The fixture receipt parser now requires this
session evidence, and runtime/conformance/execution tests reject malformed or
non-deterministic session evidence.

The exact-source RC5 runtime evidence build passed. Source digest
`sha256:9ba80f59e1f97068b36ce1a221d7c81ad69ab46da6d4c9c20ffeea172e842a0d`,
runtime image digest
`sha256:66ef26b286726e1678c93ad9dd05b1bb73cf586bf5fa98c95ef3b8a2d083a793`,
artifact digest
`sha256:a91516431474174e8e463db08bd70a9569935edd0a9d4b22d8f1d75e3e9cecfa`,
and four-check backtest conformance fingerprint
`sha256:d60605714317efec12ea3f80e07cdd1dcf1660fa6b13424be26aa3b8f598d537`.
The streaming session is deterministic and reports two batches, one fill,
order, and position, and a final account balance of `98897.79 USD`. This is
engine substrate evidence only: the fixture remains non-authoritative and
forward event-tape parity remains deferred.

Validation on the current worktree: the focused conformance/execution/runtime
set passed 66 tests; the complete Strategy Lab plus schema-migration suite
passed 1,395 tests, with its existing Unix-domain-socket test passing
separately under narrowly scoped local-socket permission (1,396 total); Ruff
check/format, targeted MyPy for `nautilus_runtime.py`, and `git diff --check`
passed. The remaining code-owned task is still the concrete forward callback
factory and long-lived runtime that consumes persisted accepted deliveries and
persists outputs before Redis acknowledgement. Stable Nautilus 2.x remains no
gate; the exact RC5 build qualifies only for the conformance scopes actually
verified, with no broker or real-capital use.

Changed code paths for this checkpoint:
`backend/app/strategy_lab_v2/nautilus_rc_fixture_probe.py`,
`backend/app/strategy_lab_v2/nautilus_runtime.py`,
`backend/app/strategy_lab_v2/tests/test_conformance_fixtures.py`,
`backend/app/strategy_lab_v2/tests/test_engine_execution.py`, and
`backend/app/strategy_lab_v2/tests/test_nautilus_runtime.py`. The next step is
to carry this verified streaming behavior into the authenticated forward-
delivery callback and isolated runtime path.

## 2026-10-05 - Authenticated Nautilus forward-delivery input factory

Added a host-owned callback factory that revalidates Redis entry identity
against the durable forward dispatch, resolves one source-verified canonical
event/SDK `MarketEvent` pair, and materializes an exact one-event Nautilus tape
carrying the persisted checkpoint, warm-up, admission, and dispatch identities.
The returned immutable input also retains the SDK event needed to build the
strategy callback context. Buffered and correction dispatches are rejected
before source resolution; corrections remain on their separately typed replay
path. The event-source resolver is an explicit local adapter seam, not a second
provider integration or a Nautilus import in the general worker.

The focused forward-delivery, Nautilus event-adapter, and PostgreSQL dispatch
suite passed 28 tests. The complete Strategy Lab and schema-migration suite
passed 1,400 tests; its one temporary Unix-domain-socket test passed separately
with scoped socket permission (1,401 total). Ruff, formatting, targeted MyPy
for `nautilus_forward_delivery.py` and `nautilus_runtime.py`, `git diff
--check`, and the branch workstream validator passed. This establishes a typed
dispatch-to-input boundary, not the persistent engine session, durable
account/runtime commit protocol, or fifth forward parity check. No stable
release label is required; the exact RC5 build remains limited to verified
offline scopes.

Changed paths in the current implementation slice:
`backend/app/strategy_lab_v2/nautilus_forward_delivery.py`,
`backend/app/strategy_lab_v2/tests/test_nautilus_forward_delivery.py`,
`backend/app/strategy_lab_v2/nautilus_rc_fixture_probe.py`,
`backend/app/strategy_lab_v2/nautilus_runtime.py`,
`backend/app/strategy_lab_v2/tests/test_conformance_fixtures.py`,
`backend/app/strategy_lab_v2/tests/test_engine_execution.py`, and
`backend/app/strategy_lab_v2/tests/test_nautilus_runtime.py`. Next, connect
these authenticated inputs to the long-lived engine/trader, strategy callback
context, persistence, and acknowledgement/recovery boundary; then qualify
forward event-tape parity on the exact runtime image.

## 2026-10-05 - Staged forward SDK context window

Added `ForwardStrategyContextWindow` for one portfolio component. It accepts
only source-verified canonical/SDK event pairs, checks exact declared fields,
instrument and dependency interval, enforces strictly advancing event time and
sequence, retains only each dependency's declared lookback plus its current
event, and constructs engine-neutral SDK contexts with no future events.
Parameters, random seed, positions, and the component manifest are carried
through the existing `build_strategy_context` contract.

For live dispatches, `prepare_delivery` binds the staged context to the complete
authenticated delivery, dispatch record, pre-event account checkpoint, and
warm-up receipt. The rolling history does not advance until explicit `commit`
after settlement; identical pending deliveries are idempotent, conflicting
inputs cannot overtake them, and a failed execution can discard its staged
window after the runtime is reset. This is the host context/commit seam, not a
Nautilus process session or durable cross-process checkpoint implementation.

Validation: the full Strategy Lab package plus schema-migration suite passed
1,409 tests. Ruff check/format and focused MyPy for the new context and delivery
modules passed. A full package MyPy invocation reports 12 errors in six
untouched test files; no reported error is in this slice. `git diff --check`
passed. The persistent same-engine strategy session, durable runtime/account
receipt recovery protocol, and fifth forward event-tape parity check remain
code-owned work. RC5 backtest conformance remains valid only for its recorded
exact image and verified scope; no stable release label is required.

Changed paths:
`backend/app/strategy_lab_v2/forward_context.py`,
`backend/app/strategy_lab_v2/tests/test_forward_context.py`,
`backend/app/strategy_lab_v2/nautilus_forward_delivery.py`, and
`backend/app/strategy_lab_v2/tests/test_nautilus_forward_delivery.py`.

## 2026-10-05 - Authenticated forward-session settlement coordinator

Added the host-owned `NautilusForwardSessionEventHandler` contract and its
settlement ordering. Only accepted non-correction dispatches are eligible;
buffered inputs retry and correction inputs remain on the counterfactual path.
The handler obtains an authenticated delivery, requires the context-window
resolution to match its pre-event account checkpoint and warm-up receipt,
stages the bounded SDK context, and validates the native result against the
delivery, context, checkpoint, canonical event, and forward instance. Account
effects are durably applied before context commit and before the consumer may
return `COMPLETE` for Redis acknowledgement. Runtime or settlement failures
restore the exact pre-event native checkpoint and discard uncommitted context.

The executor remains an injected protocol, not a concrete long-lived isolated
Nautilus process. The native output and account effects still need an explicit
durable cross-process receipt/checkpoint and replay protocol; this coordinator
does not claim those or forward parity are complete. The branch is still
qualified only for the recorded RC5 four-check local-backtest scope; the fifth
exact-image event-tape parity check remains open.

Validation on commit `53829858fcdf17f706aef91fdf5f0827b6f769e1`: 18 focused
forward context/delivery/session tests and the full Strategy Lab plus migration
suite passed (`1,414` tests). Ruff check/format, focused MyPy for the three
changed production modules, and `git diff --check` passed. The implementation
commit is published to `origin/feat/strategy-lab-v2`.

Next: implement the concrete isolated persistent Nautilus session and durable
output/checkpoint recovery across process restart, wire it through the forward
worker callback composition, and then qualify event-tape parity on the exact
runtime image. Stable 2.x labeling is not a blocker; release candidates remain
for local broker-free testing only.

Changed paths:
`backend/app/strategy_lab_v2/forward_context.py`,
`backend/app/strategy_lab_v2/nautilus_forward_session.py`, and
`backend/app/strategy_lab_v2/tests/test_nautilus_forward_session.py`.

## 2026-10-05 - Bounded forward-context reconstruction

Added `ForwardStrategyContextHistory`, an immutable recovery input binding one
forward instance, strategy manifest, pre-event checkpoint, warm-up receipt, and
source-verified market payloads. `ForwardStrategyContextWindow.replay_verified_history`
rebuilds the same rolling SDK context fingerprint from that input and fails
closed on identity mismatch, non-monotonic/duplicate events, undeclared data,
or history exceeding each dependency's declared lookback. The reconstructed
window is exposed through `ResolvedForwardContextWindow.replay_verified_history`
so the event handler continues to compare its checkpoint/warm-up pair with the
authenticated dispatch.

The history value is a bounded context-window recovery contract, not the
authoritative event store: a future persistence resolver must load the complete
accepted prefix for the requested checkpoint and prove that association. This
slice reconstructs only SDK market context; strategy-local state and native
account/engine state still require isolated-runtime replay. The canonical
contract decoder now allowlists the nested history payload types for durable
encoding.

Validation on commit `bc2188a7bfb8456310928f89352d160d94527b42`: 17 focused
forward context/session tests and the full Strategy Lab plus migration suite
passed (`1,419` tests). Ruff check/format, focused MyPy for four production
modules, and `git diff --check` passed. The implementation commit is published
to `origin/feat/strategy-lab-v2`.

Next: implement the concrete isolated persistent Nautilus process and its
durable event/result replay boundary, compose it into the forward worker, then
qualify event-tape parity on the exact runtime image. The context history
contract does not itself prove native runtime recovery or forward authority.

Changed paths:
`backend/app/strategy_lab_v2/forward_context.py`,
`backend/app/strategy_lab_v2/nautilus_forward_session.py`,
`backend/app/strategy_lab_v2/postgres_result_materialization.py`, and
`backend/app/strategy_lab_v2/tests/test_forward_context.py`.

## 2026-10-05 - Forward context carries checkpointed account positions

Implementation commit `84f54140980d1f44d8c1879341a4c55249596911` extends the
host-owned resolved forward context with an immutable, typed position snapshot
supplied by the resolver. The session handler passes those positions into
`ForwardStrategyContextWindow` before
execution, so the staged engine-neutral `StrategyContext` can represent the
account state at the same pre-event checkpoint as its market-data history.
Position keys are checked against each `PositionSnapshot.instrument_id`, and
the resulting mapping is read-only. The production resolver still must load
and authenticate these positions from the checkpoint-specific account state;
this change does not claim a concrete Nautilus process, durable native runtime
receipt, replay implementation, or forward-parity qualification.

Validation on the exact implementation commit: the focused forward
context/session suite passed `18/18`; the full Strategy Lab package plus
schema-migration suite passed `1,420/1,420`; Ruff check/format, focused MyPy for
`nautilus_forward_session.py`, and `git diff --check` passed. The implementation
commit was pushed and local `HEAD` matched `origin/feat/strategy-lab-v2`.
`validation.jsonl` records the exact validation and publication evidence.

Changed paths in this context:
`backend/app/strategy_lab_v2/nautilus_forward_session.py` and
`backend/app/strategy_lab_v2/tests/test_nautilus_forward_session.py`. The
operational checkpoint also updates `ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

Next: build the concrete isolated persistent Nautilus session, resolve its
checkpoint-specific account positions from durable storage, persist native
execution receipts before Redis acknowledgement, implement replay recovery,
then run exact-image forward event-tape parity. Stable Nautilus 2.x labeling is
not a blocker. The default shell was denied Docker API access on this checkpoint,
so no image-backed or full-stack acceptance claim is added; this is a validation
constraint, not a blocker to package-owned development.

## 2026-10-05 - Exact RC5 forward event-tape parity

Implementation commit `9cb0957ea972d9c9b6c515f7c13b2d3410bcabc2` is pushed
to `origin/feat/strategy-lab-v2`; `HEAD` and the remote ref match. The source
and probe changes are closed as one implementation context.

The exact-pinned Nautilus `2.0.0rc5` runtime image now passes the fifth
conformance check. The probe starts from the backend's canonical forward tape,
materializes quote, trade, and OHLCV native data, delivers all three through
Nautilus `BacktestEngine` callbacks, and compares callback wire records against
the tape. The saved receipt reports three observed events, zero unexpected
callbacks, no mismatches, and identical expected/observed wire digests. All
four local backtest checks also pass. The raw fixture receipt remains
`authoritative: false`; only the exact-pin-bound complete conformance report is
authoritative. This qualifies the runtime's five-check conformance, not the
still-unimplemented persistent forward worker/recovery acceptance.

Exact-image evidence: source digest
`sha256:48090d00bf5ec045e0d252a8ed72d6bcc91bed0cda8681fec02f262bd0755ebe`,
image digest
`sha256:11c3e245dc1da6607493029586b045779f32dd096d6dd9188c15f61c6f70f83b`,
artifact digest
`sha256:3ad512668fcc49a9ee049ead3a3f1e45b4b0aefa4b2cd54fdb83514952657550`, and
conformance fingerprint
`sha256:4a8f6ecd27af1976408ff8d0fa1176336cf304af078c23cd32ef0c4095b233a9`.
The artifact is retained in the local operator directory
`/tmp/strategy-lab-v2-rc-parity-20261005`; it is not a repository product
artifact.

Validation: the Strategy Lab plus schema-migration suite passed `1,421` tests;
the one local Unix-socket test denied by the default sandbox passed separately
with scoped socket permission. Seventy focused runtime/conformance/event-tape
tests passed; whole-package Ruff, changed-file formatting, focused MyPy for the
event adapter/runtime/conformance resolver, and `git diff --check` passed.

Next: implement and wire the isolated persistent Nautilus process, authenticate
checkpoint-specific event/account/runtime state, and persist native output plus
checkpoint receipts before Redis acknowledgement so crash recovery can replay
without duplicate decisions. The final `full_stack_browser` profile also still
requires Docker Buildx (`docker buildx` is currently unavailable); this does
not block package-owned implementation. Provider/ETF/TC2000 shared-path
reconciliation remains staged behind those branches reaching `staging`.

Changed paths:
`backend/app/strategy_lab_v2/nautilus_event_adapter.py`,
`backend/app/strategy_lab_v2/nautilus_rc_fixture_probe.py`,
`backend/app/strategy_lab_v2/nautilus_runtime.py`,
`backend/app/strategy_lab_v2/conformance_fixtures.py`,
`backend/app/strategy_lab_v2/nautilus_runtime_image/Dockerfile`, and their
focused tests. Operational checkpoint paths:
`ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-05 - Durable forward execution receipt

Implementation commit `35b8ef9144f568526f666d72deb921385d976258` is published
to `origin/feat/strategy-lab-v2`. The forward runtime now constructs an
immutable receipt binding the accepted canonical event, delivery binding,
prepared strategy context, pre-event checkpoint, runtime session, and native
output. The account transition stores that typed receipt alongside account
effects in the existing PostgreSQL state transaction. Replays must match the
same receipt, and the worker refuses successful settlement/acknowledgement
unless persistence confirms its exact fingerprint. Existing receipt-free
account events remain compatible; no schema migration was needed.

This closes the missing receipt-binding step, not the persistent runtime: it
does not yet retain the full native output/checkpoint payload or restore a
concrete Nautilus process after restart. Checkpoint-specific accepted-event
history/account resolution and deterministic crash replay remain required.

Validation on this implementation: 27 focused account/worker/session/result
tests passed; the complete Strategy Lab plus schema-migration suite passed
1,423 tests with one environment-restricted socket case deselected. Ruff check,
changed-file formatting, focused MyPy for four production modules, and
`git diff --check` passed. The exact implementation commit is pushed and
`HEAD` matched `origin/feat/strategy-lab-v2`.

Next: implement the concrete isolated persistent Nautilus worker session and
its checkpoint-bound event/account resolver, persist enough runtime output and
checkpoint state to restore after process loss, and exercise crash windows
before/after database commit and before dispatch acknowledgement. Nautilus
`2.0.0rc5` already passed all five scope checks including forward event-tape
parity; no stable 2.x release is required. Docker Buildx is still needed only
for the final `full_stack_browser` acceptance profile. Provider/ETF/TC2000
shared-path work remains gated on those branches reaching staging.

Changed paths:
`backend/app/strategy_lab_v2/forward_account.py`,
`backend/app/strategy_lab_v2/forward_account_worker.py`,
`backend/app/strategy_lab_v2/nautilus_forward_session.py`,
`backend/app/strategy_lab_v2/postgres_forward_account.py`, and focused tests.
Operational checkpoint paths: `ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.

## 2026-10-05 - Exact-checkpoint forward history reconstruction

Commit `2ad0a34a8c14c5b274fe642275f96a23990f6427` is pushed to
`origin/feat/strategy-lab-v2`. Forward admission checkpoints now have compact,
append-only PostgreSQL transition history, allowing the context/recovery layer
to load event identities and state at the delivery's exact pre-event checkpoint
rather than accidentally reading the latest instance state. Set deltas avoid
persisting a full growing event-id set at every event; each reconstructed
checkpoint is fingerprint-verified. Existing instances seed their current
checkpoint as a history root on first mutation; unavailable earlier legacy
checkpoints fail closed. The adapter now exposes `load_checkpoint_at` and
`load_state_at_checkpoint` for the downstream runtime resolver.

Validation on this implementation: the complete Strategy Lab plus schema
migration suite passed 1,427 tests with one environment-restricted socket test
deselected; whole-package Ruff, changed-file formatting, focused MyPy for the
three changed production modules, and `git diff --check` passed. The focused
two-file runner printed all 17 passing test dots but failed to exit cleanly in
the local command session, so its result is not counted separately. The exact
implementation commit is published and the product worktree is clean.

This removes one missing recovery primitive, not the persistence/restart gap.
Still code-owned: compose the checkpoint-specific market/account resolver,
retain native output and checkpoint payloads durably before Redis ACK, run an
isolated Nautilus process across forward deliveries, and prove restart/crash
replay. Nautilus `2.0.0rc5` already passes all five scope checks; stable 2.x is
not a gate. Docker Buildx remains necessary only for the final
`full_stack_browser` profile. Shared-path reconciliation waits for provider,
ETF, and TC2000 work to reach staging; neither condition prevents owned-path
implementation now.

Changed paths: `backend/app/strategy_lab_v2/forward_state.py`,
`backend/app/strategy_lab_v2/postgres_forward_state.py`,
`backend/app/strategy_lab_v2/postgres_result_materialization.py`, and focused
tests. Operational checkpoint paths: this handoff, `session.json`, and
`validation.jsonl`.

## 2026-10-05 - Forward account journal and exact-checkpoint replay

Commit `ac37aa9b87b3ada8ace710b7df60c899e7424fa9` is pushed to
`origin/feat/strategy-lab-v2`. PostgreSQL account persistence now keeps one
account-state baseline plus an append-only event journal containing each full
account effect and its execution receipt, linked by before/after state
fingerprints. This preserves native account output without copying the entire
growing orders/fills/cash state into every history row. The baseline may bind
to the active forward admission checkpoint and warm-up receipt. The adapter can
replay account positions/cash/orders through an exact `ForwardLiveAdmissionState`,
verifies each transition fingerprint, and fails closed for missing receipts,
missing events, mismatched warm-up, or a target outside the baseline prefix.
Legacy accounts without a checkpoint-bound baseline remain readable as current
state but cannot claim historical resolution.

Validation: 17 focused account/worker/session tests passed; whole Strategy Lab
plus schema-migration suite passed 1,428 tests, and its one sandbox-denied Unix
socket test passed separately with scoped local socket permission. Ruff check,
changed-file formatting, focused MyPy for the two changed production modules,
and `git diff --check` passed. Exact implementation commit is pushed.

This adds the durable account-history primitive, not the composed runtime.
Next, connect the authenticated historical admission/account results to the
forward context-window resolver, load declared market-data history from the
frozen warm-up and canonical payload sources, then implement the isolated
persistent Nautilus session and crash-safe native runtime checkpoint/output
restore. Stable 2.x remains no gate; exact RC5 five-scope conformance already
passes. Docker Buildx remains only a final `full_stack_browser` environment
gate, and staging reconciliation still gates shared paths rather than owned
package work.

Changed paths: `backend/app/strategy_lab_v2/forward_account.py`,
`backend/app/strategy_lab_v2/postgres_forward_account.py`, and
`backend/app/strategy_lab_v2/tests/test_postgres_forward_account.py`.
Operational checkpoint paths: this handoff, `session.json`, and
`validation.jsonl`.

## 2026-10-05 - Authenticated forward context composition

Commit `31f079e7a7376011e8294df0b46abb2890adcf82` is pushed to
`origin/feat/strategy-lab-v2`. A concrete context-window coordinator now binds
the delivery to its exact archived admission checkpoint and immutable warm-up
receipt, resolves one portfolio-bound strategy-component recipe, validates
bounded market history against the warm-up boundary and processed live-event
prefix, and replays native account positions at that same checkpoint. The
PostgreSQL forward-state adapter now exposes an owner-scoped authenticated
warm-up-receipt read for that path. An uncommitted/future live event, mismatched
checkpoint, warm-up receipt, portfolio recipe, or account identity fails
closed before native execution.

The recipe and frozen/canonical history readers remain explicit platform-owned
ports; their concrete artifact/data adapters and worker startup wiring are not
implemented yet. This coordinator currently resolves a component context; the
portfolio-wide multi-component persistent execution path and durable native
checkpoint/output recovery still remain package-owned work.

Validation: focused context/session/PostgreSQL tests passed `19/19`. The whole
Strategy Lab package passed `1,424` tests; its one temporary Unix-socket test
was denied by the default sandbox and passed on an exact single-test retry with
scoped socket access. Ruff check/format, focused MyPy for the two changed
production modules, and `git diff --check` passed. The implementation commit is
published.

Next: provide concrete, content-addressed strategy-recipe and bounded history
readers over the platform's immutable warm-up artifacts and canonical event
store, then wire them into a serial persistent Nautilus session that durably
commits native output/checkpoint receipts before Redis ACK and restores by
deterministic replay after crash. Nautilus `2.0.0rc5` already passes all five
scope checks; no stable 2.x release is required. Final `full_stack_browser`
acceptance is currently environment-limited: Docker Buildx is unavailable and
the default sandbox cannot access the Docker API socket. Shared provider/ETF/
TC2000 gates apply only to overlapping paths after those branches reach staging.

Changed workstream paths: `ops/workstreams/feat-strategy-lab-v2/handoff.md`,
`ops/workstreams/feat-strategy-lab-v2/session.json`, and
`ops/workstreams/feat-strategy-lab-v2/validation.jsonl`.
