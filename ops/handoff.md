# Active Handoff

## Current task

- ID: technical-radar-v2
- Title: Extend Technical Radar with richer structures, lifecycle, timeframe-aware workflows, outcome tracking, and matching docs/tests

## Current worker

- Name: Codex
- Session started: 2026-05-07T17:55:00Z
- Soft stop deadline: n/a

## Completed in this session

- Increased the `/radar` detail preview chart height in `frontend/src/components/radar/RadarDetailPreviewChart.vue` from `214px` to `280px` for easier chart reading.
- Reworked the dashboard radar widget setup filter so it no longer relies on free-text guessing:
  - `frontend/src/views/DashboardView.vue` now exposes a dropdown-style checkbox picker of supported setup types
  - `frontend/src/components/dashboard/DashboardRadarWidget.vue` now accepts zero/one/many setup filters, fans out multi-setup API requests, merges/dedupes results, and summarizes the active selection in widget metadata
- Replaced dashboard radar row click navigation with a widget-local detail overlay:
  - clicking a radar row now opens an in-widget detail card
  - `Open chart` is now an explicit action instead of the default row click behavior
- Tightened the `/radar` responsive layout in `frontend/src/views/RadarView.vue` so the two-pane split survives moderate horizontal compression:
  - the collapse breakpoint moved down substantially
  - the detections pane now switches to a compact card-list presentation before the table becomes unreadable
  - the results panel keeps its own visible footprint instead of disappearing beneath an oversized detail pane
- Toned down radar-owned overlay emphasis and slimmed shared line defaults:
  - reduced default indicator/drawing line widths in `frontend/src/lib/indicators/catalog.ts`, `frontend/src/components/chart/IndicatorPanel.vue`, and `frontend/src/components/chart/UPlotChart.vue`
  - reduced radar drawing glow in `frontend/src/lib/drawings/renderer.ts`
  - reduced radar indicator highlight width/blur in `frontend/src/components/chart/UPlotChart.vue`
  - reduced backend-emitted radar visual line widths in `backend/app/services/radar_engine.py`
- Expanded the dashboard radar widget test coverage in `frontend/tests/unit/components/test_dashboard_radar_widget.test.ts` to cover multi-setup filtering.
- Expanded frontend radar/dashboard coverage toward the previously thin responsive and interaction areas:
  - `frontend/tests/unit/views/test_radar_view.test.ts` now covers the compact detections-list mode
  - `frontend/tests/unit/components/test_dashboard_radar_widget.test.ts` now covers widget-local detail opening instead of row-click redirect
- Created `feat/technical-radar-v2` from `master` and updated `docs/project-todos.md` to fix numbering and reflect the current radar baseline more accurately.
- Extended the radar backend model and migration with:
  - `RadarState`
  - retest, fakeout/failure, and compression setup families
  - persisted `state`, `state_reason`, `entry_price`, `invalidation_price`, and `target_price` on detections
  - persisted `current_state` and `state_changed_at` on setup threads
  - migration `a1b2c3d4e5f6_add_radar_v2_state_and_retests.py`
- Expanded the radar engine with:
  - diagonal trendline, gap, and simple pattern-structure context
  - richer AVWAP anchor provenance plus all-time / YTD / rolling-window context
  - retest, fakeout/failure, and compression classification
  - richer score factors for multi-timeframe alignment, trend/pattern quality, gap context, and AVWAP anchor quality
  - action-level generation and overlays
  - automatic invalidated / expired thread transitions on later scans
  - duplicate-thread-event dedupe across reruns
- Extended the radar API and schemas with:
  - timeframe-aware run/filter support on `GET /api/v1/radar/runs`, `POST /api/v1/radar/run`, `GET /api/v1/radar/detections`, and `GET /api/v1/radar/instruments/{instrument_id}/overlays`
  - instrument history and outcome summary endpoints
  - radar-to-watchlist and radar-to-price-alert workflow actions
  - richer state/action/thread/outcome fields in summaries, details, and thread-history rows
- Extended the radar outcome model with:
  - `outcome_status`
  - `bars_since_signal`
  - `max_favorable_excursion_pct`
  - `max_adverse_excursion_pct`
  - `target_hit_at`
  - `invalidated_at`
- Extended the frontend radar surfaces:
  - `/radar` timeframe/state filtering, saved views, richer detail metrics, history browser, outcome research, and action-plan presentation
  - dashboard radar widget support in `DashboardView` with timeframe config
  - chart-side radar focus/detail block plus focus-aware overlay dimming
  - direct `/chart/:symbol` loads still start with detections disabled while `/radar -> /chart` preselects the chosen detection
- Expanded radar-specific tests across:
  - backend unit tests for fakeouts, richer structures, AVWAP anchors, scoring factors, and lifecycle helpers
  - backend radar API integration tests for filtering, action/evidence payloads, duplicate reruns, and invalidated transitions
  - frontend store/view/component tests for saved views, radar handoff, radar widget rendering, and richer radar UI behavior
- Reconciled radar-related docs so the written spec matches the implemented v2 baseline:
  - `docs/technical-radar.md`
  - `docs/api.md`
  - `docs/architecture.md`
  - `docs/testing.md`
  - `docs/project-todos.md`

## Pending

- Commit the current Radar v2 work in isolated commits.
- Decide the dashboard radar widget row-click behavior:
  - the widget now uses a local detail overlay by default
  - the broader future question is whether multi-instrument widgets should eventually be able to publish clicked instruments into dashboard link groups
- Run browser/E2E validation for `/radar`, the dashboard radar widget, and `/chart/:symbol` if we want a visual signoff beyond unit/integration coverage.

## Exact next step

- Review the current branch diff, group the newest radar UX/layout/native-visual changes into contextual commits, then decide the dashboard widget click model before broader dashboard-linking work.

## Files touched

- `backend/app/models/__init__.py`
- `backend/app/models/radar.py`
- `backend/app/routers/radar.py`
- `backend/app/schemas/radar.py`
- `backend/app/services/radar_engine.py`
- `backend/alembic/versions/a1b2c3d4e5f6_add_radar_v2_state_and_retests.py`
- `backend/tests/integration/api/test_radar.py`
- `backend/tests/unit/services/test_radar_engine.py`
- `frontend/src/components/chart/IndicatorPanel.vue`
- `frontend/src/components/chart/UPlotChart.vue`
- `frontend/src/components/dashboard/DashboardRadarWidget.vue`
- `frontend/src/components/radar/RadarDetailPreviewChart.vue`
- `frontend/src/stores/radar.ts`
- `frontend/src/types/index.ts`
- `frontend/src/views/DashboardView.vue`
- `frontend/src/views/RadarView.vue`
- `frontend/src/views/ChartView.vue`
- `frontend/tests/unit/components/test_dashboard_radar_widget.test.ts`
- `frontend/tests/unit/stores/test_radar_store.test.ts`
- `frontend/tests/unit/views/test_chart_view_radar_handoff.test.ts`
- `frontend/tests/unit/views/test_radar_view.test.ts`
- `docs/project-todos.md`
- `docs/api.md`
- `docs/architecture.md`
- `docs/project-todos.md`
- `docs/technical-radar.md`
- `docs/testing.md`

## Validation run

- `rtk backend/.venv/bin/pytest backend/tests/unit/services/test_radar_engine.py --no-cov -q`
- `rtk npm --prefix frontend run test -- --run tests/unit/components/test_dashboard_radar_widget.test.ts tests/unit/views/test_radar_view.test.ts tests/unit/views/test_chart_view_radar_handoff.test.ts tests/unit/stores/test_radar_store.test.ts tests/unit/lib/test_radar_visuals.test.ts`
- `rtk npm --prefix frontend run type-check`
- `rtk make test-fe`
- `rtk backend/.venv/bin/python -m py_compile backend/app/models/radar.py backend/app/models/__init__.py backend/app/routers/radar.py backend/app/schemas/radar.py backend/app/services/radar_engine.py backend/tests/unit/services/test_radar_engine.py backend/tests/integration/api/test_radar.py`
- `rtk backend/.venv/bin/python -m ruff check backend/app/models/__init__.py backend/app/models/radar.py backend/app/routers/radar.py backend/app/schemas/radar.py backend/app/services/radar_engine.py backend/tests/unit/services/test_radar_engine.py backend/tests/integration/api/test_radar.py`
- `rtk backend/.venv/bin/pytest backend/tests/unit/services/test_radar_engine.py --no-cov -q`
- `rtk backend/.venv/bin/pytest backend/tests/integration/api/test_radar.py --no-cov -q`
- `rtk npm --prefix frontend run test -- --run tests/unit/components/test_dashboard_radar_widget.test.ts tests/unit/stores/test_radar_store.test.ts tests/unit/views/test_radar_view.test.ts tests/unit/views/test_chart_view_radar_handoff.test.ts`
- `rtk npm --prefix frontend run type-check`
- `rtk make test-fe`
- `rtk make test-unit`

## Errors / warnings / logs

- Running backend unit and integration tests together in one combined pytest invocation can still fall back into the repo’s Docker/testcontainers fixture path in this environment and fail on Docker socket permissions. Running the radar integration file directly succeeded, and `make test-unit` also passed because it is unit-only.
- Frontend test output still includes the existing Vite CJS deprecation notice, but the suite passed.
- Backend tests still emit existing repo-level Pydantic/JOSE deprecation warnings outside this radar change-set.

## Assumptions made

- Moderate desktop-width reduction should preserve the split `/radar` layout; only genuinely narrow screens should collapse into a stacked layout.
- Multi-setup dashboard filtering is better implemented as explicit API fan-out and merge/dedupe than as another free-text filter box or a lossy client-side post-filter over one API response.
- Radar-owned overlays should stay visually subordinate to price/owned chart context even when they are highlighted through reused native primitives.
- Radar v2 should expand to multiple platform timeframes through the existing timeframe enum rather than introducing arbitrary user-defined intervals.
- The current pattern layer should stay explainable and lightweight rather than trying to infer complex discretionary chart patterns with opaque rules.
- Focus-aware overlay dimming is an acceptable first overlap-management step before fuller grouping/stacking semantics exist.

## Ready to commit?

- yes
- if no, why: n/a
