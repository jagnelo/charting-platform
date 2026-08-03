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

Historical chart pagination now uses a bounded, timeframe-aware repair window when the
local page is short. It anchors the request at the oldest cached bar (or a minimum cold
bootstrap window) with a small overlap, rather than fetching from the 1970 epoch; pure
service tests cover both warm-tail and cold-start calculations.

Explicit historical range reads now also detect bounded edge gaps and only obvious
internal gaps. Those slices are fetched independently instead of refetching the full
requested range; daily weekend-sized gaps are deliberately left alone because the local
bar store does not yet carry an exchange-calendar guarantee. Focused service tests cover
internal repair and the no-fetch historical-weekend case.

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
rotation plane now draws zero-axis quadrant guides, identifies the nearest tail point on
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
unexecuted because Docker socket access is unavailable.

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
operational sandbox safeguards; the complete adversarial security and resource matrix
remains open.

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
