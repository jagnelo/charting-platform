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
“visual references unavailable” state:

1. **Pinned-build shell baseline:** no source image proves the complete application shell at
   build `25.0.9571` with capture environment, permissions, and review metadata.
2. **State variants:** the pack does not fully cover loading, stale, partial, provider-error,
   blocked-pop-out, recovery, focused, keyboard-selected, and disabled states at one target
   environment.
3. **Linking:** help material explains linking, but a complete V25 capture set for all normal
   groups, yellow wildcard, grey isolation, and timeframe propagation is absent.
4. **Study Lab:** the retrieved product media does not establish the modern open-ended research
   editor, structured result renderers, occurrence browser, or sandbox-error presentation.
5. **Acceptance environments:** none of the retrieved media provides deterministic 1920×1080
   and 2560×1440 captures at both display scales with measured tokens.
6. **Permission/review evidence:** online media has source URLs and hashes but not the required
   permission classification and human approval for use as a baseline.

The board is used immediately for implementation review and gap-directed browser checks. The
strict manifest remains authoritative for screenshot acceptance; no board image is promoted to
`approved` merely because it visually complements another image.
