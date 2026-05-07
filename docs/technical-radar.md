# Technical Radar

This document describes the current Technical Radar implementation and the intended direction for future iterations.

## Current state

The repository now includes a first-pass **Technical Radar v1** intended for daily swing-trading discovery:

- backend persistence for radar runs and detections
- persisted setup threads that carry related detections across runs
- a synchronous/manual scan entrypoint at `POST /api/v1/radar/run`
- a dedicated `/radar` frontend surface
- chart-side, non-editable radar evidence overlays
- a chart-side radar sub-panel that lists all current detections for the loaded instrument
- persisted score factors and evidence payloads so the UI can explain why a setup ranked where it did

V1 is intentionally:

- daily-focused (`D1` primary timeframe)
- read-only from a workflow perspective
- transparent rather than overly clever
- separable from user drawings, alerts, watchlists, and trade plans

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
- `fresh_until`
- `thread_id`
- `thread_event_index`
- `key_level_price`
- `summary`
- `invalidation_hint`
- `evidence_json`
- `score_factors`

`evidence_json` is deliberately machine-owned, not user-editable. It is designed to feed chart overlays and explainability UI directly.

### `radar_setup_thread`

Represents one persisted setup storyline for a symbol / timeframe / nearby level cluster:

- `instrument_id`
- `timeframe`
- `context_role`
- `reference_price`
- `current_setup_type`
- `started_at`
- `last_seen_at`
- `detection_count`

The thread model is what lets the UI tell the difference between isolated detections and an evolving story such as `approaching_resistance -> rejection -> breakdown`.

## Current setup taxonomy

V1 currently supports:

- `approaching_support`
- `approaching_resistance`
- `breakout`
- `breakdown`
- `reclaim`
- `rejection`

These are derived from a deliberately narrow first-pass structure set:

- horizontal support/resistance zones clustered from repeated swing highs/lows
- prior swing points
- anchored VWAP from the latest relevant pivot in a zone
- EMA context (`20`, `50`, `200`)
- 52-week high/low context

## Current evidence payload shape

The evidence payload is structured around chart-ready overlays plus explainability metadata:

- `overlays`
  - `zone`
  - `line`
  - `marker`
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
  - `signal_time`
  - `context_time`
- `structures`
  - high-level structure metadata such as role, touch count, and timing

The chart renders these as a separate visual layer from saved drawings so radar evidence remains inspectable without becoming editable chart state.

`signal_time` and `context_time` serve different purposes:

- `signal_time`: when the current radar event should be treated as having appeared
- `context_time`: when the underlying level/zone was most recently touched

This matters because a same-day `breakdown`, `rejection`, and `approaching_resistance` can share the same daily bar but still mean different things. The chart-side radar list now uses a lightweight sequence model rather than pretending those are all the same event.

## Current scoring approach

V1 scoring is a transparent normalized blend of:

- distance to the key level
- zone touch count
- recency of the last touch
- structure age
- overlap/confluence with EMA, AVWAP, and 52-week context
- recent reaction quality
- timeframe importance

The current scoring system is intentionally rule-based and readable. Future work can add stronger empirical weighting once outcome tracking exists.

## Frontend surfaces

### `/radar`

The main radar page currently provides:

- setup-type filter
- symbol filter
- minimum-score filter
- fresh-only toggle
- latest run summary
- ranked detection list
- detail panel with score factors and evidence metrics
- detail-panel setup-thread history with clickable prior events
- “Open in chart” action
- scan-lock UX while a run is in progress so the page cannot be spammed mid-run

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
- the chart no longer relies on a global “show radar overlays” toggle

## Current limitations

V1 does not yet include:

- scheduled scan orchestration
- live scan progress beyond a blocking in-page run state
- multi-timeframe propagation logic
- gap structures
- wedges, channels, triangles, or diagonal trendline extraction
- regime-aware weighting
- forward outcome tracking
- dashboard widgets
- radar-driven alerts
- radar-driven managed watchlists
- trade-plan generation
- strong multi-bar state modeling beyond proximity-based thread matching
- strong empirical ranking calibration from observed forward outcomes

## Recommended future iteration order

### Phase 2: stronger continuity and state semantics

Build on the new thread model with:

- state-transition-aware thread updates
- explicit event families like retests and failed moves
- stronger ordering semantics when multiple daily detections share one bar
- thread-level “active / resolved / invalidated” lifecycle
- a proper symbol-level radar history browser instead of only per-detection thread slices

### Phase 3: richer structure extraction

Expand the detector to include:

- weekly/monthly propagated levels
- opening gaps and unfilled gap zones
- diagonal trendlines
- channels
- wedges
- triangles
- stronger AVWAP anchor taxonomy
- moving-average slope and compression context
- optional volume-profile-style structural zones

### Phase 4: better event semantics

Add more nuanced event types:

- fakeout
- fakedown
- failed reclaim
- failed breakdown recovery
- breakout retest
- breakdown retest
- compression near level
- expansion away from level
- regime-aware confirmation rules

### Phase 5: operational radar workflows

Introduce:

- scheduled runs
- saved radar filters/views
- radar history browser
- dashboard widgets
- radar-to-watchlist promotion
- radar-derived alerts

### Phase 6: research and feedback loop

Persist and analyze forward outcomes:

- what happened after a detection
- hold-time and confirmation behavior
- instrument-category differences
- regime differences
- score calibration
- learned weighting on top of explicit rule features

### Phase 7: platform integrations

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
