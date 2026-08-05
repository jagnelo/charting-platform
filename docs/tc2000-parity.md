# TC2000 Version 25 Parity Matrix

This is the implementation-facing matrix for the controlling plan. `Blocked` means
the source reference is required before visual acceptance; it is not an approval.

| Surface | Implementation ownership | Reference state | Functional status | Required evidence |
| --- | --- | --- | --- | --- |
| Application shell and US Top Down | `WorkstationView.vue` | Blocked | In progress | V25 capture, interaction/E2E, visual baseline |
| Workspace tabs and factory layouts | `workspaces.py` | Blocked | In progress | persistence, reset, layout visual reference |
| Docking/pop-outs | `WorkspaceLayoutHost.vue` | Blocked | In progress | pop-out/recovery, golden layout lifecycle, screenshots |
| Chart | `UPlotChart.vue` | Blocked | Existing/rework in progress | uPlot lifecycle, transforms, visual states |
| Watchlists/columns/filters | workstation tools + batch APIs | Blocked | In progress | 10k virtual-list, editor/scan/gauge tests |
| Top-down sector/breadth workflow | `analysis.py`, market groups | Blocked | In progress | point-in-time and E2E drill-down evidence |
| Unified Python | `/code`, runner | N/A | In progress | sandbox escape/resource suite |
| Study Lab | `/research`, `StudyLabView.vue` | Blocked | In progress | reproducibility/artifact/rendering suite |
| Notes and alerts | `/notes`, existing alerts | Blocked | In progress | user isolation and linked-tool tests |
| Excluded capabilities | `tc2000-capability-stubs.md` | N/A | Documented | primary-menu absence test |

No row can change to `Complete` until its full functional and visual acceptance evidence
is recorded in the referenced test/baseline system.

## Current runtime evidence (2026-08-05)

Chart surfaces now use a shared canonical OHLCV request coordinator. Identical instrument,
timeframe, range/limit, transform, adjustment, and local/basket requests coalesce while
in flight; successful results are retained briefly for linked-window reuse and failures are
not cached. The coordinator is covered by coalescing, expiry, and failure-recovery tests;
full frontend Vitest is `568/568`, rebuilt Chromium is `29/29`, and backend logs are clean.

The targeted sandbox/resource and code API slice passes `112/112` with Docker access. It
covers AST safety, forbidden imports/process/filesystem/network/reflection paths, isolated
runner limits and cancellation, immutable code versions, queued Study Lab jobs, and the
10,000-cell batch boundary. Only two existing Nautilus/NumPy deprecation warnings remain.

The browser diagnostic contract also covers the logout boundary explicitly: F5 grants only
the bounded 401 responses caused by clearing authentication while in-flight queries settle;
all other 401s remain fatal. The focused logout test and complete authenticated flow pass
`29/29`.

The dense workstation status bar now consumes the canonical technical snapshot freshness
contract rather than treating the newest local bar as an unqualified cache timestamp. It
renders `Current · canonical`, `Delayed`, `Stale · cached`, `Partial coverage`, `Coverage
limited`, `Fetching`/`Backfilling history`, or `Unavailable`. `Current` is explicitly scoped
to the canonical dataset's entitlement/freshness policy and does not imply consolidated
real-time quotes; `Delayed` is accepted only when an entitled provider reports that semantic.
The mapping is exhaustively unit-tested and the rebuilt authenticated Chromium flow remains
`29/29`.

The live shared-volume runner protocol has also been exercised for cancellation: a uniquely
named 10,000-cell prepared-universe batch was claimed by the non-root runner, observed a
cancellation sentinel during execution, returned structured `canceled` / `batch_canceled`
output with bounded completed-cell artifacts, and left the runner healthy. Probe artifacts
were explicitly removed afterward. This closes live cancellation under batch pressure;
broader multi-process namespace/resource stress remains open.

The rebuilt branch stack now passes the complete authenticated Chromium flow (`29/29`),
including Study Lab validation, isolated Python execution, and structured metric rendering.
The full backend unit suite passes (`965/965`, 69.83% coverage); the detached-auth rollback
regression is covered directly and backend logs are clean for 500s, tracebacks, pool leaks,
SQLAlchemy warnings, and unexpected errors. The research timestamp-default migration
`ea0f1a2b3c4d` has passed a PostgreSQL downgrade/upgrade round trip. A fresh disposable
PostgreSQL 16 audit against current HEAD also upgraded the complete chain to `ea0f1a2b3c4d`,
verified `watchlist_item.flagged` as `NOT NULL DEFAULT false`, downgraded one revision,
re-upgraded to head, and re-verified the invariant before the container was removed.
Current-head migration round-trip acceptance is closed.
The complete Docker-backed integration suite passes `281/281` with 54 existing dependency
warnings; its clean acceptance invocation is `--no-cov` because the integration-only subset
does not meet the repository-wide coverage threshold by itself.

The VirtualWatchlist Python polling path also rejects empty batch responses before they reach
Vue Query, preserving an explicit error contract for columns and Boolean conditions. This is
covered by the focused 46-test suite and the full 555-test frontend suite; the rebuilt
Chromium flow remains 29/29 with clean backend diagnostics. The same no-undefined query
boundary is now enforced for Market Gauge, retained EasyScan results, Research Results,
condition columns, and indicator batches; focused workstation coverage is 61 tests and the
full frontend suite is 555 tests across 84 files.

The browser acceptance harness now waits for expected unavailable-data responses before
diagnostic assertions and excludes only those documented API 404/409 responses from teardown
attachments. All four required display-scale visual probes also assert that core tool headers
and chart toolbar/surface rectangles do not overlap; each passes those geometry checks before
the exact-build screenshot gate rejects its unapproved baseline.

Raw API transport errors are not rendered in the dense workstation footer. The shell maps
common 401/403/404/409 and 5xx failures to concise recovery-oriented status text while
retaining the original diagnostic in the status tooltip. The regression covers 401/403/404/409
and 5xx mappings and is covered by the full frontend suite (`555/555`), production build, and
rebuilt Chromium flow (`29/29`).

The deep top-down browser flow now also focuses the constituent virtual list and traverses to
the next canonical member with `Space`, asserting that the linked active symbol changes without
a route transition. The complete authenticated flow remains `29/29`.

Golden Layout persistence no longer treats its observational visible-key list as a destructive
close operation. Explicit close actions remain the only path that removes a serialized tool;
this prevents transient/incomplete layout events during repeated pop-outs from deleting the
source window. The store regression and a ten-cycle browser lifecycle check cover the boundary,
including stable source canvas and browser-page counts. The full authenticated flow remains
`29/29`, including simultaneous independent pop-out recovery, and the post-run backend/runner
log audit is clean.

This is functional/runtime evidence only. The strict visual gate still rejects the required
`application-shell-default/default` state because the manifest remains `required_missing`;
discovery-only online media cannot be promoted without exact-build continuity, measurements,
permission/storage review, and human approval. Provider-live credentials, adversarial pressure
and cancellation, 10,000-row/multi-window performance, and the
complete cross-surface parity matrix likewise remain open.

## Cancellation-safe streaming evidence

The screener NDJSON route is an explicit lifecycle boundary rather than a normal
request-scoped database dependency. Authentication uses a short-lived detached session;
the route performs its ownership lookup in a separate short-lived session; and the stream
owns a dedicated session from the injectable `get_stream_session_factory` (production
returns `AsyncSessionLocal`) that always rolls back and closes in its body generator.
Rollback and close run in shielded child tasks so an ASGI disconnect cannot interrupt
asyncpg cleanup. The normal request dependency uses the same helpers for other routes.
SQLAlchemy pool termination records are filtered only when their exception is an
`asyncio.CancelledError`, preserving ordinary pool failures as errors.

Evidence: `test_screener_stream_lifecycle.py` covers route ownership and already-cancelled
cleanup; `test_database_cleanup_logging.py` proves the narrow logging filter distinction;
the full backend unit suite passed `926` tests; the Docker-backed integration suite passed
`281` tests; isolated F12 and the complete authenticated Chromium flow passed `26/26`; and
the fresh rebuilt-stack backend error/warning audit found no cancellation traceback, pool
leak, `InterfaceError`, `SAWarning`, or unexpected error.
This is runtime reliability evidence, not Version 25 visual approval; strict visual
acceptance remains controlled by the required reference manifest.

## Isolated research handoff and resource-pressure evidence

The Compose backend and isolated research runner now share explicit `/jobs` and `/results`
volume paths. Enqueue prepares the private volume directories with shared permissions so
the non-root UID 10001 runner can atomically claim backend-created jobs and write result and
progress files; job files are mode 0666 and no provider credentials are mounted. The runner
maps in-process `MemoryError` to a structured `memory_limit` diagnostic rather than an empty
runtime error.

Live evidence: a backend-enqueued 70-million-element allocation was claimed, returned the
`memory_limit` diagnostic, produced a processed sentinel, and left the capped runner
running. Full backend unit coverage passed 964 tests, research API integration passed 20,
deployment/research-job/runner tests passed, and all probe artifacts were removed. This
closes the fresh-volume handoff/path defect and one real memory-pressure case; orphan-job
cleanup after process termination, cancellation under pressure, and broader namespace/
multi-process stress remain required acceptance work.

The basic orphan recovery path has now been exercised against the same volume: a
`.running` payload was requeued by runner startup, completed as a typed scalar artifact,
and cleaned up while the capped non-root process remained healthy.

Read-only authentication lifecycle evidence: `GET /auth/me` and `GET /auth/settings` use
the detached identity-session factory, avoiding a request transaction that outlives response
serialization; writes remain request-scoped. Auth integration passed 15 tests, the full
backend unit suite passed 964, and the rebuilt authenticated Chromium flow passed 26/26 with
no pooled-connection or SQLAlchemy warning in the fresh backend/runner/worker log window.

## Authentication-session lifecycle evidence

The authenticated legacy-route matrix exposed a separate session-lifetime defect around
identity lookups during navigation and pop-out work. Normal `get_current_user` now shares the
ordinary request-scoped `get_db` session, so FastAPI owns one transaction and one finalizer for
the route instead of creating a second identity connection and manually closing it before the
generator finalizer runs. The detached streaming variant uses an injectable
`get_auth_session_factory`, opens one short-lived identity session, and closes it explicitly
before the response body starts. Cleanup helpers also accept the synchronous compatibility
adapters used by controlled tests without scheduling a non-awaitable return value.

Evidence: the ten-surface `/legacy/*` Chromium matrix passed without login redirects or fatal
overlays; backend unit coverage passed `926` tests; Docker-backed integration passed `281` tests;
the rebuilt complete Chromium flow passed `26/26` in `45.5s`; frontend Vitest passed `547` tests;
TypeScript, production build, and diff checks passed; and a fresh backend-log audit found no
garbage-collector/non-checked-in connection, `SAWarning`, `InterfaceError`, cancellation trace,
provider-runtime error, or unexpected warning. This closes the observed auth-session leak class;
it does not alter the strict V25 visual gate or broader performance/security/parity gates.

## Repeated pop-out lifecycle evidence

The browser acceptance matrix now includes repeated and simultaneous lifecycle regressions:
F8f floats and closes the same workstation tool ten consecutive times while retaining source
canvas/page counts, and F8h keeps two concurrent pop-outs independently recoverable. The
complete authenticated flow file passes `28/28` and the rebuilt-stack backend error/warning
audit is clean. This closes only the covered source-tool/pop-out lifecycle cases; multi-monitor
placement, long-running memory behavior, and broader workstation performance remain open.

Top-down asynchronous reads now use per-surface generation guards across market groups,
group snapshots, breadth/history, technical summaries, holdings, industries, constituent
snapshots, and proxy rankings. A rapid linked-symbol or timeframe change cannot let a late
response replace the current metrics, rows, or error state. Workspace-store regressions cover
stale SPY/XLK and daily/weekly analysis races; browser and full cross-window acceptance remain
open.

The deterministic browser fixture now seeds 520 adjusted D1 business-day bars for the benchmark,
sector, proxy, and constituent paths, point-in-time XLK/SMH/SOXX holdings, and explicit
Semiconductors/Systems Software classifications. The rebuilt deep acceptance flow reaches
XLK → Semiconductors → SMH → NVDA and verifies the linked ratio label follows the selected
constituent. RatioUPlot reloads its aligned series when mounted-tool symbol, benchmark, or
timeframe props change; auto-ratio rendering also derives from the current linked symbol while
the persisted configuration catches up. This is functional evidence only; strict pinned-build
visual approval remains controlled by the reference manifest.

Persisted Golden Layout snapshots from the pre-v8 workstation format are migrated at the
layout boundary: legacy numeric `width` values are converted to v2 `size` fractions only for
column nodes, while arbitrary tool-state width fields remain unchanged. The migration has a
focused regression test and is covered by the full frontend suite; this prevents existing
users' saved proportions from being silently discarded after the factory-layout upgrade.

Shared tool-window chrome now renders human-readable link-group labels and color swatches for
both symbol and timeframe links while retaining canonical group IDs in emitted events. This
keeps yellow wildcard and grey isolation discoverable in docked and pop-out tools without
coupling persistence to display text.

Current implementation evidence (not completion): the isolated Study Lab runner now
supports a typed `histogram` artifact with deterministic numeric buckets, the factory
positive-close study exposes current/longest/average/shortest streak metrics,
point-in-time forward-return rows, symbol-linked streak occurrences, and completed-
streak lengths for that distribution, and both
primary Study Lab result surfaces render the artifact through a uPlot bar overlay. The
runner now also emits typed numeric `scatter` artifacts, rendered by a dedicated uPlot
point-cloud surface with aligned x/y validation, and bounded rectangular `heatmap`
artifacts rendered by a native matrix surface. Focused runner, validation, Study Lab,
and persisted-results tests pass; visual parity remains blocked until the required
approved Version 25 references exist.

The shared Python validator and Study asset contract now recognize `scatter` and
`heatmap` output methods, so these structured artifacts survive validation and can be
reused from the same unified language rather than being runner-only extensions.
Study Lab structured outputs now also include typed categorical/numeric `bar` artifacts
and aligned lower/upper `range` bands with an optional center series. The isolated runner
validates finite values and dimensions, persists the native payload, and the active Study
Lab, persisted Research Results, and dashboard renderers display them through uPlot
components with in-place updates and teardown. This completes the remaining first-pass
native bar/range result contracts; visual acceptance still requires approved V25 baselines.

Historical chart pagination now uses a bounded, timeframe-aware repair window when the
local page is short. It anchors the request at the oldest cached bar (or a minimum cold
bootstrap window) with a small overlap, rather than fetching from the 1970 epoch; pure
service tests cover both warm-tail and cold-start calculations.

Explicit historical range reads now detect bounded edge gaps and calendar-aware internal
gaps. USD instruments use a deterministic local XNYS daily session calendar (weekends,
Good Friday, observed federal-market holidays, and Juneteenth) so expected closures are
not fetched as missing bars while a missing weekday is repaired independently. Instruments
without an explicit supported calendar retain the conservative interval-based fallback.
Focused service tests cover internal repair, the no-fetch weekend/holiday cases, and the
missing-weekday case.

The reusable `ohlcv_coverage` service now owns the provider-neutral readiness decision
for a requested instrument/timeframe/range. It distinguishes `ready`, `partial`,
`missing`, and latest-window `stale` states, returns bounded repair slices, and accepts an
injected clock for deterministic evaluation. The existing market-data read path uses the
planner while retaining provider access and persistence at its boundary; future chart,
scan, alert, and research preflight callers can consume the same contract without
reimplementing freshness logic.

Authenticated `/coverage/instruments/{symbol}/ohlcv` now exposes that assessment as a
canonical frontend contract. Callers provide timeframe, range, adjustment, and historical
versus latest mode and receive status, local bounds, bar count, bounded missing slices,
and an explanation with canonical-database provenance; reversed ranges and unknown
instruments are structured errors, and provider names/fallback order are never returned.

The primary workstation Coverage tool now consumes this range contract directly. Its
serializable controls retain timeframe, UTC-normalized start/end dates, historical/latest
mode, and split-adjustment choice in the workspace window configuration. A range check is
explicitly user-triggered, rejects reversed or incomplete ranges before dispatch, ignores
late responses after a symbol change, and renders ready/partial/missing/stale status,
covered bounds, bar count, explanation, and every bounded missing slice. The tool still
loads aggregate canonical coverage separately, so a readiness check never causes provider
fan-out or silently changes the active symbol.

The isolated image also installs pinned NumPy/Pandas wheels at build time and exposes
only restricted `np`/`pd` facades to user code. File/external-data methods are rejected
by source validation; NumPy/Pandas values are normalized before artifact persistence.
The rebuilt image import check reports NumPy `2.1.3` and Pandas `2.2.3`.

Study datasets now preserve the complete canonical OHLCV shape rather than reducing the
isolated input to closes: aligned `opens`, `highs`, `lows`, `closes`, nullable
`volumes`, `vwaps`, and timestamps are materialized for the declared instrument and
benchmark. The unified `market` namespace exposes `open`, `high`, `low`, `close`,
`volume`, `vwap`, and aligned `ohlcv()` access, while retaining the compatibility rule
that close-only hand-authored fixtures remain valid. Missing fields produce structured
runner diagnostics and never trigger provider access.
The same namespace exposes declared timestamps, session labels, and canonical instrument
metadata (identity, currency, active/synthetic state, and primary identifier) so studies
can make explicit metadata/session decisions without importing application models or
calling providers.
When a benchmark is materialized, the same namespace exposes explicit
`benchmark_*` accessors for aligned OHLCV, timestamps, sessions, and metadata; an absent
or unavailable benchmark returns a structured runner diagnostic rather than silently
falling back to the primary instrument.
The unified language also exposes a bounded set of ordinary Python composition builtins
(`len`, `sum`, `min`, `max`, `range`, collection constructors, and related pure helpers)
in both validators and the isolated runner. Dunder names remain rejected, so this
improves normal Python expressiveness without widening host, filesystem, network, or
dynamic-execution access.
Run configurations are now injected as a JSON-only `parameters` mapping in both single
instrument and prepared-universe batch execution. Parameter values stay inside the
isolated process and are included in the run payload/reproducibility input; malformed
non-object parameters fail explicitly before user code runs.
The API now treats each immutable code version's parameter schema as authoritative: it
merges declared defaults, validates required/type/enum/range/unknown-key constraints,
and rejects invalid runs before dataset materialization or sandbox enqueue.
The same gate runs when assets are created, imported, or versioned, so invalid defaults
cannot be persisted as immutable code versions in the first place.
Prepared-universe Study Lab runs now have a structured path: `output_contract: study`
executes once over the declared, provider-free `market.universe()` datasets, allowing
ranked tables, distributions, dashboards, and other typed aggregate artifacts. Structured
event outputs may identify any symbol in the declared universe and remain constrained to
that point-in-time prepared dataset; they cannot introduce undeclared symbols. Scalar and
Boolean watchlist/condition batches retain their bounded per-instrument cell contract.
Completed Study Lab runs with exactly one validated scalar, series, or Boolean output
contract can now be promoted without copying mutable run state: scalar results create a
reusable Python watchlist column, series results create a reusable chart plot, and Boolean
results create an EasyScan condition with an optional screener alert. The promotion keeps
the immutable source, parameter schema, timeframe, and canonical-data contract. Polymorphic
`study` runs remain research-only until the author explicitly supplies a single-contract
asset, avoiding ambiguous promotion of a dashboard or mixed artifact set. Focused
StudyLabTool coverage exercises the scan and alert paths; full visual and acceptance status
remains in progress.
The active Study Lab run panel also exposes snapshot and latest-data reruns through the
canonical research rerun API; queued responses return to the shared polling coordinator,
while the immutable code version and run configuration remain unchanged.
The primary editor now ships editable factory templates for consecutive positive closes,
consecutive negative closes, moving-average participation, and relative-strength history.
Selecting a template replaces only the draft source/name and clears stale validation/run
state; editing the source switches the selector to Custom Python, preserving normal Python
freedom without creating a second language.

Top-down drill-down correction: selecting a verified industry ETF proxy from the
industry surface now activates the canonical proxy symbol across the blue link group,
loads its bars and technical snapshot, updates the automatic ratio target, and retains
the selected sector/industry context. The proxy therefore behaves as an analysis target
(`SMH` within `XLK`/Semiconductors, for example) rather than a cosmetic table selection
that leaves linked charts on the prior instrument. Focused pop-out binding coverage
passes; exact-build visual and full end-to-end acceptance remain open.

Top-down cell provenance correction: benchmark, sector, constituent, and verified
industry-proxy row adapters now retain canonical per-cell warning messages from the
analysis response. Virtualized watchlists display the warning text for null values,
so insufficient history, unavailable comparisons, and coverage exclusions remain
visible at the cell where they occur instead of becoming silent dashes. Focused
virtual-watchlist coverage passes; broad visual and acceptance gates remain open.

Breadth drill-down correction: the breadth tool now exposes a canonical universe
selector (`S&P 500 sectors` or `US benchmarks`), separate Above and Below controls for
each 20/50/200-MA aggregate, and corresponding passing/failing members as linked rows.
Changing the universe loads its group snapshot plus current/historical breadth through
the local analysis APIs. Selecting a row publishes its canonical symbol to workstation
charts without a route change; the historical uPlot breadth series remains visible
alongside the drill-down. Daily/weekly/monthly timeframe and split-adjustment controls
are persisted and forwarded consistently to the group, snapshot, current-breadth, and
history requests. Focused workstation/watchlist/store coverage, TypeScript, and
production build pass; visual and full acceptance remain open.

Breadth analytics now also return canonical near-52-week-high/low, configurable
new-high/new-low, uptrend/downtrend, and aggregate moving-average-distance metrics,
with the request lookback echoed in the response. The workstation summary renders these
values with explicit unavailable states and shows metric-family coverage detail. The focused router suite and frontend store/
watchlist boundary pass; member-level high/low and trend metrics now power linked
advanced-statistic drill-downs with an in-place Pass/Fail toggle; Docker-backed integration
verification is still required.
Study Lab exposes a serializable comma-separated universe control; when populated it sends
canonical symbol selectors as `run_config.symbols` and displays the selected universe in
the run summary instead of silently using only the active symbol.
The authenticated research API now materializes that selector into a bounded canonical
dataset manifest, preserves requested order, and returns exact per-symbol exclusions for
unknown instruments or missing history before the isolated job is queued.
EasyScan result rendering now tolerates partial or malformed retained payloads: missing
match arrays and coverage metadata render as explicit zero/coverage-unavailable state
instead of throwing during a reactive update. Polling also treats missing result metadata
as non-terminal until a valid terminal status arrives.
Study Lab now exposes the same schema as generated controls, converts numeric and boolean
values before creating the immutable code version, and sends the resulting typed parameter
map with the run. The schema remains serializable in the workspace configuration boundary.
Editing or clearing the schema immediately updates that persisted window configuration, so
floating, reloading, or restoring the Study Lab does not silently discard its controls.
The editor also provides constrained cursor-word suggestions and inline signatures for
the supported SDK namespaces, plus a compact reference panel; suggestions only insert
ordinary Python source and cannot execute code or inject frontend content.

Unified Python assets now have lifecycle contracts for complete export/import, immutable
version-preserving clone, and reversible archive/unarchive operations. Each imported or
cloned version is revalidated against its asset kind and output contract before it is
persisted; user ownership and stable-key uniqueness remain enforced by the canonical API.
The primary workstation now exposes those operations through a dockable Python Library
tool with filtering, archived-state visibility, file import, JSON export, clone,
archive/unarchive, typed new-asset creation, and immutable new-version editing controls;
the component is covered by focused lifecycle and interaction tests. Editing always posts
a new validated version and never mutates an existing source record. New assets select a
surface kind and send the corresponding output contract through the same canonical API.

Python watchlist columns now carry an explicit serializable timeframe (defaulting to the
owning watchlist's linked timeframe when first added). The column editor exposes the
timeframe selector, reruns the isolated prepared-universe batch after a change, and sends
the selected timeframe in both `run_config` and the dataset manifest; restored columns
without a timeframe remain backward-compatible through the linked-timeframe default.
The same explicit timeframe contract now applies to persisted Python Boolean conditions:
the filter editor exposes it, stores it with the condition binding, and includes it in
the prepared-universe evaluation request.

Python `plot` assets are now first-class chart plot targets. The Chart Plot Library loads
user-owned plot versions on demand, persists selected code-version/color/timeframe state
in the chart window, and the workstation evaluates those versions through the isolated
research API. Typed `series` artifacts are aligned to canonical chart timestamps and
passed to uPlot as native series; invalid, incomplete, or failed artifacts are omitted
without injecting arbitrary frontend code.
When the chart symbol, timeframe, or selected plot set changes, the workstation cancels
the prior Python plot runs and ignores late results by generation, preventing stale
research work from replacing the active chart.

The relative-rotation uPlot surface now updates `setData`/`setSize` in place during
resize and data refresh; it destroys the chart only during component teardown. A
dedicated regression test proves repeated resize callbacks do not create additional
uPlot instances.

Relative Rotation now exposes and persists its transparent inputs: market-group universe,
benchmark, timeframe, sampling cadence, split-adjustment mode, lookback, and tail length.
Those values are sent to the canonical analysis endpoint rather than being hidden
SPY/D1/20/10 constants; load generations prevent a late rotation response from replacing
a newer selection.

Relative Rotation also accepts a bounded sampling cadence (every 1–30 aligned observations)
and always includes the latest aligned observation. Sampling is persisted in factory and
user tool configuration, returned in the response, and used consistently for trend,
momentum, and tail calculations; the default cadence remains one observation.

Each rotation row now also returns transparent `heading` (degrees), `distance`, vector
`velocity`, a state `transition` when the latest sampled state changed, and consecutive
`time_in_state`. The companion table exposes those values alongside trend, momentum,
coverage, and tail length instead of implying proprietary rotation metrics. Every companion
column is sortable with null-safe ordering and a visible direction marker. The uPlot
rotation plane now draws each member's color-coded historical tail as a connected trail,
labels the Leading/Weakening/Improving/Lagging quadrants, and identifies the nearest tail point on
hover with symbol/date/coordinates, and emits the normal linked-symbol selection when a
hovered point is clicked; focused component coverage proves the interaction without
recreating the chart.

The Relative Rotation backend now accepts an optional point-in-time `as_of` and applies it
to both versioned market-group membership (`effective_at`/`known_at`) and local bars. The
response echoes the cutoff and provenance selection rule, rejects groups not known at the
requested time, and never uses future members or future observations in the ratio tail.
The Docker-backed regression is recorded but remains unexecuted in the current environment
because its Docker socket is unavailable; unit coverage proves the timestamp-selection helper.

The same cutoff contract is now available on group snapshots, current breadth, and breadth
history. Sector ranking, equal-weight comparison, and breadth history can therefore be
replayed against a declared membership/bar cutoff, with shared provenance and coverage
metadata instead of silently mixing current membership with historical observations.

The canonical relative-strength ratio endpoint now accepts the same optional point-in-time
`as_of` cutoff and truncates both local series before intersecting timestamps. The response
echoes the cutoff, while the uPlot ratio component accepts an optional persisted cutoff for
historical drill-downs. Its compact `As of` control emits serializable tool configuration,
so docked and floated ratio windows retain the cutoff through workspace snapshots; current
views omit the parameter when the control is blank. The focused frontend contract and
backend helper suites pass; the Docker-backed route regression remains recorded but
unexecuted because Docker socket access is unavailable. Ratio loads also use an active
generation guard, so a late response from a prior symbol/timeframe/as-of selection cannot
replace the current ratio window; the focused component suite covers that race.

Queued Python EasyScan runs now expose their isolated research-run cancellation
control in the primary workstation. Cancellation remains isolated to that run and
the result polling path reconciles the terminal `canceled` state.

The persisted Study Results browser exposes the same cancellation contract for
queued/running research runs, preserving the run list and selected result while the
isolated worker transitions to its terminal state.

The Market Gauge tool now uses the shared TanStack Vue Query cache for retained
EasyScan definitions and gauge snapshots. Selecting a scan fetches its canonical
local-database gauge, active visible gauges refresh on the configured freshness
interval or through an explicit Refresh control, and hidden tool surfaces/document
visibility suspend automatic requests. The dense tool chrome exposes the returned
freshness state, provenance, calculation version, and coverage-warning count. A
component regression covers selection, refresh, stale-data labeling, and lineage
display. This is functional evidence only; the Version 25 visual reference remains
unapproved.

The workstation shell now exposes a single deduplicated top-down refresh command. It
refreshes benchmark and sector memberships, sector rankings, current breadth, and
historical breadth together; concurrent callers join the same request set, the shell
shows an in-progress Refresh control, and an active workstation polls every five
minutes only while the document is visible. The store records the last successful
refresh time only when every shared input succeeds, while the existing response
freshness and coverage fields remain the source of truth for stale or partial data.

The workstation shell's five-minute refresh is now coordinated by the shared TanStack
Vue Query client rather than a component-owned interval. The query is keyed as
`workstation/market-analysis`, uses the store's deduplicated refresh promise as its
single query function, pauses while the document is hidden or the tool is a browser
pop-out, and resumes through the same cache when visibility returns. The explicit
Refresh control calls the query refetch path, so manual and scheduled refreshes share
the same request identity. A WorkstationView regression covers hidden-document pause,
visibility restoration, and the pop-out exclusion; TypeScript, production build, and
the full frontend suite remain green. This is functional polling evidence only; the
Version 25 visual reference remains unapproved.

The Add Tool registry now includes every implemented primary analysis surface that was
previously factory-only: Relative Rotation, Market Breadth, Technical Summary, Coverage,
and Instrument Report. Each uses a stable tool type and serializable configuration, while
excluded domains remain absent from the registry.

The benchmark watchlist now consumes the same canonical group snapshot as the sector
workflow. It displays SPY/RSP and other benchmark rows with 1D/1W/1M/3M/YTD/1Y
performance, `/ SPY` ratio, RSI, 52-week position, and volume-ratio columns, so the
cap-weighted versus equal-weight comparison is available before sector drill-down.
Its identity strip separately labels the logical S&amp;P 500, official `SPX` series, and
the currently used tradable `SPY` proxy; the UI never relabels proxy data as SPX.

ETF constituent snapshots now carry two explicit relative-strength cells when requested:
the constituent versus the selected sector/ETF benchmark and the constituent versus an
independently named market benchmark (the primary workstation supplies `SPY`). The
batch endpoint accepts `market_benchmark`, aligns both ratios to the same local bar
timestamp, returns structured missing-alignment warnings, and echoes both benchmark
identities. Constituent watchlists render both `/ XLK`-style and `/ SPY` columns rather
than forcing the user to leave the drill-down or manually reconfigure the ratio chart.
The same endpoint accepts an optional point-in-time cutoff. At a cutoff it admits only a
holdings disclosure whose composition date and `known_at` timestamp are both historical-
safe, truncates all comparison bars at that cutoff, and records the requested cutoff in
provenance; it never silently falls back to a current snapshot. The integration contract
has a dedicated regression for this selection rule.

The ETF industry composition, curated-proxy, and industry-constituent routes now apply the
same historical rule: an explicit `as_of` requires both composition date and non-null
`known_at` at or before the cutoff. Undated disclosures remain available to latest/current
views but cannot contaminate point-in-time research.

Group breadth now preserves the requested point-in-time cutoff separately from the latest
bar available in the returned data. Its `as_of` describes the latest usable observation,
while `universe_provenance.membership_as_of` remains the caller's cutoff in canonical UTC
wire format; this prevents a data-availability timestamp from replacing the historical
membership boundary used by the calculation.

Factory `Drill Down` and `Sector by Year` industry windows now use the selected ETF's
point-in-time industry composition rather than falling through to benchmark rows.
Industry selections publish the industry key into the linked drill-down, preserve
resolved/total constituent coverage, and expose verified proxy counts when available.
The `Sector by Year` sector window now consumes canonical calendar-year return cells
from the group snapshot (five bounded years, with explicit no-bars and insufficient-
history warnings) and renders those years as selectable percentage columns. This is
functional evidence only; the Version 25 visual reference remains unapproved.
All shared ranking snapshots now calculate `YTD` from the first available bar in the
current calendar year rather than treating 252 bars as a calendar boundary, and emit
an explicit insufficient-YTD warning when the year has fewer than two valid bars.
Fixed-period returns likewise return a structured zero-base warning rather than
dividing by zero, preserving valid cells and exact exclusion reasons in batch output.
The factory relative-strength chart is now explicitly auto-ratio-enabled: selecting
SPY/RSP, a sector, a constituent, or an industry proxy updates it to the relevant
benchmark relationship while custom expressions remain untouched.

The chart plot library now retains the linked-chart shortcut and adds explicit target
mode for copying an indicator plot to any other chart or watchlist window in the active workspace,
including isolated/grey-link charts. The copy operation clones parameters, style, and
timeframe locks without replacing the target symbol. A selected plot can also be copied
into a reusable indicator-threshold condition, an EasyScan created from that condition,
or an indicator alert for the active canonical instrument; each promotion preserves the
indicator parameters, chart timeframe, operator, threshold, and provenance metadata.
Watchlist targets persist indicator-column definitions in serializable workspace
configuration. The workstation loads each configured indicator in one canonical
`/analysis/indicator-batch` request per column over the local security master and bars,
returns cell-level warnings plus coverage, and renders numeric values in the same
virtualized column/filter editor with null-safe numeric sorting. Unknown instruments,
missing bars, unsupported indicators, and insufficient history remain explicit rather
than triggering provider fan-out. The same promotion flow can create an EasyScan
from the saved condition and bind it to a selected watchlist window as an active persisted
filter; later filter edits still use the shared integrated column/filter controls. Visual
approval remains blocked by the V25 reference manifest.
Indicator-column requests use the shared TanStack Vue Query cache keyed by the sorted
canonical symbol set, indicator parameters, timeframe, adjustment, and output, so
docked/pop-out watchlists reuse active results instead of fanning out duplicate requests;
the 30-second cache window is separate from historical chart polling.
When the active symbol set, timeframe, or configured indicator changes, obsolete
indicator queries are canceled through Vue Query and an `AbortSignal`-aware API client;
generation guards still prevent any already-returned response from replacing newer
cells.

Chart plots now expose a bounded versioned drag payload (`application/x-charting-platform-plot`)
containing only canonical indicator type, primitive parameters, timeframe, label, and source
window identity. The payload is validated before use and cannot carry executable frontend
content or uPlot state. Virtualized watchlists accept the payload as a drop target and persist
the resulting numeric indicator column through the owning workstation window; EasyScan accepts
the same payload as an editable technical-condition node in its shared condition tree. Focused
ChartPlotLibrary, VirtualWatchlistTool, EasyScanTool, and payload-validation tests cover the
source, both targets, malformed versions, unknown indicators, invalid timeframes, and bounded
payloads. EasyScan condition trees are also drag sources: dropping one into a watchlist saves
the canonical condition, materializes/runs an EasyScan through the existing local screener API,
and persists a Boolean column keyed by the screener result; the watchlist refreshes that result
through Vue Query and renders True/False/unknown cells with Boolean sorting. This is functional
drag/drop evidence; exact-build visual approval and full browser acceptance remain separate
gates.

Floated workstation tools now forward watchlist condition modes, Boolean pinning,
column grouping/stacking, arbitrary serializable configuration, and industry-proxy
selection back to the source shell. Pop-out startup hydrates the existing link-group
symbol without publishing a default `SPY` selection into the source workspace. Focused
watchlist Space/Shift+Space traversal stops at the list boundary, and a shared editor
target guard suppresses workstation and uPlot shortcuts inside native inputs,
contenteditable/code editors, and role-textbox search surfaces. Dedicated pop-out,
keyboard-boundary, symbol-preservation, and editor-target tests plus the full frontend
suite provide functional evidence; visual approval remains blocked by the manifest.

Workstation chart windows now expose persisted comparison symbols and feed normalized,
timestamp-aligned comparison series into the existing uPlot renderer. Comparison anchors
are explicit, missing timestamps remain gaps, and each target exposes a return summary;
the comparison utility has deterministic alignment and no-valid-anchor coverage tests.

Virtualized watchlists now support desktop-style plain, Ctrl/Meta, and Shift selection
while retaining canonical row activation. A multi-selection exposes a Compare action;
the workstation routes it to the first non-ratio chart and persists up to six comparison
symbols without changing the active symbol. Component coverage proves selection semantics
and the full frontend suite remains green. Arrow/Space traversal and Ctrl+wheel now also
update the selection model, while filtering prunes symbols that are no longer visible;
the pop-out binding test proves the comparison event reaches the persisted chart config.
This is functional evidence only; the Version 25 visual reference remains unapproved.

Virtualized watchlist rows now expose a wired desktop context menu for opening the row's
chart, comparing it with the active symbol, opening symbol notes or alerts, and copying
the canonical ticker. Actions are routed through `WorkstationView` for docked and floated
tools; no context-menu item is a dead visual control. Focused component and pop-out
binding tests cover the menu and shell routing. This is functional evidence only; the
Version 25 visual reference remains unapproved.

The integrated column editor now persists per-column display overrides alongside the
existing visibility, order, grouping, stacking, and Boolean-pinning settings. Users can
rename a column and set a bounded pixel/fraction/percentage track width without changing
the canonical field key or row identity; every workstation watchlist, including personal
lists, uses the same serializable configuration path. Focused virtual-list coverage proves
the override events and restored header rendering; visual approval remains blocked by the
V25 reference manifest.

Numeric columns additionally expose persisted percent-versus-number formatting and bounded
decimal precision, including indicator and Python-derived columns, so dense ranking tables can
be tuned without changing their canonical values.
Numeric cells also receive automatic positive/negative/zero color classes while Boolean and
warning cells retain their explicit state colors.

The same editor now supports direct drag-and-drop ordering in addition to its explicit
left/right controls. Dragging emits the shared visible-column configuration, so saved
column sets and floated/docked watchlists retain one ordering contract; focused virtual-
list coverage proves the reorder event.

Personal watchlist item order is now persisted through
`POST /watchlists/{watchlist_id}/items/reorder`. The endpoint requires the complete item
set, assigns contiguous positions, rejects duplicate or incomplete IDs, and refuses
managed or locked lists. The Pinia watchlist store applies the order optimistically and
restores the prior order if persistence fails. Docker-backed watchlist integration and
store regression coverage prove the contract; the primary workstation's managed market
groups remain source-ranked and are not incorrectly presented as manually reorderable.

The primary workstation now exposes a first-class personal `WatchList` tool in its tool
library. It loads user-owned lists through the canonical watchlist store, persists the
selected list ID in the serializable workspace window configuration, renders symbol/name/
last/change columns through the same 10,000-row virtualized table, and publishes row
selection into the linked-symbol bus. Unlocked personal lists expose HTML drag ordering;
managed and locked lists remain visibly non-reorderable. Editable lists also expose
canonical symbol insertion and a context-menu removal action; locked/managed surfaces do
not expose either mutation. The focused virtual-list suite covers source-item-ID
preservation during drag/drop and the explicit removal boundary; visual approval remains
blocked by the V25 reference manifest.

The same context menu now exposes explicit personal-list membership actions. Any
workstation list can copy a canonical row into a selected unlocked personal list; an
editable personal list can move its row by adding it to the destination first and removing
the source item only after the destination accepts it. Current/source and locked targets
are disabled, and the action carries canonical instrument and destination IDs rather than
ticker-only state. Focused virtual-list coverage proves both copy and move events.
The same menu can expand canonical membership inspection, showing every personal list
whose stored instrument IDs contain the selected row and identifying the current source;
it does not infer membership from ticker text.

Watchlist items now also have a durable user flag. The authenticated item PATCH contract
persists `flagged` independently of membership locks, personal rows render the marker, and
the context menu toggles Flag/Unflag only when a canonical source item exists. Reloaded
watchlists retain the state, and copied lists preserve flags for retained items.

The personal WatchList tool now exposes a derived `Flagged Items` source alongside named
personal lists. It deduplicates flagged canonical instruments across the user's personal
lists, retains the originating watchlist and item IDs for linked context-menu actions,
disables membership-mutating controls that have no valid source list, and allows a flag to
be removed through the same authenticated PATCH contract. The derived view is persisted as
the serializable `watchlist_id: "flagged"` selection and refreshes from the canonical
watchlist store, so it remains consistent across reloads and pop-outs. Component coverage
now proves the flagged marker, preserved source item identity, and explicit Unflag action;
visual approval is still blocked by the V25 reference manifest.

The same WatchList source selector now supports user-owned combo lists. A combo is stored
as a versioned `combo_list` library item with canonical source watchlist IDs and explicit
union, intersection, and exclusion sets; it never evaluates ticker text or silently
materializes a new membership list. The editor loads, creates, updates, and deletes these
definitions through the authenticated library API, while derived rows retain the first
participating source item for linked selection, copying, and flag actions. Empty or
unavailable source lists produce an empty, explicit result rather than a provider fan-out.
The focused helper suite covers union/intersection/exclusion, intersection-only seeds,
canonical deduplication, deterministic source metadata, and quote projection. Visual
approval remains blocked by the V25 reference manifest.

Virtualized watchlist condition and Python batch requests now carry both a request
generation and a linked-universe generation. Changing the active universe invalidates
late results, starts evaluation for the new rows, and prevents old matches, progress,
errors, or cancellation state from filtering or annotating the replacement list. A
focused regression resolves the old saved-condition request after the new universe and
proves that the new rows remain unfiltered by stale matches.

The same tool now supports creating and renaming user-owned lists in place. The selected
list name and ID remain serializable workspace state, while managed/locked rename paths
are disabled and backend `409` conflicts are surfaced as explicit recovery text rather
than silently overwriting another window's change. Store and full-workstation regression
coverage remain functional evidence only; visual approval is still blocked by the V25
reference manifest.

Personal list management also exposes copy and confirmed deletion for editable lists.
Deletion selects the next remaining user-owned list only after the canonical delete
request succeeds; locked and managed lists cannot be deleted. A failed or conflicting
delete returns an explicit failure, leaves the local list and selection unchanged, and
surfaces recovery text rather than fabricating success.

Watchlist mutations now publish a `BroadcastChannel` invalidation event. A floated tool
that adds, removes, reorders, creates, renames, copies, locks, unlocks, seeds, deletes, or
reorders lists causes other workstation windows to reload the canonical watchlist cache,
so docked and pop-out surfaces converge without sharing non-serializable Vue state. When
`BroadcastChannel` is unavailable, the same event uses the browser storage-event fallback;
both paths have direct store regression coverage.

Linked Notes and Alerts tools now guard every symbol-scoped load and mutation with a
view-generation token. A slower response for a previously selected instrument cannot
overwrite the newly linked instrument, leave its loading state stuck, or apply a stale
alert mutation to the new symbol. Focused race regressions cover both tools; visual
approval remains blocked by the V25 reference manifest.

The primary Alerts tool also lists saved EasyScan alerts alongside price and indicator
alerts, with the same pause/resume, repeat, rearm, delete, and user-scoped mutation behavior;
this makes scan-entry/exit alerts visible from the shared alert workstation surface.
The backend screener-alert integration contract now covers create/list/pause/repeat/rearm/delete
and cross-user read/update isolation. The test is Docker-backed and remains environment-blocked
when the current runner cannot access the Docker socket.
Global EasyScan alerts are also loaded before an instrument identity is available, so the
primary alert surface does not lose scan-entry/exit state during workstation startup or
empty-symbol recovery.

Alert notifications now use authenticated, user-scoped WebSocket delivery. The screener
engine targets the correct user instead of calling the nonexistent legacy manager symbol,
and the frontend passes its access token to the socket and renders scan entry/exit events.
Unauthenticated legacy/test sockets retain only the explicitly broadcast compatibility path;
production alert evaluators no longer broadcast one user's alert payload to every client.
The frontend also accepts both the current `kind` and older `alert_kind` payload keys, so
indicator notifications cannot be misclassified as price alerts during compatibility windows.
The application now opens the socket only while the auth store is authenticated and closes it
on logout, preventing an anonymous pre-login connection from surviving into the user session.
Screener entry/exit firings are persisted as user-scoped `screener` history events with the
instrument, scan, direction, and run snapshot, so the existing alert history and instrument
filter APIs retain scan events alongside price and indicator firings.

The workstation shell and shared tool-window chrome now consume one global token sheet for
font stack, shell/window/control surfaces, borders, accents, state colors, density, and core
heights. The values mirror the current measured implementation and remain explicitly reviewable
against the approved four-environment V25 reference pack rather than being scattered literals.

The shared chart store applies the same generation boundary to instrument metadata,
indicator configuration, OHLCV pages (including infinite-history backfill),
transformed/synthetic bars, loading/error state, and coverage polling. Rapid symbol
changes therefore cannot paint an older response into
the active uPlot model; a focused two-symbol store regression proves the current symbol,
instrument, bars, and loading state remain aligned.

Top-down ETF holdings, constituent snapshots, sector/industry composition, industry
constituents, curated proxies, and proxy rankings use active-request generations as
well. Rapidly traversing SPY → XLK → XLE or switching industries cannot replace the
current drill-down with a late response from the previous selection; the workspace
store regression covers the active ETF boundary.

Chart-tool synthetic-expression resolution is generation-guarded before it hands a
target to the chart store, so a late `=XLK/SPY` or symbol-resolution failure cannot
overwrite a newer linked chart selection.

The primary EasyScan tool now exposes the shared technical-condition editor in addition
to its quick price/volume builder. Saved conditions can use indicator, price, period,
performance, 52-week, and statistics condition types under AND, OR, or NOT composition,
including recursively nested groups, while the existing unified-Python condition path
remains available. Scan definitions now also carry an explicit timeframe and all,
watchlist-ID, basket-ID, or custom instrument-ID universe selector instead of silently
hard-coding all instruments/D1. The focused scan suite proves both the advanced tree and
universe/timeframe fields are persisted through the canonical condition contract, and
supports manual, daily-close, and weekly-close cron scheduling. Completed runs retain a
bounded recent-result history in the tool, with a selector for inspecting prior match
sets without rerunning the scan.

The shared timeframe-link compatibility path now preserves valid `M1` one-minute
timeframes and normalizes only the legacy `MN1` monthly token to canonical `MN`.
This prevents intraday selections from being silently converted to monthly bars while
retaining persisted legacy-state recovery. The primary workstation shell and shared
tool-window selectors expose the complete supported set from `M1` through `MN` rather
than silently reducing linkable tools to four coarse intervals.

Study Lab now exposes explicit timeframe, benchmark, adjustment, session, and date-range
controls in the primary workstation tool. The research-run API validates those controls,
materializes only the requested canonical bars, records the normalized dataset manifest,
and rejects unsupported adjustments, invalid sessions, malformed dates, and reversed ranges.
The selected benchmark is now materialized as a separate aligned canonical close series
when available, exposed to the isolated Python runtime as `benchmark`, and reported with
explicit ready/unavailable coverage. The tool displays the selected dataset contract and
benchmark coverage alongside reproducibility output. Session remains an explicit canonical
metadata setting until session-qualified bars are available; it does not imply provider-
specific intraday availability. Focused backend, runner, and component tests cover the
contract. This is functional evidence only; the Version 25 visual reference remains
unapproved.

Canonical OHLCV bars now carry a persisted session classification (defaulting existing
history to `regular`) with an indexed instrument/timeframe/session access path. Study Lab
regular runs filter to regular-session bars, while `all` runs retain pre-market and
post-market classifications when present. Provider ingestion still reports only the
classification it can substantiate; it never infers a session from an unqualified source.

The isolated runner now restores process resource limits and alarm handlers after each
single or batch execution. CPU limits are offset from already-consumed process time while
preserving the hard boundary, preventing an in-process caller or test harness from
inheriting an immediately-expired limit. The deployment container still supplies the
independent cgroup, read-only filesystem, and no-network boundaries.

The isolated Python SDK now exposes bounded `scipy.stats` and `statsmodels.api.OLS`
facades alongside the existing NumPy/Pandas, market, technical-analysis, statistics,
research, and output namespaces. User code still cannot import modules or reach package
internals: only the curated statistical functions and regression result fields are
available. The runner image pins NumPy 2.1.3, Pandas 2.2.3, SciPy 1.14.1, and
statsmodels 0.14.4, constrains BLAS/OpenMP thread fan-out, and was smoke-tested in a
read-only, no-network, non-root container. The application `/code/validate` gate now
accepts the same curated roots and locally composed values as the isolated runner, so
the supported language is consistent across authoring, API validation, and execution.
This is functional sandbox evidence only; the complete security/resource acceptance
matrix and Version 25 visual reference remain open.

The runner file protocol now enforces bounded structured-output bytes, rows, artifact
count, and input-job bytes through deployment-configured limits. It converts malformed
or crashing jobs into terminal failed results, cleans progress/cancellation sentinels,
and recovers claimed `.running` jobs when the worker restarts. Focused tests cover row
and byte rejection, malformed-job recovery, and orphaned-claim recovery. These are
operational sandbox safeguards. The adversarial runner matrix now explicitly covers
dynamic execution/import/namespace calls, filesystem/network/process names, reflection
and object-graph/curated-wrapper introspection, dangerous NumPy attributes, and wall-time
alarm restoration: the combined validator/runner slice is 90 passing tests and the complete
backend unit suite is 955 passing tests. Docker namespace, seccomp, resource-pressure,
crash/orphan, and live image probes remain separate deployment gates.

The branch-scoped live runner was rebuilt with container-level ceilings of 768 MiB,
1 CPU, and 128 PIDs in addition to the per-job limits. Docker inspection confirmed
`uid=10001`, `network=none`, read-only root, dropped capabilities, no-new-privileges,
and the configured ceilings. Direct probes returned read-only-filesystem and
network-unreachable errors. This is deployment evidence for the isolated runner;
the full resource-pressure/crash/orphan matrix remains open.

Study Lab dataset controls are now part of the serializable workstation-window
configuration. Reopening, reloading, or floating a Study Lab preserves timeframe,
benchmark, adjustment, session, and date bounds through the existing workspace
configuration event path; legacy invalid monthly `MN1` state is normalized to `MN`.
Focused component coverage proves hydration and normalization. This is functional
evidence only; the Version 25 visual reference remains unapproved.

Persisted Research Results now renders the same typed scatter and heatmap artifacts as
the active Study Lab surface, using the dedicated uPlot point-cloud and native matrix
components rather than falling back to raw JSON. Saved studies therefore retain their
structured visual form after reload, comparison, or rerun; focused component coverage
proves both render paths.

The primary Study Lab and Persisted Research Results tools now use the shared TanStack
Vue Query client for run retrieval and terminal-aware polling. They stop refetching once
the run reaches `completed`, `failed`, or `canceled`, refetch after explicit cancel/rerun
actions, and suspend requests when the document is hidden or the tool surface is not
intersecting the viewport. This removes their independent interval timers and aligns
research polling with the Market Gauge freshness/coordinator contract. Focused component
coverage passes with the real Vue Query plugin; exact Version 25 visual approval and the
full polling/performance acceptance matrix remain open.

Study Lab, which owns its active run, now cancels that run when the tool is destroyed.
Persisted Research Results remains an observer and never cancels a durable run merely because
its viewer closes; explicit user cancellation remains available in the result detail. Chart-
tool Python plot evaluation follows the owner lifecycle: known plot runs are canceled and
chart/plot generations are invalidated during teardown, preventing late artifacts from
reaching a destroyed uPlot surface. Focused Study Lab teardown coverage passes; full
multi-window and long-running-job performance acceptance remains open.

The reusable uPlot chart host applies the same visibility contract to live latest-bar
refreshes through a reactive Vue Query observer. Its timeframe-aware `refetchInterval`
is disabled when the browser is hidden, the chart root leaves the viewport, or the chart
has not finished initializing; it resumes when visibility/intersection returns. Latest-bar
requests use a shared Vue Query key for canonical symbol, timeframe, and bar type, so
linked charts and pop-outs reuse the same fresh response instead of issuing duplicate
requests. Symbol/timeframe/bar-type changes create a new query key, while the existing
uPlot tail merge and chart teardown remain in place. Focused chart-adjacent regressions,
TypeScript checking, and production build pass. This is lifecycle evidence only; the
complete 100,000-point, multi-window performance and visual acceptance suites remain open.

Virtualized watchlist Python column and Boolean-condition batches now read their
`/research/runs/{id}/batch-results` snapshots through the shared Vue Query client keyed
by immutable run ID. Existing generation guards still discard late symbol/universe
responses, cancellation remains per run, and the cached result path prevents duplicate
reads when the same watchlist is recreated or linked across windows. The focused
10,000-row/Python watchlist suite passes; full polling and performance acceptance remains
open.

The same cancellation contract now covers Python timeframe edits and tool destruction.
Changing a column or condition timeframe invalidates the prior request generation before
starting the replacement run; destroying a docked or floated watchlist cancels every known
active run and invalidates pending generations so late POST/poll responses cannot repopulate
destroyed state. Focused VirtualWatchlistTool coverage exercises universe, timeframe, and
unmount cancellation; full polling, multi-window, and performance acceptance remains open.

EasyScan's queued Python-condition result history now uses the same Vue Query cache
identity (`screener-results:{screener_id}`) while retaining the existing bounded polling,
partial-result safeguards, and isolated-run cancellation. Repeated result refreshes for
the same saved scan therefore share one canonical retained snapshot; the focused EasyScan
suite passes. Full coordinator, hidden-tool, and long-running scan acceptance remains open.

EasyScan teardown now cancels a known queued or running Python research run when its tool
window is destroyed, while leaving completed, failed, and canceled results untouched. This
keeps the isolated worker lifecycle aligned with dock/pop-out recovery and the watchlist
teardown contract. Focused EasyScan coverage exercises both explicit and unmount
cancellation; full coordinator and long-running scan acceptance remains open.

Python chart-plot artifact polling in the workstation now uses the shared research-run
Vue Query key by immutable run ID as well. Obsolete runs are still canceled and sequence
guards discard late series, while repeated chart renders reuse the retained terminal
artifact response instead of issuing a second request. Focused chart/popup coverage and
TypeScript pass; complete multi-window polling/performance acceptance remains open.

The unified Python SDK now supports a typed `output.dashboard` composition contract. A
dashboard contains only bounded references to named scalar, table, series, histogram,
scatter, heatmap, or event artifacts plus title/span metadata; user code cannot provide
HTML, CSS, JavaScript, or components. Active Study Lab and persisted Research Results
render those panels through the shared native dashboard surface, with focused runner,
validator, and frontend coverage. The isolated runner rejects missing or self-referential
panel targets before persisting a completed result, so a dashboard cannot silently render
an unavailable artifact.

The new-workstation provider defaults are free-source-first and provider-neutral:
Alpaca (free IEX entitlement) supplies default US price/latest-price, SEC EDGAR supplies
US identity metadata and ticker-directory search, Alpaca supplies corporate actions and
US universe discovery, and OpenFIGI is the default stable-identifier reconciler. An
optional Massive reference adapter is available for ticker search and US-universe
corroboration when an entitlement is configured; it is not a runtime dependency. The
optional Alpha Vantage adapter supplies quota-limited raw daily history and symbol search
for corroboration; it is also never a required workstation path. The
default chains no longer include yfinance. yfinance remains registered only for explicit
legacy/options configuration and is not a required path for the new workstation; absent
Alpaca credentials are reported as unavailable rather than silently switching providers.

The primary workstation registry now has explicit unit evidence for the capability
boundary: supported chart, watchlist, scan, gauge, Study Lab, breadth, and rotation
tools remain discoverable, while brokerage/trading, options, news, ratings, earnings,
financial statements, and consolidated real-time domains are absent rather than shown
as disabled shells. This verifies menu registration only; legacy-route and full browser
acceptance remain separate gates.

The application route contract now has focused unit evidence for the shell boundary:
`/` and `/chart` (including `/chart/:symbol`) resolve to the authenticated workstation,
while the retained dashboard, chart, alerts, Radar, Strategy Lab, Baskets, ETF Holdings,
Screener, Watchlist, and Settings views are registered only beneath `/legacy/*`.
Pre-workstation top-level paths redirect into their corresponding legacy route. This
proves route registration and redirect intent without claiming full browser-authenticated
legacy usability or visual parity; those remain separate acceptance gates.

The `/study-lab` deep link now redirects into the workstation's persisted `study-lab`
factory tab instead of mounting a second standalone shell. The primary Study Lab tool
therefore owns symbol, link-group, dataset, layout, and pop-out state consistently with
all other workstation tools; its existing focused rendering and run tests remain the
functional evidence, while visual approval is still pending.

Instrument notes now have Docker-backed integration coverage for authenticated
round-tripping, canonical-instrument validation, unauthenticated rejection, and strict
per-user isolation. The API already scopes both read and upsert queries by user ID; the
tests prove one user cannot read or overwrite another user's note for the same instrument.
Linked-tool stale-load/save protections remain covered separately in the frontend race
suite. Full legacy browser usability and Version 25 visual acceptance remain open.

The primary workstation now exposes the persisted personal-layout lifecycle directly in
the TC-style Workspace menu: select, rename, clone, drag-reorder, delete (with the last
layout protected), reset the factory layout, and JSON export/import. Import accepts only
serializable layout snapshots with non-empty, unique layout IDs and preserves the
existing revision-checked backend snapshot path; malformed or duplicate layouts remain
in place with an explicit error. The focused workspace-store suite covers normalization,
reordering, deletion protection, export/import, and persistence scheduling. Visual
comparison, browser drag/drop evidence, and the broader acceptance matrix remain open.

An active unified-Python Boolean condition in a watchlist can now be promoted directly to
a repeatable EasyScan entry/exit alert. The workstation creates the canonical Python-backed
screener, then the user-scoped screener alert through the existing alert lifecycle, while
retaining explicit success/failure status and the condition timeframe. Focused
VirtualWatchlist coverage proves the screener and alert requests and the resulting status;
full authenticated browser and provider/runtime acceptance remain open.

Watchlist column customization now has an explicit internal clipboard contract. Column
settings (label, width, formatting, grouping, stack, and Boolean pin state) can be copied
from the integrated editor and pasted into the same canonical column on another linked or
restored watchlist; system clipboard failure falls back to an in-memory session copy, and
unknown/missing source columns are reported instead of creating a blank column. Focused
virtual-watchlist coverage proves the copy/paste round trip; full browser and visual
acceptance remain open.

Top-down benchmark, sector, constituent, and verified-proxy watchlists now expose
response-level `Coverage`, `Freshness`, and `Provenance` columns alongside the technical
ranking fields. They are populated from the canonical analysis metadata rather than a
provider-specific frontend assumption, and remain visible as explicit unavailable values
when a batch is not ready. The frontend contract accepts membership/version lineage for
future detail panes; visual density and full backend/E2E acceptance remain open.

The explicit E2E seed can now provision identity-only SPY/RSP, major benchmarks, and all
11 sector ETFs with unresolved ETF profiles. It deliberately does not create OHLCV bars,
holdings, or provider entitlements, so browser fixtures exercise the same labelled
unavailable/coverage states as a cold free-source-first deployment rather than masking
missing data with fabricated values.

Provider documentation is now aligned with the runtime entitlement policy: the default
free-source-first chain is Alpaca/Alpha Vantage for permitted history, EDGAR/Alpaca for
identity and events, and Massive/Alpha Vantage only for optional corroboration. yfinance
is documented as an explicit legacy/options fallback only, and excluded options, analyst,
earnings-estimate, and futures domains are capability stubs rather than new-workstation
fallbacks. This is documentation/contract evidence, not live-provider probe evidence.
The backend reference environment now matches those defaults as well: its ordinary
price-history, latest-price, discovery, event, metadata, and instrument-search seeds
exclude yfinance; yfinance remains listed only for explicit option/legacy slots. A fresh
environment therefore cannot accidentally restore the unofficial provider to the new
workstation's normal path by copying `backend/.env.example`.
Study Lab now ships editable factory starters for the core open-ended research patterns
required by the workstation scope: positive and negative close streaks (including
occurrence events, completed-length tables, histograms, and forward outcomes), moving-
average participation, forward-return distributions, configurable-20-session high/low
breakouts, realised-volatility regimes, monthly seasonality, relative-strength regime
crossings, declared-universe cross-sectional ranking, declared-universe breadth
participation, and the existing raw relative-strength history study. Every starter is ordinary
unified Python source using only the declared `market`, `ta`, `stats`, `research`, and
`output` SDK surfaces; editing the source returns the selector to Custom Python. All ten
new/retained sources pass the isolated runner's static validator and deterministic sample
execution, including the new declared-universe `research.cross_sectional_rank` and
`research.breadth_snapshot` helpers; the Study Lab component suite now covers the factory
catalogue (`8` tests) and the runner has direct aggregate-rank/breadth assertions.
This adds functional authoring coverage; exact Version 25 visual approval, aggregate
cross-sectional breadth studies, live-provider probes, and the broader acceptance matrix
remain open.

Study Lab Boolean and event results can also be promoted directly into a reusable Strategy Lab
signal asset through the same immutable Python code-version path used by columns, plots,
EasyScan conditions, and alerts. Event signals retain their structured `events` output
contract; they are not coerced into a Boolean condition. Aggregate ranking/breadth starters explicitly require a
declared comma-separated universe and show a visible warning rather than silently falling
back to the active symbol; the run guard prevents an invalid single-symbol request. Focused
Study Lab coverage now includes this promotion and missing-universe recovery path (`9`
tests), with TypeScript and production build passing.

Promotion now also creates a user-owned Strategy Lab definition through
`POST /api/v1/strategy-lab/signals/from-code/{code_version_id}`. Its version snapshot and
metadata retain the immutable signal code-version id and output contract instead of
copying source text, so the Strategy Lab library can discover the promoted signal and
revisions remain reproducible. The endpoint rejects archived, cross-user, non-signal, and
non-Boolean/event code versions. The isolated runner now evaluates declared event signals
across prepared-universe cells and returns bounded, symbol-qualified event artifacts. The
existing Strategy Lab engine remains authoritative for which execution modes are supported;
signal persistence and Study Lab event evaluation are complete for this contract, while
Strategy Lab Python-signal runs now queue through the same canonical dataset materializer
and isolated runner, expose queued/terminal research status, and reconcile bounded event or
Boolean artifacts through run retrieval/refresh. This is research/signal evaluation rather
than brokerage execution or a claim of trade-fill simulation; the existing Nautilus/rules
engine remains authoritative for execution statistics and portfolio replay.

The shared primary-facing provenance hint now reports canonical source, observation/fetch
times, selection reason, quality, and notes without exposing provider-specific symbol
aliases. This keeps the workstation's provenance contract provider-neutral while the
legacy options models retain their isolated provider fields for legacy-only routes.

The Sector by Year factory watchlist now exposes the same `Coverage`, `Freshness`, and
`Provenance` columns as the live sector ranking view, so calendar-year cells do not become
a lineage-free exception when the factory layout changes.

Industry drill-down rows now retain ETF-holdings classification lineage as well: resolved
coverage ratio, holdings composition date, and source/provenance are visible beside proxy
counts. Missing classification or proxy data remains explicitly unavailable rather than
being inferred from an industry name.

Study Lab dataset controls now include an explicit `As of` timestamp. The backend clamps
canonical bar materialization to that cutoff, rejects a cutoff before the requested start,
and retains the normalized cutoff in the dataset manifest. This prevents future bars from
entering historical studies and gives reruns a visible point-in-time boundary.
Sandbox hardening: the isolated NumPy facade can still return array-like values for
normal numerical composition, but the shared source validator now rejects dangerous
array attributes such as `tofile`, `dump`, `setflags`, `resize`, and `ctypes` regardless
of the local variable name used to reach them. Focused runner coverage exercises file
writes, raw-memory exposure, and mutation attempts; this closes a concrete gap between
the declared no-filesystem/no-host-access contract and the raw ndarray methods exposed
by NumPy. Docker-level network, namespace, seccomp, and resource-limit acceptance
remains a separate deployment gate.

The renderer acceptance suite now includes a real Chromium uPlot benchmark at
`frontend/tests/e2e/uplot_performance.spec.ts`. It loads the packaged uPlot build,
renders 100,000 points, performs forty viewport zoom/pan updates, verifies the chart
element is preserved, and enforces a bounded interaction time. The test passed in the
host-permitted Chromium run on 2026-08-04; this is renderer-level evidence only and
does not replace the pending authenticated workstation, pop-out, memory, and
multi-environment performance matrix.
