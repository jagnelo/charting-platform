# TC2000 Version 25 composite reference board

## 2026-08-18 — Provider-field conflict state remains visually unrepresented

Market Map now exposes a deterministic provider-precedence value plus explicit conflict provenance
and `profile_field_conflict` warnings when eligible persisted profile snapshots materially disagree.
The board has no authoritative Version 25 capture for this diagnostic treatment: warning copy,
candidate-detail affordance, tooltip geometry, or stale/conflict badge state.

Gap status: `required_missing` for exact conflict badge/detail geometry and interaction treatment.
Interim oracle: provider-precedence integration, helper tests `2/2`, complete watchlist/workspace
integration `91/91`, Ruff, compileall, and diff checks. No acceptance flexibility was used.
Evidence needed: an authoritative V25 state reference or a documented decision that this diagnostic
state is outside visual parity; until then it remains a tracked visual gap.

## 2026-08-18 — Provider-quality fields have no exact V25 visual authority

Locked source descriptors now retain adapter status/confidence and snapshot quality/provenance,
including the case where cached holdings remain usable after a provider failure. The board has no
authoritative V25 capture for this route-status/freshness treatment in a source picker, coverage
panel, or Market Map header.

Gap status: required_missing for exact status badge, stale/error copy, confidence/quality detail,
and geometry. Interim oracle: focused source/coverage 2/2 and full watchlist/workspace analysis
91/91. No acceptance flexibility was used. Evidence needed: an authoritative V25 capture or an
explicit decision that this diagnostic state is outside visual parity.

## 2026-08-18 — Same-date holdings revision state remains visually unrepresented

The implementation now preserves point-in-time truth when two ETF/index-proxy holdings snapshots
share a composition date but become known at different times: Market Map selects the latest
known-at revision eligible at the requested evaluation timestamp. The board has no authoritative
V25 capture for the resulting revision/freshness disclosure, warning, or tile-area transition.

Gap status: required_missing for exact revision badges, copy, stale/partial state, and geometry.
Interim oracle: the Docker-backed same-date revision Market Map regression and full 42/42
watchlist integration file. No acceptance flexibility was used. Evidence needed: an authoritative
V25 revision-state reference or an explicit decision that this data-integrity disclosure is outside
visual parity; provider population and historical continuity remain separate gaps.

## 2026-08-19 — Availability badges for arbitrary locked universes remain a visual gap

The product vision now treats every index/index-ETF constituent set as a locked watchlist that
can feed the same Market Map as a personal or arbitrary list. The implementation distinguishes
populated sources (`available`) from an empty membership load (`membership_not_loaded`) and an
ETF profile with no holdings snapshot (`holdings_snapshot_not_loaded`); all remain visible for
audit, are labelled `Unavailable`, and are disabled rather than silently replaced.

The board has no authoritative exact-build V25 capture for these ordinary locked-source states.
Gap status: `required_missing` for the exact unavailable label, provenance badge, disabled-option
styling, and picker geometry across market groups and ETF holdings. Interim oracle: Docker-backed
descriptor/API `2/2`, focused Market Map `24/24`, full frontend `888/888`, type/build, Ruff,
compileall, and diff checks. No acceptance flexibility was used. Evidence needed: an authoritative
V25 capture or an explicit product decision that this state is outside visual parity; provider
quality and historical continuity remain separate gaps.

## 2026-08-19 — Unavailable family-source picker state remains unrepresented

The board contains no authoritative exact-build capture for a benchmark-family source picker that
shows a mapped-but-unavailable value/growth/equal role. The workstation now keeps that canonical
locked source visible, labels it `Unavailable`, disables accidental selection, and prefers an
available source at startup; it never hides or substitutes the role. The focused `24/24` Market
Map component suite and full frontend `888/888` suite are the interim interaction oracle.

Gap status: `required_missing` for exact V25 unavailable-role label, badge, disabled-option styling,
and picker geometry. Evidence needed: a reviewed V25 capture of this state or an explicit accepted
product decision that the state is outside visual parity. Provider-backed family population and
historical continuity remain separate data gaps.

## 2026-08-19 — Bulk family refresh has no authoritative visual reference

The board contains no sufficiently authoritative Version 25 capture for an administrator running
an all-family or historical holdings backfill, nor for the per-family/per-leg success, unavailable,
route-not-ready, failure, snapshot, and composition-date report. The backend now supplies this
operational contract through one canonical locked-watchlist population path; it is intentionally
not exposed as a workstation menu or represented as a user-facing V25 visual claim.

Gap status: `captured_unmeasured`/`required_missing` for the admin refresh/report surface. Interim
oracle: deterministic API schemas, savepoint failure isolation, the `61/61` ETF integration file,
and the `90/90` affected Market Map/workstation suites. Evidence needed to close the gap: an
authoritative V25 administrator/backfill capture or an explicit product decision that this
maintenance surface is out of visual-parity scope.

## 2026-08-19 — Evaluation-time weight state is a backend acceptance gap

The board does not contain an authoritative exact-build capture for a historical map switching
between dated holdings weights. The backend now selects system-managed composition at the map's
evaluation timestamp and preserves the selected snapshot lineage; personal/combo current-list
semantics are intentionally distinct. Exact V25 weight badge, disclosure, stale/partial, and
revision geometry remain unrepresented and must not be mistaken for visually approved parity.

## 2026-08-19 — Universal family-role acceptance coverage

The controlled reference environment now represents every configured, available benchmark-family
leg as a locked WatchlistSource so the Market Map and breadth acceptance path can be exercised
across all S&P/Russell/Nasdaq roots and roles. This improves the browsable product vision's
functional coverage without inventing a visual claim: the family source-picker, unavailable-role,
derived-weight, and membership-revision states still have no exact-build V25 capture and remain
tracked as board gaps.

## 2026-08-19 family-leg source composition gap narrowed

The board supports a single dense heatmap language for arbitrary lists, but it does not show the
exact Version 25 source-picker treatment for a benchmark family whose cap, equal, value, and
growth legs are separately selectable locked lists. The implementation now composes those legs
as `benchmark-family:<family>:<role>` sources, preserves the same map/list surface, labels
derived equal-weight membership and unavailable roles, and reuses the canonical source lineage
through Market Map and generic breadth. Source/resolver/cache and `88/88` integration assertions
are the interim oracle.

Still unrepresented: exact V25 labels/icons, follow/clone affordance placement, derived equal
weight disclosure, unavailable-role styling, revision/freshness badges, and the populated visual
appearance of every family. These remain tracked reference gaps rather than silent passes.

## 2026-08-19 numeric profile-area state gap narrowed

The board has no authoritative Version 25 treatment for choosing a numeric tile-area field from
multiple provider profile snapshots, especially when one provider lacks that field. The backend
now uses one source-neutral alias/precedence contract for market cap, volume, 52-week range, P/E,
beta, and dividend yield, selecting a covered point-in-time snapshot and explicitly warning on
stats fallback. Exact V25 field selector, tooltip, conflict badge, and mixed-coverage geometry are
still unrepresented; provenance and integration assertions are the interim oracle.

## 2026-08-19 historical entitlement-revision area gap narrowed

The board has no authoritative Version 25 state for a historical Market Map whose profile source
changed free/paid or review status between two as-of dates. The implementation now reconstructs
the latest immutable entitlement revision known at the map evaluation timestamp, prevents future
revisions from leaking backward, and exposes revision/effective-time evidence in tile provenance.
The current-row fallback for sources with no revision is visibly warned and remains a tracked
compatibility gap. Exact V25 badge, tooltip, warning-copy, and revision-history geometry remain
unrepresented; deterministic API provenance and historical regression tests are the interim oracle.

## 2026-08-19 provider-precedence area state gap narrowed

The board does not show how Version 25 labels a market-cap tile when multiple providers have
different profile observations, or when a persisted snapshot comes from a source that is no
longer entitled. The implementation now selects the enabled free adapter-capable provider chain,
records provider rank and entitlement verification in tile provenance, and keeps an unranked
snapshot only with explicit cell/response warning state. The provider-policy integration and
complete watchlist suite are the interim correctness oracle. Exact V25 tooltip/badge wording,
provider-conflict affordances, and historical entitlement-revision controls remain unrepresented.

## 2026-08-19 point-in-time area provenance gap narrowed

The board has no authoritative capture of Version 25’s tile treatment when market-cap area is
point-in-time, mixed-coverage, or falling back to current metadata. The implementation now uses
canonical profile snapshots where available, labels each tile with snapshot provenance in the
data contract, and surfaces a response warning for current-metadata fallbacks. Deterministic
integration and component assertions are the interim oracle. Exact tooltip/badge wording and
mixed-coverage geometry remain unrepresented.

## 2026-08-19 combo historical departure gap narrowed

No authoritative board state shows how Version 25 presents a combo whose union/intersection or
exclusion dependency changes across time. The implementation now applies dependency active
intervals at `as_of`, preserves deterministic active ordering, and reports departed members as
structured exclusions. Complete watchlists integration coverage is the interim oracle. Exact
combo revision badges/history controls and multi-episode re-entry visuals remain unrepresented.

## 2026-08-19 managed departure as-of gap narrowed

The board has no authoritative capture of how Version 25 displays a managed constituent during its
grace period versus after a historical departure. The implementation now keeps current grace
visibility but excludes `left_screener_at <= as_of` from historical WatchlistSource resolution,
returning the departure timestamp and a structured exclusion. The focused integration regression
is the interim oracle. Exact badges, copy, and history controls remain unrepresented; combo
re-entry and append-only membership history are separate backend gaps.

## 2026-08-19 locked market-group revision gap narrowed

The board still has no authoritative capture of how Version 25 presents a refreshed locked index,
sector, or industry membership/weight revision. The implementation now has deterministic
membership lineage for those sources: member-row changes alter the source version and map cache
identity, and the rendered map reports the new weight. Focused integration assertions are the
interim acceptance oracle for correctness. Exact V25 revision badges, refresh copy, timestamps,
and any user-facing history affordance remain unrepresented and must stay tracked until a
complementary reference closes them.

## 2026-08-19 Python map source-polymorphism reference gap

The board does not show whether Version 25 exposes a derived combo or ephemeral multi-symbol
selection as a Python-backed map universe. The implementation follows the established dense map
language and uses the canonical source ID for every locked, derived, personal, ETF, and explicit
universe; component/API source-preservation checks are the interim oracle. Exact V25 affordance
copy and badges for this state remain unrepresented.

## 2026-08-19 arbitrary-watchlist lineage reference gap

The composed board supports one heatmap language for locked index/ETF constituent universes,
derived combo lists, managed scans, and editable personal watchlists, but it does not show the
exact V25 visual treatment for a membership revision or a derived source invalidating a cached
map. The implementation now uses deterministic membership fingerprints and preserves the same
heatmap surface; source/resolver/cache assertions are the interim oracle. Exact badges, refresh
copy, and revision-history geometry remain unrepresented and must stay tracked until a
complementary reference is reviewed.

## 2026-08-19 aggregate breadth plot reference gap

The board has no authoritative V25 capture of the complete flow from a cross-sectional breadth
result to a reusable chart plot, including its source-universe retention and aggregate-series
rerun state. The interim oracle therefore checks the explicit `percentage_history` output contract,
full declared-universe materialization, isolated `breadth_aggregate_percentage` adapter, and chart
plot metadata carrying the locked source ID or explicit symbols. Exact button wording, placement,
plot-library badges, and any V25 target-mode affordance remain a named visual gap and must not be
silently inferred from the member-level plot surface.

## 2026-08-19 explicit-source reference gap

The board does not contain an authoritative V25 capture of the exact multi-symbol ad-hoc universe
entry and its locked/ephemeral provenance treatment. The workstation now uses the board's dense
universe-control language, resolves symbols to canonical IDs, and renders the same Market Map as
saved lists and index/ETF sources. Functional resolution, deduplication, missing-symbol, and map
orchestration tests are the interim oracle; historical explicit membership and exact visual
geometry remain tracked gaps.

The current implementation resolves a multi-symbol entry through a single canonical batch request;
the board has no authoritative visual reference for request progress, partial missing-symbol
feedback, or the 500-member validation state. Those states remain functional/performance gaps for
visual comparison, not reasons to invent a V25 appearance or silently accept provider fallback.

The board also has no authoritative capture of the explicit-source durability action. The interim
oracle is the source-descriptor member-ID set plus the user-isolated personal-watchlist write and
the explicit confirmation count; exact V25 button wording/placement remains a tracked visual gap.

## 2026-08-19 universal derived-watchlist reference gap

The board supports the product decision that a combo watchlist should render in the same dense
heatmap language as an index/ETF constituent list or personal watchlist. The implementation now
exposes combo definitions as locked, derived `WatchlistSource` inputs and reuses the same Market
Map interaction contract. No authoritative V25 capture shows the exact combo-definition lineage or
locked-derived badge, so those details remain a tracked visual gap; deterministic source identity,
membership, and interaction tests are the interim acceptance oracle.

## 2026-08-19 Boolean breadth promotion reference gap

The board contains the dense Research Results/action language but no authoritative capture of the
exact Version 25 state after a Boolean breadth run is promoted successively to an alert, Market
Gauge, and Strategy signal. The implementation reuses one saved EasyScan and immutable code
version, and deterministic component/API assertions are the interim oracle. Button placement,
confirmation copy, and any target-specific V25 affordance remain a named visual gap until a
complementary reference is reviewed; this does not block the represented Research Results surface.

## 2026-08-18 universal-source and recursive-Python visual gap

The composed board supports the product decision that a locked index/ETF constituent list should
look and behave like any other TC2000 watchlist source when opened in a map: the membership is
managed and immutable, but the same dense heatmap, grouping, selection, linking, filtering, and
drill-down surfaces apply. It does not contain an authoritative V25 capture of the exact
locked-source lineage affordance or the recursive Python condition authoring/result state.

Those states therefore use the board's dense list/map/editor language plus deterministic
functional oracles. The functional tree path now supports both member and cross-sectional Python
leaves, but the exact V25 authoring/result geometry remains a tracked visual gap; no screenshot
threshold, mask, or older-generation reference is being promoted silently to close it.

## 2026-08-18 cross-sectional Python-series reference gap

The backend and isolated runner now support a Python numeric-series target whose comparison is
member-minus-group statistic, but the board has no authoritative V25 capture of that exact
authoring/result state. Functional acceptance is therefore covered by deterministic API/runner
oracles; exact visual acceptance remains a named gap until a complementary reference is found.

## 2026-08-17 mixed-scope breadth reference gap

The current board has no sufficiently authoritative Version 25 capture of a recursive breadth
condition that combines member-level and cross-sectional targets. The implementation uses the
board-guided dense condition-editor language and existing heatmap composition, with a deterministic
interim oracle covering scope labels, nested groups, clause diagnostics, pass/fail tiles, and
historical exclusions. The local API and isolated Study Lab runner now share the same nested
current/history evaluator, including the explicit group-statistic leaf. This remains a gap for exact
visual judgement; closure requires a reviewed
V25 capture or successor reference showing the mixed statistical authoring/result state.

## 2026-08-14 canonical workstation revalidation

The current non-seeded branch deployment was revalidated against the board-guided interaction
contract after the bootstrap repair. The complete authenticated workstation matrix passed `140/140`;
the four-environment board baselines and gap-directed state oracles remain the active visual track.
This run confirms represented shell density, tool-window containment, charts, grids, linking,
Study Lab composition, and top-down traversal behavior, but it does not promote any board image to
exact-build approval. `REF-SHELL-V25`, `REF-STATE-VARIANTS`, `REF-LINKING-V25`, `REF-STUDY-LAB-V25`,
`REF-ENV-TOKENS`, and `REF-PERMISSION-REVIEW` remain explicit where the board lacks authoritative
pinned-build state evidence.

## 2026-08-12 deterministic drawing-toolbar visual correction

The chart drawing toolbar was compared against the board's chart/comparison and dense-window
groups. The board supports the compact dark chart-tool composition, separators, flyout treatment,
and dense control language, but does not contain a pinned-build capture or measured icon sheet for
the drawing toolbar itself. The repository-controlled mismatch was therefore corrected without
invented exact-build claims: emoji and Unicode glyphs were replaced with deterministic original
CSS geometry, controls were tightened to a measured 32px button contract inside a 40px rail, and
utility controls received explicit accessible names and button types.

The focused drawing browser suite passes `4/4`, including the no-text-glyph and compact-geometry
contract, the no-update represented default-workstation visual assertion passes at 1920x1080/100%,
and the complete seeded authenticated Chromium matrix passes `107/107` executed tests with two
intentional skips. This is board-guided represented chart composition plus controlled seeded
interaction/data flexibility. It does not close the exact pinned-build drawing-icon/style gap:
`REF-STATE-VARIANTS` remains open for exact toolbar glyphs and unrepresented selected/disabled
variants, and stronger evidence would require a reviewed pinned-build capture or measurements.
No visual threshold, mask, uPlot renderer, provider, or product-scope rule changed.

## 2026-08-11 deterministic fixture isolation and complete revalidation

The seeded acceptance runtime was found to be mixing canonical bars/holdings with controlled
fixture rows when a persistent database already contained data. That was a real test-environment
defect, not a visual mismatch to be hidden: seeded E2E startup now replaces adjusted daily bars
for the controlled fixture universe, and seeded holdings reads are explicitly scoped to the
`controlled_fixture`/`e2e_reference` provenance. The focused router/seed regression slice passes
`17/17`.

Because the corrected runtime changed the deterministic observations (including the chart range,
sector values, and no-sector Industries prompt), the four-environment board-guided screenshots were
refreshed once from that runtime and then verified without update mode: `104/104` pass at
1920x1080 and 2560x1440, both at 100% and 125% display scale. The visual diff thresholds and masks
were not changed. This is explicitly seeded-fixture/board-guided flexibility, recorded to keep
the local oracle honest; it does not promote the web-sourced board to exact-build approval and
does not close the exact-build, permission, or unrepresented-state gaps below.

## 2026-08-10 acceptance update

The workstation now has a deterministic visual oracle for the integrated EasyScan condition
editor. The state is tracked as `watchlist-column-filter/condition_editor` with four local
display-scale baselines and is now board-covered because the composed board contains the
official Version 25 condition-editor/filter-selection states. The source pages do not prove
pinned build `25.0.9571`; that remains optional strengthening evidence, not an unrepresented-state
gap. The full board-guided matrix passes `104/104`; no visual threshold or mask was relaxed.

The retrieved reference pack is now composed into a single browsable visual board so
implementation decisions are made against a coherent product vision rather than isolated
screenshots.

## Build and review

The controlled pack is stored at `/private/tmp/tc2000-v25-reference-pack` and contains 230
retrieved images. It was refreshed and revalidated on 2026-08-10 from the recorded official
source URLs; the board validator passed all 230 local media sources. Generate the board with:

```bash
python3 tests/visual/build-tc2000-reference-board.py \
  /private/tmp/tc2000-v25-reference-pack \
  /private/tmp/tc2000-v25-reference-pack/reference-board.html

npx playwright screenshot --device='Desktop Chrome HiDPI' --full-page \
  file:///private/tmp/tc2000-v25-reference-pack/reference-board.html \
  /private/tmp/tc2000-v25-reference-pack/reference-board.png

python3 tests/visual/validate-tc2000-reference-board.py \
  /private/tmp/tc2000-v25-reference-pack/reference-board.html
```

The board groups every image by surface and labels it with source type, source build,
filename, and source-page link. It is an implementation and review aid; it does not merge
different product states into a claim that they are one deterministic screenshot.
The validator is a deterministic completeness check: it confirms that every generated image
card has a local source file. It does not promote any reference to an approved baseline.

## Current coverage

| Surface group | References | What it contributes |
|---|---:|---|
| Factory/default layouts | 47 | Dense workspace composition, layout tabs, chart/watchlist proportions |
| Data grids and columns | 53 | Column/filter editor, condition selection, grouping, stacking, historic columns, creation, use, appearance |
| Market gauges | 24 | Gauge creation, readings, condition-driven visuals |
| Charts and comparisons | 35 | Timeframes, comparisons, projections, markers, past performance |
| Windows and layout mechanics | 10 | Floating windows, tab repositioning, drag/drop composition |
| Notes and value-column workflows | 8 | Notes window and chart/watchlist transfer mechanics |
| Symbol linking | 6 | Link-color mechanics and linked-window behavior |
| Version 25 product/shared-layout evidence | 3 | Current product-level shell and shared-layout composition |

The grouped board exposes the intended visual language: dense dark chrome, compact title and
link controls, thin separators, small typography, data-grid-first workflows, chart panes with
minimal decoration, and frequent drag/drop transfer between tools.

### 2026-08-10 visual iteration note

The pack was expanded with official current Version 25 help pages for the integrated condition
editor, ALL/ANY filter selection, symbol linking, and historic columns. The resulting board now
contains 230 images across 26 surfaces. These additions strengthen the board-guided visual target
for watchlist/filter/linking composition; their source/build labels remain discovery evidence where
the page does not prove pinned build `25.0.9571`, so they do not silently close the related exact-
build or state-variant gaps.

The board-guided comparison of the compact relative-strength window exposed a concrete
repository-controlled mismatch: uPlot's default HTML legend was rendered below the plot while
the workstation-owned ratio legend was already rendered above it. `RatioUPlot` now disables the
duplicate legend, with a unit regression and a rebuilt browser overlap check. The earlier stale
baseline run was superseded: baselines were regenerated once from a fresh controlled fixture and
the complete matrix then passed `100/100` without update mode across all four required environments.
No mask or threshold was promoted. This uses the board-guided/fixture flexibility recorded in the
acceptance-governance ledger; it does not alter any gap's closure requirement. Exact-build and
unrepresented-state gaps remain in the register.

### 2026-08-12 deterministic fixture alignment after data-grid work

The first no-update visual run after adding watchlist header separators reported `90/104`, with
all `14` failures confined to the 2560x1440/125% project. Actual/expected review showed a common
historical-content mismatch across unrelated shell, chart, ratio, and freshness surfaces; it was
not a header geometry regression. The branch-scoped stack was rebuilt with both seed flags, the
per-test immutable factory reset was retained, and only the stale 125% snapshots were regenerated
after review. The complete no-update matrix then passed `104/104` across all four required
environments. No mask, threshold, or product criterion was changed. This closed the local
fixture-version alignment issue; the later native hit-target correction is recorded immediately
below.

The subsequent native hit-target audit found and fixed a repository-controlled geometry issue: the
header grid had collapsed to 1px, so the scroll surface intercepted real pointer input. The 23px
minimum-height/stacking correction was reviewed against the board's dense grid composition. Native
resize now passes `1/1`, the full authenticated flow passes `109/109` executed with two skips, and
the no-update four-environment visual matrix passes `104/104`. This closes the native hit-target
part of the resize gap; exact-build pointer-state measurements remain `REF-STATE-VARIANTS`.

## Gaps identified from the board

These are now explicit implementation/acceptance gaps rather than an undifferentiated
“visual references unavailable” state. Each gap has an interim oracle so development can
continue without disguising the absence of authoritative Version 25 evidence.

| Gap ID | Missing reference and affected acceptance cases | Current implementation treatment | Interim test/oracle | Evidence required to close the gap |
|---|---|---|---|---|
| `REF-SHELL-V25` | Any shell detail not sufficiently represented by the board, including exact pinned-build-only variants | Use the board’s factory-layout/product-image groups as the visual authority for represented density, proportions, chrome, and token direction; track only uncovered details as limited | Four seeded environment geometry/containment audits, deterministic screenshot harness, and browser shell interaction tests | Additional exact-build evidence only for the identified uncovered detail; it is not a blanket gate |
| `REF-STATE-VARIANTS` | Loading, stale, partial, provider-error, blocked-pop-out, recovery, focused, keyboard-selected, and disabled states | Implement explicit freshness/error/recovery states from platform contracts; do not infer their exact V25 styling from unrelated screenshots | Browser tests for stale/partial/error/recovery flows, including `F8i-a` provider-error, `F8i-b` loading, `F8i-c` stale, `F8i-d` partial, and `F8k-a` blocked pop-out, plus four-environment `chart-loading-gap`, `stale-freshness-gap`, `partial-coverage-gap`, and `blocked-popout-gap` baselines, accessibility/focus assertions, structured cell warnings, and the official V25 hotkey behavior article | Complete state capture set from the pinned build at a reviewed target environment |
| `REF-LINKING-V25` | All normal link groups, yellow wildcard, grey isolation, timeframe propagation, linked crosshair, and cross-window propagation | Preserve canonical-ID link bus and test behavioral semantics independently of missing visual proof | Link-group, keyboard, cross-window, and chart crosshair integration tests; official timeframe-linking behavior evidence is recorded in the manifest | Authoritative captures covering every link state and interaction, with timing and environment metadata |
| `REF-STUDY-LAB-V25` | Open-ended research editor, structured renderers, occurrence browser, sandbox-error and promotion surfaces | This is an original surface with no direct TC2000 analogue; use the board’s dense editor/grid language for composition and the product contracts for behavior | Four-environment `Study Lab original surface` local baselines (manifest-linked for `editor`) plus validation, run, cancellation, recovery, structured-output, occurrence-link, and promotion tests | A reviewed V25 analogue only if one is discovered; otherwise retain the original-surface exception and its local baseline |
| `REF-BREADTH-COMPOSER-V25` | User-authored breadth predicate editor, target-scope controls, aggregate/member/history views, occurrence linking, and promotion affordances | The board shows related dense condition/filter language but no sufficiently authoritative V25 capture of this complete cross-sectional study workflow; the recursive nested predicate tree and aggregate Study Lab promotion are implemented from the generic breadth contract, while target axes and exact promotion geometry remain explicit | Four-environment local baselines plus API/runner/browser tests for selected universe, measured field, target/operator, nested clauses, pass/fail drill-down, history, linked symbols, and aggregate Study Lab rerun; the authenticated tree flow proves `all(any(new_high_low))` | A reviewed V25 capture covering the generic breadth authoring/result/promotion states, or a reviewed successor reference that explicitly covers them |
| `REF-ENV-TOKENS` | Deterministic 1920×1080 and 2560×1440 captures at 100% and 125% display scale, with measured tokens | Maintain four seeded visual environments and tokenized geometry checks; keep screenshot comparison failures visible | Geometry/viewport containment, token assertions, and unmasked screenshot diff reporting | Captures and measurements for all four required environments, approved against the manifest |
| `REF-PERMISSION-REVIEW` | Permission classification for any future redistribution or exact-build baseline promotion | The board is valid for local implementation and acceptance guidance under its recorded provenance; permission review is required only before redistribution or promotion to a stronger exact-build baseline | Manifest schema/unit tests require source, hash, state, and review fields; board-guided regression remains valid | Permission decision, reviewer identity/date, storage classification, and optional stronger baseline entry |

The board is used immediately for implementation review, board-guided screenshot acceptance, and
gap-directed browser checks. No board image is promoted to exact-build `approved` merely because
it visually complements another image. That stronger status is optional evidence for a covered
state and targeted closure evidence for a documented gap; see
`docs/tc2000-acceptance-governance.md`.

This board is therefore the active visual reference for the current goal, not merely a discovery
artifact. Each UI iteration must consult the relevant board group, compare a deterministic local
render, and record any uncovered or ambiguous state below. Using the board in this way is an
explicit acceptance flexibility and must be reported as such; it does not erase the gap register.

## State coverage ledger

The manifest records `board_covered_states` and `board_gap_states` for every required surface.
Covered means the board provides enough applicable visual/interaction evidence to guide the
implementation; it still requires a measured local regression baseline before final acceptance.
Gap states are not ignored: they remain limited, receive an interim functional oracle, and need
specific closure evidence.

| Surface | Board-covered states | Remaining gap states |
|---|---|---|
| Application shell | default, menu open, focused search | keyboard help, keyboard-selected search, fetching, stale data, delayed data, unavailable data |
| Workspace docking | tabbed, maximized, floating, restored, drag target | tool menu open, blocked pop-out |
| Chart window | daily candles, linked crosshair, drawing, alert marker | loading, error |
| Watchlist/columns/filters | sorted, grouped, stacked, filtered, selected, column editor, condition editor | partial coverage |
| Breadth composer/results | dense condition/filter language only | target-scope editor, nested predicate tree, aggregate/member/history states, occurrence linking, promotion |
| Study Lab | none (original product surface) | editor, validation, disabled controls, running, histogram, occurrence table, sandbox error |

Provider-error and Study Lab validation-error states now also have deterministic local baselines
in all four required display environments. They remain `required_missing` because the board does
not provide authoritative pinned-build styling for those states; the added screenshots strengthen
the interim oracle but do not close either visual-reference gap.

Study Lab structured-result rendering now has the same four-environment interim baseline for its
histogram and occurrence-table states. The fixture exercises the completed run surface, scalar
metric, bar chart, histogram, table, and clickable occurrence event together; these states remain
`required_missing` under `REF-STUDY-LAB-V25` because the board contains no authoritative Study Lab
capture.

Study Lab sandbox failures now also have a four-environment interim baseline. The failed-run fixture
keeps the sandbox diagnostic, warning, execution log, resource usage, and rerun affordance visible;
`sandbox_error` remains `required_missing` because the board contains no authoritative error-state
capture for this original surface.

## 2026-08-11 current-source visual revalidation

After the logout/request-boundary repair, the current Vite source was rechecked against the seeded
visual backend. The four-environment board-guided matrix passed `104/104` at 1920×1080 and
2560×1440, both at 100% and 125% display scale. No threshold, baseline, or mask changed. This is
the documented board-plus-deterministic-fixture interim track; exact-build, permission, and the
unrepresented state gaps remain unchanged and actionable.
