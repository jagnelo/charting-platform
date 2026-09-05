# TC2000 Frontend Rework Roadmap

Status: active implementation roadmap  
Branch: `feat/tc2000-frontend-rework`  
Parent: `staging`  
Last reconciled: 2026-09-05

## 2026-09-05 — Aggregate readiness gate receipt

The authenticated focused Market Map history flow passed `1/1` on a rebuilt branch-scoped
stack. The exact-tip `full_stack_browser` gate at metadata tip `4932fbc2` (product tip
`ea4514fa`) passed all locked dependency/migration, workstream, lint/format/type-check,
backend unit/integration and combined coverage (`80.92%`), frontend Vitest (`952/952`),
build, compose/provider, stack-health, runner-isolation, and functional Playwright stages
(`157/157` with `106` documented skips across `263` specs). The four-project visual matrix
remains `98/104`: the six unchanged state-oracle diffs are `watchlist-column-editor-open`
at visual-1080p-100/125 (`13,844` pixels each) and `workspace-floating` at
visual-1080p-100/125/1440p-100/1440p-125 (`12,097`/`12,097`/`9,770`/`9,770` pixels).
No baseline, mask, threshold, skip, fallback oracle, provider rule, or acceptance policy
changed; teardown removed all assigned resources. The gate is explicitly blocked only by
those existing visual diffs, while canonical provider/history breadth and remaining R2-R6
gaps stay open.

This is the concise, branch-owned execution map for the TC2000 frontend rework. The chronological
records in `docs/project-todos.md`, `docs/tc2000-parity.md`,
`docs/tc2000-acceptance-governance.md`, and `docs/tc2000-visual-parity.md` remain the detailed
evidence ledgers. If a summary here conflicts with a dated test receipt or the current code, the
current code and fresh evidence win.

## 2026-09-05 — Separate aggregate analysis readiness from covered history

The generic watchlist source-history response now includes an aggregate `analysis_ready` boolean
and `analysis_ready_status` across every requested timeframe. The existing `overall_status` remains
the compatibility-oriented covered/worker state, while the new aggregate applies the declared
D1/W1/MN floors (252/52/24 bars) to prevent daily-only or one-bar coverage from being presented as
study-ready. Market Map renders both states. Product commit `ea4514fa` (`feat(tc2000): expose
aggregate history readiness`) is committed on the feature branch. Backend watchlist-history units
pass `6/6`, full backend units pass `1,319/1,319` with the existing `34` warnings, focused Market
Map component coverage passes `36/36`, full frontend Vitest remains `952/952` across `109` files,
TypeScript, Ruff, format, and `git diff --check` pass. The exhaustive gate and authenticated
browser recheck at this new product tip remain pending; the prior gate's six unchanged visual
state-oracle diffs remain explicit.

## 2026-09-05 — Generic source history exposes analysis-ready floors

The shared watchlist source-history status now reports analysis-ready members and percentages for
the canonical D1/W1/MN floors (252/52/24 bars), alongside the existing covered-member, bar-count,
date-range, and worker-progress fields. Market Map labels surface the distinction without changing
the compatibility-oriented overall status or any provider entitlement/fallback behavior. Product
commit `8490f2dd` (`feat(tc2000): expose history analysis-ready floors`) is pushed to
`origin/feat/tc2000-frontend-rework`.
Backend units passed `1,318/1,318`; the focused history unit/API checks passed `5/5` and `1/1` (the
selected API invocation has the expected coverage-floor caveat); frontend component coverage passed
`36/36`, full frontend Vitest `952/952` across `109` files, TypeScript, Ruff/format, and diff checks
passed, and authenticated F8s-market-map-watchlist passed `1/1` on a rebuilt branch-scoped stack
with clean teardown. The exact-tip exhaustive gate then ran at metadata tip `0af0bed5` (product tip
`8490f2dd`): all non-visual stages and functional Playwright passed (`157/157` with `106` documented
skips across `263` specs). The unchanged visual matrix completed `104` cases with `98` passes and
six failures: `watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` pixels each), and
`workspace-floating` at visual-1080p-100/125/1440p-100/1440p-125 (`9,770`/`11,901`/`11,901`/
`12,097` pixels). Teardown and resource accounting were clean; existing visual acceptance remains
unchanged and the six state-oracle diffs are the only gate blocker.

The current product slice is `8490f2dd` (`feat(tc2000): expose history analysis-ready floors`).

The preceding product slice is `7f672897` (`feat(tc2000): promote range centers through thresholds`).
The primary Study Lab and persisted Research Results now expose explicit finite comparison controls
for completed structured `range` artifacts with aligned center values. A user can save a typed
Boolean column or reuse the condition for a watchlist filter, scan, Market Gauge, or alert. The
immutable code asset and screener provenance retain the selected output, canonical members/source/
membership, timeframe, dataset/run lineage, `range_center_target_to_boolean` adapter, and
`study_range_center_threshold_as_boolean` semantics; lower/upper bands remain source-only. The
prepared-universe runner requests the range output, extracts each member's latest finite center, and
applies the supported relation outside user code. Backend runner coverage passed `113/113`, code API
`24/24`, screener integration `27/27`, focused frontend coverage `63/63`, full frontend Vitest
`952/952` across `109` files, TypeScript/build/Ruff/workstream/diff checks passed, and authenticated
F8t-results browser proof passed `1/1` on a rebuilt branch-scoped Docker stack with clean teardown.
The commit is pushed to `origin/feat/tc2000-frontend-rework`. The exact-tip gate then ran at metadata
tip `93883674` after formatter correction `c2f3a588` (product tip `7f672897`): all non-visual stages
and functional Playwright passed (`157/157` with `106` documented skips across `263` specs), while
the visual matrix remained `98/104` with six unchanged state-oracle failures. The six diffs are
`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` pixels each) and
`workspace-floating` at visual-1080p-100/125/1440p-100/1440p-125
(`11,901`/`11,901`/`12,097`/`9,770` pixels). No visual policy, provider fallback rule, or
acceptance policy changed; teardown and resource accounting were clean. Canonical provider/history,
richer Study, native-window/accessibility/security, dense-data, and visual-oracle gaps remain open.

The preceding product slice is `928bf8ae` (`feat(tc2000): promote range centers to watchlist columns`).
The primary Study Lab and persisted Research Results now expose a typed latest-value watchlist-column
promotion for completed structured `range` artifacts with aligned finite `center` values. Lower/upper
band values remain source-only; the saved code asset declares scalar output plus the explicit
`range_center_to_scalar` adapter and `study_range_center_result_as_latest_watchlist_column` lineage.
The immutable research job envelope carries that adapter into prepared-universe batch execution,
which requests the range output and extracts the latest finite center as each member's scalar cell
outside user code. Backend runner coverage passed `112/112`, job-envelope coverage `5/5`, code API
integration `24/24`, focused frontend coverage `61/61`, full frontend Vitest `950/950` across `109`
files, type-check/build/diff checks passed, and authenticated F8t-results plus the adjacent primary
threshold flow passed `1/1` each on a rebuilt branch-scoped Docker stack. The commit is pushed to
`origin/feat/tc2000-frontend-rework`; focused teardown/resource accounting was clean. The exact-tip
gate then passed every non-visual stage and functional Playwright (`157` passed, `106` documented
skips across `263` specs). The unchanged four-project visual matrix completed `104` cases with
`98` passes and six state-oracle failures: `watchlist-column-editor-open` at visual-1080p-100/125
(`13,844` pixels each), and `workspace-floating` at visual-1080p-100/125/1440p-100/125 (`12,097`
pixels each). No visual baseline, mask, threshold, skip, fallback oracle, provider rule, or
acceptance policy changed; assigned stack teardown and resource accounting were clean. Canonical
provider/history, richer Study, native-window/accessibility/security, dense-data, and visual-oracle
gaps remain open.

The preceding product slice is `b6316871` (`feat(tc2000): promote Study Lab series thresholds`). The
primary Study Lab now exposes the same safe threshold fan-out as persisted Research Results for
completed single-output finite numeric `series` runs: an explicit operator (`gt`, `gte`, `lt`,
`lte`, `eq`, or `ne`) and finite threshold can produce a typed Boolean column or one reusable
current-data condition for a watchlist filter, scan, Market Gauge, or alert. The selected output,
canonical member IDs/source/membership, timeframe, dataset/run lineage, and
`series_target_to_boolean` adapter remain explicit; the immutable Study source is not rewritten and
unsupported/non-finite runs remain unavailable. Focused Study Lab coverage passed `26/26`; full
frontend Vitest passed `949/949` across `109` files; TypeScript, production build, and diff checks
passed; authenticated F9j passed `1/1` on a rebuilt branch-scoped Docker stack. The exact-tip gate
at this product tip passed every non-visual stage, including backend units `1,315/1,315`, backend
integration `384/384` with the existing `54` warnings, combined coverage `80.91%`, and functional
Playwright `157` passed with `106` documented skips across `263` specs. The four-project visual
matrix remains `98/104` with the same six state-oracle diffs; teardown and resource accounting were
clean, and no visual policy or provider fallback rule changed. The preceding persisted-results
slice is `225ab93f`, which supplies the same adapter contract at the Research Results boundary.
Primary provider/history, richer Study, native-window/accessibility/security, dense-data, and
visual-oracle gaps remain open.

The preceding product slice was `225ab93f` (`feat(tc2000): promote Study series thresholds`). Persisted
Research Results now exposes an explicit operator/threshold control for finite numeric `series`
artifacts and promotes the selected output into a typed Boolean column, watchlist filter, scan,
Market Gauge, or alert. The source run/code/output identity, declared canonical members, timeframe,
dataset lineage, threshold relation, and `series_target_to_boolean` adapter remain explicit; the
immutable Study source is never rewritten. The backend validates that the source actually declares a
numeric series and that the relation uses a finite supported threshold, then carries the metadata
through the screener into the isolated runner. Focused Results/capability coverage passed `34/34`,
full frontend Vitest passed `948/948` across `109` files, type-check/build/diff checks passed, and
backend code+screener integration passed `51/51` with the existing NumPy deprecation warnings.
The authenticated `F8t-results-series-threshold` flow passed `1/1` on a rebuilt branch-scoped
Docker stack with the operator/threshold, Boolean asset lineage, canonical member universe, and
screener provenance assertions. Exact-tip gate evidence is now recorded below: the first functional
pass had one transient `F8j` timeout, isolated `F8j` passed `1/1`, and the complete rerun passed
`153/153` with `109` documented skips; the visual-only matrix remains `98/104` with the same six
state-oracle diffs. The primary Study
Lab direct threshold controls, canonical provider/history enrichment, native-window/accessibility/
security, dense-data, and visual-oracle gaps remain open; no visual policy or provider fallback rule
changes.

The latest product slice is `ad90b988` (`feat(tc2000): surface source history ranges`). Market
Map's canonical source-history readiness strip now renders every returned timeframe, not only the
first, with covered/member counts, observed bar totals, and oldest/newest dates; missing bounds
remain explicit as `unknown` and no date is inferred or substituted. Focused Market Map coverage
passed `36/36`, the full frontend suite passed `947/947` across `109` files, TypeScript/type-check,
production build, and diff checks passed, and the authenticated F8s family-matrix check passed
`1/1` with the range assertion on a rebuilt branch-scoped Docker stack. Teardown removed all
assigned resources. The preceding product slice `6fa41b81` added the same observed date bounds to
the benchmark-family role labels; this follow-on generalizes the visibility to all source-history
timeframes without changing provider or fallback policy.

The latest exact-tip exhaustive gate ran at metadata tip `70d99baf` (product tip `ad90b988`, with
the source-history readiness records committed). Locked dependency/migration checks, Ruff/format,
TypeScript, backend units `1,315/1,315`, integration `383/383` with the existing `54` warnings,
combined coverage `80.90%`, frontend Vitest `947/947` across `109` files, production build,
compose/provider policy, stack health, runner isolation, and authenticated functional Playwright
(`155` passed, `106` documented skips across `261` specs) all passed. The four-project visual
matrix remains the only failing stage at `98/104`: `watchlist-column-editor-open` differs by
`13,844` pixels at 1080p-100/125, and `workspace-floating` differs by
`11,901`/`12,097`/`12,097`/`5,512` pixels at 1080p-100/125 and 1440p-100/125. No visual baseline,
mask, threshold, skip, fallback oracle, provider rule, or acceptance policy changed; the
workspace-floating actual still intentionally contains canonical benchmark rows after late-popout
hydration. The first full rerun had one transient F8r Python Library narrow-window discovery
failure; a fresh-stack isolated retry passed `1/1` and `3/3` repeats, and the subsequent full
functional rerun passed. Teardown and resource accounting were clean. The goal remains active while
canonical provider/history, richer Study, native-window, accessibility/security, dense-data, and
visual-oracle gaps remain open.

The preceding product slice is `22fd676e` (`feat(tc2000): promote structured study events to signals`).
Research Results now offers `Save Strategy signal` for a named event artifact from a completed
multi-output Study run. It creates an explicit `events` signal asset for the selected output and
hands that immutable version to Strategy Lab with source run/code/dataset/output lineage,
`events_to_signal` semantics, and an explicit current-data re-evaluation boundary. Focused
Research Results/capability tests passed `33/33`; full frontend Vitest passed `947/947` across
`109` files; type-check, production build, and diff checks passed; authenticated F8t-results passed
`1/1` on the rebuilt branch-scoped stack with clean teardown/resource accounting. This closes the
structured-event signal cell without coercing event lists into Boolean values or widening the
declared universe.

The latest product fix is `3a7e4861` (`feat(tc2000): preserve Study event signal lineage`). The
primary Study Lab now routes both single-output and named multi-output `events` artifacts through
an explicit `events_to_signal` asset adapter before creating a Strategy Lab signal. The selected
artifact name, immutable source/run/dataset lineage, current-data re-evaluation semantics, and
point-in-time limitation are preserved; the raw Study version is no longer reused without a
promotion contract. Focused Study Lab coverage passed `25/25`, full frontend Vitest passed
`947/947` across `109` files, type-check/build/diff checks passed, and authenticated F8o passed
`1/1` on the rebuilt branch-scoped stack with clean teardown/resource accounting.

The backend contract for this path is now covered by
`test_multi_output_study_event_output_promotes_to_strategy_signal`. It verifies that the selected
named event output is persisted as an `events` signal asset with the explicit `events_to_signal`
adapter and source/output lineage, then promoted through Strategy Lab without changing the
immutable source. The focused test passed `1/1` with `--no-cov`; the full backend integration
suite passed `383/383` with the existing `54` warnings. The integration-only coverage report is
`48.09%` and hits the configured `55%` floor because the normal threshold is measured across the
combined unit/integration gate; this is recorded as an invocation-scope caveat.

The preceding exact-tip exhaustive gate ran at metadata tip `aa8fbd0b` (product tip `3a7e4861`, with
the durable Study event-lineage records committed). All non-visual stages and authenticated
functional Playwright passed: backend units `1,315/1,315`, integration `383/383` with the existing
`54` warnings, combined coverage `80.90%`, frontend Vitest `947/947` across `109` files, and
functional E2E `155` passed with `106` documented skips across `261` specs. The four-project visual
matrix remains the only failing stage at `98/104`: `watchlist-column-editor-open` differs by
`13,844` pixels at 1080p-100/125, and `workspace-floating` differs by
`11,901`/`9,770`/`9,770`/`12,097` pixels at 1080p-100/125 and 1440p-100/125. No visual
baseline, mask, threshold, skip, fallback oracle, provider rule, or acceptance policy changed;
assigned stack teardown and resource accounting were clean. The goal therefore remains active while
canonical provider/history, richer Study, native-window, accessibility/security, dense-data, and
visual-oracle gaps remain open.

The preceding exact-tip gate ran at metadata tip `df95b3c5` before the primary Study Lab event-lineage
fix and is retained below as historical evidence.

The latest product commit is `0712951` (`feat(tc2000): expose complete benchmark history readiness`).
Market Map's provider-neutral benchmark-family readiness panel now renders every D1/W1/MN
member-bar timeframe returned by the canonical API for each role, including analysis-ready versus
covered members, observed bar totals, and the declared analysis floor. A missing weekly or monthly
leg is visible as incomplete rather than inferred from daily coverage. Focused Market Map coverage
passed `36/36`; full frontend Vitest passed `946/946` across `109` files`; TypeScript type-check,
production build, and diff checks passed. Authenticated F8s passed `1/1` on a rebuilt
branch-scoped Docker stack with clean teardown and resource accounting. This product commit is
committed locally on the feature branch.

The preceding product commit is `2ee80c3` (`fix(tc2000): preserve single-output series promotion contract`).
The primary Study Lab's single-output numeric-series promotion now derives the explicit output
name from the returned series artifact, so the persisted scalar watchlist column satisfies the
backend's declared-output contract for both structured timestamp/value payloads and raw numeric
series arrays. The `latest_series_to_scalar` adapter, selected output, and immutable Study/run
lineage remain explicit; validation still rejects incompatible shapes and does not add a
latest-only fallback. Focused Study Lab coverage passed `25/25`; the full frontend suite passed
`946/946` across `109` files; TypeScript type-check, production build, and diff checks passed.
The authenticated F9i direct Study Lab flow passed `1/1` on a rebuilt branch-scoped Docker stack;
teardown and resource accounting reported zero containers, volumes, known image bytes, and
test-container sessions. This product fix is committed locally on the feature branch.

The preceding product commit is `a12c428c` (`feat(tc2000): promote Study range centers`).
The primary Study Lab now aligns with the persisted-result capability matrix for structured
`range` artifacts: a named range with aligned finite center values offers `Save center plot` and
persists a chart-compatible `series` asset through the explicit `range_center_to_series` adapter.
The immutable source/run lineage is preserved and lower/upper bounds remain source-only; invalid
centers and unsupported shapes stay view/export-only. Focused Study Lab coverage passed `24/24`;
the full frontend suite passed `945/945` across `109` files; TypeScript type-check, production
build, and diff checks passed. The product commit is pushed to the feature branch. The preceding
direct Study Lab latest-series-column slice is `ec17b0fb`; its updated F9i browser assertion and
the branch-scoped exhaustive gate remain pending at the new tip. The existing exhaustive receipt
still has the unchanged `98/104` visual blocker.

The preceding product commit is `ec17b0fb` (`feat(tc2000): expose latest Study series column`).
The primary Study Lab now offers the same safe latest-value target already available from Study
Results: a completed numeric `series` with at least one finite observation can be saved as a typed
watchlist column through the explicit `latest_series_to_scalar` adapter. The selected output name
and immutable Study/run lineage are preserved, while the chart-plot action and unsupported-shape
boundaries remain unchanged. Focused Study Lab coverage passed `24/24`; the full frontend suite
passed `945/945` across `109` files at this product boundary; TypeScript type-check, production
build, and diff checks passed. The authenticated F9i flow now exercises both direct Study Lab
promotions; the product commit is pushed to the feature branch. The next coherent validation batch
should rerun the branch-scoped browser/gate receipts at this tip; the existing exhaustive receipt
still has the unchanged `98/104` visual blocker.

The preceding product commit is `37af72fa` (`feat(tc2000): expose canonical readiness evidence`).
Market Map now surfaces the existing provider-neutral benchmark role evidence alongside each
family source: member/weighted/classified counts and statuses, point-in-time support, entitlement
provider and live-probe state, latest disclosed composition/as-of/known-at dates with resolved-row
counts, and observed continuity gaps. This is a truthful readiness display only; interactive reads
remain local-contract reads with no provider fan-out or neighboring-role substitution. Focused
Market Map coverage passed `36/36`; full frontend Vitest passed `945/945` across `109` files;
TypeScript type-check, production build, and diff checks passed. The commit is pushed to the feature
branch.

The preceding product commit is `a6301f0f` (`feat(tc2000): promote latest study series values`).
Persisted Research Results now offers a latest-value watchlist-column target for numeric `series`
artifacts when a finite observation exists. The frontend sends an explicit
`latest_series_to_scalar` adapter with the selected output name and complete Study run lineage;
the API accepts that adapter only when source validation observes a series contract, and the
isolated runner projects the latest finite observation into the typed scalar column. Series plots
remain available, unsupported shapes are unchanged, and no lossy promotion or provider fallback is
introduced. Focused Results/capability coverage passed `32/32`; the targeted backend runner/API
slice passed `135/135` with two existing NumPy warnings; full frontend Vitest passed `945/945`
across `109` files; type-check, production build, and diff checks passed. Authenticated
`F8t-results` browser coverage passed `1/1` against the rebuilt branch-scoped Docker stack,
including the latest-column action, with clean teardown and complete resource accounting.

The exact-tip exhaustive gate then reran at metadata tip `c8dee130` (product tip `a6301f0f`). All
non-visual stages and authenticated functional Playwright passed: backend units `1,315/1,315`,
integration `382/382` with the existing `54` warnings, combined coverage `80.90%`, frontend
Vitest `945/945` across `109` files, and functional E2E `155` passed with `106` documented skips
across `261` specs. The unchanged four-project visual matrix remains the only blocker at `98/104`,
with `watchlist-column-editor-open` diffs of `13,844` pixels at 1080p-100/125 and
`workspace-floating` diffs of `9,770`/`12,097`/`9,770`/`12,097` pixels at 1080p-100/125 and
1440p-100/125. No visual baseline, mask, threshold, skip, fallback, provider rule, or acceptance
policy changed; teardown and resource accounting were clean.

The preceding product commit is `4026d8d3` (`fix(tc2000): show benchmark route readiness`).
Market Map now surfaces the existing provider-neutral canonical readiness contract for each
benchmark-family source: all four independently mapped roles, dated-holdings coverage, route and
member-history state, selected-timeframe analysis-ready counts, and explicit pending/unavailable
reasons. The frontend makes no interactive provider calls and never substitutes a neighboring
proxy. Focused Market Map, Research Results, and capability coverage passed `67/67`; full frontend
Vitest passed `944/944` across `109` files; type-check, production build, and diff checks passed.
Authenticated `F8s-family-map-drilldown` browser coverage passed `1/1` against the seeded
branch-scoped Docker stack, with clean teardown and complete resource accounting. Product commit
`19896f1e` adds the browser regression.
The follow-up `4026d8d3` refinement renders each role's route/provider and holdings-refresh state
explicitly, with the focused Market Map suite still green (`36/36`).

The preceding range-center product commit is `397c554a` (`feat(tc2000): promote structured range centers`).
Persisted Research Results now exposes named `Save filter: <artifact>` and `Promote alert:
<artifact>` actions for events artifacts, `Save column: <artifact>` and `Save chart plot:
<artifact>` actions for scalar and numeric-series artifacts, the complete Boolean matrix
(`Save column`, `Save filter`, `Promote scan`, `Use Gauge`, `Promote alert`), and an explicit
`Save center chart plot: <artifact>` action for structured range artifacts in completed multi-output
Study runs. The range adapter projects aligned finite center values only; lower/upper bounds stay
in the immutable source and unsupported shapes are not coerced. The focused Research Results
component suite passed `27/27`, the full frontend suite passed `939/939` across `108` files,
TypeScript type-check and production build passed, and the authenticated `F8t-results` browser
flow passed `1/1` against the rebuilt branch-scoped Docker stack with clean teardown and resource
accounting. The exact-tip exhaustive gate has now rerun at product tip `397c554a`: all non-visual
and functional stages passed, while the unchanged visual matrix remains `98/104` with the same
six diffs recorded below.

The preceding capability-matrix product commit is `95b12a0f` (`feat(tc2000): expose study artifact capability matrix`).
Persisted Research Results now makes the compatible promotion matrix explicit: scalar, Boolean,
numeric-series, range-center, and structured-event artifacts state their safe workstation targets;
table, categorical bar, histogram, scatter, heatmap, dashboard, and historical-breadth shapes are
marked view/export-only. Range-center promotion is offered only when the artifact contains an
aligned finite center series, while lower/upper bounds remain source-only. Focused capability and
Research Results coverage passed `31/31`; full frontend Vitest passed `943/943` across `109` files;
type-check, production build, and diff checks passed. Authenticated `F8t-results` browser coverage
passed `1/1` against the seeded branch-scoped Docker stack, with clean teardown and complete
resource accounting. This slice does not alter the backend contract,
visual policy, provider fallback rules, or the unchanged exact-tip visual result (`98/104`).

The prior exact-tip gate at product tip `6f575a34` passed all non-visual stages and the functional
browser suite (`155` passed, `106` documented skips across `261` specs). A first invocation's single
F8t-results-open lookup failure was not reproducible in an isolated `3/3` rerun and did not recur
in the complete gate.

The unchanged visual matrix remains the only failing stage: `98/104` passed and six screenshot
diffs remain—`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` differing pixels
each), and `workspace-floating` at visual-1080p-100 (`9,770`), visual-1080p-125 (`5,512`),
visual-1440p-100 (`12,097`), and visual-1440p-125 (`12,097`). No visual oracle, provider fallback,
or acceptance policy changed. The branch remains active while the visual review blocker and the
remaining canonical provider/history, richer promotion, native-window, accessibility/security,
and dense-data gaps are addressed.

The latest exhaustive gate ran at product commit `7c930fd1` (`fix(tc2000): scope event adapter by
instrument`). Event rows carrying a symbol or canonical instrument ID can no longer match a
different candidate. The focused event suite passed `8/8`, the full runner unit suite `107/107`,
event-promotion integration passed `2/2`, and compileall/Ruff/diff checks passed. The exhaustive
gate passed locked dependencies/migrations, Ruff/format, TypeScript, backend units `1,310/1,310`,
integration `381/381` with the existing `54` warnings, combined coverage `80.90%`, frontend
Vitest `934/934` across `108` files, production build, compose/provider policy, stack health,
runner isolation, and authenticated functional Playwright `155` passes with `106` documented
skips across `261` specs. The unchanged visual matrix is the only gate failure: `98/104` passed
and six screenshot diffs remain—`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844`
differing pixels each), and `workspace-floating` at visual-1080p-100 (`9,770`), visual-1080p-125
(`12,097`), visual-1440p-100 (`9,770`), and visual-1440p-125 (`12,097`). Docker stack teardown
and resource accounting were clean; no visual oracle, provider fallback, or acceptance policy
was changed.

The exact-tip exhaustive gate was then rerun at product commit `1918ca81` (`feat(tc2000): promote
structured study events`). Backend units passed `1,311/1,311`, integration `382/382` with the
existing `54` warnings, combined coverage remained `80.90%`, frontend Vitest passed `934/934`,
and all static/build/compose/provider/runner and functional Playwright stages passed (`155` with
`106` documented skips across `261`). The unchanged visual matrix remains the only failure:
`98/104` passed and six screenshot diffs remain—`watchlist-column-editor-open` at
visual-1080p-100/125 (`13,844` each), and `workspace-floating` at visual-1080p-100 (`12,097`),
visual-1080p-125 (`11,901`), visual-1440p-100 (`12,097`), and visual-1440p-125 (`5,512`).
Docker teardown and resource accounting were clean; no visual oracle, provider fallback, or
acceptance policy was changed.

The work is one continuous delivery stint, not an MVP followed by optional phases. The workstreams
below are dependency-ordered checkpoints so correctness, data lineage, and visual evidence can be
verified without weakening the end goal.

## Product end state

Deliver a rebranded, TC2000 V25-inspired US-market workstation that lets a swing trader move
quickly from the whole market to a trade candidate while preserving source, time, and analytical
lineage:

1. start at an index or ETF benchmark and compare cap-weighted, equal-weight, value, and growth
   views only where those roles are supported by evidence;
2. drill from benchmark to sector, optional industry/proxy, and constituent;
3. compare ratios such as `XLK/SPY`, `XLK/XLE`, `NVDA/XLK`, and `NVDA/SPY` alongside price,
   indicators, drawings, breadth, rotation, rankings, scans, gauges, and alerts;
4. use the same versioned `WatchlistSource` contract for locked index/ETF populations and editable
   personal, managed, combo, sector, industry, and explicit lists;
5. create arbitrary reproducible studies in one Python-native method, edit the visual subset as
   the same AST, and promote compatible immutable outputs throughout the workstation;
6. restore authenticated layouts, linked tools, tabs, pop-outs, selections, studies, and drawings
   reliably across sessions and windows;
7. expose freshness, coverage, provider, entitlement, effective-time, known-time, and unavailable
   states rather than substituting or fabricating data.

### Required benchmark-family roots

- S&P 500, S&P 400, S&P 600, and S&P 1500
- Russell 1000, Russell 2000, and Russell 3000
- Nasdaq 100

Cap/equal/value/growth legs are independent. A root or role is not complete merely because its
identity exists or another proxy can be substituted. QQQ/QQQE is the intended Nasdaq 100
cap/equal comparison when the underlying evidence and entitlement permit it.

## Non-negotiable decisions recovered from the prior session

- TC2000 V25 is the behavioral and visual direction, not a license to copy branding or to call an
  unverified screenshot exact parity.
- uPlot remains the sole renderer for numeric time-series plots.
- New canonical market-data paths are free-source-first, must not require a paid subscription for
  the core workflow, and must not introduce `yfinance`.
- User-authored programming has one Python-native model. The visual editor is a constrained editor
  for the same Python-backed AST, not a separate language.
- Locked sources prevent membership edits only. They remain available to follow, pin, clone,
  chart, map, ratio, breadth, scan, gauge, alert, and Study Lab workflows.
- Market Map is source-polymorphic and hierarchical. It must support arbitrary versioned sources,
  arbitrary supported periods, sector/industry grouping, configurable area and colour metrics,
  and selection handoff without per-tile provider fan-out.
- Breadth is an arbitrary predicate over an arbitrary versioned universe, with current and
  historical results, pass count, denominator, exclusions, and member-level evidence.
- Repository-controlled defects encountered in an acceptance path are fixed and regression-tested;
  they are not relabeled as external blockers. An unavailable external source remains an explicit
  data gap rather than a reason to weaken an oracle.
- Trading/broker execution, options workflows, news, analyst ratings, earnings, full financial
  statements, paid core dependencies, and consolidated real-time feeds are outside this roadmap.

## Evidence reconciliation

| Evidence | What it establishes | Authority and limitation |
| --- | --- | --- |
| Current branch and durable TC2000 ledgers | Implemented behavior, named gaps, and historical validation receipts | Primary repo evidence; old receipts are not fresh reruns |
| Prior Codex rollout `019fa949-e419-77c1-8d7d-188b5235029c` | Product intent, tie-breaks, scope additions, acceptance expectations, and user examples across 78 canonical user turns | Historical deliberation; implementation claims were reconciled against the current repo |
| Four distinct user-shared visual subjects | A breadth-over-price example and Finviz-style constituent, sector, and industry treemaps | Product/composition requirements only; they are not TC2000 pixel authorities |
| Reconstructed TC2000 public reference pack | 230 hash-indexed images from 26 source groups, covering dense lists/grids, chart chrome, linking, tabs/windows, gauges, editors, and shared layouts | Discovery/behavior/board evidence under the manifest; not blanket exact-build approval |
| Deterministic seeded browser evidence | Repeatable product-state and cross-environment regression coverage | Does not prove provider population, historical continuity, entitlements, or exact V25 pixels |

The rollout contains hundreds of `input_image` occurrences because compaction/replay repeated the
same material. After deduplicating the user intent, there are four distinct user-shared visual
subjects. The larger 230-image corpus is a separately fetched public reference board, not 230 user
attachments.

The fetched reference pack is reproducible through
`tests/visual/fetch-tc2000-v25-reference-pack.sh` and
`tests/visual/build-tc2000-reference-board.py`. A `/private/tmp` copy is useful for inspection but
is not durable evidence. Any long-lived archive must keep the index, source URLs, hashes, retrieval
date, and authority classification in a controlled artifact location without committing copied
third-party media blindly.

## Current baseline

These capability claims are inherited from the latest detailed records dated 2026-08-19 unless a
row explicitly says it was checked on 2026-09-03. They are the starting point for a fresh baseline
run, not a claim that the old counts still pass unchanged.

| Capability | Current understanding | Evidence boundary |
| --- | --- | --- |
| Authenticated workstation shell, layouts, linking, persistence, keyboard traversal | Substantially implemented | Historical unit and browser coverage; fresh branch run pending |
| Seeded top-down trader path | Benchmark → sector → ratio/indicator/drawing → industry → constituent → restored state passed | Fixture-backed; canonical live-source equivalent remains open |
| Eight-family entry matrix | Seeded Market Map, breadth, and rotation paths passed | Identity/fixture coverage is not complete provider population |
| Market Map | Recursive sector → industry geometry, source polymorphism, selection, follow/pin/clone, and cross-tab Breadth/Study handoff implemented | Exact nested typography/gutters/hover density and point-in-time data completeness remain open |
| Breadth and Study Lab | Recursive conditions, symbol/reference-universe comparisons, historical contracts, Python isolation, reusable immutable definitions, and some typed promotion adapters implemented | Richer history and complete promotion fan-out remain open |
| Visual regression | Exact-tip four-project run at `7c930fd1` passed 98/104; six board-state diffs remain: `watchlist-column-editor-open` at both 1080p projects (`13,844` pixels each) and `workspace-floating` at all four projects (`9,770`, `12,097`, `9,770`, `12,097` by viewport) | Board-guided product baseline, not exact V25 approval; canonical late-popout hydration now makes the floating state data-bearing; do not weaken or silently rewrite the visual policy |
| Frontend static/unit checks | Exact-tip gate passed 934/934 Vitest across 108 files, plus type-check and build | Fresh receipt at `7c930fd1`; existing large-chunk build warning remains |
| Branch ancestry | Feature product tip `7c930fd1`; local staging `8b885a2f`; staging is an ancestor, feature remains staging-derived | Verified 2026-09-04; no merge/rebase performed during this checkpoint |
| Public visual corpus | 230 indexed media assets reconstructed and the board/manifest validators passed | Verified 2026-09-03 in an ephemeral inspection directory |

The earlier concern that Market Map → Breadth/Study handoff was still failing is superseded by the
later 2026-08-19 repair and `1/1` browser receipt in the repo. A separate late-session mention of a
Golden Layout activation problem is ambiguous relative to later passing fixes; treat it as a
reproduction target, not a confirmed current defect.

### Rough progress view

These are planning estimates, not acceptance percentages and not an arithmetic completion score:

| Area | Rough maturity | Why it is not complete |
| --- | ---: | --- |
| Workstation foundations and persisted mechanics | 90% | Fresh synchronization/baseline and native-window audit remain |
| Deterministic top-down swing-trader workflow | 85% | Canonical-data counterpart is not yet proven |
| Source-polymorphic map, breadth, and drill-down | 75% | History, complete populations, and richer analytics remain |
| Unified Python research and reusable outputs | 70% | Promotion compatibility matrix is partial |
| Canonical provider population and point-in-time history | 35% | This is the largest practical readiness gap |
| Exact V25 visual/state evidence | 45% | Many states remain `required_missing`; board-guided is interim |
| External/runtime/endurance acceptance | 50% | Live-provider, entitlement, native multi-window, and extended-soak proof remain |

Overall functional implementation is roughly 65–70% mature, while real-data daily readiness is
materially lower because family population and point-in-time history are gating inputs.

## Dependency-ordered workstreams

### R0 — Re-establish a current, reproducible baseline

Objective: begin feature work from a known green staging checkpoint without discarding the two
branch-owned workstream commits or treating August receipts as current.

Tasks:

- reconcile the 14 staging commits currently ahead of the branch using the repository-prescribed
  feature synchronization workflow;
- inventory changed validation/runtime rules before running product gates;
- run type-check, full frontend unit coverage, production build, the focused authenticated
  top-down/family/Market Map → Breadth/Study flows, and the unchanged four-environment visual suite;
- reproduce the ambiguous Golden Layout activation concern across open/close, cross-tab handoff,
  save/restore, and repeated family traversal;
- record exact commands, environment, commit, counts, skips, and acceptance flexibility.

Exit evidence: the selected staging checkpoint is an ancestor of the feature head, the worktree is
clean, all named baseline gates have fresh receipts, and any failure is either fixed with a focused
regression or recorded with an exact external cause.

### R1 — Complete canonical family population and point-in-time data

Objective: make the eight benchmark roots and every evidenced role genuinely usable from local
canonical data rather than identity-only or seeded fixtures.

Tasks:

- maintain an explicit root/role/provider/entitlement matrix, including unsupported and pending
  legs; never infer a role from a neighboring ETF;
- hydrate dated holdings with provider evidence, effective time, known time, weights, and
  continuity across rebalance/month-end boundaries;
- hydrate adjusted D1/W1/MN member bars to declared analysis floors and expose covered versus
  analysis-ready counts;
- retain point-in-time sector/industry classification and market-cap/weight inputs without future
  leakage;
- run bounded scheduled ingestion/backfill outside interactive reads; no UI-triggered provider
  fan-out and no fabricated fallbacks;
- document provider terms, rate limits, provenance, cache behavior, failure modes, and deployment
  bootstrap/maintenance operations.

Exit evidence: every required root/role has a dated status; supported legs can reconstruct their
universe and analysis inputs at multiple dates; unavailable legs say why; live probes and database
assertions match the UI coverage/provenance display.

### R2 — Prove the canonical top-down daily workflow

Objective: make the target swing-trader journey pass on canonical provider-backed data, with the
seeded path retained as a deterministic regression rather than a substitute.

Tasks:

- prove benchmark → cap/equal/style → sector → optional industry/proxy → constituent traversal;
- prove benchmark, sector, cross-sector, constituent/sector, and constituent/benchmark ratios;
- preserve linked symbol/timeframe, indicators, drawings, selection, keyboard traversal, and
  save/restore across the journey;
- prove the same Market Map and downstream actions for locked system sources and editable personal
  sources;
- display actionable pending, partial, stale, delayed, unavailable, and entitlement states.

Exit evidence: authenticated live-source browser oracles pass for each supported family role and
for one editable source; source version, as-of time, provider, exclusions, and readiness remain
visible throughout the flow.

### R3 — Finish breadth, rotation, ranking, and historical analytics

Objective: turn the existing general contracts into complete current and historical decision tools.

Tasks:

- complete condition-driven breadth history and occurrences for price/MA, near-high/new-high,
  trend, relative-strength, event, Python, and mixed/cross-sectional predicates;
- preserve denominator, pass/fail/excluded members, missing-reason diagnostics, source version,
  adjustment, timeframe, and benchmark alignment at every date;
- add multi-stage derived-series composition without forward-filling unavailable observations;
- extend rotation history beyond bounded tails and add concentration, dispersion, and
  condition-driven ranking where canonical inputs support them;
- keep map colour/area and historical grouping metrics point-in-time safe.

Exit evidence: current and historical outputs reconcile to independently computed fixtures and at
least one canonical populated family, with reproducibility hashes and no look-ahead leakage.

### R4 — Complete compatible artifact promotion

Objective: let one immutable, reproducible definition travel to every compatible workstation
surface without inventing coercions for incompatible result shapes.

Tasks:

- define the output-shape/capability matrix for scalar numeric, Boolean, series, event,
  cross-sectional, aggregate, and structured results;
- finish adapters for columns, filters, scans, gauges, alerts, chart plots, and Strategy Lab
  signals where the matrix permits them;
- keep code version, dataset manifest, run configuration, source version, output name,
  reproducibility hash, and promotion semantics intact;
- return structured capability errors for invalid promotions;
- make visual-subset edits round-trip through the same Python-backed AST.

Exit evidence: each compatible cell has unit, authenticated API, persistence, and consuming-UI
proof; each incompatible cell has a stable explicit error contract.

### R5 — Close V25 visual and interaction evidence gaps

Objective: converge the rebranded workstation on the reference hierarchy state by state, without
confusing deterministic screenshots, public discovery media, and exact-build authority.

Tasks:

- preserve a reproducible receipt for the 230-item/26-group public board and map every used image to
  a manifest state and authority class;
- work through every `required_missing` state, prioritizing source/picker actions, nested treemap
  labels/gutters/hover density, Study Lab/promotion controls, error/loading/freshness states,
  keyboard-selected states, tool menus, and blocked-popout recovery;
- derive and test dense typography, row height, gutters, headers, menu hierarchy, selection,
  linking colours, chart chrome, gauge geometry, and state variants from authorized evidence;
- use the user-supplied Finviz maps to guide hierarchy and information density, not TC2000 pixel
  values or branding;
- retain all thresholds, masks, overlap assertions, and multi-scale projects unless a separately
  reviewed evidence change justifies an update.

Exit evidence: every required state is `approved`, `board_covered` with an explicit limitation, or
`required_missing` with an exact acquisition blocker; the unchanged 104-case deterministic matrix
and any approved exact-reference gates pass.

### R6 — Close resilience, native-window, accessibility, and performance gaps

Objective: prove the workstation remains usable during real multi-tool research rather than only
in isolated component paths.

Tasks:

- stress Golden Layout tab activation, tool replacement, close/reopen, maximize/restore,
  cross-tab publication, and stale callback rejection;
- distinguish browser pop-out simulation from native multi-monitor behavior and obtain explicit
  native evidence where the product claims it;
- extend beyond the bounded 100-round two-pop-out guard with a declared workload, duration, memory
  budget, listener/window leak checks, and recovery assertions;
- verify 10k-cell Market Map interaction, dense grids, linked crosshairs, pan/zoom, drawing, and
  keyboard response against explicit budgets;
- close accessibility, authentication, authorization, sandbox, persistence, export, migration,
  logging, and critical console/network diagnostics.

Exit evidence: repeatable endurance and performance receipts meet declared budgets on supported
display scales; native/browser limitations remain explicit; no critical diagnostics or leaked
windows/listeners remain.

### R7 — Final product audit and review handoff

Objective: demonstrate that the product end state is complete without relying on hidden fixtures,
stale receipts, undocumented waivers, or unavailable evidence.

Tasks:

- audit every requirement against code, current tests, live evidence, manifest state, and provider
  readiness;
- run changed tests, complete frontend/backend suites, migrations, visual gates, authenticated
  browser suites, opt-in live provider checks, and the repository exhaustive integration gate;
- reconcile all skips, expected failures, acceptance-flexibility entries, security findings,
  deployment/bootstrap instructions, and remaining external limitations;
- update the detailed ledgers and this roadmap with exact final evidence.

Exit evidence: every in-scope end goal has a current receipt, every external limitation is
accurately visible to the user/operator, the worktree is clean and pushed, and the branch stops at
`ready_for_human_review`. Integration and deployment still require separate human authorization.

## Completion definition

The TC2000 frontend rework is ready for human review only when all of the following are true:

- the canonical live-data version of the top-down workflow passes for all supported roots/roles;
- unsupported or unentitled roots/roles are explicit and evidence-backed, not silently replaced;
- historical universe, weights, classifications, bars, and analytical results respect effective
  and known-time boundaries;
- arbitrary source-polymorphic Market Map and breadth workflows preserve immutable source lineage;
- Python/visual definitions and all compatible promotions are reproducible and round-trip safely;
- persisted, linked, cross-window, keyboard, drawing, and dense-workstation behavior survives the
  declared endurance matrix;
- every required visual state has an honest manifest disposition and all applicable visual gates
  pass unchanged;
- full automated, live-provider, security, migration, performance, and exhaustive integration
  evidence is current at the exact feature tip;
- no hidden fixture, paid-provider assumption, acceptance waiver, or stale historical claim is
  presented as product completion.

## Immediate next checkpoint

Continue with the next canonical provider/history slice and compatible chart/list/gauge consumers
with authenticated evidence. The latest readiness-display slice is at product tip `37af72fa`; its
focused and full frontend checks pass. The exact-tip gate has previously been rerun at product tip
`a6301f0f`; all non-visual and functional stages pass, while the unchanged six visual diffs remain
explicit. The latest product fix is `2ee80c3`, with focused/full frontend and direct F9i evidence;
the exhaustive gate should be rerun after the next coherent implementation batch. Preserve
the declared provider fallback boundaries and all existing acceptance policy while expanding the
remaining richer Study Lab targets, native-window/accessibility/security evidence, and dense-data
budgets.
