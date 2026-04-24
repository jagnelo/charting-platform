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

## Notes

- This file intentionally focuses on postponed work that already came up in discussion.
- It is not meant to replace issue tracking if we later decide to formalize roadmap management elsewhere.
- This is the only file that should be treated as the canonical TODO memory for deferred work in this repo.
