# Technical Radar

This document describes the current Technical Radar implementation and the intended direction for future iterations.

## Current state

The repository now includes a first-pass **Technical Radar v1** plus a broader **Radar v2** continuation intended for explainable multi-timeframe discovery:

- backend persistence for radar runs and detections
- persisted setup threads that carry related detections across runs
- thread-level current state tracking
- a synchronous/manual scan entrypoint at `POST /api/v1/radar/run`
- a dedicated `/radar` frontend surface
- chart-side, non-editable radar evidence rendered through native chart indicators and drawings
- a chart-side radar sub-panel that lists all current detections for the loaded instrument
- persisted score factors and evidence payloads so the UI can explain why a setup ranked where it did
- actionable level fields (`entry_price`, `invalidation_price`, `target_price`) carried through backend and frontend
- explicit retest, fakeout/failure, and compression setup families
- state-aware filtering and presentation (`developing`, `confirmed`, `resolved`, `invalidated`, `stale`)
- lifecycle-driven invalidated / resolved / stale transitions on later scans
- richer AVWAP anchor provenance plus all-time / YTD / rolling-window context
- diagonal trendline, gap, and simple pattern-structure context in evidence payloads
- saved radar views, a radar dashboard widget, and focus-aware chart overlay dimming
- timeframe-aware runs, detections, overlays, history, and outcome summaries
- radar-side workflow actions to create price alerts and add detections to watchlists
- a per-instrument history browser plus aggregated forward-outcome research summaries

V1 began intentionally:

- daily-focused (`D1` primary timeframe)
- read-only from a workflow perspective
- transparent rather than overly clever
- separable from user drawings, alerts, watchlists, and trade plans

The current v2 baseline has moved past those constraints:

- manual radar runs are timeframe-selectable
- the primary radar UI supports alert/watchlist workflows directly
- chart/radar consumers can inspect both current detections and broader prior-run history for an instrument

## Backend model

### `radar_run`

Represents one scan execution:

- `timeframe`
- `universe_type`
- `universe_filter`
- `status`
- `started_at`
- `completed_at`
- `evaluated_count`
- `detection_count`
- `error_summary`

### `radar_detection`

Represents one persisted opportunity:

- `run_id`
- `instrument_id`
- `timeframe`
- `setup_type`
- `score`
- `observed_at`
- `signal_at`
- `context_at`
- `state`
- `state_reason`
- `fresh_until` (legacy persisted field; no longer used as a lifecycle TTL)
- `thread_id`
- `thread_event_index`
- `key_level_price`
- `entry_price`
- `invalidation_price`
- `target_price`
- `summary`
- `invalidation_hint`
- `outcome_status`
- `outcome_last_evaluated_at`
- `bars_since_signal`
- `max_favorable_excursion_pct`
- `max_adverse_excursion_pct`
- `target_hit_at`
- `invalidated_at`
- `evidence_json`
- `score_factors`

`evidence_json` is deliberately machine-owned, not user-editable. It is designed to feed native chart indicators, drawings, and explainability UI directly.

### `radar_setup_thread`

Represents one persisted setup storyline for a symbol / timeframe / nearby level cluster:

- `instrument_id`
- `timeframe`
- `context_role`
- `reference_price`
- `current_setup_type`
- `current_state`
- `state_changed_at`
- `started_at`
- `last_seen_at`
- `detection_count`

The thread model is what lets the UI tell the difference between isolated detections and an evolving story such as `approaching_resistance -> rejection -> breakdown`.

## Current setup taxonomy

The current detector supports:

- `approaching_support`
- `approaching_resistance`
- `breakout`
- `breakout_retest`
- `breakdown`
- `breakdown_retest`
- `fakeout`
- `fakedown`
- `failed_reclaim`
- `failed_breakdown_recovery`
- `compression_support`
- `compression_resistance`
- `reclaim`
- `rejection`

These are derived from a broader structure set than the original v1 baseline:

- horizontal support/resistance zones clustered from repeated swing highs/lows
- prior swing points
- anchored VWAP from recent/contextual anchors
- EMA context (`20`, `50`, `200`)
- 52-week high/low context
- all-time high/low context
- YTD open/high/low context
- rolling weekly/monthly window extremes
- diagonal trendlines
- gap zones
- simple channel / wedge / triangle context when opposing trendlines are available

## Current evidence payload shape

The evidence payload is structured around native chart visual primitives plus explainability metadata:

- `indicator_visuals`
  - `ema`
  - `avwap`
  - `bb`
  - `keltner`
- `drawing_visuals`
  - `rectangle`
  - `trendline`
  - `horizontal_line`
  - `text_box`
- `overlays`
  - legacy compatibility field, now expected to remain empty for current radar-generated evidence
- `metrics`
  - `close`
  - `atr_14`
  - `zone_center`
  - `distance_to_zone`
  - `ema_levels`
  - `avwap`
  - `week52_high`
  - `week52_low`
  - `week52_high_time`
  - `week52_low_time`
  - `entry_price`
  - `invalidation_price`
  - `target_price`
  - `target_source`
  - `risk_reward`
  - `state`
  - `state_reason`
  - `signal_time`
  - `context_time`
  - `all_time_*`, `ytd_*`, and rolling-window level prices/times
  - `gap_count`
  - `pattern_count`
  - `multi_timeframe_hits`
  - `avwap_anchor_type`
  - `avwap_anchor_time`
  - `secondary_avwap`
- `structures`
  - high-level structure metadata such as role, touch count, timing, trendline, gap, and pattern context

The chart renders these through the same native indicator and drawing pipelines used elsewhere in the platform. Radar evidence remains non-editable and machine-owned, but it now reuses matching user indicators/drawings rather than drawing duplicate bespoke radar-only geometry on top.

`signal_time` and `context_time` serve different purposes:

- `signal_time`: when the current radar event should be treated as having appeared
- `context_time`: when the underlying level/zone was most recently touched

This matters because a same-day `breakdown`, `rejection`, and `approaching_resistance` can share the same daily bar but still mean different things. The chart-side radar list now uses a lightweight sequence model rather than pretending those are all the same event.

## Current scoring approach

Current scoring is a transparent normalized blend of:

- distance to the key level
- zone touch count
- recency of the last touch
- structure age
- overlap/confluence with EMA, AVWAP, and 52-week context
- multi-timeframe alignment
- trend/pattern context quality
- gap context
- AVWAP anchor quality
- recent reaction quality
- timeframe importance

The current scoring system is intentionally rule-based and readable. Future work can add stronger empirical weighting once outcome tracking exists.

## Frontend surfaces

### `/radar`

The main radar page currently provides:

- timeframe filter (`M30`, `H1`, `H4`, `D1`, `W1`, `MN`)
- setup-type filter
- state filter
- saved views
- symbol filter
- minimum-score filter
- open-only toggle
- latest run summary
- ranked detection list
- detail panel with score factors, evidence metrics, and an action-plan block
- detail-panel setup-thread history with clickable prior events
- instrument-level timeline across current detections
- instrument-level history browser across prior runs for the selected symbol/timeframe
- aggregated outcome research summaries by setup/timeframe
- direct workflow actions for creating a price alert or promoting a detection into a watchlist
- “Open in chart” action
- scan-lock UX while a run is in progress so the page cannot be spammed mid-run

The dashboard now also supports a radar widget for top detections with lightweight filter config.

### `/chart/:symbol`

When a detection is opened from the radar page:

- the chart loads the referenced symbol
- the selected detection is handed off internally, not through a public query-string contract
- the chart loads all current radar detections for that instrument into a dedicated radar sub-panel
- only the clicked detection is enabled by default when arriving from `/radar`
- direct chart loads keep detections available but disabled by default
- overlays remain non-editable
- the user can toggle detections individually
- the chart keeps radar evidence separate from saved drawings
- each radar row exposes human-readable detail plus thread timeline context via an info tooltip
- when multiple detections are enabled, the focused one stays at full opacity while the others dim
- the radar sub-panel includes a focused-detail block with action levels and thread timeline context
- the chart no longer relies on a global “show radar overlays” toggle

## Current limitations

Radar still does not yet include:

- scheduled scan orchestration
- live scan progress beyond a blocking in-page run state
- regime-aware weighting
- deeper outcome calibration / research beyond the current per-detection forward metrics and aggregate summary endpoint
- managed watchlist workflows beyond one-off promotion actions
- trade-plan generation
- strong empirical ranking calibration from observed forward outcomes
- richer overlap grouping/stacking semantics than the current focused-overlay dimming
- deeper multi-timeframe propagation semantics than the current contextual overlays and window levels

## Recommended future iteration order

### Phase 2: implemented Radar v2 baseline

Radar v2 now adds:

- retest, fakeout/failure, and compression setup families
- persisted detection and thread state fields
- lifecycle-driven invalidated / resolved / stale transitions on later scans
- richer AVWAP anchor context plus all-time / YTD / rolling-window level context
- diagonal trendlines, gap zones, and simple pattern-structure context
- state-aware filtering on `/radar`
- explicit entry / invalidation / target semantics in the persisted model
- saved radar views and a radar dashboard widget
- chart and radar UI surfaces for action-plan-style inspection, timelines, and focus-aware overlap handling
- timeframe-aware manual runs and filtering across the supported radar UI timeframes
- direct radar-to-alert and radar-to-watchlist workflow actions
- per-instrument history browsing and aggregate outcome summaries

### Phase 3: stronger continuity, chronology, and lifecycle semantics

Build on the current thread model with:

- stronger ordering semantics when multiple daily detections share one bar
- thread-level “active / resolved / invalidated” lifecycle
- better handling of repeated same-day state changes within one storyline

### Phase 4: richer structure extraction

Expand the detector to include:

- weekly/monthly propagated levels
- channels
- wedges
- triangles
- stronger AVWAP anchor taxonomy beyond the current contextual set
- moving-average slope and compression context
- optional volume-profile-style structural zones

### Phase 5: better event semantics

Add more nuanced event types:

- compression near level
- expansion away from level
- regime-aware confirmation rules

### Phase 6: operational radar workflows

Introduce:

- scheduled runs
- managed radar watchlists
- richer alert orchestration and state-transition-driven workflows
- downstream trade-plan / signal workflows

### Phase 7: research and feedback loop

Persist and analyze forward outcomes:

- what happened after a detection
- hold-time and confirmation behavior
- instrument-category differences
- regime differences
- score calibration
- learned weighting on top of explicit rule features

### Phase 8: platform integrations

Connect radar into:

- Strategy Lab universes
- trade signal / virtual trade tracking
- managed watchlists
- user notifications
- dashboard-level market triage workflows

## Design rules that should remain true

- Radar evidence must stay visually inspectable.
- Radar overlays should remain structurally separate from editable user drawings.
- The system should continue to prefer explainable detections over opaque scoring.
- Future automation should build on persisted detections rather than bypassing them.
