# fix/workflow-hardening

Created from `master` at `aecea059fa39ee43fdae36ad935c401a6b5a607e`.

Implemented the runtime stale-allocation proof, corrected the worktree merge-base
closure guard, and implemented `integrate.py --continue` for paused semantic
conflict candidates. The ratio row-action path now remounts Golden Layout after
the snapshot response replaces the canonical workspace, keeping the visible
ratio in step with the persisted `=XLK/SPY` configuration. Focused runtime tests
pass 2/2; the deterministic F8e.2/F8e.2a browser pair passes; Ruff,
formatting, and diff-check pass. Remaining gap: semantic conflict edits still
require explicit agent review and staging before continuation.

The backend GitHub job now strips uv's path-dependent generated header before
comparing the compatibility export, and invokes pytest through `uv run` after the
frozen environment is installed. The first replay then exposed a second workflow
defect: the integration-only job applied the repository-wide coverage threshold
and failed after 369 passing tests at 47.78%. It now explicitly uses
`--cov-fail-under=0`, matching the Makefile; the branch replay and full candidate
gate must still be rerun.

The replay then exposed an Actions cleanup-only failure from setup-python's
unused `cache: pip` configuration after uv had installed dependencies. That cache
configuration is removed; uv remains the sole dependency cache.

Integration now requires a completed successful push-triggered GitHub replay for
the exact source SHA before validation can publish, and for the published master
SHA after push. A failed master replay records `.ai/master-degraded.json`, which
blocks later integration until the replay is repaired and a successful publish
clears the marker.

The first exact detached candidate reached the full browser gate but failed after
37/260 Playwright tests when the frontend proxy became unreachable at its
allocated port (`ECONNREFUSED 127.0.0.1:18081`), cascading to 119 failures; the
candidate stack was stopped by the exact project-scoped trap and its clean
worktree was removed. The source now adds an nginx frontend healthcheck so stack
startup waits for the browser proxy, and a fresh GitHub replay plus exact
candidate gate is required before promotion.

The authoritative gate now also builds all three production application images
for `linux/arm64`, inspects their platform metadata, and removes only its
temporary validation tags. The local hardening worktree passed that check at
`12a98620df34`; the source replay and exact candidate must still record it.

The first ARM64-enabled exact candidate failed only in the separate visual
replay command: its four setup probes used the Playwright default `localhost:80`
instead of the allocated candidate `STACK_URL`, producing four `ECONNREFUSED
::1:80` failures and skipping the remaining 100 visual cases. The candidate
stack was healthy throughout. The Make target now exports the runtime file for
that visual command as well; the candidate must be rebuilt and rerun.

The branch workflow also now starts E2E Compose with deterministic instrument and
market-data fixtures. A debounced user-settings watcher is guarded by the access
token so logout cannot issue a post-logout PATCH/401; its focused unit regression
passes alongside the existing frontend suite.

The authoritative gate now also renders the development and RPi Compose files
with explicit contract values and runs the frontend production build after the
type-check/unit coverage stage. The new source replay must verify this expanded
gate before exact integration.

The branch-owned helper scripts have now also been normalized with Ruff format;
the focused runtime tests and script lint/format checks pass at this boundary.

The first seeded provider/RPi replays completed backend and frontend jobs
successfully but exposed five browser failures. The canonical-search failure was
deterministic on Linux because the test used `Meta+A`; it now uses Playwright's
cross-platform `ControlOrMeta+A`. The pop-out, benchmark-family, and performance
failures reproduced as passing in focused runs against the isolated seeded stack
and are retained as full-suite replay evidence rather than hidden with changed
baselines or thresholds. The focused canonical-search, pop-out, benchmark-family,
and performance runs all pass locally after this correction; a fresh replay is
required.

The integration gate now executes the captured source workstream's `branch_tests`
through `scripts/run-branch-tests.py` after the seeded stack and visual checks.
The helper parses only the branch-local list, supports a listing mode for audit,
and returns the first failing command without converting retries into success.
The same gate now asserts exactly one Alembic head before dependency installation
and application suites, so competing migration heads cannot reach the browser or
deployment stages.

The next source replay exposed a long-suite-only `apiResponse.json: Response has
been disposed` failure in the benchmark-family drilldown fixture. The fixture
now returns a complete deterministic response instead of mutating a fetched
response. The drilldown and both workstation performance guards pass together
against the isolated seeded stack (3 tests, 21.1 seconds); no visual baseline,
retry budget, or assertion threshold was changed.

The subsequent full replay reached the benchmark-family matrix and breadth-ratio
tests but exposed the same response-disposal race in two additional route mocks,
then the expected context teardown cascaded into one performance test. All three
remaining `route.fetch()` mutations in these family fixtures are now replaced by
complete deterministic payloads; the focused drilldown, matrix, breadth-ratio,
and performance scenarios must pass in the next full replay.

Replay `32326840415` confirmed the response-disposal fixes: 149/149 executed
browser tests passed outside two remaining long-suite races. The family matrix
occasionally asserted before the rendered Market Map summary exposed its locked
source, and the repeated popup soak observed five canvases during asynchronous
teardown instead of the three-canvas baseline. The assertions now wait for the
scoped summary and allow a bounded 15-second cleanup window while retaining exact
canvas-count equality. Focused matrix and complete performance runs pass against
the seeded isolated stack; a fresh replay of the new source SHA is required.

Replay `32328718771` passed backend/frontend and 150 browser tests; the only
remaining failure was a popup teardown race where a sibling popup closed before
the test's close click (`Target page, context or browser has been closed`). The
teardown helper now treats an already-closed popup as converged cleanup while
still requiring exactly one context page and the original canvas/tool counts.
The complete performance spec passes locally after this change; another exact
source replay is required.

Replay `32330338005` passed backend/frontend and 150 browser tests but still
failed once in the full-suite benchmark-family matrix. The `sp400` market-map
request returned the correct locked-source payload, while stale `sp500` source
observations and Golden Layout lifecycle churn left the visible map instance
without its rendered summary. The focused matrix remained green, so this was
recorded as a full-suite lifecycle race rather than hidden with a longer retry
or changed oracle. A complete local flow replay also exposed a separate
condition-editor defect: the shared breadth threshold carried a previous
volume-ratio value into `prior_high_low`. Condition changes now seed the
documented default for the new condition; focused matrix and breadth-ratio
checks pass after this correction. A fresh source replay is required.

Replay `32332726711` passed backend/frontend and 147 browser tests, with the
four visual projects executing, but retained two hard failures (popup close
teardown and the benchmark-family matrix) plus two flaky diagnostics. The
matrix trace showed correct `sp1500` API data followed by a revision-conflict
recovery workspace that restored the earlier `sp400` layout. Popup close paths
now share the bounded already-closed helper. Snapshot reconciliation records
explicit local closes and preserves them when a stale remote snapshot still
contains the closed tool; unaccounted removals still create recovery copies.
The new store regression passes, the full frontend suite is 108 files/920
tests, and the complete seeded local flow replay is 148 passed/5 skipped. A
fresh source replay is required before exact integration.

Source replay `32335614592` is green at `abca0c1f88d7fcfacbabdd7ea776dc6753b8bd7a`.
Backend dependency/export, unit, and integration jobs passed; frontend Vitest
passed; and the full Playwright job completed successfully after running all
four visual projects. This independently validates the popup lifecycle and
explicit-close workspace reconciliation fixes without changing visual
baselines, masks, retry budgets, or assertion thresholds. The branch is clean
and synchronized and is ready for exact-SHA candidate integration.

The first explicit candidate run also passed the complete backend coverage,
frontend unit/contract, seeded 260-test browser, 104-case visual, and ARM64
image gates. Its branch-declared E2E commands initially failed because the
workstream listed Playwright invocations without changing into `frontend`;
the commands now use the repository-root-safe `cd frontend &&` form and must
be included in the next exact source replay.

The corrected branch-declared suite now passes directly: the runtime unit and
Ruff checks are green, the ratio-editor pair is 2/2, and the benchmark-family
matrix/breadth pair is 2/2. The first correction used an over-escaped YAML
regex; the workstream now uses single-quoted YAML commands with one escaped
dot, and this exact source boundary requires one more independent replay.

Replay `32340786778` retained the first-failure evidence for the exact
`b3df2edee060b7fe20ab5ff06f145eef685745ce` source: backend and frontend unit
jobs passed, 149 browser tests passed, all four visual projects executed, and
the two retried failures were the full-suite benchmark-family summary race and
multi-window canvas cleanup (received five canvases instead of the exact three).
The focused branch-declared matrix and performance checks remain green; the
failure is recorded as a diagnostic red replay and requires a fresh source
replay before integration.

Replay `32345906663` for `c82231731725fad96f5b3017fcb0870bb27a0f82` passed the
backend and frontend jobs and executed all four visual projects, but the browser
job remained red after 17 minutes. Its preserved first failures were the same
full-suite Market Map lifecycle race (the correct family request completed but
the visible map lost its rendered summary/tile), the popup soak retaining five
canvases instead of the exact three baseline, and a workspace-menu `End` event
that left the reset action unfocused. The focused reproductions were green; the
red evidence is retained and no browser oracle, visual baseline, retry budget,
or threshold was changed.

The next source boundary added the workspace-menu product guard: root-targeted
Home/End events are handled during capture while the nested saved-workspace
listbox keeps its own roving-focus semantics. An attempted Market Map duplicate
in-flight request fence was also evaluated, but it did not address the
full-suite lifecycle race and is not retained. The three focused regressions
passed together against the seeded stack; independent replay `32348730473`
covered that earlier boundary.

Replay `32351389163` for `73d03682298ce246d5c5bbe8f4caf9e7646daeaa` passed the
backend and frontend jobs but the exhaustive browser job remained red after
17m36s. Its preserved first failures were the full-suite F8s family matrix
losing the rendered `Locked source` summary after the correct family response,
and F8s Market Map watchlist timing out on a button that detached during the
Golden Layout lifecycle churn. The focused reproductions remained green. The
duplicate in-flight request fence did not resolve the full-suite race and is
being reverted; no browser oracle, baseline, retry budget, or threshold is being
relaxed. The same source boundary also fixed a real integration-gate shell
scope defect: frontend build/visual commands now run in subshells so later root
Make targets remain available. The next boundary will retain that Makefile fix
while investigating workspace layout installation/reconciliation as the likely
cause of the remaining lifecycle race.

The current source boundary defers destructive Golden Layout reinstalls to the
next macrotask while retaining the latest serializable layout and active-window
pair. This lets a tool action finish before adding or publishing a destination
tool tears down the old virtual component. Frontend type-check passes, the
family matrix passes three consecutive focused runs (8.8s, 8.6s, 8.7s), and the
Market Map watchlist flow reaches its final assertion without the former
detached-control timeout; its local unseeded stack reports only the known
unseeded ETF snapshot 404. A fresh independent source replay is required.

Replay `32354479150` did not reach browser execution: the new deferred host
contract initially failed its two existing synchronous Vitest assertions (the
host intentionally waits one macrotask before a destructive reinstall). Those
tests now await the documented timer boundary; the focused WorkspaceLayoutHost
unit contract passes 8/8. The replay is retained as red first-failure evidence,
and a fresh source replay is required.

The local seeded acceptance stack was rebuilt from the current source boundary.
F8h simultaneous pop-outs and F8s-family-matrix both pass together (2/2 in
13.8s), including the exact popup-page count and locked-source summary/tile
assertions. The unseeded-stack diagnostic classifier also now treats the
documented ETF constituent snapshot 404 as an expected unavailable-data path;
it does not alter the assertions or retry policy. Fresh independent CI replay
remains the required final source evidence.

The follow-up lifecycle hardening fences callbacks by Golden Layout generation and
workstation-tab identity, rejects state/activation callbacks while a deferred
replacement is pending, and hides the old dock during tab replacement. This
prevents a destroyed layout from writing its previous tree into the selected
Market Map tab and prevents stale drawing-tool instances from remaining visible
during a tab switch. The focused seeded matrix passed 5/5 and the drawing
instance-scope test passed 5/5; the WorkspaceLayoutHost contract now passes 9/9,
frontend type-check passes, and the branch is pushed at `a421ebc7`. A fresh
independent GitHub replay for this exact SHA remains required before candidate
integration.

Replay `32362915161` passed frontend/backend jobs but retained three exhaustive
browser failures: the full-suite family matrix could lose the mounted Market Map
summary, a breadth percentile edit could be overwritten back to the default
252-window, and popup churn could transiently retain five canvases instead of the
exact three baseline. The report is preserved under
`/private/tmp/ci-32362915161-report`; no visual oracle, threshold, or retry policy
was changed. The follow-up hardening cancels asynchronous Market Map work after
unmount and preserves local breadth-editor drafts until canonical props catch up.
The seeded family/breadth sequence passed 10/10 and repeated popup churn passed
10/10 locally after rebuilding the isolated stack; fresh CI replay for the new
boundary is required.

Replay `32366018869` for `3874eaf9` passed backend and frontend jobs but the
exhaustive browser job remained red after 18m06s. Its preserved first failures
were a transient F8s family-matrix loss of the rendered summary, an F8j popup
close race after the popup page had already closed, and workstation-performance
starting from a workspace snapshot with missing persisted factory tools (and
therefore no Float control). The report is preserved under
`/private/tmp/ci-32366018869-report`; no visual oracle, threshold, retry policy,
or assertion was relaxed. The full serialized local `flows.spec.ts` replay
against the rebuilt seeded stack then completed with 151 passed and 2 skipped
of 153 tests in 7m, so the missing-tool state has not reproduced locally and
fresh CI evidence remains required before integration.

Replay `32370618720` for `f647539e` passed the independent backend and frontend
jobs and executed the full browser matrix, but retained two exhaustive browser
failures. The F8s family matrix lost its mounted Market Map after the final
family close/reopen cycle: the persisted remote snapshot had removed the old
map while the local newer generation had reopened a new map, and the merge
helper treated the shared deletion as an unresolved conflict, replacing the
local reopen with the remote deletion. The workstation-performance retry
started with five canvases instead of the expected three; trace inspection
showed the additional ratio and relative-rotation uPlot canvases were legitimate
hidden factory tools whose asynchronous loads completed after the baseline,
not leaked pop-outs. The report and traces are preserved under
`/private/tmp/ci-32370618720-report` and `/private/tmp/ci-32370618720.log`.

The follow-up fixes preserve a local reopen when both writers removed the same
base window, while still producing a recovery copy for a remote-only deletion;
the new store regression and combined workspace/ratio unit run pass 81/81.
RatioUPlot now exposes an explicit `aria-busy` readiness state, and the exact
canvas baseline waits for hidden ratio/rotation tools to finish loading without
changing the count oracle. Focused seeded acceptance passes the performance
churn test 5/5 and the family matrix 3/3; frontend type-check and diff-check
are green. A fresh source replay for the resulting commit is required.
