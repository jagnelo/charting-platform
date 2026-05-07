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
  - backend full-suite coverage is materially improved but still has dark areas and currently sits below the normal default minimum coverage expectation
  - frontend lines/statements/branches are strong, but function coverage remains the main weak point
- The backend coverage gate was temporarily lowered so `make test` would stop failing on policy alone while the suite itself is green again.

What remains:
- Raise backend overall coverage back to at least the default `75%` minimum and restore the backend coverage gate accordingly.
- Raise frontend function coverage, especially around:
  - stores
  - composables
  - uPlot plugins
  - chart rendering helpers
- Raise backend coverage in currently under-covered routers/services/providers, especially:
  - core instrument and OHLCV flows
  - dashboard-facing routers
  - watchlist/provider/options routers
  - provider adapters and ingestion-heavy services
  - alerting, screener, sync/task, and background workflow paths
- Add broader integration and end-to-end coverage where unit coverage alone leaves behavioral gaps.

Why this was deferred:
- The immediate goal was to first fix broken tests and restore reliability.
- The next coverage push should be targeted, not broad or mechanical, but it now has a concrete acceptance target: restore the overall default `75%` coverage floor.

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

### 5. Expand the Technical Radar / Level-of-Interest engine beyond the new v1 foundation
Status: `Deferred`

Context:
- We want the platform to automate a large part of the manual chart-scanning and level-finding work typically done by experienced technical analysts.
- The goal is not merely to label an instrument as "interesting", but to identify instruments approaching technically meaningful areas and explain why they are on the radar.
- The user explicitly wants this to be exhaustive up front: include a broad set of technical ideas and confluence mechanisms now, then later validate and prune what proves useful.
- The user also wants visual transparency: if the radar flags an instrument because of zones, wedges, channels, anchored VWAPs, moving averages, or other structures, the platform should let the user visually inspect those exact internal detections on charts.
- A first implementation pass now exists:
  - persisted `radar_run` / `radar_detection` records
  - a synchronous/manual scan trigger
  - a dedicated `/radar` page
  - a non-editable chart-side radar evidence layer separate from saved drawings
  - initial setup types:
    - approaching support
    - approaching resistance
    - breakout
    - breakdown
    - reclaim
    - rejection
  - initial evidence sources:
    - clustered swing-based horizontal zones
    - anchored VWAP from recent pivots
    - EMA context
    - 52-week high/low context
- That v1 should be treated as a foundation, not as the finished expression of the radar vision.

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

- Strengthen the technical-structure extraction layer beyond the current v1 set, including:
  - horizontal support/resistance zones with better width/strength/merge logic
  - diagonal trendlines
  - channels
  - wedges
  - triangles
  - prior swing highs/lows
  - weekly/monthly highs and lows
  - multi-timeframe level propagation
  - opening gaps and gap boundaries
  - richer AVWAP anchor taxonomy tied to significant technical/contextual events
    - recent swing highs and swing lows
    - absolute highs/lows over the loaded history window, and later true all-time high/low anchors when sufficient history exists
    - 52-week high / 52-week low anchors when structurally relevant
    - year-to-date anchors such as YTD open, YTD high, and YTD low
    - major event anchors such as earnings gaps, large breakaway gaps, or other instrument-event timestamps when the provider stack can supply them reliably
    - optional user-auditable "anchor class" metadata so the UI can say not only that an AVWAP matters, but what kind of anchor it came from
  - explicit AVWAP anchor-selection / precedence rules so the engine can choose among multiple plausible anchors on the same symbol without becoming opaque, including:
    - when recent swing anchors outrank broader contextual anchors
    - when broader anchors (ATH/ATL, 52-week, YTD, event anchors) should dominate because they define the active market narrative
    - whether multiple AVWAPs should coexist as parallel evidence rather than forcing a single winner
    - how the chosen AVWAP anchor affects setup scoring versus merely acting as secondary confluence
  - stronger AVWAP provenance and validation, including:
    - storing the chosen AVWAP anchor timestamp and anchor type explicitly in radar evidence
    - chart-side labels/markers for the chosen anchor point
    - unit/integration coverage for obvious anchor-selection cases so the engine remains deterministic as the taxonomy expands
  - moving-average clusters and moving-average slope/context
  - later, if useful, volume-profile or other structural liquidity/acceptance zones

- Strengthen the event-detection layer beyond the current v1 set, including:
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
  - better sequencing rules for first break vs retest vs late continuation
  - clearer confirmation/invalidation state transitions

- Evolve the confluence/scoring layer from the current transparent heuristic blend into a more complete framework that can combine evidence such as:
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
  - forward-tracked outcome quality
  - regime/context-conditioned weighting
  - later, if useful, learned weighting on top of interpretable rule features

- Extend the persistent radar/setup model beyond the current run+detection basics so it can also store:
  - setup state transitions over time
  - whether a setup confirmed, failed, or expired
  - evolving score history instead of only one snapshot
  - grouping/continuity for repeated detections of “the same setup”
  - later outcome / forward-performance tracking

- Expand the UI surfaces beyond the current dedicated `/radar` page, including:
  - a richer radar list / scanner view
  - saved radar filters/views
  - side-by-side comparison of multiple detections
  - setup history / state-transition history
  - dashboard widgets specifically for radar discoveries
  - instrument-specific radar timelines or history views

- Expand visual evidence rendering on charts beyond the current v1 zone/line/marker overlays, including:
  - shaded support/resistance zones
  - trendlines
  - channels / wedges / triangles
  - marked AVWAP anchors and lines
  - EMA/SMA overlays involved in the setup
  - breakout / fakeout / retest markers
  - optionally visibility toggles for each radar evidence type
  - ideally some notion of "radar layer" separate from the user's own drawings
  - clearer provenance / legend for evidence layers
  - grouping/stacking for overlapping detections on one symbol
  - chart-side switching between active and historical detections

- Keep improving the radar’s human-readable explanation layer so it does more than output a label, e.g.:
  - setup type
  - score
  - why it matters
  - what structures are involved
  - what timeframe(s) are driving it
  - what would confirm it further
  - what would invalidate it
  - what specifically made this candidate outrank nearby alternatives
  - which evidence is primary versus merely supporting
  - what changed since the previous detection state

- Expand filter/ranking behavior beyond the current simple setup/symbol/score/freshness controls, such as:
  - breakout candidates
  - support-bounce candidates
  - resistance-approach candidates
  - highest-confluence setups
  - recent fakeouts
  - reclaim setups
  - strongest multi-timeframe level clusters
  - freshest detections
  - most actionable / closest-to-level detections
  - per-sector / per-industry / per-instrument-type slices

- Add stronger validation / research capabilities around the radar, such as:
  - tracking what happened after each detected setup
  - evaluating historical success rates of different definitions
  - instrument-category-specific behavior
  - regime-aware quality differences
  - leaderboard-style comparisons of setup definitions
  - false-positive review tooling
  - later, if useful, learned weighting on top of the rule-based engine

Entry, exit, and invalidation semantics to add (explicitly deferred from v1):
- **Explicit entry level**: v1 detects setups but produces no concrete entry price. Add a per-setup suggested entry level (e.g., zone boundary ± ATR fraction, or first close above/below zone for breakout/reclaim setups). Store as a numeric field alongside key_level_price so the chart and trade-signal layer can use it.
- **Price-action-based auto-invalidation**: `fresh_until` is currently a hardcoded 5-day TTL unrelated to actual price action. Add a background task (or per-scan pass) that checks active detections against the latest bar and marks them `INVALIDATED` (via a new status field or by setting `fresh_until = now`) when the invalidation condition in `invalidation_hint` is met. This requires storing `invalidation_price` as a queryable numeric field (currently only in evidence_json.metrics) and comparing it against incoming closes.
- **Connection to trade signal engine (item 7)**: When item 7 is implemented, radar detections are the natural input — a detection with an entry level, invalidation level, and score becomes the seed for a structured trade plan. The invalidation level becomes the stop, and the implied target can be the opposing zone or a fixed R-multiple. Both systems should share schema vocabulary from the start (entry_price, stop_price, target_price, risk_multiple).

Nearer-term concrete follow-up phases worth treating as the next likely implementation path:
- Phase 2:
  - richer structure extraction
  - scheduled runs
  - saved radar filters/views
  - stronger chart overlay controls
- Phase 3:
  - fakeout/retest/compression state modeling
  - dashboard widgets
  - radar-to-watchlist promotion
  - radar-derived alerts
- Phase 4:
  - historical outcome tracking
  - score calibration
  - strategy/trade-signal integrations

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

Why this was deferred:
- The initial v1 landed, but the original radar vision is much broader than the currently implemented slice.
- The remaining work is still a major platform capability, not a small feature.
- It depends on stronger data coverage, better operational definitions, deeper validation, and richer visualization design.
- It deserves continued dedicated implementation passes with room for experimentation and later evidence-based pruning.

### 6. Build unattended multi-LLM orchestration for overnight development
Status: `Deferred`

Context:
- We discussed a future workflow where Codex and Claude can be used in sequence, with an orchestrator switching between them so platform development can continue unattended for long stretches such as overnight runs.
- The key requirement is continuity: when one worker expires or becomes unavailable, the next one should not have to reconstruct state from scratch or guess where work was left.
- A major constraint identified in the discussion is that nominal session limits are not reliable in practice. A worker may lose usable budget much earlier than expected, sometimes within minutes, which means a single final handoff at the end of a session is not enough.
- To address this, we introduced a repo-owned orchestration model:
  - one canonical orchestration document
  - repo-carried task/state/handoff/report files
  - explicit stop-before-expiry behavior
  - frequent intermediate checkpoints
- We also established the recommended tool direction:
  - use **LangGraph** as the orchestrator
  - treat **Codex CLI** and **Claude Code CLI** as interchangeable workers
  - do not treat the VS Code extensions as the automation surface
  - eventually, if stronger workflow durability is needed, consider adding Temporal underneath later

What this system should become:
- A reliable unattended development workflow that can:
  - read a task queue
  - launch the appropriate worker
  - guide that worker through repo-defined rules
  - validate code and UX changes
  - checkpoint progress frequently
  - rotate workers when one nears exhaustion
  - resume from repo state rather than ephemeral conversation memory
- A neutral orchestration setup that is LLM-agnostic enough for different coding agents to read the same project guidance and obey the same rules.

What remains:

- Build the actual orchestrator around the repository-owned workflow, likely using LangGraph, including:
  - worker selection
  - task loading
  - checkpoint scheduling
  - worker rotation
  - retry behavior
  - failure handling
  - end-of-run reporting

- Ensure the orchestrator treats the following as the single canonical entry point for all workers:
  - `docs/agent-orchestration.md`
- That file should remain the top-level instruction file which then directs workers to the live `ops/*` state files.

- Keep and evolve the repo-owned shared state model, including:
  - `ops/tasks.yaml`
  - `ops/handoff.md`
  - `ops/state.json`
  - `ops/run-report.md`
- These files should be treated as durable continuity memory between workers.

- Preserve and enforce the stop-before-expiry / continuity-first behavior, including:
  - workers must assume usable session budget may collapse early
  - workers must not postpone handoff writing until the end
  - workers must checkpoint during the session after meaningful progress
  - workers must switch into preservation mode if exhaustion risk rises
  - the orchestrator must still impose its own fallback checkpoint/stop rules rather than trusting the worker entirely

- Add orchestrator support for bounded-run / checkpoint behavior, such as:
  - periodic heartbeat prompts
  - periodic checkpoint requests
  - wall-clock soft stop
  - optional max-turn segmentation
  - forcing handoff mode before risky long validations or before likely exhaustion

- Add environment-level support so workers can safely validate the platform end to end, including controlled access to:
  - Docker / Docker Compose
  - Alembic migrations
  - backend/frontend test runners
  - Playwright and browser automation
  - backend and frontend logs
- The preferred future deployment model is a dedicated dev machine or isolated VM for unattended runs rather than exposing a worker to the user's full everyday host environment.

- Prefer an allowlisted-script model for infra control rather than unconstrained shell power where practical, e.g. dedicated scripts for:
  - infra up/down
  - migrations
  - backend tests
  - frontend tests/build
  - E2E flows
  - backend/frontend log collection

- Require unattended workers to validate not only code correctness but actual user-facing behavior when relevant, including:
  - browser interaction flows
  - layout/UX sanity
  - browser console errors
  - backend log errors
  - successful startup/health of the relevant services

- Define the reporting expectations for each unattended run, including:
  - tasks completed
  - tasks partially completed
  - assumptions made
  - blockers found
  - tests run
  - UX validation performed
  - errors encountered
  - exact next step if work remains

- Keep the repo-level agent discoverability in place:
  - root `AGENTS.md` should continue to point to the canonical orchestration doc
  - the canonical doc should remain the first thing an external orchestrator tells any worker to read

Why this was deferred:
- We set up the repository-side memory and rule structure first, but not the actual orchestrator.
- The real value comes from building the supervisor workflow around these rules, which is a separate piece of work from day-to-day platform development.

### 6. Build a Strategy Lab with backtesting, walk-forward testing, and paper forward testing, likely powered by Nautilus Trader as the simulation engine
Status: `Deferred`

Context:
- Right after the Technical Radar / Level-of-Interest initiative, the next major research feature discussed was a strategy research and validation layer: a place where users can define strategies, run historical backtests, compare strategies against one another, and later forward test them in a paper/simulated manner.
- We explicitly discussed avoiding reinvention of the execution/backtesting engine if a mature system can handle that responsibility. Nautilus Trader was identified as a strong candidate because it already provides a serious event-driven backtesting/live-trading architecture, portfolio analytics, options support, and custom data capabilities.
- The agreed architectural direction is not to turn this platform into a thin wrapper around Nautilus Trader, but rather to keep this platform as the research/product/orchestration layer while treating Nautilus as a worker/simulation engine behind a provider-agnostic and platform-owned data model.
- The platform must remain the source of truth for:
  - canonical instruments and identifiers
  - watchlists, screeners, radar results, and user-defined universes
  - strategy definitions and versions
  - run configurations
  - stored backtest / forward-test results
  - analytics, comparisons, dashboards, and UI
- The external simulation engine should be treated as replaceable infrastructure. Even if Nautilus Trader becomes the first engine, the platform should not become tightly coupled to Nautilus-specific assumptions any more than it is coupled to any single data provider.

What this system should become:
- A broad **Strategy Lab** / **Research Lab** that allows users to:
  - define strategies ranging from simple rules to complex multi-instrument systems
  - run historical backtests over one instrument or a custom-selected instrument universe
  - run walk-forward and out-of-sample tests
  - compare strategies against one another
  - analyze risk, return, drawdown, robustness, correlation, and diversification characteristics
  - later, run simulated forward tests on freshly arriving data
- A persistent research environment where the platform can answer questions such as:
  - "How would this strategy have performed on this watchlist?"
  - "How does this strategy compare to another one over the same universe and date range?"
  - "Which strategies are the least correlated, so I can combine them in a portfolio?"
  - "How does performance differ by instrument category, market regime, or technical context?"

Guiding architectural principles:
- Keep the platform's internal domain model authoritative and provider-agnostic.
- Treat the simulation engine as an implementation detail hidden behind a strategy-execution abstraction layer.
- Persist everything that matters:
  - strategy definitions
  - strategy versions
  - strategy parameter sets
  - test configurations
  - run artifacts
  - trade/fill logs
  - equity curves
  - portfolio curves
  - aggregate metrics
  - correlations
  - attribution
  - robustness results
- Keep strategy-research workflows compatible with other platform features, especially:
  - watchlists
  - screener outputs
  - Technical Radar candidate lists
  - instrument universes defined manually or dynamically
- Support a future in which another engine or custom executor could sit behind the same platform-owned orchestration interfaces.

What remains:

- Design and implement a platform-owned strategy domain model, including concepts such as:
  - strategy definition
  - strategy version
  - parameter schema
  - parameter set
  - run configuration
  - selected universe
  - benchmark configuration
  - test mode
  - execution assumptions
  - run result summary
  - detailed run artifacts

- Define clear test modes and make them first-class, including:
  - standard historical backtest
  - walk-forward / rolling out-of-sample testing
  - parameter sweep / optimization batches
  - robustness testing
  - paper forward testing on newly arriving data
  - eventually, if ever needed, live execution mode as a separate concern and not something entangled into the initial research architecture

- Introduce a strategy-execution abstraction layer in the backend so the platform can submit a run without caring whether the underlying engine is Nautilus Trader or something else, including:
  - engine registration / engine type
  - engine capabilities
  - engine job submission
  - engine run status tracking
  - engine artifact retrieval
  - engine error reporting
  - engine versioning / compatibility metadata

- Build a dedicated Nautilus Trader integration layer as the likely first implementation, including:
  - mapping our canonical instruments to Nautilus instrument representations
  - exporting our persisted market data into Nautilus-compatible input formats
  - handling data catalog generation if needed
  - converting our stored bars / quotes / options data / custom events into Nautilus-readable datasets
  - collecting Nautilus results and translating them back into platform-owned result schemas
  - insulating the rest of the platform from Nautilus-specific symbols, IDs, config conventions, and storage assumptions

- Be very careful around instrument identity and symbology:
  - Nautilus has its own instrument identity conventions
  - our platform already has a provider-agnostic canonical identity model
  - the strategy system must use the platform's canonical identity everywhere user-facing or persistent
  - any Nautilus-specific mapping should live only in the adapter/integration layer
  - this is especially important for:
    - international equities
    - indices
    - futures
    - options contracts
    - synthetic / expression instruments, if they ever become relevant to strategy testing

- Build a research-universe selection layer tightly integrated with the rest of the platform, so a strategy run can target:
  - a single instrument
  - a manual selection of instruments
  - a watchlist
  - screener results
  - radar-discovered instruments
  - later, dynamic universes refreshed by scheduled rules

- Build a strategy-definition layer that can support multiple levels of user sophistication:
  - a visual rule builder for simpler strategies
  - a declarative intermediate schema or DSL for more expressive strategies
  - fully coded strategies for advanced users
- The platform should not force all users into raw engine code if they only want rule-based or parameterized strategies.
- The visual/declarative path should likely be platform-native and later compiled/transformed into an executable representation for the simulation engine.

- Support strategies with a wide range of possible logic, not just simple single-instrument trend following, including eventually:
  - indicator-driven entry/exit logic
  - price-action and pattern conditions
  - multi-timeframe conditions
  - universe-level filtering
  - ranking / top-N selection
  - volatility or liquidity filters
  - event-aware logic
  - options-aware logic if/when supported well enough
  - pair or relative-strength logic
  - portfolio-level allocation and rebalancing rules

- Model execution assumptions and market-friction settings explicitly, including:
  - bar-based vs richer-data assumptions
  - slippage models
  - commissions / fees
  - spread assumptions
  - latency assumptions where meaningful
  - fill models
  - venue/exchange awareness
  - position sizing models
  - leverage / margin assumptions
  - portfolio constraints
- These assumptions must be visible in run configs and persisted as part of the provenance of any run result.

- Build a data-preparation/export layer from the platform's DB to the simulation engine, including:
  - selecting the required historical window
  - selecting the required instruments / contracts
  - selecting the required timeframes
  - selecting supporting event/custom data
  - enforcing data coverage checks
  - documenting missing/stale data before or during a run
  - exporting data in a reusable cached form when possible
- This layer must be very mindful of:
  - data completeness
  - timeframe alignment
  - corporate actions / adjusted vs unadjusted series
  - options chain snapshots vs timeseries
  - future support for richer quote-level or tick-level data

- Treat result persistence as a first-class system rather than ephemeral output, storing at minimum:
  - run metadata
  - strategy version used
  - parameter set used
  - date range
  - selected universe
  - benchmark used
  - execution assumptions
  - engine used
  - run status
  - error logs / warnings
  - trade list
  - order/fill history
  - position history
  - equity curve
  - drawdown curve
  - exposure history
  - per-instrument contribution / attribution
  - summary metrics
  - artifacts generated by the engine

- Build a rich result-analytics layer on top of those stored results, including:
  - total return
  - annualized return
  - volatility
  - Sharpe / Sortino and similar ratios
  - drawdown metrics
  - win/loss metrics
  - expectancy
  - turnover
  - exposure metrics
  - per-instrument attribution
  - sector/category attribution where possible
  - benchmark-relative performance
  - rolling performance windows
  - regime breakdowns
  - trade distribution analytics

- Build explicit strategy-comparison tooling, including:
  - compare two or more strategy runs side-by-side
  - compare multiple parameterizations of the same strategy
  - compare strategies over the same universe/date range
  - compare strategies by regime
  - correlation matrix of strategy returns
  - covariance/diversification analysis
  - portfolio-construction ideas such as combining less-correlated strategies
  - ranking by robustness instead of raw total return alone

- Support walk-forward / out-of-sample research directly rather than treating it as an afterthought, including:
  - segmented train/test windows
  - rolling calibration windows
  - rolling evaluation windows
  - parameter freeze vs periodic retuning behavior
  - aggregated walk-forward summaries
  - per-window stability views
  - degradation / drift diagnostics

- Add robustness-testing ideas that are valuable even before any machine-learning layer, including:
  - parameter sweeps
  - sensitivity analysis
  - Monte Carlo reshuffling where appropriate
  - start-date robustness
  - universe robustness
  - timeframe robustness
  - cost/slippage stress tests
  - data-delay / execution-delay stress assumptions
- The goal should be to separate "looks great on one chart" from "survives perturbation."

- Define what forward testing means in the platform and make it explicit that there are two distinct ideas:
  - walk-forward testing over historical data
  - paper forward testing on newly arriving data in simulated mode
- Later paper forward testing should reuse the same strategy definition and, where possible, the same simulation semantics as backtests, while operating on fresh platform-ingested data.

- Build a paper forward-testing mode that can eventually:
  - subscribe to selected active strategies
  - run on newly arriving bars/quotes/events
  - maintain paper positions and paper P&L
  - track divergence versus historical expectations
  - expose current paper state in the UI
  - alert when a strategy's current behavior meaningfully deviates from historical norms or risk thresholds

- Add frontend surfaces for the Strategy Lab, including:
  - strategy list / catalog
  - create/edit strategy view
  - strategy version history
  - run-configuration form
  - universe picker
  - backtest run history
  - walk-forward results view
  - strategy comparison view
  - portfolio-of-strategies comparison view
  - paper forward-testing monitor

- Add rich visualizations, such as:
  - equity curves
  - underwater/drawdown charts
  - rolling Sharpe / rolling return charts
  - trade distribution histograms
  - heatmaps by month/week/regime
  - parameter sweep heatmaps
  - correlation matrices between strategies
  - contribution / attribution charts
  - benchmark overlays
  - trade markers on the main chart where appropriate

- Tie the Strategy Lab into the rest of the platform where it makes sense, especially:
  - run a strategy against a watchlist directly
  - run a strategy against screener results
  - later run a strategy against Technical Radar candidate lists
  - allow chart/radar discoveries to feed directly into strategy research
  - eventually compare "radar-guided" strategies versus plain universe strategies

- Make this system compatible with options and more complex instruments over time, but stage expectations carefully:
  - initial strategy work may begin with bar-based underlying instruments
  - later support options strategies as data quality and engine capability allow
  - keep the architecture broad enough for multi-leg options and derivatives research later, even if not all of it is implemented immediately
- This point is especially important because the platform is already becoming more options-aware and the strategy system should not corner itself into equities-only assumptions.

- Add scheduling/orchestration support eventually, including:
  - queued backtest jobs
  - asynchronous run execution
  - batch research jobs
  - periodic re-runs when fresh data arrives
  - retention rules for large artifacts
  - cancellation / pause / retry semantics

- Track provenance and reproducibility very carefully:
  - which strategy version was used
  - which engine version was used
  - which data snapshot/coverage state was used
  - which assumptions were used
  - which benchmarks/universe definitions were used
  - which parameters were used
- A historical run should be reconstructable later as faithfully as practical.

- Be mindful of realistic limitations and caveats, especially if Nautilus Trader is used:
  - engine/library evolution and possible breaking changes
  - symbol and identity mismatch between the platform and Nautilus
  - data-realism limits when only bar data exists
  - richer realism only becoming available once richer quote/order-book data exists
  - licensing/commercialization implications that should be revisited before public productization

Broader feature ideas explicitly worth keeping in scope for future exploration:
- strategy templates and starter packs
- library of common technical/systematic strategy archetypes
- import/export of strategy definitions
- collaborative comparison of multiple strategies or parameter families
- scorecards for robustness vs overfitting risk
- regime-aware strategy ranking
- combination/ensemble strategies
- benchmark families beyond simple buy-and-hold
- strategy tagging and taxonomy
- automated reporting / PDF or shareable summaries
- linking strategy events back onto the chart page visually
- linking forward-tested active strategy state into dashboards
- using platform events, radar detections, or custom factor series as strategy inputs

Phasing expectations:
- Phase 1 should likely focus on:
  - backend abstraction for strategy engines
  - Nautilus Trader as the first engine implementation
  - platform-owned run configs and persisted results
  - bar-based historical backtesting
  - single-instrument and small-universe support
  - basic comparison analytics
- Phase 2 should likely add:
  - richer strategy-definition UX
  - parameter sweeps
  - walk-forward testing
  - stronger comparison and robustness tooling
- Phase 3 should likely add:
  - paper forward testing on new incoming data
  - better monitoring and alerting
  - tighter integration with radar/screener/watchlist workflows
- Later phases can expand toward:
  - richer data realism
  - advanced options strategies
  - more sophisticated portfolio construction
  - engine pluralism beyond Nautilus if needed

Interpretation expectations for future work:
- This should be treated as a major platform initiative, not a small feature.
- The platform should own the research workflow and user experience, even if Nautilus owns the underlying simulation semantics.
- The intent is not merely "add a backtest button", but to build a full strategy research environment that complements the Technical Radar and the broader analytics direction of the product.
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

### 7. Build a Trade Signal, Virtual Trade Tracking, and Trader-Follower engine
Status: `Deferred`

Context:
- After discussing the Technical Radar and the Strategy Lab, we explored whether a full auto-trading layer should sit on top of them.
- The agreed conclusion was that full live auto-execution is a natural long-term extension, but not the right first step.
- The better intermediate product is a **trade signal generator plus virtual trade lifecycle tracker**:
  - the platform identifies a trade idea,
  - alerts the user,
  - defines and tracks the hypothetical trade in the background,
  - continues issuing alerts for entries, stop movement, partial exits, take profits, invalidations, and final exits,
  - while collecting forward-tested performance data as if the trade had been followed systematically.
- This gives most of the research and discipline benefits of automation without immediately taking on broker integration, live order routing, or full auto-trading risk.

What this system should become:
- A **Trade Signal & Lifecycle Engine** that turns strategy/radar detections into structured trade plans.
- A **manual-execution companion** for users: the user places the trade themselves, while the platform tracks the plan and keeps monitoring it.
- A **forward-testing layer** that measures how well the platform’s ideas and trade-management rules actually perform in live-market conditions over time.
- A **bridge layer** between:
  - Technical Radar candidate discovery
  - Strategy Lab research/backtesting
  - later paper trading
  - and eventually, if desired, semi-automated or fully automated execution

Core product goals:
- Generate structured trade idea alerts from technical/rule-based detections.
- Represent a full trade plan rather than only an entry alert.
- Track hypothetical trades continuously in the background after signal creation.
- Alert users when the trade transitions through important lifecycle states.
- Measure live forward-tested trade outcomes to validate setups and trade-management logic.
- Provide a disciplined, auditable trade journal even when execution is still manual.

What remains:
- Define the **signal-to-trade-plan transformation layer**, including:
  - how a Technical Radar setup or Strategy Lab rule becomes a candidate trade
  - entry model types, such as:
    - immediate market-style entry at signal
    - breakout trigger entry
    - pullback/retest entry
    - support-bounce style entry
    - reclaim/recovery entry
    - limit-style or zone-based entry logic
  - directional context:
    - long
    - short
    - both where appropriate
  - validity windows for entries:
    - same-session only
    - N bars only
    - expires if level already moved too far
    - expires on structure invalidation

- Define a persistent **trade plan model**, capturing things like:
  - instrument
  - signal source
  - source setup id / strategy run id / radar detection id
  - side (long/short)
  - entry logic
  - entry zone or entry trigger
  - stop loss
  - one or more profit targets
  - optional partial-take-profit structure
  - optional trailing-stop logic
  - invalidation logic
  - creation time
  - expiry time / entry validity window
  - current lifecycle status
  - notes / rationale / evidence payload
  - provenance of how the trade was derived

- Define the **virtual trade lifecycle state machine**, including statuses such as:
  - proposed
  - alerted
  - entry pending
  - entered
  - partially exited
  - trailing / management active
  - stopped out
  - target hit
  - fully exited
  - invalidated before entry
  - expired before entry
  - cancelled
  - manually overridden / user-dismissed

- Define the **trade-monitoring engine** that continuously evaluates open or pending trade plans against incoming data, including:
  - entry-trigger monitoring
  - stop-hit detection
  - target-hit detection
  - partial-target-hit detection
  - trailing-stop adjustment logic
  - break-even transition logic
  - time-based invalidation or forced exit logic
  - setup-quality decay / “setup no longer valid” logic
  - session or event-aware logic if relevant later

- Add a broad **alert-generation layer** around trade lifecycle events, including:
  - new trade setup generated
  - entry triggered
  - entry missed / expired
  - stop loss hit
  - take-profit level reached
  - partial exit reached
  - stop moved to break-even
  - trailing stop updated
  - trade invalidated
  - final exit completed
  - outcome summary alert / notification

- Define how the engine handles **pricing and hypothetical fills**, including:
  - whether fills are assumed on touch, close, or open of next bar
  - whether intrabar hit sequencing matters when stop and target are both touched
  - how gaps are handled
  - how slippage assumptions are represented
  - how fills differ across timeframes and data quality levels
  - how assumptions remain visible and auditable to users

- Add a persistent **virtual trade / forward-test ledger**, storing:
  - original trade plan
  - all lifecycle transitions
  - timestamps of each transition
  - hypothetical fills
  - realized and unrealized P&L
  - MFE / MAE
  - risk multiple (R)
  - duration in bars and wall-clock time
  - target sequence reached
  - reason for exit
  - whether the trade was user-followed or only platform-tracked
  - optional user annotation about whether the human actually took the trade

- Build a **trade journal / follower UI layer**, including:
  - list of active trade ideas
  - list of pending entries
  - list of active virtual trades
  - completed trades
  - outcome and statistics views
  - filtering by source, setup type, instrument, timeframe, side, and status
  - trade detail pages or panels showing:
    - the original setup rationale
    - planned entry/stop/targets
    - lifecycle history
    - current state
    - forward-tested performance

- Add chart-side visualization for the entire trade plan and lifecycle, including:
  - entry line / zone
  - stop line
  - target lines
  - partial target markers
  - trailing stop path if active
  - entry trigger marker
  - exit markers
  - invalidation marker
  - trade-state overlays or labels
  - ability to distinguish radar evidence from trade-plan overlays

- Tie this system to the rest of the platform so trade ideas can originate from:
  - Technical Radar detections
  - Strategy Lab forward-tested strategies
  - manually promoted user-selected chart setups
  - later screener outputs or other analytics engines

- Add **forward-testing analytics** so the platform can answer questions like:
  - which setup types generate the best live-tracked outcomes?
  - which entry models are most robust?
  - how often do trade ideas reach TP1, TP2, or stop first?
  - how often are signals invalidated before entry?
  - how does forward-tested outcome compare with historical backtest expectation?
  - which instruments, sectors, or regimes respond best to the engine’s trade ideas?

- Add a **portfolio / batch view** of live tracked trade ideas, including:
  - active trade count
  - net long/short bias
  - total hypothetical risk exposure
  - clustering by sector/industry/theme
  - overlapping setup concentration
  - strategy-source concentration
  - calendar/event exposure overlap

- Add user-control concepts around manual-following behavior, such as:
  - mark trade as “taken” or “ignored”
  - mark trade as “follow partially” or “watch only”
  - compare platform-tracked trade plan against actual user execution later if desired
  - allow the user to dismiss or pause certain signal sources

- Later, optionally extend this into progressively more automated layers, such as:
  - paper-trading execution simulation using the same trade plans
  - semi-automated “confirm before send” broker actions
  - eventually, full auto-execution for validated strategy subsets

Research and modeling expectations:
- Keep this initially focused on **signals plus virtual lifecycle tracking**, not true live broker automation.
- Treat all fills and outcomes as model-based and explicitly assumption-dependent.
- Ensure every tracked trade is transparent:
  - where it came from
  - why it exists
  - what rules govern it
  - how outcomes were computed

Broader feature ideas explicitly worth keeping in scope for future exploration:
- signal ranking by live forward-tested quality rather than only historical backtest quality
- user-configurable trade templates per setup type
- trade idea confidence intervals or quality bands
- regime-aware trade-plan templates
- sector / basket follower signals
- options-specific trade-following later
- multi-leg / scaling-in / scaling-out logic later
- correlation-aware throttling of simultaneous ideas
- event-aware pause logic around earnings or macro events
- strategy-vs-radar blended signal sources
- dashboard widgets for active trade ideas and tracked outcomes

Why this was deferred:
- It is a substantial subsystem in its own right and depends conceptually on the Technical Radar and Strategy Lab being better defined first.
- It is the safest and most useful intermediate step before any future broker-linked automation.
- It deserves a focused design and data-model pass rather than being smuggled in piecemeal under “alerts” or “paper trading.”

### 8. Activate paid providers for options data and forward earnings estimates
Status: `Planned`

Context:
- The platform now has a full free-provider stack (Alpaca, FRED, Binance, CoinGecko, EDGAR)
  covering US equity OHLCV, crypto, corporate actions, rates, and historical earnings.
- The following data types have no viable free alternative and are currently covered only by
  yfinance (unofficial, no SLA):
  - **US options chains with real greeks** — delta, gamma, theta, vega
  - **Forward earnings calendar** — upcoming confirmed/estimated earnings dates
  - **Analyst price targets and recommendations**

Low-budget candidates already anticipated in config.py (keys are present, providers not yet built):
- `MARKETDATA_API_KEY` → MarketData.app ($25/month) — US options with real greeks + earnings calendar
- `FMP_API_KEY` → Financial Modeling Prep ($15/month) — forward estimates, analyst data, richer fundamentals
- IBKR TWS API (free with account) — comprehensive US + international options, futures, real greeks;
  requires IB Gateway sidecar process and a throttled scheduler due to IBKR pacing limits

What remains:
- Implement `marketdata` provider (MarketData.app): `OptionChainProvider` with real greeks,
  `EventProvider` for earnings calendar
- Implement `fmp` provider (FMP): `EventProvider` for forward earnings + analyst data,
  `InstrumentMetadataProvider` for richer fundamentals
- Optionally implement `ibkr` provider (IBKR TWS): comprehensive coverage for priority instruments,
  requires IB Gateway sidecar and a pacing-aware scheduler queue
- Demote yfinance options/events capabilities to last-resort once paid providers are active

Why this was deferred:
- The free provider stack covers the high-volume refresh use case well.
- Options and forward estimates require a budget commitment; the user will decide when to activate.

### 9. Expand provider chain seeding and scheduling for bulk universe refresh
Status: `Planned`

Context:
- Five new providers (Alpaca, FRED, Binance, CoinGecko, EDGAR) are registered but the
  PROVIDER_CHAIN_SEEDS defaults in config.py are still empty `{}`.
- The scheduler tasks (instrument_sync_tasks, data_tasks) are not yet wired to use the new
  providers in an ordered way for daily refresh cycles.

What remains:
- Set production-ready `PROVIDER_CHAIN_SEEDS` defaults per capability so new providers
  are automatically preferred over yfinance without manual env override.
- Review `INSTRUMENT_DAILY_METADATA_CAP` and `INSTRUMENT_DAILY_IDENTIFIER_CAP` — these
  may need tuning when Alpaca-discovered universe (~9 000 equities) is active.
- Add a scheduled daily task for Alpaca OHLCV batch refresh (leveraging the multi-symbol
  endpoint to refresh thousands of equities in ~10–15 requests).
- Add a scheduled task for corporate actions sync (Alpaca splits/dividends).
- Add a scheduled task for EDGAR earnings history enrichment for newly added instruments.

Why this was deferred:
- The providers are implemented and registered; wiring the scheduler is a separate operational
  concern that should be done alongside end-to-end testing of the new provider stack.

### 10. Custom instrument baskets, ETF holdings navigation, and breadth analysis
Status: `Planned`

Context:
- The platform already supports individual instruments and expression-based synthetics (e.g., `=SPY-QQQ`).
- The next natural building block is **user-defined instrument baskets**: named, weighted collections of instruments that can be treated as a first-class platform object, similar to a custom ETF.
- Beyond pure user-defined baskets, real ETFs carry composition data — the platform should eventually be able to materialise an ETF's holdings as a basket automatically, enabling holdings navigation ("show me all Nasdaq 100 constituents").
- Once baskets exist as objects, they become a natural surface for **breadth analysis**: computing aggregate technical properties across holdings to get a collective health view of the basket as a whole.
- These three concerns — basket construction, ETF holdings navigation, and breadth analysis — are closely coupled and should share a common data model from the start.

---

#### 10a. Custom basket construction

What this should become:
- A named, user-owned collection of instruments with associated weights.
- Weights can be equal (platform distributes 1/N automatically) or fully custom (user assigns fractions that must sum to 1.0, or raw market-value notional if the UX calls for it).
- A basket can be used anywhere an instrument is referenced: charted as a synthetic price series (using the weighted sum or index-relative formula), added to a watchlist, used as a screener universe, used as a breadth analysis target, or used as a Strategy Lab universe.
- Baskets are distinct from expression instruments (`=A-B`, `=A/B`) which are formula-based rather than weighted-membership-based.

What remains:

Backend:
- Introduce a `basket` domain model, storing: id, user_id, name, description, created_at, updated_at, rebalance_frequency (if the platform ever supports periodic rebalancing semantics), weighting_scheme (equal / custom / market_cap_weighted), and optionally a `classification_mode` (auto / manual).
- Introduce a `basket_member` model, storing: basket_id, instrument_id, weight (decimal, nullable when scheme=equal), and an optional notes/label field per member.
- Introduce basket CRUD endpoints: create, rename, update description, add/remove/reweight members, delete.
- Add a basket-as-instrument synthetic OHLCV path: given a basket with weights and member OHLCV histories, compute the basket's price series on demand so it can be charted like any other instrument. Start with a rebased-to-100 cumulative return series as the simplest viable option.

Frontend:
- A basket builder UI: create/name, add instruments (via the existing search flow), assign weights or leave equal, confirm.
- Weight editor: show all members, allow dragging or typing weights, show a real-time "remaining" allocation indicator, validate sum=1.
- Basket detail view: list all members, their weight, and a sparkline or mini-stat row per member.
- Ability to open a basket in the chart view as a synthetic price series.
- Basket list view accessible from the sidebar.

---

#### 10b. Basket sector / industry classification

Context:
- If every member of a basket shares the same GICS sector (or industry), the basket clearly belongs to that sector/industry and can be classified automatically.
- When members span multiple sectors/industries, automatic classification breaks down. The right answer here is not fully settled:
  - One option is a user-selectable custom label from a predefined list (including a catch-all like "Multi-sector" or "Thematic").
  - Another option is a tag system where the basket carries multiple sector/theme tags.
  - A third option is purely user-free-text labeling.
  - Which of these is best depends on how the classification is used downstream (breadth grouping, screener filtering, radar slicing). This should be revisited once the downstream use cases are clearer.

What remains:
- Add a `sector` and `industry` field to the basket model, nullable.
- On basket creation/save, run an auto-classification pass: if all members share the same GICS sector, populate the field automatically. If they share the same industry sub-sector, populate industry as well.
- If members are mixed-sector, leave classification null and surface a prompt in the UI inviting the user to set a custom classification label.
- Build a lightweight classification UX: a picker or text field that offers predefined sector names plus a free-text "Thematic / Custom" escape hatch.
- Revisit and expand this once the breadth analysis feature (10c) and radar filter/slice feature (item 5) make it clear what the classification taxonomy needs to look like.

---

#### 10c. ETF holdings navigation and auto-materialised baskets

Context:
- Real ETFs are instruments in the platform's DB. Their holdings are composition data that can be sourced from providers (e.g., ETF.com, iShares disclosures, State Street, or financial data providers that expose holdings).
- Once ETF holdings data exists in the platform, an ETF can be treated as a system-managed basket automatically: the platform creates or refreshes a basket representing the ETF's current composition and weights.
- This enables: "click SPY, see all 503 holdings and their weights". Or: "click QQQ, open all Nasdaq 100 constituents as a basket and then chart any one of them".
- The holdings-navigation flow is especially valuable for users who want to do their own constituent-level research: e.g., scan through all S&P 500 members to find technically interesting setups, or look at which Nasdaq 100 members are near 52-week highs.

What remains:

Data / provider side:
- Identify and integrate a provider for ETF holdings data. Candidates include Financial Modeling Prep (FMP), ETF.com, or a dedicated ETF holdings API. The provider should supply: constituent symbol, weight, and ideally shares held and market value per member.
- Introduce a scheduled refresh task that updates ETF holdings on a configurable cadence (daily or weekly is likely sufficient for non-leveraged index funds).
- Model ETF holdings as a special case of basket: a system-managed basket with a reference to the source ETF instrument, a composition_date field, and a flag distinguishing user-owned baskets from ETF-derived baskets.

Backend:
- ETF-derived baskets should be read-only from the user's perspective (no user-editable weights).
- Provide an endpoint to list/search ETFs that have holdings data available.
- Provide an endpoint to retrieve the holdings basket for a given ETF instrument.
- Provide an endpoint for the holdings navigation flow: given an ETF instrument id, return the full member list with weights, instrument details, and optional mini-stats per member.

Frontend:
- On the chart page, when viewing an ETF, surface a "Holdings" tab or panel showing the basket composition.
- From the holdings panel, each member instrument should be clickable to open that instrument's chart.
- A "Browse all constituents" mode: a paginated/scrollable table of all members with mini-stats (price, change, distance to 52w high, etc.) with click-through to each instrument's chart.
- The holdings panel should make it easy to open multiple instruments in sequence (e.g., step through constituents one by one) for manual scanning.
- Later, a "chart all" or "compare all" shortcut that opens a screener-results-like view filtered to the ETF's holdings.

---

#### 10d. Breadth analysis over baskets and ETFs

Context:
- Once baskets exist and their member OHLCV histories are queryable, the platform can compute aggregate technical properties across the membership and surface a collective health view.
- Breadth analysis answers questions like: "What percentage of S&P 500 members are above their 200-day EMA right now?" or "How many Nasdaq 100 stocks are within 5% of their 52-week high?" or "What's the average distance to the 50-day SMA across this basket?".
- This kind of analysis is a tool used by technical macro analysts to evaluate whether a broad market move is being driven by wide participation or narrow concentration.
- The feature should be general enough to work on any user-defined basket or ETF-derived basket, not just major US indices.

What remains:

Computation engine:
- Define a set of per-member breadth metrics to compute, including (but not limited to):
  - percentage of members above their 20/50/100/200-day SMA or EMA
  - percentage of members within N% of their 52-week high or low
  - average distance (in % or ATR multiples) from a given EMA/SMA across members
  - percentage of members with recent volume above their N-day average
  - percentage of members in uptrend vs downtrend by a chosen definition (e.g., above 200 EMA = uptrend)
  - percentage of members making new N-day highs or lows
  - percentage of members above a user-specified price level or within a zone
- Implement a backend breadth computation service that takes a basket id, a reference date, and a set of requested metrics and returns a breadth snapshot.
- Optionally persist historical breadth snapshots so the platform can show a breadth indicator time series (e.g., "% above 200 EMA over the last 12 months") rather than only the current snapshot.

Frontend:
- A basket breadth panel / dashboard widget that shows a summary of current breadth metrics for a selected basket or ETF.
- A breadth chart: a time series showing how a selected breadth metric has evolved over time (e.g., a McClellan-oscillator-style view of participation).
- A drill-down from the breadth summary: click "38% of members are above 200 EMA" to see the list of which members are above vs below, sortable/filterable.
- A comparison view: show breadth for multiple baskets side by side (e.g., compare S&P 500 breadth vs Nasdaq 100 breadth vs a user-defined sector basket).
- Later: dashboard widgets specifically for basket breadth, so users can pin a breadth indicator to their main dashboard.

---

#### Shared design principles across 10a–10d

- **Baskets are first-class objects.** They are not just lists; they carry weights, metadata, classification, and a potential synthetic price series. The domain model should reflect this from the start.
- **ETF-derived baskets are a special case of the same model.** User baskets and ETF holdings baskets share the same backend schema and frontend surfaces; the distinction is managed vs unmanaged ownership and refresh semantics.
- **The basket model feeds other platform features.** Baskets should be usable as: chart synthetic instruments, screener universes (item 3), Strategy Lab universes (item 6/7), radar filter slices (item 5), and breadth analysis targets. These integrations should inform the basket schema design so it isn't retrofitted later.
- **Breadth analysis should be additive, not a re-architecture.** The breadth engine reads member OHLCV histories that already exist in the platform. It does not require new data infrastructure, only a computation layer on top of existing data.
- **Sector/industry classification for mixed baskets remains an open design question.** The taxonomy used for classification should be revisited once downstream use cases (breadth grouping, radar slicing) clarify what granularity is actually needed.

Phasing expectations:
- Phase 1: Custom basket creation/editing with equal and custom weights, basket charted as a synthetic price series, basic basket list/detail UI.
- Phase 2: ETF holdings data ingestion, ETF-as-basket materialisation, holdings navigation UI.
- Phase 3: Breadth analysis engine, breadth snapshot views, breadth time-series charting.
- Phase 4: Basket breadth dashboard widgets, cross-basket comparison views, integration with radar and screener universe selectors.

Why this was deferred:
- Baskets are a foundational building block but depend on having a stable instrument model (already done) and clear downstream consumers.
- ETF holdings data requires a dedicated provider integration.
- Breadth analysis depends on both basket membership and historical OHLCV coverage being in good shape.
- The right design for mixed-sector basket classification needs more downstream context before being finalised.

### 11. Build a platform-wide OHLCV coverage, freshness, and acquisition orchestration layer
Status: `Planned`

Context:
- The platform now has several different price-data consumers, but they do not all behave consistently:
  - chart OHLCV routes are read-through and may fetch/backfill on demand
  - first-time instrument discovery can enqueue broad history fetches in the background
  - indicator alerts currently fetch OHLCV on demand before evaluating
  - `run_screener` is DB-only
  - `stream_screener` is hybrid: DB-first, then fetches for instruments with no cached bars
  - radar is currently DB-only
  - nightly refresh and bulk-fetch flows explicitly seed or refresh OHLCV ahead of time
- This inconsistency is manageable while the platform is small, but it becomes increasingly dangerous as more evaluators come online.
- We explicitly want to preserve three platform rules:
  - external providers should only be contacted when there is strong evidence that the DB is missing required data or has gone stale enough to invalidate the use case
  - when data is missing, the platform should fetch only the missing slice, not an arbitrarily broad range
  - any mechanism that issues factual, price-based outcomes (alerts, screener matches, radar detections, future breadth or signal outputs) must not silently evaluate on stale or incomplete data
- This future item is about making those rules concrete and enforceable across the whole platform, not just inside one feature.

Why this deserves a dedicated roadmap item:
- This is not only a radar concern. It directly affects:
  - chart OHLCV loading
  - instrument detail widgets derived from OHLCV
  - screeners
  - indicator alerts
  - radar scans
  - breadth analysis over baskets and ETFs
  - future signal/trade-plan engines
  - future strategy or validation workflows that depend on OHLCV readiness
- If each subsystem keeps inventing its own "fetch if missing", "fresh enough", or "latest bars" logic, the platform will drift into multiple incompatible truth models:
  - one feature may skip an instrument because the DB is cold
  - another may fetch a fresh tail and produce a different answer
  - another may operate on stale bars and produce an answer that is factually out of date
- A shared orchestration layer is the cleanest way to preserve:
  - deterministic evaluation behavior
  - low provider dependency
  - bounded provider spending/quota usage
  - eventual consistency with market reality

Desired global policy:
- Split OHLCV consumers into three explicit classes and apply different rules to each.

#### 11a. Interactive, user-driven data views

Examples:
- chart OHLCV requests
- transformed-bar chart requests
- historical pagination while the user pans left on a chart
- instrument detail views that need one symbol's recent OHLCV-derived metrics
- later, narrow single-symbol analytical views

Policy:
- allow narrow read-through fetch/backfill
- allow on-demand repair of the exact requested historical slice
- allow limited freshness repair of the exact latest window needed for the request
- still route these through a shared coordinator so provider throttling and missing-slice logic remain centralized

Reason:
- the user explicitly requested a narrow unit of data
- read-through behavior is acceptable here because it is scoped, intentional, and observable

#### 11b. Broad evaluators / decision engines

Examples:
- radar scans
- scheduled screeners
- screener-alert post-processing
- indicator alerts
- future breadth snapshots
- future trade-signal engines
- future strategy/lifecycle engines that consume price-derived signals

Policy:
- do not let these flows perform ad hoc provider fetches inside the actual evaluation loop
- evaluate from DB-backed data only
- if data freshness/completeness is required, acquire it in a dedicated preflight phase before evaluation begins
- if preflight cannot produce adequate coverage, the evaluator should mark the run as partial/deferred/unavailable rather than silently evaluating stale data

Reason:
- these flows can touch many instruments and many timeframes
- letting each engine fetch on the fly is the fastest path to:
  - quota waste
  - inconsistent results
  - bad runtime performance
  - subtle race conditions between evaluation and refresh

#### 11c. Background maintenance / data-orchestration flows

Examples:
- nightly OHLCV refresh
- bulk instrument history fetch
- discovery-triggered initial history seeding
- future pre-market or post-close refresh waves
- future scheduled "prepare data for radar/screener/alerts" tasks

Policy:
- these are the preferred place for broad provider usage
- they may fetch at larger scale, but should still fetch precisely where possible
- they should aim to keep the DB sufficiently ready that evaluators rarely need to wait

Reason:
- this centralizes provider communication
- this makes rate limiting and retry behavior operationally visible
- this avoids broad evaluators becoming selfish and independently burning provider quota

Desired platform rules:
- Rule 1: never perform factual evaluation on known-stale or known-missing price data.
- Rule 2: never fetch broad history when a narrow missing slice will do.
- Rule 3: never allow multiple callers to independently hit providers for the same instrument/timeframe/range if the request can be coalesced.
- Rule 4: never allow a broad evaluator to spend provider quota without going through a shared coordinator.
- Rule 5: historical ranges already fully covered in the DB should not be treated as stale merely because they are old relative to the current wall clock.
- Rule 6: freshness semantics must be use-case aware, not just "is the latest bar older than now?".

What should be built:

#### 11d. Shared OHLCV coverage/freshness coordinator

Introduce one central service, rather than many feature-specific implementations, with an interface conceptually similar to:
- `ensure_ohlcv_coverage(instrument_id, timeframe, start, end, freshness_policy, mode)`

The exact final API can differ, but the coordinator should be responsible for:
- inspecting the current DB coverage for the exact instrument/timeframe/range requested
- determining whether the request is:
  - ready
  - partially covered
  - missing
  - stale
  - already being refreshed
  - unavailable due to provider/runtime constraints
- computing the exact missing slice rather than defaulting to broad "latest N" fetches unless that is truly the narrowest correct request
- coalescing overlapping requests from multiple callers
- reusing in-flight refresh work when one caller already requested the same coverage
- routing provider work through the existing provider runtime / throttling / health machinery
- returning explicit status so callers know whether they may proceed synchronously, should queue work, or must defer

The coordinator should understand the difference between:
- latest-window freshness
- historical-range completeness
- cold-start absence of any OHLCV
- partial historical gaps in the middle of a range
- synthetic instruments whose OHLCV is computed internally rather than fetched from providers

#### 11e. Formal freshness semantics by use case

Define "fresh enough" in a way that is aware of:
- timeframe
- market/session timing
- the consuming engine
- whether the use case needs the latest completed bar, a historical range, or a live latest-price signal

Examples:
- `D1` radar/screener:
  - should require the latest completed daily bar for the relevant session
  - should not demand a synthetic "today" bar before the daily bar has actually completed
- `W1` computations:
  - should care about the latest completed weekly bar, not naïvely treat mid-week partial state as missing unless the feature explicitly supports it
- historical chart pagination:
  - should care about completeness of the requested window, not freshness to the current timestamp
- price alerts:
  - may legitimately require a live latest-price capability rather than OHLCV-bar freshness alone
- indicator alerts:
  - should run against refreshed OHLCV snapshots at the required timeframe, ideally grouped by instrument/timeframe rather than fetching per-alert

This freshness logic should eventually become exchange-aware and asset-aware where relevant:
- weekends and holidays
- pre-market / regular session / post-market behavior
- `24/7` assets like crypto
- provider-specific publication timing for daily/weekly bars

#### 11f. Evaluation preflight for broad engines

Broad evaluators should move to a two-phase model.

Phase 1: coverage preflight
- determine the exact required OHLCV window per instrument and timeframe
- check freshness and completeness
- queue refresh/fill only for the instruments that need work
- optionally wait for a bounded refresh wave to complete
- mark unresolved instruments as unavailable/blocked rather than guessing

Phase 2: evaluation
- run the evaluator strictly against DB-backed data
- never mix provider fetches into the evaluation loop itself
- persist whether the run was:
  - full
  - partial
  - deferred
  - stale-blocked
  - provider-unavailable

This pattern should eventually apply to:
- radar scans
- `run_screener`
- `stream_screener`
- grouped indicator-alert evaluation
- future breadth snapshots
- future signal/strategy engines

#### 11g. Request coalescing and anti-selfishness controls

The future orchestration layer should explicitly prevent anti-patterns like:
- radar, screener, alerts, and chart loads all noticing the same stale `AAPL D1` coverage and each independently calling the provider

Add shared controls for:
- in-flight deduplication per `(instrument, timeframe, adjusted, range/freshness intent)`
- bounded concurrency by provider and capability
- global and per-provider refresh budgets
- caller-visible statuses such as:
  - `already_refreshing`
  - `queued`
  - `ready`
  - `deferred_due_to_budget`
  - `provider_unavailable`
  - `no_provider_support`

This should integrate with the provider runtime / policy / health system rather than bypassing it.

#### 11h. Precise missing-slice fetch logic

The implementation should aggressively avoid over-fetching.

Expected behaviors:
- if the DB has bars through `2026-05-05` and only `2026-05-06` is missing, fetch only that missing tail
- if the user paginates older chart history and the DB lacks only the older tail needed for that page, fetch only that tail
- if the DB already fully covers a historical range, do not fetch anything just because the range ends in the past
- if an instrument is new and entirely cold, fetch only the minimum viable bootstrap window needed for the current synchronous use case unless a broader background seed job is intentionally requested
- if a background bulk-fetch wave is already responsible for fuller history, synchronous flows should avoid redundantly asking for the entire history themselves

The coordinator should explicitly understand:
- latest-window repair
- historical-gap repair
- cold-start bootstrap
- overlap buffers for late-arriving bars or provider revisions

#### 11i. Better dataset-state tracking

The platform already has some dataset-state/provider-observation ideas, but this future work should deepen them for OHLCV specifically.

Track enough metadata to answer:
- what coverage window currently exists for this instrument/timeframe?
- when was it last observed from a provider?
- when should it be considered stale for each major consumption mode?
- did the most recent refresh succeed, partially succeed, return empty, or fail?
- is a refresh already in progress?
- what provider last supplied or refreshed the data?
- is the dataset totally absent or only partially missing?

This should make it possible to:
- avoid recalculating freshness naively on every caller
- explain why a symbol was skipped by radar or a screener
- later expose operational insight in admin or diagnostics surfaces

#### 11j. Unify currently inconsistent consumers

The current mixed behavior should be normalized over time.

Specific migration targets:
- radar:
  - keep the detector DB-only at evaluation time
  - add a preflight coverage stage
- `run_screener`:
  - move from "DB-only, no preflight" to "DB-only after preflight"
- `stream_screener`:
  - stop being a special fetch-on-the-fly exception
  - instead stream:
    - coverage-preflight progress
    - then evaluation progress
- indicator alerts:
  - stop refreshing OHLCV separately inside each alert path
  - group by `(instrument, timeframe)` and refresh once, then evaluate all alerts from the same DB snapshot
- chart/instrument OHLCV routes:
  - keep read-through semantics
  - but route through the same coordinator so missing-slice and freshness policy stay consistent across the app

#### 11k. Operational orchestration and scheduling

The shared design should also inform platform scheduling.

Questions to settle and later implement:
- which refresh waves should run automatically:
  - nightly / post-close `D1` refresh
  - weekly `W1` refresh
  - selected intraday refreshes for alert-heavy assets
  - discovery-triggered bootstrap refreshes
- what readiness guarantees should exist before:
  - scheduled screeners
  - future scheduled radar scans
  - alert checks
  - future breadth snapshots
- what intentional order should exist between:
  - OHLCV refresh
  - evaluator runs
  - downstream watchlist/notification/state-propagation workflows

The long-term goal is that broad evaluators rarely discover missing data themselves because scheduled refresh waves have already kept the DB sufficiently ready.

#### 11l. Failure handling and run semantics

The future system should not force every evaluation to be all-or-nothing.

Support nuanced outcomes such as:
- run completed with full coverage
- run completed with partial coverage
- run deferred because refresh work would exceed current budget or timeout
- run skipped because provider chain health made refresh unsafe/unreliable
- instrument skipped because no provider-backed OHLCV source exists for it

These statuses should become visible where appropriate in persisted run metadata for:
- radar runs
- screener runs
- later breadth/signal/strategy runs

This matters because:
- "no matches"
- "could not evaluate accurately"
- and "some instruments were unevaluable"
are materially different outcomes.

#### 11m. Testing and verification expectations

This roadmap item deserves explicit tests of its own.

Expected test coverage:
- exact missing-slice calculation
- historical-range completeness vs latest-window freshness
- no-fetch behavior when a historical range is already fully covered
- deduplication of concurrent refresh requests
- grouped refresh behavior for indicator alerts
- preflight + evaluation separation for radar and screeners
- correct partial/deferred run statuses
- protection against stale-data evaluations
- provider-budget and throttle behavior under multiple simultaneous callers

Integration scenarios should explicitly cover:
- a cold instrument with no bars
- an instrument missing only the most recent bar
- an instrument with historical gaps
- provider unavailability during preflight
- chart read-through paths and evaluator preflight paths both using the same coordinator

Open design questions to preserve for later:
- Should broad evaluators block synchronously for missing data up to a short deadline, or always queue and retry later?
- Which assets/timeframes deserve proactive readiness guarantees versus on-demand preflight?
- How much exchange/session awareness should live in the coordinator versus provider adapters or market-calendar utilities?
- Should the platform have a formal freshness-SLA registry per capability / asset class / timeframe?
- How should synthetic instruments inherit or aggregate constituent freshness?
- Should options-related spot-price consumers use the same OHLCV freshness gate or a lighter latest-price-specific policy?

Suggested implementation sequence:
- Phase 1:
  - document the platform policy explicitly
  - introduce a shared coverage/freshness coordinator API
  - keep existing market-data fetch helpers, but route decision logic through the new abstraction
- Phase 2:
  - migrate chart/instrument read-through OHLCV flows to the coordinator
  - migrate radar preflight
  - migrate `run_screener` and `stream_screener`
- Phase 3:
  - migrate grouped indicator-alert evaluation
  - add persisted run statuses and richer skip/defer semantics
  - deepen dataset-state visibility
- Phase 4:
  - align scheduling so refresh waves intentionally precede evaluation waves
  - extend the same model to breadth, signal, and strategy engines

Why this was deferred:
- The current platform already works well enough for chart read-through, basic background refresh, and feature-specific point solutions.
- Solving this correctly is architectural work, not a small feature patch.
- Its value rises as more broad evaluators come online, especially radar expansion, breadth analysis, and future signal/strategy engines.

## Notes

- This file intentionally focuses on postponed work that already came up in discussion.
- It is not meant to replace issue tracking if we later decide to formalize roadmap management elsewhere.
- This is the only file that should be treated as the canonical TODO memory for deferred work in this repo.
