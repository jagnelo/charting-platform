# TC2000 Frontend Rework Roadmap

Status: active implementation roadmap  
Branch: `feat/tc2000-frontend-rework`  
Parent: `staging`  
Last reconciled: 2026-09-04

This is the concise, branch-owned execution map for the TC2000 frontend rework. The chronological
records in `docs/project-todos.md`, `docs/tc2000-parity.md`,
`docs/tc2000-acceptance-governance.md`, and `docs/tc2000-visual-parity.md` remain the detailed
evidence ledgers. If a summary here conflicts with a dated test receipt or the current code, the
current code and fresh evidence win.

The latest exhaustive gate ran at product commit `0da00e08` (`feat(tc2000): promote event
artifacts to filters and alerts`). A follow-up product fix is now committed as `7c930fd1`
(`fix(tc2000): scope event adapter by instrument`): event rows carrying a symbol or canonical
instrument ID can no longer match a different candidate. The focused event suite passed `8/8`, the
full runner unit suite `107/107`, event-promotion integration passed `2/2`, and compileall/Ruff/
diff checks passed. All stages through authenticated functional Playwright passed at `0da00e08`:
backend units `1,309/1,309`, integration `381/381` with the existing `54` warnings, combined
coverage `80.90%`, frontend Vitest `934/934` across `108` files, and functional Playwright
`155` passes with `106` documented skips across `261` specs. Static/type/build/compile, compose,
provider-policy, stack-health, and runner-isolation checks also passed. The unchanged visual
matrix remains the only gate failure: `98/104` passed and six screenshot diffs remain—
`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` differing pixels), and
`workspace-floating` at all four projects (latest captures: `11,901`, `9,770`, `12,097`, and
`12,097` differing pixels). Docker stack teardown and resource accounting were clean; no visual
oracle, provider fallback, or acceptance policy was changed.

The work is one continuous delivery stint, not an MVP followed by optional phases. The workstreams
below are dependency-ordered checkpoints so correctness, data lineage, and visual evidence can be
verified without weakening the end goal.

## Product end state

Deliver a rebranded, TC2000 V25-inspired US-market workstation that lets a swing trader move
quickly from the whole market to a trade candidate while preserving source, time, and analytical
lineage:

1. start at an index or ETF benchmark and compare cap-weighted, equal-weight, value, and growth
   views only where those roles are supported by evidence;
2. drill from benchmark to sector, optional industry/proxy, and constituent;
3. compare ratios such as `XLK/SPY`, `XLK/XLE`, `NVDA/XLK`, and `NVDA/SPY` alongside price,
   indicators, drawings, breadth, rotation, rankings, scans, gauges, and alerts;
4. use the same versioned `WatchlistSource` contract for locked index/ETF populations and editable
   personal, managed, combo, sector, industry, and explicit lists;
5. create arbitrary reproducible studies in one Python-native method, edit the visual subset as
   the same AST, and promote compatible immutable outputs throughout the workstation;
6. restore authenticated layouts, linked tools, tabs, pop-outs, selections, studies, and drawings
   reliably across sessions and windows;
7. expose freshness, coverage, provider, entitlement, effective-time, known-time, and unavailable
   states rather than substituting or fabricating data.

### Required benchmark-family roots

- S&P 500, S&P 400, S&P 600, and S&P 1500
- Russell 1000, Russell 2000, and Russell 3000
- Nasdaq 100

Cap/equal/value/growth legs are independent. A root or role is not complete merely because its
identity exists or another proxy can be substituted. QQQ/QQQE is the intended Nasdaq 100
cap/equal comparison when the underlying evidence and entitlement permit it.

## Non-negotiable decisions recovered from the prior session

- TC2000 V25 is the behavioral and visual direction, not a license to copy branding or to call an
  unverified screenshot exact parity.
- uPlot remains the sole renderer for numeric time-series plots.
- New canonical market-data paths are free-source-first, must not require a paid subscription for
  the core workflow, and must not introduce `yfinance`.
- User-authored programming has one Python-native model. The visual editor is a constrained editor
  for the same Python-backed AST, not a separate language.
- Locked sources prevent membership edits only. They remain available to follow, pin, clone,
  chart, map, ratio, breadth, scan, gauge, alert, and Study Lab workflows.
- Market Map is source-polymorphic and hierarchical. It must support arbitrary versioned sources,
  arbitrary supported periods, sector/industry grouping, configurable area and colour metrics,
  and selection handoff without per-tile provider fan-out.
- Breadth is an arbitrary predicate over an arbitrary versioned universe, with current and
  historical results, pass count, denominator, exclusions, and member-level evidence.
- Repository-controlled defects encountered in an acceptance path are fixed and regression-tested;
  they are not relabeled as external blockers. An unavailable external source remains an explicit
  data gap rather than a reason to weaken an oracle.
- Trading/broker execution, options workflows, news, analyst ratings, earnings, full financial
  statements, paid core dependencies, and consolidated real-time feeds are outside this roadmap.

## Evidence reconciliation

| Evidence | What it establishes | Authority and limitation |
| --- | --- | --- |
| Current branch and durable TC2000 ledgers | Implemented behavior, named gaps, and historical validation receipts | Primary repo evidence; old receipts are not fresh reruns |
| Prior Codex rollout `019fa949-e419-77c1-8d7d-188b5235029c` | Product intent, tie-breaks, scope additions, acceptance expectations, and user examples across 78 canonical user turns | Historical deliberation; implementation claims were reconciled against the current repo |
| Four distinct user-shared visual subjects | A breadth-over-price example and Finviz-style constituent, sector, and industry treemaps | Product/composition requirements only; they are not TC2000 pixel authorities |
| Reconstructed TC2000 public reference pack | 230 hash-indexed images from 26 source groups, covering dense lists/grids, chart chrome, linking, tabs/windows, gauges, editors, and shared layouts | Discovery/behavior/board evidence under the manifest; not blanket exact-build approval |
| Deterministic seeded browser evidence | Repeatable product-state and cross-environment regression coverage | Does not prove provider population, historical continuity, entitlements, or exact V25 pixels |

The rollout contains hundreds of `input_image` occurrences because compaction/replay repeated the
same material. After deduplicating the user intent, there are four distinct user-shared visual
subjects. The larger 230-image corpus is a separately fetched public reference board, not 230 user
attachments.

The fetched reference pack is reproducible through
`tests/visual/fetch-tc2000-v25-reference-pack.sh` and
`tests/visual/build-tc2000-reference-board.py`. A `/private/tmp` copy is useful for inspection but
is not durable evidence. Any long-lived archive must keep the index, source URLs, hashes, retrieval
date, and authority classification in a controlled artifact location without committing copied
third-party media blindly.

## Current baseline

These capability claims are inherited from the latest detailed records dated 2026-08-19 unless a
row explicitly says it was checked on 2026-09-03. They are the starting point for a fresh baseline
run, not a claim that the old counts still pass unchanged.

| Capability | Current understanding | Evidence boundary |
| --- | --- | --- |
| Authenticated workstation shell, layouts, linking, persistence, keyboard traversal | Substantially implemented | Historical unit and browser coverage; fresh branch run pending |
| Seeded top-down trader path | Benchmark → sector → ratio/indicator/drawing → industry → constituent → restored state passed | Fixture-backed; canonical live-source equivalent remains open |
| Eight-family entry matrix | Seeded Market Map, breadth, and rotation paths passed | Identity/fixture coverage is not complete provider population |
| Market Map | Recursive sector → industry geometry, source polymorphism, selection, follow/pin/clone, and cross-tab Breadth/Study handoff implemented | Exact nested typography/gutters/hover density and point-in-time data completeness remain open |
| Breadth and Study Lab | Recursive conditions, symbol/reference-universe comparisons, historical contracts, Python isolation, reusable immutable definitions, and some typed promotion adapters implemented | Richer history and complete promotion fan-out remain open |
| Visual regression | Exact-tip four-project run at `0da00e08` passed 98/104; six board-state diffs remain: `watchlist-column-editor-open` at both 1080p projects (`13,844` pixels) and `workspace-floating` at all four projects (latest captures `11,901`, `9,770`, `12,097`, `12,097`) | Board-guided product baseline, not exact V25 approval; canonical late-popout hydration now makes the floating state data-bearing; do not weaken or silently rewrite the visual policy |
| Frontend static/unit checks | Exact-tip gate passed 934/934 Vitest across 108 files, plus type-check and build | Fresh receipt at `0da00e08`; existing large-chunk build warning remains |
| Branch ancestry | Feature product tip `7c930fd1`; local staging `8b885a2f`; staging is an ancestor, feature remains staging-derived | Verified 2026-09-04; no merge/rebase performed during this checkpoint |
| Public visual corpus | 230 indexed media assets reconstructed and the board/manifest validators passed | Verified 2026-09-03 in an ephemeral inspection directory |

The earlier concern that Market Map → Breadth/Study handoff was still failing is superseded by the
later 2026-08-19 repair and `1/1` browser receipt in the repo. A separate late-session mention of a
Golden Layout activation problem is ambiguous relative to later passing fixes; treat it as a
reproduction target, not a confirmed current defect.

### Rough progress view

These are planning estimates, not acceptance percentages and not an arithmetic completion score:

| Area | Rough maturity | Why it is not complete |
| --- | ---: | --- |
| Workstation foundations and persisted mechanics | 90% | Fresh synchronization/baseline and native-window audit remain |
| Deterministic top-down swing-trader workflow | 85% | Canonical-data counterpart is not yet proven |
| Source-polymorphic map, breadth, and drill-down | 75% | History, complete populations, and richer analytics remain |
| Unified Python research and reusable outputs | 70% | Promotion compatibility matrix is partial |
| Canonical provider population and point-in-time history | 35% | This is the largest practical readiness gap |
| Exact V25 visual/state evidence | 45% | Many states remain `required_missing`; board-guided is interim |
| External/runtime/endurance acceptance | 50% | Live-provider, entitlement, native multi-window, and extended-soak proof remain |

Overall functional implementation is roughly 65–70% mature, while real-data daily readiness is
materially lower because family population and point-in-time history are gating inputs.

## Dependency-ordered workstreams

### R0 — Re-establish a current, reproducible baseline

Objective: begin feature work from a known green staging checkpoint without discarding the two
branch-owned workstream commits or treating August receipts as current.

Tasks:

- reconcile the 14 staging commits currently ahead of the branch using the repository-prescribed
  feature synchronization workflow;
- inventory changed validation/runtime rules before running product gates;
- run type-check, full frontend unit coverage, production build, the focused authenticated
  top-down/family/Market Map → Breadth/Study flows, and the unchanged four-environment visual suite;
- reproduce the ambiguous Golden Layout activation concern across open/close, cross-tab handoff,
  save/restore, and repeated family traversal;
- record exact commands, environment, commit, counts, skips, and acceptance flexibility.

Exit evidence: the selected staging checkpoint is an ancestor of the feature head, the worktree is
clean, all named baseline gates have fresh receipts, and any failure is either fixed with a focused
regression or recorded with an exact external cause.

### R1 — Complete canonical family population and point-in-time data

Objective: make the eight benchmark roots and every evidenced role genuinely usable from local
canonical data rather than identity-only or seeded fixtures.

Tasks:

- maintain an explicit root/role/provider/entitlement matrix, including unsupported and pending
  legs; never infer a role from a neighboring ETF;
- hydrate dated holdings with provider evidence, effective time, known time, weights, and
  continuity across rebalance/month-end boundaries;
- hydrate adjusted D1/W1/MN member bars to declared analysis floors and expose covered versus
  analysis-ready counts;
- retain point-in-time sector/industry classification and market-cap/weight inputs without future
  leakage;
- run bounded scheduled ingestion/backfill outside interactive reads; no UI-triggered provider
  fan-out and no fabricated fallbacks;
- document provider terms, rate limits, provenance, cache behavior, failure modes, and deployment
  bootstrap/maintenance operations.

Exit evidence: every required root/role has a dated status; supported legs can reconstruct their
universe and analysis inputs at multiple dates; unavailable legs say why; live probes and database
assertions match the UI coverage/provenance display.

### R2 — Prove the canonical top-down daily workflow

Objective: make the target swing-trader journey pass on canonical provider-backed data, with the
seeded path retained as a deterministic regression rather than a substitute.

Tasks:

- prove benchmark → cap/equal/style → sector → optional industry/proxy → constituent traversal;
- prove benchmark, sector, cross-sector, constituent/sector, and constituent/benchmark ratios;
- preserve linked symbol/timeframe, indicators, drawings, selection, keyboard traversal, and
  save/restore across the journey;
- prove the same Market Map and downstream actions for locked system sources and editable personal
  sources;
- display actionable pending, partial, stale, delayed, unavailable, and entitlement states.

Exit evidence: authenticated live-source browser oracles pass for each supported family role and
for one editable source; source version, as-of time, provider, exclusions, and readiness remain
visible throughout the flow.

### R3 — Finish breadth, rotation, ranking, and historical analytics

Objective: turn the existing general contracts into complete current and historical decision tools.

Tasks:

- complete condition-driven breadth history and occurrences for price/MA, near-high/new-high,
  trend, relative-strength, event, Python, and mixed/cross-sectional predicates;
- preserve denominator, pass/fail/excluded members, missing-reason diagnostics, source version,
  adjustment, timeframe, and benchmark alignment at every date;
- add multi-stage derived-series composition without forward-filling unavailable observations;
- extend rotation history beyond bounded tails and add concentration, dispersion, and
  condition-driven ranking where canonical inputs support them;
- keep map colour/area and historical grouping metrics point-in-time safe.

Exit evidence: current and historical outputs reconcile to independently computed fixtures and at
least one canonical populated family, with reproducibility hashes and no look-ahead leakage.

### R4 — Complete compatible artifact promotion

Objective: let one immutable, reproducible definition travel to every compatible workstation
surface without inventing coercions for incompatible result shapes.

Tasks:

- define the output-shape/capability matrix for scalar numeric, Boolean, series, event,
  cross-sectional, aggregate, and structured results;
- finish adapters for columns, filters, scans, gauges, alerts, chart plots, and Strategy Lab
  signals where the matrix permits them;
- keep code version, dataset manifest, run configuration, source version, output name,
  reproducibility hash, and promotion semantics intact;
- return structured capability errors for invalid promotions;
- make visual-subset edits round-trip through the same Python-backed AST.

Exit evidence: each compatible cell has unit, authenticated API, persistence, and consuming-UI
proof; each incompatible cell has a stable explicit error contract.

### R5 — Close V25 visual and interaction evidence gaps

Objective: converge the rebranded workstation on the reference hierarchy state by state, without
confusing deterministic screenshots, public discovery media, and exact-build authority.

Tasks:

- preserve a reproducible receipt for the 230-item/26-group public board and map every used image to
  a manifest state and authority class;
- work through every `required_missing` state, prioritizing source/picker actions, nested treemap
  labels/gutters/hover density, Study Lab/promotion controls, error/loading/freshness states,
  keyboard-selected states, tool menus, and blocked-popout recovery;
- derive and test dense typography, row height, gutters, headers, menu hierarchy, selection,
  linking colours, chart chrome, gauge geometry, and state variants from authorized evidence;
- use the user-supplied Finviz maps to guide hierarchy and information density, not TC2000 pixel
  values or branding;
- retain all thresholds, masks, overlap assertions, and multi-scale projects unless a separately
  reviewed evidence change justifies an update.

Exit evidence: every required state is `approved`, `board_covered` with an explicit limitation, or
`required_missing` with an exact acquisition blocker; the unchanged 104-case deterministic matrix
and any approved exact-reference gates pass.

### R6 — Close resilience, native-window, accessibility, and performance gaps

Objective: prove the workstation remains usable during real multi-tool research rather than only
in isolated component paths.

Tasks:

- stress Golden Layout tab activation, tool replacement, close/reopen, maximize/restore,
  cross-tab publication, and stale callback rejection;
- distinguish browser pop-out simulation from native multi-monitor behavior and obtain explicit
  native evidence where the product claims it;
- extend beyond the bounded 100-round two-pop-out guard with a declared workload, duration, memory
  budget, listener/window leak checks, and recovery assertions;
- verify 10k-cell Market Map interaction, dense grids, linked crosshairs, pan/zoom, drawing, and
  keyboard response against explicit budgets;
- close accessibility, authentication, authorization, sandbox, persistence, export, migration,
  logging, and critical console/network diagnostics.

Exit evidence: repeatable endurance and performance receipts meet declared budgets on supported
display scales; native/browser limitations remain explicit; no critical diagnostics or leaked
windows/listeners remain.

### R7 — Final product audit and review handoff

Objective: demonstrate that the product end state is complete without relying on hidden fixtures,
stale receipts, undocumented waivers, or unavailable evidence.

Tasks:

- audit every requirement against code, current tests, live evidence, manifest state, and provider
  readiness;
- run changed tests, complete frontend/backend suites, migrations, visual gates, authenticated
  browser suites, opt-in live provider checks, and the repository exhaustive integration gate;
- reconcile all skips, expected failures, acceptance-flexibility entries, security findings,
  deployment/bootstrap instructions, and remaining external limitations;
- update the detailed ledgers and this roadmap with exact final evidence.

Exit evidence: every in-scope end goal has a current receipt, every external limitation is
accurately visible to the user/operator, the worktree is clean and pushed, and the branch stops at
`ready_for_human_review`. Integration and deployment still require separate human authorization.

## Completion definition

The TC2000 frontend rework is ready for human review only when all of the following are true:

- the canonical live-data version of the top-down workflow passes for all supported roots/roles;
- unsupported or unentitled roots/roles are explicit and evidence-backed, not silently replaced;
- historical universe, weights, classifications, bars, and analytical results respect effective
  and known-time boundaries;
- arbitrary source-polymorphic Market Map and breadth workflows preserve immutable source lineage;
- Python/visual definitions and all compatible promotions are reproducible and round-trip safely;
- persisted, linked, cross-window, keyboard, drawing, and dense-workstation behavior survives the
  declared endurance matrix;
- every required visual state has an honest manifest disposition and all applicable visual gates
  pass unchanged;
- full automated, live-provider, security, migration, performance, and exhaustive integration
  evidence is current at the exact feature tip;
- no hidden fixture, paid-provider assumption, acceptance waiver, or stale historical claim is
  presented as product completion.

## Immediate next checkpoint

Execute R0 only far enough to synchronize the feature with a selected green staging checkpoint and
produce a fresh baseline. Then begin R1 with the root/role/provider/entitlement matrix and use it to
choose the first real population/history slice. Do not start opportunistic visual polishing before
the current runtime and canonical-data prerequisites are known.
