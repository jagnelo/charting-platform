# TC2000 Version 25 Reference Sources

This is the source catalogue for the internal visual and interaction reference
pack. It complements `tests/visual/references/tc2000-v25/manifest.yaml` and the
strict parity rules in `docs/tc2000-visual-parity.md`.

## Retrieved pack

On 2026-08-04, the retrieval script obtained 83 publicly reachable screenshots
from the official TC2000 Help Site into a controlled directory outside the
repository. The current pack is at:

`/private/tmp/tc2000-v25-reference-pack`

The exact location is intentionally configurable because some source media may
be permission-sensitive and must not enter the product bundle. Recreate it with:

```sh
TC2000_REFERENCE_DIR=/private/tmp/tc2000-v25-reference-pack \
  bash tests/visual/fetch-tc2000-v25-reference-pack.sh
```

The generated `media-index.tsv` records each source page, media URL, local file,
source classification, and SHA-256. The files are discovery/reference material,
not approved Version 25 baselines. They can become baselines only after exact
build continuity, environment metadata, measurements, permissions, and human
review are recorded in the visual manifest.

## Official source catalogue

| Source | Coverage | Classification |
| --- | --- | --- |
| [Version 25 release notes](https://www.tc2000.com/features/whatsnew) | Build authority for `25.0.9571`; release changes affecting columns, charts, notes, layouts, data disclosures, and stability | `official_release_notes` |
| [Pinning Columns](https://help.tc2000.com/m/125751/l/1916114-pinning-columns) | V25.0.9172 column pinning, secondary sort, and indicator states | `official_v25_help` |
| [Managing Event Markers](https://help.tc2000.com/m/125751/l/1909214-managing-event-markers) | V25 chart marker settings, marker counts, and marker menus | `official_v25_help` |
| [Past Performance Lines](https://help.tc2000.com/m/125751/l/1909245-past-performance-lines) | V25 conditional-color past-performance controls and chart projections | `official_v25_help` |
| [Factory Default Layout Workspace](https://help.tc2000.com/m/69401/l/743982-factory-default-layout-workspace) | Factory layouts, Drill Down, Sector by Year, 1-Chart, 4-Timeframe, and workspace composition | `official_help_behavioral_history` |
| [Market Gauge: understand](https://help.tc2000.com/m/125751/l/1874582-how-to-understand-a-market-gauge) | Gauge geometry, count/percent display, watchlist/timeframe controls, and detailed view | `official_help_discovery` |
| [Market Gauge: create](https://help.tc2000.com/m/125751/l/1687541-how-to-create-a-market-gauge) | Gauge creation from columns, scans, conditions, and market indicators | `official_help_discovery` |
| [Use a Data Grid](https://help.tc2000.com/m/125751/l/1874646-how-to-use-a-data-grid) | Dockable symbol-linked grid containing system, technical, fundamental, and condition values | `official_help_discovery` |
| [Create a Data Grid](https://help.tc2000.com/m/125751/l/1874647-how-to-create-a-data-grid) | Grid construction, target mode, reusable items, and library workflow | `official_help_discovery` |
| [Edit Data Grid appearance](https://help.tc2000.com/m/69401/l/1678533-how-to-edit-how-a-data-grid-looks) | Color, gradient, grid lines, font, cell margins, and dense layout controls | `official_help_behavioral_history` |
| [Multiple-symbol comparison chart](https://help.tc2000.com/m/125751/l/1874643-how-to-create-a-comparison-chart-from-multiple-symbols) | Multi-selection, comparison mode, active-symbol price, and line comparisons | `official_help_discovery` |
| [Projection space](https://help.tc2000.com/m/125751/l/1874606-how-to-create-projection-space-on-a-chart) | Chart future-space mechanics and projection controls | `official_help_discovery` |
| [Chart timeframes](https://help.tc2000.com/m/125751/l/1874607-how-to-change-chart-timeframes) | Timeframe menu, chart history, and linked-timeframe behavior | `official_help_discovery` |
| [Floating windows](https://help.tc2000.com/m/125751/l/1874615-how-to-drag-items-to-a-floating-window) | Drag-to-float mechanics, browser windows, and target states | `official_help_discovery` |
| [Reposition tabs](https://help.tc2000.com/m/125751/l/1874614-how-to-drag-drop-tabs-to-reposition-in-a-tool-window) | Tab drag/reorder and tool-window tab stacks | `official_help_discovery` |
| [Redesigned Notes controls](https://help.tc2000.com/m/125751/l/1874628-how-to-use-the-redesigned-news-or-notes-window-controls) | Symbol-link selector, lock state, and notes-window relationships | `official_help_discovery` |
| [Column editor](https://help.tc2000.com/m/125751/l/1874588-how-to-use-the-column-editor) | Integrated columns/filters editor and reusable values/conditions | `official_help_discovery` |
| [Group columns](https://help.tc2000.com/m/125751/l/1874601-how-to-group-columns) | Group selection and column grouping | `official_help_discovery` |
| [Stack columns](https://help.tc2000.com/m/125751/l/1874595-how-to-stack-columns-in-a-watchlist) | Dense vertical stacking and drag/drop states | `official_help_discovery` |
| [Drag value column to chart](https://help.tc2000.com/m/125751/l/1874609-how-to-drag-drop-a-value-column-to-a-chart) | Column-to-chart target mode and placement overlay | `official_help_behavioral_history` |

The official [Latest Help Articles](https://help.tc2000.com/m/125751) index is the
navigation map used to discover additional V25-linked pages. The [saved chart
condition workflow](https://help.tc2000.com/m/69401/l/786679-how-to-save-a-chart-condition-to-the-library)
also documents reuse into filters, Data Grids, Market Gauges, Market Indicators,
True/False columns, and target-mode windows.

## Secondary discovery sources

These are useful for discovering additional states and composition patterns, but
they are not visual authorities and must never become pixel baselines without
independent V25 build verification:

- [Liberated Stock Trader TC2000 review](https://www.liberatedstocktrader.com/tc2000-review/)
- [DayTradingZ TC2000 review](https://daytradingz.com/stock-screener/)
- [Newton Advisor TC2000 review](https://newtonadvisor.com/tc2000-review/)
- [The Sovereign Investor sector/industry review](https://thesovereigninvestor.net/tc2000-review/)
- [GreatWorkLife sector analysis review](https://www.greatworklife.com/tc2000-review/)
- [TC2000 shared watchlist example](https://www.tc2000.com/share/affiliate/donaldwilliams/watchlist/b1de8768-7e45-4d0e-b2da-57317e3e483c)

These pages are retained as URLs only. Their screenshots may be old, altered,
subscription-specific, or copyright-protected.

## Use in implementation

The pack is used to:

1. identify missing interaction states and dense-window composition;
2. compare control hierarchy, spacing, chart chrome, watchlist density, and
   target-mode behavior during implementation;
3. derive candidate design-token measurements;
4. expand the parity matrix and interaction tests;
5. locate the states that still require an authorised exact-build capture.

It does **not** relax the visual gate. All retrieved images remain
`discovery_candidate`, `discovery_only`, or `behavior_only` until the manifest
records approved build continuity and review.
