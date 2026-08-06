# TC2000 Version 25 composite reference board

The retrieved reference pack is now composed into a single browsable visual board so
implementation decisions are made against a coherent product vision rather than isolated
screenshots.

## Build and review

The controlled pack is stored at `/private/tmp/tc2000-v25-reference-pack` and contains 190
retrieved images. Generate the board with:

```bash
python3 tests/visual/build-tc2000-reference-board.py \
  /private/tmp/tc2000-v25-reference-pack \
  /private/tmp/tc2000-v25-reference-pack/reference-board.html

npx playwright screenshot --device='Desktop Chrome HiDPI' --full-page \
  file:///private/tmp/tc2000-v25-reference-pack/reference-board.html \
  /private/tmp/tc2000-v25-reference-pack/reference-board.png
```

The board groups every image by surface and labels it with source type, source build,
filename, and source-page link. It is an implementation and review aid; it does not merge
different product states into a claim that they are one deterministic screenshot.

## Current coverage

| Surface group | References | What it contributes |
|---|---:|---|
| Factory/default layouts | 47 | Dense workspace composition, layout tabs, chart/watchlist proportions |
| Data grids and columns | 24 | Column editor, grouping, stacking, creation, use, appearance |
| Market gauges | 24 | Gauge creation, readings, condition-driven visuals |
| Charts and comparisons | 35 | Timeframes, comparisons, projections, markers, past performance |
| Windows and layout mechanics | 10 | Floating windows, tab repositioning, drag/drop composition |
| Notes and value-column workflows | 8 | Notes window and chart/watchlist transfer mechanics |
| Version 25 product/shared-layout evidence | 3 | Current product-level shell and shared-layout composition |

The grouped board exposes the intended visual language: dense dark chrome, compact title and
link controls, thin separators, small typography, data-grid-first workflows, chart panes with
minimal decoration, and frequent drag/drop transfer between tools.

## Gaps identified from the board

These are now explicit implementation/acceptance gaps rather than an undifferentiated
“visual references unavailable” state. Each gap has an interim oracle so development can
continue without disguising the absence of authoritative Version 25 evidence.

| Gap ID | Missing reference and affected acceptance cases | Current implementation treatment | Interim test/oracle | Evidence required to close the gap |
|---|---|---|---|---|
| `REF-SHELL-V25` | Pinned-build shell at `25.0.9571`; application shell, menus, workspace tabs, search, status areas, and factory-layout geometry | Use the board’s factory-layout/product-image groups for density, proportions, chrome, and token direction; keep strict manifest state `required_missing` | Four seeded environment geometry/containment audits, deterministic screenshot harness, and browser shell interaction tests | Permission-cleared capture of the exact build with environment metadata, measurements, SHA-256, and reviewer approval |
| `REF-STATE-VARIANTS` | Loading, stale, partial, provider-error, blocked-pop-out, recovery, focused, keyboard-selected, and disabled states | Implement explicit freshness/error/recovery states from platform contracts; do not infer their exact V25 styling from unrelated screenshots | Browser tests for stale/partial/error/recovery flows, accessibility/focus assertions, and structured cell warnings | Complete state capture set from the pinned build at a reviewed target environment |
| `REF-LINKING-V25` | All normal link groups, yellow wildcard, grey isolation, timeframe propagation, linked crosshair, and cross-window propagation | Preserve canonical-ID link bus and test behavioral semantics independently of missing visual proof | Link-group, keyboard, cross-window, and chart crosshair integration tests | Authoritative captures covering every link state and interaction, with timing and environment metadata |
| `REF-STUDY-LAB-V25` | Open-ended research editor, structured renderers, occurrence browser, sandbox-error and promotion surfaces | Use the board’s dense editor/grid language for composition; use product contracts and existing browser tests for behavior | Study Lab validation, run, cancellation, recovery, structured-output, occurrence-link, and promotion tests | Pinned-build Study Lab captures or authoritative V25 documentation with reviewed visual states |
| `REF-ENV-TOKENS` | Deterministic 1920×1080 and 2560×1440 captures at 100% and 125% display scale, with measured tokens | Maintain four seeded visual environments and tokenized geometry checks; keep screenshot comparison failures visible | Geometry/viewport containment, token assertions, and unmasked screenshot diff reporting | Captures and measurements for all four required environments, approved against the manifest |
| `REF-PERMISSION-REVIEW` | Permission classification and human review needed to promote online media to a baseline | Keep retrieved media in controlled storage as implementation aid only; do not promote any board entry to `approved` | Manifest schema/unit tests require source, hash, state, and review fields | Permission decision, reviewer identity/date, storage classification, and approved manifest entry |

The board is used immediately for implementation review and gap-directed browser checks. The
strict manifest remains authoritative for screenshot acceptance; no board image is promoted to
`approved` merely because it visually complements another image.
