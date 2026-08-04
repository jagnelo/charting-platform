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
  - thread-aware continuity/history via persisted `radar_setup_thread` records
  - chart-side radar selection/toggling with thread context for the loaded instrument
  - the current Radar v2 baseline with:
    - persisted detection/thread state fields
    - breakout-retest / breakdown-retest families
    - action-level fields (`entry_price`, `invalidation_price`, `target_price`)
    - state-aware filtering/presentation in `/radar`
    - fakeout / failure / compression setup families
    - richer AVWAP anchor provenance plus all-time / YTD / rolling-window context
    - diagonal trendline / gap / simple pattern context
    - invalidated / resolved / stale transition persistence
    - saved radar views, instrument timelines, and a radar dashboard widget
  - initial setup types:
    - approaching support
    - approaching resistance
    - breakout
    - breakout retest
    - breakdown
    - breakdown retest
    - fakeout
    - fakedown
    - failed reclaim
    - failed breakdown recovery
    - compression support
    - compression resistance
    - reclaim
    - rejection
  - initial evidence sources:
    - clustered swing-based horizontal zones
    - anchored VWAP from recent/contextual anchors
    - EMA context
    - 52-week high/low context
    - all-time / YTD / rolling-window context
    - diagonal trendlines
    - gap zones
    - simple pattern structures
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
  - fakeout
  - fakedown
  - failed reclaim
  - failed breakdown recovery
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

- Extend the persistent radar/setup model beyond the current run+detection+thread foundation so it can also store:
  - richer state transitions over time beyond the current `developing` / `confirmed` baseline
  - automatic handling of failed / invalidated / stale states
  - evolving score history instead of only one snapshot
  - richer setup-thread semantics beyond today’s nearby-level continuity matching
  - later outcome / forward-performance tracking

- Expand the UI surfaces beyond the current dedicated `/radar` page, including:
  - a richer radar list / scanner view
  - side-by-side comparison of multiple detections
  - fuller setup history / state-transition history beyond the current thread + history-browser surfaces
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

Entry, exit, and invalidation semantics to deepen from the current v2 slice:
- **Explicit entry / invalidation / target levels now exist**, but they are still heuristic and detector-local. Improve them into a more rigorous action model (e.g., breakout close vs retest hold vs reclaim confirmation) and make the rationale more explicit in evidence payloads.
- **Lifecycle refinement beyond the current stale model**: Radar no longer hard-expires detections by TTL; it now keeps them open until they become `target_hit`, `invalidated`, or contextually `stale`. Future work here should refine the stale heuristics further with better regime awareness, thread supersession semantics, and setup-family-specific decay rules rather than reintroducing fixed expiry windows.
- **Connection to trade signal engine (item 8)**: When item 8 is implemented, radar detections are the natural input — a detection with an entry level, invalidation level, and score becomes the seed for a structured trade plan. The invalidation level becomes the stop, and the implied target can be the opposing zone or a fixed R-multiple. Both systems should share schema vocabulary from the start (entry_price, stop_price, target_price, risk_multiple).

Nearer-term concrete follow-up phases worth treating as the next likely implementation path:
- Phase 2:
  - richer structure extraction
  - scheduled runs
  - stronger chart overlay controls
- Phase 3:
  - fakeout/compression/failure state modeling beyond the current retest slice
  - managed radar/watchlist workflows beyond one-off actions
  - richer alert orchestration and state-transition workflows
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

### 7. Build a Strategy Lab with backtesting, walk-forward testing, and paper forward testing, likely powered by Nautilus Trader as the simulation engine
Status: `In progress`

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
- Keep a clean product boundary between present-looking platform surfaces and historical research:
  - Radar and Screeners remain primarily present-looking discovery/evaluation products operating on the latest sufficiently fresh data.
  - Historical "what would this have done in the past?" replay should not become an ad hoc mode inside those products.
  - Instead, the shared Strategy Lab / Research Lab should own historical replay, backtesting, walk-forward testing, and paper-forward evaluation for both user-authored strategies and platform-owned signal sources.
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
- Treat the research engine as capable of consuming multiple signal-source classes, not only user-authored strategy rules, including:
  - custom strategies defined by users
  - platform-owned Radar detections treated as a built-in signal family
  - later, if useful, screener-derived signal/event feeds or other platform-owned discovery engines
- Support a future in which another engine or custom executor could sit behind the same platform-owned orchestration interfaces.

What remains:

- Continue from the current Strategy Lab baseline now present in the codebase, which already establishes:
  - persisted strategy definitions, versions, and runs
  - a visual-first frontend builder for rule-based strategies instead of raw JSON authoring
  - a backend run path that now uses Nautilus Trader for backtesting/simulation instead of the earlier in-house placeholder path
  - persisted backtest outputs exposed in platform-owned result schemas and shown in a platform-native UI
  - a clean separation between this research layer and present-looking products like Radar and Screeners
- Evolve that baseline from "good first visual backtest workspace backed by Nautilus" into a serious research workstation that can credibly compete with stronger retail/professional strategy-testing products.

- Be explicit about the current product boundary and current limitations so future work does not overestimate how complete this feature already is:
  - The current user value is real:
    - users can visually define a strategy
    - persist and version it
    - run historical backtests, walk-forward passes, and paper-forward-style continuation windows
    - inspect summary metrics, equity curves, benchmark context, warnings, trades, per-symbol attribution, and richer distributions
  - But the current implementation is still materially earlier-stage than mature competitors.
  - It should be treated as a functioning v1 research product, not a finished research lab.

- Capture the current gaps versus stronger competitors and use them as the roadmap for continuing this feature:
  - **Walk-forward and paper-forward are now real product surfaces, but still not deep enough yet.**
    - The current surface now exposes real walk-forward research segments and refreshable paper-forward monitoring snapshots, but it is still not a full end-to-end research/deployment workflow.
    - Walk-forward still needs deeper split configuration, rolling calibration/evaluation behavior, and richer out-of-sample stability surfaces.
    - Paper-forward now persists monitor snapshots on refresh, but it still is not a continuously scheduled live simulated monitoring loop over newly arriving data.
    - This is one of the largest product gaps because many stronger competitors let users validate not only historical fit but also forward behavior.
  - **The visual rule builder is materially stronger now, but still not broad enough for every serious strategy.**
    - Current rule authoring now supports nested `All` / `Any` / `NOT` groups and grouped precedence instead of only a flat condition list, but it is still limited.
    - Missing:
      - broader condition families
      - richer multi-timeframe logic
      - more session/time/event filters
      - stronger validation of structurally invalid rule combinations
    - This makes the current builder useful for simple systems but too narrow for many real strategies.
  - **Execution modeling is still thinner than it should be.**
    - Current support is centered on:
      - bar-driven entries/exits
      - stop loss
      - R-multiple target
      - time exit
      - break-even promotion
      - trailing-stop adjustment
      - capped pyramiding / multi-entry behavior
      - slippage assumptions
      - basic commission-model assumptions
    - Missing:
      - partial exits
      - richer order semantics
      - more advanced contingent-order workflows
      - more nuanced time-in-force and expiry handling where relevant
      - deeper fee modeling such as exchange / regulatory fees and tiered broker schedules
    - This is a major realism gap versus competitors and a major determinant of whether a backtest says anything useful.
  - **Multi-symbol portfolio simulation is improved, but still not production-grade.**
    - Current multi-symbol handling now applies portfolio-level trade acceptance controls such as concurrent-position caps, portfolio-risk caps, and symbol-allocation caps before building the combined portfolio result.
    - This is still not yet a full portfolio-aware scheduler/executor.
    - Missing:
      - deeper capital contention modeling across simultaneous opportunities
      - realistic position prioritization policies
      - sector exposure caps
      - more realistic cash reservation and overlapping-trade handling
    - This is one of the biggest reasons current multi-symbol results should be considered directionally useful rather than fully production-grade.
  - **Analytics are still thinner than serious research platforms, even though the baseline is now broader.**
    - Current outputs are useful but still compact:
      - summary metrics
      - equity curve
      - benchmark overlay / excess-return context
      - drawdown curve
      - monthly/quarterly performance breakdowns
      - warnings
      - trade list
      - per-symbol attribution
      - trade histograms/distributions
    - Missing:
      - MAE/MFE distributions
      - deeper holding-time and trade-outcome analytics
      - broader strategy-to-strategy comparison surfaces
      - richer run-to-run diffing between revisions
      - broader cohort/regime analysis
    - Competitors extract a large amount of user value from rich post-run analysis; this remains an important growth area.
  - **Multi-strategy correlation and composition research is still too shallow.**
    - We discussed wanting users to go beyond isolated strategy runs and evaluate how multiple strategies behave together as a portfolio.
    - Missing:
      - rolling correlation stability between strategies rather than only static snapshots
      - covariance/clustering analysis of strategy behavior
      - marginal contribution to portfolio return, volatility, and drawdown when adding or removing one strategy from a mix
      - portfolio-of-strategies simulation with configurable capital-allocation and rebalance rules
      - optimization/screening flows that help users deliberately combine lower-correlation strategies to reduce drawdowns and smooth equity curves
    - This is an important competitive gap because many users ultimately care more about the behavior of the combined strategy portfolio than about the headline metrics of one isolated system.
  - **Parameter exploration and robustness analysis are still early.**
    - Missing:
      - richer parameter sweeps than the current bounded leaderboard
      - optimization batches
      - sensitivity heatmaps
      - robustness summaries across periods/universes
      - overfitting detection aids
      - version-to-version comparison under the same scenario matrix
    - Without this, users can test a strategy, but cannot yet systematically improve it at scale.
  - **Radar/screener/platform-signal research integration is only partially in place.**
    - One of the most important strategic goals discussed was to use Strategy Lab as the shared validation layer for both:
      - user-authored strategies
      - platform-owned signal sources like Radar
    - That second half is now started, but not yet broad enough.
    - Missing:
      - apples-to-apples comparison of custom strategies versus Radar signals
      - screener-derived signal replay rather than only latest-result screener universes
      - later, if valuable, screener-derived or other platform-owned signal/event replay
    - This is a major latent value source because it turns Strategy Lab into the place where platform intelligence is validated and improved, not just user-authored logic.
  - **Asset-model breadth and realism are still limited.**
    - The current Nautilus adapter is strongest for equity-style, OHLCV-bar-based strategies.
    - It is not yet a broad, fully generalized research layer for:
      - futures
      - options
      - FX
      - crypto
      - synthetic/expression instruments
    - Missing:
      - broader canonical instrument-to-Nautilus mapping
      - more complete venue/account/execution semantics per asset class
      - more nuanced data-shape support where the strategy depends on more than simple OHLCV bars
    - This means Strategy Lab is already real, but not yet broad enough to inherit the full breadth of the platform’s instrument universe.
  - **The results UI is still more of an enhanced report than a full research workstation.**
    - Current UI is now materially broader, with richer analytics panes, comparison, export, grouped rule authoring, and paper-forward refresh/monitor surfaces, but it is still not yet a full analysis environment.
    - Missing:
      - stronger result navigation
      - richer dedicated tabs/panels for analytics
      - stronger visual benchmarking
      - saved result views
      - revision history comparison workflows
      - broader export surfaces
    - This is not just polish; research UX determines whether users can actually learn anything from their runs.
  - **Backtest/live continuity is still underexploited.**
    - One major reason Nautilus is valuable is that it supports a deeper parity model between historical and forward/live semantics.
    - We are not using that deeply yet.
    - Missing:
      - a continuously scheduled paper-forward loop
      - deeper state continuity from historical run definitions into forward simulation
      - richer operational surfaces that let users monitor a running simulated strategy over fresh incoming data
    - This is a major future-value area.
  - **Benchmarking is better than before, but still not first-class enough.**
    - Benchmark symbols/config now feed benchmark curves and excess-return reporting, but the overall benchmarking workflow is still thinner than what users expect.
    - Missing:
      - relative drawdown reporting
      - benchmark cohort comparison
      - strategy-as-benchmark workflows where another strategy/run can be treated as the benchmark rather than only a passive instrument
      - benchmark-aware run summaries beyond the current baseline
    - This is important because users do not just care whether a strategy "made money"; they care whether it beat a passive alternative.
  - **The feature does not yet fully exploit the rest of the platform.**
    - Long-term value should come from Strategy Lab acting as the validation/research layer for:
      - watchlists
      - screeners
      - Radar
      - baskets
      - breadth views
      - economic events / context filters
    - Today that integration is still early.
    - This is one of the biggest strategic advantages available to this platform over standalone testing products, so it should be treated as a first-class roadmap lane.

- Distinguish clearly between the current flaws and the future opportunities for extracting more value:
  - Current flaws:
    - too narrow for many real-world strategies
    - too weak in portfolio realism
    - still too thin in result analysis relative to competitors
    - platform-signal research is started but not yet broad enough
    - too limited in asset/model breadth
  - Current value:
    - real no-code/low-code visual strategy authoring
    - real Nautilus-backed backtesting in the backend
    - versioned/persisted strategy research objects
    - an integrated foundation that already fits the rest of the platform better than an external standalone tool would
  - Major future value sources:
    - use Strategy Lab as the validation layer for Radar
    - use Strategy Lab as the experimentation/tuning layer for platform-owned signal engines
    - connect watchlists/screeners/baskets/Radar directly into research universes and signal sources
    - grow it into a differentiated integrated research layer rather than just a generic backtester UI

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
- Be explicit that the current Strategy Lab screener-universe implementation is intentionally only a **snapshot universe** for now:
  - the current `Latest screener result` behavior should be treated as:
    - "take the screener membership as of run submission time"
    - freeze that basket
    - run the strategy historically over that fixed symbol set
  - keep this current approach in place for now because it is simpler, deterministic, and already useful for:
    - testing a strategy on a screener-defined basket
    - comparing strategies over the same frozen screener membership
    - ad hoc research without introducing time-varying universe lifecycle complexity
- Add a future **dynamic screener universe** mode for Strategy Lab rather than treating screener-universe research as permanently snapshot-only:
  - the long-term user-facing concept should likely be something closer to `Screener universe` or `Dynamic screener universe`, not only `Latest screener result`
  - the intended behavior is:
    - during a simulated run, the screener is re-evaluated through simulated time
    - at each refresh point, only the data that would have existed at that historical moment is used
    - the eligible symbol basket can change over time as the screener membership changes
  - this should be modeled as a time-varying **entry-eligibility universe**, not as a simplistic "replace the whole portfolio immediately" mechanism
- When implementing the dynamic screener universe mode, explicitly define and persist the following policies so behavior is unambiguous and testable:
  - **Refresh cadence**
    - every bar
    - every N bars
    - daily
    - weekly
    - or another configured rebalance cadence
  - **Evaluation timing**
    - whether the screener membership for a bar is computed:
      - on the close of that bar
      - on the next bar open
      - or on another explicit decision point
    - this matters because the screener output must not peek into data not yet available at the simulated decision moment
  - **Entry eligibility policy**
    - only symbols currently in the screener membership are eligible for new entries
    - newly-added symbols become eligible only from the next defined execution/rebalance point
    - symbols removed from the screener should no longer accept fresh entries unless they later re-enter
  - **Open-position removal policy**
    - define what happens when a symbol leaves the screener while a position is already open
    - supported policies should eventually include:
      - `hold_until_exit`
      - `force_exit_on_removal`
      - `grace_period_after_removal`
    - the most natural default discussed was:
      - a symbol leaving the screener only blocks new entries
      - existing positions continue to be managed by their own stop/target/time-exit logic until they close naturally
  - **Re-entry policy**
    - if a symbol leaves the screener and later re-enters, it should become eligible again
    - re-entry should still respect the strategy's own entry logic and portfolio rules rather than blindly re-open a position just because the screener includes it again
  - **Portfolio interaction policy**
    - because the eligible universe changes over time, dynamic screener universes must work cleanly with:
      - capital contention
      - concurrent-position limits
      - symbol-allocation caps
      - portfolio-risk caps
      - any later sector/exposure caps
    - this means the screener universe should be treated as an upstream candidate filter, not as a direct instruction to allocate capital to everything newly included
- Treat dynamic screener universes as a first-class simulation concern rather than a small UI tweak:
  - the backtest engine will need a scheduled screener-refresh mechanism during simulation
  - the strategy run must be able to evaluate screener conditions point-in-time against historical data available at each simulated step
  - run artifacts/results should make it possible to inspect:
    - when screener refreshes happened
    - how membership changed over time
    - which trades were allowed or blocked because of screener membership at that moment
  - if helpful, later expose a membership timeline artifact showing:
    - symbols entering/leaving the screener universe through time
    - position lifecycle relative to that changing universe
- Keep a clean product distinction between the two screener-universe modes once both exist:
  - **Snapshot screener universe**
    - fixed basket
    - easier to reason about
    - useful for static-basket research
  - **Dynamic screener universe**
    - membership evolves over simulated time
    - more realistic for strategy behavior
    - requires explicit lifecycle policies
- Do not blur these modes together silently:
  - users should know whether a strategy run used:
    - a frozen screener snapshot
    - or a time-evolving screener universe
  - this choice should be visible in run configuration and stored in run artifacts/results for reproducibility

- Add a first-class **portfolio rotation / scheduled rebalance strategy mode** to support strategies that are not merely "evaluate entry/exit rules independently for each symbol", using the Starter System PDF discussion as a concrete forcing case:
  - The Starter System should be treated as an example of a strategy that Strategy Lab should eventually be able to express **exactly**, not approximately:
    - use a point-in-time broad equity universe such as the Russell 3000
    - evaluate filters on a monthly schedule
    - rank all passing candidates cross-sectionally
    - select the five lowest RSI(2) names
    - allocate 20% of capital to each selected name
    - rebalance on the next monthly open
    - exit all positions at the next rebalance unless selected again
    - force exits when a market-regime condition turns off
    - produce a monthly action list the user can follow manually
  - This exposes a major missing capability in the current Strategy Lab baseline:
    - the current engine is strongest at per-instrument rule evaluation
    - portfolio controls are layered on top of independently-generated opportunities
    - this is not enough for strategies where the primary decision is "rank the whole universe, choose the best N, and build the portfolio from those choices"
  - Add an explicit strategy archetype / execution mode for:
    - single-instrument rule strategies
    - multi-instrument independent-signal strategies
    - portfolio rotation strategies
    - later, pair/spread strategies and multi-leg strategies
  - A portfolio rotation strategy needs a different internal lifecycle:
    - build candidate universe for a decision point
    - evaluate all filters point-in-time
    - rank the filtered candidates
    - select top-N / bottom-N / percentile buckets
    - compare selected target portfolio versus currently-held portfolio
    - generate exits, holds, entries, and weight adjustments
    - apply execution assumptions at the configured execution point
    - persist the rebalance artifact before moving to the next decision point

- Add point-in-time index/constituency universe support because serious portfolio-rotation systems cannot be tested faithfully against only today's survivors:
  - support universes such as:
    - Russell 3000 constituents as-of each historical date
    - S&P 500 constituents as-of each historical date
    - ETF holdings as-of each historical date where available
    - user-defined universes with membership-effective date ranges
  - Treat ETF holdings as a useful lower-cost proxy universe when official index-constituent history is unavailable or too expensive, but never silently equate the two:
    - official index constituents are the authoritative, usually licensed dataset
    - ETF holdings are the fund issuer's disclosed portfolio and may differ due to sampling, cash, derivatives, timing, corporate actions, or tracking methodology
    - runs should record whether they used official point-in-time index membership, ETF-holdings proxy membership, a latest holdings snapshot, or a manual/static universe
  - persist universe membership as a time-varying dataset:
    - universe identifier
    - instrument identifier
    - membership start date
    - membership end date
    - membership source/provider
    - confidence/provenance
    - optional weight/classification metadata where the source provides it
  - make survivorship-bias status visible in run configuration and results:
    - `point_in_time_universe`
    - `latest_membership_snapshot`
    - `manual_static_universe`
  - warn clearly when a strategy that claims to test an index universe is actually using a latest-only or manually frozen universe.
  - Allow the data-prep layer to request missing member instruments and their historical bars as part of run preflight instead of discovering missing coverage only after a run has produced misleading results.

- Add scheduled decision/rebalance calendars as first-class strategy inputs:
  - support cadences such as:
    - every bar
    - daily
    - weekly
    - monthly
    - quarterly
    - custom cron/calendar schedules
    - exchange-aware "last trading day of month"
    - exchange-aware "first trading day of month"
  - separate the **decision timestamp** from the **execution timestamp**:
    - screen on month-end close
    - execute at next monthly open
    - screen on today's close
    - execute on next bar open
    - screen intraday and execute immediately where data/execution assumptions allow
  - persist schedule semantics in run configuration:
    - calendar used
    - timezone
    - exchange/market holiday handling
    - decision price source
    - execution price source
    - handling of missing bars on the scheduled decision or execution day
  - expose scheduled events in run artifacts:
    - decision points
    - rebalance points
    - symbols evaluated at each point
    - selected basket at each point
    - target weights
    - executed portfolio changes

- Add cross-sectional ranking and candidate-selection primitives:
  - allow strategies to rank candidates by:
    - indicator values such as RSI(2)
    - price returns over configurable windows
    - volatility
    - liquidity
    - fundamental metrics
    - platform-computed statistics
    - custom expressions/factors later
  - support ranking directions:
    - lowest first
    - highest first
    - absolute distance from target value
    - percentile buckets
    - z-score / normalized ranking later
  - support selection policies:
    - top N
    - bottom N
    - top/bottom percentile
    - rank threshold
    - weighted by rank score
    - tie-breakers
  - persist the rank table for every decision point so the user can inspect:
    - symbols that passed filters
    - symbols that failed filters
    - the filter that rejected each failed symbol
    - each candidate's rank metric value
    - final rank position
    - selected/not-selected reason
  - This should unlock not only the Starter System, but also:
    - momentum rotation
    - mean-reversion baskets
    - low-volatility selection
    - high-quality/fundamental factor screens
    - sector rotation
    - ETF rotation
    - breadth-driven basket strategies

- Add portfolio construction and target-allocation rules instead of relying only on per-trade position sizing:
  - support target portfolio policies such as:
    - equal weight across selected symbols
    - fixed percent per selected symbol
    - volatility-scaled weights
    - rank-score-weighted allocation
    - inverse-volatility weighting
    - max position weight
    - min position weight
    - cash reserve target
  - support rebalance behavior:
    - full liquidation and rebuild
    - only trade differences from current holdings
    - hold selected names that remain selected
    - rebalance back to target weights
    - drift bands before rebalancing
    - minimum trade-size thresholds
  - explicitly model what happens when fewer than the target number of names pass:
    - leave unused capital in cash
    - redistribute among available names
    - skip the rebalance entirely
    - keep existing holdings until enough replacements exist
  - persist target-vs-actual portfolio state:
    - target symbols
    - target weights
    - actual filled weights
    - cash after rebalance
    - turnover
    - symbols bought/sold/held/skipped
    - rejected trades and rejection reasons

- Add cross-instrument and portfolio-level condition inputs:
  - allow a condition on one instrument/index to control trading in another universe:
    - "only open Russell 3000 positions when S&P 500 RSI(4) > 50"
    - "force exit all open positions when S&P 500 RSI(4) < 50"
    - "only run this strategy when VIX is below/above a threshold"
    - "only buy sector constituents when the sector ETF is above its moving average"
  - distinguish:
    - instrument-local conditions
    - benchmark/regime conditions
    - universe-level aggregate conditions
    - portfolio-state conditions
  - support regime conditions as:
    - entry gates
    - exit triggers
    - allocation scalers
    - cash/defensive-state switches
  - Persist regime state through time and show it in results:
    - when regime was on/off
    - which entries were blocked by regime
    - which positions were closed because regime turned off
    - whether the strategy was fully invested or sitting in cash

- Expand condition/stat/factor support required by portfolio-rotation strategies:
  - add rolling liquidity metrics:
    - 20-day average volume
    - 30-day average volume
    - 60-day / 3-month average volume
    - average dollar volume
    - median dollar volume
    - minimum liquidity over a lookback window
  - add price and tradability filters:
    - price greater/less than a threshold
    - adjusted versus unadjusted price basis
    - minimum trading history length
    - minimum bars available in lookback window
    - exclusion of suspended/untradable instruments where known
  - support indicator calculations on:
    - the candidate instrument
    - a benchmark/regime instrument
    - a sector/index/ETF proxy
    - later, a synthetic basket or expression instrument
  - ensure all filters are evaluated point-in-time using only data available at the decision timestamp.

- Add explicit forward **published strategy runtime** support so Strategy Lab strategies can produce passive, recurring action signals without turning Screener or Radar into strategy owners:
  - Strategy Lab should own:
    - strategy definition
    - versioning
    - backtests
    - validation
    - publish workflow
  - A published strategy runtime should own:
    - scheduled forward execution of published versions
    - persisted strategy state
    - current open simulated/manual-following portfolio state
    - recurring decision runs
    - signal/action generation
  - The runtime should generate actionable outputs such as:
    - buy these symbols
    - sell these symbols
    - hold these symbols
    - rebalance these weights
    - no action because regime is off
    - data coverage is insufficient
    - candidate excluded because it failed a filter
  - These outputs should be stored as strategy action sets, not as plain screener results:
    - action set id
    - strategy version id
    - decision timestamp
    - execution timestamp
    - target basket
    - current basket
    - diff/actions
    - quantities/weights if configured
    - rank/filter evidence
    - user acknowledgement status later
  - This runtime should be able to support "manual execution" workflows first:
    - the platform tells the user what the strategy says to do
    - the user decides whether/how to place trades outside the platform
    - the platform can later let the user mark actions as followed, skipped, or adjusted
  - Later, this can integrate with broker execution if/when the platform grows beyond research/manual-action workflows.

- Keep Screener and Radar as reusable inputs, not owners of stateful strategy execution:
  - Screener should remain useful for:
    - authoring/reusing filter condition sets
    - present-looking "what passes now?" discovery
    - scheduled screen results where the output is simply a matching instrument set
    - serving as one possible upstream candidate-filter component for Strategy Lab
  - Radar should remain useful for:
    - autonomous technical opportunity discovery
    - platform-owned signal families
    - candidate feeds into Strategy Lab/research
  - Neither Screener nor Radar should own:
    - target weights
    - open strategy positions
    - rebalance state
    - ranking-driven portfolio construction
    - portfolio-level exits
    - strategy action-set history
  - If a user wants a saved screener to feed a strategy:
    - Strategy Lab/runtime should reference the screener definition or condition set
    - the runtime should still own selection, allocation, state, and actions
  - If a user wants Radar to feed a strategy:
    - Radar should provide candidate events/detections
    - Strategy Lab/runtime should still own execution policy and portfolio state

- Add a reusable **condition-set / filter-set borrowing** mechanism between Screener and Strategy Lab without collapsing the products together:
  - allow a Strategy Lab strategy to:
    - import a Screener condition tree as a starting point
    - reference a saved Screener condition set by version
    - fork a Screener condition set into strategy-owned logic
    - expose strategy condition sets to Screener where the semantics are compatible
  - define compatibility boundaries:
    - pure point-in-time instrument filters can be shared
    - portfolio-level ranking/allocation rules cannot be represented as ordinary screeners
    - entry/exit semantics are strategy-owned, not screener-owned
    - rebalance cadence is strategy-owned, not screener-owned
  - Persist provenance:
    - imported from screener X version Y
    - still linked to screener version
    - forked and no longer linked
  - This gives users the practical benefit of reusing work from Screener while keeping Strategy Lab as the correct owner for serious strategy behavior.

- Add a strategy action / signal feed surface for published strategies:
  - This can be a new surface, or part of a broader Signals/Alerts area, but it should not live only inside the Strategy Lab edit page.
  - It should answer:
    - "Which published strategies have actions due now?"
    - "Which actions were generated by the latest scheduled run?"
    - "What changed versus last month/last run?"
    - "Which symbols entered or left the target basket?"
    - "Which actions are blocked by data quality, regime, or portfolio constraints?"
  - For a monthly rotation strategy, the user-facing output should be closer to:
    - next rebalance date
    - target basket
    - sell list
    - buy list
    - unchanged holds
    - target weights
    - ranking evidence
    - filter evidence
    - data warnings
  - It should later support notifications:
    - in-app alerts
    - email/push/webhook where appropriate
    - "rebalance due" reminders
    - "strategy regime turned off" alerts
    - "data coverage insufficient to generate reliable action" alerts

- Add strategy-state and manual-following tracking as a bridge between research and real user behavior:
  - Store the strategy runtime's expected/paper state separately from the user's actual brokerage state.
  - Allow the user to mark generated actions as:
    - followed
    - skipped
    - partially followed
    - modified
  - Later, connect this to a portfolio/journal feature so the platform can compare:
    - model strategy performance
    - paper/runtime performance
    - user's actually-followed performance
  - This is important for passive strategies where the platform produces actions but the user executes manually.

- Add run/result artifacts specifically for portfolio-rotation strategies:
  - candidate universe snapshot per decision point
  - filter pass/fail table per decision point
  - rank table per decision point
  - selected basket per decision point
  - target weights per decision point
  - rebalance trades per decision point
  - regime state timeline
  - cash allocation timeline
  - turnover timeline
  - constituents entering/leaving the eligible universe
  - selected symbols entering/leaving the target portfolio
  - reasons a symbol was not selected despite passing filters
  - reasons a current holding was sold
  - reasons no new positions were opened
  - These artifacts are essential because users need to trust not just the final return, but the month-by-month decision logic.

- Add a platform-owned signal-source abstraction for research/test runs so the same testing layer can evaluate:
  - user-authored strategies that generate entries/exits from rules
  - Radar detections replayed historically as a built-in black-box signal engine
  - eventually other platform-owned event/signal sources
- This abstraction should make it possible to ask questions such as:
  - "Give me all Radar breakout signals on D1 between 2023-01-01 and 2024-12-31."
  - "Replay all Radar signals in this score bucket using execution policy X."
  - "Compare my custom strategy against the platform Radar over the same universe and date range."
- The query/export contract for platform-owned signal sources should include, at minimum:
  - source type (`strategy`, `radar`, later others)
  - source version / engine version
  - signal/setup family
  - timeframe
  - signal timestamp
  - context timestamp if distinct
  - entry / invalidation / target semantics when available
  - score / confidence / rationale metadata where relevant

- Keep Radar itself non-configurable and present-looking, but make Radar historically researchable through this shared testing layer:
  - the `/radar` product should answer "what looks interesting now?" and "how has this active setup evolved recently?"
  - the Strategy Lab / Research Lab should answer "what would Radar have produced over this historical period?" and "how did those signals perform under execution policy X?"
  - this preserves Radar as a curated black box while still allowing internal tuning and user-facing trust/validation statistics

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
    - flat round-trip fees
    - flat per-order fees
    - percent-of-notional commissions
    - later: tiered fee schedules and venue/regulatory fee components
  - spread assumptions
  - latency assumptions where meaningful
  - fill models
  - venue/exchange awareness
  - position sizing models
  - leverage / margin assumptions
  - portfolio constraints
- These assumptions must be visible in run configs and persisted as part of the provenance of any run result.

- Extend the research engine beyond single-currency portfolio assumptions:
  - support a user portfolio base currency distinct from the traded instrument currency
  - translate P&L, exposure, and drawdown into the portfolio base currency for reporting
  - model FX conversion costs when buying instruments denominated in a different currency than the portfolio base
  - later support configurable spot-conversion pricing assumptions and broker-specific FX conversion fee schedules

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
  - rolling correlation stability across time/regimes
  - covariance/diversification analysis
  - clustering/similarity analysis of strategy behavior
  - portfolio-construction ideas such as combining less-correlated strategies
  - portfolio-of-strategies simulation with configurable weights, capital-allocation rules, and rebalance cadence
  - marginal contribution analysis: "what happens to portfolio return, volatility, Sharpe, and drawdown if this strategy is added or removed?"
  - optimization/screening flows that favor complementary lower-correlation strategies rather than only the highest standalone return
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
  - multi-strategy composition / allocation workspace
  - paper forward-testing monitor

- Add rich visualizations, such as:
  - equity curves
  - underwater/drawdown charts
  - rolling Sharpe / rolling return charts
  - trade distribution histograms
  - heatmaps by month/week/regime
  - parameter sweep heatmaps
  - correlation matrices between strategies
  - rolling correlation charts between strategies
  - portfolio contribution and marginal-risk charts for multi-strategy mixes
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

### 8. Build a Trade Signal, Virtual Trade Tracking, and Trader-Follower engine
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

### 9. Activate paid providers for options data and forward earnings estimates
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

### 9A. Add a free-source-first forward IPO and market-events calendar
Status: `Planned`

Context:
- The platform already has pieces that are adjacent to this problem, but not the actual subsystem we need:
  - persisted per-instrument event storage
  - a `/calendar` router
  - dashboard economic-calendar widget surfaces
  - historical and semi-forward instrument-level events from current providers such as yfinance/EDGAR
- What is still missing is a **market-wide, forward-looking event layer** that lets the platform look ahead, not just look back.
- We explicitly want this for two strategic reasons:
  - discover new tickers before or as they enter the instrument universe
  - give users forward visibility into market events so they can adjust portfolio exposure ahead of them
- The initial focus should be **US markets**, because free structured sources are far more realistic there than for EU or APAC right now.

Free-source provider direction confirmed from primary sources:
- **Massive** should be the first-class free IPO provider:
  - the Stocks docs expose `GET /vX/reference/ipos`
  - the endpoint is marked as included in **Stocks Basic Free**
  - docs describe both **upcoming and historical** IPO events starting from **2008**
  - docs expose statuses such as:
    - `rumor`
    - `pending`
    - `new`
    - `history`
    - `postponed`
    - `withdrawn`
    - `direct_listing_process`
  - docs also expose pagination and sort/order controls, so this can support both:
    - daily forward polling
    - backfill of historical IPOs for research/audit
- **Alpha Vantage** is a sensible free complementary provider:
  - docs expose `function=IPO_CALENDAR`
  - docs state it returns IPOs expected in the **next 3 months**
  - this is CSV-based and easy to ingest cheaply
  - Alpha Vantage also exposes `EARNINGS_CALENDAR` with `3month`, `6month`, and `12month` horizons, which is useful for broadening the same market-events subsystem beyond IPOs
  - Alpha Vantage `LISTING_STATUS` is also useful as a **post-listing reconciliation feed**, not a forward calendar:
    - use it to confirm when a previously future/pending IPO instrument has actually entered the listed universe
    - use it to enrich exchange / active-status / listing-date metadata after first trade support appears
    - do not confuse it with a future event source; it is for instrument-master follow-through after the event
- **SEC EDGAR** should be treated as a free **pipeline/enrichment source**, not the canonical IPO calendar:
  - SEC search/filings tools and APIs give us free access to registration/prospectus workflows
  - this is useful for tracking forms such as:
    - `S-1`
    - `S-1/A`
    - `F-1`
    - `F-1/A`
    - `424B*`
  - this will help us detect issuers moving through the IPO funnel earlier than a structured calendar sometimes will
  - but EDGAR should not be presented as an exact listing-date authority because it is filing-driven, not listing-calendar-driven
- **Massive market-holiday data** is also worth folding into the same subsystem:
  - `GET /v1/marketstatus/upcoming` is forward-looking and included in Stocks Basic Free
  - this is not an IPO feed, but it is a good example of a free market-calendar input that belongs in the same page/widget layer
- **Finnhub** can be kept as an evaluation candidate, not a committed provider yet:
  - official docs expose `/calendar/ipo?from=...&to=...`
  - Finnhub also offers a free API key
  - but we should not commit to building against it until we explicitly verify that the free tier truly allows this endpoint in practice and with acceptable quotas/terms

Product goals:
- Build a **forward market-events calendar** that is broader than today’s instrument-specific event history.
- Make IPOs a first-class event family with both:
  - calendar-facing UX
  - instrument-universe bootstrap implications
- Ensure this subsystem explicitly answers two different user questions:
  - **what is coming up?**
  - **what newly tradable instruments should now exist in our universe?**
- Support both:
  - a full page
  - a compact widget
- Treat this subsystem as part of both:
  - market research / monitoring
  - instrument-master / discovery

What remains:

- Add a new provider capability for **forward market events**, distinct from the current instrument-event history model:
  - examples:
    - `market_event_calendar`
    - or a clearly named equivalent
  - do not overload the current per-instrument event fetch path with market-wide future events
  - allow multiple providers to contribute to the same normalized market-event feed

- Add provider implementations for the free sources that actually make sense:
  - `massive`
    - ingest `reference/ipos`
    - support status filtering and pagination
    - store the provider payload and provider-specific status semantics
    - use this as the primary free IPO backbone
  - `alphavantage`
    - ingest `IPO_CALENDAR`
    - later also ingest `EARNINGS_CALENDAR` into the same broader market-events system
    - ingest `LISTING_STATUS` into the instrument-master follow-through side so future IPO placeholders can be promoted once the listing is real
    - normalize CSV payloads into the same event schema
  - `edgar`
    - add a supplementary IPO-pipeline detector for filings such as `S-1`, `S-1/A`, `F-1`, `F-1/A`, `424B*`
    - use this to enrich “watchlist of possible upcoming listings” rather than to claim exact listing dates
  - optionally `finnhub`
    - only after free-tier access is explicitly validated in practice
    - if validated, use it as another corroborating structured IPO source, not as the sole source of truth

- Introduce a normalized **market event** model that is not equity-price-history-centric:
  - event family:
    - `ipo`
    - `direct_listing`
    - `market_holiday`
    - later:
      - `earnings_calendar`
      - `fed/cpi/macro`
      - `lockup_expiry`
      - `index_rebalance`
      - `etf_rebalance`
  - event dates/timestamps:
    - announced date
    - expected listing date
    - actual listing date
    - last updated timestamp
  - lifecycle/status:
    - rumor
    - pending
    - priced
    - new/live
    - history/completed
    - postponed
    - withdrawn
    - direct listing
  - identifiers:
    - provisional ticker
    - issuer name
    - exchange / MIC
    - ISIN / CUSIP / other identifiers where available
    - SEC CIK / filing references where available
  - economics:
    - expected price range
    - final issue price
    - shares offered
    - offer size
    - currency
  - provenance:
    - source provider
    - source URL
    - raw payload snapshot
    - confidence / reconciliation state

- Build a reconciliation strategy across providers so we do not create duplicate IPO events or duplicate future instruments:
  - match first by:
    - ISIN
    - CUSIP
    - CIK
    - exchange + ticker + listing date
  - then by conservative issuer-name similarity only as a weaker fallback
  - keep provider-specific aliases and raw source ids for auditability
  - preserve conflicting provider claims instead of silently overwriting them

- Materialize **pre-listing instruments** as a first-class concept:
  - upcoming IPOs should be able to create instrument records before bars exist
  - these should be clearly marked as:
    - pre-listing / pending
    - not chartable yet if no price history exists
    - event-driven / future-facing rather than provider-price-history-backed
  - when the instrument actually lists and our normal instrument providers begin supporting it:
    - reconcile the pre-listing placeholder with the real listed instrument
    - preserve the IPO event history and source provenance
  - this should directly improve the instrument universe by letting us know about new tickers before first trade data arrives
  - the reconciliation flow should intentionally combine:
    - future event sources (Massive / Alpha IPO calendar / EDGAR pipeline)
    - post-listing confirmation sources (Alpha `LISTING_STATUS`, normal instrument search/materialization, regular metadata providers)
  - this lets us support the whole lifecycle:
    - rumor / pending
    - expected listing
    - listed but still thinly-covered
    - fully normal instrument in the broader platform

- Extend the calendar UX from instrument-specific history into a **market-wide forward planner**:
  - page:
    - list/calendar timeline of upcoming IPOs and other future market events
    - filters by event type, date range, exchange, status, and provider
    - sort by expected date, provider update recency, or event importance
    - search by issuer name, ticker, or identifier
  - widget:
    - compact “upcoming IPOs / market events” surface for dashboard use
    - configurable horizon such as:
      - 1 week
      - 1 month
      - 3 months
    - should be able to exist both:
      - as a general market-events widget
      - as a narrower “upcoming IPOs” widget for users specifically tracking future listings
  - interaction:
    - clicking a future IPO instrument should open its instrument details page if no chart exists yet, and the chart only once price history exists
    - hovering/clicking a market event should expose provenance and confidence:
      - which provider(s) reported it
      - whether the date is tentative or confirmed
      - whether the instrument is already listed in our master

- Make the subsystem useful for portfolio/risk workflows:
  - let users inspect upcoming IPOs and future event clusters by date
  - later allow strategies/radar/alerts to pause or adapt around forward event windows
  - surface event density such as:
    - many IPOs this week
    - major holiday-shortened week
    - large concentration of future earnings in selected watchlists
  - allow simple “watch ahead” workflows such as:
    - all upcoming IPOs in the next 14/30/90 days
    - all pending listings that do not yet exist as normal instruments
    - all events affecting a chosen exchange or watchlist
    - all events whose dates or statuses changed since last refresh

- Add explicit coverage semantics so users know how far ahead each provider can see:
  - Massive IPO coverage:
    - structured historical + upcoming, with status lifecycle
  - Alpha Vantage IPO coverage:
    - next 3 months only
  - Alpha Vantage earnings coverage:
    - 3/6/12 month forward windows
  - Alpha Vantage listing-status coverage:
    - post-listing universe confirmation, not a future-calendar source
  - EDGAR pipeline coverage:
    - filing-driven, not guaranteed listing-date accuracy
  - the UI should not pretend that all providers offer the same horizon or confidence
  - the UI should also clearly distinguish:
    - **future calendar confidence**
    - **instrument-master readiness**
    - **price-history readiness**

- Keep geography segmented in the design:
  - implement US first
  - keep provider/region fields in the schema so we can later add:
    - EU IPO/event sources
    - APAC IPO/event sources
  - do not hard-code the model to US-only assumptions even though the first provider stack will be US-heavy
  - for now, explicitly document that:
    - reliable free structured forward IPO coverage is strongest for the US
    - EU / APAC support should remain adapter-ready in the schema but not be promised until solid free sources are identified

Why this was deferred:
- The platform already has the beginnings of a calendar/event story, but not the forward-looking market-wide event model this needs.
- The best free implementation is broader than “just add one endpoint”; it touches:
  - providers
  - storage
  - instrument discovery/materialization
  - dashboards
  - calendar UX
  - later strategy/risk workflows
- It deserves a focused implementation pass instead of being quietly bolted onto the existing per-instrument event tables.

### 10. Expand provider chain seeding and scheduling for bulk universe refresh
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

### 11. Custom instrument baskets, ETF holdings navigation, and breadth analysis
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
- Baseline basket persistence and user-owned CRUD now exists:
  - `basket` and `basket_member` models support user-owned manual baskets and read-only system-managed ETF-derived baskets
  - manual baskets can be created, updated, listed, read, and deleted through authenticated APIs
  - member edits replace the full member set and require existing resolved instruments; arbitrary/unresolved typed symbols are rejected at the API boundary
  - equal-weight baskets store null member weights and can be interpreted as 1/N downstream
  - custom-weight baskets require every member to provide a weight and the weights must sum to 1.0
  - duplicate instruments are rejected
  - read-only/system-managed baskets cannot be edited or deleted through the manual basket API
  - auto-classification currently sets sector/industry when all members share the same metadata values
- Strategy Lab can now use a basket as a static universe through `universe_config.basket_id`, including coverage preview, saved strategy versions, run execution, and run-subset restriction to basket members.
- Still expand the basket API beyond the baseline where needed:
  - partial member operations if the UI benefits from add/remove/reweight endpoints rather than full member replacement
  - market-cap-weighted basket semantics once reliable constituent market-cap data is available
  - richer classification labels/tags for mixed-sector/thematic baskets
- Basket synthetic OHLCV now exists on the backend:
  - `GET /api/v1/baskets/{basket_id}/ohlcv/{timeframe}` returns a rebased-to-100 weighted cumulative-return series using aligned member OHLCV bars
  - equal-weight baskets are interpreted as 1/N
  - custom/source-weight baskets normalize explicit weights before computing the series
  - the first viable aligned bar is 100, making basket behavior easy to compare against constituent or benchmark returns
  - still wire this endpoint into the main Chart view so users can open a basket as a normal chart surface

Frontend:
- Strategy Lab now exposes Basket as a universe type and persists/loads `basket_id` from the visual builder.
- A dedicated basket builder UI now exists at `/baskets` and is accessible from the sidebar:
  - list manual and ETF-derived baskets
  - create new user-owned baskets
  - add instruments through the platform search picker
  - choose equal or custom weighting
  - edit custom weights with a real-time allocation indicator and sum validation
  - delete manual baskets through a platform modal
  - display ETF-derived baskets as read-only system-managed baskets
- Weight editor still needs richer interaction if useful:
  - drag/reorder members
  - bulk equalize/rebalance helper
  - optional add/remove/reweight actions that do not require replacing the entire member set
- Basket detail view: list all members, their weight, and a sparkline or mini-stat row per member.
- Ability to open a basket in the chart view as a synthetic price series.

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
- ETF holdings are also an important low-cost proxy for index-constituent universes:
  - exact historical index membership, such as Russell 3000 constituents, is often licensed and expensive
  - ETF issuers frequently disclose current holdings, and regulatory filings can provide historical holdings snapshots
  - this gives the platform a practical starter path for "close enough" index-universe workflows without requiring expensive index-data contracts on day one
  - the product must clearly label these as ETF-holdings proxy universes, not official index-constituent universes

What remains:

Implementation status:
- Baseline ETF holdings infrastructure now exists:
  - persistent ETF profile, raw artifact, holdings snapshot, holding row, adapter-state, and ETF/index-proxy mapping tables
  - authenticated APIs for listing/searching ETFs with holdings, latest snapshots, available dates, nearest point-in-time snapshots, constituent timelines, unresolved rows, requested-range coverage summaries, manual ingestion, CSV ingestion, ETF profile routing updates, and manual refresh triggering
  - canonical parser support for common issuer CSV exports and simple XLSX/OpenXML holdings workbooks
  - metadata-only lightweight materialization of ETFs and holdings constituents through the existing instrument mastering model
  - explicit source/provenance fields, `as_of_date`, `known_at`, `published_at`, source quality, completeness, raw artifact retention, and adapter health tracking
  - scheduled refresh hook behind `ETF_HOLDINGS_REFRESH_ENABLED`
  - a usable free-source baseline where ETF profiles refresh through provider-specific holdings adapters instead of arbitrary profile-level download URLs
  - Chart page holdings panel with source/freshness/resolution metadata, filter/sort, selected holding details, previous/next navigation, and explicit constituent open actions
  - Strategy Lab can use ETF holdings as a strategy universe through the visual builder:
    - latest available snapshot mode
    - latest snapshot on/before a chosen date
    - dynamic point-in-time mode for rules backtests, where membership is filtered by the latest holdings snapshot known at each bar date
    - an explicit dynamic-universe constituent-removal policy for leaving positions open at the last eligible mark or realizing them as `constituent_removed` exits
    - dynamic-run result attribution with `dynamic_universe` snapshot metadata plus execution-log fields that identify the ETF snapshot, composition date, known-at timestamp, and membership status behind entries/removal exits
    - baseline frontend surfacing of dynamic membership attribution in the Strategy Lab execution log reason cell and reason filter search values
  - ETF holdings snapshots can be materialized into read-only, system-managed baskets through the backend basket model and API
  - user-owned manual basket CRUD exists on the backend, and Strategy Lab can consume baskets as static universes through the visual builder
  - ETF-derived system baskets can opt into dynamic ETF history in Strategy Lab through `universe_config.basket_snapshot_mode = "dynamic"`; this delegates point-in-time membership to the basket's source ETF holdings profile instead of treating the materialized basket as only a frozen member list
  - user-owned/manual baskets now persist composition snapshots on create/update and expose basket snapshot history through the backend API
  - Strategy Lab can opt manual baskets with stored composition snapshots into dynamic point-in-time replay through `basket_snapshot_mode = "dynamic"`
  - a basket builder/editor workspace now exists for user-owned baskets, and ETF-derived baskets are visible as read-only entries
  - a first backend basket synthetic OHLCV endpoint exists for rebased-to-100 basket return series
  - Chart can open basket synthetic series through `/chart/BASKET:{id}` from the basket builder, using the backend weighted basket OHLCV endpoint without treating the basket token as a normal watchlist/recent instrument
  - an adapter registry seam exists; only concrete provider-specific ETF issuer adapters are registered, and adapter-state health is persisted per profile/provider
  - issuer-aware CSV adapter routes now exist for major issuer keys:
    - ETF profiles can resolve holdings downloads from explicit issuer URLs, URL templates, issuer product ids, and issuer-specific file names instead of requiring every route to be stored as a raw `holdings_url`
    - ETF profiles can also provide issuer product/fund page URLs; the adapter can discover linked CSV/XLSX holdings files from those pages and then ingest the resolved file
    - ARK-style holdings file-name route construction is implemented against ARK's current public `assets.ark-funds.com` CSV files for known ARK ETF symbols
    - iShares/BlackRock product-id and State Street/SPDR symbol-based daily workbook routes are implemented as backend-reachable public constructors
    - issuer product-page discovery is implemented for explicit product URLs and for candidate symbol-addressable page templates; only backend-reachable routes should be treated as ready after live/provider probing
    - current backend-reachable live-tested issuer routes cover SPDR, iShares/BlackRock, ARK, VanEck, and Global X; these are the only issuer adapters currently treated as supported default routes
    - iShares/BlackRock now uses the current BlackRock product-data JSON holdings API for live-backed default routes; tested seeded product ids include IVV and IWM, so selecting IWM can bootstrap a full holdings snapshot on an empty branch instead of falling back to top-holdings page data
    - the live provider test matrix covers every registered issuer adapter, either as a successful backend-reachable route or as an explicit candidate-route gap, so unsupported providers cannot silently masquerade as supported
    - Invesco has an explicit JSON parser for configured source URLs, but its currently embedded public `dng-api` holdings endpoint returns HTTP 406 to backend requests and must not be auto-advertised as ready
    - Vanguard and Schwab candidate product pages remain useful routing hints, but backend-reachable full-holdings extraction is not yet live-proven and should remain a provider-support gap until current public routes can be fetched and parsed reliably
    - the intended architecture is one provider-specific implementation per ETF issuer/provider, just like market-data providers; explicit product URLs, issuer discovery feeds, and profile-level URL templates remain useful provider-configuration seams while that provider-specific catalogue is built, but they are not a substitute for claiming provider support
    - each provider implementation should be promoted to supported only when backend-reachable live tests prove that the provider-specific route fetches full holdings reliably
    - issuer adapters probe whether enough route metadata exists before refresh, and profiles without enough metadata are marked as needing issuer route configuration instead of silently pretending refresh support exists
    - admin `POST /api/v1/etf-holdings/{symbol}/probe-adapter` exposes route-readiness status, resolved source URL, confidence, and missing identifier requirements before a refresh is attempted
    - fetched issuer artifacts now run through explicit identity validation before ingestion:
      - ETF profiles can provide expected artifact identifiers such as expected ETF/fund symbol, name, CUSIP, or ISIN through `provider_aliases`
      - if expected identifiers are configured, the raw downloaded artifact must contain at least one of them before a snapshot is stored
      - generic downloaded table metadata extraction can infer ETF identity from conservative source fields such as two-column preamble metadata or explicit `Fund Ticker` / `ETF Name` style columns, while ignoring generic constituent `Ticker` columns
      - matched/unverified validation status is stored in snapshot/raw-artifact legal metadata for auditability
      - mismatched artifacts fail refresh rather than silently creating a holdings snapshot for the wrong ETF
    - successful issuer-adapter refreshes persist source URL, parser version, row counts, composition date, and adapter-state health
    - failed issuer-adapter refreshes classify common provider blocking/transient states such as HTTP 429, 403, and server/time-out failures into persisted adapter health, and successful retries clear stale rate-limit/blocking state
    - admin `GET /api/v1/etf-holdings/{symbol}/adapter-state` exposes persisted adapter health, including last success/failure, source URL, parser/count metadata, completeness, and rate-limit/blocking state
  - admin SEC N-PORT/N-PORT-P-style XML ingestion now exists as a reconstruction primitive:
    - raw SEC filing XML can be parsed into canonical holdings rows
    - report dates are inferred from the filing where possible
    - CUSIP/ISIN/SEDOL, shares, market value, currency, asset category, and percent-of-value weights are normalized where present
    - snapshots are stored as `sec_nport_reconstructed_holdings` with filing source identifiers, source URL, raw XML, and known/published timestamps preserved
  - admin legacy SEC N-Q/N-CSR-style XML/table ingestion now exists as an older-history reconstruction primitive:
    - simple table-like legacy filing XML can be parsed into canonical holdings rows
    - period/report dates, CUSIP/ISIN/SEDOL, shares, market value, currency, asset/security type, and percent-of-net-assets weights are normalized where present
    - snapshots are stored as `sec_legacy_reconstructed_holdings` with filing source identifiers, source URL, raw XML, and known/published timestamps preserved
  - an admin EDGAR N-PORT backfill primitive now exists:
    - ETF profiles with `sec_cik` can query SEC submissions metadata for recent N-PORT filings and older SEC submissions `files` archive pages
    - discovered N-PORT primary XML documents are downloaded, parsed, and ingested through the same filing-reconstructed holdings path
    - discovered legacy N-Q/N-CSR-style primary XML/table documents are downloaded, parsed, and ingested through the legacy filing-reconstructed holdings path
    - backfill jobs and accession-level filing state are persisted, making repeated backfills duplicate-safe and auditable
    - per-run summaries report discovered, ingested, skipped, and failed filings, with admin endpoints to inspect recent jobs and per-filing state
    - a bulk/admin SEC backfill endpoint and scheduled worker hook exist for processing ETF profiles with configured SEC CIKs under bounded limits
  - Screener and Radar can consume manual or ETF-derived baskets as universe inputs, alongside Strategy Lab basket/ETF snapshot universe support
  - Screener and Radar now expose frontend controls for selecting manual or ETF-derived baskets as run universes:
    - Screeners can save/load basket universes from the visual builder through `universe_basket_id`
    - Radar can run scans against either all instruments or a selected basket through the existing run action
  - the Chart ETF holdings panel now provides a compact browse workspace rather than only a flat table:
    - users can select a holding and inspect mini-stats such as weight, market value, shares, venue, identifiers, row type, resolution state, and resolution notes
    - users can move through the currently filtered/sorted holdings with previous/next controls
    - opening a constituent chart is now an explicit action from the selected holding details
  - a dedicated `/etf-holdings` browse workspace now exists for larger holdings lists:
    - ETF profiles with stored holdings can be searched and selected from a dedicated holdings surface
    - holdings rows are loaded through a server-side paginated/searchable/sortable API instead of requiring the frontend to load the whole snapshot
    - users can page through holdings, search by symbol/name/CUSIP/ISIN/SEDOL, sort by position/weight/value/shares/symbol/name/resolution, inspect selected holding details, and open a constituent chart
    - users can compare the selected snapshot against another stored snapshot to inspect holdings additions, removals, and weight changes through a dedicated diff view
    - the diff workspace now includes a first cross-snapshot research-summary layer with gross churn, total added/removed weight, total upweights/downweights, and largest additions/removals/reweights
    - the workspace now includes a first weight-evolution panel that ranks top constituent weight movers across stored snapshots and shows each mover's weight path over the available snapshot range
    - constituent timeline API responses now include per-point weight delta from the previous observed snapshot, making individual constituent reweighting paths inspectable without client-side recomputation
    - the workspace now includes a first turnover timeline that batch-navigates adjacent historical snapshots and summarizes each transition's churn, additions, removals, reweights, and top movers without requiring users to manually compare every pair
    - cross-ETF overlap analytics now exist through `POST /api/v1/etf-holdings/overlap-summary`, comparing selected ETF snapshots for shared/unique constituents, Jaccard overlap, shared weight, minimum-overlap weight, and top shared holdings
    - many-ETF overlap matrix analytics now exist through `POST /api/v1/etf-holdings/overlap-matrix`, returning row/column ETF symbols, per-cell overlap metrics, closest/most-distinct peers, and highest/lowest overlap pair callouts for heatmap-style research
    - overlap matrix requests can now expand their ETF set from profile metadata such as issuer, fund family, and search query instead of requiring every ETF symbol to be listed manually
    - the ETF holdings workspace now exposes a first compact overlap panel where users can select peer ETFs from the loaded profile list and inspect pairwise overlap cards plus a heatmap-style overlap matrix
    - the overlap panel also exposes a first issuer/family/search expansion flow for server-side overlap matrix comparisons without manually selecting every ETF
  - Remaining work is now primarily about downstream consumption and long-tail source maintenance:
    - source hardening baseline is now in place:
      - issuer adapters reject malformed/empty holdings artifacts instead of silently creating useless snapshots
      - adapter failure state distinguishes provider blocking/rate limits from parse/malformed failures
      - common issuer schema variants are normalized beyond the initial ticker/name/weight shape, including security identifier/CUSIP-like columns, issuer/title fields, fund weight aliases, shares/principal aliases, market-value aliases, local currency, country, exchange, cash rows, accounting negatives, and disclaimer-row skipping
      - legacy SEC parsing handles simple XML/table filings, simple HTML tables, split identity/value rows, month-name report dates, accounting negatives, and value-in-thousands schedules
      - ZIP/XLSX/CSV issuer artifacts, product-page discovery, fetched-artifact identity validation, route probes, adapter catalog inspection, and persisted adapter health form the current robustness baseline
    - remaining source work is long-tail maintenance rather than a core gap: unusual issuer-specific schemas, non-tabular/PDF-like disclosures, automatic website discovery beyond explicit configured feeds, and extra direct-download constructors where product-page discovery or configured feeds prove insufficient
  - richer Chart basket UX beyond the initial synthetic series route, such as synthetic basket metadata and better comparison/watchlist semantics
  - dynamic point-in-time Strategy Lab ETF/basket universes that rebalance through historical holdings snapshots during simulation, rather than using only a static snapshot
    - implemented ETF holdings baseline: Strategy Lab rules backtests can opt into `universe_config.etf_holdings.snapshot_mode = "dynamic"` from the visual builder to resolve the latest point-in-time ETF holdings snapshot for each bar date, avoiding look-ahead by honoring snapshot `known_at`
    - implemented ETF-derived basket baseline: Strategy Lab can save/load an ETF-derived basket with `basket_snapshot_mode = "dynamic"` and replay the source ETF profile's point-in-time holdings snapshots during rules backtests
    - implemented manual basket-history baseline: manual basket create/update operations persist composition snapshots, and Strategy Lab can replay those basket snapshots point-in-time when `basket_snapshot_mode = "dynamic"`
    - implemented ETF constituent-removal policy: dynamic ETF runs can either leave positions open at the last eligible mark or realize them as `constituent_removed` exits when the ETF no longer carries that instrument by run end
    - implemented baseline dynamic attribution: result summaries include the dynamic ETF snapshot set, execution-log rows include snapshot/membership fields showing which point-in-time ETF holdings snapshot drove entries and removal exits, and the Strategy Lab execution log surfaces this context compactly
    - still needed: richer basket rebalance policy controls, historical basket snapshot editing/import UX, and deeper attribution drilldowns/specialized filtering beyond the baseline execution-log context
  - richer cross-snapshot/cross-ETF holdings research beyond the current diff/summary, turnover timeline, top-mover weight-evolution views, constituent timeline deltas, overlap matrix API with issuer/family/search expansion, and compact overlap/matrix/family panel, especially saved comparison sets and deeper exposure clustering

Data / provider side:
- Implement ETF holdings ingestion as a **free-source-first** capability, not as a dependency on a paid holdings aggregator:
  - the platform should be able to build a useful ETF holdings database using public issuer disclosures and SEC filings before any paid holdings API is considered
  - paid API aggregators such as FMP, EODHD, Alpha Vantage, Finnhub, or ETF.com-style datasets can remain optional future accelerators/fallbacks, but should not be required for the baseline feature
  - premium official index constituent providers should be reserved only for workflows that explicitly require exact point-in-time index membership rather than ETF-holdings proxy membership
  - this roadmap item should therefore be treated as a real ingestion product, not merely a wrapper around one commercial data provider
- Split the ETF holdings problem into two complementary free-source tracks:
  - **historical backfill from SEC/EDGAR-hosted filings**
    - use SEC N-PORT / N-PORT-P structured data as the primary free structured historical source from the N-PORT era
    - use legacy SEC filings such as N-Q and N-CSR where practical to reconstruct older lower-frequency holdings history before N-PORT
    - preserve the fact that SEC-derived history is filing/reported holdings data, not official index membership
    - preserve both the holdings `as_of_date` and the date the filing became publicly available / known to the platform so Strategy Lab can avoid look-ahead bias
    - expect SEC backfills to be lower-frequency and delayed relative to issuer daily/weekly holdings files
    - treat SEC backfill parsing as a separate pipeline from issuer-current ingestion because the schemas, file formats, timing, and quality controls are different
    - baseline N-PORT/N-PORT-P XML parsing, manual/admin ingestion, recent and archived SEC submissions discovery/download ingestion, scheduled/bulk backfill hooks, and persistent accession/job dedupe now exist
    - baseline N-Q/N-CSR-style legacy XML/table parsing and manual/admin ingestion now exists for older pre-N-PORT history
    - baseline legacy SEC HTML schedule-of-investments table parsing now exists for simple EDGAR HTML filings with recognizable issuer/ticker/CUSIP/shares/value/percent columns
    - legacy SEC HTML parsing now also handles a common split-row schedule shape where security identity/CUSIP appears in one row and shares/value/percent appear in the following numeric row
    - automated EDGAR discovery/download/backfill orchestration for legacy N-Q/N-CSR-style filings now exists, including duplicate-safe accession state and bulk processing
    - still broaden legacy parser coverage for additional filing/table shapes, deeply nested/footnoted HTML filings, and PDF-like documents beyond the simple HTML table path
  - **forward daily/weekly snapshots from ETF issuer/provider disclosures**
    - build individual adapters for major US ETF issuers and fund families that publish holdings files or holdings pages
    - target iShares/BlackRock, State Street/SPDR, Vanguard, Invesco, Schwab, First Trust, Global X, VanEck, ARK, WisdomTree, ProShares, Direxion, JPMorgan, Dimensional, PIMCO, Franklin, Fidelity, and other large US-listed ETF sponsors over time
    - let each adapter understand that issuer's own URL structure, downloadable file formats, date fields, disclaimers, cash rows, derivative rows, currency fields, and naming conventions
    - store raw downloaded files/pages/artifacts before normalization so parser changes can be audited and historical ingestions can be replayed
    - schedule refreshes daily where the issuer appears to publish daily holdings, and weekly where daily refresh is unnecessary or not reliably available
    - keep the adapter framework tolerant of issuer website changes, because free public issuer files are valuable but brittle
- Provider-specific holdings adapter framework status:
  - a registry and common adapter interface now exists
  - the previous `configured_csv_url` fallback has been retired; arbitrary profile-level download URLs are not treated as provider support
  - major issuer adapter keys now use isolated provider-specific route adapters that resolve from that provider's own known route shape, product ids, issuer-specific file-name hints, or product-page discovery
    - issuer-aware adapters can now discover linked holdings CSV/XLSX/ZIP files from configured issuer product/fund page URLs before ingesting
    - product-page holdings discovery now scans conservative URL-bearing attributes and quoted page configuration strings, not only literal anchor `href` links, while still requiring holdings/portfolio/constituent file hints
  - concrete issuer-specific URL constructors now exist for:
    - ARK file-name based public CSV holdings files
    - iShares/BlackRock product-id based public CSV holdings files
    - State Street/SPDR symbol-based public daily holdings XLSX files
  - inferred issuer product-page templates now exist for:
    - Global X symbol-addressable fund pages, currently live-tested through product-page discovery
    - VanEck symbol-addressable holdings/download routes, currently live-tested through deterministic holdings workbook download
    - Vanguard symbol-addressable ETF profile pages as candidate route hints only, pending backend-reachable holdings extraction
    - Schwab symbol-addressable product pages as candidate route hints only, pending backend-reachable holdings extraction
    - Invesco explicit holdings source URLs through the JSON parser only; automatic backend route support is not currently live-backed because the embedded public API returns HTTP 406 to backend requests
  - admin route-readiness probing exists and persists adapter-state health for ready and under-configured profiles
  - admin adapter-state inspection now exposes persisted adapter health, including HTTP rate-limit/blocking classification from failed refreshes and clearing on successful retry
  - admin adapter-catalog inspection now exposes registered adapter keys, route identifiers, required identifiers, supported artifact formats, parser confidence, and explicit dated-fetch/ETF-discovery capability flags
  - issuer adapters now support explicit dated holdings URL templates, allowing admin-triggered fetch/ingest for a requested composition date when an issuer archive URL pattern is known
  - issuer adapters now support explicit issuer fund-list discovery feeds:
    - admin `POST /api/v1/etf-holdings/discover` can fetch a configured issuer CSV/XLSX/ZIP fund-list feed, parse ETF identity/route columns, materialize lightweight ETF instruments, and upsert ETF profiles
    - discovered profiles preserve issuer product ids, product URLs, holdings URLs, dated holdings URL templates, CUSIP/ISIN identifiers, discovery source URLs, and the raw discovery row in profile metadata
    - discovered profiles now also preserve SEC CIK/series/class ids and FIGI/composite/share-class FIGI aliases where the fund-list feed provides them, keeping issuer discovery connected to EDGAR backfills and instrument mastering
    - this is a deliberate explicit-feed ingestion path, not automatic broad website crawling or guessed ETF discovery
  - explicit fetched-artifact identity validation exists for profiles that provide expected fund identifiers
  - conservative generic fetched-artifact identity extraction exists for preamble metadata and explicit fund/ETF identity columns in downloaded table files
  - simple XLSX/OpenXML holdings workbooks and ZIP archives containing CSV/XLSX holdings files now ingest through the same common parser/identity-validation path without adding a spreadsheet dependency
  - source-hardening baseline is now in place:
    - malformed/empty issuer artifacts fail refresh and persist adapter failure state instead of producing empty snapshots
    - common issuer schema aliases, CUSIP-like security identifiers, cash rows, accounting negatives, and non-holding disclaimer rows are handled by the common parser
    - SEC legacy reconstruction handles simple XML/table filings, simple HTML tables, split identity/value rows, month-name dates, and value-in-thousands schedules
    - live issuer smoke tests now exist behind `RUN_LIVE_ETF_HOLDINGS_TESTS=1`, intentionally separated from deterministic CI so provider drift can be checked against real issuer websites/files without making the normal suite network-dependent
    - current live suite passes against backend-reachable public issuer routes for SPDR, iShares, ARK, Global X, and VanEck; iShares has an inline top-holdings parser for the current HTML-shell response, ARK uses its public assets CSV files, and VanEck uses its deterministic holdings workbook download route
  - still ongoing as source-coverage work, not merely incidental maintenance: unusual issuer-specific schemas beyond the common parser, richer issuer-specific identity extraction for non-tabular pages/PDFs/unusual issuer metadata formats, direct-download/API constructors for issuers where product-page discovery is insufficient, automatic issuer-specific historical-date discovery beyond explicitly configured dated URL templates, automatic per-issuer ETF discovery beyond explicit configured fund-list feeds, and backend-reachable live routes for currently blocked/non-static issuers such as Vanguard, Schwab, Invesco, First Trust, WisdomTree, ProShares, Direxion, JPMorgan, Dimensional, PIMCO, Franklin, and Fidelity
- Continue expanding the provider-specific holdings adapter framework:
  - each adapter should expose a common interface:
    - discover supported ETFs
      - implemented baseline: adapters can ingest explicitly configured issuer fund-list discovery feeds through the admin discovery endpoint, parse common ETF identity/route columns, and upsert ETF profiles without relying on ticker-only guessing
    - resolve issuer product id / slug / URL for a known ETF
    - fetch latest holdings
    - fetch holdings for a specific date when the issuer supports it
      - implemented baseline: issuer adapters can fetch a specific date from an explicit profile-level dated URL template using placeholders such as `{date}`, `{date_yyyymmdd}`, `{year}`, `{month}`, and `{day}`
    - parse raw holdings into canonical rows
    - report source metadata and parser confidence
    - probe whether an ETF belongs to that issuer/provider path
  - adapter output should normalize:
    - constituent symbol
    - constituent name
    - CUSIP / ISIN / SEDOL where available
    - weight
    - shares held
    - market value
    - asset class / holding type
    - currency
    - country / exchange where available
    - cash, futures, swaps, options, collateral, and other non-equity rows
    - source row id / source row hash
      - implemented: holdings rows persist a per-snapshot `source_row_hash` and expose it through API outputs for audit/replay tooling
  - adapter output should also preserve source-specific fields that do not fit the canonical schema yet so we do not throw away useful data too early
  - implemented for observability: admin adapter-catalog endpoint reports source metadata, parser confidence, supported formats, route identifiers, and which interface capabilities are still unavailable per adapter
- Add an ETF identity and adapter-routing layer so the platform knows which free issuer/provider path to use for each ETF:
  - never infer issuer solely from ticker
  - master each ETF using the existing instrument identity model plus ETF-specific identifiers:
    - symbol
    - exchange / MIC
    - fund name
    - issuer / sponsor / adviser / fund family when known
    - CUSIP
    - ISIN
    - FIGI / composite FIGI / share-class FIGI where available
    - SEC CIK
    - SEC series id
    - SEC class id
    - provider aliases and issuer product ids
    - implemented baseline: explicit issuer discovery feeds can now populate SEC CIK/series/class ids plus FIGI/composite/share-class FIGI aliases when those columns are present
  - use market-data-provider metadata as a candidate signal when it includes issuer/fund-family/sponsor fields
  - use SEC Investment Company Series/Class data as a canonical US fallback for ticker-to-CIK/series/class mapping
    - implemented baseline: admin `POST /api/v1/etf-holdings/discover-sec-funds` ingests SEC `company_tickers_mf`-style ticker mappings, materializes lightweight ETF instruments, and upserts ETF profiles with SEC CIK/series/class ids for EDGAR backfill routing
    - the SEC discovery endpoint supports the default SEC public file plus an explicit `source_url` override for mirrors/fixtures, and accepts both keyed-object and `fields`/`data` payload shapes
  - use identifier resolvers such as OpenFIGI where available to reconcile CUSIP/ISIN/FIGI/ticker/exchange aliases
  - maintain an issuer adapter registry with confidence-scored matchers:
    - exact issuer id / fund-family match
    - SEC registrant/fund family match
    - issuer product id match
    - domain/URL match
      - implemented: configured ETF profile/product/holdings URLs now contribute confidence-scored domain matching for known issuer adapters without falling back to ticker-only guessing
    - name-pattern match as a last resort only
  - after selecting an adapter, run a lightweight probe before ingesting holdings:
    - implemented: route-readiness probe that reports adapter status, confidence, resolved source URL, and missing route identifiers
    - implemented: fetched-artifact validation for explicitly configured expected ETF/fund name, symbol, CUSIP, or ISIN
    - implemented: conservative generic identity extraction from two-column preamble metadata and explicit fund/ETF identity columns in downloaded CSV/XLSX tables
    - still needed: richer issuer-specific automatic identity extraction/probing for non-tabular pages/PDFs and unusual issuer formats
  - if an ETF cannot be routed confidently, mark it as `holdings_adapter_unresolved` rather than silently trying a guessed provider path
- Store adapter/source health and coverage:
  - last successful refresh by ETF and adapter
  - last failed refresh and failure reason
  - source URL / SEC accession / raw artifact id
  - parser version
  - row count
  - resolved constituent count
  - unresolved constituent count
  - apparent composition date
  - observed publication date / ingestion date
  - whether the file appears complete, partial, delayed, empty, or malformed
  - whether the issuer blocks or rate-limits automated access
- Add clear source/provenance semantics for free ETF holdings data:
  - `issuer_current_holdings`: latest free issuer-disclosed holdings file/page
  - `issuer_self_snapshotted_holdings`: point-in-time history accumulated by our scheduled issuer adapters from today onward
  - `sec_nport_reconstructed_holdings`: historical holdings reconstructed from SEC N-PORT / N-PORT-P
  - `sec_legacy_reconstructed_holdings`: older lower-frequency holdings reconstructed from N-Q / N-CSR where practical
  - `paid_api_historical_holdings`: optional commercial source, not required by the free baseline
  - `official_index_constituents`: authoritative licensed index membership, separate from ETF holdings
- Add legal/usage metadata to every source and adapter:
  - public availability does not automatically mean unrestricted redistribution
  - store issuer terms/disclaimer review notes where known
  - distinguish internal research use, user-facing derived analytics, raw holdings redistribution, and commercial resale
  - avoid presenting this feature as "we own/redistribute issuer data" unless licensing has been checked
  - design the platform so we can initially show derived/normalized holdings for product functionality while preserving a path to stricter licensing controls later
- Introduce a scheduled refresh task that updates ETF holdings on a configurable cadence (daily or weekly is likely sufficient for non-leveraged index funds).
- Model ETF holdings as a special case of basket: a system-managed basket with a reference to the source ETF instrument, a composition_date field, and a flag distinguishing user-owned baskets from ETF-derived baskets.
- Persist ETF holdings snapshots over time instead of overwriting only the latest composition:
  - ETF instrument id
  - constituent instrument id
  - reported constituent symbol/name at source
  - weight
  - shares held where available
  - market value where available
  - cash/derivative/other holding classification where available
  - composition date
  - source/provider
  - ingestion timestamp
  - source file/report identifier where available
  - confidence/provenance flags
- Support multiple holdings-history quality levels and make them visible downstream:
  - `current_issuer_holdings`: latest issuer-published holdings snapshot
  - `self_snapshotted_holdings`: snapshots the platform has collected going forward
  - `filing_reconstructed_holdings`: lower-frequency historical holdings reconstructed from regulatory filings
  - `api_historical_holdings`: provider-supplied historical holdings snapshots
  - `official_index_constituents`: authoritative licensed index membership, when available
- Add explicit caveats and metadata so Strategy Lab, Screener, Radar, baskets, and breadth analysis know whether a holdings-derived universe is:
  - exact enough for navigation and current analysis
  - a reasonable proxy for historical research
  - too sparse/stale for a specific requested backtest date range
  - unsuitable for claims about official index membership
- Model timing carefully:
  - issuer files may be current or previous-close holdings
  - regulatory filings are delayed and should not be treated as known before their filing/public availability date in point-in-time simulations
  - reconstructed historical ETF holdings should preserve both `as_of_date` and `known_at` / `published_at` where available
  - Strategy Lab must avoid look-ahead bias when using historical holdings snapshots as dynamic universes.
- Add provider adapters that can ingest both API responses and downloadable issuer files:
  - normalize source symbols into canonical instruments through the platform's instrument resolver
  - instantiate lightweight instruments for holdings not yet known locally
  - preserve source-specific labels/symbols for auditability
  - record unmatched constituents so users can see which holdings could not be resolved
- For ETF/index proxy workflows, support mapping common index ETFs to their intended benchmark/index:
  - `SPY` / `VOO` / `IVV` as S&P 500 proxies
  - `QQQ` as a Nasdaq 100 proxy
  - `IWV` / `VTHR` or similar as Russell 3000 proxies
  - `IWM` / `VTWO` as Russell 2000 proxies
  - keep this mapping explicit and user-visible, because an ETF proxy is not the same as the official index.

Backend:
- ETF-derived baskets should be read-only from the user's perspective (no user-editable weights).
- Provide an endpoint to list/search ETFs that have holdings data available.
- Provide an endpoint to retrieve the holdings basket for a given ETF instrument.
- Provide an endpoint for the holdings navigation flow: given an ETF instrument id, return a paginated/searchable/sortable member list with weights, instrument details, and optional mini-stats per member.
- Provide endpoints to inspect holdings history and coverage:
  - latest holdings snapshot for an ETF
  - available composition dates for an ETF
  - holdings snapshot nearest to a requested date
  - historical membership timeline for a constituent within an ETF
  - unresolved/unmatched holdings for a provider/source
  - coverage summary showing whether a requested Strategy Lab date range has usable holdings snapshots
- Allow ETF holdings baskets to be used as first-class universes in:
  - Screener (backend/API/engine implemented for basket universes; frontend builder selector implemented)
  - Radar slicing/filtering where appropriate (backend/API/engine implemented for basket universes; frontend scan selector implemented)
  - Strategy Lab snapshot universes (implemented for static ETF holdings snapshots and baskets)
  - Strategy Lab dynamic point-in-time ETF holdings universes for rules backtests (implemented as an opt-in backend baseline using `snapshot_mode = "dynamic"`)
  - Strategy Lab dynamic point-in-time ETF-derived basket universes for rules backtests (implemented by delegating system-managed ETF baskets to their source ETF holdings history)
  - Strategy Lab dynamic point-in-time manual basket universes for rules backtests (implemented through persisted basket composition snapshots)
  - later, richer constituent-exit/rebalance policies and historical basket snapshot editing/import UX

Frontend:
- On the chart page, when viewing an ETF, surface a "Holdings" tab or panel showing the basket composition.
  - implemented: compact Chart panel with source/freshness/resolution metadata, filter/sort, selected holding details, previous/next navigation, and explicit constituent open actions.
- Provide a dedicated holdings browse workspace for larger ETFs:
  - implemented: `/etf-holdings` lists ETFs with stored holdings and loads holdings rows through the server-side paginated/searchable/sortable API.
  - implemented: selected holding details show weight, market value, shares, venue, identifiers, and resolution context.
  - implemented: first-pass holdings churn/addition/removal/reweight summaries and top constituent weight-evolution movers across stored snapshots.
  - still needed: richer market mini-stats such as price, change, distance to 52-week high, volatility, liquidity, and deeper cross-sectional historical analytics.
- The holdings panel should make it easy to open multiple instruments in sequence (e.g., step through constituents one by one) for manual scanning.
  - implemented in the compact Chart panel through previous/next selection controls and explicit constituent chart open actions.
- Later, a "chart all" or "compare all" shortcut that opens a screener-results-like view filtered to the ETF's holdings.
- Show holdings-source and freshness metadata directly in the ETF holdings UI:
  - source/provider
  - composition date
  - ingestion time
  - number of resolved holdings
  - number of unresolved holdings
  - whether the holdings are issuer-current, self-snapshotted, filing-reconstructed, API-historical, or official index constituents
- In Strategy Lab universe selection, allow the user to choose ETF-derived universes with clear semantics:
  - latest ETF holdings snapshot
  - platform-snapshotted point-in-time ETF holdings where available
  - filing-reconstructed holdings where available
  - official index constituents only if a premium source is configured
  - warn when the selected mode is a proxy or when historical coverage is incomplete.
  - implemented backend baseline: `snapshot_mode = "dynamic"` can use historical ETF holdings snapshots during rules backtests.
  - implemented ETF-derived basket baseline: `basket_snapshot_mode = "dynamic"` can use the source ETF holdings profile behind a system-managed ETF basket during rules backtests.
  - implemented manual basket baseline: `basket_snapshot_mode = "dynamic"` can use stored basket composition snapshots for user-authored basket history during rules backtests.
  - still needed: richer UI around historical basket snapshot inspection/import/editing and more detailed dynamic-membership drilldowns in results.

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

#### 10e. Cross-instrument correlation and relationship analysis

Context:
- While strategy-to-strategy correlation belongs primarily in Strategy Lab, we also discussed a separate need for **instrument-level correlation analysis** as a more general market-analysis tool.
- This should not be treated only as a strategy-testing concern. Users may want to answer questions such as:
  - "How correlated are these two instruments over the last 3/6/12 months?"
  - "Which members of this basket are moving most independently from the rest?"
  - "Which instruments are highly correlated so I should avoid doubling the same exposure?"
  - "Which instruments could diversify this watchlist or basket?"
- This feature sits naturally adjacent to baskets, ETF holdings navigation, breadth, watchlists, and Strategy Lab because all of those surfaces benefit from understanding cross-instrument relationships.

What remains:

Backend / analytics:
- Define a reusable correlation-analysis service that can compute, at minimum:
  - return correlation matrices across a selected set of instruments
  - rolling correlations between pairs or groups
  - covariance matrices
  - optionally beta-style relative sensitivity for common benchmark pairs
- Support multiple selectable lookback windows and return granularities so users can compare short-term vs medium-term vs long-term relationships.
- Support applying the service to:
  - arbitrary manually selected instruments
  - watchlists
  - baskets
  - ETF holdings baskets
  - Strategy Lab result universes where useful
- Later, if valuable, extend into adjacent relationship measures such as relative strength, cointegration/pair-candidate analysis, or cluster/group detection.

Frontend / product surfaces:
- A standalone correlation analysis view or panel where users can:
  - pick a set of instruments/watchlists/baskets
  - choose the lookback window and return granularity
  - inspect matrix and pairwise outputs
- Correlation heatmaps and sortable pair tables.
- Rolling pair-correlation charts for selected instrument pairs.
- Cross-basket or watchlist comparison views that highlight concentration vs diversification.
- Later, dashboard widgets for compact correlation snapshots or "top correlated / least correlated" lists.

Why this matters:
- This is useful even outside Strategy Lab because it helps users reason about hidden exposure concentration across watchlists, baskets, and manually selected instruments.
- It also creates a natural bridge into multi-strategy and portfolio-construction research by giving the platform a common language for diversification at both the instrument and strategy levels.

---

#### 10f. Relative Rotation Graph (RRG-style) relative-strength rotation analysis

Context:
- We discussed adding a **Relative Rotation Graph-style** view so users can track relative leadership and rotation across a peer set, with the first practical use case being **S&P sector ETFs** against a common benchmark such as the S&P 500.
- The same capability should then generalize to **any arbitrary basket of instruments**:
  - sector ETFs
  - country ETFs
  - factor ETFs
  - watchlists
  - ETF holdings subsets
  - user baskets
  - later even Strategy Lab result series or platform-owned signal baskets where useful
- Based on the source material we reviewed, the core idea is:
  - compute a **relative-strength series** of each instrument versus a selected benchmark
  - derive a normalized **trend-of-relative-strength** axis (`RS-Ratio`)
  - derive a normalized **momentum-of-relative-strength** axis (`RS-Momentum`)
  - plot each instrument on a two-dimensional plane whose axes cross at a neutral center and whose four quadrants describe the instrument's current relative phase
  - retain a **tail/history** so users can see the recent rotation path, not just the latest point
- The classic quadrant semantics are:
  - `Leading`: strong relative trend and strong relative momentum
  - `Weakening`: strong relative trend but fading relative momentum
  - `Lagging`: weak relative trend and weak relative momentum
  - `Improving`: weak relative trend but improving relative momentum
- The user's intended workflow is tactical sector allocation:
  - compare sector ETFs to a benchmark
  - see which sectors are emerging, rolling over, improving, or deteriorating
  - adjust portfolio positioning based on relative leadership and its evolution through time
- This should be treated as a **market-analysis / cross-instrument analytics** feature first, not only a Strategy Lab concern.

Important implementation note:
- The exact proprietary JdK normalization used in branded/commercial RRG implementations should not be assumed to be freely reproducible unless we intentionally license or explicitly clone it from an allowed/public method.
- Our implementation should therefore be framed as:
  - either a licensed/faithful RRG implementation if we later choose that path
  - or a clearly labeled **RRG-style relative rotation view** built from transparent relative-strength and momentum transforms
- Product naming, disclosure, and UX copy should respect the trademarked nature of `Relative Rotation Graphs` / `RRG` where relevant.

What remains:

Analytics / computation engine:
- Build a reusable **relative-rotation analytics service** that accepts:
  - a benchmark instrument
  - a peer universe of instruments
  - timeframe / bar granularity
  - lookback window
  - tail length
  - sampling frequency for the plotted tail points
- Compute a canonical **relative-strength series** for every instrument versus the benchmark:
  - typically ratio- or return-based relative performance
  - with explicit handling of missing bars, partial overlap, and benchmark/instrument calendar mismatches
  - with consistent point-in-time alignment rules so cross-instrument comparisons are not distorted by stale or shifted bars
- Derive two normalized dimensions per instrument:
  - a **relative-trend dimension** equivalent in spirit to `RS-Ratio`
  - a **relative-momentum dimension** equivalent in spirit to `RS-Momentum`
- Be explicit about the platform math:
  - if we cannot or should not reproduce the exact commercial JdK formula, document the transparent internal alternative
  - keep the transforms deterministic and auditable
  - expose enough metadata that advanced users can understand what the chart is based on
- Persist or cache computed rotation snapshots where useful so the platform can support:
  - historical replay
  - animation
  - dashboard widgets
  - cross-date comparison
  - export without recomputing large universes every time

Quadrant / state model:
- Classify each instrument into a current relative state:
  - leading
  - weakening
  - lagging
  - improving
- Also compute richer state descriptors beyond the raw quadrant:
  - distance from center
  - heading / angle of travel
  - rate of change of heading
  - recent quadrant transitions
  - time spent in current quadrant
  - acceleration / deceleration of rotation
- This richer state is important because users do not only care where an instrument is now, but:
  - whether it is moving deeper into leadership
  - whether it is curling over
  - whether it is improving with conviction
  - whether it is merely bouncing around near the origin without real signal

Primary product surface:
- Add a dedicated **Relative Rotation** workspace or analysis panel where users can:
  - choose a benchmark
  - choose a peer set
  - switch timeframes
  - adjust lookback and tail length
  - animate or scrub through history
  - inspect both the latest state and recent path
- The first-class preset should be **S&P sector ETFs**:
  - benchmark default: `SPY`, `IVV`, or the S&P 500 index if available
  - peer set default: the major US sector ETFs
  - one-click load should exist because this is the main intended use case
- But the selector model must remain generic so the same workspace can be reused for:
  - arbitrary instruments
  - watchlists
  - baskets
  - ETF-derived baskets
  - later, strategy or signal peer sets where that makes product sense

Visualization / UX:
- Plot instruments on a scatter-plot style canvas with:
  - horizontal axis for relative-trend
  - vertical axis for relative-momentum
  - clear neutral/origin crosshair
  - color-coded quadrants
  - labeled latest points
  - tails showing recent motion
- Support interaction suitable for dense universes:
  - hover tooltip with symbol, name, latest relative metrics, quadrant, heading, and recent change
  - click to pin one or more instruments
  - isolate/highlight selected symbols
  - hide or fade non-selected symbols
  - search within the plotted set
- Support both:
  - a **latest snapshot** view
  - a **time-evolution** view where the tail / animation is the star
- Handle clutter carefully:
  - adaptive label density
  - optional point-only mode
  - optional tail-only-on-selection mode
  - shorter tails automatically suggested when the plotted universe is large
- Make the visual feel native to the platform:
  - consistent typography, sizing, control layout, color tokens, hover behavior, and popups
  - no oversized or visually disconnected custom control block

Companion views:
- Add a sortable **rotation table** next to or below the graph showing:
  - symbol
  - current quadrant
  - relative-trend metric
  - relative-momentum metric
  - heading / angle
  - distance from center
  - recent quadrant transition
  - rank within selected peer set
- Add a **history strip / event log** for selected instruments:
  - when they moved between quadrants
  - when they crossed the neutral thresholds
  - how long they remained in leadership vs lagging states
- Add a **pair/trio comparison mode** where a few selected instruments can be seen with more detail and less clutter.

Data and coverage considerations:
- This depends on robust aligned OHLCV coverage for:
  - the benchmark
  - every instrument in the peer set
- The view should surface coverage limitations clearly:
  - partial overlap
  - benchmark starts later than the selected range
  - peer instruments with too little history to compute stable signals
- If coverage is insufficient, the platform should:
  - either exclude the instrument with a clear reason
  - or visually mark it as coverage-limited
  - but never silently compute a misleading path

Downstream integrations:
- Watchlists / baskets / ETF holdings:
  - allow any of these to be launched directly into the rotation workspace
- Correlation / breadth / relative-performance tooling:
  - share universe selectors and time-range controls with those analytics surfaces where possible
- Radar:
  - later, allow radar candidate sets to be inspected through a relative-rotation lens
  - this can help answer whether a technical setup is also occurring in a strengthening or weakening relative context
- Strategy Lab:
  - later, consider whether relative-rotation state should become:
    - an input condition family
    - a universe-ranking aid
    - or a comparative analysis surface for strategy output baskets
  - but do not force the initial implementation to depend on Strategy Lab

Validation and testing:
- Add unit coverage for:
  - relative-strength series construction
  - normalization/transformation math
  - quadrant classification
  - heading / angle / distance calculations
  - missing-data alignment rules
- Add integration coverage for:
  - benchmark-relative calculations across realistic ETF peer sets
  - coverage-warning semantics
  - server/API response shape if the computation is backend-driven
- Add frontend coverage for:
  - graph rendering
  - selection/highlight behavior
  - dense-universe decluttering behavior
  - tooltip correctness
  - table/graph cross-linking

Why this matters:
- This becomes a high-signal visual way to inspect **relative leadership rotation**, which is especially useful for:
  - sector rotation
  - macro/factor allocation
  - ETF peer comparisons
  - basket triage
- It also complements, rather than duplicates:
  - breadth analysis
  - correlation analysis
  - strategy research
- Breadth tells us how broad participation is.
- Correlation tells us how related instruments are.
- Relative rotation tells us **who is leading, who is improving, and how that leadership is evolving over time versus a benchmark**.

---

#### Shared design principles across 10a–10f

- **Baskets are first-class objects.** They are not just lists; they carry weights, metadata, classification, and a potential synthetic price series. The domain model should reflect this from the start.
- **ETF-derived baskets are a special case of the same model.** User baskets and ETF holdings baskets share the same backend schema and frontend surfaces; the distinction is managed vs unmanaged ownership and refresh semantics.
- **The basket model feeds other platform features.** Baskets should be usable as: chart synthetic instruments, screener universes (item 3), Strategy Lab universes (item 7), radar filter slices (item 5), and breadth analysis targets. These integrations should inform the basket schema design so it isn't retrofitted later.
- **Breadth analysis should be additive, not a re-architecture.** The breadth engine reads member OHLCV histories that already exist in the platform. It does not require new data infrastructure, only a computation layer on top of existing data.
- **Sector/industry classification for mixed baskets remains an open design question.** The taxonomy used for classification should be revisited once downstream use cases (breadth grouping, radar slicing) clarify what granularity is actually needed.
- **Cross-instrument correlation analysis should reuse the same universe-selection building blocks.** Watchlists, baskets, ETF holdings, and later Strategy Lab result sets should be usable as correlation-analysis inputs without needing a separate parallel selector model.
- **Relative-rotation analysis should reuse the same universe-selection and coverage primitives.** Benchmarks, watchlists, baskets, ETF-derived baskets, and later strategy/signal peer sets should all plug into the same selectors and OHLCV readiness rules rather than introducing another bespoke instrument-set model.

Phasing expectations:
- Phase 1: Custom basket creation/editing with equal and custom weights, basket charted as a synthetic price series, basic basket list/detail UI.
- Phase 2: ETF holdings data ingestion, ETF-as-basket materialisation, holdings navigation UI.
- Phase 3: Breadth analysis engine, breadth snapshot views, breadth time-series charting.
- Phase 4: Basket breadth dashboard widgets, cross-basket comparison views, integration with radar and screener universe selectors.
- Phase 5: Cross-instrument correlation analysis surfaces, rolling correlation views, and integration of those relationship tools into watchlists/baskets/Strategy Lab workflows.
- Phase 6: Relative-rotation analysis over arbitrary instrument sets, with S&P sector ETF presets, benchmark-relative tails, and richer downstream integration into watchlists/baskets/Radar/Strategy Lab where useful.

Why this was deferred:
- Baskets are a foundational building block but depend on having a stable instrument model (already done) and clear downstream consumers.
- ETF holdings data requires a dedicated provider integration.
- Breadth analysis depends on both basket membership and historical OHLCV coverage being in good shape.
- The right design for mixed-sector basket classification needs more downstream context before being finalised.

### 12. Build a platform-wide OHLCV coverage, freshness, and acquisition orchestration layer
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
- Also be explicit that this item governs **price/coverage acquisition**, not all provider communication in general.
- A separate but adjacent platform rule needs to be preserved:
  - some flows are fundamentally about **instrument discovery / identity / metadata**
  - other flows are about **OHLCV / freshness / historical coverage**
  - those must not be conflated, because the correct provider-access policy is different for each

#### 11a0. Separate instrument discovery/materialization from OHLCV acquisition

The platform should explicitly model two adjacent but different responsibilities:

- **Instrument discovery / identity / metadata**
  - "What is this thing?"
  - search results
  - canonical symbol resolution
  - provider symbol mappings
  - provider profile / metadata ingestion
  - provider-overlap reconciliation and mastering
- **Market-data acquisition / freshness / coverage**
  - "Do we have the price/history needed for this use case?"
  - OHLCV completeness
  - latest-bar freshness
  - missing-slice repair
  - background refresh/seed orchestration

This roadmap item is primarily about the second responsibility, but the first one must be documented alongside it so provider-access boundaries stay coherent.

Current gap we discussed:
- provider-backed search results can be shown in the UI without necessarily materializing a canonical `Instrument` row in the DB
- that creates downstream incoherence, because a symbol can be:
  - real according to provider search
  - visible/selectable in the UI
  - but still absent from the platform DB until some later route explicitly instantiates it
- this affects flows like Strategy Lab universes and any other picker-driven feature that assumes selected provider-backed instruments are already locally materialized

Desired future behavior:
- when the user selects a provider-backed instrument from a search/picker flow, the platform should be able to:
  - fetch lightweight metadata/profile details
  - instantiate or reconcile a canonical local `Instrument` row
  - register provider-symbol identity mappings
  - merge overlaps appropriately if the instrument already exists under another provider identity
- this should happen **without** automatically fetching OHLCV unless a separate policy explicitly asks for it

In other words:
- metadata discovery/materialization should be allowed to talk to providers
- broad OHLCV consumers should still be forbidden from doing ad hoc provider fetches inside evaluation loops

This gives the platform the desirable model we discussed:
- search/discovery makes an instrument locally known
- OHLCV/history is still fetched later on demand or by scheduled preparation flows
- features like Strategy Lab, Screener, Radar, and Alerts can then assume:
  - selected instruments are real platform objects
  - but price data may still be cold and must go through the shared OHLCV coordinator

Provider-access boundary to preserve:
- **Allowed to call providers for identity/metadata/materialization**
  - `/instruments/search` follow-up selection flows
  - explicit instrument-add or instrument-picker commit flows
  - `/instruments/{symbol}` resolution/lookup
  - expression constituent resolution
  - instrument mastering / background sync jobs
- **Not allowed to call providers directly for OHLCV as part of evaluation**
  - Radar
  - Screener
  - Strategy Lab
  - Alerts
  - breadth evaluators
  - any broad decision engine
- those OHLCV consumers must instead go through the shared coverage/freshness coordinator defined below

Search-time lightweight instrument materialization should therefore eventually become a first-class platform behavior:
- provider search may remain a lightweight discovery step by itself
- but once the user actually selects a result for use in the platform, the system should:
  - materialize/reconcile that instrument into the DB
  - persist canonical identity and provider-symbol mappings
  - optionally enqueue a background OHLCV bootstrap
- the OHLCV bootstrap, if any, should be asynchronous and policy-driven:
  - it should not block search UX unnecessarily
  - it should not blur the line between metadata instantiation and price acquisition

This should align cleanly with the rest of this roadmap item:
- interactive/search flows are allowed to create or reconcile instrument metadata
- OHLCV consumers remain DB-first and coordinator-driven
- first discovery may enqueue background history seeding
- evaluators later rely on preflight readiness rather than silently fetching bars themselves

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

### 13. Let multi-instrument dashboard widgets publish clicked instruments into dashboard link groups
Status: `Deferred`

Context:
- We discussed a future dashboard interaction model where clicking an instrument inside a multi-instrument widget would not have to navigate away from the dashboard.
- The main idea was that widgets such as:
  - radar
  - watchlists
  - screener results
  - heat maps
  - and similar multi-instrument widgets
  could eventually publish the clicked instrument into a chosen dashboard link group.
- Linked quote/chart/details/options widgets could then update live from that click, preserving dashboard flow instead of forcing a route change.
- We explicitly chose not to build this immediately, but we do not want to lose the concept.

What this should eventually solve:
- Allow multi-instrument widgets to act as dashboard instrument publishers, not only as isolated result lists.
- Preserve a clear distinction between:
  - widgets that consume a linked instrument
  - widgets that can publish one when a user clicks a row/tile/item
- Let users inspect a result locally first, then optionally broadcast that instrument context to the rest of the dashboard.

Open questions to settle later:
- How should a multi-instrument widget declare which link group it publishes into?
  - fixed per widget
  - chosen in widget config
  - chosen ad hoc during interaction
- Should a widget be allowed to consume one link group while publishing into another?
- What is the UX split between:
  - local row/detail inspection
  - broadcasting to a link group
  - opening the full `/chart` route
- How do we make this predictable enough that users understand whether they are:
  - selecting something locally
  - updating a dashboard-wide context
  - or navigating away?

Suggested direction:
- Treat this as a dashboard interaction-system feature, not as radar-only behavior.
- Keep current widget-local detail interactions simple until the broader publisher/consumer dashboard-link model is designed properly.

Why this was deferred:
- It is cross-cutting dashboard architecture, not a small widget tweak.
- We do not want to bolt it onto one widget first and then retrofit the dashboard model later.

### 14. Replace the primary frontend with a TC2000 Version 25-style workstation and build its supporting backend/research platform
Status: `Planned`

Branch:
- `feat/tc2000-frontend-rework`

Controlling objective:
- This section and `docs/tc2000-visual-parity.md` are the controlling specification for
  the branch and supersede every older or narrower frontend-rework plan where they
  conflict. Do not silently reduce, defer, phase, reinterpret, or substitute any part
  of this completion contract during implementation.
- Replace the authenticated primary frontend with a pixel-close, rebranded clone of
  TC2000 Version 25 desktop build `25.0.9571` and its interaction model.
- Treat this as one continuous implementation stint with one completion bar. Internal
  checkpoints are for repository continuity, not partial delivery, phased scope, or an
  MVP stopping point.
- Keep Vue 3, TypeScript, Vite, and uPlot. uPlot remains the only chart renderer because
  fast rendering, direct canvas control, and flexible plugins are non-negotiable.
- Use Golden Layout's Vue-compatible virtual-component model for arbitrary docking,
  tab stacks, maximizing, saved layouts, browser pop-outs, and multi-monitor use.
- Match TC2000 Version 25 desktop geometry, density, colors, control styling, window chrome,
  menus, dialogs, keyboard behavior, and interaction states as closely as practical,
  while retaining this platform's branding and using original CSS/SVG assets rather
  than TC2000 logos or proprietary images.
- Keep the existing frontend available under `/legacy/*`. Do not migrate its dashboards.
  Radar, Strategy Lab, Baskets, ETF Holdings administration, seasonality, options, and
  provider diagnostics remain available only through legacy routes and do not appear
  in the new primary interface.
- Exclude visible options, brokerage/trading, news, analyst ratings, earnings, and full
  financial statements. Create explicit capability contracts, source-level TODOs, and
  extension documentation for all excluded or data-blocked features without rendering
  misleading disabled shells in the primary interface.
- Continue using the current provider-neutral polling model. Do not add streaming quote
  infrastructure as part of this task.
- Make the backend/data work required by the workstation part of the same completion
  contract: API-first free-source reconciliation, canonical security mastering,
  point-in-time market groups, batch analytics, adjusted-history correctness, provider
  entitlement reporting, and isolated user-code execution are not follow-up projects.
- Use one Python-native market-analysis language and SDK for chart calculations,
  watchlist columns, EasyScan conditions, alerts, gauges, reusable signals, and
  open-ended studies. Do not build or expose separate PCF, Optuma, and Python languages.
- Add a first-class Study Lab to the primary workstation for Optuma-style event,
  statistical, breadth, regime, distribution, forward-outcome, and current-versus-
  history research. Keep it separate from the execution/backtesting Strategy Lab.

#### Completion contract

This work is complete only when:
- the new TC2000-style workstation is the default authenticated application;
- every in-scope window, workflow, keyboard interaction, persistence path, linking
  behavior, and error state below is implemented;
- the top-down US-market workflow can be completed without leaving the workstation;
- the unified Python language works consistently across every programmable surface and
  executes only in the dedicated sandboxed research worker;
- Study Lab can define, run, reproduce, inspect, and reuse non-chart-centric historical
  research with structured native results;
- the new workstation has no required yfinance, paid-API, provider-specific frontend,
  or reliable consolidated real-time dependency;
- current canonical watchlists, drawings, alerts, screeners, indicator presets, OHLCV,
  instrument metadata, ETF holdings, and baskets remain usable;
- legacy-only surfaces remain directly accessible but absent from the new navigation;
- backend, frontend, integration, end-to-end, visual, console, log, performance, and
  sandbox-security, provider, migration, and diff validation all pass;
- unsupported functions and product domains are documented and stubbed honestly;
- every in-scope visual surface and interaction state is backed by an approved
  Version 25 reference, measured design tokens, deterministic baselines, and passing
  behavioral plus screenshot comparisons;
- no temporary placeholder, dead control, unexplained visual mismatch, or unhandled
  known failure remains before handoff.

#### Version 25 visual-reference and parity contract

`docs/tc2000-visual-parity.md` is the complete visual implementation contract. It pins
TC2000 desktop build `25.0.9571`, records the official source catalogue, defines the
capture and measurement process, and prevents visual implementation from being based on
memory or informal resemblance.

Visual authority, highest to lowest:
1. authorised live desktop captures from Version 25 build `25.0.9571`;
2. official help material explicitly tagged Version 25;
3. official Version 23/24 help only when a live Version 25 capture proves the surface
   remains materially unchanged;
4. Version 20 help only as behavioral history;
5. third-party material for discovery only, never pixel acceptance.

"Authorised live capture" means a provenance-verifiable capture of the actual pinned
desktop build, not a capture that must be made locally by the implementation machine.
Permission-cleared online captures and controlled-storage reference packs are eligible
when the manifest verifies the build, state, capture environment, unmodified hash,
source/permission classification, and reviewer approval. Official Version 25 online
material is likewise eligible where it covers the required state. Third-party material
cannot become a visual baseline without independently establishing those facts.

The release notes at <https://www.tc2000.com/features/whatsnew> are the generation/build
authority. The generic download page currently exposes stale Version 24 copy and does not
override the dated release record or a captured Version 25 desktop.

Before a tool can satisfy visual completion:
- create `tests/visual/references/tc2000-v25/manifest.yaml`;
- obtain approved references for every required shell, window, menu, dialog, chart,
  watchlist, column/filter, gauge, alert, notes, and Study Lab state;
- record build, date, source, resolution, display scale, theme, crop, dynamic masks,
  measurements, interaction recipe, SHA-256, review status, and permission/storage
  classification for every reference;
- measure and centralize geometry, typography, spacing, borders, gradients, colors,
  icon boxes, scrollbars, shadows, overlay order, and interactive states;
- capture deterministic product baselines at 1920x1080 and 2560x1440, each at 100% and
  125% display scale with 100% browser zoom;
- separately verify layout robustness at 125% browser zoom;
- validate the corresponding mechanics through interaction tests; a static screenshot
  never proves linking, keyboard navigation, docking, pop-outs, chart interaction,
  editors, or recovery behavior.

Pixel acceptance:
- no unexplained geometry difference greater than one CSS pixel;
- tokenized dimensions and declared typography exactly match approved values;
- solid-color CIEDE2000 delta E is at most 2;
- the unmasked differing-pixel ratio is at most 0.5% per approved image;
- dynamic masks are minimal, named, owned, and justified;
- no broad mask or raised global threshold may hide a structural mismatch;
- every baseline change receives human review and an intentional-change note.

Reference images remain non-distributable test/reference material. Ship only original
platform branding, CSS, SVG, and iconography. If protected captures cannot be committed,
keep them in controlled storage and commit the manifest metadata, hashes, capture
instructions, and measurements needed to reproduce the comparison.

#### Desktop shell and workspace mechanics

Replace the icon-sidebar and route-per-feature model with a TC2000-style desktop shell:
- compact global menu bar;
- workspace/layout tab strip;
- active-symbol entry and symbol-history navigation;
- provider/freshness/status area;
- central dockable tool-window surface;
- original platform branding rather than TC2000 branding.

Every tool window must share a dense TC2000-style chrome with:
- title and active-symbol display where applicable;
- symbol-link selector;
- tool-specific menu;
- drag handle;
- tab-stack behavior;
- maximize/restore;
- float/pop-in;
- close;
- minimum-size and resize constraints;
- focused/active state that is visually distinct without consuming excessive space.

Workspace behavior:
- allow arbitrary row/column docking, tab stacks, drag rearrangement, maximization,
  browser pop-outs, and restoration of exact sizes and positions;
- use Golden Layout virtual components so Vue retains ownership of its component tree;
- persist only serializable tool configuration and state, never DOM nodes, uPlot
  instances, request caches, or transient hover/crosshair state;
- use one elected browser window as persistence leader;
- synchronize pop-outs using `BroadcastChannel`, with same-origin storage events as a
  fallback;
- synchronize symbol changes, active list rows, explicitly linked timeframes, crosshair
  timestamps, code/library changes, layout changes, and logout;
- transfer persistence leadership automatically if the leader closes;
- keep a window docked and show a clear notification if the browser blocks a pop-out;
- restore an unexpectedly closed pop-out to its source layout on the next load.

Reproduce TC2000 Version 25 symbol-link semantics:
- use the exact current Version 25 link-group names and colors captured in the visual-reference
  audit;
- windows in the same normal group follow symbol changes;
- yellow behaves as the global/wildcard receiver;
- gray remains isolated until manually changed;
- link behavior crosses workspace tabs and browser pop-outs;
- link events carry stable instrument identity, not only a display ticker.

Global keyboard behavior:
- typing while focus is outside an editor opens symbol search;
- `Space` and `Shift+Space` traverse the focused list forward/backward;
- arrow keys move list selection;
- `Enter` activates the selected item;
- `Ctrl+mouse-wheel` traverses symbols in the focused list;
- chart shortcuts retain zoom, pan, log scale, latest-bar, drawing cancel/delete, and
  help behavior;
- no global shortcut fires while a text, code, numeric, or search editor owns focus;
- tool menus expose the current shortcut so the interface remains discoverable.

#### Factory and personal layouts

Ship immutable factory layouts that users can clone:

`US Top Down` is the default layout and contains:
- major benchmark list;
- cap-weighted/equal-weight comparison;
- sector list;
- industry list;
- constituent list;
- primary chart;
- ratio/relative-strength chart;
- technical, breadth, provenance, and coverage summary.

`TC Classic` contains:
- watchlist;
- main chart;
- symbol notes in place of unavailable news.

`Drill Down` contains:
- sector list;
- industry list;
- component list;
- selected-symbol chart;
- tabbed sector-comparison chart.

`Sector by Year` contains:
- linked sector, industry, and constituent lists;
- selectable year-performance columns;
- selected-symbol and normalized-comparison charts.

`1 Chart` contains:
- an uncluttered full-workspace chart.

`4 Timeframe` contains:
- four symbol-linked uPlot charts with independently configurable timeframes.

`Fundamentals` contains:
- chart;
- supported fundamental/metadata columns;
- supported-data report.

`Study Lab` contains:
- Python editor and parameter controls;
- universe, benchmark, timeframe, date-range, adjustment, and session selectors;
- coverage/look-ahead/survivorship preflight;
- run progress, logs, and cancellation;
- structured metrics, tables, plots, event occurrences, and linked-chart inspection.

Do not create Trading or Options factory layouts. Personal workspaces and layout tabs
must support create, clone, rename, reorder, import, export, delete, and reset-from-
factory operations. Factory definitions remain versioned, read-only, and resettable.

#### uPlot chart-window implementation

Refactor the current large chart component into:
- a framework-neutral chart model;
- reusable uPlot host/lifecycle layer;
- independent uPlot plugins;
- TC2000-style chart-window wrapper;
- serializable chart/template configuration.

Preserve and harden:
- candlestick, OHLC, line, area, baseline, Heikin-Ashi, Renko, Kagi, and Point & Figure;
- infinite historical backfill;
- automatic and logarithmic scales;
- current-price and visible-range projections;
- comparison series and normalized comparisons;
- ratio/synthetic expressions such as `=XLK/SPY`, `=XLK/XLE`, and `=NVDA/XLK`;
- indicator overlays and independent sub-panes;
- resizing of sub-panes;
- chart drawings and drawing ordering;
- alert lines and firing markers;
- supported dividend and split markers;
- linked crosshairs;
- multi-chart layouts;
- cached-history and background-fetch messaging.

Chart templates must save and restore:
- plot stack and order;
- styles and colors;
- panes and pane heights;
- axes and scale settings;
- timeframe;
- adjustment/transform settings;
- drawing defaults;
- comparison settings;
- event-marker visibility;
- indicator parameters and timeframe locks.

Applying a template must not replace the active symbol. Templates support save, clone,
rename, import, export, delete, and factory reset.

The plot library must support:
- price history;
- every locally implemented indicator;
- relative strength against any selected symbol;
- normalized comparison plots;
- scan plots;
- watchlist/basket synthetic indexes;
- Python calculations that evaluate to numeric series.

Plot interaction must support:
- hover legend;
- edit, move, hide, duplicate, and delete;
- drag a numeric plot/indicator into a watchlist to create a value column;
- drag a condition into a watchlist to create a Boolean column;
- copy a plot or condition to another chart, watchlist, EasyScan, or alert through
  TC2000-style target mode.

uPlot performance rules:
- Golden Layout resize events flow through a single `ResizeObserver`/`setSize` path;
- ordinary resize, docking, tab switching, and maximization must not recreate uPlot;
- identical OHLCV requests are deduplicated across linked charts using symbol,
  timeframe, adjustment, range, and transformation query keys;
- hidden tabs suspend polling and expensive redraws;
- destroyed tool instances release canvases, observers, subscriptions, and plugins.

#### Watchlists, related lists, and column mechanics

Implement a virtualized TC2000-style watchlist window supporting at least 10,000 rows.

Supported list sources:
- personal lists;
- managed EasyScan result lists;
- system market-group lists;
- ETF/index-proxy constituent lists;
- sectors;
- industries;
- related items;
- combo lists using union, intersection, and exclusion rules.

Row behavior:
- mouse or keyboard selection publishes to the window's symbol-link group;
- active symbols remain visibly selected;
- personal lists support drag reordering;
- compatible lists support drag/drop copy or move;
- multi-select can launch comparison charts and bulk list operations;
- context menus support add, copy, move, remove, flag, note, chart, alert, related lists,
  and membership inspection;
- list selection is retained by instrument ID after sorting/filtering, not by row index.

Reusable column types:
- raw price and volume;
- numeric/value;
- Boolean/condition;
- tag or list membership;
- Python calculation;
- indicator output;
- relative strength and period performance;
- supported metadata/fundamental values;
- provenance/freshness where useful.

Column behavior:
- insert, delete, duplicate, rename, resize, and reorder;
- horizontal scrolling;
- vertical stacking of multiple values in one visual column;
- column grouping;
- saved reusable columns and column sets;
- configurable header, decimals, units, positive/zero/negative colors, alignment, and
  missing-value display;
- ascending/descending click sort;
- manual ordering;
- Boolean/tag pinning above the remaining value sort;
- copy/paste through the internal library clipboard;
- drag an indicator/condition/calculation from another tool to create a column;
- refresh timestamp, current filter, polling state, and manual refresh in window chrome.

#### Unified Python market-analysis language

Use normal Python syntax with one versioned platform SDK across charts, watchlists,
EasyScan, alerts, gauges, reusable signals, and Study Lab. A simple calculation is a
short Python program such as `result = ta.rsi(market.close, 14)`; a larger study uses
the same syntax, editor, runtime, functions, versioning, and output contracts.

SDK namespaces:
- `market`: OHLCV, instruments, universes, benchmarks, metadata, events, sessions,
  memberships, and point-in-time data access;
- `ta`: the platform's technical indicators and transformations;
- `stats`: descriptive statistics, streaks, ranks, percentiles, rolling calculations,
  correlation, regression, and distributions;
- `research`: occurrences, forward returns, regimes, conditional outcomes, breadth,
  cross-sectional studies, and current-versus-history comparisons;
- `output`: typed metrics, tables, plots, event sets, and dashboards.

Language rules:
- do not implement independently executable PCF or Optuma syntax;
- reproduce useful TC2000/Optuma semantics through canonical Python SDK functions and
  searchable migration documentation;
- use the same saved code asset/version everywhere rather than copying source into each
  chart, column, scan, alert, or study;
- let the visual condition builder edit the supported subset of the same Python AST;
  Python source remains authoritative when code exceeds the visual subset;
- preserve source positions, dependency/required-lookback analysis, diagnostics, and
  recursive dependency detection;
- batch-evaluate by universe and timeframe so watchlists never issue per-cell calls;
- pin every consumer to an immutable code version and require an explicit upgrade when a
  newer version is published.

Every saved code version records:
- stable asset ID, name, intended output contract, source, parameters, and defaults;
- immutable version, SDK/runtime version, data dependencies, required lookback, and
  referenced symbols/universes;
- capability requirements, compile diagnostics, creator, and timestamps.

Code interfaces:
- SDK/capability registry and documentation;
- validate/compile and dependency preflight;
- scalar batch, numeric-series, Boolean-series, event-set, and structured-study execution;
- saved code CRUD/versioning/import/export through the workspace library;
- structured diagnostics, warnings, coverage failures, and execution-limit errors.

#### Sandboxed Python execution

Never execute user-authored Python inside FastAPI, the general ARQ worker, a browser
context, or any process that holds provider credentials.

Create a dedicated research execution service and worker image with:
- a non-root runtime and read-only root filesystem;
- an ephemeral per-run writable directory and no host filesystem mounts;
- no external network, secrets, provider credentials, subprocess creation, or runtime
  package installation;
- Linux namespace isolation plus seccomp/AppArmor restrictions where supported;
- explicit CPU, memory, wall-time, output-size, row-count, and file-size limits;
- heartbeats, forced termination, orphan cleanup, and structured limit failures.

Curated imports:
- explicitly approved numerical/research modules from the Python standard library;
- NumPy, pandas, SciPy, and statsmodels;
- the internal `market`, `ta`, `stats`, `research`, and `output` SDK namespaces.

Reject arbitrary imports, sockets, subprocesses, reflection into host internals,
unrestricted filesystem access, dynamic code execution, unsafe deserialization, and
runtime `pip` or package downloads. AST validation is a preflight and usability layer,
not the security boundary; the isolated process/container remains mandatory.

Execution flow:
1. parse the Python AST and return source-positioned diagnostics;
2. reject prohibited syntax/imports/attributes and validate the declared output type;
3. derive static data dependencies where possible and combine them with the explicit
   universe, benchmark, timeframe, date range, adjustment, and session configuration;
4. resolve all data through the canonical local database, never directly from a provider;
5. create a versioned dataset manifest and materialize read-only Arrow/Parquet inputs;
6. execute the pinned code/SDK/worker versions in the isolated worker;
7. validate and persist bounded structured outputs, logs, warnings, exclusions, resource
   use, and the reproducibility hash.

Dynamic market access is limited to instruments and universes already present in the run
manifest. Missing data produces a structured coverage failure rather than a provider
call. Interactive columns/scans use a warm worker pool and vectorized universe batches;
long studies use queued runs with progress, cancellation, and durable artifacts.

#### EasyScan, conditions, scan plots, and gauges

Generalize the current screener into a TC2000-style EasyScan workflow:
- select all instruments, asset class, watchlist, combo list, market group, basket,
  ETF-derived basket, or explicit symbols as universe;
- create nested AND/OR/NOT condition trees;
- add price, volume, indicator, metadata, relative-strength, or Python conditions;
- choose timeframe per condition;
- preview match counts;
- save, clone, rename, reorder, schedule, enable/disable, and delete;
- run synchronously for small prepared universes or stream progress for large/cold ones;
- cancel in-progress runs;
- display per-instrument preparation/evaluation failures;
- retain historical results.

Reusable actions:
- apply a saved condition as a watchlist filter;
- turn a condition into a Boolean column;
- create an alert from a condition;
- create a managed watchlist from an EasyScan;
- plot historical match count or percentage as a scan plot;
- create a market gauge from a saved scan;
- copy conditions between scans, columns, plots, and alerts.

Historical scan plots must start only when valid recorded history exists; do not fabricate
past membership or results.

The current Version 25 interaction model is authoritative: columns, True/False
conditions, filters, groups, stacks, and Market Gauges are edited as one integrated
watchlist workflow. Preserve EasyScan as the name and reusable saved-scan capability,
but do not reproduce the obsolete standalone Version 20 editor when current Version 25
behavior has replaced it.

#### Top-down US-market analysis

Create a versioned market taxonomy containing:
- logical benchmark identities separated from their official index series and tradable
  proxies, including SPX/S&P 500 where entitled plus SPY, RSP, QQQ, DIA, and IWM;
- all 11 Select Sector SPDR ETFs;
- normalized, source-labelled sectors and industries;
- verified industry ETF proxy associations;
- point-in-time ETF holdings memberships;
- representative, equal-weight, and comparison relationships;
- source, provenance, known-at time, composition date, and freshness.

Industry ETF semantics:
- treat industry ETFs as curated proxies associated with an industry, not as fictional
  children owned by a sector ETF;
- allow zero, one, or several verified proxy ETFs per industry;
- require source documentation and holdings/classification validation;
- expose “No mapped ETF proxy” when none is verified;
- never infer an ETF relationship solely from a similar name.

Index constituent semantics:
- use ETF holdings as an explicit proxy when official licensed constituents are absent;
- label the universe as ETF-proxy membership;
- surface snapshot date, known-at time, source quality, resolution count, and unresolved
  rows;
- fall back to metadata classification only with an equally explicit label;
- never silently claim official historical index membership.

Index-series semantics:
- use an official index series only when a configured provider entitlement supplies it;
- otherwise use a clearly labelled tradable proxy such as SPY;
- never display SPY data under an SPX label or imply that proxy holdings are official
  licensed index constituents.

Linked drill-down mechanics:
- selecting a benchmark loads technicals and its equal-weight comparison;
- selecting a sector loads industries, constituents, breadth, relative strength, and
  sector comparison;
- selecting an industry loads its constituents and verified proxy ETFs;
- selecting an industry proxy now publishes that proxy to the linked symbol group,
  loads its canonical bars/technicals, and preserves the selected sector/industry
  taxonomy context so the proxy can be compared against its sector without replacing
  the drill-down tree with the proxy's own holdings;
- selecting a constituent updates linked stock charts;
- one action creates sector/benchmark, industry-proxy/sector, stock/sector, and
  stock/benchmark ratio views;
- list traversal updates all windows in the same link group without route changes.

Batch ranking columns:
- 1D, 1W, 1M, 3M, 6M, YTD, and 1Y performance;
- benchmark-relative performance;
- ratio trend and momentum;
- RSI;
- price relative to 20/50/200 moving averages;
- distance from 52-week high/low;
- volume ratio;
- provider coverage and freshness.

Top-down row adapters must preserve the backend `AnalysisCell.warning` message for
performance, relative-strength, technical, and calendar-year cells. The workstation
watchlist renders those messages (for example, `⚠ insufficient_history`) instead of
turning an unavailable value into an unexplained blank or dash.

Breadth analytics:
- percentage above configurable 20/50/200 moving averages;
- percentage near 52-week highs/lows;
- percentage making configurable-period highs/lows;
- percentage in configured uptrend/downtrend;
- aggregate distance from selected averages;
- current snapshot and historical series;
- click-through to passing/failing constituent lists;
- comparison of multiple groups side by side.

The primary breadth surface now exposes a canonical group selector, Above/Below controls
for the 20/50/200-MA states, and a linked passing/failing member drill-down. It loads
the selected group's snapshot and current/historical breadth through the existing local
analysis APIs; the drill-down preserves canonical symbol identity and publishes the
selected member to the workstation link group.

Relative rotation:
- accept benchmark, peer universe, timeframe, lookback, sampling, and tail length;
- calculate aligned relative-strength series;
- derive transparent relative-trend and relative-momentum dimensions;
- classify leading, weakening, lagging, and improving;
- calculate heading, distance, velocity, recent transition, and time in state;
- provide interactive tails and sortable companion table;
- surface partial-overlap and insufficient-history warnings;
- call the feature “relative rotation,” not a proprietary JdK/RRG implementation.

#### API-first free-source backend and data foundation

The frontend must consume canonical platform APIs only. It must never know provider
symbols, credentials, quotas, endpoint shapes, or fallback ordering.

Use the existing capability-oriented provider runtime, priorities, token buckets,
cooldowns, health measurements, request logs, provenance, and circuit behavior as the
foundation, but replace single-provider field selection with source reconciliation.

Required free-source provider roles:
- US security universe: reconcile Massive reference tickers, Alpaca assets, and Alpha
  Vantage listing/delisting data rather than trusting any one list;
- corporate identity: use SEC CIK/ticker/exchange associations as an official identity
  anchor while acknowledging that SEC does not guarantee complete exchange coverage;
- identifiers: use OpenFIGI v3 for FIGI mapping and listing reconciliation;
- current/delayed prices: use Alpaca IEX and permitted delayed SIP data, always exposing
  feed, venue scope, observation time, and freshness;
- broad EOD corroboration: use Massive free aggregates/reference endpoints only where
  the configured entitlement currently permits them;
- deep raw daily history: use Alpha Vantage raw daily history within its quota;
- adjustments: derive locally reproducible split/dividend-adjusted views from stored raw
  bars and reconciled corporate actions;
- corporate actions: reconcile Alpaca and Massive events with SEC evidence where useful;
- fundamentals: use SEC submissions/XBRL and explicitly identify every derived value;
- taxonomy: normalize source-labelled sector/industry data, ETF membership evidence,
  SEC SIC, and curated mappings without claiming licensed GICS data unless entitled;
- ETF holdings: retain issuer-native adapters, raw artifacts, and SEC N-PORT/N-Q
  reconstruction;
- macro/regime inputs: retain FRED;
- optional validation: allow a quota-limited secondary source such as Twelve Data, but
  make no core workflow depend on it.

Primary source-documentation anchors:
- Massive reference tickers: <https://massive.com/docs/rest/stocks/tickers/all-tickers>;
- Alpha Vantage listing status and raw daily history:
  <https://www.alphavantage.co/documentation/>;
- Alpaca market-data plan/feed semantics:
  <https://docs.alpaca.markets/us/docs/about-market-data-api>;
- SEC EDGAR company ticker/exchange files and scope caveat:
  <https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data>;
- OpenFIGI v3 mapping and limits: <https://www.openfigi.com/api/documentation>.

Nasdaq Trader/exchange directory files may be ingested as audit or backfill evidence.
They are not the primary master, are not treated as Nasdaq-only coverage, and are never
a runtime dependency.

yfinance policy:
- remove yfinance from every default priority and every completion/acceptance path;
- keep it temporarily only as an explicitly enabled legacy fallback if an existing
  legacy capability still requires it;
- attach provider provenance to all retained yfinance-derived values;
- prohibit new-workstation tests, fixtures, or startup from requiring it;
- remove the adapter once the legacy capability audit proves it is unused.

The absence of consolidated free real-time data is an accepted product constraint, not a
reason to fabricate a real-time experience. The workstation must distinguish `current`,
`delayed`, `stale`, `fetching`, `partial`, `coverage-limited`, and `unavailable`.

#### Canonical security master and provider reconciliation

Retain and extend the active canonical identity model:
- `Instrument`;
- `InstrumentListing`;
- `InstrumentIdentifier`;
- `InstrumentProviderSymbol`;
- `InstrumentProviderCapabilityStatus`;
- field-level provenance.

Consolidate the unused duplicate instrument-listing model so one definition and migration
source remain authoritative.

For each provider observation:
- retain the raw record, provider symbol, capability, observation time, and source terms;
- match strong identifiers before ticker/name text;
- resolve canonical instrument, listing, exchange/MIC, share class, and active state;
- store field-level source, confidence, observed-at, effective-at, and known-at metadata;
- detect ticker reuse, symbol changes, listing moves, class-share ambiguity, mergers,
  delisting, and relisting;
- queue ambiguous candidates for review instead of silently merging them;
- maintain listing/provider status independently so one provider cannot incorrectly
  deactivate a canonical instrument.

The local database is the authoritative read path. Scheduled/backfill jobs update it;
ordinary UI reads do not trigger uncontrolled provider fan-out.

#### Historical data, adjustment, and point-in-time correctness

Store raw provider bars separately from canonical derived views and retain provider/feed/
venue provenance. Add deterministic conflict selection, gap/anomaly detection, corporate
action reconciliation, rebuildable adjustment factors, cached derived timeframes, and
coverage ranges.

Support raw, split-adjusted, and total-return modes with a versioned adjustment set.
Calculations and caches must include adjustment mode/version in their identity.

Research and analysis rules:
- resolve universe membership as it was known at the evaluation time;
- never expose future bars, future constituent knowledge, or revised future metadata to
  a historical signal;
- distinguish event/signal time from forward-outcome time;
- exclude and count events that lack a complete requested outcome horizon;
- align comparisons on intersecting valid timestamps;
- never forward-fill across a gap that changes ratio/rotation meaning;
- label survivorship-biased or current-snapshot universes and reject them when a study
  explicitly requires point-in-time membership;
- return excluded instruments/events and exact reasons with every batch/study result.

#### Provider entitlement and capability governance

Add a versioned provider-entitlement registry with:
- provider, capability, configured plan, authentication requirement, and free/paid state;
- permitted personal/internal/commercial use and redistribution restrictions;
- request/token quota, historical horizon, venue coverage, and real-time/delayed/EOD
  semantics;
- effective/review date, enabled environments, and current live-probe result.

A provider is usable only when both its adapter and configured entitlement permit the
requested capability. Do not hard-code today's free-plan promises as permanent facts.

Promoting a provider/capability to supported requires:
- deterministic response fixtures and parser tests;
- capability/completeness and provenance tests;
- throttling, retry, cooldown, and failure-classification tests;
- an opt-in backend-reachable live probe;
- an entitlement/terms review.

Provider removal, changed terms, throttling, or exhausted quota must degrade the affected
capability honestly without inventing data or breaking unrelated providers.

#### Batch analytics and coverage APIs

Add batch-oriented backend services for:
- market-group trees, members, proxies, and related groups;
- technical/ranking snapshots;
- relative strength and normalized comparison;
- breadth and relative rotation;
- scan and Python-code evaluation;
- Study Lab runs and artifacts;
- coverage, provenance, and freshness;
- notes and workspace persistence.

Batch requests accept a universe selector, timeframe, as-of time, adjustment mode,
requested built-ins/code versions, filters, sorting, and pagination.

Each returned cell includes value, observation time, adjustment mode, source/freshness,
and structured warning/error. Each response includes universe provenance/membership
version, coverage, exclusions/reasons, calculation/code version, and refresh time.

Cache identity must include universe membership version, timeframe/date range/as-of time,
adjustment set, code/indicator/SDK version, requested fields, and source dataset versions.

#### Alerts, notes, and supported reports

Restyle price, indicator, and screener alerts as TC2000-style tools/dialogs.

Alert creation sources:
- chart price level;
- plotted indicator;
- saved condition;
- Boolean Python calculation;
- EasyScan entry/exit.

Retain alert status, repeat/rearm behavior, firing history, chart markers, notification
delivery, and instrument filtering.

Add per-symbol notes:
- autosave;
- modified timestamp;
- watchlist note indicator;
- symbol-linked notes window;
- user isolation.

Supported-data report:
- instrument identity and listings;
- sector and industry;
- market cap, P/E, beta, and dividend yield where available;
- 52-week range;
- average volume;
- identifiers;
- field-level provider provenance and freshness.

Do not expose earnings estimates/results, analyst opinions, news, or unavailable financial
statement fields.

#### Frontend architecture

Retain:
- Vue 3;
- TypeScript;
- Vite;
- Pinia for local interaction/session state;
- uPlot and the reusable portions of its existing plugins.

Add:
- `golden-layout` for workspace docking and pop-outs;
- `@tanstack/vue-query` for server state, polling, caching, invalidation, and deduplication;
- `@tanstack/vue-table` and `@tanstack/vue-virtual` for dense virtualized lists.

Core modules:
- `WorkspaceShell`: global menus, tabs, active workspace, search, and status;
- `WorkspaceLayoutHost`: Golden Layout integration, save/load, pop-outs, and recovery;
- `ToolRegistry`: tool metadata, factory, capability requirements, and schema version;
- `ToolWindowHost`: shared dense TC2000 window chrome;
- `LinkBus`: symbol, timeframe, crosshair, and selection events;
- `LibraryStore`: code assets, conditions, columns, column sets, scans, studies, chart templates,
  layout templates, and combo lists;
- `UPlotHost`: chart lifecycle, data binding, plugins, and resize behavior;
- `CapabilityRegistry`: supported, partial, and unavailable product/data capabilities.

Create centralized TC2000 Version 25 design tokens for:
- typography;
- spacing;
- window borders and gradients;
- toolbar height;
- menu and dialog geometry;
- tabs;
- hover/focus/selection states;
- scrollbars;
- table density;
- positive/negative/neutral colors;
- z-index and overlay rules.

Use the measured Version 25 font stack with Segoe-compatible fallbacks. Validate the
four required display-scale environments and the separate 125% browser-zoom robustness
case defined in `docs/tc2000-visual-parity.md`.

#### New persistence and API contracts

Keep existing dashboard tables and APIs untouched for `/legacy/*`. Create new persistence:

`workspace`:
- user ID;
- name;
- default flag;
- position;
- revision;
- settings;
- schema version;
- timestamps.

`workspace_tab`:
- workspace ID;
- stable key;
- name;
- position;
- Golden Layout configuration;
- active-window key;
- timestamps.

`workspace_window`:
- tab ID;
- stable instance key;
- tool type;
- title;
- link group;
- configuration;
- style;
- state-schema version;
- position;
- timestamps.

`workspace_library_item`:
- user ID;
- kind: code, condition, column, column set, scan, study, chart template, layout
  template, or combo list;
- stable key;
- name;
- version;
- payload;
- dependency metadata;
- timestamps.

`market_code_asset` and `market_code_version`:
- user ID, stable key, name, description, and intended output contract;
- immutable Python source version and SDK/runtime version;
- parameters/defaults, dependency metadata, required lookback, referenced symbols/
  universes, capability requirements, diagnostics, and timestamps.

`research_definition`, `research_run`, and `research_artifact`:
- owner, code-version reference, universe/benchmark/timeframe/date-range configuration,
  parameters, adjustment/session settings, and timestamps;
- queued/running/succeeded/failed/cancelled status, progress, heartbeat, resource usage,
  warnings, exclusions, dataset/reproducibility hash, and structured logs;
- typed compressed result artifacts for metrics, tables, plots, event sets, and
  multi-panel dashboards, with queryable metadata retained in PostgreSQL.

`provider_entitlement` and `dataset_snapshot`:
- provider/capability/plan, authentication, free/paid status, permitted deployment use,
  redistribution restriction, quota, historical horizon, venue/freshness semantics,
  review date, and enabled environments;
- exact input versions, universe membership, adjustments, provenance, coverage, and
  prepared Arrow/Parquet artifact references used by a code execution.

`instrument_note`:
- user ID;
- instrument ID;
- content;
- timestamps;
- unique user/instrument constraint.

`market_group`:
- stable key;
- type;
- name;
- parent;
- representative/equal-weight instrument;
- source and provenance;
- effective/known-at metadata.

`market_group_member` and `market_group_proxy`:
- group/instrument relationship;
- weight;
- relationship type;
- source;
- effective and known-at times;
- verification state.

Workspace endpoints:
- list/create/get/patch/delete workspaces;
- clone workspace;
- atomically save a complete workspace snapshot;
- library CRUD;
- library import/export.

Workspace snapshot writes:
- accept `base_revision`;
- atomically persist settings, tabs, layouts, and window states;
- increment revision;
- return `409` for stale revisions;
- let the leader fetch, merge disjoint instance-key changes, and retry once;
- create a named recovery copy instead of silently overwriting an unresolved conflict.

Code/research endpoints:
- SDK/capability registry and documentation;
- validate/compile;
- dependency and coverage preflight;
- scalar/series/Boolean/event batch evaluation;
- code asset/version CRUD and import/export through the workspace library;
- research definition/version CRUD, run/cancel/progress/log/artifact/compare/export.

Market/analysis endpoints:
- market-group tree;
- group details and members;
- related groups for a symbol;
- batch analysis snapshot;
- relative strength;
- relative rotation;
- breadth;
- per-instrument note read/write.

Batch analysis request supports:
- universe selector;
- timeframe and as-of time;
- requested built-in/code-version columns;
- filter and sort definitions;
- pagination.

Every returned cell includes:
- value;
- observation time;
- source/freshness status;
- structured warning/error where applicable.

Every batch response includes:
- universe provenance;
- coverage summary;
- excluded instruments and reasons;
- refresh time.

#### Polling, caching, and data flow

Use Vue Query as the single client polling coordinator:
- active latest-price views poll according to provider freshness policy;
- historical ranges do not poll;
- hidden tabs suspend chart polling;
- watchlists use one batch refresh per window rather than one request per cell;
- pop-outs share invalidation messages;
- only the elected leader initiates a refresh for a shared query key;
- stale requests are canceled when symbol, universe, timeframe, or code version changes.

Expose `current`, `delayed`, `stale`, `fetching`, `partial`, `coverage-limited`, and
`unavailable` states.
Provider failures leave prior data visible with stale/error labeling and retry actions.

Cache batch code, relative-strength, rotation, breadth, and study-preflight results using:
- universe membership/version;
- timeframe;
- as-of time;
- code/indicator/SDK version;
- requested columns;
- adjustment mode.

Alignment rules:
- use intersecting valid timestamps for comparisons;
- never forward-fill across a gap that changes the meaning of a ratio or rotation path;
- identify and exclude insufficient-history instruments with reasons;
- preserve point-in-time membership where the requested universe supports it.

#### Legacy interface and capability stubs

Routing:
- `/` and authenticated default routes open the new workstation;
- `/chart/:symbol` opens the default workspace and publishes the symbol to the active
  link group;
- current authenticated pages move under `/legacy/*`;
- legacy Radar, Strategy Lab, Baskets, ETF Holdings administration, seasonality,
  options, and provider diagnostics have no new-shell menu entry.

Preserve canonical data:
- watchlists;
- drawings;
- alerts;
- screeners;
- indicator presets;
- instruments/OHLCV;
- ETF holdings;
- baskets.

Do not migrate legacy dashboard layouts.

Create `docs/tc2000-parity.md` with every reviewed TC2000 surface and:
- supported/partial/excluded status;
- implementation location;
- backend/data dependency;
- validation evidence.

Create `docs/tc2000-capability-stubs.md` covering:
- options;
- brokerage/trading;
- news;
- analyst ratings;
- earnings/full financial statements;
- unavailable data/SDK capabilities.

Each stub must have:
- stable capability ID;
- intended inputs/outputs;
- provider/data requirements;
- frontend tool contract;
- explicit source-level TODO;
- enabling conditions;
- tests proving unavailable tools stay out of visible menus.

Backend provider protocols and frontend descriptors may exist for these domains, but their
routers/tools must remain unregistered until implemented.

#### Study Lab

Add Study Lab as a first-class primary-workstation tool. It owns open-ended market and
statistical research that is not naturally a chart indicator, ratio, scan, alert, or
position-based backtest.

Study Lab and Strategy Lab remain distinct:
- Study Lab answers what happened, how often, under which state/regime, how outcomes were
  distributed, and how the current state compares with history;
- Strategy Lab owns entries, exits, fills, positions, capital, portfolio state,
  execution assumptions, walk-forward tests, and paper-forward strategy behavior;
- both share code assets, indicators/statistics, universe resolution, point-in-time
  membership, coverage reporting, artifacts, and reproducibility primitives;
- new Strategy Lab signals reference immutable unified-Python code versions;
- existing `RULES`, `DSL`, and `PYTHON` strategy versions remain executable through
  compatibility adapters so saved work is not destroyed, but new authoring converges on
  the unified language.

Study types:
- arbitrary event definitions and historical occurrence analysis;
- positive/negative streaks and general state-duration studies;
- before/after behavior and forward returns over multiple horizons;
- breadth events, thrusts, new-high/new-low behavior, and moving-average participation;
- price/breadth and cross-market divergences;
- volatility, trend, breadth, and relative-strength regimes;
- calendar/day/month seasonality;
- cross-sectional ranking, correlation, regression, and relationship studies;
- distributions, percentiles, analogues, and current-state-versus-history comparisons.

Authoring and run controls:
- Python editor with autocomplete, signatures, SDK documentation, source diagnostics,
  formatting, and parameter declarations;
- generated parameter controls plus universe, benchmark, timeframe, date-range,
  adjustment, and session selectors;
- input-size, coverage, point-in-time membership, look-ahead, and survivorship preflight;
- run, cancel, clone, version, compare, archive, import, export, rerun-same-snapshot, and
  rerun-latest-data actions;
- durable queued status, progress, heartbeat, structured logs, warnings, exclusions,
  resource use, and artifacts.

Structured native result types:
- metric cards;
- time series and range/band plots;
- numeric/categorical bars and histograms;
- scatter plots;
- heatmap/matrix views;
- event sets;
- ranked/detail tables;
- summary-statistics tables;
- multi-panel dashboards composed from these types.

Implementation checkpoint: the unified runner now exposes typed `output.bar(...)` and
`output.range(...)` methods for the numeric/categorical-bar and lower/upper-band contracts.
The active Study Lab, persisted Research Results, and dashboard surfaces render both through
uPlot-backed components, with finite-value/dimension validation and no user-supplied UI code.
The active run panel also supports rerunning the immutable study against its saved snapshot
or latest canonical data through the versioned research API.
The primary editor includes editable factory templates for positive/negative close streaks,
moving-average participation, and relative-strength history; changing source returns the
editor to Custom Python while retaining the single unified language.

uPlot plus platform-owned plugins renders every axes-based numeric result. Vue/HTML
renders tables, metric cards, and layout. Do not add a second chart library and do not
allow study-authored HTML, CSS, JavaScript, or frontend components.

Result behavior:
- show sample size, mean, median, percentiles, dispersion, and confidence context where
  meaningful;
- highlight the current observation against the historical distribution;
- allow filtering/drill-down into underlying events and excluded cases;
- publish a selected occurrence's instrument/date to linked charts;
- export tabular artifacts;
- compare code/parameter/dataset versions;
- promote a suitable Boolean result to an alert, scan condition, watchlist column, or
  Strategy Lab signal source;
- save a suitable numeric series as a reusable chart plot.

Ship editable factory studies for:
- consecutive positive/negative closes;
- event frequency and occurrence browsing;
- multi-horizon forward returns;
- 90/90-style breadth events;
- new-high/new-low and moving-average breadth;
- price/breadth divergence;
- volatility and trend regimes;
- month/day seasonality;
- relative-strength regime changes;
- cross-sectional sector/industry ranking.

#### Failure and recovery behavior

Missing ETF holdings:
- use metadata-derived constituents only when available;
- label the fallback source;
- never imply official index membership.

Missing industry proxy:
- keep the industry and stocks usable;
- show “No mapped ETF proxy.”

Missing or misaligned bars:
- exclude misleading calculations;
- expose the exact reason;
- preserve other valid peers.

Unsupported Python/data capability:
- preserve/save the code version;
- report every missing SDK/data capability and coverage requirement;
- block dependent scans/alerts/columns/studies without losing configuration.

Sandbox timeout/resource violation:
- terminate and clean up the isolated worker;
- preserve bounded logs and execution metadata;
- return a structured resource-limit/security error without affecting API workers.

Provider throttling/outage:
- retain cached data;
- expose freshness/provider state;
- follow provider-policy retries and limits.

Changed or invalid provider entitlement:
- disable only the affected provider/capability;
- expose the plan/terms/configuration reason;
- fall through only to independently entitled providers.

Missing SPX/index series:
- use a clearly labelled tradable proxy such as SPY when configured;
- never silently rename the proxy to the official index.

Unknown/corrupt workspace tool:
- retain raw snapshot;
- load known windows;
- replace only the affected window with a recovery/export panel.

Concurrent browser sessions:
- use revision checks;
- merge only disjoint changes;
- create a recovery copy when automatic merge is unsafe.

Large lists:
- virtualize rows and columns;
- keep stable selection by instrument ID;
- cancel stale calculations;
- show incremental scan progress.

#### Required validation and acceptance

Backend unit/integration coverage:
- workspace CRUD, cloning, snapshots, conflicts, recovery, and user isolation;
- unified Python behavior across scalar/series/Boolean/event/study output contracts;
- AST diagnostics, source spans, dependencies, lookback, versioning, and cycles;
- sandbox network/subprocess/filesystem/import/reflection/dynamic-execution escape tests;
- CPU, memory, time, output, cancellation, crash, and orphan-cleanup enforcement;
- implemented SDK/indicator parity against the authoritative indicator engine;
- structured unsupported-capability and coverage errors;
- security-master matching, ambiguity, ticker reuse, delisting, listing moves, and
  provider field conflicts;
- provider entitlement, quota, cooldown, live-probe, and provenance behavior;
- raw/adjusted bar rebuilding and corporate-action correction;
- point-in-time membership, look-ahead prevention, complete forward horizons, and
  survivorship-bias handling;
- market taxonomy hierarchy and proxy provenance;
- no-proxy industries;
- batch snapshot filtering, sorting, pagination, and partial cell errors;
- relative-strength alignment and missing-history exclusion;
- breadth and relative-rotation math;
- Study Lab definition/version/run/artifact/reproduction behavior;
- notes and library isolation/import/export;
- unchanged legacy API behavior.

Frontend unit/component coverage:
- Golden Layout bind/unbind lifecycle;
- uPlot cleanup and non-recreation on resize/tab changes;
- every link-group rule;
- cross-window message handling and persistence leadership;
- keyboard routing and input-focus suppression;
- column add/remove/reorder/stack/pin/sort/manual ordering;
- Python editor, diagnostics, version-upgrade, and capability states;
- Study Lab output renderers and occurrence-to-chart linking;
- template application without symbol replacement;
- polling suspension and request deduplication;
- snapshot conflict recovery and schema upgrades;
- excluded tools absent from primary menus.

End-to-end flows:
- launch directly into `US Top Down`;
- select SPY and compare with RSP;
- rank all 11 sectors against SPY;
- select XLK and load industries/proxies/constituents;
- select NVDA and automatically open `NVDA/XLK` and `NVDA/SPY`;
- traverse constituents with Space while linked charts update;
- prove different/gray link groups do not change;
- float a chart and prove symbol/crosshair/persistence synchronization;
- customize, stack, pin, save, and restore watchlist columns;
- create a Python value column, use it in EasyScan, and create an alert;
- create the positive-close streak study, render its metrics/histogram, and inspect
  historical occurrences on a linked chart;
- promote a Study Lab Boolean result into a scan or alert;
- save/reload/import/export chart and layout templates;
- create/edit/lock/persist drawings;
- verify missing holdings, missing index series, stale bars, provider/entitlement failure,
  unsupported Python/data capability, sandbox failure, popup blocking, workspace
  conflict, and corrupt-tool recovery;
- verify legacy routes remain usable but absent from the primary interface.

Visual acceptance:
- complete the full capture matrix in `docs/tc2000-visual-parity.md`, not only the
  representative happy-path screens;
- maintain deterministic baselines at 1920x1080 and 2560x1440 at both 100% and 125%
  display scale, plus the separate 125% browser-zoom robustness check;
- compare component crops and full layouts against approved TC2000 Version 25 references;
- enforce one-CSS-pixel geometry, exact token/typography, delta-E-at-most-2 solid-color,
  and at-most-0.5-percent unmasked pixel-difference limits;
- require every mask and visual-regression difference to be narrowly justified,
  reviewed, and fixed when it is not an intentional product divergence.

Performance acceptance:
- cached symbol changes render without full-shell reflow;
- 100,000-point uPlot series remains interactively zoomable/pannable;
- 10,000-row watchlists do not create DOM proportional to row count;
- linked charts issue no duplicate identical OHLCV requests;
- docking/resizing/tab changes do not recreate uPlot;
- hidden tools do not continue expensive polling/rendering;
- browser memory remains stable while repeatedly opening/closing chart windows.
- warm sandbox calculations are responsive enough for interactive columns/scans;
- long studies remain cancellable and do not degrade API responsiveness.

Final validation:
- backend unit and integration suites;
- frontend unit/component suites;
- TypeScript check;
- production build;
- Playwright;
- sandbox security and resource-limit suites;
- deterministic provider tests and configured opt-in live probes;
- visual-regression suite;
- browser console inspection;
- backend log inspection;
- YAML/JSON parsing;
- migration upgrade/downgrade verification;
- `git diff --check`.

#### Locked assumptions

- Reference interface: TC2000 Version 25 desktop, pinned to build `25.0.9571`.
- Fidelity: pixel-close geometry and interaction, rebranded with original assets.
- Runtime: desktop browser with browser pop-outs, not Electron/Tauri and not mobile.
- Market updates: current polling, not streaming.
- Programming language: one Python-native market-analysis language and SDK; no separate
  executable PCF or Optuma language.
- Python dependencies: curated built-in library set only; no user/runtime package installs.
- Study output: structured native results only; no arbitrary HTML/CSS/JavaScript.
- Study Lab: a primary-workstation tool distinct from legacy Strategy Lab.
- Data providers: API-first, multi-source, reconciled, free-source-first, and never
  provider-specific in the frontend.
- yfinance: absent from default/new-workstation paths and retained only as an explicit
  temporary legacy fallback until audited away.
- Security master: canonical local records reconciled from multiple APIs; exchange
  directory files are optional evidence only.
- Market truth: provider/feed/freshness/coverage are always visible; consolidated
  real-time data is not promised.
- Legacy dashboards: retained only in the legacy frontend and not migrated.
- Extra current platform tools: hidden outside the core clone rather than removed.
- External unsupported domains: hidden, stubbed, and documented.
- Delivery model: one continuous full implementation stint followed by user-led
  fine-tuning and bug fixing, with no MVP or phase boundary treated as completion.

Why this is planned:
- The current frontend exposes powerful backend capabilities as separate routes and dense,
  unrelated surfaces rather than as one coherent analysis workstation.
- The backend already provides the reusable instrument, OHLCV, indicator, drawing, alert,
  screener, synthetic-expression, basket, and ETF-holdings foundations.
- Rebuilding the primary interaction model around TC2000-style linked workspaces makes the
  requested top-down daily market analysis fast while retaining uPlot's performance.

## Notes

- This file intentionally focuses on postponed work that already came up in discussion.
- It is not meant to replace issue tracking if we later decide to formalize roadmap management elsewhere.
- This is the only file that should be treated as the canonical TODO memory for deferred work in this repo.
