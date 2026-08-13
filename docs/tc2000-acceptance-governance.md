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
