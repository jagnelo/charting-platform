# TC2000 Version 25 Visual-Parity Specification

Status: `Controlling implementation plan`

Current audit state (2026-08-07): all four seeded workstation environments pass the
independent geometry, viewport-containment, and core-overlap checks. Screenshot comparison
remains intentionally blocked by `application-shell-default/default: required_missing`; the
available online/help and shared-layout media are discovery evidence only until pinned-build
and permission metadata are approved. No stale local screenshot is promoted as a baseline.

Reference release: `TC2000 Version 25.0.9571`

Reference date: `2026-08-03`

## Authority and precedence

This document is the visual and interaction authority for the
`feat/tc2000-frontend-rework` branch.

It is subordinate only to the complete product contract in
`docs/project-todos.md`, section 14. Together, those two documents supersede every
older repository note that refers to TC2000 Version 20, treats visual research as an
open question, or describes a less complete frontend-only reskin.

The target is a pixel-close, behavior-close reproduction of the current TC2000
Version 25 desktop workstation for the features supported by this platform. The
result must use this platform's name, copy, icons, and original assets. TC2000
trademarks, logos, screenshots, and proprietary artwork are reference material only
and must not be shipped as product assets.

The pinned build prevents the target from changing during implementation. A newer
TC2000 build does not silently replace it. Refreshing the reference requires:

1. an explicit plan/documentation update;
2. a new reference-pack version;
3. a reviewed list of changed surfaces and mechanics;
4. regenerated and approved visual baselines.

## Version authority

The release authority is the official TC2000 release-notes page:

- Current release notes:
  <https://www.tc2000.com/features/whatsnew>
- Product download/version page:
  <https://www.tc2000.com/download/version>

As verified on `2026-08-03`, the release notes identify Version `25.0.9571` as the
April 2026 release and state that Version 25 became current for all customers in
October 2025. The generic download page still renders Version 24 copy, while the
help index exposes an earlier Version 25 help build (`25.0.9172.22877`). Where those
pages disagree, the dated release notes and an authorised live desktop capture take
precedence over generic marketing-page text.

The reference generation is therefore:

- product generation: TC2000 Version 25;
- pinned desktop build: `25.0.9571`;
- supported reference platform: desktop application;
- excluded reference surfaces: brokerage, trading, options, news, analyst ratings,
  earnings, full financial statements, and any other capability excluded by section 14.

## Evidence hierarchy

Resolve visual or behavioral ambiguity in this order:

1. **Authorised live Version 25 desktop capture at the pinned build.** This is the
   primary source for exact geometry, fonts, colors, spacing, icons, states, overlay
   order, and interaction timing. "Live capture" identifies evidence of the actual
   desktop application; it does not require the implementation machine to have made
   the capture. A permission-cleared, provenance-verifiable online or controlled-
   storage capture is equally eligible when the manifest proves its build and state.
2. **Official help material explicitly tagged Version 25.** Use it for controls or
   states that cannot be reproduced in the live capture environment.
3. **Official Version 23 or Version 24 help material.** Use it only after a live
   Version 25 capture confirms that the surface is materially unchanged.
4. **Official Version 20 help or release material.** Use it only as behavioral history
   where newer sources do not explain a still-present mechanic.
5. **Third-party screenshots or videos.** Use them only to discover a state that must
   then be confirmed using an authoritative source. They never decide dimensions,
   colors, or acceptance.

Written descriptions do not overrule visible live behavior. If sources conflict,
record the conflict in the reference manifest and obtain an approved authoritative
Version 25 reference before accepting the affected surface.

Online acquisition is an approved reference path. An online or controlled-storage
reference can be approved when its source is authoritative, its Version 25 build and
required state are verifiable, its unmodified source hash and capture environment are
recorded, its permission/storage classification is known, and a reviewer approves it.
Official Version 25 material can therefore supply a baseline without a local capture.
Third-party material remains discovery-only unless those same facts are independently
verified and recorded; it must never be silently promoted to an acceptance baseline.

The manifest may also record explicit `discovery_candidates` while evidence is being
reconciled. Candidates carry their source page, direct image locator, source build,
image hash, resolution, eligibility, and status. A candidate is not a baseline: it
cannot satisfy `--require-approved`, and older-generation history is explicitly
labelled discovery-only until a pinned-build review confirms the surface is unchanged.

## Official behavior and visual-source catalogue

These links are the initial authoritative catalogue. Each entry must be represented
in the capture manifest by an owned capture, a reviewed official image, or a recorded
reason that it is out of scope.

### Shell, layouts, linking, and window mechanics

- Symbol linking:
  <https://help.tc2000.com/m/69401/l/312314-how-symbol-linking-works>
- Timeframe linking:
  <https://help.tc2000.com/m/69401/l/327472-how-timeframe-linking-works>
- Tabbed tool windows:
  <https://help.tc2000.com/m/69401/l/1701300-how-to-tab-tool-windows>
- Floating tool windows:
  <https://help.tc2000.com/m/69401/l/324100-how-to-float-tool-windows>
- Factory default workspace and Drill Down / Sector by Year / 1-Chart / 4-Timeframe
  behavior:
  <https://help.tc2000.com/m/69401/l/743982-factory-default-layout-workspace>
- Workspace save/restore:
  <https://help.tc2000.com/m/69401/l/793640-how-to-save-a-workspace>
- Create layout tab:
  <https://help.tc2000.com/m/69401/l/323126-how-to-create-a-new-layout-tab>
- Drag/drop a value column to a chart (official historical interaction reference):
  <https://help.tc2000.com/m/125751/l/1874609-how-to-drag-drop-a-value-column-to-a-chart>

The captures must establish:

- top menu, workspace tab strip, active workspace state, and status areas;
- active, inactive, hovered, pressed, dragged, maximized, floating, and blocked-pop-out
  tool-window states;
- window title bar, link selector, tool menu, drag area, tab stack, maximize, float,
  pop-in, close, resize borders, and minimum-size behavior;
- all eight normal symbol-link groups plus yellow wildcard and grey isolation behavior;
- timeframe-link selector and linked/unlinked states;
- between-layout and multi-monitor propagation;
- drag preview, drop target, tab insertion, row/column split, and invalid-drop feedback.

The drag/drop article's linked images are recorded in the manifest with their direct
online locators, SHA-256 hashes, pixel dimensions, and Version 23 discovery-only status.
They inform interaction discovery but cannot become V25 visual baselines unless an
authorised pinned-build review confirms the surface is unchanged.

The manifest also records official discovery candidates for the integrated column editor,
column-group selection, and stacked-column drag/drop states. Their direct image locators
were recovered from the help articles, but they intentionally remain non-approved because
the pages do not prove exact build `25.0.9571`, complete capture environment, permissions,
measurements, or human review.

Two additional official shared-layout previews are retrieved by
`tests/visual/fetch-tc2000-v25-reference-pack.sh` into controlled storage and recorded as
`official_shared_layout` discovery candidates: the [Bulls on Wallstreet layout](https://www.tc2000.com/share/affiliate/bulls/layout/7fe75a78-4faa-4f1d-8088-b4f4ff94b954)
and the [Emmanuel layout](https://www.tc2000.com/share/el3470/layout/18fbc0d1-daa4-4260-8167-111a275d6dc1).
Their previews are useful high-resolution evidence for dense shell geometry, chart/watchlist
composition, tab chrome, symbol/timeframe controls, and multi-window arrangements. The
pages expose no pinned desktop build or capture environment, so both remain discovery-only
and cannot satisfy exact-build visual approval.

### Watchlists, columns, filters, and market gauges

- Column editor:
  <https://help.tc2000.com/m/125751/l/1874588-how-to-use-the-column-editor>
- Column grouping:
  <https://help.tc2000.com/m/125751/l/1874601-how-to-group-columns>
- Stacking columns:
  <https://help.tc2000.com/m/125751/l/1874595-how-to-stack-columns-in-a-watchlist>
- Add/remove columns:
  <https://help.tc2000.com/m/125751/l/1874629-how-to-add-or-remove-a-column-in-the-watchlist-window>
- Rearrange/group/stack columns:
  <https://help.tc2000.com/m/69401/l/1678518-how-to-change-the-order-of-columns-in-a-watchlist>
- Condition/filter editor:
  <https://help.tc2000.com/m/125751/l/1659573-how-to-create-filters-with-the-new-condition-editor>
- Market Gauge:
  <https://help.tc2000.com/m/125751/l/1874582-how-to-understand-a-market-gauge>
- Related items:
  <https://help.tc2000.com/m/69401/l/316383-how-to-open-the-related-items-watchlist>
- Sector and industry filtering:
  <https://help.tc2000.com/m/69401/l/861712-how-to-filter-sector-and-industry-watchlists>

The captures must establish:

- watchlist chrome, list selector, count/status text, Edit control, scrollbars, frozen
  identity area, data rows, headers, sort indicators, filter markers, and empty/loading/
  stale/error states;
- default row height, header height, column padding, grid lines, numeric alignment,
  positive/negative/neutral colors, selection, keyboard focus, hover, multi-select,
  drag source, and drop feedback;
- column-editor tree/list structure, visibility controls, column stacks and groups,
  per-column timeframe, active/inactive/off filter states, add/edit/delete menus, and
  saved column-set controls;
- condition-editor nesting, operand menus, timeframe controls, validation, match preview,
  active/inactive/off states, and cancel/confirm behavior;
- Boolean/tag pinning, primary and secondary sort, manual ordering, horizontal scroll,
  and narrow-column behavior;
- Market Gauge label, value, bar/scale, thresholds, positive/negative/neutral states,
  tooltip, edit state, and placement inside a dense layout.

The Version 25 watchlist model is the controlling product model: columns, True/False
conditions, filters, groups, stacks, and Market Gauges are integrated. Do not recreate
an obsolete standalone Version 20 EasyScan visual model when current behavior is
available. “EasyScan” remains the platform feature name for saved/reusable scanning,
while its primary editing mechanics follow the current Version 25 column/filter model.

### Charts and chart controls

- Chart toolbar:
  <https://help.tc2000.com/m/69401/l/325473-how-to-edit-the-chart-toolbar>
- Scaling menu:
  <https://help.tc2000.com/m/69401/l/1236908-how-to-use-the-scaling-menu>
- Event markers:
  <https://help.tc2000.com/m/125751/l/1909214-managing-event-markers>

The captures must establish:

- chart title/symbol header, quote/freshness labeling, toolbar controls, timeframe and
  timespan selectors, drawing controls, scale controls, plot labels, legends, axes,
  pane separators, grid, crosshair, value readouts, projection space, and scroll/zoom
  feedback;
- light and dark chart themes if Version 25 exposes both, while the factory workstation
  follows the measured primary reference theme;
- candlestick, line, comparison, ratio, overlay, sub-pane, alert-line, drawing-selected,
  drawing-edit, event-marker, no-data, partial-data, delayed-data, and background-fetch
  states;
- plot context menu, plot editor, move/duplicate/hide/delete controls, drag-to-window
  target mode, pane resize, scale lock, log/linear state, and chart-template menus;
- crosshair propagation across linked charts and the visible state when timestamps do
  not align.

uPlot remains the sole chart renderer. Visual parity is judged on the resulting pixels
and mechanics, not on whether TC2000's internal rendering technology is reproduced.

### Notes and supported symbol information

- Notes controls:
  <https://help.tc2000.com/m/125751/l/1874628-how-to-use-the-redesigned-news-or-notes-window-controls>

The captures must establish the notes-window title, symbol/link state, toolbar,
autosave/modified feedback, editor density, empty state, note marker, tooltip/preview,
and the relationship between a note marker and its linked chart. News-specific controls
remain excluded and must not appear as disabled placeholders.

## Reference pack

Implementation must create:

- `tests/visual/references/tc2000-v25/manifest.yaml`;
- reference images stored outside distributable application bundles;
- `tests/visual/baselines/` for this platform's deterministic screenshots;
- a visual-test helper that validates manifest completeness before comparisons run.

The repository may contain authorised reference captures only when their storage and
use are permitted. Otherwise, the manifest stores a stable controlled-storage
identifier or source URL, hashes, measurements, and capture instructions while the
protected reference pack remains outside the distributable source tree. No visual test
may silently fall back to an absent or older-generation image.

Each manifest entry must record:

- stable reference ID and semantic surface/state;
- product generation, exact build, capture date, and capture operator;
- source kind: authorised desktop capture, official Version 25 image/help, or
  behavior-only help; an authorised capture may be online or in controlled storage;
- source URL or controlled capture identifier;
- operating system, display resolution, display scale, browser/app zoom, and theme;
- full-window bounds and crop bounds;
- expected dynamic regions and any approved masks;
- related token measurements;
- interaction/capture recipe;
- SHA-256 of the unmodified source image;
- review status, reviewer, notes, and superseded reference ID where applicable;
- permission/storage classification so protected material cannot enter a product bundle.

The repository manifest also records a `state_entries` list for every item in
`required_states`. Each state entry has its own stable ID, lifecycle status, and review
status; a surface-level `approved` flag cannot conceal an unmeasured or missing state.

Manifest status is one of:

- `required_missing`;
- `captured_unmeasured`;
- `measured_unapproved`;
- `approved`;
- `superseded`;
- `out_of_scope`.

Implementation of a surface may begin from `captured_unmeasured`, but it cannot satisfy
visual acceptance until every required state is `approved`.

## Deterministic capture environments

Capture and test these four primary desktop environments:

| Viewport | Display scale | Browser/app zoom | Purpose |
| --- | ---: | ---: | --- |
| 1920 x 1080 | 100% | 100% | Primary parity target |
| 1920 x 1080 | 125% | 100% | Common scaled desktop |
| 2560 x 1440 | 100% | 100% | Dense multi-tool workspace |
| 2560 x 1440 | 125% | 100% | High-density scaled desktop |

Browser zoom remains at 100% for reference capture. The implementation also receives a
separate robustness check at 125% browser zoom, but those images do not replace the
display-scale references.

For each environment:

- use the same platform font stack and font-smoothing settings;
- disable operating-system animation and non-deterministic cursor effects;
- pin locale, timezone, number/date format, color profile, and device pixel ratio;
- use deterministic seeded market fixtures and a fixed clock;
- wait for fonts, layout stabilization, canvas drawing, and data-idle markers;
- capture full viewports and named component crops;
- record any OS-owned chrome that is intentionally excluded from comparison.

## Required capture matrix

### Application shell and layouts

- application launch/default US Top Down workspace;
- menu closed and representative first/second-level menus open;
- workspace tab inactive, active, hover, rename, drag, overflow, and context-menu states;
- global symbol search empty, typing, result, keyboard-selection, no-result, and error;
- status area for current, delayed, stale, partial, fetching, and unavailable data;
- TC Classic, Drill Down, Sector by Year, 1 Chart, 4 Timeframe, Fundamentals, and
  Study Lab factory layouts;
- workspace create, clone, rename, reorder, import, export, delete, reset, unsaved,
  revision-conflict, and recovery-copy dialogs.

### Docking and tool windows

- active/inactive tool chrome;
- normal docked, tabbed, maximized, floating, restored, minimum-size, and overflow;
- horizontal/vertical split targets, tab insertion target, invalid target, and drag ghost;
- pop-out blocked, pop-out disconnected, leader transfer, and recovery;
- every symbol-link color, yellow wildcard, grey isolation, and timeframe-link state.

### Charts

- default price chart and every supported chart type;
- multi-pane indicators, pane resize, overlay, comparison, normalized comparison, and
  ratio expressions;
- toolbar and scaling menus;
- plot editor, chart settings, template manager, indicator library, and target mode;
- drawing create/select/edit/lock/delete and alert-line states;
- crosshair, linked crosshair, missing aligned timestamp, zoom/pan, latest bar,
  infinite-history fetch, and projection space;
- split/dividend markers, note markers, alert markers, marker tooltip, and marker menu;
- no data, insufficient history, delayed, stale, partial, provider error, and cached data.

### Watchlists, columns, filters, and scans

- personal, managed, market-group, ETF proxy, sector, industry, related-item, combo,
  empty, loading, partial, stale, and unavailable lists;
- default row, hover, selected, focused, multi-selected, drag, drop, manual-order, sorted,
  filtered, pinned, and validation-error states;
- column insert, edit, duplicate, rename, resize, reorder, stack, group, hide, remove,
  timeframe, formatting, and saved-set states;
- active, inactive, and off True/False filters;
- nested condition editor with valid, incomplete, and invalid conditions;
- scan progress, cancellation, results, historical-result limitation, and managed list;
- Market Gauge positive, negative, neutral, partial, empty, and edit states.

### Alerts, notes, and Study Lab

- alert creation from price, plot, condition, scan entry/exit, and Python;
- active, paused, fired, rearmed, error, history, and notification configuration;
- notes empty, editing, autosaved, error, marker, preview, and linked symbol change;
- Study Lab editor, parameters, preflight, queued/running/cancelling/succeeded/failed,
  logs, coverage warning, look-ahead warning, and reproducibility metadata;
- metric, series, range, bar, histogram, scatter, heatmap, event set, table, dashboard,
  current-versus-history, occurrence detail, compare versions, and export states.

## Measurement and token extraction

Do not eyeball reusable geometry. Measure the approved references and encode the result
as centralized design tokens.

Measure at minimum:

- application menu, workspace strip, status bar, tool title, chart toolbar, table header,
  row, tab, button, input, menu item, and dialog-title heights;
- outer shell, tool, pane, grid, menu, input, dialog, focus, and selection borders;
- horizontal/vertical padding, gaps, indent levels, icon boxes, resize handles, splitter
  thickness, scrollbar track/thumb, and overlay offsets;
- font family, fallback stack, size, line height, weight, letter spacing, number
  alignment, truncation, and anti-aliasing assumptions;
- all solid fills, gradients, borders, text colors, link colors, chart/grid colors,
  positive/negative/neutral colors, focus/selection colors, disabled states, and
  translucent overlays;
- corner radii, shadows, blur, opacity, z-index, menu overlap, tooltip placement, and
  drag/drop overlays;
- hover, focus-visible, keyboard focus, pressed, active, selected, disabled, loading,
  warning, error, delayed, stale, and unavailable states.

Every token must carry:

- semantic name rather than a screenshot coordinate;
- CSS value at the primary environment;
- scaling rule where the value changes at 125% display scale;
- reference IDs and measured sample points;
- permitted variance;
- review status.

One-off adjustments are allowed only when the reference proves the element is genuinely
different. Do not compensate for a wrong global token with per-component pixel nudges.

## Implementation workflow

For each surface:

1. reproduce every required Version 25 state and capture it;
2. add the source evidence and measurement records to the manifest;
3. derive or confirm reusable design tokens;
4. implement semantic HTML/Vue structure and original CSS/SVG assets;
5. add stable visual-test fixtures and deterministic data;
6. capture this platform at every required environment;
7. compare geometry first, then typography, color, iconography, and transient states;
8. correct the implementation or explicitly document a justified product divergence;
9. obtain visual approval before marking the surface complete.

Behavioral parity is validated alongside screenshots. A static image is insufficient
for drag/drop, linking, keyboard traversal, pop-outs, menus, editors, chart interaction,
or error/recovery behavior.

## Pixel-diff policy

Visual acceptance uses component crops and full-layout screenshots.

- No unexplained geometry difference may exceed `1 CSS pixel`.
- Tokenized dimensions must match their approved values exactly at the primary target.
- Declared font family, size, line height, and weight must match exactly.
- Solid-color comparisons must have CIEDE2000 `Delta E <= 2`.
- The unmasked differing-pixel ratio must be `<= 0.5%` per approved screenshot.
- Anti-aliasing tolerance may cover edge pixels only; it must not hide shifted geometry,
  wrong type metrics, incorrect borders, or missing controls.
- Dynamic data, clocks, cursor position, and OS-owned chrome must be deterministic when
  possible. Otherwise use the smallest named rectangular mask around that field.
- Each mask requires a reason and manifest owner. Broad masks over tool content, charts,
  menus, dialogs, or table structure are prohibited.
- Do not raise a global threshold to accept one mismatch.
- Every changed baseline requires human review and a note linking it to an intentional
  plan or reference change.

A screenshot passing the numeric threshold can still fail review when it contains a
visually material mismatch. A screenshot exceeding the threshold cannot be approved
solely by prose.

## Accessibility and platform constraints

Pixel parity does not justify removing semantic or keyboard behavior. Preserve:

- keyboard reachability and visible focus;
- correct menu/dialog focus trapping and restoration;
- accessible names and roles;
- screen-reader status for loading, delayed, stale, partial, unavailable, validation,
  and execution states;
- reduced-motion behavior;
- usable contrast.

If the Version 25 reference conflicts with a non-negotiable accessibility requirement,
retain the closest appearance compatible with the requirement and record the divergence
in the manifest and parity matrix.

## Visual completion gate

Visual work is complete only when:

- every in-scope capture-matrix entry has an approved source reference;
- all required design tokens are measured and reviewed;
- the implementation has approved baselines for all four primary environments;
- interaction tests cover the mechanics represented by the images;
- component and full-layout comparisons meet the pixel-diff policy;
- no unexplained mismatch, temporary icon, dead control, broad mask, or reference from
  an obsolete TC2000 generation remains;
- `docs/tc2000-parity.md` maps every reviewed surface to implementation evidence,
  behavioral tests, visual baselines, supported/partial/excluded status, and any
  justified divergence;
- protected reference material is absent from product bundles and distributable assets.
