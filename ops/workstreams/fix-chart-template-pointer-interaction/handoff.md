# fix/chart-template-pointer-interaction

Created from `staging` at `5267f11a491795d85ee35b56cabbe550394f3823`.

## Human authorization

- Recorded at: 2026-10-15T17:44:28.775011+00:00
- Request: Human approved the coordinator proposal to open a narrowly scoped chart-template pointer repair and stated: Yes I approve, and you do not need my acceptance to close it off, it is a waste of time for me to individually verify each individual fix in all the 4 parallel development branches - do this yourself, with care, I just want to get to the merged-into-staging state to finally try this out. Scope: repair physical desktop overlap between populated comparison chips and Plots; preserve no-comparison default and passing narrow layout; validate with ordinary pointer actions, required full profile and exact CI; coordinator owns technical closure and staging integration. No other feature worktree writes, Help oracle changes, provider calls, deployment or data cleanup.
- Closure record: pending validation; human already delegated technical closure for this narrow repair. Deployment remains unauthorized.
- Planning state: ready; PTR1-PTR5 and full_stack_browser retain all required validation. Delegated technical closure will be recorded after validation; deployment remains unauthorized.

## Active changeset: pointer-persisted-regression-boundaries

Boundary verified clean/synchronized at
`bdc3938069884c22e7f52edaf48eb32ccef1848a`; diff-check passes. The prior
visual-fixture context and its operational closure are committed and pushed.
This context initially owned existing flows.spec.ts and this workstream;
the causal source-repair extension and exact final ownership are recorded below.
At that boundary the full replay had finished flows.spec.ts; keep its later modules unchanged and
do not start a second browser against its fixture. Its full result remains
bound to the original b011b0e test source, not the upcoming stronger assertions.

Trace establishes that a successful map response is insufficient: a workspace
save may still reconcile older persisted source configuration and remount the
component. Require a successful real snapshot response containing watchlist:7
before selecting and publishing. If the source is actually lost, that stronger
assertion must fail; do not reselect/retry the publication action or mock saves.
Also preserve PTR1 as a regression in the existing template flow: wait for a
real populated RSP percentage, ordinarily open/close Plots while RSP remains,
then remove and restore the same saved comparison. The initial test-only
approach exposed the source defect recorded below. No reference/tolerance
change, force/trial click, browser sleep or relaxed timeout is permitted.

The original b011 full replay is now terminal RED: 255 passed, 2 skipped,
3 failed in35.2m. One functional Market Map persistence failure and two
popup-close teardown failures (1080p100/1440p100); every pixel comparison
passed. Full artifacts preserved intact at
`/tmp/chart-pointer-repair-evidence-20261015/b011-complete-red-results`.
The first strengthened two-case validation ran five repetitions each with zero
retries (process87188), using the same pinned isolated browser/font/proxy setup.
The first Docker launch was sandbox-denied before start; the normal narrow
elevated retry launched successfully. No sibling resource was touched.

The stronger source-persistence assertion is RED on repeated execution: it
does not conceal an actual lost update. Inspection shows saveSnapshot ignores
an accepted older-generation response entirely, leaving its server revision
unacknowledged. A subsequent save uses that obsolete revision and invokes
conflict reconciliation/remount, which can drop the new map's configuration.
The existing unit test protects newer field values but never checks the next
base_revision, so its fake server accepted a request the real server rejects.

This same causal validation context now explicitly owns workspace.ts and its
existing unit spec as well as flows.spec.ts and own ops. The human's recorded
instruction to handle validated technical fixes needed for all four branches
without per-fix signoff authorizes this narrowly necessary save-path repair;
it does not authorize unrelated feature scope, cross-worktree writes, waived
conflict safeguards or product checkpoint acceptance. First demonstrate the
missing revision assertion fails, then preserve the acknowledged revision and
baseline without replacing newer local fields or another selected workspace.
Keep the stronger browser persistence assertion. This is a real source repair,
not a claim that adding a wait cured the product defect. Full validation and
exact CI must be rerun on the resulting source before review/integration.

The original ten-case repeated browser check finished 6 passed/4 failed in5.4m:
all five populated pointer/template repetitions pass; four Market Map source
persistence repetitions fail. Artifacts are preserved at
`/tmp/chart-pointer-repair-evidence-20261015/persistence-assertion-before-source-fix`.
The unit regression proves the next base_revision was4 instead of acknowledged5.
Initial acknowledgement correction passes all73 store tests and type/build.
A further unit regression now proves a second part of the same race: when the
350ms timer joins a pending older-generation save, comparing against the
waiter's generation drops the trailing write. Track the generation of the
actual in-flight save, not the later waiter. Its unit currently fails with
one PUT instead of two. Keep both red proofs; no passing complete profile.
An initial frontend image was built from the acknowledgement-only source but
has not replaced the running container. Rebuild after the trailing-save repair
and verify the served bundle before the next browser proof. The in-progress
full unit run loaded the earlier73-test store module; do not claim it covers
the subsequently added74th regression or the upcoming final source correction.

Final focused result: both source corrections pass all74 workspace-store tests,
and the final complete frontend suite passes927/927 across108 files in119.13s.
The two new failure proofs fail before their respective source correction:
base_revision4 instead of5, and one PUT instead of the required trailing second
PUT. The first unit command's conflicting worker bounds were a pre-execution
runner error; explicitly setting both min/max workers to1 corrected that setup.
Negative tests retain switched-workspace identity, an already newer revision,
and edits made during a real conflict retry. Existing genuine conflict/recovery
tests pass unchanged. Final Docker build runs vue-tsc and Vite successfully;
force-recreated only this repair's frontend and verified served
`index-C0soaeCM.js` (not the earlier acknowledgement-only image).
Repeated final browser proof passes10/10 in1.9m, zero retries, against that fresh
seeded app: five populated1920x1080 pointer/template cases and five successfully
persisted Market Map → Study Lab source handoffs. Every original assertion and
critical browser diagnostic remains. No provider request or sibling write.

Current reviewed paths are frontend/src/stores/workspace.ts,
frontend/tests/unit/stores/test_workspace_store.test.ts,
frontend/tests/e2e/flows.spec.ts and only this workstream's four records:
ops/workstreams/fix-chart-template-pointer-interaction/plan.yaml,
ops/workstreams/fix-chart-template-pointer-interaction/handoff.md,
ops/workstreams/fix-chart-template-pointer-interaction/session.json,
ops/workstreams/fix-chart-template-pointer-interaction/validation.jsonl.
Publish this coherent causal save-path context before another implementation
context. Then synchronize its operational closure; only after the clean matching
boundary may the existing visual popup-close teardown test be corrected.
No complete final-source browser profile, exact CI, closure or integration is
claimed yet. The six own services/four disposable volumes remain for that run.

## Published changeset: pointer-visual-state-fixture

Boundary: clean matching HEAD/origin67abfc8752d5c0f7297d044dcec3d9afadc2df0f;
diff-check passed. Cache-aware transform context owns flows.spec.ts + own ops,
was staged/reviewed, committed, pushed and focused-tested3/3 without retries.
It is complete as a changeset, not product acceptance. The next permitted
action is this existing-visual-fixture repair, owning only
frontend/tests/e2e/tc2000_visual.spec.ts and this workstream.

Independently viewed the existing sandbox-error1080 reference: its adjacent
chart explicitly says Loading SPY, header is Unavailable/Refreshing and the
Persisted runs panel is loading. The old test never holds those reads, so a
fast seeded backend can render a different background. TC's already validated
fixture repair demonstrates holding exactly those existing gap-state reads.
Implement only equivalent loading fixtures and explicit state assertions here,
preserving the image, screenshot tolerance, original failure/recovery checks
and all product code. For structured-result, wait for the newly opened Study
workspace's real chart and empty persisted-results state, plus rendered result
canvases, before the original screenshot. Its old readiness wait only covered
the preceding US Top Down layout. The exact staging gate's103pass+1flaky visual
receipt confirms this is a real pre-existing gate problem, not acceptance.

Some earlier journal `at` values were manually rounded labels rather than
captured command-end times (the18:48 focused-reset row was written before
the18:46:30 session progress receipt). Treat command transcripts, durations,
commit/source and CI timestamps as authoritative; no future execution is
claimed by those manual labels. This correction preserves the append-only log.

Focused validation of both visual fixture repairs now passes8/8 across all
four protected profiles in1.0m with retries disabled. No application source,
image reference, mask, tolerance or original assertion was removed/changed.
Own workstream validation and diff-check pass. Publish this independently
reviewed context, then run the entire260case matrix on the resulting clean
source. The original failures and interrupted runs remain non-acceptance.

Visual-fixture context closure: scoped staged review contained only the existing
visual spec and this workstream. Commit `b011b0e458d2e512719328f3ec2aee8715ad1db1`
is pushed; clean HEAD and origin matched at 19:08 UTC and diff-check passed.
Focused evidence is 8/8, zero retries, unchanged screenshots and tolerance.
The complete isolated 260-case replay remains active (process 8142), but is
already RED: F8s-market-map-watchlist again loses the selected-member action.
Its retained trace shows a real workspace snapshot 409/reconciliation remount
after tile selection, not just the preceding map refresh. The earlier focused
pass does not establish full stability. Keep the run intact for its remaining
functional and visual evidence. No full-profile or integration acceptance.
Next permitted action after this operational closure is a read-only diagnosis
of the exact persistence/remount race; do not weaken the selected-source
handoff assertion or silently expand into workspace persistence product code.
The Help policy approval remains queued for the TC owner and does not authorize
Help edits in this repair. Official V25 parity remains unfinished roadmap work.

## Published changeset: pointer-transform-reset-observer

Boundary verified clean/synchronized at543a7817a9bd24a8543066dd96c9472b45e98cd8.
Prior Market Map synchronization context (flows.spec.ts + own ops) is committed,
pushed and focused-behavior validated: the unchanged original handoff assertions
and both untouched1080Study screenshots passed3/3 in49.3s with an isolated
browser namespace, secure localhost proxy and read-only UbuntuDejaVu fonts.
The child test process completed successfully; its first fixture proxy retained
keep-alive handles and was stopped explicitly, then shutdown was corrected.
No full integration pass or acceptance follows from this focused result.

The full no-retry replay then found a separate F9c-transform observer defect;
it was stopped explicitly as RED/incomplete after preserving its trace at
`/tmp/chart-pointer-repair-evidence-20261015/final-isolated-transform-failure`.
Trace requests prove initial point_figure with brick_size12 is fetched,5/2
overrides are fetched, and resetting legitimately reuses that first response.
The final persisted primary-chart configuration already omits box_size/reversal.
The production dedupe coordinator retains completed responses for5000ms; no
network request is required for that valid cache hit. This context owns only
flows.spec.ts and this workstream: retain the UI reset, observe its successful
saved configuration, reload to empty the client cache, then retain the exact
parameter-free transformed-request assertion and verify restored fields/chart.
No production cache change, forced request, weakened assertion or longer timeout.
Focused validation now passes3/3 in33.8s with retries disabled; the corrected
fixture launcher exits0 and removes its own browser container. Workstream and
diff checks pass. Reviewed staging owns only flows.spec.ts and own workstream;
publish this context before the next independent validation repair. Full profile
is still open; no red/interrupted run is relabelled green.

Further evidence: rawNoble falls back toWenQuanYi monospace; host usesDejaVu.
Supplying host DejaVu font files read-only preserves Noble's sans rendering and
made both old visual mismatches pass without reference/source changes. The
normal host attempt passed all Market Map product assertions but strict browser
diagnostics failed ERR_NETWORK_CHANGED; the isolated proxy removes host network
churn from Chromium's namespace. All artifacts retained under the evidence root.
The earlier staging5267f11a job badge was success, but direct terminal-log audit
found103visual passes +1flaky structured-result1080 screenshot (16142pixels)
which recovered on retry. This is not clean non-flaky product acceptance.
Do not conceal or count any red/interrupted/flaky run as a passing full profile.

## Published changeset: pointer-validation-harness-reconciliation

Context boundary: clean matching HEAD/origin
`8b4e68538f2e0cc476434e0767b97f6d1954e808`; diff-check passed. The geometry
changeset owns WorkstationToolContent.vue and this workstream, was reviewed,
committed and pushed, with 923 units, build and focused application checks
passing. It is published, not integration-ready: full regression below is red.
Next permitted action is the required regression-test synchronization repair,
not another product feature. This context owns frontend/tests/e2e/flows.spec.ts
and this workstream; all application source stays fixed.

Full pinned run84402 completed its functional portion with one observed failure,
F8s-market-map-watchlist at flows.spec.ts:3500: the ordinary Study Lab handoff
button became invisible/detached. Evidence is copied intact to
`/tmp/chart-pointer-repair-evidence-20261015/market-map-full-run-failure`.
The screenshot has no comparison; the new conditional geometry is inactive.
TC's existing durable history describes the same detached-button failure and
refresh-completion synchronization repair at product157f41c. Read-only review
of its current test confirms request-count, terminal-refresh and selected-state
assertions before publication. Port only that synchronization idea using this
baseline's existing roles/classes; do not import TC product/UI/role changes.
Retain all original source-lineage, explicit-ID, browser diagnostics and
ordinary-click assertions. No increased timeout, forced action, skip or oracle
change is allowed. The current worker has advanced to the unchanged
tc2000_visual.spec.ts matrix; changing the finished functional spec does not
change that active module or the served application. Original run remains red;
after visual completion replay the focused case and complete final functional
suite on the new committed source before closure.

Synthetic long-label stress also passed ordinary controls at desktop/390px with
two long labels, extreme percentage strings and Plots12345. Fixture/evidence:
`/tmp/chart-pointer-diagnostic/stress.html` and its output/playwright directory.
This supplements, not replaces, real application evidence; no market data was
fabricated in the application. Own stress browser/server15993 closed. Own6.174GB
generated builder cache was removed after builds; own seeded stack is retained
only until this validation concludes. Original TC6services/4volumes were
independently enumerated and remain intact.

## Published changeset: pointer-toolbar-geometry

Boundary verified clean and synchronized at `58075cefa5b90338f3ca95d78151ca7761a47751`.
This context owns WorkstationToolContent.vue and this workstream. Implement
conditional comparison-aware geometry, preserving no-comparison and narrow
positions; use the isolated seeded application for before/after ordinary clicks.
Planning context is closed and published. No sibling stacks or Help references
are owned here.

Source checkpoint: the six-line conditional geometry patch passes all 923
frontend tests (108 files), type checking and production build. The baseline
bundle `index-DOowz8qP.js` reproduced ordinary populated Remove RSP timeout
(Plots intercepts). Rebuilt/force-recreated only this project's frontend;
`index-5WPCnrNS.js` now gives all five toolbar controls independent center hits.
Desktop ordinary Plots/close/removal and saved-template restore pass with RSP
+23.50%; two populated comparisons also pass. Removing all comparisons restores
the exact baseline Plots rectangle. At 390x800 TC Classic the chart is on-screen
(367px wide), all five centers own their targets, ordinary Plots/close/removal
and template restore pass; the plot menu is x45..345 within the viewport.
Post-reload browser console: zero errors/warnings; backend tail: successful
local API calls, existing missing-Alpaca-key skip warning, no traceback.
Evidence moved intact to `/tmp/chart-pointer-repair-evidence-20261015` after
closing only this diagnostic browser. The six own services/four generated
volumes remain for the full regression run. Source checkpoint commit/push
precedes exact-source full regression; long-label stress review, full profile,
CI, cleanup and delegated technical closure are still required. Not accepted.

The human has now approved the reviewed local-only Help reference policy;
authorization was delivered to the existing TC owner. Help changes remain
outside this repair's owned paths, and official V25 parity stays roadmap debt.

## Completed planning context

Owns this workstream only. Existing source is bootstrap commit
`936074d3679b0b76687dd0d39231417c56eecda6`, clean and pushed before preflight.
Writer claim: `4f5ba990-9325-4502-b830-8f1c5ea4572b`; preflight found no owned
containers or volumes. Start from exact green staging `5267f11a`, run
`38773602828`; all required jobs passed before worktree creation.

TC's populated +23.50% real-app cross-check at source `389069a3` shows the
desktop Plots center hitting Remove RSP; its ordinary Plots click times out.
Remove RSP itself passes. The 390x800 TC Classic on-screen 365px chart passes
both ordinary clicks and menu open/close. The full receipt is published in TC
HEAD `6051b078` / evidence commit `13ecdb22`; do not modify that source.

Coordinator-only Chromium diagnostic `/tmp/chart-pointer-diagnostic` confirms
the earlier layering proposal can merely reverse which control is blocked.
A separated right-hand Plots slot with comparisons present makes all controls
independently clickable at desktop and narrow widths in that diagnostic. This
is a candidate, not application acceptance. Preserve the default left150px
Plots placement when no comparison exists and the existing narrow two-row
behavior. Reproduce and validate on this worktree's actual seeded application.

Do not update Help snapshots, import TC/ETF/Provider code, spend provider quota,
delete test accounts or touch other feature stacks. The single TC test account
reported in its retained DB is not this repair's cleanup target. The Help-only
interim reference-policy implementation remains a separate TC-owned issue.

Planning closure: the committed planning receipt was synchronized, the guarded
`plan-ready` check passed, and the already-created session-local goal was recorded
active. The helper initially rejected the receipt's missing `command` field;
that field was corrected in its own committed planning receipt. No product code
was edited during planning. This checkpoint owns only the workstream metadata;
publish its session state, verify clean matching HEAD/origin, then open the
product-geometry context. Use only assigned resources and preserve exact
before/after evidence. The session-local goal uses the concise plan goal without
a token budget; the helper's expanded goal request is guidance, not a replacement.
