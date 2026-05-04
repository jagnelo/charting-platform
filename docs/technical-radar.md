# Technical Radar

This document describes the current Technical Radar implementation and the intended direction for future iterations.

## Current state

The repository now includes a first-pass **Technical Radar v1** intended for daily swing-trading discovery:

- backend persistence for radar runs and detections
- a synchronous/manual scan entrypoint at `POST /api/v1/radar/run`
- a dedicated `/radar` frontend surface
- chart-side, non-editable radar evidence overlays
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
- `fresh_until`
- `key_level_price`
- `summary`
- `invalidation_hint`
- `evidence_json`
- `score_factors`

`evidence_json` is deliberately machine-owned, not user-editable. It is designed to feed chart overlays and explainability UI directly.

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
- `structures`
  - high-level structure metadata such as role, touch count, and timing

The chart renders these as a separate visual layer from saved drawings so radar evidence remains inspectable without becoming editable chart state.

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
- “Open in chart” action

### `/chart/:symbol?radarDetectionId=...`

When a detection is opened from the radar page:

- the chart loads the referenced symbol
- radar overlays load through the radar API
- overlays remain non-editable
- the user can toggle the radar layer on/off independently of drawings

## Current limitations

V1 does not yet include:

- scheduled scan orchestration
- multi-timeframe propagation logic
- gap structures
- wedges, channels, triangles, or diagonal trendline extraction
- regime-aware weighting
- forward outcome tracking
- dashboard widgets
- radar-driven alerts
- radar-driven managed watchlists
- trade-plan generation

## Recommended future iteration order

### Phase 2: richer structure extraction

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

### Phase 3: better event semantics

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

### Phase 4: operational radar workflows

Introduce:

- scheduled runs
- saved radar filters/views
- radar history browser
- dashboard widgets
- radar-to-watchlist promotion
- radar-derived alerts

### Phase 5: research and feedback loop

Persist and analyze forward outcomes:

- what happened after a detection
- hold-time and confirmation behavior
- instrument-category differences
- regime differences
- score calibration
- learned weighting on top of explicit rule features

### Phase 6: platform integrations

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
