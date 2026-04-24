# Project TODO Memory

This file is the persistent deferred-work memory for the charting platform.

Purpose:
- Keep track of work that we explicitly chose to postpone.
- Preserve the surrounding context so a later pass does not lose the rationale.
- Act as the canonical place I should consult when you ask "what is still on the TODO list?"

Maintenance rules:
- When you ask to add something to the TODOs, I should add it here with context.
- When we fully solve one of these items, I should remove it from this file.
- If a TODO meaningfully changes shape, I should update the existing entry instead of duplicating it.
- This file is only for deferred or future work, not for work actively underway in the current turn.
- If another prompt, note, or agent hint disagrees with this file, prefer this file unless the user explicitly says otherwise.

Interpretation rules:
- Treat each entry as deferred work that was explicitly discussed and intentionally postponed.
- Do not use this file for the task currently in progress, vague brainstorming, or already completed work.
- Keep enough context that future sessions can understand why the item exists.
- Prefer updating an existing entry over creating a duplicate if the topic is the same.

Status legend:
- `Deferred`: explicitly postponed for later
- `Planned`: agreed future work that has not started yet

## Deferred TODOs

### 1. Expand test coverage further
Status: `Deferred`

Context:
- We stabilized the broken backend and frontend suites and got them green again.
- Measured coverage is still uneven:
  - backend full-suite coverage is materially improved but still has dark areas
  - frontend lines/statements/branches are strong, but function coverage remains the main weak point

What remains:
- Raise frontend function coverage, especially around:
  - stores
  - composables
  - uPlot plugins
  - chart rendering helpers
- Raise backend coverage in currently under-covered routers/services/providers, especially:
  - dashboard-facing routers
  - watchlist/provider/options routers
  - provider adapters and ingestion-heavy services

Why this was deferred:
- The immediate goal was to first fix broken tests and restore reliability.
- The next coverage push should be targeted, not broad or mechanical.

### 2. Enrich options navigation and contract-history UX
Status: `Deferred`

Context:
- Options contracts are now treated as proper instruments and can be opened in the main chart flow.
- The current options-chain interaction is still functional-but-basic.
- We explicitly agreed to think about deeper options navigation later.

What remains:
- Improve navigation from options chain to contract history.
- Decide whether to add:
  - quick-chart preview
  - split-pane contract chart
  - side drawer / modal inspection
  - better dashboard/widget-side inspection flow
- Make options exploration feel more fluid in both `/chart` and dashboard contexts.

Why this was deferred:
- The current path works, but the UX can be substantially better and deserves a focused design pass.

### 3. Add instrument/asset-type targeting controls for screeners and similar universe consumers
Status: `Deferred`

Context:
- Options contracts can currently participate in broader instrument workflows if present in the DB.
- This is not inherently wrong, but we agreed the platform should let users deliberately decide what kinds of instruments a screener or similar flow should target.

What remains:
- Add explicit include/exclude targeting for instrument classes, such as:
  - equities
  - ETFs
  - indices
  - forex
  - futures
  - options
  - crypto
  - synthetics
- Review whether similar filtering should exist in:
  - screeners
  - search/browse/discovery
  - any other "evaluate many instruments" workflows

Why this was deferred:
- The underlying behavior is acceptable for now, but targeted control is important before the universe grows further.

### 4. Extend provider-side options data support beyond the current baseline
Status: `Deferred`

Context:
- We agreed to squeeze as much practical value as possible out of current providers for options.
- The architecture is ready for full options timeseries.
- Current provider support is still limited in what it can truly deliver historically.

What remains:
- Push option contract OHLCV/history further where current providers allow it.
- Later support true historical timeseries for:
  - bid
  - ask
  - open interest
  - implied volatility
  - greeks
- Keep treating these as time-series data, even when a provider only gives snapshots at specific times.

Why this was deferred:
- The storage and provider-agnostic model came first.
- Richer provider capability work belongs in a dedicated follow-up pass.

### 5. Build a Technical Radar / Level-of-Interest engine with visual evidence
Status: `Deferred`

Context:
- We want the platform to automate a large part of the manual chart-scanning and level-finding work typically done by experienced technical analysts.
- The goal is not merely to label an instrument as "interesting", but to identify instruments approaching technically meaningful areas and explain why they are on the radar.
- The user explicitly wants this to be exhaustive up front: include a broad set of technical ideas and confluence mechanisms now, then later validate and prune what proves useful.
- The user also wants visual transparency: if the radar flags an instrument because of zones, wedges, channels, anchored VWAPs, moving averages, or other structures, the platform should let the user visually inspect those exact internal detections on charts.

What this system should become:
- A broad **Technical Radar** / **Confluence Scanner** that continuously scans a very large instrument universe and produces ranked, evidence-backed technical opportunities.
- A discovery and triage layer that cuts down the human time spent manually scanning charts and searching for near-term technically interesting setups.
- A transparent system where the user can see the underlying technical structures that led to detection, not just an opaque score or alert.

Core product goals:
- Detect instruments approaching technically important price areas.
- Detect instruments interacting with support/resistance structures.
- Detect breakout, breakdown, fakeout, fakedown, reclaim, rejection, and retest behavior.
- Identify confluence between multiple structures and indicators.
- Rank and summarize instruments worthy of being placed on a daily radar/watchlist.
- Present the technical evidence visually so the user can audit and interpret the setup.

What remains:

- Define and implement a broad technical-structure extraction layer, including:
  - horizontal support/resistance zones
  - diagonal trendlines
  - channels
  - wedges
  - triangles
  - prior swing highs/lows
  - weekly/monthly highs and lows
  - opening gaps and gap boundaries
  - AVWAPs anchored to significant technical/contextual events
  - moving-average clusters and moving-average slope/context
  - later, if useful, volume-profile or other structural liquidity/acceptance zones

- Define a broad event-detection layer around those structures, including:
  - approaching resistance
  - approaching support
  - breakout
  - breakdown
  - fakeout
  - fakedown
  - reclaim
  - rejection
  - failed reclaim
  - failed breakdown recovery
  - retest after breakout/breakdown
  - compression / squeeze near a level
  - expansion away from a level

- Define a flexible confluence/scoring layer that can combine evidence such as:
  - zone strength
  - touch count
  - recency of interaction
  - timeframe importance
  - ATR-normalized distance to a level
  - overlap of multiple levels or structures
  - AVWAP / EMA / SMA clustering
  - trend state
  - momentum context
  - relative volume / participation context
  - gap context
  - historical quality of similar setups

- Introduce a persistent radar/setup model that can store things like:
  - instrument
  - timeframe(s) involved
  - detection timestamp
  - setup type
  - score / confidence
  - evidence payload
  - contributing structures
  - invalidation criteria
  - expiry / freshness window
  - later outcome / forward-performance tracking

- Add UI surfaces to visualize the radar results, including:
  - a radar list / widget / scanner-like view
  - setup type and score
  - concise explanation of why the instrument is on the radar
  - distance to key levels
  - timeframe context
  - last detection / freshness info
  - ability to open the setup directly in the main chart

- Add visual evidence rendering on charts, so the user can inspect what the radar detected, including:
  - shaded support/resistance zones
  - trendlines
  - channels / wedges / triangles
  - marked AVWAP anchors and lines
  - EMA/SMA overlays involved in the setup
  - breakout / fakeout / retest markers
  - optionally visibility toggles for each radar evidence type
  - ideally some notion of "radar layer" separate from the user's own drawings

- Make the radar explain itself in human terms rather than just outputting labels, e.g.:
  - setup type
  - score
  - why it matters
  - what structures are involved
  - what timeframe(s) are driving it
  - what would confirm it further
  - what would invalidate it

- Make the radar filterable and rankable in many ways, such as:
  - breakout candidates
  - support-bounce candidates
  - resistance-approach candidates
  - highest-confluence setups
  - recent fakeouts
  - reclaim setups
  - strongest multi-timeframe level clusters

- Add optional validation / research capabilities later, such as:
  - tracking what happened after each detected setup
  - evaluating historical success rates of different definitions
  - instrument-category-specific behavior
  - regime-aware quality differences
  - later, if useful, learned weighting on top of the rule-based engine

Broader feature ideas explicitly worth keeping in scope for future exploration:
- multi-timeframe level stacking and propagation
- relative-strength context versus sector/index/benchmark
- trend-stage classification
- volatility compression / expansion context
- gap-fill probability context
- earnings/event-aware technical context
- market-structure state labeling
- crowding / repeated-level behavior
- zone aging and decay logic
- setup clustering around macro dates or earnings windows
- sector/industry heat around the same type of technical setup
- dashboards or widgets specifically for radar discoveries
- alerts derived from radar state transitions

Visualization expectations:
- Anything used internally by the radar to justify a candidate should, where practical, be visually inspectable by the user.
- The user should not have to blindly trust the radar.
- A detected setup should be explorable on the chart page and, where appropriate, in dashboard widgets.
- Visual overlays should make it easy to distinguish:
  - user-created drawings
  - instrument-linked technical evidence
  - ephemeral radar detections currently active

Suggested implementation philosophy:
- Do not try to perfectly imitate a human analyst in one opaque leap.
- Build a transparent technical-discovery engine that:
  - extracts structures
  - detects events around them
  - scores confluence
  - ranks candidates
  - visualizes its reasoning
- Start broad in scope, then later validate and filter for signal quality instead of prematurely narrowing the concept.

Why this was deferred:
- This is a major platform capability, not a small feature.
- It depends on strong data coverage, careful operational definitions, and good visualization design.
- It deserves a dedicated implementation pass with room for experimentation and later evidence-based pruning.

## Notes

- This file intentionally focuses on postponed work that already came up in discussion.
- It is not meant to replace issue tracking if we later decide to formalize roadmap management elsewhere.
- This is the only file that should be treated as the canonical TODO memory for deferred work in this repo.
