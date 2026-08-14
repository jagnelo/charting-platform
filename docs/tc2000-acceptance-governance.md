# TC2000 Workstation Acceptance Governance

Status: `Controlling completion and exception policy`

This policy makes the TC2000 workstation goal rigorous and finishable without pretending that
external evidence or hardware which is unavailable in the current environment has been tested.
It supplements `docs/project-todos.md` section 14 and
`docs/tc2000-visual-parity.md`; where an older document makes an external condition a blanket
completion blocker, this document controls.

## Evidence tracks

### Board-guided visual parity

The 230-image composite board in `docs/tc2000-reference-board.md` is the accepted visual and
interaction authority for every state it represents. A board-covered state is accepted when the
implementation has a measured deterministic local baseline, interaction coverage, and no
unexplained geometry, containment, overlap, console, or accessibility regression. It does not
need a locally captured permission-cleared screenshot of build `25.0.9571`.

Later exact-build evidence can improve or correct a board entry. It must identify a concrete
conflict before reopening already accepted board-guided work.

### Explicit visual gaps

A state with no sufficiently applicable board evidence is a gap, not a pass. It may proceed with
an original-but-TC2000-consistent component decision and an interim test oracle, but the gap must
remain recorded in the board register and visual manifest. The record must name the affected
surface/state, missing evidence, implementation decision, interim oracle, remaining risk, and
evidence that would close it.

### External service and hardware evidence

Provider adapters are accepted through deterministic fixtures, entitlement enforcement,
provenance/fallback behavior, and every live probe that is configured and authorised in the
environment. A missing credential or unavailable provider is a recorded live-evidence gap, not a
reason to block unrelated implementation or to claim live success.

Browser pop-out, cross-window synchronization, restoration, and placement tests are the
acceptance evidence for multi-window behavior. Native physical multi-monitor placement is a
recorded hardware-validation gap and a later audit, not a global blocker.

Endurance is evaluated by documented bounded stress runs, not an impossible “indefinite soak”.
The current minimum is the checked-in sustained runner/resource/cancellation probes plus the
100-round two-pop-out churn guard. Any higher budget must state duration/count, workload,
resource ceilings, outcome, and diagnostics.

## Mandatory flexibility ledger

Every time implementation or acceptance relies on one of the policies above, the developer must
say so in the progress report and append/update a row in the appropriate register:

| Situation | Required record |
|---|---|
| Board is used instead of a direct exact-build image | visual manifest state entry and the board gap register if the evidence is partial |
| No visual reference exists | `docs/tc2000-reference-board.md` gap row plus interim test/oracle |
| Fixture/contract evidence substitutes for a live provider | `ops/handoff.md` and provider/capability records |
| Browser evidence substitutes for physical multi-monitor hardware | `ops/handoff.md` and the applicable parity item |
| Bounded stress substitutes for indefinite operation | `ops/handoff.md` with exact budget and results |

Each progress report must contain a short **Acceptance flexibility used** section. It either lists
the specific ledger entries used in that advance or states `None`. A flexibility is never
implicit, and a gap is never removed merely because an interim oracle passed.

The developer must announce the applicable flexibility in progress commentary before starting
the implementation or evidence run that relies on it. The completion report repeats the same
entry, names the gap that remains open, and links the evidence produced. This prevents a relaxed
criterion from being applied silently or discovered only after a result is presented.

## Current-goal operating rule

The active Codex goal uses this policy as its acceptance interpretation. The following
substitutions are currently authorised for continued implementation, but none is a completion
claim:

This is an explicit goal update, not an informal interpretation: the 230-image browsable
reference board is the working visual target for represented states, while missing exact-build
captures are tracked as state-level gaps. The goal therefore remains active and actionable
against the board; it must not be marked blocked solely because the stronger exact-build audit
cannot run for a represented state. Conversely, the relaxed rule must never be used to silently
close an uncovered state, suppress a mismatch, or present interim evidence as exact-build proof.

| Relaxed criterion | Evidence currently allowed | Gap that remains open |
|---|---|---|
| Locally captured, permission-cleared exact-build V25 media for represented states | The 230-image browsable reference board, its provenance/measurements, and deterministic local baselines | Any state or detail not sufficiently represented by the board; stronger exact-build evidence may still correct a concrete conflict |
| Live provider credentials for every acceptance run | Canonical DB fixtures, adapter contracts, entitlement tests, and authorised live probes where configured | Live coverage/terms/quota evidence unavailable in this environment |
| Native physical multi-monitor validation | Browser pop-out, cross-window sync, restoration, and blocked-pop-out tests | Physical monitor placement and OS window-manager behavior |
| Indefinite soak testing | Bounded churn/resource/cancellation runs with an explicit budget | Longer-duration operational endurance beyond the recorded budget |

These rows must be repeated in the relevant handoff entry whenever used. The implementation may
continue past them, but the corresponding gap IDs remain actionable until closure evidence is
recorded. A progress report that uses none of these substitutions must say `Acceptance flexibility
used: None` explicitly.

### Required reporting wording

Every advance that relies on a relaxed criterion must identify the substitution before the work
or evidence run starts, then repeat it after the run with: (a) the gap ID(s) still open, (b) the
interim evidence produced, and (c) the concrete evidence or environmental condition needed to
close the gap. “Accepted” means accepted on the documented interim track only; it never means
the gap has disappeared.

## Completion decision

The workstation may be presented for user-led fine-tuning when all in-scope implementation,
functional, security, migration, performance, and deterministic visual/interactions acceptance
checks pass; every board-covered state has evidence; and every remaining external or
unrepresented-state limitation is explicitly recorded with its interim oracle and closure path.

It must not claim exact TC2000 verification for a gap, conceal a limitation with a broad image
mask, invent provider data, or loosen the product boundaries. The outstanding flexibility ledger
is part of the handoff and remains actionable follow-up work.

## Initial robust workstation gate (not overall completion)

The first genuinely usable TC2000-style workstation is a narrower operational gate inside the
single continuous goal. It may be presented for daily top-down analysis once the following are
true in a clean authenticated deployment:

- the `US Top Down` layout opens directly into the workstation shell;
- SPY/RSP benchmark comparison, all 11 sector views, sector-to-industry/proxy/constituent
  drill-down, and `XLK/SPY`, `XLK/XLE`, `NVDA/XLK`, and `NVDA/SPY` ratios work without seeded
  fixture-only routing;
- the primary chart, linked symbol/timeframe groups, keyboard traversal, watchlist sorting and
  filtering, persistence, pop-outs, notes, alerts, and freshness/error states work together;
- Python code can be reused as a column, condition/scan, alert, and chart/study output, and the
  positive-close streak Study Lab example completes with inspectable metrics and occurrences;
- the clean browser, backend, type/build, and service-log gates pass with no known shared-state,
  security, or data-integrity defect.

This gate does **not** require all 496 ETF issuers to have native routes. Provider work is
prioritised by the universes needed for the core US workflow; the remaining issuer audits,
broader free-source coverage, exact-build/reference gaps, native physical-monitor validation,
and endurance evidence remain open completion work and must stay visible in the handoff. Seeded
fixtures may continue to support deterministic regression tests, but they cannot be the sole
evidence for this initial live-workstation gate.

### 2026-08-11 gate evidence

The rebuilt branch deployment satisfies this operational gate on the canonical, non-seeded path:

- branch health reports `e2e_seed_instruments=false` and `e2e_seed_market_data=false`;
- the complete authenticated Chromium matrix passes `88/88`, including live canonical benchmark
  and sector membership, SPY/RSP comparison, sector-to-industry/proxy/constituent drilldown,
  ratio editing and automatic ratios, linking, keyboard traversal, persistence, pop-outs, notes,
  alerts, freshness/error states, Python reuse, and the positive-close Study Lab study;
- the frontend Vitest suite passes `691/691`, type-check and production build pass, and the
  branch service/log audit is clean for tracked runtime-error signatures.

This establishes the initial daily-analysis workstation as operational. It is not the overall
completion claim: exact-build/unrepresented visual states, broader free-source/provider evidence,
native physical-monitor placement, beyond-bounded endurance, and the final requirement audit remain
open and actionable. Acceptance flexibility used: **None**.

### Expanded benchmark-family gate

The family gate is also a visual/workflow matrix. The acceptance run must launch each of the
eight roots (S&P 500/400/600/1500, Russell 1000/2000/3000, Nasdaq 100), select every mapped
cap/equal/value/growth leg, and exercise the same top-down, breadth, ratio, ranking, rotation,
and member drill-down contracts. The Nasdaq 100 cap/equal fixture is QQQ versus QQQE only when
canonical identity, holdings, and relationship evidence are verified. Missing or ambiguous
family/style evidence is a labelled gap or unavailable state, never a silent fallback and never
a reason to lower the global visual thresholds.

The QQQE provider-route sub-gate is now evidenced: canonical route metadata selects the explicit
Direxion adapter, and an opt-in live probe parsed the public symbol-scoped holdings export. This
does not satisfy the broader Nasdaq-100 fixture by itself. Historical rebalance continuity,
point-in-time membership, bars, and populated browser cap/equal visuals remain separate required
acceptance cases.

The top-down completion bar now covers S&P 500/400/600/1500, Russell 1000/2000/3000, and Nasdaq
100, not only SPY/SPX. The authenticated and backend acceptance matrix must prove that each family
can be selected as a versioned universe and exposes, where source evidence permits, its official
identity, cap-weighted proxy, equal-weight proxy/derived series, and value/growth variants. A
missing mapping must display `No verified mapped proxy` with provenance; it cannot silently fall
back to SPY, QQQ, or an unrelated family.

For every available family/style variant, acceptance must exercise the same benchmark technicals,
cap/equal/style spread, generic predicate breadth, participation/leadership, concentration,
dispersion, drawdown/volatility, relative rotation, cross-family ranking, and member drill-down
contracts. Equal-weight results must state whether weights are ETF-native or locally derived from a
point-in-time membership snapshot. The Nasdaq 100 must have a cap/equal deconstruction equivalent
to SPY/RSP (for example QQQ versus a separately verified equal-weight proxy such as QQQE). This is
a scope expansion, not a relaxation; incomplete provider, membership, or visual evidence remains
an explicit gap.

The family gate also covers factor/style analysis, not only benchmark-versus-equal pairs. The
acceptance run must attempt the verified value and growth variants for S&P 500/400/600/1500 and
Russell 1000/2000/3000, record `No verified mapped proxy` for any family without an evidenced
variant, and prove that available variants inherit the benchmark technical, breadth,
participation, concentration/dispersion, volatility/drawdown, rotation, ranking, and member
drill-down contracts. Cross-family ratios (for example S&P 500 versus Russell 2000 or a value leg
versus its cap parent) must preserve timestamp alignment, adjustment, membership version,
coverage, and provenance. A current ETF snapshot cannot satisfy a historical family study without
an explicit current-snapshot/survivorship warning, and no relationship may be inferred from naming
alone.

### Expanded condition-driven breadth gate

The fixed Market Breadth panel is not sufficient evidence for the broader breadth requirement.
Completion acceptance must prove one generic definition contract across multiple universe types
and conditions. At minimum, the authenticated browser and backend suites must demonstrate:

- a point-in-time, explicitly labelled SPY ETF-proxy constituent universe;
- percentage of eligible members above a configurable 200-day average;
- percentage of eligible members within 1% of their 52-week high;
- identical condition/universe semantics for current snapshots and aligned historical series;
- denominator, coverage, exclusions, provenance, membership date/version, and freshness visible
  at the result surface;
- passing/failing member drill-down and symbol publication into linked charts;
- reuse of the same definition as a Study Lab artifact and, where output contracts permit, a
  chart pane/plot, watchlist column/filter, EasyScan condition, Market Gauge, alert, and export;
- partial data, missing bars, incomplete holdings, current-snapshot-versus-point-in-time, and
  unsupported-capability paths returning explicit structured warnings rather than silently
  changing the universe or condition.

The existing MA20/50/200, near-high/low, new-high/low, trend, and distance controls remain
convenience presets and retain their current regression coverage. They cannot close this gate
unless they execute through the generic definition contract. No visual threshold or acceptance
flexibility is being relaxed by this expansion.

Implementation checkpoint (2026-08-14): the generic current-snapshot contract is now present at
`POST /analysis/breadth`, with local group, ETF-holdings-proxy, and explicit-symbol resolution;
deterministic condition evaluation; stable definition/membership hashes; per-member results;
coverage, freshness, and structured exclusions. The breadth tool exposes the first composer for
the two representative condition forms. This evidence closes only the initial backend/UI slice;
the historical, unified-Python, independent-uPlot, promotion, and full point-in-time ETF gates
remain required and are not being silently treated as complete.

Implementation checkpoint 2 (2026-08-14): aligned historical generic breadth and isolated Python
reuse are now implemented. The API and runner use the same condition definition, expose per-date
denominators/coverage/exclusions, and never forward-fill a member absent at a timestamp; the
workstation renders the history with uPlot and Study Lab includes two representative factory
starters. This does not close the gate: ETF point-in-time browser evidence, arbitrary Python
combination parity, and promotion/reuse acceptance remain mandatory.

#### Breadth “around what?” acceptance rule

Acceptance must verify that the user can choose what is being measured and what it is being tested
against, rather than only choosing among fixed breadth labels. The saved definition must expose:

- the canonical universe and point-in-time membership policy;
- the measured field or derived Python series;
- the target/relationship and operator (average, threshold, range, percentile, prior high/low,
  benchmark/peer ratio, event, or derived series);
- timeframe, lookback, session, adjustment, timestamp alignment, and as-of/known-at policy;
- nested AND/OR/NOT composition with clause-level diagnostics.

The acceptance fixtures must include both `close > SMA(close, 200)` and “within 1% of the rolling
252-session high” over the same explicitly labelled SPY ETF-proxy universe, plus at least one
relative-strength or volume/volatility relationship. Each fixture must show aggregate history,
per-member pass/fail, denominator/coverage, exact exclusions, provenance, and current-versus-
historical semantics. A fixed metric route or selector that cannot express the target relationship
does not satisfy this gate, even if its aggregate percentage is numerically correct.

Implementation checkpoint 3 (2026-08-14): nested composition and scalar comparisons are now
implemented in both the canonical API evaluator and isolated Python runner. Focused service/runner
coverage passes `93/93`, generic API/history integration passes `2/2`, and the workstation exposes
field/operator/target/benchmark controls plus aggregate pass/fail member drill-down. This closes
the previously missing compositional API/runtime slice only. User-authored Python condition
execution, full visual condition-tree editing, chart-linked historical occurrences, and all
promotion targets remain mandatory acceptance work; no visual threshold or acceptance flexibility
was changed.

#### Latest breadth expansion — quantifier and target-scope contract

The acceptance oracle now treats breadth as `count(predicate(member, timestamp)) / eligible`
over the selected point-in-time universe. It is not sufficient to expose a larger list of preset
labels. The visual editor and API contract must independently identify the measured field/series,
the target/relationship, operator, lookback, timestamp alignment, and composition. The target
scope must be explicit: member-level thresholds, moving averages, prior highs/lows, benchmark or
peer ratios, events, and derived series are evaluated per member before aggregation; a
cross-sectional rank/percentile or group statistic is a separate derived output.

The representative acceptance set is expanded to include the existing 200-day and within-1%
52-week-high predicates plus volume-vs-average, an RSI range, a selected-member/benchmark ratio,
and a nested combination. Each must produce the same aggregate, member pass/fail, history,
state-change/occurrence, denominator, coverage, exclusion, provenance, and reproducibility
outputs. The same immutable definition must be reusable in Study Lab and every compatible
uPlot/list/filter/scan/gauge/alert/export target. Python is the authoritative escape hatch for
predicates outside the visual subset, but only through the isolated runner and declared dataset
manifest. This is a requirements expansion, not an acceptance relaxation; the compact composer,
platform-owned comparisons, visual tree, Python execution, historical linking, and promotion gaps
remain open until their own evidence passes.

### 2026-08-11 bounded endurance evidence

The governed two-popout churn guard was run with `TC2000_POP_OUT_CHURN_ROUNDS=100`. Both performance
tests passed (`2/2`) in `2.6m`: initial multi-chart/pop-out recovery remained bounded, and all 100
two-popout open/close rounds returned to the source tool/canvas baseline. Chromium memory ceilings
and browser diagnostics passed, and the narrowed backend/worker/research-runner runtime audit found
no tracked error signatures. This is the documented bounded-stress substitution for indefinite soak;
longer-duration endurance remains open. Acceptance flexibility used: **bounded stress in place of
indefinite soak**.

## Goal-level blocker tie-breaking

An isolated, recoverable defect in one tool or interaction must not block the entire TC2000 rework by default. The defect remains a named acceptance failure with a reproduction, attempted fixes, regression tests, and current evidence, while unrelated in-scope implementation and validation continue.

Escalate a defect to a goal-wide blocker only when at least one of these is true:

- it prevents a broad class of workflows or corrupts shared persisted state;
- it creates a security, data-integrity, sandbox, or irreversible-loss risk;
- it invalidates the acceptance oracle for a major surface rather than one localized state;
- no meaningful in-scope work or evidence can proceed independently;
- the same failure remains after three independently validated remediation attempts and the remaining work requires an external dependency or user decision.

A localized Add Tool tab-activation defect is therefore tracked as a blocking acceptance failure for that interaction, but does not by itself block the whole product goal. Each attempted fix must be followed by focused automated verification, broader regression checks where relevant, and an explicit report of whether the defect remains.

This rule is also an explicit instruction of the active Codex goal: when two acceptance signals
conflict, prefer the smallest scoped interpretation that preserves safety and truthful reporting.
Continue independent implementation and tests, record the weaker signal as an open acceptance gap,
and only stop the whole goal for the escalation conditions above. A transient or ordering-sensitive
test failure must be reproduced in isolation and in the nearest relevant sequence before it is
classified as a product blocker; if it cannot be reproduced, retain the failure evidence and add a
regression guard rather than treating it as resolved or blocking the goal.
