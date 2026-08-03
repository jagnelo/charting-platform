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
focused runner, validation, Study Lab, and persisted-results tests pass; visual parity
remains blocked until the required approved Version 25 references exist.

The isolated image also installs pinned NumPy/Pandas wheels at build time and exposes
only restricted `np`/`pd` facades to user code. File/external-data methods are rejected
by source validation; NumPy/Pandas values are normalized before artifact persistence.
The rebuilt image import check reports NumPy `2.1.3` and Pandas `2.2.3`.

The relative-rotation uPlot surface now updates `setData`/`setSize` in place during
resize and data refresh; it destroys the chart only during component teardown. A
dedicated regression test proves repeated resize callbacks do not create additional
uPlot instances.

Relative Rotation now exposes and persists its transparent inputs: market-group universe,
benchmark, timeframe, split-adjustment mode, lookback, and tail length. Those values are
sent to the canonical analysis endpoint rather than being hidden SPY/D1/20/10 constants;
load generations prevent a late rotation response from replacing a newer selection.

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
historical drill-downs and leaves the current-view request shape unchanged when absent.
The focused frontend contract and backend helper suites pass; the Docker-backed route
regression remains recorded but unexecuted because Docker socket access is unavailable.

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
