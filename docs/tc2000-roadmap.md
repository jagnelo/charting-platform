# TC2000 Frontend Rework Roadmap

Status: active implementation roadmap  
Branch: `feat/tc2000-frontend-rework`  
Parent: `staging`  
Last reconciled: 2026-10-05

## 2026-10-05 — Exact-tip functional and visual rerun

At pushed workstream tip `4b88a90600420a37a3e62cc01d0c065e389affcd`, with
product source `be55d1af2de8037671d65e33d5b1d5120e11f38c` and the keyboard-flow
test change from `8448c45286b2202800e6079bc30a1a02e5999936`, the full serial
authenticated Chromium suite completed all `179` cases: `173` passed, `6`
documented skips, and zero failures (`16.9m`). The first full run at this tip
had `171` passes and two transient failures (`F9g-series-shape` local
`ERR_NETWORK_CHANGED`; `F8w` Gauge refresh control not visible). Both passed an
unchanged focused replay, then the clean-stack full rerun passed; preserve the
first result without treating the retry as a replacement for that history.

The correctly enabled pinned four-project board matrix completed all `104`
cases: `94` passed and the ten protected screenshot comparisons below failed
after their state assertions passed. The prior full matrix's additional
transport diagnostic did not recur.

| Pinned project | Workspace floating | Study structured result | Study sandbox error |
| --- | ---: | ---: | ---: |
| `visual-1080p-100` | 8,995 | 109,320 | 13,360 |
| `visual-1080p-125` | 9,825 | 105,698 | 11,188 |
| `visual-1440p-100` | 8,995 | 22,099 | Passed |
| `visual-1440p-125` | 9,825 | 21,352 | Passed |

No reference, mask, threshold, skip, or acceptance policy changed. Functional
artifacts are under `/tmp/tc2000-full-functional-clean-rerun.HJ76xu`; the
first-run failures and focused replay are preserved under
`/tmp/tc2000-full-functional-exact-tip.xsyIA9` and
`/tmp/tc2000-full-functional-failure-replay.o5iFBL`; the valid visual matrix
is under `/tmp/tc2000-exact-tip-visual-board.0tfCo1`. Scoped teardown and the
follow-up resource audit left zero assigned TC resources.

Current read-only refs are TC `4b88a90600420a37a3e62cc01d0c065e389affcd`,
staging `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`, provider platform
`88132e9145a08d1c935a0111b3dba0fbd88bdff1`, and ETF holdings
`8105d9695fa4f265e1069b18b5dec439b16dadc4`. Provider and ETF remain outside
staging. Continue independent TC-owned UI/Study/Strategy work; preserve the ten
visual gaps and defer consumer integration until both upstream branches reach
staging.

## 2026-10-05 — Pinned exact-tip validation reconciliation

At product source `be55d1af2de8037671d65e33d5b1d5120e11f38c`, the complete
authenticated Playwright 1.62.1 functional run in the pinned Noble image passed
172/174 with two documented skips and zero failures. The complete four-project
visual matrix ran all 104 cases: 93 passed, ten known screenshot differences
remain, and one watchlist-column-editor diagnostic failed during a local
`ERR_NETWORK_CHANGED` burst. The unchanged focused replay passed 4/4 across
viewport projects, but the full visual result remains 93/104.

The ten visual differences remain confined to workspace-floating in all four
viewports, Study structured-result in all four, and Study sandbox-error at both
1080p scales. The separate pinned shell smoke passed 4/4. Host-only rendering
differs on glyph pixels while geometry aligns; host Arial resolves to Nimbus
Sans while the pinned Noble image resolves to Liberation Sans. Treat that as an
environment/font diagnostic, not product-visual acceptance. No screenshot
reference, mask, threshold, skip, fallback, or acceptance rule changed. Exact
artifacts are recorded in the workstream handoff and under
`/tmp/tc2000-pinned-functional-full-9Iq2rG`,
`/tmp/tc2000-pinned-visual-full-3t8qbk`, and the two shell-smoke directories.

The exact assigned Docker stack and generated images were removed; scoped
resource accounting returned zero TC resources. Continue independent
TC-owned UI/Study/Strategy work. Consumer integration and shared-path
reconciliation stay deferred until both provider-platform and ETF tips reach
staging; the ten visual differences remain open.

## 2026-10-05 — Keyboard invocation for Boolean pin menu and exact-tip results

Product commit `be55d1af2de8037671d65e33d5b1d5120e11f38c` extends the V25
Boolean-header pin menu with `Shift+F10` and Context Menu key invocation while
preserving right-click and Ctrl/Meta-click. The focused VirtualWatchlistTool
suite passed `80/80`; full serial frontend Vitest passed `129` files / `1,202`
tests; the Docker production build passed; and authenticated F8u-boolean passed
`1/1`.

The exact-tip authenticated functional run completed `174` cases: `171` passed,
`2` documented skips, and one F8s-family-matrix diagnostic failure caused by
local API `ERR_NETWORK_CHANGED` requests after application assertions. Its
unchanged focused replay passed `1/1`, but that does not replace the full result.
The previous completed visual matrix was `93/104`, with ten protected
screenshot diffs and one transient setup failure. A current-tip full visual
attempt was stopped after broad deltas; a fresh seeded-database shell smoke
still differed in all four viewport projects. Preserve these results without
changing visual oracles, masks, thresholds, skips, or acceptance rules. The
product commit is pushed and remote-verified at the exact source SHA. The
assigned stack cleanup left zero attributable resources.

Staging remains `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`; provider is
`88132e9145a08d1c935a0111b3dba0fbd88bdff1`; ETF is
`08fad92dc4ee936b41b2b09db3b663fa4d8bf1c5`. Both dependencies remain outside
staging, so R2/R3 integration stays deferred. Continue independent TC-owned
work; the exhaustive local helper still has the Docker Buildx `--name` mismatch.

## 2026-10-05 — Boolean watchlist-column pin interaction

The V25 pinning reference shows Boolean/tag results pinned to the top while
sorting numeric columns, with header right-click or Ctrl-click as direct
gestures. Product commit `3958886632af62e0207fb02ed6961b16fd1a600c` adds the
Boolean-header context action, Ctrl/Meta-click toggle, pinned marker, and
accessible pinned-state announcement while preserving the existing sort state
and persisted pin configuration. The authenticated `F8u-boolean` flow now
verifies pin/unpin without altering sorting. A Golden Layout detached-root bug
was fixed by reading pin state from the canonical live workspace configuration.

Focused watchlist coverage passed `79/79`; the complete serial frontend
coverage suite passed `129/129` files and `1,201/1,201` tests at `85.13%`
statement coverage. The 100k range-band performance test keeps its original
1-second limit and `199,999` segment assertion; its harness now uses lightweight
counting stubs instead of recording 500,000 Vitest mock calls. Type-check and
production build passed, and the rebuilt pinned Chromium `F8u-boolean` flow
passed `1/1` with no critical browser diagnostics. The initial browser attempt
exposed the detached-root state bug; the unchanged flow passed after the fix.

No visual baselines, masks, thresholds, skips, or acceptance policies changed.
The last complete visual matrix remains `94/104` at the prior product source,
with the same ten screenshot-only differences; a current-tip visual rerun is
still required. The latest complete functional matrix likewise predates this
slice (`172` passed, `107` documented skips, three `ERR_NETWORK_CHANGED`
failures), so refresh it at current tip. Both parallel provider/ETF tips remain
outside `staging`; do not consume or reconcile them yet.

## 2026-10-05 — Aggregate gate and browser evidence refreshed

The serial aggregate run passed workstream/dependency/migration, lint/format,
backend and frontend validation, type-check/build, and Compose contract stages.
The earlier backend exit `152` did not recur: backend unit/integration suites
passed `1,621/1,621` and `409/409` with `82.26%` combined coverage; frontend
coverage passed `129` files / `1,200` tests. `make validate-integration` then
stopped at stack-up because its helper requires Docker Buildx and the host CLI
rejects `docker buildx create --name ...` with `unknown flag: --name`. Ordinary
Compose built and started the assigned six-service stack successfully, all
services became healthy, runner sandbox/resource probes passed, and scoped
cleanup left zero assigned resources.

The pinned Playwright 1.62.1 functional run completed `282` cases: `172`
passed, `107` documented skips, and three local-stack requests failed with
`ERR_NETWORK_CHANGED`. A focused `11/11` retry, including all three failures,
passed. The previous full run on the same application and test source was
`175` passed, `107` skipped, zero failed; keep the newer full-run result open
until a clean full rerun confirms it. The pinned visual matrix remains `94/104`
with the same ten screenshot-only differences after state assertions. No visual
oracle or policy changed.

Direct GitHub refs at this checkpoint: TC `49028b70c593bd5d81e7694c4f6cc3bde4e3cd23`,
staging `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`, provider platform
`88132e9145a08d1c935a0111b3dba0fbd88bdff1`, and ETF holdings
`529fc81f60fcbf5f14a7afc7e9aa62461a48e855`. Neither dependency tip is in
staging, so R2/R3 integration and shared-path reconciliation remain deferred.
Continue only TC-owned UI/Study/Strategy work meanwhile.

## 2026-10-04 — Clean pinned full browser rerun

The full seeded Playwright 1.62.1 run completed all `282` cases in `17.5m`:
`175` passed, `107` documented skips, and zero failures. The functional
profile intentionally skips the board's visual cases; those remain governed by
the separate exact-tip visual matrix below, which still has ten screenshot-only
differences. The three transient cases from the earlier full run all passed in
this clean full rerun. The exact assigned Compose project was removed with its
fixture volumes, network, containers, and locally generated images. Artifacts
are retained under `/tmp/tc2000-pinned-e2e.NIbQR4`.

## 2026-10-04 — Exact-tip pinned visual matrix at `049267c`

At pushed branch tip `049267cee5301f2e33c8857305c48f2f3fd77521` (product
source `05aac7f816aab492c7b2aadb1adb9ffc6e76f02a`), pinned Playwright 1.62.1
completed all `104` visual cases in `11.7m`: `94` passed and `10` screenshot
comparisons failed after their state and interaction assertions passed. The
same ten cases remain open: workspace-floating in all viewports (8,995 / 9,825
/ 8,995 / 9,825 pixels), Study structured-result in all viewports (109,320 /
105,698 / 22,035 / 21,352 pixels), and Study sandbox-error at 1080p/100 and
1080p/125 (13,360 / 11,188 pixels). Both 1440p sandbox-error cases passed.
No visual oracle or policy changed.

The earlier host-rendered `8/104` result is diagnostic-only and repeats the
known host-versus-pinned font/rendering drift; it is not acceptance evidence.
The assigned Compose project was removed with its six containers, four test
volumes, network, and four generated images. GitHub refs refreshed to staging
`8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`, provider platform
`88132e9145a08d1c935a0111b3dba0fbd88bdff1`, and ETF holdings
`ea477adee73ec27c865b79e2da1476e4348e47a7`; both dependency tips remain
outside staging. Keep integration deferred and continue distinct TC-owned
work.

## 2026-10-04 — Chart Plot Library search browser proof

An authenticated Chromium flow now verifies that the Chart Plot Library opens
with its search field focused, filters the catalog by the full indicator name,
and exposes no-match feedback through a status role. The new
`F9e-plot-library-search` flow passed `1/1`; the existing Chart Plot Library
component suite passed `45/45`. The full frontend coverage suite passed
`129/129` files and `1,200/1,200` tests, and `vue-tsc` type-check plus the Vite
production build passed.

A separate local-browser review captured the open dialog with the filtered RSI
option expanded (`/tmp/tc2000-chart-open-rsi-dropdown.png`). This is a screenshot
of the current TC implementation, not V25 visual authority. The local reference
board has no exact open/search capture for this panel, so screenshot parity stays
an explicit open gap; no reference, mask, threshold, skip, or visual-acceptance
rule changed. The assigned stack, fixture volumes, and generated images were
removed after the browser check. No provider-platform or ETF-owned behavior
changed.

## 2026-10-04 — Pinned exact-source visual matrix at c038aaf

At product source `c038aafc6fe8378cdf11d4b76006100488c75556` (the current
branch tip at the time was operational checkpoint
`0dc73b5b402c28f2762ac9fe487106bafe29dfa5`), the full serial visual matrix
was rerun in `mcr.microsoft.com/playwright:v1.62.1-noble`. It completed all
`104` cases in `11.9m`: `94` passed and the same ten protected local-reference
differences remained after their state and interaction assertions passed.
Workspace-floating differed by `8,995/9,825/8,995/9,825` pixels; Study
structured-result by `109,320/105,698/22,099/21,352`; Study sandbox-error by
`13,360/11,188` at 1080p/100 and 1080p/125, with both 1440p cases passing.

An initial host-rendered diagnostic produced only `8/104` passes and broad
shell/menu/freshness screenshot diffs. Repository history records the same
host-font rendering failure mode (98/104 host-rendered versus 94/104 in the
pinned browser image); that run is not an acceptance result. The pinned rerun
confirms the current source preserves the previously documented ten visual
review items. No screenshots, masks, thresholds, skips, fallbacks, or
acceptance policy changed.

The assigned Compose stack was stopped and its scoped cleanup removed six
containers, four fixture volumes, its network, and four generated images.
Resource accounting reported zero remaining containers, volumes, images,
test sessions, or unknown components. Current remote refs are staging
`8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`, provider platform
`88132e9145a08d1c935a0111b3dba0fbd88bdff1`, and ETF holdings
`f78b37999419dd5e957b6082491d9122519416e8`. Neither dependency tip is an
ancestor of staging, so consumer integration remains deferred. Continue a
distinct TC-owned UI/Study/Strategy task without expanding provider or ETF
ownership.

## 2026-10-04 — Exact-tip browser gate at a78812d

The full serial functional browser suite passed at pushed product tip
`a78812d33f6402b329c947b70765f2a84e5be9ac`: `171` passed, `110`
documented skips, and no failures. The full pinned Playwright 1.62.1 visual
matrix then completed all `104` cases across the four viewport projects:
`94` passed and `10` failed only at screenshot comparison after state and
interaction assertions passed.

The ten unchanged local-reference differences are workspace-floating in all
four projects (`8,995/9,825/8,995/9,825` pixels), Study structured-result in
all four (`109,320/105,698/22,099/21,352`), and Study sandbox-error at the
two 1080p scales (`13,360/11,188`; both 1440p cases pass). The visual
threshold remains 0.5%; no reference, mask, threshold, skip, fallback, or
acceptance rule changed. These board-guided local screenshots are not exact
V25 authority and remain review items.

The assigned TC2000 stack was cleaned with the scoped resource helper. The
post-cleanup audit reports zero containers, volumes, images, test sessions, or
unknown components. Current remote refs are staging
`8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`, provider platform
`88132e9145a08d1c935a0111b3dba0fbd88bdff1`, and ETF holdings
`48512cd934759c8a52e9b4071c281ef763a08699`. Neither dependency tip is an
ancestor of staging, so consumer integration and shared-path reconciliation
remain deferred. Continue a distinct TC-owned UI/Study/Strategy task without
expanding into provider or ETF ownership.

## 2026-10-04 — Earlier focused visual replay and fixture disposition

The focused pinned Playwright 1.62.1 replay at test SHA
`d8553e5d93419d6f2315ff587d13b4d0e8145c9b` (product source
`74fc6061c6f0a567d4212b29405ed14be9b71195`) ran 12 cases. All state
assertions passed. Workspace-floating differed from the local screenshots by
`8,995/9,825/8,995/9,825` pixels; current images show five seeded rows while
the saved images are empty. Study structured-result differed by
`109,320/105,944/22,035/21,352` pixels; current output cards and promotion
actions are absent from those saved images. These are local-reference
discrepancies, not authoritative V25 captures.

The test-only matcher fix in `d8553e5d` restores the Study sandbox-error
loading precondition after R5 pagination began requesting 26 rows. All four
cases now reach screenshot checks: 1080p/100 and 1080p/125 differ by 13,300
and 11,188 pixels, while both 1440p cases pass. The current schema example
shows lookback `20` while the saved 1080p images show `2`; this does not
establish the cause of every differing pixel. Overall, ten of these 12 focused
screenshot assertions differ and two pass. No product styling, snapshot, mask,
threshold, skip, fallback, or acceptance rule changed. This is not a rerun of
the full 104-case matrix; provider/ETF integration and the exact-tip gate
remain pending.

## 2026-10-04 — Research Results older-run pagination

Product commit `74fc6061c6f0a567d4212b29405ed14be9b71195` adds bounded,
authenticated keyset pagination to TC-owned Research Results. `/research/runs`
now returns `created_at`, orders by `(created_at DESC, id DESC)`, and accepts
the paired `(before_created_at, before_id)` cursor while retaining the current
user filter. The UI requests 26 to display 25 plus a lookahead, appends older
pages, and exposes accessible loading, retry, and missing-cursor states. It
preserves selected-run and comparison state across page fetches and refreshes.

Focused ResearchResultsTool tests passed `54/54`; the full frontend suite
passed `128/128` files and `1,195/1,195` tests; type-check and production build
passed. The focused API test passed `1/1` (30 deselected), covering stable
same-timestamp ID ordering, a newly inserted run above the cursor, and partial
cursor rejection. Ruff, TC ownership validation (124 touched paths plus six
self-tests), and workstream validation passed. Authenticated pinned Chromium
verified the first 25 rows, the exact cursor request, retry after an injected
503, 50 unique merged rows, and preservation of the selected run and active
comparison. Browser fixture data was mocked only for `GET /research/runs`; the
branch stack handled authentication and other application calls. Its assigned
Compose/browser/Testcontainer resources were removed and audited to zero.

This closes one R5 slice, not the broader TC2000 rework. It changes no provider
or ETF ownership, visual references, screenshots, masks, thresholds, skips, or
acceptance policy. The existing ten screenshot-only differences still need a
fresh exact-source reproduction and root-cause disposition; upstream consumer
integration and the final exact-tip gate remain pending.

## 2026-10-04 — Current exact-source visual matrix remains at 94/104

At clean branch tip `58975ea6bee3e506f64d97506aadf4026c626357` (product source
`defefaaafde1db3fc302dc50be923d06ccf84ea0`), the full pinned Playwright 1.62.1
four-viewport visual matrix passed `94/104`. Its ten screenshot-only failures
are the same documented differences: workspace-floating in all four projects,
Study structured-result in all four, and Study sandbox-error at both 1080p
scales. State/interaction checks passed before each screenshot assertion; the
prior Study-running capture race passed in all four projects. Teardown and
resource audit returned zero retained branch resources. Acceptance flexibility
used: board-guided local regression screenshots for represented states, not
exact V25 approval. No screenshot, mask, threshold, skip, or acceptance policy
changed. Provider and ETF dependency tips remain outside staging, so consumer
integration is still deferred.

## 2026-10-04 — Study output comparisons disclose observation dates

Product commit `defefaaafde1db3fc302dc50be923d06ccf84ea0` shows the latest
observation date beside the latest value for each compared series and range
center, with singular/plural observation counts. When the two outputs end on
different dates, the UI keeps the Changed status but withholds a numeric delta;
aligned comparisons and scalar deltas remain available. Focused
ResearchResultsTool coverage passed `52/52`; the full frontend suite passed
`128/128` files and `1,193/1,193` tests; type-check and production build passed.
The authenticated pinned Chromium browser flow passed `1/1`, verifying dates
for mismatched series and range outputs and preserving the scalar `+2` result.
Two expected 404s came from ETF/market-data lookups against the intentionally
empty local fixture; no browser errors occurred. Scope validation accepted 122
branch-touched paths and all six ownership self-tests passed. The assigned
stack and temporary browser container were removed with zero retained
resources. This is a focused TC-owned Study-results improvement, not completion
of the broader Study/Strategy matrix or final exact-tip gate. No upstream
provider/ETF behavior, screenshot reference, mask, threshold, skip, or
acceptance policy changed.

## 2026-10-04 — Study output comparison shows numeric change

Product commit `0543be24b833bad385f855aca6586f343c5b56a6` adds signed numeric
change summaries to persisted Study output comparisons: scalar values compare
later run minus earlier run; series and range-center summaries appear only when
the latest dates align. Different dates, malformed/non-finite values, and
unsupported artifact shapes remain without a numeric delta. Focused Research
Results coverage passed `52/52`, the full frontend suite passed `1,193/1,193`,
type-check and production build passed, and authenticated pinned Chromium
`F8t-results` passed `1/1`. This is one focused R5 improvement; it does not
close the broader Study/Strategy compatibility matrix, upstream staging
dependencies, protected screenshot review, or final exact-tip gate. No visual
baseline or acceptance policy changed.

## 2026-10-03 — Study sandbox-error state replay confirms a local snapshot mismatch

At exact branch test SHA `7066a6d7b72a2b26edf23c5c9abb9141d26e67ae`, the
pinned Playwright 1.62.1 browser replayed the two 1080p Study sandbox-error
cases. Their interaction/state assertions passed, but the local screenshot
checks differed by 13,300 pixels at 1080p/100 and 11,188 at 1080p/125. The
current render shows a parameter-schema lookback default of `20`, while these
two stored images show `2`. This is a local fixture/snapshot disagreement, not
an exact V25 reference; keep the snapshots and 0.5% threshold unchanged pending
the required review. The assigned TC stack was torn down and resource
accounting returned zero containers, volumes, images, or sessions.

## 2026-10-03 — Indicator settings keyboard access is covered

Test commit `695d79557f94581bf3dfed7b2b394496a8b59955` now checks that the
indicator-settings dialog wraps Tab and Shift+Tab at its boundaries, and that
Escape closes it and restores focus to the chart plot library. The focused
ChartPlotLibrary suite passed `44/44`; full coverage passed `128/128` files and
`1,182/1,182` tests, and the TC scope guard passed all 118 touched paths. This
adds accessibility evidence without changing product code, screenshots, or
acceptance policy. The prior product-tip type-check and build remain current.

## 2026-10-03 — Browser checks exercise the actual chart controls

The earlier F8 smoke check looked for an H1 button and skipped its assertions
when no matching element existed, even though the rebuilt `/chart` route uses
the workstation's `Linked timeframe` dropdown. F8 now selects H1 through that
control and checks that the chart status also switches to H1. F9 no longer
silently skips when a broadly matched toolbar is absent: it opens the Lines
menu, chooses Trend Line, and verifies the active state.

At exact test SHA `9343a9e34a7f925c12e16c2f36892f7256774256`, the focused
authenticated Chromium run passed `2/2`. The host lacks Docker Buildx, so the
assigned branch stack was built and started using ordinary Compose; teardown
removed its containers, four volumes, network, and four generated images. The
resource audit then reported zero containers, volumes, sessions, or unknown
components. The TC scope guard passed all 118 touched paths. No visual baseline,
provider/ETF behavior, or acceptance policy changed.

## 2026-10-03 — Indicator settings honor quarter-pixel line widths

Product commit `e4aab57c343d1ded1c9b3d7d8538b6c44d076e59` aligns the primary
chart's indicator-settings dialog with the plot list: line widths round to
quarter-pixel steps and clamp to `0.25–5`; clearing the field restores its last
valid value. Invalid widths are exposed with `aria-invalid` and cannot be
applied.

At this exact source tip, the focused ChartPlotLibrary suite passed `43/43`, the
full coverage-enabled frontend suite passed `128/128` files and `1,181/1,181`
tests, type-check and production build passed, and the TC scope guard passed all
118 touched paths. One initial full-suite run exceeded the existing 100,000-
point rendering timing check by 32 ms; the isolated retry completed in 985 ms,
and the subsequent complete suite passed. The timing threshold was not changed.
The existing Workstation bundle-size warning remains. No visual oracle,
provider/ETF behavior, or acceptance policy changed.

## 2026-10-03 — Study execution validates the current source

Product commit `57035ba3fd29ecb8610e97de1c40f0e56325a110` binds the primary
workstation Study Lab's Run action to the exact Python source most recently
validated. Editing code now marks the earlier result stale, announces that the
current source must be validated again, and disables Run; the action handler
repeats the guard. Validation responses are recorded against the submitted
source, so a response arriving after a further edit cannot enable the newer
code accidentally.

At clean exact tip `bca2cd5cb5f0b40f99c7f0135ae979a2dee417dd`, the full frontend
coverage suite passed `128/128` files and `1,179/1,179` tests, and frontend
type-check plus production build passed. The focused authenticated Chromium
flow `F8t-source-freshness` passed `1/1` against the assigned branch stack,
including stale-source blocking and successful revalidation. Its API calls for
validation, asset creation, and run creation were stubbed so this receipt proves
the browser interaction, not Python execution. No screenshot oracle or provider
or ETF behavior changed. The ordinary Compose fallback was used because this
host lacks Docker Buildx; cleanup found zero branch test resources.

Test-only commit `1fef32d748ec04bdeadbbb96ef13cc267163904a` adds coverage for a
validation response that arrives after another source edit. At that exact tip,
the full frontend suite passed `128/128` files and `1,180/1,180` tests, with
StudyLabTool at `44/44`; type-check and production build also passed. The
browser flow above remains the latest real-browser receipt because this
follow-up changed only unit tests, not the product component or E2E spec.

## 2026-10-03 — Chart plot line-width constraints

Product commit `1ebfe964820265c661a553b73269112d1d0fe622` makes the primary
Chart Plot Library enforce its displayed line-width contract: values are
rounded to quarter-pixel steps and constrained to `0.25–5`, while clearing the
field leaves the current width unchanged. The full frontend coverage suite
passed `128/128` files and `1,178/1,178` tests at the clean commit; `vue-tsc`,
the production build, and the 118-path TC scope guard also passed. The existing
large Workstation bundle warning is unchanged. This is a TC-owned chart
presentation fix and does not alter visual baselines or data-engine behavior.

## 2026-10-03 — Primary chart indicator discovery

Product commit `6f7559f378f12b9ed4ffc9a0510eb51958b73ba0` makes the primary
`/chart` Chart Plot Library's technical-indicator picker searchable by type,
short name, or full catalog description. Keyboard entry focuses the filter
first, no-match feedback is announced, and adding an item still uses the
existing persisted indicator path. The change stays in TC-owned frontend
behavior; it does not duplicate indicator-engine rules or touch provider/ETF
ownership.

At that clean commit, the full frontend coverage suite passed `128/128` files
and `1,177/1,177` tests; `vue-tsc`, production build, scope guard, and the
authenticated `F9e-plot-library-keyboard` browser flow passed. The four-project
pinned visual board recorded `91/104` passes and `13` failures. Ten were the
previously observed protected screenshot differences: floating workspaces in
four viewports, structured Study results in four, and Study sandbox errors at
both 1080p scales. Three additional anomalies (unavailable freshness at
1080p/100, keyboard-help readiness at 1440p/100 after `ERR_NETWORK_CHANGED`,
and Study running at 1440p/125) each passed when replayed individually. No
reference, mask, threshold, skip, or acceptance rule changed. Exact screenshot
coverage for the Chart Plot Library's open/search state is still missing from
the checked-in 104-case board; its current evidence is functional keyboard
coverage only. The assigned Docker stack was removed and resource accounting
reported zero remaining worktree resources.

## 2026-10-03 — Earlier pinned visual matrix at `1b5e2c7`

At clean product SHA `1b5e2c7e6e877c086cc355f68e7841204432c119`, the board-guided
104-case matrix completed in the pinned Playwright 1.62.1 browser image: `94`
passed and `10` failed. This supersedes the earlier broad host-browser result;
the default shell, workspace menus, drag targets, freshness states, and other
screens passed in the matching rendering environment. All ten failures were
screenshot assertions after their state/interaction assertions passed:
`workspace-floating` in all four viewports (the test captures the five hydrated
seeded rows while the saved reference is empty), `study-lab-structured-result`
in all four viewports (current structured outputs include promotion controls
not shown in the saved references), and `study-lab-sandbox-error` at the two
1080p scales. The 0.5% limit and all screenshot references remain unchanged;
these intentional-state differences need visual review before any reference
update. No provider or ETF code was changed. Their current tips are still not
ancestors of staging, so R2/R3 integration remains deferred while R1/R5 work
continues.

## 2026-10-03 — Earlier broad host-rendered matrix (superseded)

The earlier board-guided 104-case matrix at clean SHA
`fe8aaee56e035c7be52cfc887670cd29aedfc277` completed across four viewport
projects with 98 failures and 6 passes. Sampled screenshot deltas include the
default benchmark shell, workspace menu/drag states, freshness gaps, and Study
Lab running/structured-result states. Later full replays in the matching
Playwright 1.62.1 image showed the broad shell/menu/freshness failures came
from host font rendering. See the latest picker checkpoint above for the
current exact result, and the earlier pinned run below it for the ten
repeatable state-specific screenshot differences. No screenshot oracle was
changed.

The Study Lab running-state test also used an outdated accessible name for its
Cancel control. Commit `88a8452c6f1c2c5ace45f7f13892dd7f36a777dc` corrects only
that selector. A focused diagnostic then passed the running-status and button
assertions but still failed the saved screenshot by 16,052 pixels / 1% versus
the existing 0.5% threshold. This was run pre-commit against identical source
contents and is not a clean exact-SHA gate. No product behavior or visual
acceptance policy changed. Continue independent R1/R5 work and diagnose these
deltas; provider/ETF integration remains deferred until both tips reach
staging.

## 2026-10-02 — Current workstation interaction receipts

The primary workstation now shows a visible focus ring on keyboard-selected
workspace tabs (`44b837a2`) without replacing the active-tab marker. The Chart
plot library (`a5af29f5`) and Chart Templates (`7e927a1f`) are each exposed as
named dialogs rather than menus because their panels contain form controls.
Component tests cover keyboard entry, Escape focus recovery, and trigger
semantics; the E2E flows now query the dialog role, and authenticated Firefox
browser checks verified both panels.
ChartTemplateControl passed `15/15` focused tests; the exact-tip serial
frontend suite passed `128/128` files and `1,168/1,168` tests; type-check and
production build passed with the existing large Workstation bundle warning.
The branch-local Compose stack was healthy and then cleaned to zero owned
resources. These are focused R1/R6 interaction receipts only: all six
protected visual diffs remain under the existing human-review policy, and
provider/ETF consumers remain deferred until their branch tips reach staging.
No visual oracle or upstream behavior changed.

## 2026-10-02 — Native Indicator Panel selection controls

Product commit `e48ef32d61cab0a37608ce5dbf605543ea73ff3b` converts the five
TC-owned Indicator Panel selection rows—radar detections, indicators, drawings,
price alerts, and indicator alerts—to native buttons. The selected state is
announced and keyboard focus is visible; row menus and drag handles remain
separate controls. Focused unit coverage passed `2/2`, the full serial frontend
suite passed `128/128` files and `1,168/1,168` tests, type-check and production
build passed, and authenticated Chromium `F8e.native-indicator-selection`
passed `1/1` on `/legacy/chart/SPY` for Enter/Space selection and independent
row actions. The ordinary Buildx-enabled stack target is unavailable on this
host, so the TC project was built and run with ordinary Compose, then removed
and audited to zero resources.

This closes only the existing single-chart `IndicatorPanel` interaction. It
does not claim parity for the primary `/chart` workstation's Technicals tool,
and it does not close the six protected visual differences, the upstream
staging boundary, or the overall frontend rework. No visual baseline or
acceptance policy changed.

## 2026-10-02 — R6 visual-state diagnosis and resilience receipts

At product/test tip `e52009bf9`, a version-matched Playwright 1.62.1 replay
passed two of the eight targeted editor/floating screenshots. The remaining
six now have a concrete state explanation: the 1080p editor images predate the
visible all-family readiness line; the floating snapshots show no rows while
the current browser test intentionally waits for five seeded rows. The
unmodified 104-case visual policy still requires human review before any
baseline update. The controlled 10,000-row network budget check passed `1/1`
in `20.2s`, and the 100-cycle, two-popout endurance check passed `1/1` in
`4.3m`. See the TC workstream handoff and validation ledger for exact results.

## 2026-10-02 — Market Map spatial keyboard navigation

Product commit `4a4b06e5d6dabfff4c75c1e2d70912f58ba2270e` gives Market Map
treemap tiles arrow-key focus to the nearest tile in the requested direction.
Navigation prevents page scrolling but does not change selection; Enter, Space,
and click retain the native button activation path.
Focused MarketMapTool coverage passed `55/55`; full serial frontend Vitest
passed `128/128` files and `1,168/1,168` tests; `vue-tsc`, production build,
`git diff --check`, TC scope self-tests, and workstream validation passed. The
production build reports only the existing large-chunk warning. No browser
replay, provider-platform, ETF, visual baseline, threshold, mask, skip,
fallback, or acceptance policy changed. The six protected visual mismatches
and upstream staging boundary remain open; this is not an exact-tip integration
or four-project visual-gate pass.

## 2026-10-02 — Market Map keyboard-focus visibility

Product commit `db0783e24567cd89b87c51567c7c4444674db98f` adds a white inset
focus ring to keyboard-focused Market Map tiles, distinct from the gold ring
used for selected tiles. The focused `F8s-family-map-drilldown` Chromium test
passed `1/1`, including keyboard focus, visible focus styling, and click
selection. The focused MarketMapTool suite passed `55/55`; the exact-tip serial
frontend suite passed `128/128` files and `1,168/1,168` tests; type-check and
production build passed with the existing large-chunk warning. No screenshot
baseline or visual acceptance rule changed.

The longer `F8s-market-map-watchlist` flow was rerun on branch tip
`157f41c1272ce9ed8d56e8677273c8377cd878bb` and passed `1/1`, including the
watchlist selection and Study Lab handoff. The earlier detached-button result
was resolved by aligning the test with the button's accessible name and waiting
for refresh completion. `make test-stack-up` could not use its configured
Buildx option on this host, so ordinary Compose built and started only the TC
project; the repository cleanup helper then removed its resources and the
follow-up resource audit found zero containers, volumes, or images. The six
protected visual mismatches and upstream staging boundary remain open; this
does not constitute a full browser or visual-gate pass.

## 2026-09-15 - Preserve promoted Python signal lineage in Strategy Lab

Product checkpoint `7c4bd3ba494706b517d496ca63770055b88f9b3e` keeps the
existing TC Study-to-Strategy promotion model intact while making promoted
Python signals explicitly lineage-preserving in Strategy Lab. The signal's
Study Lab code version and output contract are visible and immutable; profile
fields remain editable without rewriting the code snapshot, and version edits
or new rules revisions return a clear conflict. A legacy/mislabeled definition
is also guarded by its `python_*` version snapshot. Python signal runs use the
selected run-only universe and do not publish it as a Strategy revision.

The full frontend coverage suite, type-check, and production build passed; the
branch-stack build repeated the production type-check/build. Focused Strategy
Lab integration tests passed 3/3, including the mislabeled-snapshot regression;
Ruff and format checks passed. Authenticated headless Chromium F8q passed 1/1,
verifying lineage, safe profile PATCH fields, and the run-universe guard.
Workstream validation, the TC scope guard (33 paths and six self-tests), and
diff checks passed. Teardown removed the branch-scoped stack, volumes, network,
and four generated images; resource accounting found zero retained containers,
volumes, test sessions, known bytes, or unknown components. No visual oracle,
provider/ETF behavior, or acceptance policy changed. The six protected visual
diffs and upstream staging boundary remain open; this is not an exact-tip or
four-project visual-gate pass.

## 2026-09-15 - Watchlist context-menu keyboard invocation

Product checkpoint `d20572b150cb0d20596fce66560facc2dd908a0b` opens the
VirtualWatchlist row action menu from Shift+F10 and the dedicated Context Menu
key. The menu is anchored to the focused row; keyboard invocation is stopped
before listbox/global handlers, and the existing first-item focus, arrow
navigation, Escape-close, and row-focus restoration behavior is preserved.
The original right-click path remains covered.

The authenticated headless Chromium F9e-context-keyboard flow passed 1/1,
covering mouse invocation plus Shift+F10, menu navigation, Escape, and focus
recovery. The first new browser assertion reproduced that Shift+F10 did not
open the menu; the row-scoped keyboard handler fixed it. The focused
VirtualWatchlist unit suite passed 73/73 including both Shift+F10 and Context
Menu key paths; full frontend Vitest passed 1,076/1,076; type-check and
production build passed (existing large-chunk warning). TC scope validation
passed for 29 changed paths, its six self-tests passed, workstream validation
and `git diff --check` passed.

The normal stack-up helper hit an orphaned, worktree-named Buildx registration
and safely cleaned up. The isolated stack was then built with a temporary,
unselected builder and brought up under the same TC2000-specific Compose
project; both that builder and stack were removed afterward. Resource
accounting found zero containers, volumes, test sessions, known bytes, or
unknown components. No visual oracles, provider/ETF behavior, or acceptance
policy changed; the exact-tip and four-project visual gates remain open.

## 2026-09-15 - Research Results run-selection and comparison semantics

Product checkpoint `e6d405ecb7ad8a69a32f8ef273b8711fc836a815` separates the
persisted Study Results row into a semantic list item containing two sibling
controls: a native comparison checkbox and a named native run-selection
button. This removes the former nested interactive controls while keeping
`aria-current` on the selected item. Comparison toggles no longer depend on
row click propagation, and Enter/Space/click select runs through the button.

Research Results plus keyboard-focused component coverage passed 42/42; full
frontend Vitest passed 1,076/1,076; type-check and production build passed
(existing large-chunk warning). Authenticated headless Chromium F8t-results
passed 1/1 on the isolated branch stack, asserting comparison does not change
the selected run and that Enter, Space, and click select persisted runs. The
final run targeted this worktree's `127.0.0.1:28083` stack. An initial
unsandboxed-process attempt was blocked before Chromium launch, and the first
permitted launch used Playwright's default localhost port; the exact isolated
URL then passed. No visible browser or user tab was used. Workstream validation,
scope guard (29 paths), all six scope self-tests, and `git diff --check` passed.
Teardown removed the branch stack, volumes, network, and four generated images;
resource accounting found zero retained containers, volumes, test sessions, or
known bytes.

## 2026-09-15 - Global keyboard shortcuts yield to controls

Product checkpoint `6b579185d2a0be4bc2b00040909c3a5821a848bd` teaches the
workstation-level symbol/F1/type shortcuts to yield when focus is on native or
ARIA interactive controls. This preserves Space activation for workspace tabs
and Study controls rather than traversing to another symbol. Unit coverage
passed as part of the 1,076-test frontend suite; type-check and production
build passed with only the existing large-chunk warning. Headless Chromium
F9e-keyboard and F8k-shift passed 2/2 against the branch-scoped stack.

Neither slice changes visual baselines, masks, thresholds, skips, provider/ETF
behavior, or acceptance policy. The six protected visual mismatches and
provider/ETF staging boundary remain open; these focused receipts are not an
exact-tip integration or four-project visual pass.

## 2026-09-15 - Occurrence keyboard accessibility across workstation views

Product checkpoint `64836d0ae6c69a85c085dbb8830a72924f17f585` extends the
native occurrence-button keyboard behavior from Study Lab and persisted
Research Results to Study Dashboard events and generic breadth-history rows.
Both affected buttons stop keydown propagation so the workstation's Space
symbol-traversal shortcut cannot steal activation; native Enter/Space behavior
and linked-symbol/timestamp handling remain unchanged.

Frontend Vitest passed 1,075/1,075; focused Research Results and direct Study
Dashboard component tests passed 40/40; `vue-tsc --noEmit` and production build
passed (existing large-chunk warning). Authenticated headless Chromium passed
F8t Study Results and F8s breadth-family flows (2/2), including Space activation
from QQQ back to SPY and the selected occurrence timestamp on the linked chart.
The scope guard passed for 27 changed paths, its six self-tests passed, and
workstream validation and `git diff --check` passed. Branch-stack teardown and
resource accounting found zero retained containers, volumes, test sessions,
or known bytes. No visual baseline, mask, threshold, skip, provider/ETF
behavior, or acceptance policy changed. The six protected visual mismatches
and upstream staging boundary remain open; this is not an exact-tip integration
or four-project visual pass.

## 2026-09-15 - Research Results occurrence keyboard accessibility (prior checkpoint)

Product checkpoint `03bd5b103d84fcd8e03b0ce74ec944abfa711a88` gives persisted
Study event and historical-breadth occurrences semantic list-item wrappers
containing named native buttons. The buttons stop the workstation shortcut
handler from consuming Space, so mouse, Enter, and Space activate the same
linked symbol and historical timestamp.

Authenticated headless F8t passed 1/1 against the isolated branch stack,
covering event-artifact Enter and breadth-history Space navigation and linked
chart timestamps. The focused Research Results suite passed 39/39; full
frontend Vitest passed 1,074/1,074; type-check, production build, scope guard
(24 paths), all six scope self-tests, workstream validation, and diff checks
passed. Stack teardown and resource accounting found zero retained containers,
volumes, test sessions, or known bytes. No screenshot baseline, mask,
threshold, skip, provider/ETF behavior, or acceptance policy changed. The six
protected visual mismatches and upstream staging boundary remain open; this is
not an exact-tip integration or four-project visual pass.

## 2026-09-15 - Study Lab occurrence keyboard accessibility

Product checkpoint `27698c9608f89d480f609df2d716e75eaa34a292` keeps each
structured event occurrence inside a semantic list item and exposes the
action as a named native button. The workstation's Space-to-next-symbol
shortcut no longer consumes Space while the occurrence button is focused, so
keyboard activation follows the same linked symbol/timestamp path as a click.

Authenticated headless F8o passed 1/1 with Enter and Space; Study Lab unit
coverage passed 31/31; full frontend Vitest passed 1,074/1,074; frontend
type-check and Docker production build passed. No screenshot baseline, mask,
threshold, skip, provider/ETF behavior, or acceptance policy changed. The
isolated stack was removed with zero retained containers, volumes, sessions,
or known bytes. The six known visual mismatches and upstream staging boundary
remain open; this is not an exact-tip or visual-matrix pass.

## 2026-09-15 - Headless TC workstation and Study Lab browser checkpoint

At product tip d4b288375dac, the branch-scoped Docker frontend was exercised
without opening or taking over an interactive browser. Authenticated headless
Chromium passed F9f chart-template export/import (1/1) and F8g Study Lab
validation, isolated scalar execution, result rendering, and watchlist-column
promotion (1/1). The F8g Playwright trace contains authenticated page captures
outside Git for visual inspection; no generated media was added to the branch.

The unchanged watchlist-column-editor visual assertion was rerun at
visual-1080p-100 and reproduced its known 13,844-pixel (1.0%) difference
against the checked-in board baseline. The screenshot comparison did not reveal
a sufficiently specific product cause for a safe edit, so the baseline,
threshold, masks, skips, and acceptance policy remain unchanged. The exact
named Compose project was stopped and cleaned; resource accounting found zero
containers, volumes, test sessions, or known retained bytes.

Continue independent TC-owned workstation UI and Study/Strategy work. Do not
implement provider or ETF responsibilities in TC; consume those contracts only
after promotion through staging and reconcile shared paths at the final
integration step.

## 2026-09-15 - Historical EA identifier disposition

The QQQ SEC N-PORT filings for 2025-09-30 and 2025-12-31 each retain an
Electronic Arts Inc. equity row with CUSIP 285512109 and ISIN US2855121099,
without a source ticker. The filing accessions are
[0001067839-25-000007](https://www.sec.gov/Archives/edgar/data/1067839/000106783925000007/0001067839-25-000007-index.htm)
and
[0001067839-26-000016](https://www.sec.gov/Archives/edgar/data/1067839/000106783926000016/0001067839-26-000016-index.htm).
OpenFIGI currently maps those identifiers to EA* on MM, which does not satisfy
the configured supported-US-listing guard. EA is not promoted or relabelled as
an active US listing; both source rows remain noncanonical placeholders until
point-in-time listing lifecycle support can represent the historical EA listing.
The SEC 8-K records EA common stock under ticker EA on Nasdaq and the Aug 4,
2026 merger close and delisting request:
[Electronic Arts 8-K](https://www.sec.gov/Archives/edgar/data/712515/000114036126031157/ef20079099_8k.htm).

The resolver now preserves a specific `resolution_note` when a stable-identifier
profile is rejected and no canonical profile is promoted, including on later
reconciliation of an existing placeholder. Focused resolver tests passed 31/31;
Ruff, formatting, and diff checks passed. This explicitly dispositions the two
EA rows without counting them as canonical. The Dreyfus government-cash row is
still unclassified and remains open, as do W1/MN history, rebalance continuity,
and the remaining R1-R7 evidence.

The exact full integration gate at product tip `e93de4af` passed workstream,
dependency, migration, lint, backend coverage (1,619/1,619 unit tests and
405/405 integration tests at 82.23% combined coverage), frontend Vitest
(1,067/1,067), type-check/build, Compose/provider/research-runner checks, and
functional Playwright (165 passed, 107 documented skips). Visual E2E exited 1:
98/104 passed, with the six established protected diffs—watchlist-column-editor
open at 1080p/100% and 125% (13,844 pixels each); workspace-floating at
1080p/100% and 125% (15,817 pixels each) and 1440p/100% and 125% (9,770 pixels
each). The optional branch-tests suffix was not reached. Teardown removed the
four generated images and all stack resources; the resource audit found zero
containers, volumes, test sessions, and known attributable bytes. No baseline,
mask, threshold, skip, provider/fallback behavior, or acceptance policy changed.

The workstream remains active. The Dreyfus row is retained here as historical
evidence, but its classification/parser disposition belongs to
`feat/etf-holdings-constituents` after that branch reaches staging; it is not a
forward TC-owned task under the approved 2026-09-15 scope replan. Continue with
independent TC workstation UI and Study/Strategy work. The optional
branch-tests suffix remains unrun because visual E2E failed.

## 2026-09-15 - Verified Killir GARY dated holdings

Product commit bb70fff142a7f4b247664ce4047f93ac37343523 hardens the
issuer-declared GARY dated SEI text route. Every retained row must have one
parseable date and all rows must share it; missing, invalid, and mixed dates
fail closed, and the row date must match the selected report filename. The live
public route returned 41 rows dated 2026-09-14, with no missing or mismatched
dates.

Focused Killir tests passed 5/5; the complete holdings-adapter module passed
584/584; the opt-in GARY live route test passed 1/1; Ruff, formatting, and diff
checks passed. After authorized Docker access, full integration completed all
pre-visual stages: backend units 1618/1618, integration 405/405 at 82.23%
combined coverage, frontend Vitest 1067/1067, type-check/build, Compose and
research-runner checks, and functional Playwright 165 passed with 107
documented skips. The visual stage exited 1 at 98/104 with exactly the six
established protected watchlist-column-editor-open/workspace-floating diffs.
The optional branch-tests suffix was not reached. Post-run resource audit
found zero containers, volumes, sessions, or known attributable bytes. No
provider/fallback or visual acceptance policy changed. Continue R1 family-wide
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10.

## 2026-09-15 - Verified Kingsview dated holdings

Product commit `b375a4782` hardens Kingsview/Monarch's fund-ID-scoped
FilePoint JSON holdings route. Every retained row must have the same parseable
`asOfDate`; missing, invalid, and mixed-date snapshots fail closed; source IDs
are date-scoped; and raw plus normalized metadata records composition/as-of
date, row count, completeness, and
`kingsview_native_fund_scoped_filepoint_holdings_json` provenance. The public
MVFD route returned 42 rows dated 2026-09-11.

Focused Kingsview assertions passed 3/3, the full holdings-adapter unit module
passed 581/581, the opt-in public route test passed 1/1, and Ruff, formatting,
and diff checks passed. The exact branch gate at product tip `b375a4782` passed
backend units 1615/1615, integration 405/405 at 82.23% combined coverage,
frontend Vitest 1067/1067, type-check/build, Compose and research-runner checks,
and functional E2E 165 passed with 107 documented skips. Visual E2E remains
98/104 with only the six established watchlist-column-editor/workspace-floating
state-oracle diffs. Resource accounting confirmed zero containers, volumes,
test-container sessions, or known attributable bytes; four generated images
were removed. No provider/fallback, visual baseline, mask, threshold, skip, or
acceptance policy changed. Continue R1 family-wide population/history,
D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10.

## 2026-09-15 - Verified Arlington dated holdings

Product commit `654bfe7e5` tightens Arlington's issuer-linked AQEC daily CSV:
all retained rows must share exactly one parseable composition date; missing,
invalid, and mixed dates fail closed; source IDs are date-scoped; and raw plus
normalized metadata records composition/as-of date, row count, completeness,
and `arlington_native_daily_holdings_csv` provenance. The public route probe
passed with the live suite's 20-row minimum and asserted date/route metadata.

The focused Arlington contract passed 2/2, the full holdings-adapter unit
module passed 580/580, the opt-in public route probe passed 1/1, and Ruff,
formatting, and diff checks passed. The exact branch gate at product tip
`654bfe7e5` passed backend units 1614/1614, integration 405/405 at 82.22%
combined coverage, frontend Vitest 1067/1067, type-check/build, Compose and
research-runner checks, and functional E2E 165 passed with 107 documented
skips. Visual E2E remains 98/104 with only the six established
watchlist-column-editor/workspace-floating state-oracle diffs. Docker resource
audit found zero containers, volumes, test-container sessions, or known
attributable bytes; four generated images were removed. No fallback/provider,
visual baseline, mask, threshold, skip, or acceptance policy changed. Continue
R1 family-wide population/history, D1/W1/MN floors, rebalance continuity, and
AC2-AC7/AC10.

## 2026-09-15 - Verified Liberty One dated holdings

Product commit 67a2fd65 hardens Liberty One's native fund-scoped holdings API
route for SPCT. Retained rows require exactly one parseable asOfDate; undated,
invalid, or mixed-date snapshots fail closed; row IDs are date-scoped; and
composition/as-of date, row count, completeness, and
liberty_one_native_fund_scoped_holdings_api provenance are recorded. The direct
public endpoint returned 53 complete rows dated 2026-09-11.

Focused assertions passed 2/2 including missing/invalid/mixed-date regressions;
the opt-in live route assertion passed 1/1; direct probe, Ruff, formatting, and
diff checks passed. The first exact gate attempt failed at the functional stage on F8u-boolean's
final promoted-header visibility assertion (one failed, 164 passed, 107
skipped); its visual matrix was 98/104 with the same six protected diffs.
Without code changes, a complete rerun passed the functional suite
165/165 with 107 skipped; backend unit tests passed 1613/1613, integration
405/405, and frontend Vitest 1067/1067; type-check/build, Compose contracts,
and research-runner probes passed. Visual E2E passed 98/104 with exactly the
same six protected watchlist-column-editor/workspace-floating diffs, so the
gate ended at its visual stage. Docker cleanup verified zero containers,
volumes, or test-container sessions. No provider/fallback, migration, visual
baseline, threshold, mask, skip, or acceptance policy changed. Continue R1
family-wide canonical population/history, D1/W1/MN floors, rebalance
continuity, and AC2-AC7/AC10.

## 2026-09-15 - Verified Archer Investment dated holdings

Product commit `556926982` hardens Archer Investment's product-page-linked
daily CSV route for `ARWG`. Retained rows now require exactly one parseable
snapshot date; undated, invalid, and mixed-date exports fail closed; source IDs
are date-scoped; and complete composition/as-of, row-count, and
`archer_investment_native_daily_holdings_csv` provenance metadata is recorded.
The direct public export published 42 complete rows dated 2026-09-14.

Focused Archer assertions passed 2/2 including missing/invalid/mixed-date
regressions; the escalated opt-in live route assertion passed 1/1; and the direct
public probe returned 42 complete dated rows. Ruff, formatting, and diff checks
passed. The exact branch-scoped Docker-backed gate passed backend units
1612/1612, integration 405/405 with 82.21% combined coverage, frontend Vitest
1067/1067, type-check/build, compose/deployment contracts, research-runner
sandbox/resource probes, and functional E2E 165 passed with 107 skipped. Visual
E2E passed 98/104 with exactly the six unchanged protected
watchlist-column-editor/workspace-floating diffs. Docker teardown removed all
branch-scoped containers, volumes, network, four generated images, and
testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Continue family-wide R1
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10.

## 2026-09-15 - Verified Advent Capital dated holdings

Product commit `e9bb8b476` hardens Advent Capital's issuer-native daily CSV
route for `ACVT`. Retained rows now require exactly one parseable snapshot date;
undated, invalid, and mixed-date exports fail closed; source IDs are
date-scoped; and complete composition/as-of, row-count, and
`advent_capital_native_daily_holdings_csv` provenance metadata is recorded. The
direct public export published 60 complete rows dated 2026-09-14.

Focused Advent Capital assertions passed 2/2 including missing/invalid/mixed-
date regressions; the escalated opt-in live route assertion passed 1/1; and the
direct public probe returned 60 complete dated rows. Ruff, formatting, and diff
checks passed. The exact branch-scoped Docker-backed gate passed backend units
1611/1611, integration 405/405 with 82.20% combined coverage, frontend Vitest
1067/1067, type-check/build, compose/deployment contracts, research-runner
sandbox/resource probes, and functional E2E 165 passed with 107 skipped. Visual
E2E passed 98/104 with exactly the six unchanged protected
watchlist-column-editor/workspace-floating diffs. Docker teardown removed all
branch-scoped containers, volumes, network, four generated images, and
testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Continue family-wide R1
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10.

## 2026-09-15 - Verified ACP Horizon dated holdings

Product commit `7aa159a04` hardens ACP Horizon's issuer-native multi-fund
daily CSV route for HBTA. The adapter now requires exactly one parseable
snapshot date across retained account rows, fails closed for undated, invalid,
or mixed-date exports, date-scopes source IDs, and records complete
composition/as-of, row-count, and
`acp_horizon_native_multi_fund_daily_holdings_csv` provenance metadata. The
direct public HBTA export published 207 complete rows dated 2026-09-14.

Focused ACP Horizon assertions passed 2/2 including missing/invalid/mixed-date
regressions; the escalated opt-in live route assertion passed 1/1; and the
direct public probe returned 207 complete dated rows. Ruff, formatting, and diff
checks passed. The exact branch-scoped Docker-backed gate passed backend units
1610/1610, integration 405/405 with 82.20% combined coverage, frontend Vitest
1067/1067, type-check/build, compose/deployment contracts, research-runner
sandbox/resource probes, and functional E2E 165 passed with 107 skipped. Visual
E2E passed 98/104 with exactly the six unchanged protected
watchlist-column-editor/workspace-floating diffs. Docker teardown removed all
branch-scoped containers, volumes, network, four generated images, and
testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Continue family-wide R1
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10.

## 2026-09-15 - Verified EMLes dated holdings

Product commit `a001e82cd` hardens EMLes's native public fund-page,
fund-scoped CSV route for EOPS and its listed ETF lineup. The adapter now
requires exactly one parseable snapshot date across retained rows, fails closed
for undated, invalid, or mixed-date exports, date-scopes source IDs, and records
complete composition/as-of, row-count, and
`emles_native_fund_scoped_holdings_csv` provenance metadata. The direct public
EOPS export published 1 complete row dated 2022-10-20 (cash-only disclosure).

Focused EMLes assertions passed 2/2 including missing/invalid/mixed-date
regressions; the escalated opt-in live route assertion passed 1/1; and the
direct public probe returned 1 complete dated row. Ruff, formatting, and diff
checks passed. The exact branch-scoped Docker-backed gate passed backend units
1609/1609, integration 405/405 with 82.20% combined coverage, frontend Vitest
1067/1067, type-check/build, compose/deployment contracts, research-runner
sandbox/resource probes, and functional E2E 165 passed with 107 skipped. Visual
E2E passed 98/104 with exactly the six unchanged protected
watchlist-column-editor/workspace-floating diffs. Docker teardown removed all
branch-scoped containers, volumes, network, four generated images, and
testcontainer sessions. A preceding attempt hit a transient PostgreSQL
termination during integration setup and was retried from a clean stack; no
product regression was observed. No provider/fallback, migration, visual
baseline, threshold, mask, skip, or acceptance policy changed. Continue R1
family-wide population/history, D1/W1/MN floors, rebalance continuity, and
AC2-AC7/AC10.

## 2026-09-14 - Verified Optimize dated holdings

Product commit `a9cdd8829` hardens Optimize's native product-page verified
fund-scoped XLS route for OPTZ. The adapter now requires exactly one parseable
holdings-specific composition date (`Data as of ... Holdings are subject to
change`), fails closed for undated, invalid, or ambiguous pages, date-scopes
source IDs, and records complete composition/as-of, row-count, and
`optimize_native_fund_scoped_holdings_xls` provenance metadata. The direct public
holdings export published 339 rows dated 2026-09-14.

Focused Optimize assertions passed 2/2 including invalid/mixed/missing-date
regressions; the escalated opt-in live route assertion passed 1/1; and the
direct public probe returned 339 complete rows dated 2026-09-14. Ruff,
formatting, and diff checks passed. The exact branch-scoped Docker-backed gate
passed backend units 1608/1608, integration 405/405 with 82.19% combined
coverage, frontend Vitest 1067/1067, type-check/build, compose/deployment
contracts, research-runner sandbox/resource probes, and functional E2E 165
passed with 107 skipped. Visual E2E passed 98/104 with exactly the six unchanged
protected watchlist-column-editor/workspace-floating diffs. Docker teardown
removed all branch-scoped containers, volumes, network, four generated images,
and testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Continue family-wide R1
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10.

## 2026-09-14 - Verified Cultivar dated holdings

Product commit `3de6e028b` hardens Cultivar's native fund-page holdings route
for CVAR. The adapter now requires exactly one parseable `Fund Holdings as of`
date, fails closed for undated, invalid, or ambiguous pages, date-scopes source
IDs, and records complete composition/as-of, row-count, and
`cultivar_native_current_fund_page_holdings_table` provenance metadata. The
direct public fund page published 92 rows dated 2026-09-11.

Focused Cultivar parser assertions passed 3/3 including undated, invalid, and
ambiguous-date regressions; the escalated opt-in live route assertion passed
1/1; and the direct public probe returned 92 complete rows dated 2026-09-11.
Ruff, formatting, and diff checks passed. The exact branch-scoped Docker-backed
gate passed backend units 1607/1607, integration 405/405 with 82.18% combined
coverage, frontend Vitest 1067/1067, type-check/build, compose/deployment
contracts, research-runner sandbox/resource probes, and functional E2E 165
passed with 107 skipped. Visual E2E passed 98/104 with exactly the six unchanged
protected watchlist-column-editor/workspace-floating diffs. Docker teardown
removed all branch-scoped containers, volumes, network, four generated images,
and testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Continue family-wide R1
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10.

## 2026-09-14 - Verified Canary dated holdings

Product commit `ef1ca2eed` hardens Canary's native product-page holdings route
for HBR. The adapter now requires exactly one parseable composition date across
all retained rows, fails closed for undated, invalid, or mixed-date snapshots,
date-scopes source IDs, and records complete composition/as-of, row-count, and
`canary_native_product_page_current_holdings_table` provenance metadata. The
direct public product page published 2 rows dated 2026-09-14.

Focused Canary parser assertions passed 1/1 including undated, invalid, and
mixed-date regressions; the escalated opt-in live route assertion passed 1/1;
and the direct public probe returned 2 complete rows dated 2026-09-14. Ruff,
formatting, and diff checks passed. The exact branch-scoped Docker-backed gate
passed backend units 1606/1606, integration 405/405 with 82.18% combined
coverage, frontend Vitest 1067/1067, type-check/build, compose/deployment
contracts, research-runner sandbox/resource probes, and functional E2E 165
passed with 107 skipped. Visual E2E passed 98/104 with exactly the six unchanged
protected watchlist-column-editor/workspace-floating diffs. Docker teardown
removed all branch-scoped containers, volumes, network, four generated images,
and testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Continue family-wide R1
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10.

## 2026-09-14 - Verified Water Island/AltShares dated holdings

Product commit `0d7437b01` hardens the shared Water Island/AltShares native
periodic portfolio-of-investments PDF route for `ARB` and `EVNT`. The adapter
now requires a dated non-empty snapshot, excludes swap, forward, and footnote
sections from the holdings parse, date-scopes source IDs, and records complete
composition/as-of, row-count, and
`water_island_native_periodic_complete_portfolio_report_pdf` provenance metadata.
The reviewed public report published 66 `ARB` rows and 42 `EVNT` rows dated
2026-02-28.

Focused Water Island assertions passed 2/2 including the missing-date and
non-holdings-section regressions; escalated opt-in live route assertions passed
2/2 for the Water Island and AltShares discovery keys; and direct public probes
returned the same complete dated snapshots. Ruff, formatting, and diff checks
passed. The exact branch-scoped Docker-backed gate passed backend units
1606/1606, integration 405/405 with 82.18% combined coverage, frontend Vitest
1067/1067, type-check/build, compose/deployment contracts, research-runner
sandbox/resource probes, and functional E2E 165 passed with 107 skipped. Visual
E2E passed 98/104 with exactly the six unchanged protected
watchlist-column-editor/workspace-floating diffs. Docker teardown removed all
branch-scoped containers, volumes, network, four generated images, and
testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Continue family-wide R1
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10.

## 2026-09-14 - Verified Dhandho dated holdings

Product commit `9ada7cb8e` hardens Pabrai Wagons' native complete-holdings PDF
route for WAGN. The adapter now requires a dated non-empty snapshot, fails
closed when the PDF lacks a parseable composition date or retained rows,
date-scopes source IDs, and records complete composition/as-of, row-count, and
`dhandho_native_complete_holdings_pdf` provenance metadata. The direct public
route published 21 rows dated 2026-03-31.

Focused Dhandho assertions passed 9/9 including the missing-date regression;
the escalated opt-in live route assertion passed 1/1; and the direct public
issuer probe returned 21 complete rows dated 2026-03-31. Ruff, formatting, and
diff checks passed. The exact branch-scoped Docker-backed gate passed backend
units 1606/1606, integration 405/405 with 82.18% combined coverage, frontend
Vitest 1067/1067, type-check/build, compose/deployment contracts,
research-runner sandbox/resource probes, and functional E2E 165 passed with
107 skipped. Visual E2E passed 98/104 with exactly the six unchanged protected
watchlist-column-editor/workspace-floating diffs. Docker teardown removed all
branch-scoped containers, volumes, network, four generated images, and
testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Continue family-wide R1
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10.

## 2026-09-14 - Verified Convergence dated holdings

Product commit `52771a08e` hardens Convergence's issuer page-linked holdings
route for CLSE. The adapter now requires non-empty retained CSV rows with
exactly one parseable `Date`, fails closed for missing, invalid, or mixed-date
snapshots, date-scopes source IDs, and records complete composition/as-of,
row-count, and `convergence_native_product_page_linked_holdings_csv` provenance
metadata. The direct public route published 361 rows dated 2026-09-14.

Focused Convergence assertions passed 8/8 including missing/invalid/mixed-date
regressions; the escalated opt-in live route assertion passed 1/1; and the
direct public issuer probe returned 361 complete rows dated 2026-09-14. Ruff,
formatting, and diff checks passed. The exact branch-scoped Docker-backed gate
passed backend units 1606/1606, integration 405/405 with 82.18% combined
coverage, frontend Vitest 1067/1067, type-check/build, compose/deployment
contracts, research-runner sandbox/resource probes, and functional E2E 165
passed with 107 skipped. Visual E2E passed 98/104 with exactly the six unchanged
protected watchlist-column-editor/workspace-floating diffs. Docker teardown
removed all branch-scoped containers, volumes, network, four generated images,
and testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Continue family-wide R1
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10.

## 2026-09-14 - Verified Corgi dated holdings

Product commit `94f09137e` hardens Corgi Funds' issuer-native public holdings
route for FDRS. The adapter now requires non-empty retained rows with exactly
one parseable `position_date`, fails closed for missing, invalid, or mixed-date
snapshots, date-scopes source IDs, and records complete composition/as-of,
row-count, and `corgi_native_fund_holdings_api` provenance metadata. The direct
public route published 52 rows dated 2026-09-14.

Focused Corgi assertions passed 4/4 including missing/invalid/mixed-date
regressions; the escalated opt-in live route assertion passed 1/1; and the direct
public issuer probe returned 52 complete rows dated 2026-09-14. Ruff, formatting,
and diff checks passed. The exact branch-scoped Docker-backed gate passed
backend units 1603/1603, integration 405/405 with 82.17% combined coverage,
frontend Vitest 1067/1067, type-check/build, compose/deployment contracts,
research-runner sandbox/resource probes, and functional E2E 165 passed with 107
skipped. Visual E2E passed 98/104 with exactly the six unchanged protected
watchlist-column-editor/workspace-floating diffs. Docker teardown removed all
branch-scoped containers, volumes, network, four generated images, and
testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Continue family-wide R1
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10.

## 2026-09-14 - Verified SS&C dated holdings

Product commit `da0334842` hardens the shared Capital Impact adapter for the
EntrepreneurShares and ERShares public SS&C full-holdings API routes. The
adapter now requires non-empty retained rows with exactly one parseable
`asofdate`, fails closed for undated, invalid, or mixed-date payloads,
date-scopes source IDs, and records complete composition/as-of, row-count, and
issuer-specific native SS&C provenance metadata. The reviewed public XOVR route
published 33 rows dated 2026-09-11 for both EntrepreneurShares and ERShares.

Focused SS&C assertions passed 7/7 including undated/mixed-date regressions;
opt-in live public-route assertions passed 3/3; and direct public issuer probes
returned 33 complete rows dated 2026-09-11 for each route. Ruff, formatting, and
diff checks passed. The exact branch-scoped Docker-backed gate passed backend
units 1600/1600, integration 405/405 with 82.17% combined coverage, frontend
Vitest 1067/1067, type-check/build, compose/deployment contracts,
research-runner sandbox/resource probes, and functional E2E 165 passed with
107 skipped. Visual E2E passed 98/104 with exactly the six unchanged protected
watchlist-column-editor/workspace-floating diffs. Docker teardown removed all
branch-scoped containers, volumes, network, four generated images, and
testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Continue family-wide R1
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10.


## 2026-09-14 - Verified Cohen & Steers dated holdings

Product commit `33f759bac` hardens Cohen & Steers' public WordPress fund API
route for CSRE. The adapter now requires non-empty native holdings with exactly
one parseable holding date across every retained row, fails closed for missing,
invalid, or mixed-date payloads, date-scopes source IDs, and records complete
composition/as-of, row-count, and `cohen_steers_native_public_fund_api`
provenance metadata. The direct public issuer API route published 53 rows dated
2026-09-14.

Focused Cohen & Steers assertions passed 4/4 including missing/mixed-date
regressions and mocked fetch metadata; the escalated opt-in live route assertion
passed 1/1; and the direct public issuer probe returned 53 complete rows dated
2026-09-14. Ruff, formatting, and diff checks passed. The exact branch-scoped
Docker-backed gate passed backend units 1598/1598, integration 405/405 with
82.16% combined coverage, frontend Vitest 1067/1067, type-check/build, compose/
deployment contracts, research-runner sandbox/resource probes, and functional
E2E 165 passed with 107 skipped. Visual E2E passed 98/104 with exactly the six
unchanged protected watchlist-column-editor/workspace-floating diffs. Docker
teardown removed all branch-scoped containers, volumes, network, four generated
images, and testcontainer sessions. No provider/fallback, migration, visual
baseline, threshold, mask, skip, or acceptance policy changed. Continue
family-wide R1 population/history, D1/W1/MN floors, rebalance continuity, and
AC2-AC7/AC10.

## 2026-09-14 - Require dated Calvert holdings

Product commit `3c07b4c6` hardens Calvert's official issuer-native daily JSON
route for CVLC. The adapter now requires non-empty holdings with exactly one
parseable effective date, fails closed for undated snapshots, date-scopes source
IDs, and records complete composition/as-of, row-count, and
`calvert_native_issuer_json` provenance metadata. The direct public issuer route
published 756 rows dated 2026-09-11.

Focused Calvert assertions passed 4/4 including the undated-row regression; the
dedicated live route assertions passed 2/2; and the direct public issuer probe
returned 756 dated rows. Ruff, formatting, and diff checks passed. The exact
branch-scoped Docker-backed gate passed backend units 1595/1595, integration
405/405 with 82.14% combined coverage, frontend Vitest 1067/1067, type-check/
build, compose/deployment contracts, research-runner sandbox/resource probes,
and functional E2E 165 passed with 107 skipped. Visual E2E passed 98/104; the
same six protected watchlist-column-editor/workspace-floating diffs remain.
Docker teardown removed all branch-scoped containers, volumes, network, four
generated images, and testcontainer sessions. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, rebalance continuity, and
AC2-AC7/AC10 remain open.

## 2026-09-14 - Require dated Alerian holdings

Product commit `f7f4ed33d` hardens Alerian's issuer-owned ALPS HubSpot proxy
route for AMLP/ENFR. The adapter now requires non-empty rows with exactly one
parseable `asofdate`, fails closed for undated or mixed-date payloads,
date-scopes source IDs, and records complete composition/as-of, row-count, and
`alerian_native_issuer_json` provenance metadata. The reviewed live ENFR route
published 29 rows dated 2026-09-11.

Focused Alerian assertions passed 5/5 including the undated-row regression;
the dedicated and generic live route assertions passed 2/2; and the direct
public proxy probe returned 29 dated rows. Ruff, formatting, and diff checks
passed. The exact branch-scoped Docker-backed gate passed backend units
1594/1594, integration 405/405 with 82.14% combined coverage, frontend Vitest
1067/1067, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E 165 passed with 107 skipped. Visual
E2E passed 98/104; the same six protected watchlist-column-editor/workspace-
floating diffs remain. Docker teardown removed all four generated images,
containers, volumes, network, and testcontainer sessions. No provider/fallback,
migration, visual baseline, threshold, mask, skip, or acceptance policy
changed. Family-wide R1 population/history, D1/W1/MN floors, rebalance
continuity, and AC2-AC7/AC10 remain open.

## 2026-09-14 - Require dated ACSI holdings

Product commit `b067dc884` promotes ACSI Funds' official daily holdings CSV to
an issuer-native route for ACSI. The adapter now requires non-empty rows with
exactly one parseable composition date, fails closed for undated or mixed-date
exports, date-scopes source IDs, and records complete composition/as-of,
row-count, and `issuer_native_acsi_daily_holdings_csv` provenance metadata. The
reviewed live CSV published 33 rows dated 2026-09-14.

Focused ACSI assertions passed 2/2 including the undated-row regression; the
dedicated opt-in live provider assertion passed 1/1; and the direct public CSV
probe returned 33 complete rows dated 2026-09-14. Ruff, formatting, and diff
checks passed. The exact branch-scoped Docker-backed gate passed backend units
1593/1593, integration 405/405 with 82.13% combined coverage, frontend Vitest
1067/1067, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E 165 passed with 107 skipped. Visual
E2E passed 98/104; the same six protected watchlist-column-editor/workspace-
floating diffs remain. Docker teardown removed all four generated images,
containers, volumes, network, and testcontainer sessions. No provider/fallback,
migration, visual baseline, threshold, mask, skip, or acceptance policy
changed. Family-wide R1 population/history, D1/W1/MN floors, rebalance
continuity, and AC2-AC7/AC10 remain open.

## 2026-09-14 - Require dated Oakmark holdings

Product commit `cef626151` promotes Oakmark's official symbol-scoped CSV
holdings exports to the issuer-native route for OAKM/OAKI. The adapter now
requires exactly one published composition date and non-empty rows, fails
closed for undated or ambiguous snapshots, date-scopes source IDs, and records
complete composition/as-of, row-count, and
`issuer_native_oakmark_symbol_holdings_csv` provenance metadata. The reviewed
live OAKM route published 41 rows dated 2026-09-14.

Focused Oakmark assertions passed 2/2 including the undated regression; the
opt-in live provider assertions passed 3/3 and the direct live adapter probe
returned 41 complete rows. Ruff, formatting, and diff checks passed. The exact
branch-scoped Docker-backed gate passed backend units 1592/1592, integration
405/405 with 82.13% combined coverage, frontend Vitest 1067/1067,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E 165 passed with 107 skipped. Visual E2E passed
98/104; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker teardown removed all four generated images, containers,
volumes, network, and testcontainer sessions. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, rebalance continuity, and
AC2-AC7/AC10 remain open.

## 2026-09-14 - Require dated Wellington holdings

Product commit `4e76ab33d` requires Wellington-managed VUSV/VDIG/VUSG's
issuer-native Vanguard publisher route to publish a parseable composition date
before acceptance. Undated or empty publisher results now fail closed; accepted
rows receive date-scoped source IDs and complete native-route metadata, including
composition/as-of dates, row count, and
`issuer_native_vanguard_wellington_managed_etf` provenance. The reviewed live
VUSV route published 86 rows dated 2026-06-30.

Focused Wellington assertions passed 3/3 including the undated regression; the
opt-in live provider assertions passed 2/2 and the direct live adapter probe
returned 86 complete rows. Ruff, formatting, and diff checks passed. The exact
branch-scoped Docker-backed gate passed backend units 1591/1591, integration
405/405 with 82.13% combined coverage, frontend Vitest 1067/1067,
type-check/build, compose/deployment contracts, expected research-runner probes,
and functional E2E 165 passed with 107 skipped. Visual E2E passed 98/104; the
same six protected watchlist-column-editor/workspace-floating diffs remain.
Docker teardown removed all four generated images, containers, volumes, network,
and testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Family-wide R1
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10
remain open.

## 2026-09-14 - Require dated AllianceBernstein holdings

Product commit 851d1f2af requires AllianceBernstein's issuer-native model
workbook route to publish a composition date before acceptance. The shared
AllianceBernstein route used by Equitable now fails closed for undated
workbooks, date-scopes source IDs, and records complete composition/as-of,
row-count, and issuer-native model-workbook provenance metadata. The reviewed
live FWD workbook published 128 rows with composition date 2026-07-31.

Focused AllianceBernstein/Equitable assertions passed 3/3, the opt-in live
AllianceBernstein provider assertion passed 2/2, and the direct live adapter
probe returned 128 complete rows. Ruff, formatting, and diff checks passed.
The exact branch-scoped Docker-backed gate passed backend units 1590/1590,
integration 405/405 with 82.13% combined coverage, frontend Vitest 1067/1067,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E 165 passed with 107 skipped. Visual E2E passed
98/104; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker teardown removed all four generated images, containers,
volumes, network, and testcontainer sessions. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, rebalance continuity, and
AC2-AC7/AC10 remain open.


## 2026-09-14 - Require dated Aptus holdings

Product commit `c481193f4` requires Aptus's issuer-native WordPress holdings
table to publish a composition date before acceptance. Undated pages now fail
closed; accepted rows receive date-scoped source IDs and complete native-route
metadata, including composition/as-of dates, row count, and provenance. The
reviewed current DRSK page published 33 rows with composition date 2026-09-11.

Focused Aptus assertions passed 2/2, including the undated-page regression;
the opt-in live provider assertion passed 1/1, and the direct live adapter
probe returned 33/33 rows with `complete` metadata. Ruff, formatting, and diff
checks passed. The exact branch-scoped Docker-backed gate passed backend units
1589/1589, integration 405/405 with 82.12% combined coverage, frontend Vitest
1067/1067, type-check/build, compose/deployment contracts, expected
research-runner sandbox/resource probes, and functional E2E 165 passed with
107 skipped. Visual E2E passed 98/104; the same six protected
watchlist-column-editor/workspace-floating diffs remain. Docker teardown was
clean: all four generated images, containers, volumes, network, and
testcontainer sessions were removed. No provider/fallback, migration, visual
baseline, threshold, mask, skip, or acceptance policy changed. Family-wide R1
population/history, D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10
remain open.

## 2026-09-14 - Require dated ALPS/SS&C holdings

Product commit f607797cd requires ALPS/SS&C's native holdings JSON routes to
publish a composition date before they are accepted. Undated payloads now fail
closed; accepted rows receive date-scoped source IDs and complete native-route
metadata, including composition/as-of dates, row count, and provenance. The
O'Shares route inherits the same ALPS contract.

Focused ALPS/SS&C and O'Shares assertions passed 3/3, including the undated
payload regression; the reviewed live public probes passed 3/3. Ruff,
formatting, and diff checks passed. The exact branch-scoped Docker-backed gate
passed backend units 1588/1588, integration 405/405 with 82.11% combined
coverage, frontend Vitest 1067/1067, type-check/build, compose/deployment
contracts, expected research-runner probes, and functional E2E 165 passed with
107 skipped. Visual E2E passed 98/104; the same six protected
watchlist-column-editor/workspace-floating diffs remain. Docker teardown was
clean with no retained containers, volumes, networks, testcontainer sessions,
or images. No provider/fallback, migration, visual baseline, threshold, mask,
skip, or acceptance policy changed. Family-wide R1 population/history,
D1/W1/MN floors, rebalance continuity, and AC2-AC7/AC10 remain open.

## 2026-09-14 - Make history backfill skip undated snapshots

Product commit `75a6c7e45` makes benchmark-family snapshot-history backfill fail closed for legacy holdings snapshots without a publisher-declared composition date. Such rows remain available to audit/readiness paths, but are excluded from queue planning and counted as `undated_snapshot_count`; the task response carries that evidence forward so history bounds cannot be fabricated or crash the worker.

Focused benchmark-family history/task assertions passed `34/34`; Ruff, formatting, and diff checks passed. The exact branch-scoped gate passed backend units `1587/1587`, integration `405/405` with `82.10%` combined coverage, frontend Vitest `1067/1067`, type-check/build, compose/deployment contracts, expected research-runner probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed `98/104`; the same six protected watchlist-column-editor/workspace-floating diffs remain. Docker resources were cleaned with no retained containers, volumes, networks, testcontainer sessions, or images. No provider/fallback, migration, visual baseline, threshold, mask, skip, or acceptance policy changed. Family-wide R1 population/history, D1/W1/MN floors, continuity, and AC2-AC7/AC10 remain open.


## 2026-09-14 - Verify Infrastructure Capital dated holdings

Product commit `619bd4826` requires and records Infrastructure Capital's publisher-declared composition date from the official product page before consuming its native XLS holdings workbook. The adapter verifies non-empty native rows, fails closed when the product page is undated, records composition/as-of, source URL, workbook row count, and completeness metadata, and date-scopes row IDs.

Focused Infrastructure Capital unit assertions passed `2/2`; the reviewed live workbook probe passed `1/1`; Ruff, formatting, and diff checks passed. The exact branch-scoped gate passed backend units `1587/1587`, integration `405/405` with `82.10%` combined coverage, frontend Vitest `1067/1067`, type-check/build, compose/deployment contracts, expected research-runner probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed `98/104`; the same six protected watchlist-column-editor/workspace-floating diffs remain. Docker resources were cleaned with no retained containers, volumes, networks, or testcontainer sessions. No provider/fallback, migration, visual baseline, threshold, mask, skip, or acceptance policy changed. Family-wide R1 population/history, D1/W1/MN floors, continuity, and AC2-AC7/AC10 remain open.


## 2026-09-14 - Verify Timothy Plan holdings and cold-navigation tool opens

Product commit 86c4820f1 requires and records Timothy Plan's published holdings snapshot date for its native HTML holdings table. The adapter verifies non-empty native rows, fails closed for undated snapshots, records composition/as-of and row-count metadata, scopes completeness_status: complete to the native route, and date-scopes row IDs. Product commit ad97b1aae also yields once in openTool when a shell click races the workstation's asynchronous mount, preserving the first Add-tool command on a cold /chart navigation.

Focused Timothy Plan assertions passed 12/12; the focused Playwright F8t-results-open regression passed 1/1; Ruff, formatting, diff, type-check, and build checks passed. The corrected exact branch-scoped gate passed backend units 1586/1586, integration 405/405 with 82.10% combined coverage, frontend Vitest 1067/1067, compose/deployment contracts, expected research-runner probes, and functional E2E 165 passed with 107 skipped. Visual E2E passed 98/104; the same six protected watchlist-column-editor/workspace-floating diffs remain. Docker resources were cleaned with no retained containers, volumes, networks, or testcontainer sessions. No provider/fallback, migration, visual baseline, threshold, mask, skip, or acceptance policy changed. Family-wide R1 population/history, D1/W1/MN floors, continuity, and AC2-AC7/AC10 remain open.


## 2026-09-14 — Promote verified Spear holdings completeness

Product commit `045478c6e` requires and records the published composition date
for Spear Funds' fixed issuer holdings CSV route for SPRX. The adapter verifies
non-empty native rows, fails closed for undated snapshots, records
composition/as-of and row-count metadata, scopes `completeness_status:
complete` to the native route, and date-scopes row IDs.

Focused Spear assertions passed `10/10`; Ruff/format/diff checks passed. The
exact branch-scoped gate passed backend units `1585/1585`, integration `405/405`
with `82.10%` combined coverage, frontend Vitest `1067/1067`, type-check/build,
compose/deployment contracts, expected research-runner probes, and functional
E2E `165 passed` with `107 skipped`. Visual E2E passed `98/104`; the same six
protected watchlist-column-editor/workspace-floating diffs remain. Docker
resources were cleaned with no retained containers, volumes, networks, or
testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Family-wide R1
population/history, D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified Allspring holdings completeness

Product commit `1c9ee96ed` requires and records the published composition date
for Allspring's issuer symbol-specific total-holdings CSV route. The adapter
verifies non-empty native rows, fails closed for undated snapshots, records
composition/as-of and row-count metadata, scopes `completeness_status:
complete` to the native route, and date-scopes row IDs.

Focused Allspring assertions passed `8/8`; Ruff/format/diff checks passed. The
exact branch-scoped gate passed backend units `1584/1584`, integration `405/405`
with `82.09%` combined coverage, frontend Vitest `1067/1067`, type-check/build,
compose/deployment contracts, expected research-runner probes, and functional
E2E `165 passed` with `107 skipped`. Visual E2E passed `98/104`; the same six
protected watchlist-column-editor/workspace-floating diffs remain. Docker
resources were cleaned with no retained containers, volumes, networks, or
testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Family-wide R1
population/history, D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified Tremblant holdings completeness

Product commit `27b7b24dc` requires and records the published composition
date for Tremblant TOGA's issuer-page-verified FilePoint holdings CSV. The
adapter verifies non-empty native rows, fails closed for undated snapshots,
records composition/as-of and row-count metadata, scopes
`completeness_status: complete` to the native route, and date-scopes row IDs.

Focused Tremblant assertions passed `6/6`; Ruff/format/diff checks passed. The
exact branch-scoped gate passed backend units `1583/1583`, integration `405/405`
with `82.09%` combined coverage, frontend Vitest `1067/1067`, type-check/build,
compose/deployment contracts, expected research-runner probes, and functional
E2E `165 passed` with `107 skipped`. Visual E2E passed `98/104`; the same six
protected watchlist-column-editor/workspace-floating diffs remain. Docker
resources were cleaned with no retained containers, volumes, networks, or
testcontainer sessions. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Family-wide R1
population/history, D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified FilePoint holdings completeness

Product commit `245ac0a56` requires and records the published composition
date for the FilePoint/LionShares and Twin Oak issuer-native holdings routes.
The adapters verify non-empty native rows, fail closed for undated snapshots,
record composition/as-of and row-count metadata, scope
`completeness_status: complete` to the native routes, and date-scope row IDs.

Focused LionShares/Twin Oak assertions passed `4/4`; Ruff/format/diff checks
passed. The exact branch-scoped gate passed backend units `1582/1582`,
integration `405/405` with `82.09%` combined coverage, frontend Vitest
`1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the same six protected watchlist-column-editor/
workspace-floating diffs remain. Docker resources were cleaned with no
retained containers, volumes, networks, or testcontainer sessions. No
provider/fallback, migration, visual baseline, threshold, mask, skip, or
acceptance policy changed. Family-wide R1 population/history, D1/W1/MN
floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified Cygnet holdings completeness

Product commit `ce2353738` requires and records the published composition date
for Cygnet Capital's ELM issuer-declared full holdings CSV. The adapter
verifies non-empty account-scoped rows, fails closed for undated snapshots,
records composition/as-of metadata, scopes `completeness_status: complete` to
the native route, and date-scopes row IDs.

Focused Cygnet assertions passed `3/3`; Ruff/format/diff checks passed. The
first exact gate had one transient F8u-boolean header-visibility failure; the
isolated reproduction passed `1/1` in 5.1s without code changes. The rerun
exact branch-scoped gate passed backend units `1580/1580`, integration
`405/405` with `82.07%` combined coverage, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned with no retained containers,
volumes, networks, or testcontainer sessions. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified Sterling Capital holdings completeness

Product commit `f8e071903` requires and records the published composition date
for Sterling Capital's issuer-native fund-scoped holdings PDFs, including the
Sterling Fund Management and Guardian publisher wrappers. The shared adapter
verifies non-empty rows, fails closed for undated snapshots, records
composition/as-of metadata, scopes `completeness_status: complete` to the
native route, and date-scopes row IDs.

Focused Sterling Capital, Sterling Fund Management, and Guardian assertions
passed `5/5`; Ruff/format/diff checks passed. The exact branch-scoped gate
passed backend units `1579/1579`, integration `405/405` with `82.07%` combined
coverage, frontend Vitest `1067/1067`, type-check/build, compose/deployment
contracts, expected research-runner probes, and functional E2E `165 passed`
with `107 skipped`. Visual E2E passed `98/104`; the same six protected
watchlist-column-editor/workspace-floating diffs remain. Docker resources were
cleaned with no retained containers, volumes, networks, or testcontainer
sessions. No provider/fallback, migration, visual baseline, threshold, mask,
skip, or acceptance policy changed. Family-wide R1 population/history, D1/W1/
MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified Rareview holdings completeness

Product commit `d227b50ba` requires and records the published composition date
for Rareview's official RDFI databaseInfo holdings payload. The adapter
verifies non-empty issuer-native rows, fails closed for undated snapshots,
records both `composition_date` and `as_of_date`, scopes
`completeness_status: complete` to the native route, and date-scopes row IDs.

Focused Rareview assertions passed `2/2`; Ruff/format/diff checks passed. The
exact branch-scoped gate passed backend units `1578/1578`, integration
`405/405` with `82.07%` combined coverage, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned with no retained containers,
volumes, networks, or testcontainer sessions. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified Miller Value holdings completeness

Product commit `3e6dc61c4` requires and records the published composition date
for Miller Value's official MVPA/MVPL Nuxt holdings payloads. The adapter
verifies non-empty issuer-native rows, fails closed for undated pages, records
both `composition_date` and `as_of_date`, scopes `completeness_status: complete`
to the native route, and date-scopes row IDs.

Focused Miller Value assertions passed `2/2`; Ruff/format/diff checks passed.
The exact branch-scoped gate passed backend units `1577/1577`, integration
`405/405` with `82.06%` combined coverage, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned with no retained containers,
volumes, networks, or testcontainer sessions. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified Adaptive Investments holdings completeness

Product commit `71ea4f76c` requires and records the published composition date
for Adaptive Investments' official ADPV Nuxt holdings payload. The adapter
verifies non-empty issuer-native rows, fails closed for undated pages, records
both `composition_date` and `as_of_date`, scopes
`completeness_status: complete` to the native route, and date-scopes row IDs.

Focused Adaptive Investments assertions passed `2/2`; Ruff/format/diff checks
passed. The exact branch-scoped gate at `71ea4f76c` passed backend units
`1576/1576`, integration `405/405` with `82.06%` combined coverage, frontend
Vitest `1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the same six protected watchlist-column-editor/
workspace-floating diffs remain. Docker resources were cleaned with no
retained containers, volumes, networks, or testcontainer sessions. No
provider/fallback, migration, visual baseline, threshold, mask, skip, or
acceptance policy changed. Family-wide R1 population/history, D1/W1/MN floors,
continuity, and AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified ETC/Bluemonte holdings completeness

Product commit `6dd0521df` requires and records the published composition date
for Exchange Traded Concepts and Bluemonte's official embedded holdings
payloads. The adapters verify non-empty issuer-native rows, fail closed for
undated pages, record both `composition_date` and `as_of_date`, scope
`completeness_status: complete` to the native routes, and date-scope row IDs.
The branch-tip gate at `71ea4f76c` includes this product commit.

Focused ETC/Bluemonte assertions passed `2/2`; Ruff/format/diff checks passed.
The exact branch-scoped gate passed backend units `1576/1576`, integration
`405/405` with `82.06%` combined coverage, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified WealthTrust holdings completeness

Product commit `481d60892` requires and records the published holdings
snapshot date for WealthTrust WLTG's official complete holdings table. The
adapter reads the labeled `Current as of`/`As of Date` page metadata, verifies
official product identity and non-empty rows, fails closed for undated pages,
and scopes explicit `completeness_status: complete` to the native route;
generic current/daily/table labels remain fail-closed.

Focused WealthTrust assertions passed `2/2`; Ruff/format/diff checks passed.
The exact branch-scoped gate passed backend units `1574/1574`, integration
`405/405` with `82.05%` combined coverage, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified linked-workbook holdings completeness

Product commit `c2671c2c9` requires and records a holdings-specific published
`Data as of` date for the official linked-workbook family: Little Harbor,
Pettee/Hoya, Sound Capital/River1, and Sovereign. Each adapter now parses the
issuer page's holdings section, verifies non-empty rows and native route
identity, fails closed when the holdings page is undated, and scopes explicit
`completeness_status: complete` to the native route; generic current/daily/
table labels remain fail-closed.

Focused linked-workbook assertions passed `8/8`; Ruff/format/diff checks
passed. The exact branch-scoped gate passed backend units `1573/1573`,
integration `405/405` with `82.05%` combined coverage, frontend Vitest
`1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the same six protected watchlist-column-editor/
workspace-floating diffs remain. Docker resources were cleaned. No provider/
fallback, migration, visual baseline, threshold, mask, skip, or acceptance
policy changed. Family-wide R1 population/history, D1/W1/MN floors,
continuity, and AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified GraniteShares holdings completeness

Product commit `8b4b6129d` requires a published composition date for
GraniteShares' official NVD holdings workbook route. The adapter derives the
snapshot date from the issuer-published workbook filename, verifies the native
route and non-empty rows, and now fails closed when an undated workbook is
returned; explicit `completeness_status: complete` remains scoped to the
native route and generic current/daily/table labels remain fail-closed.

Focused GraniteShares assertions passed `4/4`; Ruff/format/diff checks passed.
The exact branch-scoped gate passed backend units `1569/1569`, integration
`405/405` with `82.04%` combined coverage, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified Range ETFs holdings completeness

Product commit `827ae2b02` requires a published composition date for Range
ETFs' official COAL/NUKZ Nuxt holdings payloads. The adapter verifies
non-empty rows and the issuer-native holdings component; undated pages now fail
closed while explicit `completeness_status: complete` remains scoped to the
native route; generic current/daily/table labels remain fail-closed.

Focused Range assertions passed `2/2`; Ruff/format/diff checks passed. The
exact branch-scoped gate passed backend units `1568/1568`, integration `405/405`
with `82.04%` combined coverage, frontend Vitest `1067/1067`, type-check/build,
compose/deployment contracts, expected research-runner probes, and functional
E2E `165 passed` with `107 skipped`. Visual E2E passed `98/104`; the same six
protected watchlist-column-editor/workspace-floating diffs remain. Docker
resources were cleaned. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Family-wide R1
population/history, D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified Palmer Square holdings completeness

Product commit `4effca228` requires a published composition date for Palmer
Square's official PSQO/PSQA product-page embedded Full Investment Holdings
payload. The adapter already verifies non-empty rows and issuer-native payload
identity; undated pages now fail closed while explicit
`completeness_status: complete` remains scoped to the native route; generic
current/daily/table labels remain fail-closed.

Focused Palmer Square assertions passed `2/2`; Ruff/format/diff checks passed.
The exact branch-scoped gate passed backend units `1567/1567`, integration
`405/405` with `82.04%` combined coverage, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified Retireful/Mohr holdings completeness

Product commit `697b51d00` requires a published composition date for
Retireful/Mohr's official paginated holdings tables for RULE, SNAV, MFUL, and
CNAV. The adapter verifies non-empty rows, declared-count reconciliation, and
the published `As of` snapshot date; undated tables fail closed while explicit
`completeness_status: complete` remains scoped to the native route; generic
current/daily/table labels remain fail-closed.

Focused Retireful assertions passed `2/2`; Ruff/format/diff checks passed.
The exact branch-scoped gate passed backend units `1566/1566`, integration
`405/405` with `82.04%` combined coverage, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified Indexperts holdings completeness

Product commit `81d551a48` requires a published composition date for
Indexperts' official QIDX/RILA/YFFI holdings JSON feed. The adapter verifies
parseable non-empty rows and dated `holdingdates.medata`; undated payloads fail
closed while explicit `completeness_status: complete` remains scoped to the
native route; generic current/daily/table labels remain fail-closed.

Focused Indexperts assertions passed `2/2`; Ruff/format/diff checks passed.
The exact branch-scoped gate passed backend units `1565/1565`, integration
`405/405` with `82.04%` combined coverage, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified Soundwatch holdings completeness

Product commit `7f8c1abe5` requires a published composition date for
Soundwatch SHDG's official issuer-linked XLS workbook. The adapter verifies
parseable non-empty rows and the product-page `Data as of` snapshot date;
undated workbooks fail closed while explicit `completeness_status: complete`
remains scoped to the native route; generic current/daily/table labels remain
fail-closed.

Focused Soundwatch assertions passed `2/2`; Ruff/format/diff checks passed.
The exact branch-scoped gate passed backend units `1564/1564`, integration
`405/405` with `82.03%` combined coverage, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified Artemis and X-Square holdings completeness

Product commit `05971d070` requires a published composition date for Artemis
Capital's official holdings table and X-Square Capital's official holdings
payload. Each adapter verifies parseable non-empty rows and a published
snapshot date; undated payloads fail closed while explicit
`completeness_status: complete` remains scoped to the native routes; generic
current/daily/table labels remain fail-closed.

Focused Artemis/X-Square assertions passed `4/4`; Ruff/format/diff checks
passed. The exact branch-scoped gate passed backend units `1563/1563`,
integration `405/405`, frontend Vitest `1067/1067`, type-check/build,
compose/deployment contracts, expected research-runner probes, and functional
E2E `165 passed` with `107 skipped`. Visual E2E passed `98/104`; the same six
protected watchlist-column-editor/workspace-floating diffs remain. Docker
resources were cleaned. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Family-wide R1
population/history, D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain
open.

## 2026-09-14 — Promote verified MUFG, McIvy/Genter, and Langar holdings completeness

Product commit `6fcc3c382` requires a published composition date for MUFG Japan
Small Cap's official product-page Nuxt holdings component and McIvy/Genter and
Langar's issuer-scoped Nottingham holdings JSON routes. Each adapter verifies
parseable non-empty rows and a published snapshot date; undated payloads fail
closed while explicit `completeness_status: complete` remains scoped to the
native routes; generic current/daily/table labels remain fail-closed.

Focused MUFG/Genter/Langar assertions passed `6/6`; Ruff/format/diff checks
passed. The exact branch-scoped gate passed backend units `1561/1561`,
integration `405/405` with `82.03%` combined coverage, frontend Vitest
`1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the same six protected watchlist-column-editor/
workspace-floating diffs remain. Docker resources were cleaned. No
provider/fallback, migration, visual baseline, threshold, mask, skip, or
acceptance policy changed. Family-wide R1 population/history, D1/W1/MN floors,
continuity, and AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified National Security Index holdings completeness

Product commit `325bb4762` requires a published composition date for the
National Security Index ETF's official product-page declared holdings CSV and
preserves explicit `completeness_status: complete`. The adapter verifies
issuer/product identity, parseable non-empty rows, and a published snapshot
date; undated payloads fail closed and generic current/daily/table labels
remain fail-closed.

Focused NSI assertions passed `24/24`; Ruff/format/diff checks passed. The
exact branch-scoped gate passed backend units `1558/1558`, integration
`405/405` with `81.98%` combined coverage, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-14 — Promote verified AOT, SMI 3Fourteen, and Abacus Global holdings completeness

Product commit `56f982a39` requires a published composition date and adds
explicit `completeness_status: complete` to AOT's official holdings table,
SMI 3Fourteen's official holdings table, and Abacus Global's official holdings
CSV route. Each adapter verifies parseable non-empty rows and a published
snapshot date; undated payloads fail closed and generic current/daily/table
labels remain fail-closed.

Focused AOT/3Fourteen/Abacus assertions passed `6/6`; Ruff/format/diff checks
passed. The exact branch-scoped gate passed backend units `1557/1557`,
integration `405/405` with `81.98%` combined coverage, frontend Vitest
`1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the same six protected watchlist-column-editor/
workspace-floating diffs remain. Docker resources were cleaned. No
provider/fallback, migration, visual baseline, threshold, mask, skip, or
acceptance policy changed. Family-wide R1 population/history, D1/W1/MN floors,
continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Victory, DWS/Xtrackers, and Principal holdings completeness

Product commit `ce4937c71` requires a published composition date and adds
explicit `completeness_status: complete` to VictoryShares' official product
API, DWS/Xtrackers' official PDP holdings JSON, and Principal's official
holdings workbook routes. Each adapter verifies parseable non-empty rows and a
published snapshot date; undated payloads fail closed and generic
current/daily/table labels remain fail-closed.

Focused Victory/DWS/Principal assertions passed `7/7`; Ruff/format/diff checks
passed. The exact branch-scoped gate passed backend units `1554/1554`,
integration `405/405` with `81.98%` combined coverage, frontend Vitest
`1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the same six protected watchlist-column-editor/
workspace-floating diffs remain. Docker resources were cleaned. No
provider/fallback, migration, visual baseline, threshold, mask, skip, or
acceptance policy changed. Family-wide R1 population/history, D1/W1/MN floors,
continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Polen and Founder holdings completeness

Product commit `c581637ba` requires a published composition date and adds
explicit `completeness_status: complete` to Polen's configured official
holdings export and Founder's official holdings PDF route. Each adapter
verifies issuer/product identity, parseable non-empty rows, and a published
snapshot date; undated payloads fail closed and generic current/daily/table
labels remain fail-closed.

Focused Polen/Founder assertions passed `5/5`; Ruff/format/diff checks passed.
The exact branch-scoped gate passed backend units `1551/1551`, integration
`405/405` with `81.98%` combined coverage, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Hedgeye holdings completeness

Product commit `a3f07cb79` requires a published composition date and adds
explicit `completeness_status: complete` to Hedgeye's official daily holdings
payload routes and the S.C.M. Edge subclass using those routes. The adapter
verifies the latest requested fund snapshot, non-empty holdings, and a
published snapshot date; undated payloads fail closed and generic
current/daily/table labels remain fail-closed.

Focused Hedgeye/S.C.M. Edge assertions passed `3/3`; Ruff/format/diff checks
passed. The exact branch-scoped gate passed backend units `1548/1548`,
integration `405/405` with `81.98%` combined coverage, frontend Vitest
`1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the same six protected
watchlist-column-editor/workspace-floating diffs remain. Docker resources were
cleaned. No provider/fallback, migration, visual baseline, threshold, mask,
skip, or acceptance policy changed. Family-wide R1 population/history,
D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Liquid Strategies holdings completeness

Product commit `45ac854c3` requires a published composition date and adds
explicit `completeness_status: complete` to Liquid Strategies' official
Overlay Shares holdings-table routes (OVL, OVS, OVF, OVLH, OVB, OVT, OVM). The
adapter verifies configured product-page identity, required holdings schema,
parseable non-empty rows, and a published composition date; undated tables fail
closed and generic current/daily/table labels remain fail-closed.

Focused Liquid Strategies assertions passed `2/2`; Ruff/format/diff checks
passed. The exact branch-scoped gate passed backend units `1547/1547`,
integration `405/405` with `81.98%` combined coverage, frontend Vitest
`1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the same six protected
watchlist-column-editor/workspace-floating diffs remain. Docker resources were
cleaned. No provider/fallback, migration, visual baseline, threshold, mask,
skip, or acceptance policy changed. Family-wide R1 population/history,
D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Fortuna holdings completeness

Product commit `23ed4643c` requires a published composition date and adds
explicit `completeness_status: complete` to Fortuna's official holdings-table
route. The adapter verifies official product/table identity, parseable
non-empty rows, and a published composition date; undated tables fail closed
and generic current/daily/table labels remain fail-closed.

Focused Fortuna assertions passed `2/2`; Ruff/format/diff checks passed. The
exact branch-scoped gate passed backend units `1546/1546`, integration
`405/405` with `81.98%` combined coverage, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Hotchkis & Wiley holdings completeness

Product commit `22de7e669` requires dated holdings metadata and adds explicit
`completeness_status: complete` to Hotchkis & Wiley's HWSM official
literature-page linked monthly holdings PDF route. The adapter verifies HWSM
product-page identity, issuer-declared PDF linkage, PDF fund identity,
parseable non-empty rows, and a published composition date; undated PDFs fail
closed and generic current/daily/table labels remain fail-closed.

Focused HWSM assertions passed `2/2`; Ruff/format/diff checks passed. The exact
branch-scoped gate passed backend units `1545/1545`, integration `405/405` with
`81.98%` combined coverage, frontend Vitest `1067/1067`, type-check/build,
compose/deployment contracts, expected research-runner probes, and functional
E2E `165 passed` with `107 skipped`. Visual E2E passed `98/104`; the same six
protected watchlist-column-editor/workspace-floating diffs remain. Docker
resources were cleaned. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Family-wide R1
population/history, D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Nomura and Delaware holdings completeness

Product commit `68e059423` requires dated holdings metadata and adds explicit
`completeness_status: complete` to Nomura's configured daily product-page
routes and Delaware/Macquarie successor routes using the same official Nomura
table. Both paths verify official product identity, exact seven-column daily
schema, non-empty rows, and a parsed issuer date; generic current/daily/table
labels remain fail-closed and no fallback was added.

Focused Nomura/Delaware assertions passed `2/2`; Ruff/format/diff checks
passed. The exact branch-scoped gate passed backend unit `1544/1544`,
integration `405/405`, frontend Vitest `1067/1067`, type-check/build,
compose/deployment contracts, expected research-runner probes, and functional
E2E `165 passed` with `107 skipped`. Visual E2E passed `98/104`; the same six
protected watchlist-column-editor/workspace-floating diffs remain. Docker
resources were cleaned. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Family-wide R1
population/history, D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified IronHorse holdings completeness

Product commit `f2e00d61f` closes a bounded R1 source-quality seam for
IronHorse/Conductor's CGV official product-page declared full CSV route. The
native route verifies official product identity, declared download linkage,
exact CSV schema, dated holdings metadata, and non-empty rows before emitting
explicit `completeness_status: complete`; undated or empty native downloads
continue to fail into the existing SEC fallback.

Focused IronHorse assertions passed `2/2`; Ruff/format/diff checks passed. The
exact branch-scoped gate passed backend unit `1544/1544`, integration `405/405`,
frontend Vitest `1067/1067`, type-check/build, compose/deployment contracts,
expected research-runner probes, and functional E2E `165 passed` with `107
skipped`. Visual E2E passed `98/104`; the same six protected
watchlist-column-editor/workspace-floating diffs remain. Docker resources were
cleaned. No provider/fallback, migration, visual baseline, threshold, mask,
skip, or acceptance policy changed. Family-wide R1 population/history,
D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Cyber Hornet holdings completeness

Product commit `e0cc62996` closes a bounded R1 source-quality seam for Cyber
Hornet's BBB, EEE, SSS, and XXX issuer-page declared full holdings CSV routes.
The adapter verifies issuer download linkage, current dated holdings
disclosure, exact CSV schema, and non-empty rows before emitting explicit
`completeness_status: complete`; generic current/daily/table labels remain
fail-closed and no fallback was added.

Focused Cyber Hornet assertion passed `1/1`; Ruff/format/diff checks passed.
The exact branch-scoped gate passed backend unit `1544/1544`, integration
`405/405`, frontend Vitest `1067/1067`, type-check/build, compose/deployment
contracts, expected research-runner probes, and functional E2E `165 passed`
with `107 skipped`. Visual E2E passed `98/104`; the same six protected
watchlist-column-editor/workspace-floating diffs remain. Docker resources were
cleaned. No provider/fallback, migration, visual baseline, threshold, mask,
skip, or acceptance policy changed. Family-wide R1 population/history,
D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Dividend Assets holdings completeness

Product commit `7f7a32ef1` closes a bounded R1 source-quality seam for
Dividend Assets Capital's DVGR official product-page holdings table. The
adapter verifies official product identity and ticker, exact table schema, one
consistent effective date across issuer rows, and non-empty holdings before
emitting explicit `completeness_status: complete`; generic current/daily/table
labels remain fail-closed and no fallback was added.

Focused Dividend Assets assertion passed `1/1`; Ruff/format/diff checks passed.
The exact branch-scoped gate passed backend unit `1544/1544`, integration
`405/405`, frontend Vitest `1067/1067`, type-check/build, compose/deployment
contracts, expected research-runner probes, and functional E2E `165 passed`
with `107 skipped`. Visual E2E passed `98/104`; the same six protected
watchlist-column-editor/workspace-floating diffs remain. Docker resources were
cleaned. No provider/fallback, migration, visual baseline, threshold, mask,
skip, or acceptance policy changed. Family-wide R1 population/history,
D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Morgan Stanley holdings completeness

Product commit `d50362dfe` closes a bounded R1 source-quality seam for Morgan
Stanley's MSLC issuer-linked current holdings workbook. The adapter verifies
the official product page and linked XLSX, expected fund identity, exact
workbook schema and identifiers, dated holdings metadata, and non-empty rows
before emitting explicit `completeness_status: complete`; generic
current/daily/table labels remain fail-closed and no fallback was added.

Focused Morgan Stanley assertions passed `2/2`; Ruff/format/diff checks
passed. The exact branch-scoped gate passed backend unit `1544/1544`,
integration `405/405`, frontend Vitest `1067/1067`, type-check/build,
compose/deployment contracts, expected research-runner probes, and functional
E2E `165 passed` with `107 skipped`. Visual E2E passed `98/104`; the same six
protected watchlist-column-editor/workspace-floating diffs remain. The
provider-probe stage was skipped because this change was not classified as
provider-related. Docker resources were cleaned. No provider/fallback,
migration, visual baseline, threshold, mask, skip, or acceptance policy
changed. Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Golden Eagle holdings completeness

Product commit `9b793f88e` closes a bounded R1 source-quality seam for Golden
Eagle's HYP official product-page holdings route. The adapter verifies the
official product identity and ticker, exact holdings table schema, issuer-
declared holding count against parsed security rows, dated `As of` metadata,
and non-empty holdings before emitting explicit
`completeness_status: complete`; generic current/daily/table labels remain
fail-closed and no fallback was added.

Focused Golden Eagle assertions passed `2/2`; Ruff/format/diff checks passed;
full backend units passed `1544/1544`; integration passed `405/405` with
`81.98%` combined coverage. The exact branch-scoped gate passed frontend
Vitest `1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the same six protected watchlist-column-editor/
workspace-floating diffs remain. Docker resources were cleaned with no
retained containers, volumes, networks, or testcontainer sessions. No generic
provider/fallback, migration, visual baseline, threshold, mask, skip, or
acceptance policy changed. Family-wide R1 population/history, D1/W1/MN floors,
continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Mairs & Power holdings completeness

Product commit `4e71fd4f5` closes a bounded R1 source-quality seam for Mairs &
Power's MINN municipal-bond ETF product page. The adapter verifies the exact
product identity, dated `FULL PORTFOLIO AS OF` marker, normalized issuer table
schema, and non-empty rows before emitting explicit
`completeness_status: complete`; generic current/daily/table labels remain
fail-closed and no fallback was added.

Focused Mairs & Power assertion passed `1/1`; Ruff/format/diff checks passed;
full backend units passed `1544/1544`. The exact branch-scoped gate passed
backend unit `1544/1544`, integration `405/405`, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Retireful holdings completeness

Product commit `afcdebe3d` closes a bounded R1 source-quality seam for
Retireful/Mohr's RULE, SNAV, MFUL, and CNAV official product-page routes. The
adapter verifies product identity, dated composition, issuer-declared holding
count, pagination integrity, and exact row-count reconciliation before
emitting explicit `completeness_status: complete`. Generic current/daily/table
labels remain fail-closed; no generic inference or fallback was added.

Focused Retireful assertion passed `1/1`; Ruff/format/diff checks passed; full
backend units passed `1544/1544`. The exact branch-scoped gate passed backend
unit `1544/1544`, integration `405/405`, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Artemis holdings completeness

Product commit `180228b40` closes a bounded R1 source-quality seam for
Artemis Investment Management's ACEP and AFOS official product-page routes.
The adapter verifies the configured product identity, official page, exact
`FUND HOLDINGS` eight-column schema, dated rows, and non-empty holdings before
emitting explicit `completeness_status: complete`. Generic current/daily/table
labels remain fail-closed; no generic inference or fallback was added.

Focused Artemis assertion passed `1/1`; Ruff/format/diff checks passed; full
backend units passed `1544/1544`. The exact branch-scoped gate passed backend
unit `1544/1544`, integration `405/405`, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified X-Square holdings completeness

Product commit `538c18fbd` closes a bounded R1 source-quality seam for
X-Square's ZTAX product-page/API route. The adapter verifies the official
product page ticker and fund identity, declared Full Holdings client/API,
returned fund symbol, `full` portfolio marker, dated rows, and non-empty
holdings, then emits explicit `completeness_status: complete`. Generic
current/daily/table labels remain fail-closed; no generic inference or
fallback was added.

Focused assertion passed `1/1`; Ruff/format/diff checks passed; full backend
units passed `1544/1544`. The exact branch-scoped gate passed backend unit
`1544/1544`, integration `405/405`, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and AC2–AC7/AC10
remain open.

## 2026-09-13 — Promote verified Focus Financial holdings completeness

Product commit `8d97540ec` closes a bounded R1 source-quality seam for Focus
Financial's EQTY Kovitz FilePoint JSON and EBI Longview fund-data table routes.
Both routes verify official route/product identity, composition date,
route-specific schema, and minimum holdings floors (10/100 rows), then emit
explicit `completeness_status: complete`. Generic current/daily/table labels
remain fail-closed; no generic inference or fallback was added.

Focused assertions passed `1/1`; Ruff/format/diff checks passed; full backend
units passed `1544/1544`. The exact branch-scoped gate passed backend unit
`1544/1544`, integration `405/405`, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and AC2–AC7/AC10
remain open.

## 2026-09-13 — Promote verified Vident/MM VAM holdings completeness

Product commit `3378e533f` closes a bounded R1 source-quality seam for the
four verified Vident/MM VAM product-page holdings routes: VUSE, VIDI, VBND,
and PPTY. The adapter verifies requested ticker/product identity, exact
holdings-table headers, one dated composition, and at least ten non-empty
rows, then emits explicit `completeness_status: complete`. Generic
current/daily/table labels remain fail-closed; no generic inference or
fallback was added.

Focused Vident/MM VAM assertions passed `2/2`; Ruff/format/diff checks passed;
full backend units passed `1544/1544`. The exact branch-scoped gate passed
backend unit `1544/1544`, integration `405/405`, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
sandbox/resource probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the same six protected watchlist-column-editor and
workspace-floating diffs remain. Docker resources were cleaned. No
provider/fallback, migration, visual baseline, threshold, mask, skip, or
acceptance policy changed. Family-wide R1 population/history, D1/W1/MN floors,
continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified native holdings completeness

Product commit `ce18a1b7b` closes a bounded R1 source-quality seam for four
issuer-native routes: Soundwatch SHDG's issuer-linked XLS, WealthTrust WLTG's
public complete holdings table, Eighth Wonder/Fundsmith ETFT's product-page
holdings payload, and Range COAL/NUKZ's official Nuxt fund pages. Each route
verifies official product identity, its route-specific workbook/table/payload
contract, and non-empty holdings before emitting explicit
`completeness_status: complete`. Generic current/daily/table labels remain
fail-closed; no generic inference or fallback was added.

Focused native adapter assertions passed `4/4`; Ruff/format/diff checks
passed; full backend units passed `1544/1544`. The exact branch-scoped gate
passed backend unit `1544/1544`, integration `405/405`, frontend Vitest
`1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner sandbox/resource probes, and functional E2E `165 passed` with
`107 skipped`. Visual E2E passed `98/104`; the same six protected
watchlist-column-editor and workspace-floating diffs remain. Docker resources
were cleaned. No provider/fallback, migration, visual baseline, threshold,
mask, skip, or acceptance policy changed. Family-wide R1 population/history,
D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified linked workbook holdings completeness

Product commit `ce00fa0fa` closes a bounded R1 source-quality seam for four
issuer-linked workbook groups: Little Harbor MSTB/MSTQ/RMIF, Pettee/Hoya
HOMZ/RIET, Sound Capital RVER, and Sovereign SOVF. Each adapter verifies the
exact public product page, fund identity, declared download linkage, workbook
schema/identity, and non-empty rows, then emits explicit
`completeness_status: complete`. Generic current/daily/table labels remain
fail-closed; no generic inference or fallback was added.

Focused adapter coverage passed `4/4`; Ruff/format/diff checks passed; full
backend units passed `1544/1544`. The exact branch-scoped gate passed backend
unit `1544/1544`, integration `405/405`, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor and workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Indexperts holdings completeness

Product commit `d3fa295a9` closes a bounded R1 source-quality seam for
Indexperts' RILA/QIDX/YFFI holdings routes. The adapter verifies the exact
public ETF product page, `Portfolio Holdings` marker, payload ticker/fund
identity, dated holding metadata, and non-empty rows, then emits explicit
`completeness_status: complete`. Generic current/daily/table labels remain
fail-closed; no generic inference or fallback was added.

Focused Indexperts adapter coverage passed `1/1`; Ruff/format/diff checks
passed; full backend units passed `1544/1544`. The exact branch-scoped gate
passed backend unit `1544/1544`, integration `405/405`, frontend Vitest
`1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the same six protected watchlist-column-editor and
workspace-floating diffs remain. Docker resources were cleaned. No
provider/fallback, migration, visual baseline, threshold, mask, skip, or
acceptance policy changed. Family-wide R1 population/history, D1/W1/MN floors,
continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified MUFG holdings completeness

Product commit `96b13c816` closes a bounded R1 source-quality seam for
Mitsubishi UFJ's MJSC public product-page Nuxt holdings component. The
adapter verifies exact public product identity, route slug, named holdings
component, dated hydration payload, and non-empty rows, then emits explicit
`completeness_status: complete`. Japanese venue tickers remain source
metadata rather than fabricated platform symbols; no generic inference or
fallback was added.

Focused MUFG adapter coverage passed `1/1`; Ruff/format/diff checks passed;
full backend units passed `1544/1544`. The exact branch-scoped gate passed
backend unit `1544/1544`, integration `405/405`, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified publisher fund-scoped holdings completeness

Product commit `829ed19f2` closes a bounded R1 source-quality seam for
McIvy/Genter's GENT/GEND/GENM/GENW routes and Langar's LGHT route. The
adapters verify public issuer-settings fund identity, fund-scoped publisher
JSON ticker/fund/name identity, dated `pricing.effdate`, and non-empty
holdings; live probes require at least 30 rows with CUSIPs. They now emit
explicit `completeness_status: complete`. Generic current/daily/table labels
remain fail-closed as `unknown`; no generic inference or fallback was added.

Focused adapter assertions passed `2/2`; Ruff/format/diff checks passed; full
backend units passed `1544/1544`. The exact branch-scoped gate passed backend
unit `1544/1544`, integration `405/405`, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed.
Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified native holdings completeness

Product commit `c8ba7a600` closes a bounded R1 source-quality seam for three
issuer-native routes: NSI's product-page-declared CSV, Palmer Square's dated
Full Investment Holdings payload, and Weitz's dated identity-checked payload.
They now emit explicit `completeness_status: complete` while retaining their
curated complete-daily/full-investment labels; generic current/daily/table
labels remain fail-closed and no generic inference or fallback was introduced.

Focused NSI/Palmer Square/Weitz adapter assertions passed `4/4`; declared-
completeness refresh checks passed `8/8`; Ruff/format/diff checks passed; full
backend units passed `1544/1544`. The exact branch-scoped gate passed backend
unit `1544/1544`, integration `405/405`, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
sandbox/resource probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the same six protected
watchlist-column-editor/workspace-floating diffs remain. Docker resources were
cleaned. No provider/fallback, migration, visual baseline, threshold, mask,
skip, or acceptance policy changed. Family-wide R1 population/history,
D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified dated holdings completeness

Product commit `df0952777` closes a bounded R1 completeness seam for the
Absolute Investment Advisers ABEQ financial-statement route and STF
Management TUG quarterly-schedule route. Both existing routes are issuer-page
linked, select the newest dated complete PDF, and now emit explicit
`completeness_status: complete`; ABEQ also enforces at least ten rows and at
least 85% aggregate weight. Generic dated labels remain fail-closed and no
generic inference or fallback was introduced.

Focused ABEQ/TUG adapter assertions passed `2/2`; Ruff/format/diff checks
passed; full backend units passed `1544/1544`. The exact branch-scoped gate
passed backend unit `1544/1544`, integration `405/405`, frontend Vitest
`1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner sandbox/resource probes, and functional E2E `165 passed` with
`107 skipped`. Visual E2E passed `98/104`; the same six protected
watchlist-column-editor/workspace-floating diffs remain. Docker resources were
cleaned. No provider/fallback, migration, visual baseline, threshold, mask,
skip, or acceptance policy changed. Family-wide R1 population/history,
D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Distribution Cognizant completeness

Product commit `ba9f9a6eb` closes a bounded R1 completeness seam for the
Distribution Cognizant VOXP adapter. Its existing route verifies the
account-scoped CSV, required holdings schema, symbol/account filter, dated
snapshot, and a minimum ten-row composition before accepting the result. The
result now carries explicit `completeness_status: complete`; the generic
`issuer_reported_daily_holdings` quality label remains unchanged and no
generic inference or fallback was introduced.

Focused Concourse/Distribution adapter assertions passed `2/2`; Ruff/format/
diff checks passed; full backend units passed `1544/1544`. The exact
branch-scoped gate passed backend unit `1544/1544`, integration `405/405`,
frontend Vitest `1067/1067`, type-check/build, compose/deployment contracts,
expected research-runner sandbox/resource probes, and functional E2E
`165 passed` with `107 skipped`. Visual E2E passed `98/104`; the same six
protected watchlist-column-editor/workspace-floating diffs remain. Docker
resources were cleaned. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Family-wide R1
population/history, D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain
open.

## 2026-09-13 — Promote verified Concourse completeness

Product commit `2c9444ab0` closes a narrow R1 completeness seam for the
Concourse CCFE adapter. Its existing route checks the official product-page
identity, exact holdings-table schema, effective date, and a minimum ten-row
composition before accepting the result. The result now carries explicit
`completeness_status: complete`; the generic `issuer_reported_current_holdings`
quality label remains unchanged and no generic inference or fallback was
introduced.

The focused Concourse adapter regression passed `1/1`; Ruff/format/diff checks
passed; full backend units passed `1544/1544`. The exact branch-scoped gate
passed backend unit `1544/1544`, integration `405/405`, frontend Vitest
`1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner sandbox/resource probes, and functional E2E `165 passed` with
`107 skipped`. Visual E2E passed `98/104`; the same six protected
watchlist-column-editor/workspace-floating diffs remain. Docker resources
were cleaned and provider probes were skipped because no provider-related
changes were detected. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. Family-wide R1
population/history, D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote issuer-linked workbook holdings

Product commit `6287f6900` closes a bounded R1 source-quality seam for four
issuer-linked workbook adapters: Little Harbor, Pettee/Hoya, Sound Capital/
River1, and Sovereign/SOVF. Each adapter now emits
`issuer_page_declared_current_complete_holdings` only after verifying the
issuer page identity, declared workbook route, required workbook
identity/schema, and non-empty rows. Generic current, daily, and table labels
remain unknown; no broad inference or fallback was introduced.

Focused adapter assertions passed `4/4`, related refresh mapping checks passed
`7/7`, Ruff/format/diff checks passed, and full backend units passed
`1544/1544`. The exact branch-scoped gate passed backend unit `1544/1544`,
integration `405/405`, frontend Vitest `1067/1067`, type-check/build,
compose/deployment contracts, expected research-runner sandbox/resource
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned and provider probes were skipped
because no provider-related changes were detected. No provider/fallback,
migration, visual baseline, threshold, mask, skip, or acceptance policy
changed. Family-wide R1 population/history, D1/W1/MN floors, continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-13 — Promote verified Vident product-page holdings

Product commit `9ef91c40d` closes a narrowly verified holdings source-quality
gap. The unique `issuer_reported_product_page_holdings_table` label emitted by
the Vident/MM VAM adapter now maps to persisted `complete` evidence. That
adapter verifies its issuer page, requires the ETF Holdings schema and a
composition date, and rejects fewer than 10 rows; generic holdings-table
labels remain unknown rather than being promoted by inference.

Focused adapter/refresh coverage passed `519/519`; Ruff, formatting, and diff
checks passed; full backend units passed `1544/1544`. The exact branch-scoped
gate passed backend unit `1544/1544`, integration `405/405`, frontend Vitest
`1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the same six protected
watchlist-column-editor/workspace-floating diffs remain. Docker resources
were cleaned; provider probes were skipped because no provider-related changes
were detected. No provider/fallback, migration, visual baseline, threshold,
mask, skip, or acceptance policy changed. Family-wide R1 population/history,
D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Recognize issuer-page declared current completeness

Product commit `d0598946f` closes the next explicit source-quality seam in
the holdings persistence boundary. The curated adapter label
`issuer_page_declared_current_complete_holdings` now maps to `complete`
holdings evidence, so mature issuer-page routes that declare current,
complete holdings can participate in fail-closed readiness. Generic
current-only and ambiguous labels remain `unknown`; no substring inference or
fallback was introduced.

Focused refresh coverage passed `8/8`; Ruff, formatting, and diff checks
passed; full backend units passed `1543/1543`. The exact branch-scoped gate
passed backend unit `1543/1543`, integration `405/405`, frontend Vitest
`1067/1067`, type-check/build, compose/deployment contracts, expected
research-runner probes, and functional E2E `165 passed` with `107 skipped`.
Visual E2E passed `98/104`; the six unchanged protected
watchlist-column-editor/workspace-floating diffs remain. Docker resources
were cleaned; provider probes were skipped because no provider-related changes
were detected. No provider/fallback, migration, visual baseline, threshold,
mask, skip, or acceptance policy changed. Family-wide R1 population/history,
D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Preserve profile source quality on the latest refresh route

Product commit `9ed31ba86` closes the latest/current route-parity seam in the
holdings persistence boundary. When a curated profile declares
`holdings_source_quality`, the latest refresh route now carries that alias
through persistence instead of falling back to the generic self-snapshotted
label; the same route therefore retains the corresponding complete or filing-
reconstructed status as the dated route. Focused bootstrap/refresh coverage
passed `24/24`; Ruff, formatting, and diff checks passed; full backend units
passed `1542/1542`.

The exact branch-scoped gate passed backend unit `1542/1542`, integration
`405/405`, frontend Vitest `1067/1067`, type-check/build, compose/deployment
contracts, expected research-runner probes, and functional E2E `165 passed`
with `107 skipped`. Visual E2E passed `98/104`; the same six protected
watchlist-column-editor/workspace-floating diffs remain. Provider probes were
skipped because no provider-related changes were detected. Docker resources
were cleaned. No provider/fallback, migration, visual baseline, threshold,
mask, skip, or acceptance policy changed. R1 family-wide population/history,
D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Preserve explicit holdings completeness declarations

Product commit `42ffb4418` closes the next R1 source-quality seam. Curated
holdings routes that explicitly declare `filing_reconstructed_holdings`,
`issuer_reported_dated_complete_holdings`,
`issuer_reported_complete_daily_holdings_csv`, or
`issuer_reported_full_investment_holdings` now produce the corresponding
promotable completeness status. Explicit `completeness_status` metadata still
wins, and ambiguous/current-only source labels remain `unknown`; no broad
substring inference was introduced.

The focused refresh regression passed `7/7`, Ruff passed, and full backend
units passed `1541/1541`. The exact branch-scoped gate at this product tip
passed backend integration `405/405`, frontend Vitest `1067/1067`,
type-check/build, compose/deployment contracts, expected research-runner
probes, and functional E2E `165 passed` with `107 skipped`. Visual E2E passed
`98/104`; the same six protected watchlist-column-editor/workspace-floating
diffs remain. Docker resources were cleaned. No provider/fallback, migration,
visual baseline, threshold, mask, skip, or acceptance policy changed. R1
family-wide population/history, D1/W1/MN floors, continuity, and AC2–AC7/AC10
remain open.

## 2026-09-13 — Monotonic completeness promotion during snapshot re-ingest

Product commit `0b2f03070` closes the persistence half of the holdings
completeness gate. When a fetch reconciles to an existing snapshot content
hash, the stored evidence now merges statuses monotonically: stronger
`complete` or `filing_reconstructed` evidence is retained, weaker retries
cannot downgrade it, and adapter success state reflects the merged status.
This prevents a previously incomplete snapshot from remaining permanently
non-ready after a later complete re-ingest, without weakening the fail-closed
readiness contract.

Focused holdings-resolution coverage passed `30/30`; related refresh,
benchmark-family coverage/history suites passed `43/43`; full backend units
passed `1536/1536`; Ruff and diff checks passed. The exact branch-scoped gate
at this product tip passed frontend Vitest `1067/1067`, type-check/build,
compose/deployment contracts, expected research-runner probes, and functional
E2E `165 passed` with `107 skipped`. Visual E2E passed `98/104`; the same six
protected watchlist-column-editor/workspace-floating diffs remain. Docker
resources were cleaned. No provider/fallback, migration, visual baseline,
threshold, mask, skip, or acceptance policy changed. R1 family-wide
population/history, D1/W1/MN floors, continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Require persisted holdings completeness before readiness

The benchmark-family coverage contract now requires the selected persisted
holdings snapshot to be complete before its composite role can become `ready`.
The accepted completeness statuses are `complete` and
`filing_reconstructed`; `partial` and `unknown` remain non-ready even when
member resolution and D1/W1/MN numeric floors are present. The API and
frontend contracts expose `holdings_completeness_status` so the source-quality
gate is auditable by the workstation.

The role unit regression, real-Postgres composition regression (including the
incomplete-snapshot mutation), full backend units (`1535/1535`), frontend
Vitest (`1067/1067`), type-check/build, Ruff, formatting, and diff checks pass.
The exact gate at product tip `87f9a7a43` then passed backend integration
`405/405`, functional E2E `165 passed` with `107 skipped`, and visual E2E
`98/104`; the only visual failures are the six unchanged protected baselines.
An earlier F8u drag miss was transient: the isolated test passed once and
`5/5` repeats, and the clean gate rerun passed all functional tests. This is
one bounded R1 canonical-readiness seam; family-wide population/history,
continuity, and AC2–AC7/AC10 remain open. No provider/fallback, migration,
visual, or acceptance policy changed.

## 2026-09-13 — Canonical family readiness composition contract and exact gate

Product commit `62d4ac8de` adds a deterministic real-Postgres integration
proof for a complete SPY cap-weight role: verified SPDR entitlement for
universe discovery and price history, a complete point-in-time snapshot, two
resolved weighted/classified members, and 252 D1, 52 W1, and 24 MN adjusted
provider bars per member. The public role status is `available`; composite
readiness is `ready` with no reasons. This proves one complete family-role
composition seam, not family-wide persistence/history coverage.

The focused integration passed `1/1`. At coherent tip `4d1a05db4` (including
the test-only Golden Layout wrapper-independent F8u-boolean assertion), the
exact branch-scoped gate passed backend units `1534/1534`, integration
`405/405`, frontend Vitest `1067/1067`, functional E2E `165 passed` with
`107 skipped`, and visual E2E `98/104`. Provider probes were skipped because
no provider-related changes were present. The six unchanged protected visual
diffs remain open and Docker resources were cleaned. No product/provider/
fallback, migration, visual baseline, threshold, mask, skip, or acceptance
policy changed. Continue R1 canonical persistence/population/history,
family-wide D1/W1/MN floors, rebalance continuity, and AC2–AC7/AC10.

## 2026-09-13 — Extend the non-iShares family history matrix

Product commit `7df91ec76` adds a bounded opt-in live regression for the 12
canonical non-iShares family legs with curated SEC-backed routes at the
`2026-06-30` cutoff: `SPY`, `SPYV`, `SPYG`, `MDY`, `MDYV`, `MDYG`, `SLYV`,
`SLYG`, `SPTM`, `RSP`, `QQQ`, and `QQQE`. All 12 routes reported
`sec_filing`/`sec` lineage, verified filing identity, echoed the requested
date, and returned composition no later than the cutoff; QQQE required 80
rows and every other case required 100. The focused live suite passed `12/12`.
The deterministic taxonomy/family-history/refresh matrix passed `46/46`.

The exact branch-scoped `full_stack_browser` gate was rerun at this product
tip and completed backend unit `1534/1534`, backend integration `404/404`,
frontend Vitest `1067/1067`, functional E2E `165 passed` with `107 skipped`,
and visual E2E `98/104`. Provider probes were `not configured` because
`RUN_LIVE_PROVIDER_TESTS` was unset. The six unchanged protected visual
diffs remain the only visual failures; branch-scoped Docker resources were
cleaned. This evidence is route-level only and does not establish persisted
family snapshots/member bars, D1/W1/MN floors, or continuity. R1 population,
history, floors, continuity, and AC2–AC7/AC10 remain open. No visual,
provider/fallback, migration, or acceptance policy changed.

## 2026-09-13 — Extend the iShares family history matrix to an older cutoff

Product commit `32e1ab645` adds a parametrized opt-in live regression for all
eight canonical iShares family legs (`IJR`, `IWB`, `IWD`, `IWF`, `IWM`, `IWN`,
`IWO`, and `IWV`) at `2025-12-31`. Each route returned at least 100 holdings
rows through `issuer_public_json_api_as_of_date`, echoed the requested date,
and reported a composition date no later than the cutoff. The complete bounded
date matrix passed `17/17`, combining the eight new older-date cases, the eight
existing `2026-06-30` cases, and the dedicated older IWM regression. Full
backend units passed `1534/1534`; Ruff, formatting, and `git diff --check`
passed. The exact branch-scoped gate at docs tip `d7bbc4564` completed all
non-visual stages: backend integration `404/404`, frontend Vitest `1067/1067`,
functional E2E `165 passed` with `107 skipped`, and visual E2E `98/104`.
Provider probes were skipped because no provider-related paths changed. This
is auditable route evidence only: it does not persist snapshots, resolve
member placeholders, prove D1/W1/MN floors, or establish rebalance continuity.
The six unchanged protected visual diffs and R1/R2–R7 gaps remain open.

## 2026-09-13 — Prove older IWM point-in-time history and rerun exact gate

### Captured final gate receipt

The final captured PTY run at product commit `5caacf901` completed with the
same expected result: backend unit `1534/1534`, integration `404/404`,
frontend Vitest `1067/1067`, functional E2E `165 passed`/`107 skipped`, and
visual E2E `98/104`. Provider probes were `not configured` because
`RUN_LIVE_PROVIDER_TESTS` was unset. The six unchanged protected visual diffs
remain the only failures; the branch-scoped stack, volumes, images, and
testcontainer sessions were cleaned. This receipt does not close R1 or the
remaining acceptance criteria.

Product commit `5caacf901` adds a focused regression for the Russell 2000
IWM route at `2025-12-31`, alongside the existing `2026-06-30` family date.
Both dates resolve through the public iShares JSON route with matching
composition dates; the focused live history suite passed `10/10`. The exact
branch-scoped `full_stack_browser` gate at this coherent tip completed all
repository, dependency/migration, Ruff/format, TypeScript, backend unit,
backend integration, frontend Vitest, compose/deployment, research-runner,
functional, and four-project visual stages with the same results as the prior
IWM receipt: unit `1534/1534`, integration `404/404`, Vitest `1067/1067`,
functional `165 passed`/`107 skipped`, and visual `98/104`. Provider probes
reported `not configured` because `RUN_LIVE_PROVIDER_TESTS` was unset.
The six unchanged protected visual diffs remain; stack resources were cleaned.
No provider/fallback, visual threshold/mask/skip, migration, or acceptance
policy changed. R1 canonical population/history, D1/W1/MN floors and
continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Exact gate at IWM historical-route coverage tip

At clean product tip `f36421f49` (the focused test commit), the existing
date-aware iShares family route matrix now includes IWM. The opt-in focused
live suite passed `9/9`, including an IWM 2026-06-30 historical snapshot
resolved through the public iShares JSON route with `2009` constituent rows.
The exact branch-scoped `full_stack_browser` gate then passed repository,
dependency/migration, Ruff/format, TypeScript, backend unit (`1534/1534`,
69% total coverage), backend integration (`404/404`, 81.97% combined
coverage), frontend Vitest (`1067/1067`, 85.22%), compose/deployment
contracts, expected research-runner sandbox/resource probes, and functional
E2E (`165 passed`, `107 skipped`). Provider probes reported `not configured`
because `RUN_LIVE_PROVIDER_TESTS` was unset; deterministic provider contracts
remain authoritative. Visual E2E passed `98/104`; the six unchanged protected
diffs remain watchlist-column-editor at 1080p 100/125 and workspace-floating at
1080p 100/125 and 1440p 100/125. The branch-scoped stack, volumes, built
images, and testcontainer sessions were cleaned. No provider/fallback,
visual threshold/mask/skip, migration, or acceptance policy changed. R1
canonical provider population/history, D1/W1/MN floors and continuity, and
AC2–AC7/AC10 remain open.

## 2026-09-13 — Exact gate at corrected SLYG SEC identity tip

At product tip `c7d84436f` and documentation/session tip `e7f37222a`, the
exact branch-scoped `full_stack_browser` gate passed repository/workstream
validation, locked dependencies and migration checks, Ruff check/format,
TypeScript, backend unit (`1534/1534`, 69% total coverage), backend
integration (`404/404`, 81.97% combined coverage), frontend Vitest
(`1067/1067`, 85.22% coverage), compose/deployment contracts,
research-runner sandbox/resource probes, and functional E2E (`165 passed`,
`107 skipped`). Provider probes were correctly skipped because the gate's
provider-change detector found no provider-related path changes. Visual E2E
passed `98/104`; the six unchanged protected diffs remain
watchlist-column-editor at 1080p 100/125 and workspace-floating at 1080p
100/125 and 1440p 100/125. The branch-scoped stack, volumes, built images,
and testcontainer sessions were cleaned. No visual threshold, mask, skip,
provider, fallback, migration, or acceptance policy changed. R1 canonical
provider population/history, D1/W1/MN floors and continuity, and AC2–AC7/AC10
remain open.

## 2026-09-13 — Correct SLYG SEC identity and fail closed on curated routes

Product commit `c7d84436f` corrects SLYG's curated SEC identity to series
`S000006990` / class `C000019043`, matching the SEC filing for the State
Street SPDR S&P 600 Small Cap Growth ETF. Identity-constrained SEC searches
now use a bounded 400-filing window and apply the same series/class/ticker
check to legacy holdings documents, preventing an unrelated parseable filing
from being accepted. Focused adapter/taxonomy/SEC coverage passed `535/535`,
the full backend unit suite passed `1534/1534` with 34 dependency warnings,
Ruff/format/workstream/diff checks passed, the corrected SLYG live route passed
`1/1`, and the selected SPDR family live routes passed `9/9`. No fallback,
visual, migration, or acceptance policy changed. R1 provider population,
broader history, D1/W1/MN floors and continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Harden dock activation and rerun the exact gate

Product commit `c9e3819c4` extends the bounded Golden Layout activation wait
from roughly one second to four seconds, covering cold reinstalls while still
failing deterministically instead of waiting without a bound. The isolated
F9g/F9h sequence and five repeated F9h runs passed, and the full functional
E2E suite passed `165` tests with `107` intentional skips. The exact
branch-scoped gate completed all pre-visual stages, frontend build, compose
contracts, research-runner probes, functional E2E, and `98/104` visual
assertions. The only six visual failures are unchanged protected baselines:
watchlist-column-editor at 1080p 100/125 and workspace-floating at 1080p and
1440p 100/125. No visual threshold, mask, skip, provider, fallback, migration,
or acceptance policy changed. R1 canonical provider population/history,
D1/W1/MN floors and continuity, and AC2–AC7/AC10 remain open.

## 2026-09-13 — Bulk provider lineage promotion

Product commit `a4ce2447c3` aligns scheduled/bulk OHLCV maintenance with the
canonical provider upsert used by interactive market-data reads. Every
provider-returned bar is now upserted, so a late provider-native D1 observation
reclaims a matching locally-derived adjusted key and clears its derivation
metadata; the reported count remains the number of previously absent keys.
Focused bulk/market-data coverage passed `39/39`, the full backend unit suite
passed `1532/1532` with 69.01% total coverage, and Ruff, formatting, and diff
checks passed. No provider routing, fallback, migration, visual, or acceptance
policy changed. R1 population, W1/MN floors and continuity, and AC2–AC7/AC10
remain open; rerun the exact gate at this documentation tip.

## 2026-09-13 — Reviewed family issuer/SEC history routes

The opt-in live provider route probe exercised `19` selected iShares, SPDR,
Invesco, and SEC-backed family-history cases; all `19` tests passed. Pytest
exited non-zero only because this narrow selection covered 15.13% of the
module, below the repository's 55% coverage threshold. The probe therefore
confirms route behavior only; it does not prove persisted snapshots, complete
family population, D1/W1/MN floors, or rebalance continuity. No code, provider
fallback, visual, or acceptance policy changed.

## 2026-09-12 — Complete event-first provider-factor refresh ordering

Product commit `d0bdba6d1` closes the inverse provider-refresh ordering gap.
After raw OHLCV bars are durably upserted by range, latest-page,
historical-page, or bulk ingestion, the existing provider-factor materializer
now runs for that timeframe when explicit factors were previously observed.
The operation remains fail-closed for unsupported, incomplete, mixed, or
ambiguous evidence; raw and provider-native adjusted rows remain authoritative,
and a derived-view failure cannot fail raw ingestion. Focused event, bulk, and
market-data coverage passes `41/41`; the full backend unit suite passes
`1531/1531` with 69.01% total coverage; Ruff, formatting, and diff checks pass.
No provider routing, fallback, migration, visual, or acceptance policy
changed. R1 provider population, broader family history, bar floors, and
AC2–AC7/AC10 remain open; rerun the exact gate at the next clean documentation
tip.

## 2026-09-12 — Exact gate at event-first provider-factor tip

At product tip `d0bdba6d1`, the exact branch-scoped `full_stack_browser` gate
passed repository/workstream validation, locked dependencies and migration
checks, Ruff check/format, TypeScript, backend unit (`1531/1531`), backend
integration (`404/404`, `81.97%` combined coverage), research-runner
sandbox/resource probes, and functional E2E (`165 passed`, `107 skipped`).
Visual E2E passed `98/104`; the six unchanged protected diffs remain
watchlist-column-editor at 1080p 100/125 and workspace-floating at 1080p
100/125 and 1440p 100/125. The branch-scoped stack, volumes, and four built
images were cleaned. No visual threshold, mask, skip, provider, fallback,
migration, or acceptance rule changed. Provider population/history, bar floors,
and AC2–AC7/AC10 remain open; continue the next bounded canonical seam.

## 2026-09-12 — Exact gate at provider-factor refresh tip

At clean branch tip `04a7e283f` (product tip `77f63e7c5`, documentation tip
`efff81c9f`), the exact branch-scoped `full_stack_browser` gate passed locked
dependency and migration checks, Ruff check/format, TypeScript, backend unit
(`1530/1530`), backend integration (`404/404`, `81.98%` combined coverage),
frontend unit (`1067/1067`), research-runner sandbox/resource probes, and
functional E2E (`165 passed`, `107 skipped`). Visual E2E passed `98/104`; the
six unchanged protected diffs are watchlist-column-editor at 1080p 100/125 and
workspace-floating at 1080p 100/125 and 1440p 100/125. The branch-scoped
stack, volumes, and four built images were cleaned. No visual threshold, mask,
skip, provider, fallback, migration, or acceptance rule changed. Continue the
next bounded canonical provider/history or compatible R4/R2–R7 seam;
provider population, bar floors, and AC2–AC7/AC10 remain open.

## 2026-09-12 — Snapshot backfill collapses same-date revisions

The scheduled benchmark-family member-history backfill now keeps the
latest-known persisted disclosure for each symbol/effective composition date.
Corrected same-date rows remain intact in source history and the audit trail,
but they no longer consume the bounded backfill snapshot cap or enqueue
duplicate instrument/date work. The regression proves the corrected revision
wins deterministically from the existing known-at ordering; focused history
coverage passes `27/27`, the full backend unit suite passes `1529/1529`, and
Ruff, formatting, and diff checks pass. No provider, fallback, migration,
visual, or acceptance policy changed. This is a bounded R1 rebalance-continuity
maintenance closure; full provider population, bar floors, and AC2–AC7/AC10
remain open.

## 2026-09-12 — Materialize explicit provider factors after event refresh

Product commit `77f63e7c5` wires the provider-supplied adjustment-factor
contract into instrument-event refreshes. When a provider event response
contains an explicit factor, the refresh now discovers already-cached raw
timeframes and materializes their adjusted view through the existing
`provider_adjustment_factor` rebuilder. Split-only, amount-only, mixed, or
incomplete evidence remains fail-closed, raw/provider rows remain immutable,
and event-first or price-first arrival order is supported. Focused event and
adjustment-factor coverage passes `22/22`; the full backend unit suite passes
`1530/1530` with the existing 34 dependency warnings; Ruff, formatting, and
diff checks pass. No provider routing, fallback, migration, visual, or
acceptance policy changed. R1 provider population, broader family history,
bar floors, and AC2–AC7/AC10 remain open; rerun the exact gate at the next
clean documentation tip.

## 2026-09-12 — Exact gate at revision-aware history tip

At product tip `f54c5761a` and documentation tip `c1b502368`, the exact
branch-scoped gate passed dependency, migration, lint/format, TypeScript,
backend unit (`1529/1529`), backend integration (`404/404`, `81.98%`
combined coverage), frontend build/contracts/provider and research-runner
probes, and functional E2E (`165 passed`, `107 skipped`). Visual acceptance
remains `98/104` with exactly the six unchanged protected diffs: the
watchlist-column-editor states at 1080p 100/125 and workspace-floating states
at 1080p 100/125 and 1440p 100/125. The stack, volumes, and built images were
cleaned by the gate. No visual threshold, mask, skip, provider, fallback,
migration, or acceptance rule changed. Continue the next bounded canonical
provider/history or compatible R4/R2–R7 seam; AC2–AC7 and AC10 remain open.

## 2026-09-12 — Exact gate at point-in-time history tip

At product tip `fdb274af4` and documentation tip `a6cba5845`, the exact
branch-scoped gate passed backend unit (`1528/1528`), backend integration
(`404/404`, `81.98%` combined coverage), frontend build/contracts/provider and
research-runner probes, functional E2E (`165 passed`, `107 skipped`), and
`98/104` visual assertions. The six diffs remain the protected
watchlist-column-editor states at 1080p 100/125 and workspace-floating states
at 1080p 100/125 and 1440p 100/125; no visual threshold, mask, skip, provider,
fallback, migration, or acceptance rule changed. Stack and testcontainer
resources were cleaned. Continue the next bounded R1 provider/history or
compatible R4/R2–R7 seam; AC2–AC7 and AC10 remain open.

## 2026-09-12 — Preserve point-in-time membership in derived equal-weight history

The derived-equal-weight benchmark contract now applies canonical constituent
membership at each observation timestamp, rather than reusing a single
as-of-selected set across all history. This closes a bounded R3
look-ahead/survivorship gap for point-in-time additions and removals while
keeping bar normalization, coverage, and provenance behavior stable; the
response records the per-observation membership-selection semantics and the
number of distinct membership versions used. Docker-backed integration coverage
passes `2/2`; Ruff, format, and diff checks pass. No provider, fallback,
migration, visual, or acceptance policy changed. R1 canonical provider/history
readiness and AC2–AC7/AC10 remain open; continue with the next bounded seam and
rerun the exact gate at a clean coherent tip.

## 2026-09-12 — Exact dashboard Watchlist gate rechecked

At documentation tip `14d0a2b09` (product tip `f12e6f910`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam and rerun the exact gate at the
next coherent tip.

## 2026-09-12 — Fence dashboard Watchlist action teardown

Product commit `f12e6f910` closes a bounded R2/R6 lifecycle gap in the
dashboard Watchlist widget. Create, copy, delete, and add-by-symbol actions
now suppress late config patches or local-input cleanup when the widget is
unmounted or a newer action supersedes them. Store mutation semantics,
watchlist selection, managed/locked behavior, canonical symbol resolution,
provider routing, and visual contracts are unchanged. Focused Watchlist
lifecycle coverage passed `2/2`; full frontend Vitest passed `1067/1067` across
122 files; frontend type-check and production build passed with only the
existing chunk-size warning; and `git diff --check` passed. No visual baseline,
mask, threshold, skip, provider, fallback, or acceptance policy changed.
Record the exact gate at the next documentation tip then continue the next
bounded provider/history or compatible R4/R2-R7 seam.

## 2026-09-12 — Exact dashboard instrument-search gate rechecked

At documentation tip `87e19058f` (product tip `d924576f4`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam and rerun the exact gate at the
next coherent tip.

## 2026-09-12 — Fence dashboard instrument-search hydration teardown

Product commit `d924576f4` closes a bounded R2/R6 lifecycle gap in dashboard
Instrument Search. Debounced provider-search responses and asynchronous
canonical-symbol resolution now stop when the widget is unmounted or a newer
selection supersedes them; loading, error, dropdown, and emitted selection
state cannot be published by detached work. Search payloads, expression
resolution, canonical instrument semantics, provider routing, and visual
contracts are unchanged. Focused search coverage passed `5/5`; full frontend
Vitest passed `1065/1065` across 121 files; frontend type-check and production
build passed with only the existing chunk-size warning; and `git diff --check`
passed. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed. Record the exact gate at the next documentation tip
then continue the next bounded provider/history or compatible R4/R2-R7 seam.

## 2026-09-12 — Exact dashboard Heat Map gate rechecked

At documentation tip `d1deae3e1` (product tip `33b73482d`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam and rerun the exact gate at the
next coherent tip.

## 2026-09-12 — Fence dashboard Heat Map hydration teardown

Product commit `33b73482d` closes a bounded R2/R6 lifecycle gap in the
dashboard Heat Map. Screener/watchlist universe resolution, heatmap-data
loading, and nested live-price hydration now stop when the widget is unmounted
or a newer refresh supersedes them. Treemap geometry, metric coloring, live
price overlay semantics, API payloads, provider routing, and visual contracts
are unchanged. Focused Heat Map lifecycle coverage passed `2/2`; full frontend
Vitest passed `1064/1064` across 121 files; frontend type-check and production
build passed with only the existing chunk-size warning; and `git diff --check`
passed. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed. Record the exact gate at the next documentation tip
then continue the next bounded provider/history or compatible R4/R2-R7 seam.

## 2026-09-12 — Exact dashboard analytics gate rechecked

At documentation tip `2124d0730` (product tip `3a22c9ae9`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam and rerun the exact gate at the
next coherent tip.

## 2026-09-12 — Fence dashboard analytics teardown

Product commit `3a22c9ae9` closes bounded R2/R6 lifecycle gaps in the
Economic Calendar and Seasonality dashboard widgets. Calendar and monthly
seasonality responses now stop when the widget is unmounted or a newer symbol
request supersedes them; loading, error, month selection, and event state are
generation-guarded. Calendar/seasonality payloads, canonical symbols, provider
routing, period semantics, and visual contracts are unchanged. Focused
analytics lifecycle coverage passed `2/2`; full frontend Vitest passed
`1062/1062` across 120 files; frontend type-check and production build passed
with only the existing chunk-size warning; and `git diff --check` passed. No
visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Record the exact gate at the next documentation tip then
continue the next bounded provider/history or compatible R4/R2-R7 seam.

## 2026-09-12 — Exact dashboard screener gate rechecked

At documentation tip `520cbd60e` (product tip `e7136f18`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam and rerun the exact gate at the
next coherent tip.

## 2026-09-12 — Fence dashboard screener hydration teardown

Product commit `e7136f18` closes a bounded R2/R6 lifecycle gap in the
dashboard screener widget. Screener-list, latest-result, and nested instrument
metadata responses now stop when the widget is unmounted or a newer screener
run supersedes them; loading, error, selection, and instrument-map state are
also generation-guarded. Screener API payloads, canonical instrument
resolution, provider routing, result shapes, and visual contracts are
unchanged. Focused screener lifecycle coverage passed `2/2`; full frontend
Vitest passed `1060/1060` across 119 files; frontend type-check and production
build passed with only the existing chunk-size warning; and `git diff --check`
passed. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed. Record the exact gate at the next documentation tip
then continue the next bounded provider/history or compatible R4/R2-R7 seam.

## 2026-09-12 — Exact dashboard chart gate rechecked

At documentation tip `296d846e` (product tip `963892284`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam and rerun the exact gate at the
next coherent tip.

## 2026-09-12 — Fence dashboard chart hydration teardown

Product commit `963892284` closes a bounded R2/R6 lifecycle gap in the
dashboard advanced chart widget. Canonical symbol resolution, chart-store
hydration, read-only drawings/price-alert overlays, and error cleanup now stop
when the widget is unmounted or a newer refresh supersedes them. Chart payloads,
overlay semantics, provider routing, linked-symbol behavior, and visual
contracts are unchanged. Focused advanced-chart teardown coverage passed
`1/1`; full frontend Vitest passed `1058/1058` across 118 files; frontend
type-check and production build passed with only the existing chunk-size
warning; and `git diff --check` passed. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed. Continue the next
bounded provider/history or compatible R4/R2-R7 seam.

## 2026-09-12 — Exact dashboard hydration gate rechecked

At documentation tip `82e8786c` (product tip `7c51e3b28`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam and rerun the exact gate at the
next coherent tip.

## 2026-09-12 — Fence dashboard radar and instrument hydration

Product commits `c36c8f353` and `7c51e3b28` close bounded R2/R6 lifecycle
gaps in the dashboard consumers. Dashboard Radar list/detail refreshes and
dashboard quote/instrument-details metadata and OHLCV hydration now stop when
the widget is unmounted or a newer request supersedes them. Setup filtering,
canonical instrument resolution, API payloads, provider routing, chart links,
freshness/error behavior, and visual contracts are unchanged. Focused Radar
widget coverage passed `5/5`; focused quote/details lifecycle coverage passed
`2/2`; full frontend Vitest passed `1057/1057` across 117 files; frontend
type-check and production build passed with only the existing chunk-size
warning; and `git diff --check` passed. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed. Continue the next
bounded provider/history or compatible R4/R2-R7 seam.

## 2026-09-12 — Exact ChartPanel gate rechecked

At documentation tip `3a726786` (product tip `f50f1533`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam and rerun the exact gate at the
next coherent tip.

## 2026-09-12 — Fence ChartPanel hydration teardown

Product commit `f50f1533` closes a bounded R2/R6 chart-panel lifecycle gap.
Linked-panel symbol loads, timeframe changes, initial layout restoration,
instrument search responses, drawing hydration, and alert hydration now stop
when a newer selection or panel teardown supersedes them. Event and search
behavior, panel-store sequencing, canonical instrument resolution, provider
routing, chart payloads, drawings, alerts, and visual contracts are unchanged.
Focused ChartPanel lifecycle coverage passed `2/2`; full frontend Vitest passed
`1053/1053` across 116 files; frontend type-check and production build passed
with only the existing chunk-size warning; and `git diff --check` passed. No
visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Continue the next bounded provider/history or compatible
R4/R2-R7 seam while preserving the six protected visual state-oracle
assertions.

## 2026-09-12 — Fence Radar hydration teardown

Product commit `579eaa91` closes a bounded R2/R6 radar lifecycle gap. Radar
refresh/filter changes, detection selection/history, scan completion, basket
hydration, and alert/watchlist actions now respect mounted lifecycle state;
the refresh controls use an event-safe wrapper so filter events remain valid
requests. Radar store/API payloads, detection semantics, source handling, and
chart handoff are unchanged. Focused Radar coverage passed `6/6`; full
frontend Vitest passed `1051/1051` across 115 files; frontend type-check and
production build passed with only the existing chunk-size warning; and
`git diff --check` passed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam while preserving the six
protected visual state-oracle assertions.

## 2026-09-12 — Exact Radar gate rechecked

At documentation tip `5fc73856` (product tip `579eaa91`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam and rerun the exact gate at the
next coherent tip.

## 2026-09-12 — Fence ChartView selection hydration

Product commit `75bc03a3` closes a bounded R2/R6 top-down chart race. Single
and multi-panel symbol loads, linked drawings/alerts, comparisons, radar
overlays, timeframe changes, and mount hydration now stop when a newer
selection or teardown supersedes them. Existing canonical symbol resolution,
provider routing, chart data, ratios, indicators, drawings, and radar contracts
are unchanged. Focused ChartView handoff coverage passed `2/2`; full frontend
Vitest passed `1050/1050` across 115 files; frontend type-check and production
build passed with only the existing chunk-size warning; and `git diff --check`
passed. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed. Continue the next bounded provider/history or
compatible R4/R2-R7 seam while preserving the six protected visual
state-oracle assertions.

## 2026-09-12 — Exact provider-panel gate rechecked

At documentation tip `ff767486` (product tip `450c9746`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence Options Chain and ETF Holdings panel teardown

Product commit `450c9746` closes the paired provider/history read-panel
teardown gap. Options Chain and embedded ETF Holdings loads now combine their
existing request sequencing with mounted lifecycle generations, so late
instrument-resolution, chain, and holdings responses cannot publish detached
data, availability, loading, or error state. Canonical response shapes,
provider routing, point-in-time semantics, and unsupported-row handling are
unchanged. Focused panel coverage passed `6/6`; full frontend Vitest passed
`1049/1049` across 115 files; frontend type-check and production build passed
with only the existing chunk-size warning; and `git diff --check` passed. No
visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Continue the next bounded provider/history or compatible
R4/R2-R7 seam while preserving the six protected visual state-oracle
assertions.

## 2026-09-12 — Exact Settings-readiness gate rechecked

At documentation tip `4f927af3` (product tip `6df66ac3`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence Strategy Lab bootstrap teardown

Product commit `ce2ca1a6` closes a bounded R4/R6 lifecycle gap in the central
Strategy Lab consumer. Universe option hydration for watchlists, screeners,
baskets, and ETF holdings, post-bootstrap selection hydration, reload, and
coverage-preview responses now stop before publishing detached or superseded
local state. Strategy/Study payloads, lineage, provider routing, fallback,
and promotion contracts are unchanged. Focused Strategy Lab coverage passed
`29/29`; full frontend Vitest passed `1047/1047` across 115 files;
frontend type-check and production build passed with only the existing
chunk-size warning; and `git diff --check` passed. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed. Continue
the next bounded provider/history or compatible R4/R2-R7 seam while preserving
the six protected visual state-oracle assertions.

## 2026-09-12 — Exact reusable-basket gate rechecked

At documentation tip `8632f1aa` (product tip `f43ed459`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence Settings provider-readiness teardown

Product commit `6df66ac3` closes a bounded R6 lifecycle gap in the provider
readiness and reconciliation controls. OneSignal initialization, backend
health checks, provider policy/usage/availability loads and patches, and
admin reconciliation review now stop before publishing detached status,
policy, loading, or issue state; request sequences also prevent superseded
loads from winning. Existing provider API, entitlement, fallback, and
reconciliation contracts are unchanged. Focused Settings coverage passed
`5/5`; full frontend Vitest passed `1046/1046` across 115 files;
frontend type-check and production build passed with only the existing
chunk-size warning; and `git diff --check` passed. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed. Continue
the next bounded provider/history or compatible R4/R2-R7 seam while preserving
the six protected visual state-oracle assertions.

## 2026-09-12 — Fence reusable basket teardown

Product commit `f43ed459` closes a bounded R6 lifecycle gap in the reusable
universe editor. Basket reloads now use a lifecycle generation and request
sequence; save and delete flows stop before reloading or publishing local
selection, status, or error state after teardown. The refresh action uses an
event-safe wrapper while preserving the existing basket API, weighting,
read-only, and synthetic-chart behavior. Focused basket coverage passed
`6/6`; full frontend Vitest passed `1045/1045` across 115 files; frontend
type-check and production build passed with only the existing chunk-size
warning; and `git diff --check` passed. No provider, fallback, visual
baseline, mask, threshold, skip, or acceptance policy changed. Continue the
next bounded provider/history or compatible R4/R2-R7 seam while preserving the
six protected visual state-oracle assertions.

## 2026-09-12 — Exact ETF Holdings selection gate rechecked

At documentation tip `99328434` (product tip `a9602ebe`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence ETF Holdings profile-selection races

Product commit `a9602ebe` closes the companion R6/R2 selection-race gap in the
canonical ETF Holdings view. A profile-selection generation now scopes the
entire profile/bootstrap, snapshot, holdings, diff, weight-evolution,
transition, and overlap chain, so a newer profile invalidates older responses
before they can change the active workspace. The mounted lifecycle fence from
`d5e4b070` remains in force. API payloads, provider routing, point-in-time
semantics, fallback behavior, visual baselines, masks, thresholds, skips, and
acceptance policy are unchanged. Focused ETF Holdings coverage passed `7/7`;
full frontend Vitest passed `1044/1044` across 115 files; frontend type-check
and production build passed with only the existing chunk-size warning; and
`git diff --check` passed. A race regression proves an older profile cannot
proceed to holdings after a newer selection starts. Continue the next bounded
provider/history or compatible R4/R2-R7 seam while preserving the six
protected visual state-oracle assertions.

## 2026-09-12 — Fence ETF Holdings teardown

Product commit `d5e4b070` closes a bounded R6 lifecycle gap in the canonical
ETF Holdings view. Profile search/bootstrap, profile selection, snapshot
options, holdings, diff, weight-evolution, transition, and overlap requests
now share a mounted lifecycle generation in addition to their existing
request sequencing. Late responses stop before publishing detached profile,
snapshot, comparison, evolution, transition, overlap, loading, or error state;
chained profile selection also stops at every async boundary. API payloads,
provider routing, point-in-time semantics, fallback behavior, visual baselines,
masks, thresholds, skips, and acceptance policy are unchanged. Focused ETF
Holdings coverage passed `6/6`; full frontend Vitest passed `1043/1043` across
115 files; frontend type-check and production build passed with only the
existing chunk-size warning; and `git diff --check` passed. A teardown
regression proves a late profile response does not trigger snapshot loading.
Continue the next bounded provider/history or compatible R4/R2-R7 seam while
preserving the six protected visual state-oracle assertions.

## 2026-09-12 — Exact Research Results promotion gate rechecked

At documentation tip `7710ad52` (product tip `22a2548c`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker access was
denied for `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence Research Results promotion teardown

Product commit `22a2548c` closes a bounded R6 lifecycle gap in the persisted
Research Results surface. Breadth, event, structured scalar/series/range,
chart, column, gauge, alert, scan, Study Lab, and Strategy signal promotion
flows now fence late responses by the mounted mutation generation. Detached or
superseded responses cannot publish stale promotion messages, loading cleanup,
or cached scan/filter records. API, output-shape, lineage, provider, fallback,
visual baseline, mask, threshold, skip, and acceptance contracts are
unchanged. The focused Research Results suite passed `39/39`; full frontend
Vitest passed `1042/1042` across 115 files; frontend type-check and production
build passed with only the existing chunk-size warning; and `git diff --check`
passed. A teardown regression proves a late breadth promotion does not publish
after unmount. Continue provider/history, R4 fan-out, and R2-R7 evidence while
preserving the six protected visual state-oracle assertions.

## 2026-09-12 — Exact benchmark-analytics gate rechecked

At documentation tip `b3a8394f` (product tip `45dff3ec`), the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because the Docker API
returned permission denied for `unix:///Users/jagnelo/.docker/run/docker.sock`.
No backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence benchmark-family analytics teardown

Product commit `45dff3ec` closes a bounded R6 lifecycle gap in the shared
WorkstationToolContent benchmark-family surfaces. Benchmark-family readiness,
family analytics, overview, and benchmark-list loading indicators now use
independent request generations and stop publishing local state after teardown
or after a newer request supersedes them. Store/API contracts are unchanged.
Full frontend Vitest passed `1041/1041` across 115 files; frontend type-check
and production build passed with only the existing chunk-size warning; the
full backend unit suite passed `1523/1523` with `69.02%` coverage; and
`git diff --check` passed. No dedicated WorkstationToolContent component
harness exists, so higher-level workstation coverage remains the regression
signal. No provider, fallback, visual baseline, mask, threshold, skip, or
acceptance policy changed.

Continue provider/history, R4 fan-out, and R2-R7 evidence while preserving the
six protected visual state-oracle assertions.

## 2026-09-12 — Fence workstation watchlist mutations

Product commit `8b63be84` closes a bounded R6 lifecycle gap in the shared
WorkstationToolContent surface. Combo-list loading/mutations and personal
watchlist create, rename, copy, delete, add, and transfer actions now use
disposal-scoped sequences; on-mounted watchlist hydration also stops at each
async boundary after teardown. No store or API contract changed. Full frontend
Vitest passed `1041/1041` across 115 files; type-check and production build
passed with only the existing chunk-size warning; and `git diff --check`
passed. No provider, fallback, visual baseline, mask, threshold, skip, or
acceptance policy changed. The shared content has no dedicated component test
harness; higher-level workstation suites remain green.

## 2026-09-12 — Exact workstation-mutation gate rechecked

At product tip `8b63be84`, the exact branch-scoped gate passed git-diff,
workstream validation (30 records), dependency resolution, migration
head/compatibility, frontend dependency preparation, Ruff, formatting, and
TypeScript. `backend-coverage` then exited 2 after the fixed 180-second Docker
readiness window because Docker returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Fence Market Map definition publication

Product commit `5d4ca6a3` closes a bounded R6 lifecycle gap in reusable Market
Map breadth-definition saves. The code-asset write and cache invalidation now
remain scoped to a mounted source generation, so a detached or relinked map
cannot publish stale definition status or invalidate assets after teardown.
Focused Market Map coverage passed `51/51`; full frontend Vitest passed
`1041/1041` across 115 files; frontend type-check and production build passed
with only the existing chunk-size warning; and `git diff --check` passed. No
provider, fallback, visual baseline, mask, threshold, skip, or acceptance
policy changed. Continue the next bounded provider/history or compatible
R4/R2-R7 seam while preserving the six visual state-oracle assertions.

## 2026-09-12 — Exact definition-publication gate rechecked

At product tip `5d4ca6a3`, the exact branch-scoped gate passed git-diff,
workstream validation (30 records), dependency resolution, migration
head/compatibility, frontend dependency preparation, Ruff, formatting, and
TypeScript. `backend-coverage` then exited 2 after the fixed 180-second Docker
readiness window because Docker returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Fence personal Market Map publications

Product commit `728cc337` closes the remaining bounded Market Map publication
lifecycle gap. Selected-member and explicit-symbol personal-watchlist saves now
capture the active source and mounted generation, write members sequentially,
and stop before further writes or UI publication when the tool unmounts or the
universe changes. Focused Market Map coverage passed `50/50`; full frontend
Vitest passed `1040/1040` across 115 files; frontend type-check and production
build passed with only the existing chunk-size warning; and `git diff --check`
passed. No provider, fallback, visual baseline, mask, threshold, skip, or
acceptance policy changed. Continue the next bounded provider/history or
compatible R4/R2-R7 seam while preserving the six visual state-oracle
assertions.

## 2026-09-12 — Exact personal-publication gate rechecked

At product tip `728cc337`, the exact branch-scoped gate passed git-diff,
workstream validation (30 records), dependency resolution, migration
head/compatibility, frontend dependency preparation, Ruff, formatting, and
TypeScript. `backend-coverage` then exited 2 after the fixed 180-second Docker
readiness window because Docker returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Fence locked-source publication

Product commit `94f451e0` closes a bounded R6 lifecycle gap in Market Map's
locked-source publication. The API write, source-catalog reload, source
selection, and map rerun now share a mounted publication generation, so a late
response cannot publish a saved source into a detached or relinked universe.
Focused Market Map coverage passed `49/49`; full frontend Vitest passed
`1038/1038` across 115 files; frontend type-check and production build passed
with only the existing chunk-size warning; and `git diff --check` passed. No
provider, fallback, visual baseline, mask, threshold, skip, or acceptance
policy changed. Continue the next bounded provider/history or compatible
R4/R2-R7 seam while preserving the six visual state-oracle assertions.

## 2026-09-12 — Exact locked-source gate rechecked

At product tip `94f451e0`, the exact branch-scoped gate passed git-diff,
workstream validation (30 records), dependency resolution, migration
head/compatibility, frontend dependency preparation, Ruff, formatting, and
TypeScript. `backend-coverage` then exited 2 after the fixed 180-second Docker
readiness window because Docker returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Reset stale Market Map clone state

Product commit `cfc31024` closes the source-switch follow-on in Market Map.
Changing the active universe now clears invalidated clone busy, message, error,
and retry state, so a clone canceled by a source change cannot leave the next
universe disabled. Focused Market Map coverage passed `47/47`; full frontend
Vitest passed `1037/1037` across 115 files; frontend type-check and production
build passed with only the existing chunk-size warning; and `git diff --check`
passed. No provider, fallback, visual baseline, mask, threshold, skip, or
acceptance policy changed.

## 2026-09-12 — Exact stale-state gate rechecked

At product tip `cfc31024`, the exact branch-scoped gate passed git-diff,
workstream validation (30 records), dependency resolution, migration
head/compatibility, frontend dependency preparation, Ruff, formatting, and
TypeScript. `backend-coverage` then exited 2 after the fixed 180-second Docker
readiness window because Docker returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Fence Market Map source cloning

Product commit `8d78eb61` closes a bounded R6 lifecycle gap in Market Map's
explicit source cloning. Clone and retry flows now share a source-scoped
generation, stop sequential member writes when the tool unmounts or the
source changes, and fence all post-response status/error/loading mutations.
Focused Market Map coverage passed `46/46`; full frontend Vitest passed
`1036/1036` across 115 files; frontend type-check and production build passed
with only the existing chunk-size warning; and `git diff --check` passed. No
provider, fallback, visual baseline, mask, threshold, skip, or acceptance
policy changed. Continue the next bounded provider/history or compatible
R4/R2-R7 seam while preserving the six visual state-oracle assertions.

## 2026-09-12 — Exact source-clone gate rechecked

At product tip `8d78eb6177ed4f08359965251668574f186555a9`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker returned
permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No
backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence shared workstation content loaders

Product commit `8eb187fa` closes a bounded R6 lifecycle gap in the shared
WorkstationToolContent surface. Instrument, comparison, condition, indicator,
and Python-asset loader publications now stop after component disposal, and
teardown invalidates their independent request generations. Full frontend
Vitest passed `1035/1035` across 115 files; frontend type-check and
production build passed with only the existing chunk-size warning; and
`git diff --check` passed. No provider, fallback, visual baseline, mask,
threshold, skip, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam while preserving the six visual
state-oracle assertions.

## 2026-09-12 — Exact shared-content loader gate rechecked

At product tip `8eb187fab798eeb1c1f685e58198a3e7917ea89f`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then
exited 2 after the fixed 180-second Docker readiness window because Docker
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Fence ETF source bootstrap teardown

Product commit `f9ae2a21` closes a bounded R6 lifecycle gap in Market Map's
explicit ETF-source bootstrap. Bootstrap responses now require a mounted,
source-action generation before refreshing the source catalog, selecting the
new source, or publishing success/error/loading state. Focused Market Map
coverage passed `45/45`; full frontend Vitest passed `1035/1035` across 115
files; frontend type-check and production build passed with only the existing
chunk-size warning; and `git diff --check` passed. No provider, fallback,
visual baseline, mask, threshold, skip, or acceptance policy changed.
Continue the next bounded provider/history or compatible R4/R2-R7 seam while
preserving the six visual state-oracle assertions.

## 2026-09-12 — Exact ETF bootstrap gate rechecked

At product tip `f9ae2a2165791b4c54ec41f5f2be8bddf756773d`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then
exited 2 after the fixed 180-second Docker readiness window because Docker
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Fence Market Map history actions

Product commit `54a306bb` closes a bounded R6 lifecycle gap in Market Map.
Explicit history refresh and cancel actions now require a mounted,
source-scoped action generation before publishing queued-run state, status
messages, errors, or loading cleanup. A late response after closing the tool
cannot repopulate the detached surface. Focused Market Map coverage passed
`44/44`; full frontend Vitest passed `1034/1034` across 115 files;
frontend type-check and production build passed with only the existing
chunk-size warning; and `git diff --check` passed. No provider, fallback,
visual baseline, mask, threshold, skip, or acceptance policy changed.
Continue the next bounded provider/history or compatible R4/R2-R7 seam while
preserving the six visual state-oracle assertions.

## 2026-09-12 — Exact Market Map history-action gate rechecked

At product tip `54a306bb823596574d8e7bf1a40133380e01a6ea`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then
exited 2 after the fixed 180-second Docker readiness window because Docker
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Cancel aborted workstation opens

Product commit `67720cbb` closes a bounded R6 shell-resilience gap in
WorkstationView. Tool-open readiness waits are now released during teardown,
and an already-aborted open action exits before touching the detached DOM or
workspace state. The existing WorkstationView regression remains green at
`29/29`; full frontend Vitest passed `1033/1033` across 115 files; frontend
type-check and production build passed with only the existing chunk-size
warning; and `git diff --check` passed. No provider, fallback, visual
baseline, mask, threshold, skip, or acceptance policy changed. Continue the
next bounded provider/history or compatible R4/R2-R7 seam while preserving
the six visual state-oracle assertions.

## 2026-09-12 — Exact aborted-open gate rechecked

At product tip `67720cbb4198274975ffd8755ef61b41e80dce78`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then
exited 2 after the fixed 180-second Docker readiness window because Docker
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Fence Coverage Summary lifecycle

Product commit `05f5a4e9` closes a bounded R6 lifecycle gap in Coverage
Summary. Canonical coverage and OHLCV-range responses now invalidate on
unmount, so late responses cannot repopulate a closed coverage surface or
overwrite teardown state. Focused Coverage Summary coverage passed `5/5`; full
frontend Vitest passed `1033/1033` across 115 files; frontend type-check and
production build passed with only the existing chunk-size warning; and
`git diff --check` passed. No provider, fallback, visual baseline, mask,
threshold, skip, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam while preserving the six visual
state-oracle assertions.

## 2026-09-12 — Exact Coverage Summary gate rechecked

At product tip `05f5a4e9037e58b5938ea191bd4c679501b35f3b`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then
exited 2 after the fixed 180-second Docker readiness window because Docker
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Fence workstation hydration lifecycle

Product commit `d85bcc78` closes a bounded R6 shell-resilience gap in
WorkstationView. Initial workspace hydration, pop-out retry, symbol loading,
and canonical search callbacks now stop publishing after the workstation
unmounts; teardown also invalidates in-flight selection/search generations.
Focused WorkstationView coverage passed `29/29`; full frontend Vitest passed
`1032/1032` across 115 files; frontend type-check and production build passed
with only the existing chunk-size warning; and `git diff --check` passed. No
provider, fallback, visual baseline, mask, threshold, skip, or acceptance
policy changed. Continue the next bounded provider/history or compatible
R4/R2-R7 seam while preserving the six visual state-oracle assertions.

## 2026-09-12 — Exact workstation hydration gate rechecked

At product tip `d85bcc78db68b6dcd0d1591ca0d0d2ef7950bf73`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then
exited 2 after the fixed 180-second Docker readiness window because Docker
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Fence Study Lab mutation lifecycle

Product commit `e47b8fbf` closes a bounded R6 lifecycle gap in Study Lab.
Rerun and cancel responses are now fenced by mounted state and a mutation
generation, so late responses cannot repopulate a closed study surface or
overwrite newer run state. Focused Study Lab coverage passed `31/31`; full
frontend Vitest passed `1031/1031` across 115 files; frontend type-check and
production build passed with only the existing chunk-size warning; and
`git diff --check` passed. No provider, fallback, visual baseline, mask,
threshold, skip, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam while preserving the six visual
state-oracle assertions.

## 2026-09-12 — Exact Study Lab mutation gate rechecked

At product tip `e47b8fbf8dd7a217a6d600c19b82ae7828d9c914`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then
exited 2 after the fixed 180-second Docker readiness window because Docker
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Fence Research Results mutation lifecycle

Product commit `d9bd37c3` closes a bounded R6 lifecycle gap in Research
Results. Rerun and cancel responses are now fenced by mounted state and a
mutation generation, so late responses cannot repopulate a closed results
surface or overwrite newer state. Focused Research Results coverage passed
`38/38`; full frontend Vitest passed `1030/1030` across 115 files; frontend
type-check and production build passed with only the existing chunk-size
warning; and `git diff --check` passed. No provider, fallback, visual
baseline, mask, threshold, skip, or acceptance policy changed. Continue the
next bounded provider/history or compatible R4/R2-R7 seam while preserving
the six visual state-oracle assertions.

## 2026-09-12 — Exact Research Results mutation gate rechecked

At product tip `d9bd37c3c2d8e84f629fd4d65460771cc5ebadfb`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then
exited 2 after the fixed 180-second Docker readiness window because Docker
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence Relative Rotation lifecycle

Product commit `4a798f03` closes a bounded R6 lifecycle gap in Relative
Rotation. Rotation responses are now fenced by mounted state and load
generation, so a late request cannot repopulate a closed tool or overwrite a
newer configuration. Focused Relative Rotation coverage passed `10/10`; full
frontend Vitest passed `1029/1029` across 115 files; frontend type-check and
production build passed with only the existing chunk-size warning; and
`git diff --check` passed. No provider, fallback, visual baseline, mask,
threshold, skip, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam while preserving the six visual
state-oracle assertions.

## 2026-09-12 — Exact Relative Rotation lifecycle gate rechecked

At product tip `4a798f03ef42463a86f466e7a21a47b0d338664c`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then
exited 2 after the fixed 180-second Docker readiness window because Docker
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence Instrument Note lifecycle

Product commit `b3b1aaec` closes a bounded R6 lifecycle gap in Instrument
Notes. Note hydration and debounced saves are now fenced by mounted state and
load generation, so a late response cannot repopulate an unmounted or
relinked tool or write stale cache state after teardown. Focused linked-
instrument coverage passed `16/16`; full frontend Vitest passed `1028/1028`
across 115 files; frontend type-check and production build passed with only
the existing chunk-size warning; and `git diff --check` passed. No provider,
fallback, visual baseline, mask, threshold, skip, or acceptance policy
changed. Continue the next bounded provider/history or compatible R4/R2-R7
seam while preserving the six visual state-oracle assertions.

## 2026-09-12 — Exact Instrument Note lifecycle gate rechecked

At product tip `b3b1aaec6bcf079a393b1c7bf37407c77e54bffc`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then
exited 2 after the fixed 180-second Docker readiness window because Docker
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence Instrument Alerts lifecycle

Product commit `4ab7ceb1` closes a bounded R6 lifecycle gap in Instrument
Alerts. Alert-bundle hydration and create/update mutations are now fenced by
mounted state and the current view generation, so late responses cannot
repopulate an unmounted or relinked tool or overwrite its newer state.
Focused linked-instrument coverage passed `15/15`; full frontend Vitest
passed `1027/1027` across 115 files; frontend type-check and production
build passed with only the existing chunk-size warning; and `git diff --check`
passed. No provider, fallback, visual baseline, mask, threshold, skip, or
acceptance policy changed. Continue the next bounded provider/history or
compatible R4/R2-R7 seam while preserving the six visual state-oracle
assertions.

## 2026-09-12 — Exact Instrument Alerts lifecycle gate rechecked

At product tip `4ab7ceb194f5bdce28b85341dbe44141de9e5236`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then
exited 2 after the fixed 180-second Docker readiness window because Docker
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence VirtualWatchlist hydration lifecycle

Product commit `6e54f192` closes a bounded R6 lifecycle gap in Virtual
Watchlist. Saved screener, Python asset, and column-set hydration are now
fenced by mounted state and independent load generations, so late or
superseded responses cannot repopulate a closed list or overwrite newer
state. Focused VirtualWatchlist coverage passed `71/71`; full frontend
Vitest passed `1026/1026` across 115 files; frontend type-check and
production build passed with only the existing chunk-size warning; and
`git diff --check` passed. No provider, fallback, visual baseline, mask,
threshold, skip, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam while preserving the six visual
state-oracle assertions.

## 2026-09-12 — Exact VirtualWatchlist lifecycle gate rechecked

At product tip `6e54f192ecbc6b35fec42f75ef9541407d678675`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then
exited 2 after the fixed 180-second Docker readiness window because Docker
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence Chart Template loading lifecycle

Product commit `2cfaa4f6` closes a bounded R6 lifecycle gap in Chart Template
Control. Template hydration is now fenced by mounted state and load generation,
so a late or superseded response cannot repopulate a closed control or
overwrite newer template state. Focused Chart Template coverage passed `10/10`;
full frontend Vitest passed `1023/1023` across 115 files; frontend type-check
and production build passed with only the existing chunk-size warning; and
`git diff --check` passed. No provider, fallback, visual baseline, mask,
threshold, skip, or acceptance policy changed. Continue the next bounded
provider/history or compatible R4/R2-R7 seam while preserving the six visual
state-oracle assertions.

## 2026-09-12 — Exact Chart Template lifecycle gate rechecked

At product tip `2cfaa4f6b5e987aba6ce84684d0ca39ad572458b`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker returned
permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No
backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence Chart Plot Library loader lifecycle

Product commit `51be2db1` closes a bounded R6 lifecycle gap in Chart Plot
Library. Python asset and EasyScan history loaders are now fenced by mounted
state and independent load generations, so late or superseded responses cannot
repopulate a closed menu or overwrite newer loader state. Focused Chart Plot
Library coverage passed `31/31`; full frontend Vitest passed `1022/1022`
across 115 files; frontend type-check and production build passed with only
the existing chunk-size warning; and `git diff --check` passed. No provider,
fallback, visual baseline, mask, threshold, skip, or acceptance policy
changed. Continue the next bounded provider/history or compatible R4/R2-R7
seam while preserving the six visual state-oracle assertions.

## 2026-09-12 — Exact Chart Plot Library lifecycle gate rechecked

At product tip `51be2db172319759a13094961fc4421439d4b7d5`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker returned
permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No
backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

## 2026-09-12 — Exact Code Library lifecycle gate rechecked

At product tip `dffcc5cde1b9edee0749f12cdf6158fd9dd5da44`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker returned
permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No
backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence Code Library refresh lifecycle

Product commit `53d57c1d` closes a bounded R6 lifecycle gap in the Python
Library. Refresh responses are now fenced by the mounted component and the
latest refresh generation, so a late response after unmount or an overlapping
older request cannot publish stale assets, errors, or loading cleanup. Focused
Code Library component coverage passed `6/6`; full frontend Vitest passed
`1019/1019` across 115 files; frontend type-check and production build passed
with only the existing chunk-size warning; and `git diff --check` passed. No
provider, fallback, visual baseline, mask, threshold, skip, or acceptance
policy changed. Continue the next bounded provider/history or compatible
R4/R2-R7 seam while preserving the six visual state-oracle assertions.

## 2026-09-12 — Preserve Research Results selection during rerun

Product commit `4939c094` closes a bounded R6 selection race in Research
Results. A slower rerun response now updates the run list without stealing
focus from a newer run selected by the user. Focused Research Results
component coverage passed `37/37`; full frontend Vitest passed `1018/1018`
across 115 files; frontend type-check and production build passed with only
the existing chunk-size warning; and `git diff --check` passed. No provider,
fallback, visual baseline, mask, threshold, skip, or acceptance policy
changed. The exact branch gate was rerun at this tip and remains blocked only
at Docker-backed `backend-coverage` because the Docker socket returned
permission denied; no backend integration, provider, browser, or visual stage
ran. Continue the next bounded provider/history or compatible R4/R2-R7 seam
while preserving the six visual state-oracle assertions.

## 2026-09-12 — Exact Research Results selection gate rechecked

At product tip `4939c09433b52b6d055383e328adc348e9e82940`, the exact
branch-scoped gate passed git-diff, workstream validation (30 records),
dependency resolution, migration head/compatibility, frontend dependency
preparation, Ruff, formatting, and TypeScript. `backend-coverage` then exited
2 after the fixed 180-second Docker readiness window because Docker returned
permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No
backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

## 2026-09-12 — Restore live Market Map after snapshot selection

Product commit `02716f1b` closes a bounded R6 snapshot state-restoration gap.
Leaving a loaded saved snapshot through the selector, or deleting the selected
snapshot, now refreshes the current source result instead of presenting the
saved map under the `Live / cached result` selection. Focused Market Map
component coverage passed `43/43`; full frontend Vitest passed `1017/1017`
across 115 files; frontend type-check and production build passed with only
the existing chunk-size warning; and `git diff --check` passed. No provider,
fallback, visual baseline, mask, threshold, skip, or acceptance policy
changed. The exact branch gate was rerun at this tip and remains blocked only
at Docker-backed `backend-coverage` because the Docker socket returned
permission denied; no backend integration, provider, browser, or visual stage
ran. Continue the next bounded provider/history or compatible R4/R2-R7 seam
while preserving the six visual state-oracle assertions.

## 2026-09-12 — Exact live-snapshot transition gate rechecked

At product tip `02716f1b`, the exact branch-scoped gate passed git-diff,
workstream validation (30 records), dependency resolution,
migration head/compatibility, frontend dependency preparation, Ruff,
formatting, and TypeScript. `backend-coverage` then exited 2 after the fixed
180-second Docker readiness window because Docker returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Fence per-point breadth event knowledge

Product commit `070f6ef8` closes the remaining historical event leak in
breadth history. Event predicates now enforce each event's `fetched_at` against
the individual breadth point timestamp, so an event fetched later in the
requested range cannot affect earlier points even when the router loaded it
for the final `as_of` cutoff.

The focused breadth service suite passed `29/29`; the full backend unit suite
passed `1523/1523` at `69.02%` coverage; Ruff, formatting, and `git diff
--check` passed. No provider routing, fallback, visual baseline, mask,
threshold, skip, or acceptance policy changed. The exact branch gate was
rerun at this tip and remains pending only at Docker-backed `backend-coverage`
because the Docker socket returned permission denied.

## 2026-09-12 — Exact per-point breadth gate rechecked

The exact branch-scoped gate was rerun at product tip `070f6ef8`. Git-diff,
workstream validation (30 records), dependency resolution, migration
head/compatibility, frontend dependency preparation, Ruff, formatting, and
TypeScript all passed. The `backend-coverage` stage then stopped after the
fixed 180-second Docker readiness window because Docker returned permission
denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed.

## 2026-09-12 — Fence historical Market Map event knowledge

Product commit `26161b90` closes a bounded R2/R6 historical-event provenance
gap. Market Map event rows and source fetch-state markers now honor the map
evaluation cutoff, and event rows are associated with their own source state.
Future-fetched corporate events can no longer leak into an earlier map or make
an unavailable event dataset appear event-free; orphan event rows are handled
as unavailable instead of crashing the read path.

Focused Market Map service coverage passed `12/12`; the full backend unit suite
passed `1520/1520` at `68.99%` coverage; Ruff, formatting, and `git diff
--check` passed. No provider routing, fallback, visual baseline, mask,
threshold, skip, or acceptance policy changed. The exact branch gate remains
pending behind the Docker socket permission failure; continue the next bounded
provider/history or compatible R4/R2-R7 seam.

## 2026-09-12 — Fence historical breadth event knowledge

Product commit `218ad3b8` closes the analogous R2/R6 boundary in current and
historical breadth evaluation. Breadth event rows and source fetch-state
markers now honor the evaluation cutoff, and rows are included only when their
source has an eligible fetch state. Missing fetch state remains explicitly
unavailable instead of making an event-dependent predicate look event-free or
crashing on an orphan row.

The focused analysis-router suite passed `32/32`; the full backend unit suite
passed `1522/1522` at `69.01%` coverage; Ruff, formatting, and `git diff
--check` passed. No provider routing, fallback, visual baseline, mask,
threshold, skip, or acceptance policy changed. The exact branch gate remains
pending behind the Docker socket permission failure; continue the next bounded
provider/history or compatible R4/R2-R7 seam.

## 2026-09-12 — Fence adjustment-factor provenance by fetch time

Product commit `87134261` closes a bounded R1/R2 point-in-time provenance
gap in adjusted OHLCV dataset state. Normalized adjustment observations and
the legacy event fallback now require both an effective/event date and an
observation/fetch time no later than the persisted bar coverage end. A factor
discovered after that range can no longer be attributed backwards to an older
adjusted series.

The focused Market Data service suite passed `25/25`; the full backend unit
suite passed `1522/1522` at `69.01%` coverage; Ruff, formatting, and `git diff
--check` passed. No price transformation, provider routing, fallback, visual
baseline, mask, threshold, skip, or acceptance policy changed. The exact
branch gate was rerun at this tip and remains pending only at Docker-backed
`backend-coverage` because the Docker socket returned permission denied.

## 2026-09-12 — Exact factor-provenance gate rechecked

The exact branch-scoped gate was rerun at product tip `87134261`. Git-diff,
workstream validation (30 records), dependency resolution, migration
head/compatibility, frontend dependency preparation, Ruff, formatting, and
TypeScript all passed. The `backend-coverage` stage then stopped after the
fixed 180-second Docker readiness window because Docker returned permission
denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed.

## 2026-09-12 — Exact historical-event gate rechecked

The exact branch-scoped gate was rerun at product tip `26161b90`. Repository,
workstream validation (30 records), dependency/migration checks, frontend
preparation, Ruff, formatting, and TypeScript passed. The `backend-coverage`
stage then stopped after the fixed 180-second Docker readiness window because
the Docker socket returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

## 2026-09-12 — Fence stale Market Map snapshot mutations

Product commit `0e04d489` closes a bounded R6 snapshot-mutation race. Save and
delete operations now share the snapshot generation fence and verify mounted
state plus the current map cache or snapshot selection before applying a late
response. A save started for an older map can no longer select or label that
snapshot after a newer map refresh completes.

The focused Market Map component suite passed `42/42`; the full frontend
Vitest suite passed `1016/1016`; frontend type-check and `git diff --check`
passed. Existing expected watchlist-store failure-path stderr remains confined
to its tests. No provider, fallback, visual baseline, mask, threshold, skip,
or acceptance policy changed. The exact branch gate remains pending behind the
Docker socket permission failure; continue the next bounded provider/history
or compatible R4/R2-R7 seam at this coherent tip.

## 2026-09-12 — Fence stale Market Map snapshots

Product commit `fc012ad0` closes a bounded R6 snapshot-selection race in the
Market Map. Snapshot loads now carry a selection generation and verify the
current selection plus mounted state before applying the saved map, metadata,
errors, or loading cleanup; an older response cannot replace a newer snapshot.

The focused Market Map component suite passed `41/41`; the full frontend
Vitest suite passed `1015/1015`; frontend type-check and `git diff --check`
passed. Existing expected watchlist-store failure-path stderr remains confined
to its tests. No provider, fallback, visual baseline, mask, threshold, skip,
or acceptance policy changed. The exact branch gate remains pending behind the
Docker socket permission failure; continue the next bounded provider/history
or compatible R4/R2-R7 seam at this coherent tip.

## 2026-09-12 — Fence Market Map Python asset lifecycle

Product commit `a306e2f2` closes a bounded R6 lifecycle seam in the Market Map:
Python asset discovery now fences its response, error, and loading cleanup by
component generation and mounted state. A late `/code/assets` response after a
tool closes can no longer publish stale Python options or state.

The focused Market Map component suite passed `40/40`; the full frontend
Vitest suite passed `1014/1014`; frontend type-check and `git diff --check`
passed. Existing expected watchlist-store failure-path stderr remains confined
to its tests. No provider, fallback, visual baseline, mask, threshold, skip,
or acceptance policy changed. The exact branch gate remains pending behind the
Docker socket permission failure; continue the next bounded provider/history
or compatible R4/R2-R7 seam at this coherent tip.

## 2026-09-12 — Fence stale Market Map Python runs

Product commit `95ed93ce` closes a bounded R6/R2 stale-callback seam in
Market Map Python breadth/area runs. Queue responses and status polling now
carry the map-run generation and mounted-state guard, so a run started for an
older source cannot publish its run ID, re-enable Python loading, or continue
to the map request after a newer source/run has superseded it.

The focused Market Map component suite passed `39/39`; the full frontend
Vitest suite passed `1013/1013`; frontend type-check and `git diff --check`
passed. Existing expected watchlist-store failure-path stderr remains confined
to its tests. No provider, fallback, visual baseline, mask, threshold, skip,
or acceptance policy changed. The exact branch gate remains pending behind the
Docker socket permission failure; continue the next bounded provider/history
or compatible R4/R2-R7 seam at this coherent tip.

## 2026-09-12 — Fence dated benchmark coverage races

Product commit `6096ba0e` extends the Market Map stale-callback protection to
dated benchmark-family coverage. Each coverage read now has a generation fence
in addition to the source check, so changing the historical cutoff cannot let
an older response replace the current canonical readiness matrix; unmounted
tools cannot publish late errors or loading state.

The Market Map component suite passed `38/38`; the full frontend Vitest suite
passed `1012/1012`; frontend type-check and `git diff --check` passed. No
provider, fallback, visual baseline, mask, threshold, skip, or acceptance
policy changed. The exact branch gate remains pending behind the Docker socket
permission failure; continue the next bounded provider/history or compatible
R4/R2-R7 seam at this coherent tip.

## 2026-09-12 — Fence Market Map history readiness races

Product commit `c7a3c080` closes a bounded R6/R2 stale-callback seam in the
Market Map. History-status and refresh-run reads now carry a source/timeframe
generation and ignore late responses from an older source, timeframe, or
unmounted tool; invalidating a request also clears its loading state. This
keeps canonical coverage and refresh progress aligned with the visible source
while preserving the existing read-only history contract.

The Market Map component suite passed `37/37`, the full frontend Vitest suite
passed `1011/1011`, and frontend type-check plus `git diff --check` passed. No
provider, fallback, visual baseline, mask, threshold, skip, or acceptance
policy changed. The exact branch gate remains pending behind the Docker socket
permission failure; continue the next bounded provider/history or compatible
R4/R2-R7 seam at this coherent tip.

## 2026-09-12 — Exact coarse-cache gate rechecked

The exact branch-scoped gate was rerun at product tip `ad86c37b` after the
bulk-history cache-evidence fix. Git-diff, workstream validation, dependency
resolution, migration checks, frontend preparation, Ruff, formatting, and
TypeScript passed. The `backend-coverage` stage then stopped after the fixed
180-second Docker readiness window because the Docker socket returned
permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No
backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed. Restore
Docker health and rerun the exact gate, then continue the next bounded
provider/history or compatible R4/R2-R7 seam.

## 2026-09-12 — Preserve coarse-cache evidence during bulk history refresh

Product commit `ad86c37b` closes a bounded R1 history-worker correctness gap.
Bulk-fetch summaries count newly inserted bars, but that count is not evidence
that coarse history is absent: a repeat provider refresh can return only rows
already present in the canonical cache. The worker now probes persisted adjusted
D1/W1/MN rows through the requested end before applying its intraday-skip
optimization, so cached coarse evidence still permits the requested H1/M15/etc.
fetch. A genuinely empty coarse cache retains the existing skip optimization,
and intraday-only requests remain explicit. Bounded historical refreshes cannot
be satisfied by future rows.

Focused bulk-fetch coverage passed `12/12`; the full backend unit suite passed
`1518/1518` with the existing 34 deprecation warnings; Ruff, formatting, and
`git diff --check` passed. No provider routing, fallback, visual baseline, mask,
threshold, skip policy, or acceptance policy changed. The exact branch gate is
still pending behind the Docker socket failure; rerun it at this coherent tip,
then continue canonical provider/history and compatible R4/R2-R7 work.

## 2026-09-12 — Exact named-event target gate rechecked

The exact branch-scoped gate was rerun at product tip `033b0397` after the
named multi-output event regression correction. Git-diff, workstream
validation, dependency/migration checks, frontend preparation, Ruff,
formatting, and TypeScript passed. The `backend-coverage` stage then stopped
after the fixed 180-second Docker readiness window because the Docker socket
returned permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`.
No backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

## 2026-09-12 — Preserve named multi-output event targets

Product commit `033b0397` closes a regression in the single-event target
handler: explicitly selected named artifacts from multi-output `events` runs
again promote through their own filter/alert endpoint payload, while
single-output runs still require exactly one event artifact. The immutable
event contract and source/run/artifact lineage remain unchanged.

Focused Study Lab coverage passed `30/30`; full frontend Vitest passed
`1010/1010`; type-check, backend Ruff, formatting, and `git diff --check`
passed. The exact branch gate is pending at this coherent product tip.

## 2026-09-12 — Expose single-event Study Lab targets

Product commit `df4c89f0` closes the single-output `events` fan-out gap in the
primary Study Lab tool. Completed event studies now expose the declared
watchlist-filter and alert actions in addition to the existing Strategy signal
action. Both actions require exactly one named event artifact, route through the
existing `events_to_boolean` promotion endpoint, preserve run/artifact lineage,
and create an alert only from the persisted promoted filter. No event contract,
provider, fallback, visual, or acceptance policy changed.

Focused Study Lab component coverage passed `30/30`; full frontend Vitest passed
`1010/1010`; type-check and production build passed with only the existing
chunk-size warning; backend Ruff, formatting, and `git diff --check` passed.
The exact branch gate is pending at this coherent product tip.

## 2026-09-12 — Exact single-event target gate rechecked

The exact branch-scoped gate was rerun at product tip `df4c89f0` after the
single-event filter/alert slice. Git-diff, workstream validation,
dependency/migration checks, frontend preparation, Ruff, formatting, and
TypeScript passed. The `backend-coverage` stage then stopped after the fixed
180-second Docker readiness window because the Docker socket returned permission
denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed. Restore Docker health, rerun pending API
regressions and the exact gate, then continue the next bounded provider/history
or compatible chart/list/gauge seam.

## 2026-09-12 — Expose structured Study Lab Boolean signals

Product commit `1e128acd` closes an R4 fan-out cell in the primary Study Lab
tool. Named Boolean artifacts from multi-output studies now expose the
compatible Strategy Lab signal action alongside column, filter, scan, gauge,
and alert targets. The action creates the existing immutable signal asset with
the selected output name and lineage, then uses the existing Strategy-signal
consumer; scalar, series, range, and events capability boundaries remain
unchanged.

Focused Study Lab component coverage passed `30/30`; full frontend Vitest
passed `1010/1010`; type-check and production build passed (with only the
existing chunk-size warning); backend Ruff, formatting, and `git diff --check`
passed. The exact branch gate is pending at this coherent product tip. No
visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed.

## 2026-09-12 — Exact structured-signal gate rechecked

The exact branch-scoped gate was rerun at product tip `1e128acd` after the
structured Boolean signal slice. Git-diff, workstream validation,
dependency/migration checks, frontend preparation, Ruff, formatting, and
TypeScript passed. The `backend-coverage` stage then stopped after the fixed
180-second Docker readiness window because the Docker socket returned
permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No
backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health, rerun pending API regressions and the
exact gate at this tip, then continue the next bounded provider/history or
compatible chart/list/gauge seam.

## 2026-09-12 — Materialize scheduled coarse history from canonical D1

Product commit `9f86dc7b` closes the scheduled R1 history gap where nightly
refresh skipped missing W1/MN rows indefinitely. When canonical D1 history is
present, the nightly task now rebuilds provider-neutral W1/MN views from the
persisted D1 evidence after its recent refresh pass, preserves provider-row
precedence through the existing materializer, commits the derived state, and
reports W1/MN derived counts. No provider request, fallback policy, observed
session, or adjustment lineage is invented or changed.

Focused scheduled-history coverage passed `1/1`; the full backend unit suite
passed `1516/1516`; Ruff, formatting, and `git diff --check` passed. The exact
branch gate is pending at this coherent product tip. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

## 2026-09-12 — Next exact gate pending

The exact branch-scoped gate must be rerun at product tip `9f86dc7b`. The
previous gate stopped before backend integration because Docker's local socket
was unavailable; no backend integration, provider, browser, or visual result
is inferred from that stop. Restore Docker health, rerun the exact gate, then
continue the next bounded provider/history or compatible chart/list/gauge seam.

## 2026-09-12 — Exact scheduled coarse-history gate rechecked

The exact branch-scoped gate was rerun at product tip `9f86dc7b` after the
nightly coarse-history slice. Git-diff, workstream validation, dependency
resolution, migration checks, frontend preparation, Ruff, formatting, and
TypeScript passed. The `backend-coverage` stage then stopped after the fixed
180-second Docker readiness window because the Docker socket returned
permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No
backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health, rerun the pending API regressions and
exact gate at this tip, then continue the next bounded provider/history or
compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize Study Lab execution timestamps

Product commit `07fcfae0` closes the remaining explicit Study Lab execution
serialization seam. Portfolio entry/exit/open/rejected events, excursion rows,
and top-level trade/open-position records now use the shared UTC-`Z` timeline;
position IDs, ordering semantics, P&L, and event meanings remain unchanged.

Focused Study Lab service coverage passed `14/14`; Ruff, formatting, and
`git diff --check` passed. The exact branch gate is pending at this coherent
product tip. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

## 2026-09-12 — Exact Study Lab execution gate rechecked

The exact branch-scoped gate was rerun at product tip `07fcfae0` after the
execution timestamp slice. Git-diff, workstream validation, dependency
resolution, migration checks, frontend preparation, Ruff, formatting, and
TypeScript passed. The `backend-coverage` stage then stopped after the fixed
180-second Docker readiness window because the Docker socket returned permission
denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health, rerun pending API regressions and the
exact gate at this tip, then continue the next bounded provider/history or
compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize Study Lab timeline points

Product commit `40b8db13` closes the dense Study Lab timeline serialization
seam. Bar timestamps and trade/open-position event keys now share the UTC-`Z`
timeline, so `+00:00` and `Z` inputs cannot split one event across separate
portfolio points. Date-only fallbacks, position identity, P&L, and event
semantics remain unchanged.

Focused Study Lab service coverage passed `14/14`; Ruff, formatting, and
`git diff --check` passed. The exact branch gate is pending at this coherent
product tip. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

## 2026-09-12 — Exact Study Lab timeline gate rechecked

The exact branch-scoped gate was rerun at product tip `40b8db13` after the
dense Study Lab timeline serialization slice. Git-diff, workstream validation,
dependency resolution, migration checks, frontend preparation, Ruff,
formatting, and TypeScript passed. The `backend-coverage` stage then stopped
after the fixed 180-second Docker readiness window because the Docker socket
returned permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`.
No backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health, rerun pending API regressions and the
exact gate at this tip, then continue the next bounded provider/history or
compatible chart/list/gauge seam.

## 2026-09-12 — Exact Study Lab fallback timing gate rechecked

The exact branch-scoped gate was rerun at product tip `780ef1e3` after the
no-date Study Lab timeline fallback slice. Repository/workstream validation,
dependency resolution, migration checks, frontend preparation, Ruff,
formatting, and TypeScript passed. The `backend-coverage` stage then stopped
after the fixed 180-second Docker readiness window because the Docker socket
returned permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`.
No backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health, rerun pending API regressions and the
exact gate at this tip, then continue the next bounded provider/history or
compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize Study Lab fallback timestamps

Product commit `780ef1e3` closes the no-date Study Lab timeline fallback seam.
Benchmark and strategy result builders now use the shared UTC-`Z` formatter
when a run has no explicit start date; date-only request fields and timeline
key semantics remain unchanged.

Focused Study Lab coverage passed `3/3`; Ruff, formatting, and
`git diff --check` passed. The exact branch gate is pending at this coherent
product tip. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

## 2026-09-12 — Exact history worker timing gate rechecked

The exact branch-scoped gate was rerun at product tip `7d40c1d4` after the
scheduled benchmark-family history worker timing slice. Repository/workstream
validation, dependency resolution, migration checks, frontend preparation,
Ruff, formatting, and TypeScript passed. The `backend-coverage` stage then
stopped after the fixed 180-second Docker readiness window because the Docker
socket returned permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`.
No backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health, rerun pending API regressions and the
exact gate at this tip, then continue the next bounded provider/history or
compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize history worker completion time

Product commit `7d40c1d4` closes the scheduled benchmark-family history job
observability seam. The worker’s returned `completed_at` now uses the shared
UTC-`Z` formatter, preserving queue results, durable progress, retry/error
evidence, and requested-date semantics.

Focused history-worker lifecycle coverage passed `3/3`; Ruff, formatting, and
`git diff --check` passed. The exact branch gate is pending at this coherent
product tip. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

## 2026-09-12 — Exact SEC filing timing gate rechecked

The exact branch-scoped gate was rerun at product tip `5c8f3009` after the SEC
EDGAR fallback timing slice. Repository/workstream validation, dependency
resolution, migration checks, frontend preparation, Ruff, formatting, and
TypeScript passed. The `backend-coverage` stage then stopped after the fixed
180-second Docker readiness window because the Docker socket returned permission
denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health, rerun pending API regressions and the
exact gate at this tip, then continue the next bounded provider/history or
compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize SEC filing timing metadata

Product commit `5c8f3009` closes the SEC EDGAR fallback timing seam. Reconstructed
holdings now preserve `known_at` and `published_at` through the shared UTC-`Z`
formatter, keeping legal disclosure timing canonical without changing filing
identity, composition dates, route resolution, or source semantics.

Focused SEC fallback coverage passed `4/4`; Ruff, formatting, and
`git diff --check` passed. The exact branch gate is pending at this coherent
product tip. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

## 2026-09-12 — Exact paper-forward gate rechecked

The exact branch-scoped gate was rerun at product tip `530e8723` after the
paper-forward Study Lab timeline slice. Repository/workstream validation,
dependency resolution, migration checks, frontend preparation, Ruff,
formatting, and TypeScript passed. The `backend-coverage` stage then stopped
after the fixed 180-second Docker readiness window because the Docker socket
returned permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`.
No backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health, rerun pending API regressions and the
exact gate at this tip, then continue the next bounded provider/history or
compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize paper-forward Study Lab timestamps

Product commit `530e8723` closes the paper-forward monitoring timeline seam.
Monitor snapshot timestamps now use the shared UTC-`Z` formatter, keeping
repeated Study Lab observations aligned with the benchmark and Nautilus
execution contracts. Snapshot retention, equity selection, monitor status, and
forward-window semantics are unchanged.

Focused Study Lab service coverage passed `13/13`; Ruff, formatting, and
`git diff --check` passed. The exact branch gate is pending at this coherent
product tip. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

## 2026-09-12 — Exact benchmark timeline gate rechecked

The exact branch-scoped gate was rerun at product tip `2e2d7b78` after the
benchmark Study Lab timeline slice. Repository/workstream validation,
dependency resolution, migration checks, frontend preparation, Ruff,
formatting, and TypeScript passed. The `backend-coverage` stage then stopped
after the fixed 180-second Docker readiness window because the Docker socket
returned permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`.
No backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health, rerun pending API regressions and the
exact gate at this tip, then continue the next bounded provider/history or
compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize benchmark Study Lab timeline timestamps

Product commit `2e2d7b78` closes the benchmark buy-and-hold Study Lab result
seam. Position, execution-log, and equity-curve timestamps now use the shared
UTC-`Z` formatter, aligning benchmark output with the Nautilus execution
contract. Return calculations, position state, coverage semantics, and
date-only fields are unchanged.

Focused Study Lab service coverage passed `12/12`; Ruff, formatting, and
`git diff --check` passed. The exact branch gate is pending at this coherent
product tip. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

## 2026-09-12 — Canonicalize background alert timestamps

Product commit `fbf5ed08` closes the background alert notification timeline
seam. Price and indicator alert tasks now serialize their WebSocket
`triggered_at` values through the shared UTC-`Z` formatter, keeping scheduled
alerts aligned with the typed and synchronous alert contracts. Trigger
evaluation, repeat/status behavior, notification dispatch, targeting, and
alert persistence are unchanged.

Focused background-alert coverage passed `2/2`; Ruff, formatting, and
`git diff --check` passed. The exact branch gate is pending at this coherent
product tip. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

## 2026-09-12 — Exact screener timeline gate rechecked

The exact branch-scoped gate was rerun at product tip `8e406e36` after the
screener alert timeline slice. Repository/workstream validation, dependency
resolution, migration checks, frontend preparation, Ruff, formatting, and
TypeScript passed. The `backend-coverage` stage then stopped after the fixed
180-second Docker readiness window because the Docker socket returned permission
denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health, rerun pending API regressions and the
exact gate at this tip, then continue the next bounded provider/history or
compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize screener alert event timestamps

Product commit `8e406e36` closes the screener WebSocket notification timeline
seam. Screener alert events now serialize `triggered_at` through the shared
UTC-`Z` formatter, keeping browser notifications aligned with the typed alert
contracts. Alert membership, targeting, trigger semantics, and delivery
behavior are unchanged.

Focused screener-engine coverage passed `34/34`; Ruff, formatting, and
`git diff --check` passed. The exact branch gate is pending at this coherent
product tip. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

## 2026-09-12 — Exact Nautilus timestamp gate rechecked

The exact branch-scoped gate was rerun at product tip `7df2dd5c` after the
Nautilus Study Lab execution-timestamp slice. Repository/workstream validation,
dependency resolution, migration checks, frontend preparation, Ruff,
formatting, and TypeScript passed. The `backend-coverage` stage then stopped
after the fixed 180-second Docker readiness window because the Docker socket
returned permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`.
No backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health, rerun pending API regressions and the
exact gate at this tip, then continue the next bounded provider/history or
compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize Nautilus Study Lab execution timestamps

Product commit `7df2dd5c` closes the Study Lab execution-timeline seam.
Nautilus-generated trade, open-position, and equity-curve timestamps now use
the shared UTC-`Z` formatter. Backtest ordering, signal replay, position
semantics, and execution calculations are unchanged.

Focused Nautilus Study Lab coverage passed `14/14`; Ruff, formatting, and
`git diff --check` passed. The exact branch gate is pending at this coherent
product tip. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

## 2026-09-12 — Exact ETF provenance gate rechecked

The exact branch-scoped gate was rerun at product tip `e01d7dd1` after the ETF
constituent provenance slice. Repository/workstream validation, dependency
resolution, migration checks, frontend preparation, Ruff, formatting, and
TypeScript passed. The `backend-coverage` stage then stopped after the fixed
180-second Docker readiness window because the Docker socket returned permission
denied at `unix:///Users/jagnelo/.docker/run/docker.sock`. No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health, rerun pending API regressions and the
exact gate at this tip, then continue the next bounded provider/history or
compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize ETF constituent provenance timestamps

Product commit `e01d7dd1` closes the adjacent ETF holdings lineage seam.
Constituent classification enrichment and lightweight instrument materialization
now serialize observed/fetched provider timestamps through the shared UTC-`Z`
formatter before they are persisted into flattened field provenance. Holding
resolution, identity promotion, provider routing, and ETF membership semantics
are unchanged.

Focused ETF holdings resolution coverage passed `29/29`; Ruff, formatting, and
`git diff --check` passed. The exact branch gate is pending at this coherent
product tip because Docker access remains permission-denied. Restore Docker
health, rerun pending API regressions and the exact gate, then continue the next
bounded provider/history or compatible chart/list/gauge seam. No visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed.

## 2026-09-12 — Exact profile-provenance gate rechecked

The exact branch-scoped gate was rerun at product tip `e9921de8` after the
profile snapshot provenance slice. Repository/workstream validation,
dependency resolution, migration checks, frontend preparation, Ruff,
formatting, and TypeScript passed. The `backend-coverage` stage then stopped
after the fixed 180-second Docker readiness window because the Docker socket
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health outside the worktree, rerun pending API
regressions and the exact gate at this tip, then continue the next bounded
provider/history or compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize profile snapshot provenance timestamps

Product commit `e9921de8` closes the adjacent instrument-profile lineage seam.
Profile listing lifecycle fields and flattened field-provenance entries now
normalize offset-aware and legacy naive timestamps through the shared UTC-`Z`
formatter before they are persisted or reused by point-in-time consumers.
Identity, provider routing, listing semantics, and profile payload meaning are
unchanged.

Focused provider-persistence and instrument-sync metadata coverage passed
`14/14`; Ruff, formatting, and `git diff --check` passed. The exact branch gate
is pending at this new coherent product tip because Docker access remains
permission-denied. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed. Restore Docker health, rerun pending
API regressions and the exact gate, then continue the next bounded
provider/history or compatible chart/list/gauge seam.

## 2026-09-12 — Exact instrument-sync provenance gate rechecked

The exact branch-scoped gate was rerun at product tip `cc714b1b` after the
instrument-sync provenance slice. Repository/workstream validation,
dependency resolution, migration checks, frontend preparation, Ruff,
formatting, and TypeScript passed. The `backend-coverage` stage then stopped
after the fixed 180-second Docker readiness window because the Docker socket
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health outside the worktree, rerun pending API
regressions and the exact gate at this tip, then continue the next bounded
provider/history or compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize instrument-sync provenance timestamps

Product commit `cc714b1b` closes a nested provider-lineage seam in instrument
discovery and metadata sync. Listing observations plus symbol, profile, stats,
equity, currency, and futures field-provenance writes now use the shared UTC-`Z`
formatter, so later workstation reads do not inherit offset-specific
`+00:00` spellings. Provider selection, identity promotion, lifecycle decisions,
and stored evidence meaning are unchanged.

Focused instrument-sync metadata and provider-persistence coverage passed
`12/12`; Ruff, formatting, and `git diff --check` passed. The exact branch gate
is pending at this new coherent product tip because Docker access remains
permission-denied; no visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed. Restore Docker health, rerun the
pending API regressions and exact gate, then continue the next bounded
provider/history or compatible chart/list/gauge seam.

## 2026-09-12 — Exact provider-reconciliation gate rechecked

The exact branch-scoped gate was rerun at product tip `a0f9e252` after the
provider reconciliation timestamp slice. Repository/workstream validation,
dependency resolution, migration checks, frontend preparation, Ruff,
formatting, and TypeScript passed. The `backend-coverage` stage then stopped
after the fixed 180-second Docker readiness window because the Docker socket
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health outside the worktree, rerun pending API
regressions and the exact gate at this tip, then continue the next bounded
provider/history or compatible chart/list/gauge seam while preserving the six
protected visual state-oracle diffs and the no-integration/no-promotion/no-
deployment boundary.

## 2026-09-12 — Canonicalize provider reconciliation timestamps

Product commit `a0f9e252` closes the remaining provider-governance response
leak: reconciliation issue updates now serialize `resolved_at` on the shared
UTC-`Z` timeline. Issue status, resolution payload, audit identity, and admin
workflow semantics are unchanged.

The provider router suite passed `8/8`; Ruff, formatting, and `git diff --check`
passed. The exact gate remains pending at this coherent product tip. No visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed. Run the exact gate, then continue the next bounded provider/history or
compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize options-exposure computation time

Product commit `c4e933a0` closes the options analytics response-timeline gap:
the GEX/DEX exposure endpoint now emits `computed_at` through the shared UTC-
`Z` serializer. Exposure calculations, expiration selection, ladder values,
and provider semantics are unchanged.

Ruff, formatting, diff checks, module compilation, and the offset-normalization
serializer smoke passed. The focused options-exposure integration suite could
not initialize its Postgres fixture because Docker access was denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`; this is an environment
blocker, not a product assertion failure. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed. Rerun the focused
integration suite and exact gate once Docker is healthy, then continue the
next bounded provider/history or compatible chart/list/gauge seam.

## 2026-09-12 — Exact provider-observability gate rechecked

The exact branch-scoped gate was rerun at product tip `51e04a00` after the
provider observability timeline slice. Repository/workstream validation,
dependency resolution, migration checks, frontend preparation, Ruff,
formatting, and TypeScript passed. The `backend-coverage` stage then stopped
after the fixed 180-second Docker readiness window because the Docker socket
returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health outside the worktree, rerun the pending
API regressions and exact gate at this tip, then continue the next bounded
provider/history or compatible chart/list/gauge seam while preserving the six
protected visual state-oracle diffs and the no-integration/no-promotion/no-
deployment boundary.

## 2026-09-12 — Canonicalize provider observability timelines

Product commit `51e04a00` closes a provider-readiness contract gap in the
Settings/operator read models. Provider usage windows, lifecycle timestamps,
hourly/daily bucket starts, and provider-observation retention summaries now
cross the service boundary through the shared UTC-`Z` serializer. Provider
usage, retention, quota, and health semantics are unchanged; the client now
receives one stable timeline for provenance and freshness displays.

Focused provider usage/maintenance coverage passed `4/4`; the full backend
unit suite passed `1506/1506` at `68.83%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact gate is pending at this coherent product
tip. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed. Run the exact gate, then continue the next bounded
provider/history or compatible chart/list/gauge seam.

## 2026-09-12 — Exact analytics-tip gate rechecked

The exact branch-scoped gate was rerun at product tip `a959dcaf` after the
Market Map and breadth analytics timeline slice. Repository/workstream
validation, dependency resolution, migration checks, frontend preparation,
Ruff, formatting, and TypeScript passed. The `backend-coverage` stage then
stopped after the fixed 180-second Docker readiness window because the Docker
socket returned permission denied at
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health outside the worktree, rerun the pending
API regressions and exact gate at this tip, then continue the next bounded
provider/history or compatible chart/list/gauge seam while preserving the six
protected visual state-oracle diffs and the no-integration/no-promotion/no-
deployment boundary.

## 2026-09-12 — Canonicalize Market Map and breadth analytics timelines

Product commits `1607f017` and `a959dcaf` close two remaining analytics
provenance leaks. Market Map profile/cache timestamps now use the shared UTC-
`Z` serializer for provenance and cache identity, and breadth occurrence IDs
use the same canonical timeline. Offset-equivalent observations therefore keep
stable provenance and transition identities without changing map, breadth, or
member-selection semantics.

Focused Market Map coverage passed `10/10`; breadth coverage passed `28/28`;
the full backend unit suite passed `1506/1506` at `68.83%` coverage; Ruff,
formatting, and `git diff --check` passed. The exact gate remains pending at
this coherent product tip; the preceding run stopped at Docker readiness.
No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Rerun the exact gate now, then continue the next bounded
provider/history or compatible chart/list/gauge seam.

## 2026-09-12 — Exact research-timeline gate rechecked

The exact branch-scoped gate was rerun at product tip `36ed5513` after the
canonical research dataset timeline slice. Repository/workstream validation,
dependency resolution, migration checks, frontend preparation, Ruff,
formatting, and TypeScript passed. The `backend-coverage` stage then stopped
after the fixed 180-second Docker readiness window because the Docker socket
returned permission denied at `unix:///Users/jagnelo/.docker/run/docker.sock`.
No backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health outside the worktree, rerun the pending
API regressions and exact gate at this tip, then continue the next bounded
provider/history or compatible chart/list/gauge seam while preserving the six
protected visual state-oracle diffs and the no-integration/no-promotion/no-
deployment boundary.

## 2026-09-12 — Canonicalize research dataset timelines

Product commit `36ed5513` closes a Study Lab transport gap in the canonical
research dataset path. Dataset-manifest `as_of` values and all materialized
OHLCV/reference timestamp arrays now use the shared UTC-`Z` wire serializer,
covering instrument, benchmark, equal-reference, and batch datasets. Date-only
fields and immutable run semantics remain unchanged.

Focused research-router coverage passed `3/3`; the full backend unit suite
passed `1506/1506` at `68.83%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact gate remains pending at this new product
tip; Docker’s prior `/v1.55/info` HTTP 500 is recorded separately. No visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed. Rerun the exact gate when Docker is healthy, then continue the next
bounded provider/history or compatible chart/list/gauge seam.

## 2026-09-12 — Canonicalize combo-source exclusion timing

Product commit `dc1dfbcb` closes the remaining combo-watchlist source-history
timestamp leak: the point-in-time exclusion explaining that a combo definition
was not known at the requested cutoff now emits `known_at` through the shared
UTC-`Z` wire serializer. Membership selection, exclusion reasons, provider
behavior, and frontend shape are unchanged.

Focused watchlist-source coverage passed `7/7`; the full backend unit suite
passed `1505/1505` at `68.81%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact Docker-backed gate remains recorded as
blocked at the preceding options tip because `/v1.55/info` returned HTTP 500
after 180 seconds. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed. Continue the next bounded
provider/history or compatible chart/list/gauge seam and rerun the exact gate
at the next coherent tip when Docker is healthy.

## 2026-09-12 — Exact options-tip gate rechecked

The exact branch-scoped gate was rerun at product tip `6fb7ca7b` after the
typed options response-contract slice. Repository/workstream validation,
dependency resolution, migration checks, frontend preparation, Ruff,
formatting, and TypeScript all passed. The `backend-coverage` stage then
stopped after the fixed 180-second Docker readiness window because Docker
returned HTTP 500 for `/v1.55/info` on
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker health outside the worktree, rerun the pending
API regressions and exact gate at this tip, then continue the next bounded
provider/history or compatible chart/list/gauge seam while preserving the six
protected visual state-oracle diffs and the no-integration/no-promotion/no-
deployment boundary.

## 2026-09-12 — Options reads use typed canonical response contracts

Product commit `6fb7ca7b` closes the options read-boundary gap. Expiration,
chain, contract-summary, snapshot, and quote-history endpoints now use typed
provider-neutral response models; chain and quote observation timestamps emit
canonical UTC `Z` values while date fields retain their existing ISO date
shape. The frontend payload shape and provider/persistence behavior are
unchanged.

Focused options-schema coverage passed `2/2`; the full backend unit suite
passed `1504/1504` at `68.81%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact branch gate is pending at this new
product tip.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Run the exact gate, then continue the next bounded
provider/history or compatible chart/list/gauge seam while preserving the six
protected visual state-oracle diffs and the no-integration/no-promotion/no-
deployment boundary.

## 2026-09-12 — Exact history-progress gate rechecked

The exact branch-scoped gate was rerun at product tip `65e14448` after the
history-progress timestamp closure. Repository/workstream validation,
dependency resolution, migration checks, frontend dependency preparation,
Ruff, formatting, and TypeScript all passed. The gate then stopped at
`backend-coverage` after the fixed 180-second Docker readiness window because
Docker returned HTTP 500 for `/v1.55/info` on
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker Desktop health, rerun the pending API
regressions and exact gate, then continue the next bounded provider/history or
compatible chart/list/gauge seam while preserving the six protected visual
state-oracle diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — History progress uses canonical wire timestamps

Product commit `65e14448` closes a live refresh read-boundary gap. Redis bulk
fetch progress and durable watchlist refresh aggregation now publish their
`updated_at` values through the shared UTC `Z` helper, keeping worker progress,
history status, and the workstation timeline consistent without changing queue
identity, provider behavior, coverage semantics, or refresh state transitions.

Focused history-progress coverage passed `22/22`; the full backend unit suite
passed `1502/1502` at `68.76%` coverage; Ruff, formatting, and
`git diff --check` passed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending API regressions and
exact gate, then continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Analysis responses use canonical wire timestamps

Product commit `c072c91f` closes the shared analysis response boundary. A
common `AnalysisContractModel` now serializes direct `datetime` fields as
canonical UTC `Z` values across relative strength/rotation, breadth and
history, benchmark-family coverage/ratios/technicals/rankings, indicator
batches, technical snapshots, and Market Gauge responses. Date-only fields,
endpoint contracts, persistence, provider semantics, and analysis meaning are
unchanged.

Focused response-schema coverage passed `4/4`; the full backend unit suite
passed `1500/1500` at `68.74%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `c072c91f` passed
repository/workstream, dependency/migration, frontend-preparation, and
lint/type-check setup, then stopped at `backend-coverage` after 180 seconds
because Docker access was denied for
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending API regressions and
exact gate, then continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Calendar and legacy alert responses use canonical wire timestamps

Product commit `9462d4f6` closes the remaining calendar and legacy indicator
alert read boundaries. Economic-event `event_time`/`fetched_at` and legacy
indicator-alert lifecycle timestamps now serialize through the shared UTC `Z`
helper, keeping calendar, alerts, charts, and workstation consumers on one
stable timeline without changing endpoint, request, or persistence semantics.

Focused response-schema coverage passed `3/3`; the full backend unit suite
passed `1499/1499` at `68.74%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `9462d4f6` passed
repository/workstream, dependency/migration, frontend-preparation, and
lint/type-check setup, then stopped at `backend-coverage` after 180 seconds
because Docker access was denied for
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending API regressions and
exact gate, then continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Market Map responses use canonical wire timestamps

Product commit `0ab4c169` closes the remaining Market Map read boundary. Map
period bounds, cache freshness, per-cell observation times, and saved snapshot
lifecycle timestamps now serialize through the shared UTC `Z` helper. Map,
chart, and downstream source-read consumers therefore share one stable
timeline without changing grouping, metrics, coverage, cache, or provider
semantics.

Focused response-schema coverage passed `2/2`; the full backend unit suite
passed `1498/1498` at `68.64%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `0ab4c169` passed
repository/workstream, dependency/migration, frontend-preparation, and
lint/type-check setup, then stopped at `backend-coverage` after 180 seconds
because Docker access was denied for
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending API regressions and
exact gate, then continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Saved tool and Radar responses use canonical wire timestamps

Product commit `3377a8b1` closes the remaining saved-tool and Radar read
boundaries. Indicator presets, chart drawings, baskets, dashboards, and Radar
runs/detections/threads now serialize lifecycle and event timestamps through
the shared UTC `Z` helper. Nested workstation consumers therefore receive one
stable timeline without changing request models, persistence, ordering, or
Radar semantics.

Focused response-schema coverage passed `1/1`; the full backend unit suite
passed `1497/1497` at `68.63%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `3377a8b1` passed
repository/workstream, dependency/migration, frontend-preparation, and
lint/type-check setup, then stopped at `backend-coverage` after 180 seconds
because Docker access was denied for
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending API regressions and
exact gate, then continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Strategy and Study Lab responses use canonical wire timestamps

Product commit `aeddaa1e` closes the strategy response boundary. Saved
versions, runs, batches, definition summaries, and strategy coverage
instruments/universes/benchmarks now serialize lifecycle and requested-range
timestamps through the shared UTC `Z` helper. Study Lab lineage and coverage
diagnostics therefore retain one stable client timeline without changing run,
coverage, or immutable-definition semantics.

Focused strategy-schema coverage passed `1/1`; the full backend unit suite
passed `1496/1496` at `68.61%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `aeddaa1e` passed
repository/workstream, dependency/migration, frontend-preparation, and
lint/type-check setup, then stopped at `backend-coverage` after 180 seconds
because Docker `/v1.55/info` returned HTTP 500. No backend integration,
provider, browser, or visual stage ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker Desktop health and rerun the pending API
regressions and exact gate, then continue the next bounded provider/history or
compatible chart/list/gauge seam while preserving the six protected visual
state-oracle diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Instrument provenance responses use canonical wire timestamps

Product commit `aeaa8228` closes the instrument read-boundary seam. Computed
stats, field provenance, and listing effective/known/delisted timestamps now
serialize through the shared UTC `Z` helper, while already formatted text
provenance remains lossless. Top-down instrument identity and availability
consumers therefore share one stable timeline without changing lookup,
listing, or stats refresh behavior.

Focused instrument-router/schema coverage passed `9/9`; the full backend unit
suite passed `1495/1495` at `68.59%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `aeaa8228` passed
repository/workstream, dependency/migration, frontend-preparation, and
lint/type-check setup, then stopped at `backend-coverage` after 180 seconds
because Docker `/v1.55/info` returned HTTP 500. No backend integration,
provider, browser, or visual stage ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker Desktop health and rerun the pending API
regressions and exact gate, then continue the next bounded provider/history or
compatible chart/list/gauge seam while preserving the six protected visual
state-oracle diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Benchmark history and ETF holdings responses use canonical wire timestamps

Product commits `63e5baea` and `7afa32d8` close the remaining ETF-backed R1
response seams. Benchmark-family history summaries/runs and ETF adapter,
snapshot, dated-history, constituent-timeline, weight-evolution, filing, and
backfill-job responses now serialize lifecycle and point-in-time timestamps
through the shared UTC `Z` helper. Provider evidence, history scope, and
backfill state remain unchanged.

Focused benchmark-history coverage passed `26/26`; the ETF holdings schema
coverage passed `1/1`; the full backend unit suite passed `1494/1494` at
`68.59%` coverage; Ruff, formatting, and `git diff --check` passed. The exact
branch-scoped gate at `7afa32d8` passed repository/workstream,
dependency/migration, frontend-preparation, and lint/type-check setup, then
stopped at `backend-coverage` after 180 seconds because Docker `/v1.55/info`
returned HTTP 500. No backend integration, provider, browser, or visual stage
ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker Desktop health and rerun the pending alert,
indicator-batch, instrument-coverage, OHLCV, watchlist-history, workstation,
coverage, benchmark-history, and ETF-holdings API regressions plus the exact
gate, then continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Coverage and freshness responses use canonical wire timestamps

Product commit `a1b97145` closes the canonical local coverage response seam.
Instrument coverage, dataset state, local ranges, OHLCV requested/covered
ranges, and bounded missing slices now serialize through the shared UTC `Z`
helper. Readiness and provenance consumers therefore receive one stable
timeline without changing coverage assessment, lineage, adjustment, or
provider-neutral semantics.

Focused coverage-router schema/API coverage passed `13/13`; the full backend
unit suite passed `1492/1492` at `68.57%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `a1b97145` passed
repository/workstream, dependency/migration, frontend-preparation, and
lint/type-check setup, then stopped at `backend-coverage` after 180 seconds
because Docker `/v1.55/info` returned HTTP 500. No backend integration,
provider, browser, or visual stage ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker Desktop health and rerun the pending alert,
indicator-batch, instrument-coverage, OHLCV, watchlist-history, workstation,
and coverage API regressions plus the exact gate, then continue the next
bounded provider/history or compatible chart/list/gauge seam while preserving
the six protected visual state-oracle diffs and the no-integration/
no-promotion/no-deployment boundary.

## 2026-09-12 — Workstation and taxonomy responses use canonical wire timestamps

Product commit `54f08a5c` closes the persisted workstation response seam.
Workspace, tab/window, library-item, instrument-note, market-group, and
ETF-industry response timestamps now serialize through the shared UTC `Z`
helper. This keeps saved workstation state, source timing, and classification
provenance on one client wire timeline without changing persistence, ordering,
membership, or readiness semantics.

Focused workstation schema coverage passed `1/1`; the full backend unit suite
passed `1491/1491` at `68.56%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `54f08a5c` passed
repository/workstream, dependency/migration, frontend-preparation, and
lint/type-check setup, then stopped at `backend-coverage` after 180 seconds
because Docker `/v1.55/info` returned HTTP 500. No backend integration,
provider, browser, or visual stage ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker Desktop health and rerun the pending alert,
indicator-batch, instrument-coverage, OHLCV, watchlist-history, and workstation
API regressions plus the exact gate, then continue the next bounded
provider/history or compatible chart/list/gauge seam while preserving the six
protected visual state-oracle diffs and the no-integration/no-promotion/
no-deployment boundary.

## 2026-09-12 — Watchlist-history responses use canonical wire timestamps

Product commit `799db14d` closes the R1 watchlist-history response seam.
Watchlist source descriptors, member timing, coverage status, refresh
summaries, and durable refresh-run responses now serialize their timestamps
through the shared UTC `Z` helper. Market Map/workstation freshness and
point-in-time lineage therefore use one client wire timeline without changing
membership resolution, readiness semantics, queue state, or persistence.

Focused watchlist-history schema/service coverage passed `11/11`; the full
backend unit suite passed `1490/1490` at `68.54%` coverage; Ruff, formatting,
and `git diff --check` passed. The exact branch-scoped gate at `799db14d`
passed repository/workstream, dependency/migration, frontend-preparation, and
lint/type-check setup, then stopped at `backend-coverage` after 180 seconds
because Docker returned permission denied for
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending alert,
indicator-batch, instrument-coverage, OHLCV, and watchlist-history API
regressions plus the exact gate, then continue the next bounded provider/history
or compatible chart/list/gauge seam while preserving the six protected visual
state-oracle diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — OHLCV chart responses use canonical wire timestamps

Product commit `4a95aa1c` closes the core chart/history response seam.
`OHLCVBarOut` now serializes bar timestamps and derived-lineage metadata
(`ts`, `derived_at`, `source_start`, and `source_end`) through the shared UTC
`Z` helper. This keeps provider and derived bars on one stable client wire
format while preserving persisted datetime types, ordering, and transformation
semantics.

Focused OHLCV-router coverage passed `16/16`; the full backend unit suite
passed `1489/1489` at `68.53%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `4a95aa1c` passed
repository/workstream, dependency/migration, frontend-preparation, and
lint/type-check setup, then stopped at `backend-coverage` after 180 seconds
because Docker returned permission denied for
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending alert,
indicator-batch, instrument-coverage, and OHLCV API regressions plus the exact
gate, then continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Screener-alert API timestamps use the canonical wire format

Product commit `8ae68865` extends the alert-list response contract to
`ScreenerAlertOut`. Persisted `triggered_at`, `created_at`, and `updated_at`
values now pass through the shared UTC `Z` serializer, normalizing aware and
legacy naive datetimes without changing screener-alert state or ordering.

Focused alert notification/schema coverage passed `4/4`; the full backend unit
suite passed `1488/1488` at `68.53%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `8ae68865` passed
repository/workstream, dependency/migration, frontend-preparation, and
lint/type-check setup, then stopped at `backend-coverage` after 180 seconds
because Docker returned permission denied for
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending alert,
indicator-batch, and instrument-coverage API regressions plus the exact gate,
then continue the next bounded provider/history or compatible chart/list/gauge
seam while preserving the six protected visual state-oracle diffs and the
no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Alert-list API timestamps use the canonical wire format

Product commit `a466b3c3` closes the alert-list response seam. The shared
`PriceAlertOut` and `IndicatorAlertOut` schemas now serialize persisted
`triggered_at`, `created_at`, and `updated_at` values through the UTC `Z` wire
helper, normalizing aware and legacy naive datetimes without changing alert
ordering, persistence, or status semantics.

Focused alert notification/schema coverage passed `3/3`; the full backend unit
suite passed `1487/1487` at `68.53%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `a466b3c3` passed
repository/workstream, dependency/migration, frontend-preparation, and
lint/type-check setup, then stopped at `backend-coverage` after 180 seconds
because Docker returned permission denied for
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending alert,
indicator-batch, and instrument-coverage API regressions plus the exact gate,
then continue the next bounded provider/history or compatible chart/list/gauge
seam while preserving the six protected visual state-oracle diffs and the
no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Alert-history API timestamps use the canonical wire format

Product commit `1a4c1f70` closes the alert-history response boundary. The
`AlertFiringEventOut` schema now serializes persisted `fired_at` and
`created_at` values through the shared UTC `Z` wire helper, normalizing both
aware and legacy naive datetimes without changing persistence or ordering.

Focused alert notification/schema coverage passed `2/2`; the full backend unit
suite passed `1486/1486` at `68.52%` coverage; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `1a4c1f70` passed
repository/workstream, dependency/migration, frontend-preparation, and
lint/type-check setup, then stopped at `backend-coverage` after 180 seconds
because Docker returned permission denied for
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, browser, or visual stage ran.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending API regressions and
exact gate, then continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Compact alert history discloses canonical condition context

Product commit `fc0cef98` closes the remaining linked Instrument Alerts
history presentation gap. Recent firing rows now retain and display the
canonical condition snapshot, including selected outputs and both sides of an
indicator comparison, while keeping the observed trigger value visible. The
accessible row name carries the same expression and trigger context, with a
safe alert-type fallback for older or incomplete snapshots.

Focused linked-instrument coverage passed `13/13`; the full frontend Vitest
suite passed `1010/1010` across `115` files; frontend type-check and production
build passed with only the existing chunk-size warning; and `git diff --check`
passed. The exact branch-scoped gate at `fc0cef98` passed repository/workstream,
dependency/migration, frontend-preparation, and lint/type-check setup, then
stopped at `backend-coverage` after 180 seconds because Docker returned
permission denied for `unix:///Users/jagnelo/.docker/run/docker.sock`.
Docker-backed API, provider, browser, and visual stages remain pending.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Rerun the exact gate at this tip when Docker is available,
then continue the next bounded provider/history or compatible chart/list/gauge
seam while preserving the six protected visual state-oracle diffs and the
no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Alert WebSocket timestamps use the canonical wire format

Product commit `13535088` closes the final timestamp edge in the alert
delivery seam. Price and indicator `alert_triggered` WebSocket events now
serialize `triggered_at` through the shared UTC `Z` wire helper, aligning live
toast/history updates with the persisted alert and instrument timestamp
contracts.

Focused notification-engine and OneSignal coverage passed `2/2`; Ruff,
formatting, and `git diff --check` passed. The exact branch-scoped gate at
`13535088` passed git-diff, workstream validation, dependency/migration,
frontend dependency preparation, and lint/type-check setup, then stopped at
`backend-coverage` after the fixed 180-second Docker readiness window because
the Docker socket was inaccessible (`permission denied` for
`unix:///Users/jagnelo/.docker/run/docker.sock`). No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending alert,
indicator-batch, and instrument-coverage API regressions plus the exact gate at
this tip. Continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Instrument stats provenance timestamps use the canonical wire format

Product commit `7c4364a8` closes the remaining 52-week instrument-stat
provenance leak. Internally computed `week52_high` and `week52_low` metadata now
write `fetched_at` through the canonical UTC `Z` serializer, matching the
membership and data-coverage timestamp contract without changing statistic
values or refresh behavior.

Focused instrument-router coverage passed `8/8`; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `7c4364a8` passed
git-diff, workstream validation, dependency/migration, frontend dependency
preparation, and lint/type-check setup, then stopped at `backend-coverage`
after the fixed 180-second Docker readiness window because the Docker socket
was inaccessible (`permission denied` for
`unix:///Users/jagnelo/.docker/run/docker.sock`). No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending alert,
indicator-batch, and instrument-coverage API regressions plus the exact gate at
this tip. Continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Alert delivery preserves canonical indicator outputs

Product commit `7a517e3f` completes the alert-output contract across the
delivery path. Indicator firing snapshots, authenticated WebSocket events,
OneSignal payloads, and in-app alert toasts now retain the selected canonical
output on both comparison sides. Alert history consequently remains
unambiguous after an alert fires, including multi-output expressions such as
`BB [bb_upper] crosses above SMA [sma]`.

Backend alert-condition plus notification/engine coverage passed `24/24`; the
full frontend Vitest suite passed `1009/1009` across `115` files; frontend
type-check, production build, Ruff, formatting, and `git diff --check` passed.
The build emitted only the existing chunk-size warning. The exact
branch-scoped gate at `7a517e3f` passed git-diff, workstream validation,
dependency/migration, frontend dependency preparation, and lint/type-check
setup, then stopped at `backend-coverage` after the fixed 180-second Docker
readiness window because the Docker socket was inaccessible (`permission
denied` for `unix:///Users/jagnelo/.docker/run/docker.sock`). No backend
integration, provider, browser, or visual stage ran; no product assertion or
visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending alert,
indicator-batch, and instrument-coverage API regressions plus the exact gate at
this tip. Continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Instrument coverage timestamps use the canonical wire format

Product commit `41586210` closes a narrow R1/R7 contract seam at the
instrument membership and data-coverage boundaries. Membership `last_run_at`
and coverage `oldest`/`newest` timestamps now pass through the shared wire
serializer, so aware and naive backend values consistently reach clients as
canonical UTC `Z` timestamps rather than mixed ISO representations.

Focused instrument-router coverage passed `8/8`; Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at `41586210` passed
git-diff, workstream validation, dependency/migration, frontend dependency
preparation, and lint/type-check setup, then stopped at `backend-coverage`
after the fixed 180-second Docker readiness window because the Docker socket
was not accessible (`permission denied` for
`unix:///Users/jagnelo/.docker/run/docker.sock`). No backend integration,
provider, browser, or visual stage ran; no product assertion or visual-policy
failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Restore Docker access and rerun the pending alert,
indicator-batch, and instrument-coverage API regressions plus the exact gate at
this tip. Continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Instrument alert lists disclose canonical indicator outputs

Product commit `cbb34eab` completes the compact alert-list presentation seam.
The linked Instrument Alerts tool now formats saved indicator alerts through
the shared catalog series formatter, including explicit output keys and both
sides of indicator comparisons in the visible label and accessible name. A
saved Bollinger Band alert therefore remains identifiable as
`BB(20,2) [bb_upper] crosses above 100` instead of collapsing to `BB`.

Focused linked-instrument coverage passed `12/12`; the full frontend Vitest
suite passed `1008/1008` across `114` files; type-check, production build, and
`git diff --check` passed. The build emitted only the existing chunk-size
warning. The exact branch-scoped gate at `cbb34eab` passed git-diff,
workstream validation, dependency/migration, frontend dependency preparation,
and lint/type-check setup, then stopped at `backend-coverage` after the fixed
180-second Docker readiness window because `/v1.55/info` returned HTTP 500.
No backend integration, provider, browser, or visual stage ran; no product
assertion or visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. The pending alert and indicator-batch API fixtures remain
Docker-dependent. Continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Dashboard alert summaries disclose canonical indicator outputs

Product commit `5ed246df` closes the remaining alert-summary presentation gap.
The shared indicator catalog now owns series-label formatting, and the
dashboard alert widget uses it for both sides of indicator comparisons. A
multi-output alert therefore retains its explicit canonical series (for
example `BB(20,2) [bb_upper]`) in compact dashboard summaries instead of
falling back to an ambiguous indicator type. AlertsView and IndicatorPanel
reuse the same formatter, preventing those surfaces from drifting apart.

Focused catalog and dashboard coverage passed `51/51`; the full frontend
Vitest suite passed `1007/1007` across `114` files; type-check, production
build, and `git diff --check` passed. The build emitted only the existing
chunk-size warning. The exact branch-scoped gate at `5ed246df` passed
git-diff, workstream validation, dependency/migration, frontend dependency
preparation, and lint/type-check setup, then stopped at `backend-coverage`
after the fixed 180-second Docker readiness window because `/v1.55/info`
returned HTTP 500. No backend integration, provider, browser, or visual stage
ran; no product assertion or visual-policy failure was observed.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. The pending alert and indicator-batch API fixtures remain
Docker-dependent. Continue the next bounded provider/history or compatible
chart/list/gauge seam while preserving the six protected visual state-oracle
diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Alert lists disclose canonical indicator outputs

Product commit `0554789e` closes the alert-display side of the output
contract. The Alerts view and chart-side alert editor now format indicator
parameters through the shared catalog normalizer, omit the transport-only
`output` field from numeric parameter lists, and append the selected canonical
series (for example `[bb_upper]`) to the expression. This keeps normalized
single-output alerts readable and makes multi-output alert intent visible while
leaving layout and visual policy unchanged.

The full frontend Vitest suite passed `1004/1004` across `113` files;
type-check, production build, and `git diff --check` passed. The exact
branch-scoped gate at `0554789e` passed git-diff, workstream validation,
dependency/migration, frontend dependency preparation, and lint/type-check
setup, then stopped at `backend-coverage` after the fixed 180-second Docker
readiness window because `/v1.55/info` returned HTTP 500. No backend
integration, provider, browser, or visual stage ran; no product or
visual-policy failure was observed.

The next action is to restore Docker Desktop health, run the pending alert and
indicator-batch API regressions and exact gate at `0554789e`, then continue the
next bounded provider/history or compatible chart/list/gauge seam. Preserve
the six protected visual state-oracle diffs and the
no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Exact gate receipt at alert-form tip

The exact branch-scoped gate was rerun at product tip `a557ba57` after the
alert-form output-selector slice; the documentation tip before this receipt
was `3715caa4`. Git-diff, workstream validation (`30` records), dependency
resolution, migration-head/compatibility, frontend dependency preparation,
and lint/type-check setup passed. The gate then stopped at `backend-coverage`
after the fixed 180-second Docker readiness window because Docker returned
HTTP 500 for API route `/v1.55/info` on
`unix:///Users/jagnelo/.docker/run/docker.sock`. No backend integration,
provider, frontend build, browser, or visual stage ran, and no product
assertion or visual-policy failure was observed.

The alert and indicator-batch API regressions remain pending the Docker-backed
fixture. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed. The next action is to restore Docker Desktop health,
run those API regressions and the exact gate again at `a557ba57`, then continue
the next bounded provider/history or compatible chart/list/gauge seam while
preserving the six protected visual state-oracle diffs and the
no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Direct alert forms expose explicit multi-output selection

Product commit `a557ba57` completes the user-facing alert side of the
canonical indicator-output contract. Instrument Alerts and the reusable Alert
Form now expose output selectors whenever an indicator has multiple canonical
series (for example Bollinger Bands), require a selection before submission,
preserve selected outputs when editing or promoting alerts, and include the
explicit key in both indicator parameters. Single-output alerts retain the
existing canonicalization behavior.

The focused linked-instrument alert suite passed `11/11`; the full frontend
Vitest suite passed `1004/1004` across `113` files; frontend type-check and
build passed, with only the existing chunk-size warning; backend indicator
unit coverage remains `30/30`; Ruff, formatting, and `git diff --check`
passed. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed. The API regressions and exact branch-scoped gate
remain pending the Docker-backed fixture; rerun them at this product tip once
Docker health is available before advancing the next bounded seam.

The next action is to restore Docker Desktop health, run the pending alert and
indicator-batch API regressions plus the exact branch-scoped gate at product
tip `a557ba57`, then continue the next bounded provider/history or compatible
chart/list/gauge seam. Preserve the six protected visual state-oracle diffs
and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Indicator alerts require explicit multi-output selection

Product commit `d3bf41e3` closes the alert side of the canonical indicator
output contract. The `/alerts/indicator` API now rejects unnamed or invalid
outputs for multi-output indicators with actionable 422 capability errors and
normalizes single-output alerts to their canonical key. Chart Plot Library
alert promotion carries the selected output, and both alert evaluators fail
closed instead of selecting a first returned series. Existing single-output
alerts remain compatible.

Focused indicator-engine coverage passed `30/30`; focused Chart Plot Library
coverage passed `29/29`; the combined drag/drop, EasyScan, and plot-library
checks passed `49/49`; frontend type-check, Ruff, formatting, and
`git diff --check` passed. The exact branch-scoped gate at product tip
`d3bf41e3` passed repository/workstream/dependency/migration/frontend-
preparation and lint setup, then stopped at `backend-coverage` after the
180-second Docker readiness window because Docker returned HTTP 500 for
`/v1.55/info` on `unix:///Users/jagnelo/.docker/run/docker.sock`. Therefore
the alert/indicator-batch API fixtures and all later browser/visual stages
remain pending. No product assertion or visual-policy failure was observed;
no visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed.

The next action is to restore Docker Desktop health, run the pending alert and
indicator-batch API regressions plus the exact branch-scoped gate at this tip,
then continue the next bounded provider/history or compatible chart/list/gauge
seam. Preserve the six protected visual state-oracle diffs and the
no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Screener conditions fail closed on ambiguous indicator outputs

Product commit `93849ae6` extends the explicit output contract into the
canonical synchronous screener. Indicator-threshold, indicator-cross, and
price-vs-indicator conditions now refuse missing or invalid multi-output keys
instead of selecting the first returned series. The run records a structured
per-instrument exclusion with an actionable output-selection message, while
single-output and valid named-output conditions remain compatible.

Focused screener-engine coverage passed `33/33`; Ruff, formatting, and
`git diff --check` passed. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed. The Docker-backed API/integration gate
remains blocked at `backend-coverage` before later stages.

The next action is to restore Docker Desktop health, run the pending focused
indicator-batch API regressions and exact gate at this product tip, then
continue the next bounded provider/history or compatible chart/list/gauge seam.
Preserve the six protected visual state-oracle diffs and the
no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Indicator-batch API requires explicit multi-output selection

Product commit `39562441` closes the backend side of the chart/list output
contract. The canonical `/analysis/indicator-batch` endpoint now rejects a
missing or invalid output for multi-output indicators with an actionable
`explicit_indicator_output_required` or `invalid_indicator_output` response,
while single-output indicators and valid explicit selections remain compatible.
This prevents direct API callers from receiving an implicit first series.

The indicator engine unit suite passed `29/29`; Ruff and formatting checks
passed, and `git diff --check` passed. API regression coverage for missing,
valid, and invalid Bollinger Band outputs is recorded but requires the
Docker-backed integration fixture. The exact branch-scoped gate was then run at
this product tip and stopped at `backend-coverage` after the 180-second Docker
readiness window because the Docker API returned permission denied; no backend
integration, provider, browser, or visual stage ran. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

The next action is to restore Docker Desktop health, rerun the focused API
coverage and exact branch-scoped gate, then continue the next bounded
provider/history or compatible chart/list/gauge seam. Preserve the six
protected visual state-oracle diffs and the no-integration/no-promotion/
no-deployment boundary.

## 2026-09-12 — Persisted watchlist indicator columns fail closed on ambiguity

Product commit `385faf40` closes the legacy-configuration side of the R4
output contract. During watchlist hydration, an indicator column with a
missing or invalid output now renders explicit `explicit_output_required`
warnings and never asks the backend to choose a first series. Single-output
legacy columns are normalized to their canonical output key. This keeps
already-saved workspaces safe while the Chart Plot Library selector handles
new multi-output selections.

Focused chart/output coverage and the full frontend suite remained green at
`1002/1002` across `113` files; frontend type-check, repository Ruff/format
checks, and `git diff --check` passed. No backend contract, visual baseline,
mask, threshold, skip, provider, fallback, or acceptance policy changed. The
exact gate was rerun at product tip `385faf40` and stopped at
`backend-coverage` after the 180-second Docker readiness window because Docker
Desktop `/v1.55/info` returned HTTP 500; no backend integration, provider,
browser, or visual stage ran.

The next action is to restore Docker Desktop health and rerun the exact gate at
the new product tip, then continue the next bounded provider/history or
compatible chart/list/gauge seam. Preserve the six protected visual
state-oracle diffs and the no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Chart Plot Library exposes explicit multi-output selection

Product commit `1152b4e3` completes the user-facing side of the chart output
contract. Multi-output indicator rows now expose a bounded output selector
using the canonical backend keys (for example `bb_upper`, `macd`, or
`stoch_k`); the selected output persists in the chart indicator configuration
and flows through chart drags, watchlist columns, EasyScan conditions, and all
compatible promotion targets. Leaving the selector unset continues to fail
closed. Chart rendering and chart-to-chart copying remain supported.

Focused Chart Plot Library coverage passed `28/28`; the full frontend Vitest
suite passed `1002/1002` across `113` files; frontend type-check, repository
Ruff/format checks, and `git diff --check` passed. No backend contract, visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed. The exact gate was rerun at this product tip and stopped at
`backend-coverage` after the 180-second Docker readiness window because Docker
Desktop `/v1.55/info` returned HTTP 500; no backend integration, provider,
browser, or visual stage ran.

The next action is to restore Docker Desktop health and rerun the exact gate,
then continue the next bounded provider/history or compatible chart/list/gauge
seam. Preserve the six protected visual state-oracle diffs and the
no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Chart plot output contracts survive drag/drop handoffs

Product commit `72bdeea2` carries the chart indicator output contract through
drag/drop handoffs. Single-output indicators now serialize their canonical
backend output key; multi-output indicators require a valid explicit output
before they can become a watchlist numeric column or EasyScan technical
condition. Ambiguous drops fail visibly in the destination, and direct chart
rendering/chart-to-chart copying remains available. Direct chart-library
watchlist copying now includes timeframe/output in its stable column key, so
distinct output selections cannot collide.

Focused drag/drop and EasyScan coverage passed `20/20`; Chart Plot Library
coverage passed `27/27`; the full frontend Vitest suite passed `1001/1001`
across `113` files; frontend type-check, repository Ruff/format checks, and
`git diff --check` passed. No backend contract, visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed. The exact
branch-scoped gate was rerun at this product tip and again stopped at
`backend-coverage` after the 180-second Docker readiness window because
Docker Desktop `/v1.55/info` returned HTTP 500; no backend integration,
provider, browser, or visual stage ran.

The next action is to restore Docker Desktop health and rerun the exact gate,
then continue the next bounded provider/history or compatible chart/list/gauge
seam. Preserve the six protected visual state-oracle diffs and the
no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Chart plot promotion rejects ambiguous multi-output indicators

Product commit `4db5cc1d` closes a bounded R4 compatibility hole in the chart
plot library. Single-output indicators now declare their canonical backend
output when a condition is saved. Multi-output indicators (bands, channels,
MACD, stochastic, ADX, Aroon, pivots, and Ichimoku) no longer create a
condition, Boolean column, filter, scan, Market Gauge, alert, or Strategy
signal through an implicit first-output fallback; watchlist-column copying is
likewise refused until an explicit output-selection contract exists. Chart
plot rendering and chart-to-chart copying remain available.

Focused Chart Plot Library coverage passed `27/27`; the full frontend Vitest
suite passed `998/998` across `113` files; frontend type-check, repository
Ruff/format checks, and `git diff --check` passed. No backend contract, visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed. The exact branch-scoped gate was rerun at this product tip and again
stopped at `backend-coverage` after the 180-second Docker readiness window:
Docker Desktop's API returned HTTP 500 for `/v1.55/info`; no backend
integration, provider, browser, or visual stage ran.

The next action is to restore Docker Desktop health and rerun the exact gate,
then continue the next bounded provider/history or compatible chart/list/gauge
seam. Preserve the six protected visual state-oracle diffs and the
no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Study Lab structured artifacts gain threshold fan-out

Product commit `e048db09` closes the remaining Study Lab UI gap for named
artifacts in multi-output/structured runs. Finite scalar, series, and
range-center cards now expose explicit threshold targets for Boolean columns,
watchlist filters, scans, Market Gauges, alerts, and Strategy signals through
the existing lineage-preserving adapters. Cross-sectional aggregate runs remain
unchanged: scalar, Boolean, and range artifacts stay view/export-only and
aggregate series stay chart-plot-only. Invalid or non-finite observations do
not expose threshold controls.

Focused Study Lab coverage passed `30/30`; the full frontend Vitest suite
passed `997/997` across `113` files; frontend type-check, Ruff, formatting,
and diff checks passed. No backend contract, visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed. The exact gate remains
blocked by the existing Docker Desktop API failure and must be rerun at this
tip after Docker health is restored.

## 2026-09-12 — Study capability matrix matches threshold fan-out

The shared Study artifact capability matrix now describes the targets that the
workstation actually exposes. Scalar outputs advertise their direct watchlist
column plus explicit-threshold Boolean column, filter, scan, Market Gauge,
alert, and Strategy signal targets. Series and range-center outputs likewise
advertise their latest-value/center chart paths and threshold fan-out. The
cross-sectional aggregate guard remains authoritative: aggregate scalar,
Boolean, and range artifacts stay view/export-only, while aggregate series
artifacts remain chart-plot-only.

Focused Study Lab, Research Results, and capability coverage passed `68/68`,
and frontend type-check passed. No backend contract, visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed. The exact
Docker-backed gate remains queued behind the existing Docker API failure; the
next gate must run at this tip when Docker is healthy.

## 2026-09-12 — Capability-matrix exact gate remains Docker-blocked

The exact branch-scoped gate was attempted at documentation tip `f79a79aa`
(product tip `2523d757`). Dependency resolution, migration compatibility,
frontend dependency preparation, and lint/format/type-check setup completed.
The repository Docker readiness helper then waited 180 seconds and exited at
`backend-coverage` because Docker Desktop still returned HTTP 500 and could
not route to `192.168.65.7:2376`. Backend integration, provider, browser, and
visual stages did not run, so no product assertion or visual-policy failure
was observed. The next action remains a rerun at the current tip after Docker
health is restored, followed by the next provider/history or compatible
chart/list/gauge seam.

## 2026-09-12 — Aggregate Study series keep cross-sectional semantics

Product tip `60b485b3` makes cross-sectional Study Lab results explicit from
execution through promotion. Factory breadth/ranking studies persist their
`result_scope`; the isolated runner executes aggregate Study sources once over
the prepared universe; and the explicit `study_series_to_series` adapter
promotes one named finite series without replaying it per member. Research
Results and Study Lab expose aggregate chart-plot promotion only, while
scalar, Boolean, range, latest-value, and threshold coercions remain
view/export-only. The API requires the named `series` contract and preserves
source/run/output/membership lineage.

Focused runner coverage passed `3/3`, code-asset integration `1/1` with two
existing NumPy warnings, Research Results `36/36`, Study Lab `29/29`, frontend
type-check, Ruff, formatting, and diff checks. The exact elevated gate reached
backend unit coverage and passed `1,479/1,479`; backend integration then failed
for every test during shared Testcontainers setup because Docker returned HTTP
500 creating `testcontainers/ryuk:0.7.0` (Docker Desktop VM
`192.168.65.7:2376` had no route). The gate stopped at `backend-coverage`
before frontend/stack/provider/browser/visual stages, and cleanup refused
because Docker inspection was unavailable. No product assertion or visual
policy failure was observed. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed.

After Docker Desktop is healthy, rerun the exact gate, then continue the next
bounded provider/history or compatible chart/list/gauge seam. Preserve the six
protected visual state-oracle diffs and the no-integration/no-promotion/
no-deployment boundary.

## 2026-09-12 — Scalar Study outputs gain explicit threshold fan-out

Product tip `af142b1d` closes a bounded R4 compatibility gap. Finite numeric
scalar artifacts from direct or structured Study Lab runs can now be compared
with an explicit operator and threshold and promoted as immutable Boolean
conditions for watchlist columns, filters, scans, Market Gauges, alerts, or
Strategy signals. The backend validates the scalar output contract and finite
threshold, and the isolated runner applies the `scalar_target_to_boolean`
adapter per declared canonical member; source/run/output/membership lineage is
preserved and non-finite or incompatible values fail closed.

Focused runner coverage passed `114/114`, code-asset integration passed
`24/24` with two existing warnings, Research Results plus Study Lab component
coverage passed `35/35` and `28/28`, frontend type-check passed, and Ruff,
formatting, and diff checks passed. The exact elevated branch-scoped
Docker-backed gate then passed every non-visual stage at this product tip:
backend units `1,477/1,477`, backend integration `398/398`, frontend
dependency/lint/format/type-check/Vitest/build/contracts/probes,
compose/provider contracts, research-runner probes, and functional Playwright
`165` passed with `107` documented skips across `272` tests. Visual parity
completed `104` cases with `98` passes; the only six failures were the
established protected state-oracle set: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exited `1` only at `e2e-visual` after clean
branch-scoped teardown removed all containers, volumes, network, testcontainer
sessions, and four images. No visual, provider, fallback, or acceptance policy
changed; preserve those diffs and rerun the gate after the next bounded slice.

## 2026-09-12 — Exact gate after named event-filter artifact guard

The exact elevated branch-scoped Docker-backed gate was rerun at product tip
`df4c127f` after direct multi-output event filter/alert promotion adopted the
same explicit artifact-selection guard as Strategy signal promotion. All
non-visual stages passed: backend units `1,476/1,476`, backend integration
`396/396`, frontend dependency/lint/format/type-check/Vitest/build/contracts/
probes, compose/provider contracts, research-runner probes, and functional
Playwright `165` passed with `107` documented skips across `272` tests.

Visual parity completed `104` cases with `98` passes. The six failures are the
unchanged protected state-oracle set: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exited `1` only at `e2e-visual`; branch-scoped
teardown removed all containers, volumes, network, testcontainer sessions,
and four images. No visual, provider, fallback, or acceptance policy changed;
live 100k-point proof remains unclaimed.

Continue the next bounded provider/history or compatible chart/list/gauge seam,
then R1 canonical population/history breadth, W1/MN continuity, dense-data
evidence, and R2-R7 without changing protected visual policy.

## 2026-09-12 — Server-side event filter promotion requires named output

The follow-up to the named event-signal seam closes the remaining API
ambiguity. Direct multi-output `events` runs now require `artifact_name` for
filter/alert promotion as well as Strategy signal promotion; the selected
artifact and declared canonical member scope remain in the resulting adapter
lineage. The Strategy Lab integration regression covers both missing-name
rejection and a successful named filter (`27/27`, 54 warnings); Ruff,
formatting, and diff checks pass.

The exact exhaustive gate now has a recorded result at this follow-up tip (see
the gate section above). Preserve its six established visual state-oracle
diffs and unchanged acceptance policy. Continue the next bounded
provider/history or compatible chart/list/gauge seam, then R1 canonical
population/history breadth, W1/MN continuity, dense-data evidence, and R2-R7.

## 2026-09-12 — Named event-artifact promotion preserves output selection

Product tip `ea7eccf1` closes a concrete R4 fan-out ambiguity. A direct
`events` CodeVersion/run may emit multiple named event artifacts; the backend
now rejects an unnamed promotion in that case and carries the requested
`artifact_name` through the Strategy signal lineage. Research Results and
Study Lab show named filter/alert/signal controls for those runs, while
top-level actions remain limited to a single unambiguous event artifact.

Focused Research Results tests passed `34/34`; Study Lab plus capability tests
passed `30/30`; Strategy Lab integration passed `27/27` with 54 warnings;
frontend type-check, Ruff, format, and diff checks passed. The exact elevated
branch-scoped Docker gate then passed every non-visual stage: backend units
`1,476/1,476`, backend integration `395/395`, frontend dependency/lint/
format/type-check/Vitest/build/contracts/probes, compose/provider contracts,
research-runner probes, and functional Playwright `165` passed with `107`
documented skips across `272` tests. Visual parity remained `98/104`, with
only the six established protected state-oracle diffs. Branch-scoped teardown
was clean; no visual, provider, fallback, or acceptance policy changed.

Continue the next bounded provider/history or compatible chart/list/gauge seam,
then R1 canonical population/history breadth, W1/MN continuity, dense-data
evidence, and R2-R7. Preserve the unchanged visual acceptance policy and the
no-integration/no-promotion/no-deployment boundary.

## 2026-09-12 — Strategy Lab ETF visibility exact-tip gate

The exact elevated branch-scoped Docker-backed integration gate ran at product
tip `4579d1e0` after Strategy Lab static and dynamic ETF universes adopted the
shared exact controlled-fixture visibility boundary. All non-visual stages
passed: backend units `1,476/1,476`, backend integration `395/395`, frontend
dependency/lint/format/type-check/Vitest/build/contracts/probes,
compose/provider contracts, research-runner probes, and functional Playwright
`165` passed with `107` documented skips across `272`. Frontend Vitest completed
`113` files and `991` tests at `82.7%` statements.

Visual parity completed `98/104`; the six failures were exactly the established
protected state-oracle set: `watchlist-column-editor-open` at visual-1080p-100
and visual-1080p-125, plus `workspace-floating` at visual-1080p-100,
visual-1080p-125, visual-1440p-100, and visual-1440p-125. The gate exited `1`
only at `e2e-visual`; branch-scoped teardown removed all containers, volumes,
network, testcontainer sessions, and four images. No visual, provider, fallback,
or acceptance policy changed. Continue the next bounded provider/history or
compatible chart/list/gauge seam, then R1 canonical population/history breadth,
W1/MN continuity, dense-data evidence, and R2-R7 without changing protected
visual policy.

## 2026-09-12 — Strategy Lab ETF universes honor canonical fixture visibility

At product tip `4579d1e0`, Strategy Lab's static and dynamic ETF holdings
resolvers now share the exact controlled-fixture visibility boundary used by
the workstation source catalog. Normal canonical research excludes the
`controlled_fixture` + `e2e_reference` pair, while seeded browser runs select
that pair explicitly; ordinary deterministic integration fixtures using other
provider labels remain compatible.

The focused authenticated coverage-preview regression passed `1/1`; the
complete Strategy Lab integration file passed `26/26`; Ruff, formatting, and
diff checks passed; and the full backend unit suite passed `1,476/1,476` at
`68.52%` isolated coverage. The exact branch-scoped integration gate is still
pending for this product tip. No visual, provider, fallback, or acceptance
policy changed. Continue R1 provider/family history breadth, canonical
population, W1/MN continuity, dense-data evidence, and R2-R7 without changing
protected visual policy.

## 2026-09-12 — SEC fallback requires canonical materialized members

At product tip `87cc8bd2`, the ETF bootstrap SEC fallback now inspects
materialized holdings rows before deciding that a stored snapshot is sufficient
to suppress another source attempt. Complete snapshots containing only cash or
other non-equity rows, unresolved rows, or placeholder instruments no longer
block SEC N-PORT/legacy recovery; only a canonical resolved equity/security row
can satisfy the fallback's ready predicate. The existing metadata-only
`resolved_count` compatibility path remains unchanged where row detail is not
available.

The focused bootstrap regression suite passed `16/16`; Ruff, formatting, and
diff checks passed; and the full backend unit suite passed `1,476/1,476` at
`68.53%` isolated coverage. The exact elevated branch-scoped gate passed all
non-visual stages, including backend integration `391/391`, frontend
static/build/test/contracts/probes, and functional Playwright `165` passed
with `107` documented skips across `272`. Visual parity completed `99/104`,
with five failures all inside the established protected scaled
`workspace-floating` / `watchlist-column-editor-open` cases; no new visual
failure appeared. Teardown removed all branch resources and four images. No
visual, provider, fallback, or acceptance policy changed. Continue R1 provider
and family-history breadth, canonical population, W1/MN continuity, dense-data
evidence, and R2-R7 without changing protected visual policy.

## 2026-09-12 — Source availability requires canonical materialized members

At product tip `73fa0b33`, the shared ETF and benchmark-family source catalog
now uses the canonical materialized-member predicate when snapshot rows are
eagerly loaded. A positive raw `resolved_count` no longer makes a cash-only,
non-equity-only, unresolved, or placeholder-only materialization appear
available; those sources remain locked and explicitly
`holdings_snapshot_unresolved`. Legacy metadata-only snapshots retain the raw
counter compatibility path because row-level eligibility cannot be evaluated.

The focused source regressions passed `2/2`; the complete watchlist integration
file passed `53/53`; and Ruff, formatting, and diff checks passed. The full
backend unit suite passed `1,475/1,475` at `68%` isolated coverage. The exact
elevated branch-scoped gate passed all non-visual stages and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
remained `98/104` with exactly the six established protected diffs
(`watchlist-column-editor-open` at 1080p-100/125 and `workspace-floating` at
1080p-100/125 and 1440p-100/125). Teardown removed all branch resources and
four images. No visual, provider, fallback, or acceptance policy changed.
Continue R1 provider/family history breadth, canonical population, W1/MN
continuity, dense-data evidence, and R2-R7 without changing protected visual
policy.

## 2026-09-11 — Historical backfill requires canonical snapshot rows

At product tip `f3523bdd`, the benchmark-family member-history backfill planner
now selects only persisted snapshots containing at least one resolved,
non-placeholder canonical equity/security row. A positive raw `resolved_count`
without a queueable canonical row (including materialized cash-only or other
non-equity disclosures) no longer creates a misleading history candidate;
metadata-only snapshots likewise remain outside this queueable history plan.
The existing provider-neutral member queue and inclusive composition-date bound
are unchanged.

The real-Postgres backfill regression passed `1/1`; the complete benchmark
family-history service suite passed `25/25`; and Ruff, formatting, and diff
checks passed. The full backend unit suite passed `1,475/1,475` at `68%`
isolated coverage. The exact elevated branch-scoped gate passed all non-visual
stages, including backend integration `391/391`, frontend static/build/test/
contracts/probes, and functional Playwright `165` passed with `107` documented
skips across `272`. Visual parity remained `98/104` with exactly the six
established protected diffs (`watchlist-column-editor-open` at 1080p-100/125
and `workspace-floating` at 1080p-100/125 and 1440p-100/125). Teardown removed
all branch resources and four images. No visual, provider, fallback, or
acceptance policy changed. Continue R1 provider/family history breadth,
canonical population, W1/MN continuity, dense-data evidence, and R2-R7
without changing protected visual policy.

## 2026-09-11 — Bootstrap readiness requires canonical members

At product tip `a4571fdb`, core workstation bootstrap now uses the same
canonical-member readiness contract as ETF refresh: a materialized snapshot
must contain at least one resolved, non-placeholder equity member before it
can satisfy bootstrap readiness. Legacy metadata-only snapshots retain the
raw `resolved_count` compatibility path when no holding rows are present, so
existing summary metadata remains usable without allowing a non-equity-only
materialized disclosure to bootstrap the workstation.

The focused bootstrap/readiness suite passed `26/26`; Ruff, formatting, and
diff checks passed; and the full backend unit suite passed `1,475/1,475` at
`69%` isolated coverage. The exact elevated branch-scoped gate passed all
non-visual stages, including backend integration `391/391`, frontend
static/build/test/contracts/probes, and functional Playwright `165` passed
with `107` documented skips across `272`. Visual parity remained `98/104`
with exactly the six established protected diffs
(`watchlist-column-editor-open` at 1080p-100/125 and `workspace-floating` at
1080p-100/125 and 1440p-100/125). Teardown removed all branch resources and
four images. No visual, provider, fallback, or acceptance policy changed.
Continue R1 provider/family history breadth, canonical population, W1/MN
continuity, dense-data evidence, and R2-R7 without changing protected visual
policy.

## 2026-09-11 — Family coverage requires canonical snapshot members

At product tip `f3943b82`, benchmark-family coverage now treats a materialized
holdings snapshot as usable only when it contains at least one resolved,
non-placeholder canonical equity member. Raw `resolved_count` remains a
compatibility signal for legacy metadata-only snapshots that intentionally
persist summary counts without holding rows. This prevents non-equity-only
disclosures from making point-in-time family coverage appear available while
preserving older summary metadata.

The focused Docker-backed coverage regressions passed `3/3`; Ruff, formatting,
and diff checks passed; and the full backend unit suite passed `1,474/1,474` at
`68%` isolated coverage. The exact elevated branch-scoped gate passed all
non-visual stages, including backend integration `391/391` (`82.69%` combined
coverage), frontend static/build/test/contracts/probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
remained `98/104` with exactly the six established protected diffs
(`watchlist-column-editor-open` at 1080p-100/125 and `workspace-floating` at
1080p-100/125 and 1440p-100/125). Teardown removed all branch resources and
four images. No visual, provider, fallback, or acceptance policy changed.
Continue R1 provider/family history breadth, canonical population, W1/MN
continuity, dense-data evidence, and R2-R7 without changing protected visual
policy.

## 2026-09-11 — Family readiness metadata matches canonical members

At product tip `184cedd6`, benchmark-family coverage metadata readiness now
deduplicates publishable holdings by canonical instrument ID before counting
members, weights, and classifications. A duplicate disclosure therefore cannot
inflate family coverage or make a partially weighted/classified universe appear
ready. If duplicate rows disagree on weight presence, the canonical member is
weighted when any eligible disclosure supplies a weight; raw rows remain source
evidence.

The focused Docker-backed coverage regression passed `1/1`; Ruff, formatting,
and diff checks passed; and the full backend unit suite passed `1,474/1,474` at
`68%` isolated coverage. The exact elevated branch-scoped gate passed all
non-visual stages, including backend integration `391/391` (`82.69%` combined
coverage), frontend static/build/test/contracts/probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
remained `98/104` with exactly the six established protected diffs
(`watchlist-column-editor-open` at 1080p-100/125 and `workspace-floating` at
1080p-100/125 and 1440p-100/125). Teardown removed all branch resources and
four images. No visual, provider, fallback, or acceptance policy changed.
Continue R1 provider/family history breadth, canonical population, W1/MN
continuity, dense-data evidence, and R2-R7 without changing protected visual
policy.

## 2026-09-11 — Source catalog counts match canonical ETF members

At product tip `5819244d`, latest ETF and benchmark-family source descriptors
now derive `member_count` from the eagerly loaded publishable canonical
instrument IDs rather than raw `resolved_count`. This keeps the source picker
aligned with the deduplicated resolver stream while raw snapshot row and
resolved-row counts remain visible in provenance. The focused Docker-backed
source-listing/resolver regressions passed `3/3`; Ruff, formatting, and diff
checks passed. The full backend unit suite passed `1,474/1,474` with `69%`
total coverage.

The exact elevated branch-scoped gate passed every non-visual stage, including
backend integration `391/391` (`81.65%` combined coverage), frontend
dependency/lint/format/type-check/Vitest/build/contracts/probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
completed `104` cases with `98` passes and the same six established protected
state-oracle diffs: `watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. Teardown
removed all branch-scoped containers, volumes, network, testcontainer
sessions, and four images. No visual, provider, fallback, or acceptance policy
changed. Continue provider/family history breadth, remaining canonical
population, W1/MN continuity, dense-data evidence, and R2-R7 without changing
protected visual policy.

## 2026-09-11 — Canonical ETF source resolution deduplicates member IDs

At product tip `85eaf4da`, WatchlistSource resolution now emits one canonical
member per resolved instrument ID even when an issuer disclosure snapshot
contains duplicate rows. Derived equal-weight sources calculate their
denominator from unique canonical IDs; native ETF weights aggregate duplicate
disclosures. The generic ETF breadth resolver and evaluator apply the same
member-ID deduplication. Raw snapshot row counts and provenance remain source
evidence, and no provider, fallback, visual, or acceptance policy changed.

The focused Docker-backed regressions passed `2/2`; Ruff, formatting, and diff
checks passed. The full backend unit suite passed `1,474/1,474` with `69%`
total coverage. The exact elevated branch-scoped gate passed every non-visual
stage, including backend integration `391/391` (`81.65%` combined coverage),
frontend dependency/lint/format/type-check/Vitest/build/contracts/probes, and
functional Playwright `165` passed with `107` documented skips across `272`.
Visual parity completed `104` cases with `98` passes and the same six
established protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. Teardown removed all branch-scoped containers, volumes,
network, testcontainer sessions, and four images. Continue provider/family
history breadth, remaining canonical population, W1/MN continuity, dense-data
evidence, and R2-R7 without changing protected visual policy.

## 2026-09-11 — ETF resolver enforces canonical equity eligibility

At product tip `6365ec5a`, the low-level ETF constituent resolver and snapshot
reconcile predicate now share the canonical member contract used by breadth,
history, baskets, and Strategy Lab. Provider row type is normalized to
`security`, and only supported equity holding labels are eligible for
resolution or classification enrichment. Case/label variants such as
`Fixed Income` remain holdings evidence without creating or enriching a
constituent instrument. The focused resolver boundary regression passed `4/4`;
Ruff, formatting, and diff checks passed. The full backend unit suite passed
`1,474/1,474` with `69%` total coverage.

The exact elevated branch-scoped gate passed backend integration `391/391`
(`81.65%` combined coverage), all frontend dependency/lint/format/type-check/
Vitest/build/contracts/probes, and functional Playwright `165` passed with
`107` documented skips across `272`. Visual parity completed `104` cases with
`98` passes and exactly the six established protected state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125.
Teardown removed all branch-scoped containers, volumes, network,
testcontainer sessions, and four images. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed. Continue provider/
family history breadth, remaining canonical population, W1/MN continuity,
dense-data evidence, and R2-R7.

## 2026-09-11 — Classification maintenance targets canonical ETF candidates

At product tip `b504810f`, ETF classification maintenance now applies the
canonical member predicate before queueing enrichment: provider row type is
normalized to `security`, and only supported equity holding types are
eligible. Cash, derivatives, and other non-member disclosures remain source
evidence and cannot keep a snapshot's classification queue pending or distort
profile selection. The focused exclusion and bounded-maintenance regressions
passed `3/3`; Ruff, formatting, and diff checks passed. The full backend unit
suite passed `1,473/1,473` with `69%` total coverage.

The exact elevated branch-scoped gate reached all stages, with backend unit
`1,473/1,473`, backend integration `391/391` (`81.65%` combined coverage),
frontend dependency/lint/format/type-check/Vitest/build/contracts/probes
green, and functional Playwright at `164` passed plus `107` documented skips
across `272`. One first-run functional case (`F9e-easyscan-builder-keyboard`)
failed while opening the menu; the same focused test passed twice against a
fresh branch-scoped stack, so no product defect was reproducible. Visual parity
completed `104` cases with `98` passes and exactly the six established
protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. Teardown removed all branch resources and four images.
No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Continue provider/family history breadth, remaining canonical
population, W1/MN continuity, dense-data evidence, and R2-R7.

## 2026-09-11 — Strategy Lab ETF universes use canonical membership

At product tip `b131cfa6`, Strategy Lab's static and dynamic ETF universe
resolvers now share the canonical member contract used by watchlists, breadth,
and basket materialization. Provider row-type casing is normalized; only
resolved security equities with a linked non-placeholder instrument enter the
universe. Unresolved rows, non-equity disclosures, and internal `HOLDING-*`
placeholders remain evidence-only. Direct ETF ingestion also accepts provider
security-label casing variants without losing the raw audit fields. The
Docker-backed static/dynamic regression coverage passed as part of integration
`391/391`; Ruff, formatting, and diff checks passed. The full backend unit
suite passed `1,472/1,472` with `68.57%` total coverage on the repository
invocation.

The exact elevated branch-scoped gate passed every non-visual stage, including
backend integration `391/391` (`81.65%` combined coverage), frontend Vitest
`991/991`/build/contracts/probes, and functional Playwright `165` passed with
`107` documented skips across `272`. Visual parity completed `104` cases with
`98` passes and exactly the six established protected state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. The gate
exited at `e2e-visual` only for those unchanged diffs. Final branch-scoped
teardown removed all containers, volumes, network, testcontainer sessions, and
four images; only the default and desktop-linux Docker builders remained. No
visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Continue provider/family history breadth, canonical
population, W1/MN continuity, dense-data evidence, and R2-R7.

## 2026-09-11 — Enforce canonical ETF basket membership

At product tip `404a5e70`, read-only ETF holdings basket materialization now
uses the canonical member contract already shared by breadth and history
consumers. Basket members must be resolved security equities with a linked
non-placeholder instrument; provider row-type casing is normalized, while
cash, unsupported labels, unresolved rows, and internal `HOLDING-*` rows stay
in holdings evidence without entering the synthetic basket universe. The
Docker-backed mixed snapshot materialization regression passed `1/1`; Ruff,
formatting, and diff checks passed. The full backend unit suite passed
`1,472/1,472` with `69%` total coverage on the isolated invocation.

The exact elevated branch-scoped gate passed every non-visual stage, including
backend integration `389/389` (`81.56%` combined coverage), frontend Vitest
`991/991`/build/contracts/probes, and functional Playwright `165` passed with
`107` documented skips across `272`. Visual parity completed `104` cases with
`98` passes and exactly the six established protected state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. The gate
exited at `e2e-visual` only for those unchanged diffs. Final branch-scoped
teardown removed all containers, volumes, network, testcontainer sessions,
and four images; `docker buildx ls` showed only the default and desktop-linux
builders. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed. Continue provider/family history breadth, canonical
population, W1/MN continuity, dense-data evidence, and R2-R7.

## 2026-09-11 — Normalize family history queue and derived equal-weight labels

At product tip `c058eb0b`, benchmark-family history enqueue planning and the
derived equal-weight source denominator now normalize provider `row_type`
labels before applying the canonical security predicate. A `Security` spelling
therefore cannot silently drop a canonical member from queued D1/W1/MN history
or make a derived equal-weight source publish an unweighted member. The focused
queue regression and Docker-backed benchmark-family source workflow passed
`1/1` each; Ruff, formatting, and diff checks passed. The full backend unit
suite passed `1,472/1,472` with `69%` total coverage on the isolated
invocation.

The exact elevated branch-scoped gate passed every non-visual stage, including
backend unit `1,472/1,472`, integration `389/389` (`81.56%` combined
coverage), frontend Vitest `991/991`/build/contracts/probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
completed `104` cases with `98` passes and exactly the six established
protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exited `1` at `e2e-visual` only for those
unchanged diffs. Final branch-scoped teardown removed all containers, volumes,
network, testcontainer sessions, and four images; no inactive temporary builder
remained after verification. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue provider/family
history breadth, canonical population, W1/MN continuity, dense-data evidence,
and R2-R7.

## 2026-09-11 — Generic breadth consumers share canonical member eligibility

At product tip `09c7930c`, the shared generic breadth-universe resolver now
uses the canonical holding contract across breadth history, peer-reference
series, and Python/Study Lab consumers: rows must be resolved security
equities, use normalized issuer labels (including `common stock` variants),
and point to non-placeholder instruments. Family member-bar and metadata
readiness use the same normalized predicates, so issuer casing or punctuation
cannot make W1/MN or classification coverage disagree with breadth. The
focused Docker-backed historical ETF breadth regression passed `1/1`; Ruff,
formatting, and diff checks passed. The full backend unit suite passed
`1,472/1,472` with `69%` total coverage on the isolated invocation.

The exact elevated branch-scoped gate passed every non-visual stage, including
backend unit `1,472/1,472`, integration `389/389` (`81.56%` combined
coverage), frontend Vitest `991/991`/build/contracts/probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
completed `104` cases with `98` passes and exactly the six established
protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exited `1` at `e2e-visual` only for those
unchanged diffs. Final branch-scoped teardown removed all containers, volumes,
network, testcontainer sessions, and four images; no inactive temporary builder
remained after verification. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue provider/family
history breadth, canonical population, W1/MN continuity, dense-data evidence,
and R2-R7.

## 2026-09-11 — Canonical ETF source reads isolate controlled fixtures

At product tip `83bddc9a`, workstation source listing and resolution now apply
the same canonical-vs-controlled-fixture visibility boundary as Market Map,
coverage, and industry APIs. In normal mode, a newer `controlled_fixture` /
`e2e_reference` snapshot cannot replace a canonical provider disclosure; seeded
browser mode remains explicitly fixture-scoped. The real-Postgres regression
passed `1/1`; Ruff, formatting, and diff checks passed. The full backend unit
suite passed `1,472/1,472` with `68.55%` total coverage on the isolated
invocation.

The exact elevated branch-scoped gate passed every non-visual stage, including
backend unit `1,472/1,472`, integration `389/389` (`81.56%` combined
coverage), frontend Vitest `991/991`/build/contracts/probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
completed `104` cases with `98` passes and exactly the six established
protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exited `1` at `e2e-visual` only for those
unchanged diffs. Final branch-scoped teardown removed all containers, volumes,
network, testcontainer sessions, and four images; no inactive temporary builder
remained after verification. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue provider/family
history breadth, remaining canonical population, W1/MN continuity, dense-data
evidence, and R2-R7.

## 2026-09-11 — Industry drill-down excludes canonical placeholders

At product tip `699624db`, the market-groups industry composition, curated
proxy verification, and constituent drill-down paths now reject linked internal
`HOLDING-*` placeholder instruments through the shared holding exclusion
contract. A placeholder with a valid-looking industry classification therefore
cannot inflate industry coverage, proxy classifications, or constituent
results. The focused Docker-backed industry regressions passed `2/2`; Ruff,
formatting, and diff checks passed. The full backend unit suite passed
`1,472/1,472` with `68.57%` total coverage on the isolated invocation.

The exact elevated branch-scoped gate passed every non-visual stage, including
backend unit `1,472/1,472`, integration `389/389` (`81.56%` combined
coverage), frontend Vitest `991/991`/build/contracts/probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
completed `104` cases with `98` passes and exactly the six established
protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exited `1` at `e2e-visual` only for those
unchanged diffs. Final branch-scoped teardown removed all containers, volumes,
network, testcontainer sessions, and four images; no inactive temporary builder
remained after verification. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue provider/family
history breadth, remaining canonical population, W1/MN continuity, dense-data
evidence, and R2-R7.

## 2026-09-11 — Direct family breadth accepts canonical equity labels

At product tip `a1b08108`, the direct benchmark-family breadth resolver now
uses the shared supported-equity label set rather than accepting only the
literal `equity` spelling. Issuer labels such as `common stock` therefore
remain eligible while unresolved rows, placeholders, and non-security or
non-equity rows retain their explicit exclusions. The existing mixed-family
Docker-backed API regression now exercises a `common stock` member and passed
`1/1`; Ruff, formatting, and diff checks passed. The full backend unit suite
passed `1,472/1,472` with `68.57%` total coverage on the isolated invocation.

The exact elevated branch-scoped gate passed every non-visual stage, including
backend unit `1,472/1,472`, integration `389/389` (`81.56%` combined
coverage), frontend Vitest `991/991`/build/contracts/probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
completed `104` cases with `98` passes and exactly the six established
protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exited `1` at `e2e-visual` only for those
unchanged diffs. Final branch-scoped teardown removed all containers, volumes,
network, testcontainer sessions, and four images; no inactive branch-scoped
builder remained after verification. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed. Continue provider and
family history breadth, remaining canonical population, W1/MN continuity,
dense-data evidence, and R2-R7.

## 2026-09-11 — Generic ETF breadth excludes unresolved and placeholder members

At product tip `01dc3682`, the generic `etf_holdings` breadth resolver now
uses the canonical member eligibility contract: holdings must be resolved,
have a resolved instrument, point to a non-placeholder symbol, be security
rows, and use a supported equity issuer label (including `common stock` and
REIT variants). Disclosed source rows remain transparent in requested and
excluded counts, while unresolved and internal `HOLDING-*` rows become
`unresolved_member` diagnostics instead of entering the evaluated denominator.
The mixed-row Docker-backed API regression passed `1/1`; Ruff, formatting, and
diff checks passed. The full backend unit suite passed `1,472/1,472` with
`68.57%` total coverage on the isolated invocation.

The exact elevated branch-scoped gate passed every non-visual stage, including
backend unit `1,472/1,472`, integration `389/389` (`81.56%` combined
coverage), frontend Vitest `991/991`/build/contracts/probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
completed `104` cases with `98` passes and exactly the six established
protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exited `1` at `e2e-visual` only for those
unchanged diffs. Final branch-scoped teardown removed all containers, volumes,
network, testcontainer sessions, and four images; no inactive temporary builder
remained after verification. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue provider/family
history breadth, remaining canonical population, W1/MN continuity, dense-data
evidence, and R2-R7.

## 2026-09-11 — Direct family breadth excludes unresolved and placeholder members

At product tip `76de35a5`, direct benchmark-family breadth now uses the same
canonical member contract as the generic watchlist resolver and family member
history. Holdings that are unresolved, lack a resolved instrument, or point to
an internal `HOLDING-*` placeholder are excluded from breadth denominators and
reported as `unresolved_member` diagnostics. A Docker-backed API regression
proves that a mixed family snapshot counts only its two canonical rows while
retaining the placeholder exclusion in the response. The focused regression
passed `1/1`; Ruff, formatting, and diff checks passed. The full backend unit
suite passed `1,472/1,472` with `68.56%` total coverage on the isolated
invocation.

The exact elevated branch-scoped gate passed every non-visual stage, including
backend unit `1,472/1,472`, integration `389/389` (`81.56%` combined
coverage), frontend Vitest `991/991`/build/contracts/probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
completed `104` cases with `98` passes and exactly the six established
protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exited `1` at `e2e-visual` only for those
unchanged diffs. Final branch-scoped teardown removed all containers, volumes,
network, testcontainer sessions, and four images; the inactive branch-scoped
builder was removed after verification. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed. Continue provider and
family history breadth, remaining canonical population, W1/MN continuity,
dense-data evidence, and R2-R7.

## 2026-09-11 — Current readiness excludes open derived periods

At product tip `9b13e33c`, benchmark-family readiness now applies the shared
canonical OHLCV `source_end` visibility contract for current reads as well as
historical reads. Current readiness uses one wall-clock cutoff: derived W1/MN
rows are admitted only when their persisted source period is closed, while
provider observations remain visible by observation timestamp. Explicit
historical `as_of` reads retain their requested cutoff semantics, so a derived
row becomes visible once its source period is closed by that historical point
in time. The regression distinguishes these two contracts in the Docker-backed
benchmark-family readiness API test. Focused analysis/Market Map unit coverage
passed `40/40`; the Docker-backed readiness regression passed `1/1`; Ruff,
formatting, and diff checks passed. The full backend unit suite passed
`1,472/1,472` with `69%` total coverage on the isolated invocation.

The exact elevated branch-scoped gate passed every non-visual stage, including
backend unit `1,472/1,472`, integration `389/389` (`81.56%` combined
coverage), frontend Vitest `991/991`/build/contracts/probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
completed `104` cases with `98` passes and exactly the six established
protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exited `1` at `e2e-visual` only for those
unchanged diffs. Final branch-scoped teardown removed all containers, volumes,
network, testcontainer sessions, and four images; the temporary builder was
removed. `PLAYWRIGHT_HTML_OPEN=never` only suppressed the report server. No
visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Continue provider/family history breadth, canonical
population, W1/MN continuity, dense-data evidence, and R2-R7.

## 2026-09-11 — Analytics consumers exclude incomplete derived periods

At product tip `c288b2a8` (analytics implementation `9a8d9ff2`), Market Map
and analysis consumers now share the canonical OHLCV source-end visibility
contract. Bounded Market Map member and reference reads filter derived bars to
a non-null `source_end` no later than the map evaluation cutoff; analysis
truncation applies the same rule for explicit historical `as_of` reads and
current wall-clock reads. Provider rows remain visible by observation
timestamp, including the established current-snapshot behavior. This prevents
incomplete W1/MN periods from entering Market Map returns, breadth, rotation,
technical, and related analysis surfaces after canonical data has been guarded.
Focused Market Map/analysis unit coverage passed `40/40`; the Docker-backed
Market Map API regression passed `1/1`; Ruff, formatting, and diff checks
passed. The full backend unit suite passed `1,472/1,472` with `68.57%` total
coverage.

The exact elevated Docker-backed gate passed every non-visual stage, including
backend unit `1,472/1,472`, integration `389/389` (`81.56%` combined
coverage), frontend Vitest `991/991`/build/contracts/probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
completed `104` cases with `98` passes and exactly the six established
protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exited `1` at `e2e-visual` only for those
unchanged diffs. Final branch-scoped teardown removed all containers, volumes,
network, testcontainer sessions, and four images; the temporary builder was
removed. `PLAYWRIGHT_HTML_OPEN=never` only suppressed the report server. No
visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Continue provider/family history breadth, W1/MN continuity,
canonical population, dense-data evidence, and R2-R7.

## 2026-09-11 — Coverage readiness excludes incomplete derived periods

At product tip `b3f1b99c`, the canonical `/coverage/instruments/{symbol}/ohlcv`
readiness endpoint now shares the source-end visibility contract with
market-data range/latest reads. Historical requests use their requested
`end` cutoff; latest-mode requests use one wall-clock cutoff. Provider rows
remain visible by observation timestamp, while derived rows require a
non-null `source_end` no later than that cutoff. The shared predicate is
used by the coverage endpoint and market-data service, preventing readiness
and chart reads from disagreeing about incomplete W1/MN periods. Focused
coverage-router plus market-data coverage passed `37/37`; Ruff, formatting,
and diff checks passed. The full backend unit suite passed `1,470/1,470` with
`68.57%` total coverage.

The exact elevated Docker-backed gate passed every non-visual stage, including
backend unit `1,470/1,470`, integration `388/388` (`81.56%` combined
coverage), frontend Vitest `991/991`/build/contracts/probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
completed `104` cases with `98` passes and exactly the six established
protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exited `1` at `e2e-visual` only for those
unchanged diffs. Final branch-scoped teardown removed all containers,
volumes, network, testcontainer sessions, and four images; the temporary
builder was removed. `PLAYWRIGHT_HTML_OPEN=never` only suppressed the report
server. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed. Continue provider/family history breadth, W1/MN
continuity, canonical population, dense-data evidence, and R2-R7.

## 2026-09-11 — Latest coarse reads exclude incomplete derived periods

At product tip `64783149`, `fetch_ohlcv_latest` now applies one wall-clock
visibility cutoff to every canonical coarse-read branch. Provider rows remain
visible by observation timestamp; derived W1/MN rows are admitted only when
their persisted `source_end` is non-null and no later than the cutoff. The
guard covers the initial cache query, local-only materialization, provider-gap
fallback, and final coarse merge, closing the remaining latest-read leak of an
incomplete period. The focused market-data suite passed `25/25`; Ruff,
formatting, and diff checks passed. The full backend unit suite passed
`1,469/1,469` with `68.57%` total coverage.

The exact elevated Docker-backed gate passed every non-visual stage, including
backend unit `1,469/1,469`, integration `388/388` (`81.56%` combined coverage),
frontend Vitest `991/991`/build/contracts/probes, and functional Playwright
`165` passed with `107` documented skips across `272`. Visual parity completed
`104` cases with `98` passes and exactly the six established protected
state-oracle diffs: `watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. The gate
exited `1` at `e2e-visual` only for those unchanged diffs. Clean branch-scoped
teardown removed all containers, volumes, network, testcontainer sessions, and
four images; the temporary builder was removed. `PLAYWRIGHT_HTML_OPEN=never`
only suppressed the report server. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue provider/family
history breadth, W1/MN continuity, canonical population, dense-data evidence,
and R2-R7.

## 2026-09-11 — Historical coarse reads exclude incomplete derived periods

At product tip `8528205d`, canonical OHLCV history reads now require derived
W1/MN rows to be closed through the requested historical cutoff: provider rows
remain visible by observation timestamp, while derived rows are visible only
when their persisted `source_end` is non-null and no later than the cutoff.
The guard is applied consistently to range reads, cursor pagination, benchmark-
family readiness history, and generic watchlist-source history. Legacy derived
rows without a source-end are excluded from bounded historical reads rather than
silently leaking future observations. Focused market-data coverage passed
`24/24`; adjacent analysis-router and watchlist-history coverage passed
`38/38`; Ruff, formatting, and diff checks passed. The full backend unit suite
passed `1,468/1,468` with `68.56%` total coverage.

The exact elevated Docker-backed gate passed every non-visual stage, including
backend unit `1,468/1,468`, integration `388/388` (`81.56%` combined coverage),
frontend Vitest `991/991`/build/contracts/probes, and functional Playwright
`165` passed with `107` documented skips across `272`. Visual parity completed
`104` cases with `98` passes and exactly the six established protected
state-oracle diffs: `watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. The gate
exited `1` at `e2e-visual` only for those unchanged diffs. Clean branch-scoped
teardown removed all containers, volumes, network, testcontainer sessions, and
four images; the temporary cutoff builder was removed. `PLAYWRIGHT_HTML_OPEN=never`
only suppressed the report server. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed. Continue provider/family
history breadth, W1/MN continuity, canonical population, dense-data evidence,
and R2-R7.

## 2026-09-11 — Risk-free provider refreshes retain fetch-time freshness

At product tip `2cdfc3c4`, the risk-free-rate provider path now passes the
wall-clock fetch timestamp into canonical OHLCV persistence. Historical `^IRX`
or equivalent provider bar timestamps remain market-observation dates and no
longer make a successful refresh immediately appear stale in dataset state or
provider-observation lineage. The service documentation now matches the
persisted behavior. Focused risk-free-rate coverage passed `1/1`; Ruff,
formatting, and diff checks passed. The full backend unit suite passed
`1,467/1,467` with `68.55%` total coverage.

The exact elevated Docker-backed gate passed backend unit `1,467/1,467`,
integration `388/388` (`81.54%` combined coverage), frontend Vitest `991/991`/
build/contracts/probes, and functional Playwright `165` passed with `107`
documented skips across `272`. Visual parity remained `98/104` with exactly
the six established protected state-oracle diffs: `watchlist-column-editor-open`
at visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. Clean branch-scoped teardown removed all containers,
volumes, network, testcontainer sessions, and four images; the temporary
freshness builder was removed. `PLAYWRIGHT_HTML_OPEN=never` only suppressed the
report server. No visual baseline, mask, threshold, skip, provider, fallback,
or acceptance policy changed. Continue provider/family history breadth, W1/MN
continuity, canonical population, dense-data evidence, and R2-R7.

## 2026-09-11 — Dataset coverage preserves cumulative incremental history

At product tip `33738bf8`, `_touch_ohlcv_dataset_state` now normalizes fetched
bar timestamps and unions each incremental or out-of-order provider fetch with
the persisted `InstrumentDatasetState` coverage bounds. A recent fetch followed
by an older backfill therefore retains the full observed range instead of
appearing to contain only the latest response slice; freshness timestamps still
follow the newest input. The regression covers the union and UTC normalization.
Focused market-data coverage passed `23/23`; Ruff, formatting, and diff checks
passed. The full backend unit suite passed `1,467/1,467` with `68.55%` total
coverage.

The exact elevated Docker-backed gate passed backend unit `1,467/1,467`,
integration `388/388` (`81.54%` combined coverage), frontend Vitest `991/991`/
build/contracts/probes, and functional Playwright `165` passed with `107`
documented skips across `272`. Visual parity remained `98/104` with exactly the
same six established protected state-oracle diffs: `watchlist-column-editor-open`
at visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. Clean branch-scoped teardown removed all containers,
volumes, network, testcontainer sessions, and four images; the temporary
coverage-union builder was removed. `PLAYWRIGHT_HTML_OPEN=never` only suppressed
the report server. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed. Continue provider/family history
breadth, W1/MN continuity, canonical population, dense-data evidence, and R2-R7.

## 2026-09-11 — Bounded coarse fetch preserves future derived history

At product tip `fdd875d0`, bounded coarse provider fetches now constrain
deletion of derived W1/MN rows to observations at or before the requested
cutoff. A historical rebuild therefore cannot erase newer derived rows that
remain valid for later periods; unbounded refresh behavior is unchanged. The
regression covers a future derived row surviving beside the bounded provider
row. Focused bulk-fetch coverage passed `9/9`; Ruff, formatting, and diff
checks passed. The full backend unit suite passed `1,466/1,466` with `68.55%`
total coverage.

The exact elevated Docker-backed gate passed backend unit `1,466/1,466`,
integration `388/388` (`81.54%` combined coverage), frontend Vitest `991/991`/
build/contracts/probes, and functional Playwright `165` passed with `107`
documented skips across `272`. Visual parity remained `98/104` with exactly
the six established protected state-oracle diffs: `watchlist-column-editor-open`
at visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. Clean branch-scoped teardown removed all containers,
volumes, network, testcontainer sessions, and four images; the temporary
retry builder was removed. `PLAYWRIGHT_HTML_OPEN=never` only suppressed the
report server. No visual baseline, mask, threshold, skip, provider, fallback,
or acceptance policy changed. Continue provider/family history breadth, W1/MN
continuity, canonical population, dense-data evidence, and R2-R7.

## 2026-09-11 — Preserve bounded derived history beside future provider rows

At product tip `8ac6df20`, bounded W1/MN derivation now lets only provider
rows visible at the requested historical cutoff own a calendar period. A
newer provider row in the same week or month no longer suppresses the valid
historical derived observation, while unbounded provider precedence remains
unchanged. Focused derived-timeframe coverage passed `10/10`; Ruff, formatting,
and diff checks passed.

The exact elevated Docker-backed gate passed backend unit `1,465/1,465`
(`68%` unit coverage), integration `388/388` (`81.49%` combined coverage),
frontend Vitest `991/991`/build/contracts/probes, and functional Playwright
`165` passed with `107` documented skips across `272`. Visual parity remained
`98/104` with exactly the six established protected state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. Clean
branch-scoped teardown removed all containers, volumes, network, testcontainer
sessions, and four images; the temporary retry builder was removed.
`PLAYWRIGHT_HTML_OPEN=never` only suppressed the report server. No visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed. Continue provider/family history breadth, W1/MN continuity, canonical
population, dense-data evidence, and R2-R7.

## 2026-09-11 — Watchlist source versions stabilize equivalent timestamps

At product tip `44a8ef35`, watchlist membership digests and market-group/ETF
source-version strings now normalize timestamp inputs through the canonical UTC
`Z` formatter. Equivalent instants no longer create divergent cache or lineage
identities, while membership ordering, resolver cutoffs, and source semantics
remain unchanged.

Focused watchlist-source coverage passed `6/6`; Ruff, formatting, and diff
checks passed. The exact elevated Docker-backed gate passed backend unit
`1,464/1,464` with `68%` unit coverage, backend integration `388/388` with
`81.49%` combined coverage, frontend Vitest `991/991`/build/contracts/probes,
and functional Playwright `165` passed with `107` documented skips across
`272`. Visual parity remained `98/104` with exactly the six established
protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. Clean branch-scoped teardown removed all containers,
volumes, network, testcontainer sessions, and four images; the temporary retry
builder was removed. `PLAYWRIGHT_HTML_OPEN=never` only suppressed the report
server; no assertions, thresholds, baselines, masks, skips, provider,
fallback, or acceptance policy changed. Continue provider/family history
breadth, W1/MN continuity, canonical population, dense-data evidence, and R2-R7.

## 2026-09-11 — Watchlist-source provenance timestamps canonicalize to UTC

At product tip `00c3242e`, raw watchlist-source provenance now serializes
membership departure, saved-source known-at exclusions, and holdings snapshot
publication timestamps through the canonical UTC `Z` formatter. Offset-aware
and legacy naive persisted values therefore have one stable API spelling while
source membership semantics, resolver cutoffs, and version identity remain
unchanged.

Focused watchlist-source coverage passed `5/5`; the Docker-backed managed
watchlist departure-at-as-of API regression passed `1/1`; Ruff, formatting, and
diff checks passed. The exact elevated Docker-backed gate passed backend unit
`1,463/1,463` with `68%` unit coverage, backend integration `388/388` with
`81.49%` combined coverage, frontend Vitest `991/991`/build/contracts/probes,
and functional Playwright `165` passed with `107` documented skips across
`272`. Visual parity remained `98/104` with exactly the six established
protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. Clean branch-scoped teardown removed all containers,
volumes, network, testcontainer sessions, and four images; the temporary retry
builder was removed. `PLAYWRIGHT_HTML_OPEN=never` only suppressed the report
server; no assertions, thresholds, baselines, masks, skips, provider,
fallback, or acceptance policy changed. Continue provider/family history
breadth, W1/MN continuity, canonical population, dense-data evidence, and R2-R7.

## 2026-09-11 — Workstation bootstrap family-history queue bounds canonicalize to UTC

At product tip `389d3db0`, workstation bootstrap now serializes bounded
family-member history `as_of` arguments through the canonical UTC `Z` contract,
matching the benchmark-family, ETF, and watchlist queue paths. Offset-aware and
legacy naive values therefore produce one stable worker argument and canonical
job identity without changing family selection, provider routing, history
semantics, or deduplication behavior.

Focused workstation-bootstrap and benchmark-family-history coverage passed
`35/35`; Ruff, formatting, and diff checks passed. The exact elevated
Docker-backed gate passed backend unit `1,462/1,462` with `68%` unit coverage,
backend integration `388/388` with `81.49%` combined coverage, frontend Vitest
`991/991`/build/contracts/probes, and functional Playwright `165` passed with
`107` documented skips across `272`. Visual parity remained `98/104` with
exactly the six established protected state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. Clean
branch-scoped teardown removed all containers, volumes, network, testcontainer
sessions, and four images; the temporary retry builder was removed. The gate
used `PLAYWRIGHT_HTML_OPEN=never` only to suppress the report server after the
run; no assertions, thresholds, baselines, masks, skips, provider, fallback,
or acceptance policy changed. Continue provider/family history breadth, W1/MN
continuity, canonical population, dense-data evidence, and R2-R7.

## 2026-09-11 — Family-history queue bounds canonicalize to UTC

At product tips `9406a1c3` and `d8a539e9`, benchmark-family history queue
planning and the ETF/watchlist enqueue paths now share the canonical UTC `Z`
wire spelling for bounded `as_of`/history-end arguments. Legacy naive and
offset-aware values therefore produce one stable queue contract without
changing provider routing, history semantics, or job identity.

Focused family-history services, workers, and task coverage passed `58/58`;
Ruff, formatting, and diff checks passed. The exact elevated Docker-backed
gate passed backend unit `1,462/1,462` with `68%` unit coverage, backend
integration `388/388` with `81.49%` combined coverage, frontend Vitest
`991/991`/build/contracts/probes, and functional Playwright `165` passed with
`107` documented skips across `272`. Visual parity remained `98/104` with
exactly the six established protected state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. Clean
branch-scoped teardown removed all containers, volumes, network, testcontainer
sessions, and four images; the temporary retry builder was removed. No visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed. Continue provider/family history breadth, W1/MN continuity,
canonical population, dense-data evidence, and R2-R7.

## 2026-09-11 — Provider-governance provenance timestamps canonicalize to UTC

At product tip `6b3fe038`, provider status, entitlement, reconciliation,
availability, and maintenance read contracts now serialize provenance-facing
timestamps through one canonical UTC `Z` formatter. Offset-aware and legacy
naive persisted values therefore have a stable wire spelling for provider
readiness and workstation lineage consumers; provider routing, entitlement
semantics, and dataset state are unchanged.

Focused provider-governance coverage passed `17/17`; the full backend unit
suite passed `1,462/1,462` with `68.48%` unit coverage; Ruff, formatting, and
diff checks passed. The exact tip gate passed all non-visual stages, backend
integration `387/387` with `81.47%` combined coverage, frontend Vitest
`991/991`/build/contracts/probes, and functional Playwright `165` passed with
`107` documented skips across `272`. Visual parity remained `98/104` with
exactly the six established protected state-oracle diffs; clean branch-scoped
teardown removed all containers, volumes, network, testcontainer sessions,
and four images. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed. Continue provider/family history
breadth, W1/MN continuity, canonical population, dense-data evidence, and
R2-R7.

## 2026-09-11 — Instrument provenance timestamps canonicalize to UTC

At product tip `affde164`, the untyped instrument-provenance endpoint now
serializes listing lifecycle, profile/identifier/latest-price snapshot, and
dataset-state timestamps through the canonical UTC `Z` formatter. Offset-aware
and legacy naive persisted values therefore have one stable wire spelling for
diagnostics and workstation lineage consumers; identity, provider routing,
listing state, and stored provenance payloads are unchanged.

Focused instrument-router coverage passed `7/7`; the Docker-backed provenance
API regression passed `1/1`; the full backend unit suite passed `1,460/1,460`
with `68.44%` unit coverage; Ruff, formatting, and diff checks passed. The exact
tip gate passed all non-visual stages, backend integration `387/387` with
`81.47%` combined coverage, frontend Vitest `991/991`/build/contracts/probes,
and functional Playwright `165` passed with `107` documented skips across
`272`. Visual parity remained `98/104` with exactly the six established
protected state-oracle diffs; clean branch-scoped teardown removed all
containers, volumes, network, testcontainer sessions, and four images. No
visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. Continue provider/family history breadth, W1/MN continuity,
canonical population, dense-data evidence, and R2-R7.

## 2026-09-11 — Family readiness requires dated evidence

At product tip `d1f3da4d`, the benchmark-family composite readiness gate now
requires `point_in_time_supported` before a role can be reported as `ready`.
Roles with complete current-looking inputs but no dated holdings evidence remain
explicitly partial with the `point_in_time_unavailable` reason, preserving the
AC2 boundary against projecting current membership into historical readiness.

Focused analysis-router coverage passed `28/28`; the nine benchmark-family
coverage/readiness integration cases passed `9/9` with Docker; Ruff, formatting,
and diff checks passed. The first full-gate backend run lost its ephemeral
Postgres after `148` integration tests and produced `240` setup errors; a fresh
backend-coverage retry passed `1,459/1,459` unit tests and `387/387`
integration tests at `81.47%` combined coverage. The subsequent exact full gate
passed every non-visual stage: frontend dependency/lint/format/type-check,
Vitest `991/991`, build, compose/provider contracts, research-runner probes,
and functional Playwright `165` passed with `107` documented skips across
`272`. Visual parity completed `104` cases with `98` passes and exactly the six
established protected state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exited at `e2e-visual` only for those unchanged
diffs; clean branch-scoped teardown removed all containers, volumes, network,
testcontainer sessions, and four images. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed. Continue
provider/family history breadth, W1/MN continuity, canonical population,
dense-data evidence, and R2-R7 without changing protected visual or acceptance
policy.

## 2026-09-11 — Workstation bootstrap provenance gate receipt

At product tip `ee42a67c`, the exact elevated Docker-backed branch-scoped
integration gate completed every non-visual stage. Backend unit coverage passed
`1,457/1,457` (approximately `68%` total coverage); backend integration passed
`387/387` (`81.47%` combined coverage); frontend dependency, lint, format,
type-check, Vitest (`991/991`), build, compose/provider contracts, and
research-runner probes passed; and functional Playwright passed `165` cases with
`107` documented skips across `272`. Visual parity completed `104` cases with
`98` passes and exactly the six established protected state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and `workspace-floating`
at visual-1080p-100/125 and visual-1440p-100/125. The gate exited at
`e2e-visual` only for those unchanged diffs; clean branch-scoped teardown
removed all containers, volumes, network, testcontainer sessions, and four
images. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

This validates the workstation-bootstrap provenance serialization seam only.
R1 remains open for complete provider/family history breadth, W1/MN continuity
beyond the bounded lineage path, canonical population, dense-data evidence, and
R2-R7 goals; continue without integration or deployment.

## 2026-09-11 — Workstation bootstrap provenance canonicalizes to UTC

At product tip `ee42a67c`, curated workstation identity-bootstrap provenance
timestamps now use the canonical UTC `Z` wire spelling for both newly-created
identities and existing registry audit entries. Offset-aware and legacy naive
values are normalized without changing identity selection, provider bindings,
ETF profiles, taxonomy relationships, or hydration/queue behavior.

Focused workstation-bootstrap coverage passed `10/10`; Ruff, formatting, and
diff checks passed. The exact full integration gate receipt is recorded above:
all non-visual and functional stages passed, while visual parity remained
`98/104` with the six established protected diffs. R1 remains open for complete
provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, and R2-R7 evidence; continue without integration
or deployment.

## 2026-09-11 — Strategy Lab coverage timestamp gate receipt

At product tip `4f0abd68`, the exact elevated Docker-backed integration gate
completed its full branch-scoped matrix. Backend unit coverage passed
`1,456/1,456` (approximately `68%` total coverage); backend integration passed
`387/387` (`81.47%` combined coverage); frontend dependency, lint, format,
type-check, Vitest (`991/991`), build, compose/provider contracts, and
research-runner probes passed; and functional Playwright passed `165` cases with
`107` documented skips across `272`. Visual parity completed `104` cases with
`98` passes and exactly the six established protected state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and `workspace-floating`
at visual-1080p-100/125 and visual-1440p-100/125. The gate exited at
`e2e-visual` only for those unchanged diffs; clean branch-scoped teardown
removed all containers, volumes, network, testcontainer sessions, and four
images. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

This validates the coverage-timestamp slice without closing R1 or R2-R7.
Provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, dense-data evidence, and the remaining roadmap
goals remain open; continue without integration or deployment.

## 2026-09-11 — Strategy Lab coverage timestamps canonicalize to UTC

At product tip `4f0abd68`, the Strategy Lab universe-coverage envelope now
serializes per-instrument and aggregate available/requested bar timestamps
through the shared canonical UTC `Z` formatter. Offset-aware and legacy naive
database timestamps therefore have one stable wire representation alongside
the existing dynamic-universe provenance fields; coverage status, membership,
provider routing, cache semantics, and visible visual states are unchanged.

Focused Strategy Lab coverage passed `14/14`; Ruff, formatting, and diff checks
passed. The exact full integration gate has not yet been rerun for this bounded
serialization-only change. R1 remains open for complete provider/family
history breadth, W1/MN continuity beyond the bounded lineage path, canonical
population, and R2-R7 evidence; continue without integration or deployment.

## 2026-09-11 — Study Lab universe provenance gate receipt

At product tip `b460ee98`, Study Lab dynamic-universe execution logs now
serialize `universe_snapshot_known_at` and summary snapshot timestamps through
the shared canonical UTC `Z` formatter. This keeps the frontend-visible
provenance envelope stable for offset-aware and legacy naive timestamps without
changing universe membership, provider routing, fallback, or cache semantics.

Focused Study Lab service coverage passed `2/2`; the complete backend unit
suite passed `1,455/1,455` at approximately `68%` total coverage, with Ruff,
formatting, and diff checks clean. The exact elevated Docker-backed gate passed
all non-visual stages, backend integration (`387/387`, `81.46%` combined
coverage), frontend Vitest (`991/991`) and build, compose/provider contracts,
research-runner probes, and functional Playwright (`165` passed, `107`
documented skips across `272`). Visual parity remains `98/104` with exactly
the six established protected state-oracle diffs (watchlist-column-editor-open
at visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125). The gate exited at `e2e-visual` only for those unchanged
diffs; clean branch-scoped teardown removed all containers, volumes, network,
testcontainer sessions, and four images. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed.

This closes the Study Lab universe-provenance serialization seam only. Full
provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, dense-data evidence, and R2-R7 goals remain open;
continue without integration or deployment.

## 2026-09-11 — Analysis universe provenance gate retry receipt

At product tip `d46e76cd`, the remaining ETF/family constituent and breadth
universe provenance envelopes now serialize `known_at` and requested `as_of`
timestamps through the shared canonical UTC wire formatter. Point-in-time
membership selection, provider precedence, fallback boundaries, and cache
identity semantics are unchanged.

Focused analysis-router coverage passed `26/26`; the complete backend unit
suite passed `1,453/1,453` at `68%` total coverage; Ruff, formatting, and diff
checks passed. The first exact elevated Docker-backed gate had one isolated
F8u real-drag timeout (`164` passed, `107` documented skips), so the exact
gate was rerun against a fresh branch-scoped stack. The retry passed all
functional Playwright cases (`165` passed, `107` documented skips across
`272`), backend integration (`387/387`, `81.46%` combined coverage), frontend
Vitest (`991/991`), build, compose/provider contracts, and research-runner
probes. Visual parity remains `98/104` with exactly the six established
protected state-oracle diffs (watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125). The retry exited at `e2e-visual` only for those known
diffs; branch-scoped teardown removed all containers, volumes, network,
testcontainer sessions, and four images. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed.

The F8u timeout is recorded as non-reproducible on the fresh stack, not as a
product defect. This closes the analysis-universe provenance serialization
seam only. Full provider/family history breadth, W1/MN continuity beyond the
bounded lineage path, canonical population, dense-data evidence, and R2-R7
goals remain open; continue without integration or deployment.

## 2026-09-11 — Market Map provenance timestamps canonicalize to UTC

At product tip `2eecb822`, Market Map now serializes persisted profile,
membership, bar-watermark, event-watermark, and provider-policy timestamps on
the canonical UTC timeline. Equivalent offset-bearing observations therefore
retain one provenance and cache identity representation without changing source
precedence, fallback boundaries, or map calculations.

Focused Market Map coverage passed `10/10`; the complete backend unit suite
passed `1,453/1,453` at `68.26%` total coverage; Ruff, formatting, and diff
checks passed. The exact elevated Docker-backed gate passed all non-visual
stages, backend integration (`387/387`, `81.46%` combined coverage), frontend
Vitest (`991/991`) and build, and functional Playwright (`165` passed, `107`
documented skips across `272`). Visual parity completed `104` cases with `98`
passes and exactly the six established protected state-oracle diffs
(watchlist-column-editor-open at visual-1080p-100/125 and workspace-floating at
visual-1080p-100/125 and visual-1440p-100/125). The gate exited at
`e2e-visual` after clean branch-scoped teardown removed all containers,
volumes, network, testcontainer sessions, and four images. No visual baseline,
mask, threshold, skip, provider, fallback, or acceptance policy changed.

This closes the Market Map provenance serialization seam only. Full
provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, dense-data evidence, and R2-R7 goals remain open;
continue without integration or deployment.

## 2026-09-11 — Breadth occurrence timestamps canonicalize to UTC

At product tip `59357f54ec6cc3acc86e7747bd5f73ae67b3dc46`, the shared breadth
occurrence engine now normalizes offset-aware and legacy naive point timestamps
to UTC before emitting occurrence payloads and deterministic IDs. Generic and
Study Lab breadth-history consumers therefore expose one canonical timeline
without changing member eligibility or provider behavior.

Focused breadth-service coverage passed `28/28`; the complete backend unit suite
passed `1,451/1,451` at `68%` total coverage; Ruff, formatting, and diff checks
passed. The exact elevated Docker-backed gate passed all non-visual stages,
backend integration (`387/387`), frontend Vitest (`991/991`) and build, and
functional Playwright (`165` passed, `107` documented skips across `272`).
Visual parity completed `104` cases with `98` passes and exactly the six
established protected state-oracle diffs (watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125). The gate exited `1` at `e2e-visual` after clean
branch-scoped teardown removed all containers, volumes, network, testcontainer
sessions, and four images. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

This closes the breadth occurrence timestamp seam only. Full provider/family
history breadth, W1/MN continuity beyond the bounded lineage path, canonical
population, dense-data evidence, and R2-R7 goals remain open; continue without
integration or deployment.

## 2026-09-11 — Analysis provenance timestamps serialize canonically

At product tip `8c77d03459d6fc432453251730a79abdce6c4821`, analysis provenance
serialization now converts naive and offset-aware timestamps to UTC before
emitting the canonical `Z` spelling. Historical membership and cache identity
consumers therefore disclose one timeline even when an offset-bearing cutoff
reaches the analysis router.

Focused analysis-router coverage passed `26/26`; the complete backend unit suite
passed `1,450/1,450` at `68%` total coverage; Ruff, formatting, and diff checks
passed. The exact elevated Docker-backed gate passed all non-visual stages,
backend integration (`387/387`), frontend Vitest (`991/991`) and build, and
functional Playwright (`165` passed, `107` documented skips across `272`).
Visual parity completed `104` cases with `98` passes and exactly the six
established protected state-oracle diffs (watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125). The gate exited `1` at `e2e-visual` after clean
branch-scoped teardown removed all containers, volumes, network, testcontainer
sessions, and four images. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

This closes the analysis provenance serialization seam only. Full provider/family
history breadth, W1/MN continuity beyond the bounded lineage path, canonical
population, dense-data evidence, and R2-R7 goals remain open; continue without
integration or deployment.

## 2026-09-11 — Calendar-event history ranges canonicalize to UTC

At product tip `707b783906704bfb41a7460f2030d11808bf8d2c`, direct calendar
event-history queries now normalize naive and offset-aware `start`/`end`
boundaries to UTC before SQL predicates. Internal callers that bypass the HTTP
router therefore use the same canonical timeline as public calendar requests.

Focused calendar-event coverage passed `2/2`; the complete backend unit suite
passed `1,450/1,450` at `68%` total coverage; Ruff, formatting, and diff checks
passed. The exact elevated Docker-backed gate passed all non-visual stages,
backend integration (`387/387`), frontend Vitest (`991/991`) and build, and
functional Playwright (`165` passed, `107` documented skips across `272`).
Visual parity completed `104` cases with `98` passes and exactly the six
established protected state-oracle diffs (watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125). The gate exited `1` at `e2e-visual` after clean
branch-scoped teardown removed all containers, volumes, network, testcontainer
sessions, and four images. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

This closes the calendar-event history timestamp seam only. Full provider/family
history breadth, W1/MN continuity beyond the bounded lineage path, canonical
population, dense-data evidence, and R2-R7 goals remain open; continue without
integration or deployment.

## 2026-09-11 — Option quote history ranges canonicalize to UTC

At product tip `b657c2c4da537bccb915511aab1a8146cecbef37`, option quote history
now normalizes naive and offset-aware `start`/`end` values at the service edge
before provider coverage checks and persisted quote SQL. Equivalent ranges
therefore select the same UTC timeline and send canonical bounds to providers.

Focused option-history coverage passed `2/2`; the complete backend unit suite
passed `1,449/1,449` at `68%` total coverage; Ruff, formatting, and diff checks
passed. The exact elevated Docker-backed gate passed all non-visual stages,
backend integration (`387/387`), frontend Vitest (`991/991`) and build, and
functional Playwright (`165` passed, `107` documented skips across `272`).
Visual parity completed `104` cases with `98` passes and exactly the six
established protected state-oracle diffs (watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125). The gate exited `1` at `e2e-visual` after clean
branch-scoped teardown removed all containers, volumes, network, testcontainer
sessions, and four images. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

This closes the option quote-history timestamp seam only. Full provider/family
history breadth, W1/MN continuity beyond the bounded lineage path, canonical
population, dense-data evidence, and R2-R7 goals remain open; continue without
integration or deployment.

## 2026-09-11 — Synthetic basket history ranges canonicalize to UTC

At product tip `40b790db71847bc15f4ed7bfc655f670d6666379`, synthetic basket and
ratio history now normalize naive and offset-aware `start`/`end` boundaries to
UTC in both the router and service before direct SQL selection and rebasing.
Equivalent API ranges therefore use one persisted timeline instead of relying
on database/session timezone behavior.

Focused basket integration coverage passed `4/4`; the complete backend unit
suite passed `1,448/1,448` at `68%` total coverage; Ruff, formatting, and diff
checks passed. The exact elevated Docker-backed gate passed all non-visual
stages, backend integration (`387/387`), frontend Vitest (`991/991`) and build,
and functional Playwright (`165` passed, `107` documented skips across `272`).
Visual parity completed `104` cases with `98` passes and exactly the six
established protected state-oracle diffs (watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125). The gate exited `1` at `e2e-visual` after clean
branch-scoped teardown removed all containers, volumes, network, testcontainer
sessions, and four images. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

This closes the synthetic basket/ratio timestamp seam only. Full provider/family
history breadth, W1/MN continuity beyond the bounded lineage path, canonical
population, dense-data evidence, and R2-R7 goals remain open; continue without
integration or deployment.

## 2026-09-10 — OHLCV router boundaries canonicalize to UTC

At product tip `22742ac1d44966f88a9c9dbb2e28bff3fba454f0`, the chart OHLCV
router now canonicalizes naive and offset-aware `start`, `end`, and `before`
boundaries to UTC across local pagination, transformed reads, provider-backed
range reads, and local adjustment materialization. Direct local SQL predicates
and hydrated chart requests therefore use the same timeline as persisted bars
and the market-data service.

Focused OHLCV-router regressions passed `15/15`; the complete backend unit suite
passed `1,448/1,448` with `68%` total coverage; Ruff, formatting, and diff
checks passed. The exact elevated Docker-backed gate passed all non-visual
stages, backend integration (`387/387`), frontend Vitest (`991/991`) and build,
and functional Playwright (`165` passed, `107` documented skips across `272`).
Visual parity completed `104` cases with `98` passes and exactly the six
established protected state-oracle diffs (watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125). The gate exited `1` at `e2e-visual` after clean
branch-scoped teardown removed all containers, volumes, network, testcontainer
sessions, and four images. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

This closes the chart-router timestamp seam only. Full provider/family history
breadth, W1/MN continuity beyond the bounded lineage path, canonical population,
dense-data evidence, and R2-R7 goals remain open; continue without integration
or deployment.

## 2026-09-10 — Coverage request boundaries normalize to UTC

At product tip `c1f141a52c6dd296595c2b5998578cc79aac2f8d`, the instrument OHLCV
coverage endpoint now normalizes naive and offset-aware `start`/`end` request
boundaries to UTC before reversed-range validation, SQL selection,
coverage/provenance assessment, and response serialization. Equivalent ranges
expressed in non-UTC offsets therefore select the same persisted bars and
disclose one canonical request envelope.

Focused coverage-router regressions passed `11/11`; the complete backend unit
suite passed `1,446/1,446` with `68%` total coverage; Ruff, formatting, and diff
checks passed. The exact elevated Docker-backed gate passed all non-visual
stages, backend integration (`387/387`), frontend Vitest (`991/991`) and build,
and functional Playwright (`165` passed, `107` documented skips across `272`).
Visual parity completed `104` cases with `98` passes and exactly the six
established protected state-oracle diffs (watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125). The gate exited `1` at `e2e-visual` after clean
branch-scoped teardown removed all containers, volumes, network, testcontainer
sessions, and four images. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

This closes the public coverage-request timestamp seam only. Full
provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, dense-data evidence, and R2-R7 goals remain open;
continue without integration or deployment.

## 2026-09-10 — Market Map range and cache boundaries normalize to UTC

At product tip `b5b6a5f9`, Market Map now canonicalizes naive and offset-aware
timestamps to UTC across membership evaluation, custom/preset period bounds,
bar eligibility and returns, reference/source watermarks, provider snapshot
windows, and cache-key serialization. Equivalent requests expressed in
different offsets therefore select the same historical bars and cache identity
instead of depending on the database or caller timezone.

Focused Market Map regressions passed `8/8`; the complete backend unit suite
passed `1,445/1,445` with `68%` total coverage; Ruff, formatting, and diff
checks passed. The exact branch-scoped Docker gate passed all non-visual stages,
backend integration (`387/387`, `81.39%` combined coverage), frontend Vitest
(`991/991`) and build, and functional Playwright (`165` passed, `107`
documented skips across `272`). Visual parity completed `104` cases with `98`
passes and exactly the six established protected state-oracle diffs
(watchlist-column-editor-open at visual-1080p-100/125 and workspace-floating at
visual-1080p-100/125 and visual-1440p-100/125); clean branch-scoped teardown
removed the stack and four images. No visual baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed.

This closes the Market Map timestamp-boundary seam only. Full provider/family
history breadth, W1/MN continuity beyond the bounded lineage path, canonical
population, dense-data evidence, and R2-R7 goals remain open; continue without
integration or deployment.

## 2026-09-10 — Market-data range boundaries normalize at the public service edge

At product tip `36c42c43`, all public market-data range and pagination
boundaries now normalize naive and offset-aware timestamps to UTC before
provider fetches, cache-coverage checks, and latest-window calculations. This
keeps coarse-range and historical page-before reads on the same canonical
timeline as persisted bars and prevents offset-bearing API cutoffs from
drifting across provider/cache decisions.

Focused market-data regressions passed `22/22`; the complete backend unit suite
passed `1,443/1,443` with `68%` total coverage; Ruff, formatting, and diff
checks passed. The valid focused reproduction of the earlier F8r Python
Library browser failure passed `1/1`; the exact branch-scoped Docker gate then
passed all functional coverage (`165` passed, `107` documented skips across
`272`) and all non-visual stages, including backend integration (`387/387`,
`81.38%` combined coverage), frontend Vitest (`991/991`) and build. Visual
parity completed `104` cases with `98` passes and exactly the six established
protected state-oracle diffs (watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125); clean branch-scoped teardown removed the stack and four
images. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

This closes the public market-data range-boundary timestamp seam only. Full
provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, dense-data evidence, and R2-R7 goals remain open;
continue without integration or deployment.

## 2026-09-10 — Market-data cutoff normalization completes the R1 timestamp seam

At product tip `2f07b17f`, the shared market-data timestamp helper now
canonicalizes both naive and offset-aware values to UTC before bar cutoff
comparisons. Historical OHLCV consumers therefore evaluate API and persisted
timestamps on one timeline instead of preserving a non-UTC offset.

Focused market-data regressions passed `22/22`; the complete backend unit suite
passed `1,443/1,443` with `68%` total coverage; Ruff, formatting, and diff
checks passed. The exact branch-scoped Docker gate passed all non-visual stages,
backend integration (`387/387` with `81.38%` combined coverage), frontend
Vitest (`991/991`) and build, and functional Playwright (`165` passed, `107`
documented skips across `272`). Visual parity completed `104` cases with `98`
passes and exactly the six protected state-oracle diffs (watchlist-column-
editor-open at visual-1080p-100/125 and workspace-floating at
visual-1080p-100/125 and visual-1440p-100/125); the gate exited `1` at
`e2e-visual` after clean branch-scoped teardown. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

This closes the shared market-data timestamp seam only. Full provider/family
history breadth, W1/MN continuity beyond the bounded lineage path, canonical
population, dense-data evidence, and R2-R7 goals remain open; continue without
integration or deployment.

## 2026-09-10 — Watchlist history cutoffs normalize across source and bar reads

At product tip `7b5069f7`, the remaining watchlist historical timestamp seams
now normalize to UTC at the resolver boundary: market-group membership
effective/known timestamps and watchlist-history OHLCV bar queries share one
canonical evaluation cutoff, including offset-aware API values.

Focused watchlist-source/history coverage passed `14/14`; the complete backend
unit suite passed `1,442/1,442` with `68%` total coverage; Ruff, formatting,
and diff checks passed. The exact branch-scoped Docker gate passed all
non-visual stages, backend integration (`387/387`), frontend Vitest
(`991/991`) and build, and functional Playwright (`165` passed, `107`
documented skips across `272`). Visual parity completed `104` cases with `98`
passes and exactly the six protected state-oracle diffs (watchlist-column-
editor-open at visual-1080p-100/125 and workspace-floating at
visual-1080p-100/125 and visual-1440p-100/125); the gate exited `1` at
`e2e-visual` after clean branch-scoped teardown. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

This closes the remaining direct watchlist source/bar cutoff seam only. Full
provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, dense-data evidence, and R2-R7 goals remain open;
continue without integration or deployment.

## 2026-09-10 — Watchlist source cutoffs normalize across membership and holdings

At product tip `7b3990b1`, the shared watchlist-source resolver now normalizes
historical cutoffs and persisted timestamps to UTC for watchlist membership
intervals, saved explicit-source knowledge, combo definitions, and benchmark/
ETF holdings snapshot selection. Offset-less and non-UTC aware values therefore
use one point-in-time timeline across the remaining source-resolution seam.

Focused watchlist-source/history coverage passed `12/12`; the complete backend
unit suite passed `1,440/1,440` with `68%` total coverage; Ruff, formatting, and
diff checks passed. The exact branch-scoped Docker gate passed all non-visual
stages, backend integration (`387/387`), frontend Vitest (`991/991`) and build,
and functional Playwright (`165` passed, `107` documented skips across `272`).
Visual parity completed `104` cases with `98` passes and exactly the six
protected state-oracle diffs (watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125); the gate exited `1` at `e2e-visual` after clean
branch-scoped teardown. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

This closes the shared source-resolution timestamp seam only. Full
provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, dense-data evidence, and R2-R7 goals remain open;
continue without integration or deployment.

## 2026-09-10 — Historical analysis cutoffs normalize across consumers

At product tip `9fcbd55c`, analysis bar truncation, technical snapshots,
industry-proxy snapshots, ETF constituent snapshots, family member history,
and concentration history now compare persisted timestamps against a canonical
UTC cutoff. Offset-less API values and non-UTC aware values therefore follow
one timeline instead of raising naive/aware errors or relying on database
timezone coercion.

The focused analysis/taxonomy regression suite passed `42/42`; the complete
backend unit suite passed `1,438/1,438` with `68%` total coverage; Ruff,
formatting, and diff checks passed. The exact branch-scoped Docker gate passed
all non-visual stages, backend integration (`387/387`), and functional
Playwright (`165` passed, `107` documented skips across `272`). Visual parity
completed `104` cases with `98` passes and exactly the six protected
state-oracle diffs (watchlist-column-editor-open at visual-1080p-100/125 and
workspace-floating at visual-1080p-100/125 and visual-1440p-100/125); the gate
exited `1` at `e2e-visual` after clean branch-scoped teardown. No visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed.

This closes one cross-consumer historical timestamp seam only. Full
provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, dense-data evidence, and R2-R7 goals remain open;
continue without integration or deployment.

## 2026-09-10 — Historical industry classification honors fetch cutoff

At product tip `3ab0d18c`, dated ETF industry and constituent reads now require
profile snapshots to prove both `observed_at` and non-null `fetched_at` at or
before the normalized UTC `as_of` cutoff. Holdings cutoffs use the same UTC
normalization, and source classification accepts offset-less API cutoffs
without mixing naive and aware timestamps. A profile observed before a
historical date but fetched after it can no longer leak future classification
into a dated response.

The focused taxonomy/router regression suite passed `41/41`; the complete
backend unit suite passed `1,437/1,437` with `68%` total coverage; Ruff,
formatting, and diff checks passed. The exact branch-scoped Docker gate passed
all non-visual stages, backend integration (`387/387` with `81.36%` combined
coverage), and functional Playwright (`165` passed, `107` documented skips
across `272`). Visual parity completed `104` cases with `98` passes and exactly
the six protected state-oracle diffs (watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125); the gate exited `1` at `e2e-visual` after clean
branch-scoped teardown. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

This closes one historical classification fetch-time seam only. Full
provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, dense-data evidence, and R2-R7 goals remain open;
continue without integration or deployment.

## 2026-09-10 — Historical coarse-timeframe factor proof honors fetch cutoff

At product tip `b35d5f5e`, dated W1/MN materialization now requires both
`coverage_end` and `fetched_at` temporal proof before inheriting a D1 factor
version. Missing or future fetch proof leaves the historical coarse-timeframe
state without an inherited factor version instead of projecting later evidence
backwards; unbounded/latest materialization behavior is unchanged.

The focused derived-timeframe regression suite passed `9/9`; the complete
backend unit suite passed `1,435/1,435` with `68%` total coverage; Ruff,
formatting, and diff checks passed. The exact branch-scoped Docker gate passed
all non-visual stages and functional Playwright (`165` passed, `107` documented
skips across `272`). Visual parity completed `104` cases with `98` passes and
exactly the six protected state-oracle diffs (watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125); the gate exited `1` at `e2e-visual` after clean
branch-scoped teardown. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

This closes one bounded historical factor-provenance seam only. Full
provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, dense-data evidence, and R2-R7 goals remain open;
continue without integration or deployment.

## 2026-09-10 — Coverage resolution honors explicit lineage-key precedence

At product tip `edce3e824`, range coverage now orders persisted dataset state by
the caller's explicit `dataset_keys` precedence before applying recency. A
lineage-specific key such as `D1:adj:local_split_ratio` therefore cannot be
silently shadowed by the generic `D1:adj` fallback when both are present; the
existing conservative temporal checks remain unchanged.

The focused coverage-router suite passed `10/10`; the complete backend unit
suite passed `1,433/1,433` at `68.00%`; Ruff, formatting, and diff checks
passed. The exact branch-scoped Docker gate passed all non-visual stages and
functional Playwright (`165` passed, `107` documented skips across `272`).
Visual parity remains `98/104` with exactly the six protected state-oracle
diffs (watchlist-column-editor-open at visual-1080p-100/125 and
workspace-floating at visual-1080p-100/125 and visual-1440p-100/125); the gate
exited `1` at `e2e-visual` after clean branch-scoped teardown. No visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed.

This closes one bounded coverage-state precedence seam only. Full
provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, dense-data evidence, and R2-R7 goals remain open;
continue without integration or deployment.

## 2026-09-10 — Range coverage factor provenance honors requested end

At product tip `64bb8829`, the range coverage endpoint now bounds factor-state
projection by the requested inclusive `end`: persisted factor state must carry
both `coverage_end` and `fetched_at`, and both must be no later than that end.
Rows without temporal proof remain conservatively unavailable, so a later
provider/local factor version cannot be projected into an earlier coverage
window.

Focused coverage/watchlist/family regression coverage passed `20/20`; the
complete backend unit suite passed `1,432/1,432` at `68.00%`; Ruff, formatting,
and diff checks passed. The exact branch-scoped Docker gate passed all
non-visual stages and functional Playwright (`165` passed, `107` documented
skips across `272`). Visual parity remains `98/104` with exactly the six
protected state-oracle diffs (watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125); the gate exited `1` at `e2e-visual` after clean
branch-scoped teardown. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

This closes the adjacent range-coverage point-in-time provenance seam only.
Full provider/family history breadth, W1/MN continuity beyond the bounded
lineage path, canonical population, dense-data evidence, and R2-R7 goals remain
open; continue without integration or deployment.

## 2026-09-10 — Historical factor evidence honors `as_of`

At product tip `a8b7d304`, generic watchlist and benchmark-family history now
pass dated `as_of` cutoffs into factor-evidence resolution. Persisted state is
accepted only when its `coverage_end` and `fetched_at` are present and do not
extend beyond the requested cutoff; future or unverifiable state is treated as
absent, so historical responses remain conservative instead of projecting a
later factor version/status backwards. Legacy four-field test doubles remain
compatible while production queries select the temporal state fields.

The focused historical-cutoff regression and adjacent family-history check
passed `11/11`; the complete backend unit suite passed `1,431/1,431` at
`68.00%`; Ruff, formatting, and diff checks passed. The exact branch-scoped
Docker gate passed all non-visual stages and functional Playwright (`165`
passed, `107` documented skips across `272`). Visual parity remains `98/104`
with exactly the six protected state-oracle diffs (watchlist-column-editor-open
at visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125); the gate exited `1` at `e2e-visual` after clean scoped
teardown. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

This closes the bounded point-in-time factor-evidence seam only. Full
provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, dense-data evidence, and R2-R7 goals remain open;
continue without integration or deployment.

## 2026-09-10 — Benchmark-family history exposes factor lineage

At product tip `78d1e042`, benchmark-family member history now selects and
groups `OHLCVBar.derivation_method`, retains the per-member derived methods,
and reads method-specific D1 state for both `local_split_ratio` and
`provider_adjustment_factor`. Family adjustment provenance therefore exposes
verified factor version/status when the covered bars carry that lineage, while
missing, mixed, or incomplete evidence remains conservative and provider rows
remain distinct.

The focused family-history regression passed `1/1`; the complete backend unit
suite passed `1,430/1,430` at `67.98%`; Ruff, formatting, and diff checks
passed. The exact branch-scoped Docker gate passed its non-visual stages and
functional Playwright (`165` passed, `107` documented skips across `272`).
Visual parity remains `98/104` with exactly the six protected state-oracle
diffs (watchlist-column-editor-open at visual-1080p-100/125 and
workspace-floating at visual-1080p-100/125 and visual-1440p-100/125); the gate
exited `1` at `e2e-visual` after clean scoped teardown. No visual baseline,
mask, threshold, skip, provider, fallback, or acceptance policy changed.

This closes the family member factor-lineage display seam only. Full
provider/family history breadth, W1/MN continuity beyond the bounded lineage
path, canonical population, dense-data evidence, and R2-R7 goals remain open;
continue without integration or deployment.

## 2026-09-10 — D1 history exposes local provider-factor lineage

At product tip `7eb10de1`, generic watchlist source-history status now reads
method-specific D1 derived state (`D1:adj:local_split_ratio` and
`D1:adj:provider_adjustment_factor`) and associates it with the derived rows
that are actually covered. This preserves a verified factor version/status for
local provider-adjusted D1 history instead of collapsing it to unavailable;
provider-source state remains separate, and mixed or incomplete evidence stays
conservative. Focused watchlist-history coverage passed `9/9`; the full backend
unit suite passed `1,429/1,429` with `67.88%` coverage; Ruff, formatting, and
diff checks passed.

The exact branch-scoped gate passed backend integration `387/387`, frontend
Vitest/type-check/build, uPlot and visual-policy checks, compose/health/
performance checks, and functional Playwright (`165` passed, `107` documented
skips across `272`). Visual parity remains `98/104` with exactly the six
protected state-oracle diffs (`watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125); the gate exited `1` at `e2e-visual` after clean
branch-scoped teardown. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

This closes the D1 local-factor history display seam only. Full provider/family
history breadth, W1/MN continuity beyond the bounded lineage path, canonical
population, and dense-data evidence remain open; continue without integration
or deployment.

## 2026-09-10 — Explicit provider-factor precedence

At product tip `58dd6926`, explicit provider-factor materialization now has
deterministic precedence when a local split-derived row already occupies the
same symbol/timeframe/timestamp. Provider rows remain immutable; a
`provider_adjustment_factor` row upgrades an existing `local_split_ratio`
derived row, while the split-only path cannot downgrade provider-factor
materialization or overwrite unrelated derived lineage. Focused adjustment-
factor coverage passed `19/19`; the full backend unit suite passed `1,428/1,428`
with `67.87%` coverage; Ruff, formatting, and diff checks passed.

The exact branch-scoped gate passed backend integration `387/387`, frontend
Vitest/type-check/build, uPlot and visual-policy checks, compose/health/
performance checks, and functional Playwright (`165` passed, `107` documented
skips across `272`). Visual parity remains `98/104` with exactly the six
protected state-oracle diffs (`watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125); the gate exited `1` at `e2e-visual` after clean
branch-scoped teardown. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

This closes the precedence seam for explicit provider factors only. Provider/
family history breadth, W1/MN continuity beyond the bounded lineage path,
canonical population, and dense-data evidence remain open; continue without
integration or deployment.

## 2026-09-10 — Explicit provider-factor materialization and lineage

At product tip `dc71bf6c`, the authenticated OHLCV API now exposes an explicit
`POST /ohlcv/{symbol}/{timeframe}/materialize-local-provider` route. It reads
persisted provider-supplied adjustment factors, applies the dedicated
adjusted/raw multiplier contract (prices/VWAP multiply; volume scales
inversely), and persists provider-neutral `provider_adjustment_factor`
derived rows without replacing provider rows. Missing, invalid, mixed-kind,
mixed-version, amount-only, and ambiguous source evidence remains structured
and opaque; no provider convention is inferred.

Coverage lineage and D1-to-W1/MN provenance now recognize the provider-factor
derived state while retaining point-in-time checks and the existing split-only
rebuilder. Focused materialization/lineage coverage passed `53/53`; the full
backend unit suite passed `1,427/1,427` with `67.86%` coverage; Ruff,
formatting, and diff checks passed. The exact branch-scoped gate passed backend
integration `387/387`, frontend Vitest/type-check/build, uPlot and
visual-policy checks, compose/health/performance checks, and functional
Playwright (`165` passed, `107` documented skips across `272`). Visual parity
remains `98/104` with exactly the six protected state-oracle diffs
(`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125); the
gate exited `1` at `e2e-visual` after clean branch-scoped teardown. No visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed.

This closes the bounded provider-factor materialization seam only. Provider/
family history breadth, W1/MN continuity beyond the bounded lineage path,
canonical population, and dense-data evidence remain open; preserve the six
protected visual assertions and continue without integration or deployment.

## 2026-09-10 — Explicit provider-factor application contract

At product tip `2f3e59c6`, the adjustment-factor service now has a pure
`rebuild_provider_adjusted_bars` path for persisted `factor_kind=provider_supplied`
observations. Its contract is explicit: the provider factor is an
adjusted/raw price multiplier for bars strictly before the event, so prices and
VWAP are multiplied and volume is scaled inversely. This remains separate from
the split-only rebuilder, which uses reciprocal raw split ratios. Missing,
non-positive, mixed-kind, mixed-version, and amount-only evidence returns an
opaque structured result; no provider convention is inferred and raw/provider
rows are not mutated.

Focused adjustment-factor coverage passed `17/17`; the full backend unit suite
passed `1,422/1,422` with `67.85%` coverage against the configured `55%`
threshold; Ruff, formatting, and diff checks passed. The exact branch-scoped
gate then passed backend integration `387/387`, frontend Vitest/type-check/
build, uPlot and visual-policy checks, compose/health/performance checks, and
functional Playwright (`165` passed, `107` documented skips across `272`).
Visual parity remained `98/104` with exactly the six protected state-oracle
diffs (`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125); the
gate exited `1` at `e2e-visual` after clean branch-scoped teardown. No visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed.

This is the bounded R1 factor-application/rebuild seam only; provider-factor
materialization, family/provider history, W1/MN continuity beyond the bounded
path, canonical population, and dense-data evidence remain open. Preserve the
six protected visual assertions and continue without integration or deployment.

## 2026-09-10 — Bounded historical coarse-timeframe materialization

At product tip `cacdeb4e`, dated bulk-history fetches now pass their inclusive
UTC cutoff into W1/MN materialization. D1 source rows are filtered through that
cutoff; only derived coarse rows through the cutoff are replaced; newer local
derived cache rows and their state metadata are preserved; and factor
provenance is certified only when its provider/local evidence also ends within
the requested historical range. The unbounded path retains normal latest-cache
behavior, provider-period precedence is unchanged, and no prices, bars,
routing, fallback, layout, pixels, or acceptance policy changed.

The focused derived-timeframe/bulk-fetch regression set passed `14/14`; the
full backend unit suite passed `1,420/1,420` with `67.84%` coverage against the
configured `55%` threshold; Ruff, formatting, and diff checks passed. The
exact gate was rerun after the follow-up mounted-watchlist fix below; retain
this bounded-history seam as the next R1/R6 consumer contract to exercise.

## 2026-09-10 — Mounted watchlist promotion visibility

At product tip `b2de94ae`, chart plot promotion preserves the mounted
watchlist configuration object's identity, applies Boolean-column and filter
patches in place, and emits the complete target configuration through the
workstation contract. This closes the cross-root Golden Layout case where a
persisted promotion was invisible until a later remount. The focused
`ChartPlotLibrary` suite passed `25/25`, and the focused authenticated
`F8u-boolean` browser flow passed `1/1`; no persistence schema, provider,
fallback, layout policy, pixels, visual baseline, threshold, skip, or
acceptance policy changed.

The exact branch-scoped gate then passed backend unit/integration `1,420/1,420`
and `387/387` with `81.33%` combined coverage, frontend Vitest/type-check/
build, compose/health/performance/acceptance checks, and functional Playwright
`165` passed with `107` documented skips across `272`. Visual parity remained
`98/104` with exactly the six protected state-oracle diffs
(`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125); the
gate exited `2` at `e2e-visual` after clean branch-scoped teardown. The
research-runner denials were expected; no visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed.

R1/R6 remain active for provider/family history, W1/MN continuity beyond this
bounded seam, canonical population, and dense-data evidence; R2-R5 and R7
remain open. Preserve the six protected visual assertions and continue the
next bounded product seam.

## 2026-09-10 — Local split provenance carried into coarse views

At product tip `8259e5e2`, W1/MN materialization now recognizes a fully local
split-derived D1 series and carries its verified factor version into the
provider-neutral coarse-timeframe dataset state. When provider and local
derived D1 rows coexist, versions must agree; missing, opaque, or conflicting
evidence remains explicitly unversioned. This closes provenance continuity
only; it does not change aggregation, provider precedence, fallback, prices,
bars, visible layout, pixels, or acceptance policy.

The focused derived-timeframe suite passed `5/5`; the complete backend unit
suite passed `1,418/1,418` with `67.82%` coverage against the configured `55%`
threshold; Ruff, formatting, and diff checks passed. The exact branch-scoped
gate reran at this tip: backend unit/integration passed `1,418/1,418` and
`387/387`; frontend Vitest, type-check/build, compose, health, performance,
acceptance, and functional Playwright passed (`165` passed, `107` documented
skips across `272`). Visual parity remained `98/104` with exactly the six
protected state-oracle diffs (`watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125). The gate exited `2` at `e2e-visual` after clean scoped
teardown; no visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

R1/R6 remain active for provider/family history, W1/MN continuity beyond this
lineage seam, canonical population, and dense-data evidence; R2-R5 and R7
remain open. Preserve the six protected visual assertions and rerun the exact
gate after the next coherent product change.

## 2026-09-10 — Local split-adjusted materialization behind explicit lineage

At product tip `1fc650a7`, the backend now exposes an authenticated local
split-adjusted materialization route behind the explicit
`view=canonical|provider|derived` OHLCV contract. It reads one identified raw
provider source, applies the pure version-consistent split-only rebuilder, and
persists only local derived rows where provider-adjusted rows do not already
exist. Provider collisions remain untouched. The receipt and persisted state
carry provider-neutral `local_split_ratio` provenance plus factor version;
unsupported, ambiguous, incomplete, dividend, and no-data inputs remain
structured and are never guessed. Coverage lineage recognizes this local
derived state while preserving the established D1-derived W1/MN behavior.

Focused materializer coverage passed `15/15`, focused OHLCV router coverage
passed `12/12`, and the full backend unit suite passed `1,417/1,417` before
the exact gate. Ruff, formatting, and diff checks passed. No provider rows,
factor conventions, routing, precedence, fallback, visible layout, pixels,
visual baselines, thresholds, skips, or acceptance policy changed.

The exact branch-scoped gate reran at this tip: backend unit/integration passed
`1,417/1,417` and `387/387` with `81.32%` combined coverage; frontend
Vitest, type-check/build, compose, health, performance, acceptance, and
functional Playwright passed (`165` passed, `107` documented skips across
`272`). Research-runner denials were expected. Visual parity remained `98/104`
with exactly the six protected state-oracle diffs (`watchlist-column-editor-open`
at visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125). The gate exited `2` at `e2e-visual` after clean scoped
teardown. The live 100k-point proof remains unclaimed.

R1/R6 remain active for provider/family history, W1/MN continuity, canonical
population, and dense-data evidence; R2-R5 and R7 remain open. Preserve the
six protected visual assertions and rerun the exact gate after the next
coherent product change.

## 2026-09-10 — Explicit local split-factor rebuild contract

At product tip `4af7917f`, the adjustment-factor service now provides a pure
local split-ratio rebuilder. Given raw OHLCV bars and one complete,
version-consistent set of persisted split observations, it applies cumulative
pre-event price factors, inversely scales volume, preserves timestamps, and
returns explicit derived lineage without mutating raw/provider ORM rows.
Dividend amounts and provider-labelled factors are rejected with structured
unsupported states because their orientation/convention is source-specific;
incomplete or mixed-version inputs return the existing opaque provenance
states. This is the first executable application/rebuild seam, not a claim
that provider-native dividend conventions are reproducible or that any stored
provider bars were silently rewritten.

The focused adjustment-factor suite passed `14/14`; the complete backend unit
suite passed `1,413/1,413` with `67.78%` coverage against the configured `55%`
threshold; Ruff, formatting, and diff checks passed. No provider routing,
fallback, API response, visible layout, pixel, visual baseline, threshold,
skip, or acceptance policy changed. R1/R6 remain active for wiring an
explicitly selected derived view, provider/family history readiness, W1/MN
continuity, canonical population, and live 100k-point evidence; R2-R5 and R7
remain open. Rerun the exact gate at the next coherent documentation tip
while preserving the six protected visual assertions.

## 2026-09-10 — Exact integration gate after local split-factor rebuilder

The prescribed branch-scoped `make validate-integration` gate reran at
documentation checkpoint `4cf80612` with product behavior from `4af7917f`.
Backend unit coverage passed `1,413/1,413`; backend integration passed
`387/387`; frontend Vitest, type-check/build, compose startup/contract,
health, performance, and acceptance checks passed; and authenticated
functional Playwright passed `165` with `107` documented skips across `272`.
The research-runner probe returned the expected sandbox/resource denials.

Visual parity completed `104` cases with `98` passes and exactly the six
protected state-oracle diffs: `watchlist-column-editor-open` at
`visual-1080p-100/125`, and `workspace-floating` at
`visual-1080p-100/125` and `visual-1440p-100/125`. The gate exited `2` at
`e2e-visual` after clean branch-scoped teardown. No baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed; the live 100k-point
proof remains unclaimed.

R1/R6 remain active for wiring the explicit derived view, provider/family
history readiness, W1/MN continuity, canonical population, and dense-data
evidence. R2-R5 and R7 remain open. Continue the next bounded seam and rerun
the exact gate after the next coherent product change while preserving all
six protected visual assertions.

## 2026-09-10 — Explicit persisted OHLCV lineage views

At product tip `b189478e`, the OHLCV read routes now expose a backward-compatible `view` contract:
`canonical` (the existing provider-plus-derived merge), `provider` (only
persisted provider-observed rows), or `derived` (only rows marked
`is_derived`). The selector is available on local, provider-capable, and
transformed chart reads; coarse local materialization remains enabled only for
the canonical/derived views, while provider-only reads never manufacture
derived rows. This makes source selection explicit for the workstation without
changing the default response, provider precedence, adjustment factors, or
visual behavior.

The focused OHLCV router suite passed `11/11`; backend unit coverage passed
`1,414/1,414` with `67.79%` coverage against the configured `55%` threshold;
Ruff, formatting, and diff checks passed. The persisted derived-view contract
is now wired for existing W1/MN lineage. Local split-ratio materialization,
full family/provider history, W1/MN continuity, canonical population, and live
100k-point evidence remain open; preserve the six protected visual assertions
and rerun the exact gate at the next coherent product tip.

## 2026-09-10 — Exact integration gate rerun after factor-cutoff regression

The prescribed `make validate-integration` gate reran from branch HEAD
`e1fa2478` (product behavior `95f3b67a`, regression tip `d793e5a9`) after the
point-in-time factor cutoff tests were added. Backend unit coverage passed
`1,409/1,409`; the isolated backend integration suite passed `387/387`; and
frontend Vitest, type-check/build, compose contract, provider/runner/health/
performance/acceptance checks, and authenticated functional Playwright all
passed (`165` passed, `107` documented skips across `272`). Provider probes
were skipped because no provider-related files changed, and the
research-runner probe reported the expected sandbox/resource denials.

Visual parity completed `104` cases with `98` passes and exactly the six
protected state-oracle diffs: `watchlist-column-editor-open` at
`visual-1080p-100/125`, and `workspace-floating` at
`visual-1080p-100/125` and `visual-1440p-100/125`. The gate exited `2` at
`e2e-visual` after clean branch-scoped teardown. No baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed. This confirms the
same reproducible visual blocker after the factor-provenance regression and
does not claim the live 100k-point proof.

R1/R6 remain active for provider-factor application/rebuild verification,
family/provider-history readiness, W1/MN continuity, canonical population,
and dense-data evidence; R2-R5 and R7 remain open. Continue the next bounded
evidence-backed seam and rerun the exact gate after the next coherent product
change while preserving the six protected assertions.

## 2026-09-10 — Point-in-time factor cutoff regression completion

The follow-up regression at test tip `d793e5a9` covers both adjustment-factor
sources: normalized persisted observations and the legacy instrument-event
fallback. The focused point-in-time factor set passed `6/6`, and the complete
backend unit suite passed `1,409/1,409` with `67.76%` coverage against the
configured `55%` threshold. Ruff, formatting, and diff checks passed. This is
coverage-only hardening of product tip `95f3b67a`; no prices, bars, provider
routing, fallback, visible layout, pixels, visual baselines, thresholds,
skips, or acceptance policy changed.

R1/R6 remain active for provider-factor application/rebuild verification,
family/provider-history readiness, W1/MN continuity, canonical population, and
the live 100k-point proof; R2-R5 and R7 remain open. Rerun the exact gate after
the next coherent product change while preserving the six protected visual
assertions.

## 2026-09-10 — Point-in-time adjustment-factor provenance

At product tip `95f3b67a`, canonical adjusted dataset-state provenance now
limits normalized adjustment observations and legacy event fallback rows to
events effective on or before the dataset's `coverage_end`. A later corporate
action can no longer change the factor version reported for an earlier
historical range. Focused factor/market-data coverage passed `5/5`; the full
backend unit suite passed `1,408/1,408` with `67.76%` coverage against the
configured `55%` threshold; Ruff, formatting, and diff checks passed. No
prices, bars, provider routing, fallback, visible layout, pixels, visual
baselines, thresholds, skips, or acceptance policy changed.

R1/R6 remain active for provider-factor application/rebuild verification,
family/provider-history readiness, W1/MN continuity, canonical population, and
the live 100k-point proof; R2-R5 and R7 remain open. Rerun the exact gate after
the next coherent product change while preserving the six protected visual
assertions.

## 2026-09-10 — Exact integration gate receipt at the coherent product tip

The prescribed `make validate-integration` gate ran against product tip
`02bc0bd8` in the branch-scoped TC2000 worktree. Backend unit coverage passed
`1,407/1,407`; the isolated backend integration suite passed `387/387` with
`81.30%` combined coverage; frontend Vitest, type-check, production build,
compose contract, health, performance, and acceptance checks passed. Provider
probes were skipped because this tip has no provider-related changes, and the
research-runner probe reported the expected sandbox/resource denials. The
authenticated functional Playwright suite passed `165` with `107` documented
skips across `272` tests.

Visual parity completed `104` cases with `98` passes and exactly the six
protected state-oracle diffs: `watchlist-column-editor-open` at
`visual-1080p-100/125`, and `workspace-floating` at
`visual-1080p-100/125` and `visual-1440p-100/125`. The gate therefore exited
at `e2e-visual` with status `2`; no baseline, mask, threshold, skip, provider,
fallback, or acceptance policy was changed. Branch-scoped containers,
volumes, network, images, and test sessions were cleaned up by the gate.

This is an explicit reproducible visual blocker, not a Docker blocker. Continue
the next bounded R1 provider-factor/history/provenance seam and R6 dense-data
proof; rerun the exact gate after the next coherent product change while
preserving the six protected assertions.

## 2026-09-10 — Linear-time OHLCV reconciliation

At product tip `02bc0bd8`, canonical OHLCV storage reconciliation now
precomputes provider identities and counts orphan observations with a hash-set
lookup. The previous nested comparison was `O(observations × provider bars)`;
the identity-preserving result is now `O(observations + provider bars)`, which
keeps the R6 large-range path viable without changing any status semantics.
Focused storage and coverage-router coverage passed `12/12`; Ruff,
formatting, and diff checks passed. Prices, bars, provider routing, fallback,
visible layout, pixels, visual baselines, thresholds, skips, and acceptance
policy are unchanged.

R1/R6 remain active for provider/history readiness, W1/MN continuity, canonical
population, and large-data runtime evidence; R2-R5 and R7 remain open. The
exact Docker-backed gate still needs to be rerun at `bab365e9` and then at the
current coherent tip when Docker is responsive.

## 2026-09-10 — UTC normalization at the bulk-history boundary

At product tip `6dbf5fac`, bulk-history timestamp coercion now converts
offset-aware provider timestamps to UTC before comparison and persistence;
naive timestamps continue to be treated as UTC. This keeps the canonical
OHLCV bar contract consistent with the storage-reconciliation identity and
prevents equivalent instants with different offsets from producing divergent
stored keys. Focused bulk-fetch coverage passed `7/7`; the full backend unit
suite passed `1,406/1,406` with `67.76%` coverage against its `55%` threshold.
Ruff, formatting, and diff checks passed. Prices, bars, provider routing,
fallback, visible layout, pixels, visual baselines, thresholds, skips, and
acceptance policy are unchanged.

R1 remains active for provider factor application/rebuild verification,
family/provider-history readiness, W1/MN continuity, broader cadence, and
canonical population evidence; R2-R7 remain open. The exact Docker-backed gate
still needs to be rerun at `bab365e9` and then at the current coherent tip when
Docker is responsive.

## 2026-09-10 — Explicit intraday history requests

At product tip `e8bef95c`, the bulk-history worker no longer silently skips an
explicit intraday-only request such as `H1`. The coarse-history optimization is
now applied only when a daily/weekly/monthly prerequisite was actually
requested and all such requests have completed; caller-supplied timeframe
ordering no longer changes whether an intraday request reaches the provider.
Focused bulk-fetch coverage passed `6/6`; the full backend unit suite passed
`1,405/1,405` with `67.76%` coverage against its `55%` threshold. Ruff,
formatting, and diff checks passed. Prices, bars, provider routing, fallback,
visible layout, pixels, visual baselines, thresholds, skips, and acceptance
policy are unchanged.

R1 remains active for provider factor application/rebuild verification,
family/provider-history readiness, W1/MN continuity, broader cadence, and
canonical population evidence; R2-R7 remain open. The exact Docker-backed gate
still needs to be rerun at `bab365e9` and then at the current coherent tip when
Docker is responsive.

## 2026-09-10 — Storage reconciliation identity hardening

At product tip `794d5e35`, canonical OHLCV storage reconciliation now keys
provider bars and raw observations by instrument, source, timeframe, UTC
timestamp, and adjustment mode. Offset-aware timestamps are normalized to UTC
before matching, so a D1/W1 or raw/adjusted row cannot satisfy the wrong
evidence record. Focused storage-reconciliation and coverage-router coverage
passed `11/11`; the full backend unit suite passed `1,403/1,403` with
`67.75%` coverage against its `55%` threshold; Ruff, formatting, and diff
checks passed. Prices, bars,
provider routing, fallback, visible layout, pixels, visual baselines,
thresholds, skips, and acceptance policy are unchanged.
The complete frontend Vitest suite also passed `991/991`; frontend type-check
and production build passed with the existing large-chunk warning.

R1 remains active for provider factor application/rebuild verification,
family/provider-history readiness, W1/MN continuity, broader cadence, and
canonical population evidence; R2-R7 remain open. The exact Docker-backed gate
still needs to be rerun at `bab365e9` and then at the current coherent tip when
Docker is responsive.

## 2026-09-10 — Conflict recovery after late snapshot callbacks

At product tip `bab365e9`, the workspace snapshot conflict path now
distinguishes a request that began before a structural tool mutation from one
that already contained that mutation. A late Golden Layout/configuration
callback no longer suppresses the recovery-copy path for the user's original
tool addition, while the older-request retry path still protects a newly
opened tool from being recovered away. The change is limited to the
revisioned-save generation guard and its regression coverage; prices, bars,
provider routing, fallback, visible layout, pixels, visual baselines,
thresholds, skips, and acceptance policy are unchanged.

The focused workspace-store suite passed `72/72`; the full frontend Vitest
suite passed `991/991`; frontend type-check and production build passed; and
Ruff, formatting, and diff checks were green. The exact Docker-backed gate
was first run at provider tip `00849c5b` and failed only at functional E2E
`F8j-conflict`: `164` passed and `107` documented skips across `272`, with
the recovery footer not observed. The gate performed clean scoped teardown
before stopping, so its visual stage did not run. The failure was diagnosed
to the late-generation race and fixed in `bab365e9`; the exact rerun remains
pending because Docker Desktop became unresponsive while rebuilding the
branch stack (`BuildKit` returned HTTP 500 from the local Docker socket).

R1 remains active for provider-factor application/rebuild verification,
family/provider-history readiness, W1/MN continuity, broader cadence and
canonical population evidence; R2-R7 remain open. Next action: rerun the
exact gate at `bab365e9` when the branch-scoped Docker stack is available,
then continue the next bounded evidence-backed R1 seam.

## 2026-09-10 — Adjustment-factor input audit evidence

At product tip `bc703b3a`, canonical adjusted OHLCV coverage now carries
conservative adjustment-input evidence from the durable provider event or
normalized-observation lineage: total observed inputs, rebuildable versus
opaque input counts, and the observed factor kinds. The evidence is propagated
through dataset state, the coverage response, and Coverage Summary's existing
screen-reader-only range description. It is explicitly an input audit only;
it does not prove that prices were recalculated locally. Visible layout,
prices, bars, provider routing, fallback, visual baselines, thresholds,
skips, and acceptance policy are unchanged.

Focused adjustment-factor, market-data, and coverage-router backend coverage
passed `36/36`; the Coverage Summary frontend suite passed `4/4`; frontend
type-check, Ruff, formatting, and diff checks were green. The exact
Docker-backed gate completed migration compatibility (skipped because no
migration changes existed from its comparison tip) and every other non-visual
stage: backend unit/integration `1,399`/`387` with `81.23%` combined coverage,
frontend Vitest `990/990`, functional Playwright `165` with `107` documented
skips across `272`, frontend build, compose/provider/runner/health/
performance/acceptance checks, and clean scoped teardown. Visual parity
remained `98/104` with exactly the six established state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125.

R1 remains active for actual provider factor application/rebuild verification,
complete family/provider-history readiness, W1/MN continuity, broader cadence
and canonical population evidence; R2-R7 remain open. Next action: continue
the next bounded evidence-backed R1 history/provenance seam and rerun the exact
gate at the next coherent tip.

## 2026-09-10 — Observed OHLCV cadence contract

At product tip `9e9026be`, the canonical OHLCV coverage endpoint now reports
observed cadence measured from the distinct UTC bar timestamps returned for the
requested range. The additive contract exposes status, sample count, and
median/minimum/maximum interval days, with explicit semantics that this is
diagnostic of returned bar timestamps only. It does not infer an official
provider schedule or completeness for missing observations. Coverage Summary
surfaces the evidence through its existing screen-reader-only range
description; visible layout, prices, bars, provider routing, fallback,
visual baselines, thresholds, skips, and acceptance policy are unchanged.

Focused service/router coverage passed `26/26`; the Coverage Summary frontend
suite passed `4/4`; frontend type-check, Ruff, formatting, and diff checks were
green. The exact Docker-backed gate completed migration compatibility (skipped
because no migration changes existed from its comparison tip) and every other
non-visual stage: backend unit/integration `1,399`/`387` with `81.23%`
combined coverage, frontend Vitest `990/990`, functional Playwright `165`
with `107` documented skips across `272`, frontend build, compose/provider/
runner/health/performance/acceptance checks, and clean scoped teardown.
Visual parity remained `98/104` with exactly the six established state-oracle
diffs: `watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125.

R1 remains active for broader provider factor application/rebuild verification,
complete family/provider-history readiness, W1/MN continuity, broader cadence
and canonical population evidence; R2-R7 remain open. Next action: continue
the next bounded evidence-backed R1 history/provenance seam and rerun the exact
gate at the next coherent tip.

## 2026-09-10 — Benchmark-family observed cadence evidence

At implementation tip `011c1ee1`, benchmark-family coverage now reports
observed spacing between the distinct composition dates actually returned for
each D1/W1/MN role. The additive role contract includes cadence status,
sample count, and median/minimum/maximum interval days; family provenance
explicitly labels this as diagnostic evidence for returned snapshot dates
only. It does not infer an official disclosure schedule or claim completeness
for missing snapshots. Market Map and family-role accessibility summaries
surface the evidence without visible layout or pixel changes; prices, bars,
provider routing, fallback behavior, visual baselines, thresholds, skips, and
acceptance policy are unchanged.

Focused cadence coverage passed `9/9`; the family-coverage integration fixture
passed `1/1`; the related Market Map frontend suite passed `36/36`; frontend
type-check, Ruff, formatting, and diff checks were green. The exact
Docker-backed gate completed migration compatibility (skipped because no
migration changes existed from its comparison tip) and every other non-visual
stage: backend unit/integration `1,397`/`387` with `81.22%` combined coverage,
frontend Vitest `990/990`, functional Playwright `165` with `107` documented
skips across `272`, frontend build, compose/provider/runner/health/
performance/acceptance checks, and clean scoped teardown. Visual parity
remained `98/104` with exactly the six established state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125.

R1 remains active for broader provider factor application/rebuild verification,
complete family/provider-history readiness, W1/MN continuity, broader cadence
and canonical population evidence; R2-R7 remain open. Next action: continue
the next bounded evidence-backed R1 history/provenance seam and rerun the exact
gate at the next coherent tip.

## 2026-09-10 — Benchmark-family history factor-evidence consumer

At product tip `1bfd7470`, the benchmark-family member-bar history contract
now carries durable `InstrumentDatasetState` adjustment provenance for each
role's D1/W1/MN coverage. Provider source identities are retained while
aggregating member bars, null-source derived states are included when present,
and the shared conservative factor-evidence helper reports versioned, opaque,
and unavailable member counts only when the observed lineage supports them.
The additive schema/type fields reach both Market Map and the family-role
workstation accessibility summaries; visible labels, prices, bars, provider
routing, fallback behavior, visual baselines, thresholds, skips, and
acceptance policy are unchanged.

Focused family-coverage integration passed `1/1`; watchlist-history unit
coverage passed `8/8`; the related Market Map frontend suite passed `36/36`;
frontend type-check, Ruff, formatting, and diff checks were green. The exact
Docker-backed gate completed migration compatibility (skipped because no
migration changes existed from its comparison tip) and every other
non-visual stage: backend unit/integration `1,394`/`387` with `81.21%`
combined coverage, frontend Vitest `990/990`, functional Playwright `165`
with `107` documented skips across `272`, frontend build, compose/provider/
runner/health/performance/acceptance checks, and clean scoped teardown. Visual
parity remained `98/104` with exactly the six established state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125.

R1 remains active for broader provider factor application/rebuild verification,
complete family/provider-history readiness, W1/MN continuity, cadence beyond
source-declared metadata, and canonical population; R2-R7 remain open. Next
action: continue the next bounded evidence-backed R1 history/provenance seam
and rerun the exact gate at the next coherent tip.

## 2026-09-10 — Generic history factor-evidence consumer

At implementation tip `d33ef30e`, watchlist source-history status now joins
covered canonical provider and derived bars to durable `InstrumentDatasetState`
adjustment provenance. It reports member-level versioned, opaque, and
unavailable factor counts, plus one aggregate `factor_version`/`factor_status`
only when every covered lineage member has complete, consistent rebuildable or
inherited evidence. Legacy provider bars without source-state evidence remain
opaque; mixed and incomplete lineage stays conservative. Market Map carries the
new counts through its existing assistive provenance label without visible
layout or pixel changes. No prices, bars, provider routing, fallback behavior,
visual baseline, threshold, skip, or acceptance policy changed.

Focused watchlist-history backend coverage passed `8/8`; the related Market Map
frontend suite passed `36/36`, frontend type-check passed, and Ruff, formatting,
and diff checks were green. The exact Docker-backed gate (run against this same
tree before commit) completed migration compatibility (skipped because no
migration changes existed from its comparison tip) and all other non-visual
stages: backend unit/integration `1,394`/`387` with `81.21%` combined coverage,
frontend Vitest `990/990`, and functional Playwright `165` with `107` documented
skips across `272`. Visual parity remained `98/104` with exactly the six
established state-oracle diffs (`watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125); scoped teardown removed all assigned resources and test
sessions cleanly. A PostgreSQL grouping defect found on the first gate attempt
was corrected before this qualifying run.

R1 remains active for broader provider factor application/rebuild verification,
complete family/provider-history readiness, W1/MN continuity, cadence beyond
source-declared metadata, and canonical population; R2-R7 remain open. Next
action: continue the next bounded evidence-backed R1 history/provenance seam
and rerun the exact gate at the next coherent tip.

## 2026-09-10 — Derived factor provenance reaches coverage consumers

At product tip `e2263da9`, the canonical OHLCV coverage endpoint now reads
the null-source derived W1/MN dataset state for derived-only ranges, exposing
the inherited D1 factor version to the workstation accessibility contract.
Mixed provider/derived ranges remain conservative and do not claim one factor
version. No prices, bars, provider routing, fallback behavior, visible layout,
pixels, or acceptance policy changed.

The focused derived-timeframe, adjustment-factor, market-data, and coverage
router suite passed `38/38`, with Ruff, formatting, and diff checks passing.
The exact Docker-backed gate completed its migration-compatibility stage
(reported skipped because no migration changes existed from its comparison
tip) and all other non-visual stages: backend unit/integration `1,393`/`387`
with `81.21%` combined coverage, frontend Vitest `990/990`, and functional
Playwright `165` with `107` documented skips across `272`. Visual parity
remained `98/104` with exactly the six established state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. Scoped
teardown removed all assigned resources and test sessions cleanly.

R1 remains active for broader provider factor application/rebuild verification,
complete family/provider-history readiness, W1/MN continuity, cadence beyond
source-declared metadata, and canonical population; R2-R7 remain open. Next
action: continue the next bounded evidence-backed R1 history/provenance seam
and rerun the exact gate at the next coherent tip.

## 2026-09-10 — Derived timeframe factor-lineage propagation

At product tip `ef5f2caa`, derived W1/MN dataset states now retain a verified
canonical D1 `factor_version` when every contributing provider D1 source has
the same rebuildable split or provider-factor provenance. Missing, mixed,
opaque, raw, or otherwise incomplete evidence remains unversioned; no prices,
bars, provider routing, fallback behavior, visible layout, pixels, or
acceptance policy changed.

The focused derived-timeframe, adjustment-factor, market-data, and coverage
router suite passed `37/37`, with Ruff, formatting, and diff checks passing.
The exact Docker-backed gate completed its migration-compatibility stage
(reported skipped because no migration changes existed from its comparison
tip) and all other non-visual stages: backend unit/integration `1,392`/`387`
with `81.20%` combined coverage, frontend Vitest `990/990`, and functional
Playwright `165` with `107` documented skips across `272`. Visual parity
remained `98/104` with exactly the six established state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. Scoped
teardown removed all assigned resources and test sessions cleanly.

R1 remains active for broader provider factor application/rebuild verification,
complete family/provider-history readiness, W1/MN continuity, cadence beyond
source-declared metadata, and canonical population; R2-R7 remain open. Next
action: continue the next bounded evidence-backed R1 history/provenance seam
and rerun the exact gate at the next coherent tip.

## 2026-09-10 — Provider-factor fingerprint compatibility correction

At product tip `1875ac4f`, the provider-factor seam preserves the established
legacy `afv1-…` fingerprint for split-only evidence while still including
explicit provider-factor metadata whenever provider factors are present.
This keeps existing split-derived dataset identities stable and promotes
provider-supplied factor sets without changing prices, bars, provider routing,
fallback behavior, visible layout, pixels, or acceptance policy.

The focused factor/market-data/event coverage passed `28/28`, the related
provider adapter suite passed `83/83`, and Ruff, formatting, and diff checks
passed. The exact Docker-backed gate completed its migration-compatibility
stage (reported skipped because no migration changes existed from its
comparison tip) and all other non-visual stages: backend unit/integration
`1,391`/`387` with `81.20%`
combined coverage, frontend Vitest `990/990`, and functional Playwright `165`
with `107` documented skips across `272`. Visual parity remained `98/104`
with exactly the six established state-oracle diffs: watchlist-column-editor-
open at visual-1080p-100/125 and workspace-floating at visual-1080p-100/125
and visual-1440p-100/125. Scoped teardown removed all assigned resources and
test sessions cleanly.

R1 remains active for broader provider factor application/rebuild verification,
complete family/provider-history readiness, W1/MN continuity, cadence beyond
source-declared metadata, and canonical population; R2-R7 remain open. Next
action: continue the next bounded evidence-backed R1 history/provenance seam
and rerun the exact gate at the next coherent tip.

## 2026-09-10 — Provider-supplied adjustment-factor persistence

At product tip `d322584f`, the provider event contract accepts an explicit
positive `adjustment_factor` and persists it alongside the original event.
Normalized adjustment observations now retain `factor_kind`, distinguishing a
provider-supplied factor from a split ratio. Deterministic `afv1-…` snapshots
and dataset-state provenance promote a complete, consistently versioned set to
`rebuildable_provider_factors`; dividend amounts without a factor remain
explicitly opaque. Migration `ff2a3b4c5d6e` adds both nullable fields, and event
fetch version `3` causes older event rows to be refreshed for the new payload.
This seam records and verifies factor provenance; it does not transform prices
or claim a provider adjustment convention that was not supplied.

Focused factor/market-data/event coverage passed `28/28`, the related provider
adapter suite passed `83/83`, and Ruff, formatting, and diff checks passed. The
exact Docker-backed gate passed migration compatibility, backend unit/integration
`1,391`/`387` with `81.20%` combined coverage, frontend Vitest `990/990`, and
functional Playwright `165` with `107` documented skips across `272`. Visual
parity remained `98/104` with exactly the six established state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. Scoped
teardown removed all assigned resources and test sessions cleanly.

R1 remains active for broader provider factor application/rebuild verification,
complete family/provider-history readiness, W1/MN continuity, cadence beyond
source-declared metadata, and canonical population; R2-R7 remain open. Next
action: continue the next bounded evidence-backed R1 history/provenance seam
and rerun the exact gate at the next coherent tip.

## 2026-09-10 — Accessible storage evidence consumer

At product tip `285f1942`, the Coverage Summary tool now includes the
raw/provider storage reconciliation result in its existing screen-reader-only
range description. Users of assistive technology can distinguish reconciled,
missing, mismatched, orphaned, and not-observed source evidence without a
visible layout or pixel change. No prices, provider routing, fallback
behavior, visual baseline, mask, threshold, skip, or acceptance policy
changed.

The focused frontend accessibility test passed `4/4`, with type-check green;
the preceding backend storage/coverage contract passed `8/8` and backend
unit-only suite `1,387/1,387`. The exact Docker-backed gate passed all
non-visual stages, backend unit/integration coverage (`1,387`/`387`,
`68%`/`81.19%`), frontend Vitest (`990/990`), and functional Playwright
(`165` passed, `107` documented skips across `272`). Visual parity completed
`104` cases with `98` passes and the same six established state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. Scoped
teardown removed all assigned resources and test sessions cleanly.

R1 remains active for provider-supplied dividend-factor coverage and factor
application/rebuild verification, complete family/provider-history readiness,
W1/MN continuity, cadence beyond source-declared metadata, and broader
canonical population; R2-R7 remain open. Next action: continue the next
bounded evidence-backed R1 history/provenance seam and rerun the exact gate at
the next coherent tip.

## 2026-09-10 — Raw/provider storage reconciliation evidence

At product tip `49d87f6f`, adjusted OHLCV coverage now reports explicit storage
evidence by comparing canonical provider bars with matching raw
`MarketBarObservation` rows. It distinguishes reconciled, missing,
mismatched, orphaned, and not-observed states; locally derived rows are not
expected to have raw observations. This is additive API evidence only: no
prices, provider routing, fallback behavior, visible layout, pixels, or
acceptance policy changed.

The focused storage/coverage checks passed `8/8`, and the backend unit-only
suite passed `1,387/1,387`; Ruff, formatting, and diff checks passed. The exact
Docker-backed gate passed all non-visual stages, backend unit/integration
coverage (`1,387`/`387`, `68%`/`81.19%`), frontend Vitest (`990/990`), and
functional Playwright (`165` passed, `107` documented skips across `272`).
Visual parity completed `104` cases with `98` passes and the same six
established state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. Scoped teardown removed all assigned resources and test
sessions cleanly. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

R1 remains active for provider-supplied dividend-factor coverage and factor
application/rebuild verification, complete family/provider-history readiness,
W1/MN continuity, cadence beyond source-declared metadata, and broader
canonical population; R2-R7 remain open. Next action: continue the next
bounded evidence-backed R1 history/provenance seam and rerun the exact gate at
the next coherent tip.

## 2026-09-10 — Persisted factor completeness guard

At product tip `2cbf74a8`, durable split-factor provenance refuses to promote
rows when any valid split observation lacks its persisted version. Mixed or
incomplete normalized evidence remains explicitly opaque, preventing a
partial refresh from masquerading as a rebuildable factor set. No dividend
factor, price transformation, provider response, fallback behavior, visible
layout, pixels, or acceptance policy changed.

The focused adjustment-factor and market-data suites passed `23/23`; Ruff,
formatting, and diff checks passed. The exact Docker-backed gate passed all
non-visual stages, backend unit/integration coverage (`1,385`/`387`,
`68%`/`81.18%`), frontend Vitest (`990/990`), and functional Playwright
(`165` passed, `107` documented skips across `272`). Visual parity completed
`104` cases with `98` passes and the same six established state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. Scoped
teardown removed all assigned resources and test sessions cleanly. No visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed.

R1 remains active for provider-supplied dividend-factor coverage and factor
application/rebuild verification, raw-versus-derived reconciliation, complete
family/provider-history readiness, W1/MN continuity, cadence beyond
source-declared metadata, and broader canonical population; R2-R7 remain open.
Next action: continue the next bounded evidence-backed R1 history/provenance
seam and rerun the exact gate at the next coherent tip.

## 2026-09-10 — Durable factor provenance reconciliation

At product tip `00dd7f1b`, adjusted OHLCV dataset-state provenance now prefers
the durable normalized split/dividend observation rows for the requested
provider. A single consistent split-factor version remains rebuildable;
incomplete or mixed persisted evidence is explicitly opaque. Existing event
rows remain a compatibility fallback for older data, and no dividend factor,
price transformation, provider response, fallback behavior, visible layout,
pixels, or acceptance policy is invented or changed.

Focused adjustment-factor and market-data coverage passed `22/22`; Ruff,
formatting, and diff checks passed. The exact Docker-backed gate passed all
non-visual stages, backend unit/integration coverage (`1,384`/`387`,
`68%`/`81.18%`), frontend Vitest (`990/990`), and functional Playwright
(`165` passed, `107` documented skips across `272`). Visual parity completed
`104` cases with `98` passes and the same six established state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. Scoped
teardown removed all assigned resources and test sessions cleanly. No visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed.

R1 remains active for provider-supplied dividend-factor coverage and factor
application/rebuild verification, raw-versus-derived reconciliation, complete
family/provider-history readiness, W1/MN continuity, cadence beyond
source-declared metadata, and broader canonical population; R2-R7 remain open.
Next action: continue the next bounded evidence-backed R1 history/provenance
seam and rerun the exact gate at the next coherent tip.

## 2026-09-10 — Coverage exposes verified adjustment-factor version

At product tip `e3a29a3d`, adjusted OHLCV coverage now consumes the newest
provider dataset-state provenance for the requested timeframe and exposes a
verified `factor_version`/`factor_status` pair when a deterministic split-factor
fingerprint exists. Provider-native opaque or absent factor evidence remains
unchanged; the endpoint does not invent dividend factors or alter bars, prices,
fallback behavior, visible layout, pixels, or acceptance policy.

The focused coverage-router and adjustment-factor regressions passed `10/10`,
with the previously verified factor/event suites at `20/20`, adjacent
derived-timeframe/OHLCV units at `13/13`, and OHLCV integration at `19/19`;
Ruff, formatting, and diff checks passed. The exact Docker-backed gate passed
all non-visual stages, backend unit/integration coverage (`1,381`/`387`,
`68%`/`81.17%`), frontend Vitest (`990/990`), and functional Playwright
(`165` passed, `107` documented skips across `272`). Visual parity completed
`104` cases with `98` passes and the same six established state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. Scoped
teardown removed all assigned resources and test sessions cleanly. No visual
baseline, mask, threshold, skip, provider, fallback, or acceptance policy
changed.

R1 remains active for provider-supplied dividend-factor coverage and factor
application/rebuild verification, raw-versus-derived reconciliation, complete
family/provider-history readiness, W1/MN continuity, cadence beyond
source-declared metadata, and broader canonical population; R2-R7 remain open.
Next action: continue the next bounded evidence-backed R1 history/provenance
seam and rerun the exact gate at the next coherent tip.

## 2026-09-10 — Durable normalized adjustment-factor observations

At product tip `91bc8f5d` (with required import-order correction
`1dd94507`), provider event ingestion now persists normalized split/dividend
observations in the additive `adjustment_factor_observation` table. The
natural key is instrument, source, factor type, effective time, and source
event key, so refreshes update evidence idempotently. Complete split inputs
retain the deterministic `afv1-…` version; dividend amounts and incomplete
inputs are stored without being converted into invented price factors. The
Alembic migration is `ff1a2b3c4d5e`. No provider response, price, fallback,
visible layout, pixel, or acceptance policy changed.

Focused adjustment-factor/market-data/event coverage passed `20/20`, adjacent
derived-timeframe/OHLCV units passed `13/13`, and the OHLCV integration
contract passed `19/19`; model metadata registration, Ruff, formatting, and
diff checks passed. The exact Docker-backed gate passed all non-visual stages,
backend unit/integration coverage (`1,380`/`387`, `68%`/`81.17%`), frontend
Vitest (`990/990`), and functional Playwright (`165` passed, `107` documented
skips across `272`). Visual parity completed `104` cases with `98` passes and
the same six established state-oracle diffs: `watchlist-column-editor-open`
at visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. Scoped teardown removed all assigned resources and test
sessions cleanly. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

R1 remains active for provider-supplied dividend-factor coverage and factor
application/rebuild verification, raw-versus-derived storage reconciliation,
complete family/provider-history readiness, W1/MN continuity, cadence beyond
source-declared metadata, and broader canonical population; R2-R7 remain open.
Next action: continue the next bounded evidence-backed R1 history/provenance
seam and rerun the exact gate at the next coherent tip.

## 2026-09-10 — Rebuildable split-factor provenance fingerprint

At product tip `64a17354`, the provider dataset-state path now fingerprints a
complete persisted split-event set as a deterministic `afv1-…` adjustment
factor version. Events are sorted and canonically encoded before hashing, so
the same source inputs can be reproduced independently. Dividend events,
missing/invalid split ratios, and absent event evidence remain explicitly
opaque because dividend amounts alone do not define a provider's adjustment
factor convention. No provider response, price, fallback, visible layout,
pixel, or acceptance policy changed.

The focused adjustment-factor and market-data suites passed `18/18`, adjacent
derived-timeframe/OHLCV units passed `13/13`, and the Docker-backed OHLCV
integration contract passed `19/19`; Ruff, formatting, and diff checks passed.
The exact Docker-backed gate passed all non-visual stages, backend
unit/integration coverage (`1,379`/`387`, `68%`/`81.16%`), frontend Vitest
(`990/990`), and functional Playwright (`165` passed, `107` documented skips
across `272`). Visual parity completed `104` cases with `98` passes and the
same six established state-oracle diffs: `watchlist-column-editor-open` at
visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. Scoped teardown removed all assigned resources and test
sessions cleanly. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

R1 remains active for broader factor-event persistence and dividend-factor
coverage, raw-versus-derived storage separation, complete family/provider-
history readiness, W1/MN continuity, cadence beyond source-declared metadata,
and broader canonical population; R2-R7 remain open. Next action: continue
the next bounded evidence-backed R1 history/provenance seam and rerun the exact
gate at the next coherent tip.

## 2026-09-10 — Provider history promotes derived rows to canonical lineage

At product tip `2a83bd46`, every provider OHLCV persistence path now uses a
lineage-aware upsert. When a provider W1/MN observation arrives for a key
previously occupied by a locally materialised D1-derived row, the provider
values and source are retained while `is_derived` and all D1 derivation
metadata are cleared. This preserves provider precedence and keeps raw versus
derived storage evidence truthful; no price transformation, provider fallback,
visible layout, pixels, or acceptance policy changed.

The focused market-data unit suite passed `14/14`, adjacent derived-timeframe
and OHLCV router units passed `13/13`, and the OHLCV integration contract
passed `19/19`; Ruff format/check and diff checks passed. The exact Docker-
backed gate passed dependency, migration, lint, backend unit/integration
coverage (`1,375`/`387`, `68%`), frontend/build/probe stages, and functional
Playwright (`165` passed, `107` documented skips across `272`). Visual parity
completed `104` cases with `98` passes and exactly the six established
state-oracle diffs: `watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. The gate
exits at `e2e-visual` only for those unchanged diffs; scoped teardown removed
all assigned resources and test sessions cleanly. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

R1 remains active for a rebuildable adjustment-factor/version model, complete
family/provider-history readiness, W1/MN continuity, cadence beyond
source-declared metadata, broader canonical population, and further raw versus
derived evidence; R2-R7 remain open. Next action: continue the next bounded
evidence-backed R1 history/provenance seam while preserving the six visual
state-oracle assertions and rerun the exact gate at the next coherent tip.

## 2026-09-10 — Generic history source provenance evidence

At product tip `4cefce9b`, generic watchlist history now preserves source-
declared publication and parser metadata per timeframe, including effective
and known membership timing, published-at, cadence, parser version, source
identifier, and declared timing provenance when available. Unavailable source
legs remain explicit nulls; cadence is not inferred and no source metadata is
fabricated. Market Map exposes the evidence only through a hidden accessibility
summary. Visible layout, pixels, provider precedence, fallback, storage, and
acceptance policy remain unchanged.

Focused watchlist-history units passed `7/7`; Market Map Vitest passed `36/36`;
frontend type-check, Ruff check/format, and diff checks passed. The exact
Docker-backed gate passed dependency, migration, lint, backend unit/integration
coverage (`1,374`/`387`, `68%`), frontend/build/probe stages, and functional
Playwright (`165` passed, `107` documented skips across `272`). Visual parity
completed `104` cases with `98` passes and exactly the six established
state-oracle diffs: `watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. The gate
exits at `e2e-visual` only for those unchanged diffs; scoped teardown removed
all assigned resources and test sessions cleanly. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

R1 remains active for a rebuildable adjustment-factor/version model,
raw-versus-derived storage separation, complete family/provider-history
readiness, W1/MN continuity, cadence beyond source-declared metadata, and
broader canonical population; R2-R7 remain open. Next action: continue the
next bounded evidence-backed R1 history/provenance seam while preserving the
six visual state-oracle assertions and rerun the exact gate at the next
coherent tip.

## 2026-09-09 — Generic history adjustment provenance evidence

At product tip `667577c1`, generic watchlist history status now carries an
explicit adjustment-provenance envelope per timeframe. It distinguishes
provider-native opaque factors, derived bars inheriting the canonical adjusted
D1 contract, mixed provider/derived coverage, and unavailable coverage. The
contract reports `factor_version` as null when the provider does not expose a
rebuildable version; no factor set or price transformation is invented. Market
Map exposes this only through hidden accessibility evidence, with visible
layout, pixels, provider precedence, fallback, storage, and acceptance policy
unchanged.

Focused watchlist-history units passed `7/7`; Market Map Vitest passed `36/36`;
frontend type-check, Ruff check/format, and diff checks passed. The exact
Docker-backed gate passed dependency, migration, lint, backend unit/integration
coverage (`1,374`/`387`, `68%`), frontend/build/probe stages, and functional
Playwright (`165` passed, `107` documented skips across `272`). Visual parity
completed `104` cases with `98` passes and exactly the six established
state-oracle diffs: `watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. The gate
exits at `e2e-visual` only for those unchanged diffs; scoped teardown removed
all assigned resources and test sessions cleanly. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

R1 remains active for a rebuildable adjustment-factor/version model, raw versus
derived storage separation, complete family/provider-history readiness, W1/MN
continuity, cadence beyond source-declared timing, and broader canonical
population; R2-R7 remain open. Next action: continue the next bounded
evidence-backed R1 history/provenance seam while preserving the six visual
state-oracle assertions and rerun the exact gate at the next coherent tip.

## 2026-09-09 — Generic history membership timing evidence

At product tip `31c6565c`, generic watchlist history status preserves the
resolver's point-in-time membership `effective_at` and `known_at` timestamps
and any declared timing-provenance labels. Market Map exposes that evidence
through a hidden accessibility summary only. The contract does not infer an
issuer cadence or manufacture timestamps; visible layout, pixels, provider
precedence, fallback, storage, and acceptance policy are unchanged.

Focused watchlist-history units passed `7/7`; Market Map Vitest passed `36/36`;
frontend type-check, Ruff check/format, and diff checks passed. The exact
Docker-backed gate passed dependency, migration, lint, backend unit/integration
coverage (`1,374`/`387`, `68%`), frontend/build/probe stages, and functional
Playwright (`165` passed, `107` documented skips across `272`). Visual parity
completed `104` cases with `98` passes and exactly the six established
state-oracle diffs: `watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. The gate
exits at `e2e-visual` only for those unchanged diffs; scoped teardown removed
all assigned resources and test sessions cleanly. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

R1 remains active for complete family/provider-history readiness, W1/MN
continuity, cadence beyond source-declared timing, adjustment-factor/version
provenance, raw-versus-derived storage, and broader canonical population;
R2-R7 remain open. Next action: continue the next bounded evidence-backed R1
history/provenance seam while preserving the six visual state-oracle
assertions and rerun the exact gate at the next coherent tip.

## 2026-09-09 — Generic watchlist history lineage evidence

At product tip `7fe87c3a` (feature `d5c2e7af` plus the required formatter-only
follow-up), generic watchlist history status now reports provider-versus-derived
bar lineage per timeframe, including provider/derived member counts, exclusive
and mixed member splits, bar totals, and a normalized lineage label. Readiness
floors are evaluated after combining each member's provider and derived rows, so
a member split across storage lineages cannot be incorrectly classified below
the D1/W1/MN analysis floors. Market Map exposes the contract only through a
hidden accessibility summary; visible layout, pixels, provider precedence,
fallback, storage, and acceptance policy are unchanged.

Focused watchlist-history units passed `7/7`; Market Map Vitest passed `36/36`;
frontend type-check, Ruff check/format, and diff checks passed. The exact
Docker-backed gate passed dependency, migration, lint, backend unit/integration
coverage (`1,374`/`387`, `68%`), frontend/build/probe stages, and functional
Playwright (`165` passed, `107` documented skips across `272`). Visual parity
completed `104` cases with `98` passes and exactly the six established
state-oracle diffs: `watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. The gate
exits at `e2e-visual` only for those unchanged diffs; scoped teardown removed
all assigned resources and test sessions cleanly. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

R1 remains active for complete family/provider-history readiness, W1/MN
continuity, cadence/effective-time and adjustment-factor/version provenance,
raw-versus-derived storage, and broader canonical population; R2-R7 remain
open. Next action: continue the next bounded evidence-backed R1 history or
provenance seam while preserving the six visual state-oracle assertions and
rerun the exact gate at the next coherent tip.

## 2026-09-09 — Unified watchlist history disposition evidence

At product commit `bda0f964`, the generic user-scoped history refresh and
read-only status contracts now carry the same provider-neutral member
disposition map as benchmark-family maintenance: `canonical`, `placeholder`,
`unresolved`, and `excluded`. Aggregate `excluded_count` behavior remains
compatible, unavailable sources return deterministic zero maps, and canonical
counts use unique resolved members. Market Map exposes the map only through a
hidden accessible evidence label, so visible layout and pixels are unchanged.

The focused backend history planner/status suite passed `7/7`; the focused
Docker-backed watchlist API regressions passed `2/2`; the adjacent benchmark
history and watchlist unit suites passed `32/32`; frontend Market Map coverage
passed `36/36`, type-check passed, and Ruff/format/diff checks passed. The exact
Docker-backed gate passed backend unit/integration (`1,374`/`387`), frontend
Vitest (`990/990`), build, compose/provider/runner/research-runner probes,
stack health, performance, acceptance policy, and functional Playwright
(`165` passed, `107` documented skips across `272`). Visual parity remains
`98/104` with exactly the six established state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. The gate
exits at `e2e-visual` only for those unchanged diffs; scoped teardown removed
all assigned resources and test sessions cleanly. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

R1 remains active for complete family/provider-history readiness, W1/MN
coverage and continuity, cadence/effective-time and adjustment-factor/version
provenance, raw-versus-derived storage, and broader canonical population;
R2-R7 remain open. Next action: continue the next bounded evidence-backed R1
history/provenance seam while preserving the six visual state-oracle
assertions and rerun the exact gate at the next coherent tip.

## 2026-09-09 — Explicit history queue disposition readiness

At product commit `96bfea6e`, the admin canonical history-refresh planner now
reports the same provider-neutral member disposition breakdown as the
persisted benchmark-family snapshot contract: `canonical`, `placeholder`,
`unresolved`, and `excluded`. The legacy aggregate `unresolved_count` and
`excluded_count` fields remain intact for existing consumers, while ready and
pending legs expose the explicit map and error legs return a deterministic
zero-valued map. Canonical counts continue to use unique resolved
security/equity IDs; placeholder provenance and exclusion reasons are not
silently promoted to canonical readiness. No provider precedence, fallback,
storage, UI layout, visual baseline, or acceptance policy changed.

The focused planner contract suite passed `25/25`; the Docker-backed ETF
history API integration suite passed `65/65`; frontend type-check, Ruff,
format, and diff checks passed. The exact Docker-backed gate passed backend
unit/integration (`1,373`/`387`), the full frontend suite and build, compose/
provider/runner/research-runner probes, stack health, performance, acceptance
policy, and functional Playwright (`165` passed, `107` documented skips across
`272`). Visual parity remains `98/104` with exactly the six established
state-oracle diffs: `watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. The gate
exits at `e2e-visual` only for those unchanged diffs; scoped teardown removed
all assigned resources and test sessions cleanly. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

R1 remains active for complete family/provider-history readiness, W1/MN
coverage and continuity, cadence/effective-time and adjustment-factor/version
provenance, raw-versus-derived storage, and broader canonical population;
R2-R7 remain open. Next action: continue the next bounded evidence-backed R1
history/provenance seam while preserving the six visual state-oracle
assertions and rerun the exact gate at the next coherent tip.

## 2026-09-09 — Explicit family member disposition readiness

At product commit `7333b328`, the benchmark-family snapshot contract now
reports provider-neutral member dispositions for every persisted snapshot:
`canonical`, `placeholder`, `unresolved`, and `excluded`. Canonical member IDs
and readiness denominators remain limited to resolved security/equity rows, so
cash and other non-member records cannot silently inflate family coverage.
The existing hidden Market Map evidence label includes the sorted disposition
counts without changing visible layout, pixels, provider precedence, fallback,
or acceptance policy. The persisted workspace integration contract passed
`57/57`; focused Market Map/accessibility/pop-out frontend coverage passed
`66/66`; type-check, Ruff, and diff checks passed.

The exact Docker-backed gate at this product tip passed all locked and
non-visual stages, backend unit/integration coverage (`1,372`/`387`), the
functional Playwright matrix (`165` passed, `107` documented skips across
`272`), and the four-project visual run's non-failing cases (`98/104`). The
only visual failures are the six established state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 and
`workspace-floating` at visual-1080p-100/125 and visual-1440p-100/125. Scoped
teardown removed all assigned containers, volumes, images, and test sessions
cleanly. No visual baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

R1 remains active for complete family/provider-history readiness, W1/MN
coverage and continuity, cadence/effective-time and adjustment-factor/version
provenance, raw-versus-derived storage, and broader canonical population;
R2-R7 remain open. Next action: continue the next bounded evidence-backed R1
history/provenance seam while preserving the six visual state-oracle
assertions and rerun the exact gate at the next coherent tip.

## 2026-09-09 — Missing pop-out recovery alert accessibility

At product commit `07bafee7`, the existing missing-tool recovery state for a
blocked or unavailable workstation pop-out is now exposed as an assertive
`role="alert"` with `aria-live="assertive"`. Its existing recovery copy,
layout, browser/OS boundary disclosure, provider/fallback behavior, and
visual output remain unchanged. The focused workstation/pop-out view suite
passed `28/28`; frontend type-check and diff checks passed.

The exact Docker-backed gate at this product tip passed every non-visual stage
and the full functional Playwright matrix (`165` passed, `107` documented
skips across `272`). Visual parity completed `104` cases with `98` passes and
the same six established state-oracle diffs: `watchlist-column-editor-open`
at visual-1080p-100/125 and `workspace-floating` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exits at `e2e-visual` only for those unchanged
diffs. Scoped teardown removed all assigned containers, volumes, images, and
test sessions cleanly; no visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

R1 remains active for complete canonical family/provider-history readiness,
placeholder disposition, cadence/effective-time and adjustment-factor/version
provenance, raw-versus-derived storage, and broader continuity; R2-R7 remain
open. Next action: continue the next bounded evidence-backed R1 or compatible
Study target slice while preserving the six visual state-oracle assertions.

## 2026-09-09 — Workstation recovery status accessibility

At product commit `4daf9b95`, the concise workstation footer recovery message
now exposes a polite, atomic status announcement. Transport failures,
permission messages, stale-data notices, and browser pop-out recovery guidance
therefore reach assistive technology without changing their copy, tooltip
detail, footer layout, provider/fallback behavior, or visual output. The
focused workstation/pop-out view suite passed `27/27`; frontend type-check and
diff checks passed.

The exact Docker-backed gate at this product tip passed all non-visual stages
and the full functional Playwright matrix (`165` passed, `107` documented
skips across `272`). Visual parity completed `104` cases with `98` passes and
the same six established state-oracle diffs: `watchlist-column-editor-open.png`
at visual-1080p-100/125 and `workspace-floating.png` at
visual-1080p-100/125 and visual-1440p-100/125. The gate exits at `e2e-visual`
only for those unchanged diffs; scoped teardown removed all assigned
containers, volumes, images, and test sessions cleanly.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. R1 canonical family/provider-history readiness and R2-R7
evidence remain open; continue the next bounded evidence-backed R1 or
compatible Study target slice.

## 2026-09-09 — Browser-managed pop-out boundary disclosure

At product commit `83bcb722`, hydrated workstation pop-outs now expose an
accessible description stating that placement across monitors and window
controls are browser/operating-system managed. The disclosure is hidden from
the visual surface, keeps the named focusable landmark and post-hydration
focus introduced by `caff874b`, and avoids implying that the application can
control native window placement. The focused pop-out view suite passed `27/27`;
frontend type-check and diff checks passed.

The unchanged exact Docker-backed gate rerun passed every non-visual stage and
the full functional matrix (`165` passed, `107` documented skips across
`272`). Visual parity completed `104` cases with `98` passes and exactly the
same six established state-oracle diffs: `watchlist-column-editor-open.png` at
visual-1080p-100/125 and `workspace-floating.png` at visual-1080p-100/125 and
visual-1440p-100/125. The gate exits at `e2e-visual` only for those unchanged
diffs; scoped teardown removed all assigned containers, volumes, images, and
test sessions cleanly.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. R1 canonical family/provider-history readiness and R2-R7
evidence remain open; continue the next bounded evidence-backed R1 or
compatible Study target slice.

## 2026-09-09 — Pop-out landmark and transient Boolean promotion

At product commit `caff874b`, hydrated workstation pop-outs now expose a named,
focusable main landmark (`TC2000 <tool> pop-out`) and move focus into it after
hydration. This gives keyboard and assistive-technology users a deterministic
entry point without changing the rendered tool surface or pop-out geometry.
The focused pop-out view suite passed `27/27`; frontend type-check and diff
checks passed.

The earlier F8u-boolean failure passed in isolation (`1/1`) against a fresh
seeded stack. The governed functional suite then passed `165` cases with `107`
documented skips across `272`; the exact Docker-backed gate passed every
non-visual stage (backend `1,372` unit / `387` integration, `81.10%` combined
coverage, frontend Vitest `989/989`, build, compose/provider/runner and
stack-health probes, performance, uPlot, and acceptance policy). Visual parity
completed `104` cases with `98` passes and exactly the six established
state-oracle diffs: `watchlist-column-editor-open.png` at visual-1080p-100/125
and `workspace-floating.png` at visual-1080p-100/125 and visual-1440p-100/125.
The gate exits at `e2e-visual` for those unchanged diffs; scoped teardown
removed all assigned containers, volumes, images, and test sessions cleanly.

No visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. R1 canonical family/provider-history readiness and R2-R7
evidence remain open; continue the next bounded evidence-backed R1 or
compatible Study target slice and rerun the exact gate at the next coherent
tip.

## 2026-09-09 — Snapshot generation queue recovery

At product commit `d70d072a`, workstation snapshot persistence now records the
generation owned by the in-flight PUT. If a newer local layout or tool edit
arrives before that request settles, the trailing save retries against the
newest generation instead of incorrectly concluding that the edit was already
persisted. This closes the full-suite timing race that could leave a promoted
watchlist filter visible locally but absent from the canonical workspace
snapshot. The regression test holds the first PUT open while the newer timer
fires and verifies the second PUT is issued only after the older request
settles.

The focused workspace-store suite passed `71/71`, the Chart Plot Library suite
passed `25/25`, frontend type-check and diff checks passed, and the exact
Docker-backed gate passed backend unit/integration (`1,372`/`387`, `81.10%`
combined coverage), frontend Vitest (`988/988`), build, compose/provider/
runner and research-runner probes, stack health, performance, uPlot,
acceptance policy, and functional Playwright (`165` passed, `107` documented
skips across `272`). Visual parity remains `98/104` with exactly the six
established state-oracle diffs: `watchlist-column-editor-open.png` at
visual-1080p-100/125 and `workspace-floating.png` at
visual-1080p-100/125 and 1440p-100/125. The gate exits at the visual stage only
for those established diffs; scoped teardown removed all stack resources and
test sessions cleanly. No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed.

R1 remains open for full canonical family population, W1/MN provider history,
placeholder disposition, explicit cadence/effective-time evidence beyond the
timing metadata, rebuildable adjustment-factor/raw-versus-derived storage
provenance, and broader continuity/readiness proof; R2-R7 remain open.

## 2026-09-09 — OHLCV range lineage and adjustment provenance accessibility

At product commit `9a80c8f7`, canonical OHLCV range readiness now returns
explicit provider/derived/unknown bar counts, source lineage, derived source
timeframes, and an adjustment-provenance envelope. The contract deliberately
keeps provider-native event-level adjustment factors opaque when the provider
does not expose them, while identifying derived coarse bars as inheriting the
canonical adjusted D1 contract and leaving `factor_version` unreported rather
than inventing one. The Coverage Summary tool exposes the same range evidence
through a hidden accessible description; visible layout, pixels, provider
precedence, fallback behavior, storage policy, and visual acceptance policy
remain unchanged.

The focused frontend utility/consumer tests passed `6/6`; the focused backend
coverage router tests passed `5/5` (the intentionally narrow backend command
still exits non-zero only when the repository-wide coverage floor is applied).
Frontend type-check, Ruff, format, and diff checks passed. The exact
Docker-backed integration gate passed backend unit/integration (`1,372`/`387`,
`81.10%` combined coverage), frontend Vitest (`987/987`), build,
compose/provider/runner and research-runner probes, stack health, performance,
uPlot, acceptance policy, and functional Playwright (`165` passed, `107`
documented skips across `272`). Visual parity remains `98/104` with exactly
the six established state-oracle diffs: `watchlist-column-editor-open.png` at
visual-1080p-100/125 and `workspace-floating.png` at
visual-1080p-100/125 and 1440p-100/125. The gate exits at the visual stage only
for those established diffs; scoped teardown removed all stack resources and
test sessions cleanly. No baseline, mask, threshold, skip, visual, provider,
fallback, or acceptance policy changed.

R1 remains open for full canonical family population, W1/MN provider history,
placeholder disposition, explicit cadence/effective-time evidence beyond the
timing metadata, rebuildable adjustment-factor/raw-versus-derived storage
provenance, and broader continuity/readiness proof; R2-R7 remain open.

## 2026-09-09 — Exact-tip gate after Market Map canvas accessibility

At product commit `61304578`, large canvas Market Maps now expose one hidden,
non-visual summary through `aria-describedby`. It reports the canonical source,
period/timeframe and adjustment, colour/area metrics, visible members and
groups, evaluated/requested coverage, freshness, colour/area coverage, warning
and exclusion counts, and current selection count without duplicating every
tile in the accessibility tree. The existing canvas label, keyboard member
search/selection path, layout, provider precedence, fallback behavior, and
visual output remain unchanged.

The focused Market Map accessibility utility and canvas consumer regressions
passed `38/38`; frontend type-check and diff check passed. The exact
Docker-backed integration gate passed backend unit/integration (`1,371`/`387`)
with `81.10%` combined coverage, frontend Vitest (`985/985`), build,
compose/provider/runner and stack-health probes, functional Playwright
(`165` passed, `107` documented skips across `272`), performance, uPlot, and
acceptance-policy checks. Visual parity remains `98/104` with exactly the six
established state-oracle diffs: `watchlist-column-editor-open.png` at
visual-1080p-100/125 and `workspace-floating.png` at
visual-1080p-100/125 and 1440p-100/125. The gate exits at the visual stage only
for those established diffs; scoped teardown removed all stack resources and
test sessions cleanly. No baseline, mask, threshold, skip, visual, provider,
fallback, or acceptance policy changed.

R1 remains open for full canonical family population, W1/MN provider history,
placeholder disposition, explicit cadence/effective-time evidence beyond the
timing metadata, and rebuildable adjustment-factor/raw-versus-derived storage
provenance; R2-R7 remain open.

## 2026-09-09 — Exact-tip gate after Study artifact accessibility

At product commit `44496b2a`, Study Lab and persisted Study Results now share
one non-visual accessibility description for scalar/boolean values, aligned
series coverage, ranges, tables, bars, histograms, scatter pairs, heatmaps,
dashboards, events, and breadth-history artifacts. The summaries state the
shape and finite/missing coverage without changing rendered pixels, layout,
artifact immutability, promotion contracts, provider precedence, fallback
behavior, or visual policy.

The focused accessibility and consumer regressions passed `64/64`; frontend
type-check and diff check passed. An initial full-gate browser run had one
isolated `F8u-filter` timeout while waiting for a workspace snapshot response;
the same case passed independently against a freshly rebuilt stack in `5.2s`.
The complete exact Docker-backed gate was then rerun: backend unit/integration
passed (`1,371`/`387`), combined backend coverage was `81.09%`, frontend
Vitest passed `983/983`, build, compose/provider/runner and health probes,
performance, uPlot, and acceptance-policy checks passed, and functional
Playwright passed `165` with `107` documented skips across `272`. Visual
parity remains `98/104` with exactly the six established state-oracle diffs:
`watchlist-column-editor-open.png` at visual-1080p-100/125 and
`workspace-floating.png` at visual-1080p-100/125 and 1440p-100/125. The gate
therefore exits at the visual stage only for those pre-existing diffs; scoped
teardown removed all stack resources and test sessions cleanly. No baseline,
mask, threshold, skip, visual, provider, fallback, or acceptance policy
changed.

R1 remains open for full canonical family population, W1/MN provider history,
placeholder disposition, explicit cadence/effective-time evidence beyond the
timing metadata, and rebuildable adjustment-factor/raw-versus-derived storage
provenance; R2-R7 remain open.

## 2026-09-09 — Exact-tip gate after chart history provenance accessibility

At product commit `960fd82f`, the typed OHLCV chart contract now retains the
existing derived/source lineage fields (`is_derived`, source timeframe,
derivation method, materialization time, source bar count, and observed
bounds). The chart's existing accessible `Chart workspace` region now adds a
non-visual loaded-range summary covering bar count, timeframe, adjustment
state, and provider/derived/unknown lineage; the selected-bar tooltip exposes
the same provider-observed or derived description. No provider is invented and
no chart pixels, layout, precedence, fallback, storage, or visual acceptance
policy changed.

The focused provenance utility and ETF holdings view regressions passed
(`9/9`), frontend type-check passed, and the diff check passed. The exact
Docker-backed integration gate passed backend unit and integration tests
(`1,371`/`387`), `81.09%` combined coverage, frontend Vitest (`975/975`),
build, compose/provider/runner and health probes, functional Playwright
(`165` passed, `107` documented skips across `272`), performance, uPlot, and
acceptance-policy checks. Visual parity remains `98/104` with the same six
established state-oracle diffs: column editor at visual-1080p-100/125 and
floating workspace at visual-1080p-100/125 and 1440p-100/125. The gate exits at
the visual stage only because those established diffs remain; scoped teardown
removed all stack resources and test sessions cleanly. No baseline, mask,
threshold, skip, visual, provider, fallback, or acceptance policy changed.

R1 remains open for full canonical family population, W1/MN provider history,
placeholder disposition, explicit cadence/effective-time evidence beyond the
new timing metadata, and rebuildable adjustment-factor/raw-versus-derived
storage provenance; R2-R7 remain open.

## 2026-09-09 — Exact-tip gate after ETF history-point provenance accessibility

At product commit `a8b3a2cf`, the ETF weight-evolution track now exposes each
point's existing disclosure and lineage context through an accessible labelled
`role="img"` track and point metadata titles. The point-specific contract
includes composition date, weight, as-of/known/published timestamps, provider,
source identifier, cadence, parser version, timing provenance, and the
provider/derived provenance envelope. This is a disclosure surface only: no
provider fact is invented and no workstation layout, precedence, fallback,
storage, or visual acceptance policy changed.

The focused ETF holdings view regression passed (`5/5`), frontend type-check
passed, and the diff check passed. The exact Docker-backed integration gate
passed backend unit and integration tests (`1,371`/`387`), `81.09%` combined
coverage, frontend Vitest (`975/975`), build, compose/provider/runner and
health probes, functional Playwright (`165` passed, `107` documented skips
across `272`), performance, uPlot, and acceptance-policy checks. Visual parity
remains `98/104` with the same six established state-oracle diffs: column
editor at 1080p 100/125 and floating workspace at 1080p 100/125 and 1440p
100/125. The gate exits at the visual stage only because those established
diffs remain; scoped teardown removed all stack resources and test sessions
cleanly. No baseline, mask, threshold, skip, visual, provider, fallback, or
acceptance policy changed.

R1 remains open for full canonical family population, W1/MN provider history,
placeholder disposition, explicit cadence/effective-time evidence beyond the
new timing metadata, and rebuildable adjustment-factor/raw-versus-derived
storage provenance; R2-R7 remain open.

## 2026-09-09 — Exact-tip gate after ETF history-point provenance

At product commit `9365671f`, ETF constituent timelines and weight-evolution
points now carry the disclosure and lineage fields already available on
snapshot-date history: publication time, source identifier, cadence, parser
version, timing provenance, and the source/provider provenance envelope. The
backend keeps these fields point-specific, while the typed frontend contract
can expose them without changing the visible workstation layout or inventing
provider facts.

The focused Docker-backed historical-weight-mover regression passed (`1`
passed, `64` deselected); the affected ETF holdings frontend unit suite passed
(`5/5`), frontend type-check passed, and Ruff, format, and diff checks passed.
The exact Docker-backed integration gate passed backend unit and integration
tests (`1,371`/`387`), `81.09%` combined coverage, frontend Vitest (`975/975`),
build, compose/provider/runner and health probes, functional Playwright
(`165` passed, `107` documented skips across `272`), performance, uPlot, and
acceptance-policy checks. Visual parity remains `98/104` with the same six
established state-oracle diffs: column editor at 1080p 100/125 and floating
workspace at 1080p 100/125 and 1440p 100/125. The gate exits at the visual
stage only because those established diffs remain; scoped teardown removed all
stack resources and test sessions cleanly. No baseline, mask, threshold, skip,
visual, provider, fallback, or acceptance policy changed.

R1 remains open for full canonical family population, W1/MN provider history,
placeholder disposition, explicit cadence/effective-time evidence beyond the
new timing metadata, and rebuildable adjustment-factor/raw-versus-derived
storage provenance; R2-R7 remain open.

## 2026-09-09 — Exact-tip gate after ETF disclosure provenance

At product commit `690c1979`, the authenticated ETF snapshot-date history
endpoint now carries publication time, cadence, parser version, source
identifier, and the explicit timing-basis map already retained in snapshot
legal metadata. The frontend's compact snapshot selector exposes the same
disclosure context through native option titles, keeping date selection
keyboard/assistive-friendly without changing the rendered layout. No timing
is promoted to a provider fact when it is absent; provider precedence,
fallback routing, and visual policy remain unchanged.

The focused Docker-backed ETF dates regression passed (`1/1`), the affected
ETF holdings frontend unit suite passed (`5/5`), frontend type-check passed,
and Ruff, format, and diff checks passed. The exact Docker-backed integration
gate passed backend unit and integration tests (`1,371`/`387`), `81.09%`
combined coverage, frontend Vitest (`975/975`), build, compose/provider/runner
and health probes, functional Playwright (`165` passed, `107` documented
skips across `272`), performance, uPlot, and acceptance-policy checks. Visual
parity remains `98/104` with the same six established state-oracle diffs:
column editor at 1080p 100/125 and floating workspace at 1080p 100/125 and
1440p 100/125. The gate exits at the visual stage only because those
established diffs remain; scoped teardown removed all stack resources and test
sessions cleanly. No baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

R1 remains open for full canonical family population, W1/MN provider history,
placeholder disposition, explicit cadence/effective-time evidence beyond the
new timing metadata, and rebuildable adjustment-factor/raw-versus-derived
storage provenance; R2-R7 remain open.

## 2026-09-09 — Exact-tip gate after disclosure timing provenance

At product commit `a5be2a2f`, benchmark-family coverage now preserves the
origin of each disclosure timestamp instead of treating every date as equally
authoritative. Dated and latest provider refreshes classify composition date,
as-of date, known-at time, and publication time as provider-reported,
requested-date/profile fallbacks, or ingestion-time fallbacks; SEC fallback
ingestion records filing acceptance as the known/publication basis. The
provenance map is retained in snapshot legal metadata, serialized by the
coverage API, and exposed in typed Market Map/workstation readiness labels.
No timestamp is inferred beyond the existing documented fallback, and visible
layout, provider precedence, fallback routing, and visual policy remain
unchanged.

The focused timing regressions passed (`3` tests; the narrow command exits
non-zero only because the repository-wide `55%` coverage threshold is not met
by that intentionally small slice); Ruff, format, diff, frontend type-check,
and affected Market Map units (`36/36`) passed. The exact Docker-backed
integration gate passed backend unit and integration tests (`1,371`/`387`),
`81.09%` combined coverage, frontend Vitest (`975/975`), build,
compose/provider/runner and health probes, functional Playwright (`165`
passed, `107` documented skips across `272`), performance, uPlot, and
acceptance-policy checks. Visual parity remains `98/104` with the same six
established state-oracle diffs: column editor at 1080p 100/125 and floating
workspace at 1080p 100/125 and 1440p 100/125. The gate exits at the visual
stage only because those established diffs remain; scoped teardown removed all
stack resources and test sessions cleanly. No baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed.

R1 remains open for full canonical family population, W1/MN provider history,
placeholder disposition, explicit cadence/effective-time evidence beyond the
new timing basis, and rebuildable adjustment-factor/raw-versus-derived storage
provenance; R2-R7 remain open.

## 2026-09-09 — Exact-tip gate after unresolved member accounting

At product commit `29d5407a`, benchmark-family member-bar readiness now keeps
excluded holding rows explicit: canonical members, placeholder members, and
unresolved member rows are counted separately, with
`unresolved_member_count` carried through the API and typed Market Map/
workstation provenance surfaces. The readiness denominator therefore cannot
silently shrink when a holding row has no resolved instrument; visible layout,
provider precedence, fallback behavior, and visual policy remain unchanged.

Focused family-readiness coverage passed `23/23`; the targeted unresolved-row
regression passed, affected Market Map units passed `36/36`, frontend
type-check passed, and Ruff, format, and diff checks passed. The exact
Docker-backed integration gate passed backend unit and integration tests
(`1,371`/`387`), `81.08%` combined coverage, frontend Vitest (`975/975`),
build, compose/provider/runner and health probes, functional Playwright
(`165` passed, `107` documented skips across `272`), performance, uPlot, and
acceptance-policy checks. Visual parity remains `98/104` with the same six
established state-oracle diffs: column editor at 1080p 100/125 and floating
workspace at 1080p 100/125 and 1440p 100/125. The gate exits at the visual
stage only because those established diffs remain; scoped teardown removed all
stack resources and test sessions cleanly. No baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed.

R1 remains open for full canonical family population, W1/MN provider history,
placeholder disposition, explicit cadence/effective-time evidence, and
rebuildable adjustment-factor/raw-versus-derived storage provenance; R2-R7
remain open.

## 2026-09-09 — Exact-tip gate after mixed lineage provenance assertion

At product commit `b81cda8a`, the Market Map regression now asserts the
strict `provider_and_derived` lineage label and the provider-only, derived-only,
and mixed member split in the hidden workstation provenance evidence. This
keeps the UI contract aligned with the backend's per-member aggregation while
leaving visible layout, provider precedence, fallback behavior, and visual
acceptance policy unchanged.

The exact Docker-backed integration gate passed backend unit and integration
tests (`1,371`/`387`), `81.08%` combined coverage, frontend Vitest (`975/975`),
build, compose/provider/runner and health probes, functional Playwright (`165`
passed, `107` documented skips across `272`), performance, uPlot, and
acceptance-policy checks. Visual parity remains `98/104` with the same six
established state-oracle diffs: column editor at 1080p 100/125 and floating
workspace at 1080p 100/125 and 1440p 100/125. Scoped teardown removed all stack
resources and test sessions cleanly. No baseline, mask, threshold, skip,
provider, fallback, or acceptance policy changed.

R1 remains open for full canonical family population, W1/MN provider history,
placeholder disposition, explicit cadence/effective-time evidence, and
rebuildable adjustment-factor/raw-versus-derived storage provenance; R2-R7
remain open.

## 2026-09-09 — Exact-tip gate after mixed member-bar lineage

At product commit `3562919a`, benchmark-family member-bar readiness now
distinguishes provider-only, derived-only, and mixed members in addition to the
aggregate provider/derived member and bar counts. Mixed members are aggregated
once before coverage and readiness floors, while the typed Market Map and
workstation provenance labels carry the split as assistive evidence. The
`source_lineage` contract is constrained to its four known states; visible
layout and provider/fallback policy remain unchanged.

Focused coverage/readiness integration tests passed `9/9`; frontend unit tests
covering the affected Market Map/store surfaces passed `107/107`, Ruff,
format, and frontend type-check passed. The exact Docker-backed integration
gate passed backend unit and integration tests (`1,371`/`387`), `81.08%`
combined coverage, frontend Vitest (`975/975`), build, compose/provider/runner
and health probes, functional Playwright (`165` passed, `107` documented
skips across `272`), performance, uPlot, and acceptance-policy checks.
Visual parity remains `98/104` with the same six established state-oracle
diffs: column editor at 1080p 100/125 and floating workspace at 1080p 100/125
and 1440p 100/125. Scoped teardown removed all stack resources and test
sessions cleanly. No baseline, mask, threshold, skip, provider, fallback, or
acceptance policy changed.

R1 remains open for full canonical family population, W1/MN provider history,
placeholder disposition, explicit cadence/effective-time evidence, and
rebuildable adjustment-factor/raw-versus-derived storage provenance; R2-R7
remain open.

## 2026-09-09 — Exact-tip gate after member-bar source lineage

At commit `ea1118cc`, benchmark-family member-bar readiness now reports
provider-versus-derived member and bar counts plus a stable `source_lineage`
(`provider_only`, `derived_only`, `provider_and_derived`, or `unavailable`).
The aggregation deduplicates a member that spans provider and derived periods,
so coverage cannot exceed 100%; readiness floors apply to the combined
per-member bar history. The lineage is carried through the typed Market Map
and workstation provenance labels without changing visible layout or provider
precedence. Focused coverage/readiness integration tests passed `9/9`, Ruff
and frontend type-check passed.

The exact Docker-backed integration gate passed repository/workstream,
dependency/lint/format/type-check, migration compatibility, backend unit and
integration tests (`1,371`/`387`, `81.08%` combined coverage), frontend Vitest
(`975/975`), uPlot and visual-policy checks, frontend build, compose/provider/
runner and stack-health probes, and functional Playwright (`165` passed,
`107` documented skips across `272`). Visual parity completed `104` cases with
`98` passes and exactly the six established state-oracle diffs:
watchlist-column-editor-open at 1080p 100/125 and workspace-floating at 1080p
100/125 and 1440p 100/125. Scoped teardown removed all containers, volumes,
network, images, and test sessions cleanly. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

R1 remains open: provider adjustment factors and versioned/rebuildable raw
versus derived storage are not yet available; canonical family population is
still partial (20 mapped roles, 12 unavailable, 0 failed; 56 capped member
slots yielded 44 instruments and 94,540 adjusted D1 bars through 2025-12-31,
with provider W1/MN still zero). Full family population, placeholder
disposition, explicit cadence/effective-time evidence beyond exposed
timestamps, and R2-R7 evidence remain open.

## 2026-09-09 — Exact-tip gate after explicit adjustment provenance

At commit `0c1f1b0b`, canonical dataset-state responses now expose nested
adjustment provenance. Provider observations identify their requested mode
(`split_adjusted` or `raw`) and explicitly mark adjustment factors as
provider-native and opaque/unavailable; locally derived W1/MN observations
identify inheritance from canonical D1. `factor_version` remains null because
the provider contracts do not expose per-event factors; no factors are
fabricated and no prices, precedence, fallback, or storage policy changed.
The typed coverage consumer accepts the existing `extra_data` envelope without
changing rendered UI behavior. Focused market-data, derived-timeframe,
coverage-router, Ruff, format, diff, and frontend type checks passed.

The exact Docker-backed integration gate passed repository/workstream,
dependency/lint/format/type-check, migration compatibility, backend unit and
integration tests (`1,371`/`387`, `81.07%` combined coverage), frontend Vitest
(`975/975`), uPlot and visual-policy checks, frontend build, compose/provider/
runner and stack-health probes, and functional Playwright (`165` passed,
`107` documented skips across `272`). Visual parity completed `104` cases with
`98` passes and exactly the six established state-oracle diffs:
watchlist-column-editor-open at 1080p 100/125 and workspace-floating at 1080p
100/125 and 1440p 100/125. Scoped teardown removed all containers, volumes,
network, images, and test sessions cleanly. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed.

R1 remains open: provider adjustment factors and versioned/rebuildable raw
versus derived storage are not yet available; canonical family population is
still partial (20 mapped roles, 12 unavailable, 0 failed; 56 capped member
slots yielded 44 instruments and 94,540 adjusted D1 bars through 2025-12-31,
with provider W1/MN still zero). Full family population, placeholder
disposition, explicit cadence/effective-time evidence beyond exposed
timestamps, and R2-R7 evidence remain open.

## 2026-09-09 — Exact-tip gate after SEC publication provenance

At commit `e19f1b76604e371d74b976cfcfe42da9609ddd48`, the SEC fallback
ingestion path now retains the filing acceptance instant as both `known_at` and
`published_at`; dated and latest refresh routes normalize that metadata to UTC
while retaining wall-clock fallback behavior for providers that do not report a
publication time. Focused adapter, refresh, holdings, EDGAR, and Ruff checks
passed. The exact integration gate passed repository/workstream,
dependency/lint/format/type-check, migration compatibility, backend unit and
integration tests (`1,370`/`387`, `81.07%` combined coverage), frontend Vitest
(`975/975`), uPlot and visual-policy checks, frontend build, compose/provider/
runner and stack-health probes, and functional Playwright (`165` passed,
`107` documented skips across `272`). Visual parity completed `104` cases with
`98` passes and exactly the six established state-oracle diffs:
watchlist-column-editor-open at 1080p 100/125 and workspace-floating at 1080p
100/125 and 1440p 100/125. Scoped teardown removed all containers, volumes,
network, images, and test sessions cleanly. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed. R1 remains
open for full canonical family population, placeholder disposition, explicit
cadence/effective-time evidence beyond exposed timestamps,
adjustment-factor/version provenance beyond state metadata,
raw-versus-derived storage decisions, and R2-R7 evidence.

## 2026-09-09 — Exact-tip gate after cadence/parser provenance

At commit `32b005ab`, the exact integration gate passed repository/workstream,
dependency/lint/format/type-check, migration compatibility, backend unit and
integration tests (`1,370`/`387`, `81.07%` combined coverage), frontend Vitest
(`975/975`), uPlot and visual-policy checks, frontend build, compose/provider/
runner and stack-health probes, and functional Playwright (`165` passed, `107`
documented skips across `272`). Visual parity completed `104` cases with `98`
passes and exactly the six established state-oracle diffs: watchlist-column-
editor-open at 1080p 100/125 and workspace-floating at 1080p 100/125 and
1440p 100/125. Scoped teardown removed all containers, volumes, network,
images, and test sessions cleanly. Holdings coverage now exposes retained
cadence and parser-version metadata through the API and workstation readiness
surfaces; no cadence is inferred when the source does not report one. No
visual baseline, mask, threshold, skip, provider, fallback, or acceptance
policy changed. R1 and R2-R7 remain open.

## 2026-09-09 — Exact-tip gate after frontend disclosure provenance

At commit `a1c41196`, the exact integration gate passed repository/workstream,
dependency/lint/format/type-check, migration compatibility, backend unit and
integration tests (`1,370`/`387`, `81.06%` combined coverage), frontend Vitest
(`975/975`), uPlot and visual-policy checks, frontend build, compose/provider/
runner and stack-health probes, and functional Playwright (`165` passed, `107`
documented skips across `272`). Visual parity completed `104` cases with `98`
passes and exactly the six established state-oracle diffs: watchlist-column-
editor-open at 1080p 100/125 and workspace-floating at 1080p 100/125 and
1440p 100/125. Scoped teardown removed all containers, volumes, network,
images, and test sessions cleanly. The Market Map and workstation readiness
surfaces now carry publication date, known-at timing, and source identifier
alongside the existing canonical coverage evidence; the frontend fixture now
resets its shared source state between tests. No visual baseline, mask,
threshold, skip, provider, fallback, or acceptance policy changed. R1 and
R2-R7 remain open.

## 2026-09-09 — Exact-tip gate after holdings timing provenance

At commit `c49db774`, the exact integration gate passed repository/workstream/
dependency/lint/format/type-check, migration compatibility, backend unit and
integration tests (`1,370`/`387`, `81.06%` combined coverage), frontend Vitest
(`975/975`), uPlot and visual-policy checks, frontend build (`510` modules),
compose/provider/runner and stack-health probes, and functional Playwright
(`165` passed, `107` documented skips across `272`). Visual parity completed
`104` cases with `98` passes and exactly the six established state-oracle diffs:
watchlist-column-editor-open at 1080p 100/125 and workspace-floating at 1080p
100/125 and 1440p 100/125. Scoped teardown removed all containers, volumes,
network, images, and test sessions cleanly. No visual baseline, mask, threshold,
skip, provider, fallback, or acceptance policy changed. R1 and R2-R7 remain
open.

## 2026-09-09 — Constituent timelines follow effective-date revisions

Constituent history now selects the latest known disclosure for each effective
composition date before emitting the timeline. Corrected same-date disclosures
remain available in source history, while the constituent chart no longer shows
duplicate dates or revision-only points. The focused Docker-backed regression
passed `1/1`. At commit `e228f13d`, the exact gate passed backend
unit/integration (`1,370`/`387`, `81.06%` combined coverage), frontend Vitest
(`975/975`), build, contracts, probes, stack health, and functional Playwright
(`165` passed, `107` documented skips). Visual parity remains `98/104` with the
six established state-oracle diffs; scoped teardown was clean. R1 still needs
full family population, placeholder disposition, explicit cadence/effective-time
evidence, adjustment-factor/version provenance, raw-versus-derived decisions,
and R2-R7.

## 2026-09-09 — Weight evolution follows effective-date revisions

Weight-evolution analytics now use the same latest-known-per-composition-date
selection as rebalance transitions. Corrected disclosures remain retained in
the audit trail, while historical series no longer contain duplicate points
or revision-induced deltas for one effective date. The focused Docker-backed
regression passed `1/1`. At commit `c6b20f95`, the exact gate passed backend
unit/integration (`1,370`/`387`, `81.06%` combined coverage), frontend Vitest
(`975/975`), build, contracts, probes, stack health, and functional Playwright
(`165` passed, `107` documented skips). Visual parity remains `98/104` with
the six established state-oracle diffs; scoped teardown was clean. R1 still
needs multi-date family population, explicit cadence/effective-time evidence,
adjustment-factor/version provenance, placeholder disposition, raw-versus-
derived decisions, and R2-R7.

## 2026-09-09 — Rebalance timelines collapse same-date disclosure revisions

Holdings ingestion intentionally retains revised issuer disclosures for audit,
but the rebalance transition timeline now collapses revisions sharing one
effective composition date and compares the latest known revision. This keeps
source history intact while preventing a corrected disclosure from appearing
as a phantom rebalance boundary. The focused Docker-backed regression passed
`1/1` (with the suite-wide coverage threshold intentionally disabled for the
single-test run). At commit `c0e8ea24`, the exact gate passed backend
unit/integration (`1,370`/`387`, `81.06%` combined coverage), frontend Vitest
(`975/975`), build, contracts, probes, stack health, and functional Playwright
(`165` passed, `107` documented skips). Visual parity remains `98/104` with
the six established state-oracle diffs; scoped teardown was clean. R1 still
needs multi-date population, explicit cadence/effective-time evidence,
adjustment-factor/version provenance, placeholder disposition, raw-versus-
derived decisions, and R2-R7.

## 2026-09-09 — Provider dataset states expose adjustment provenance

Provider-backed dataset state now records the observed bar count, whether the
payload was adjusted, the adjustment mode (`split_adjusted` or `raw`), the
provider-observation source kind, and the provider source identifier. Coverage
consumers can distinguish an explicit provider observation from provider-neutral
derived lineage without changing provider precedence or fallback policy.
The focused market-data/coverage checks passed `19/19`. At commit `4ba6285b`,
the exact gate passed backend unit/integration (`1,370`/`387`, `81.06%` combined
coverage), frontend Vitest (`975/975`), build, contracts, probes, stack health,
and functional Playwright (`165` passed, `107` documented skips). Visual parity
remains `98/104` with the six established state-oracle diffs; scoped teardown
was clean. R1 remains open for adjustment-factor/version provenance beyond
this state label, full family population, placeholder disposition,
raw-versus-derived storage decisions, rebalance continuity, and R2-R7.

## 2026-09-09 — Derived coarse coverage now has canonical state lineage

Derived W1/MN materialization now writes provider-neutral `InstrumentDatasetState`
records alongside the derived rows. Coverage consumers can therefore see the
source timeframe (`D1`), deterministic aggregation method, adjustment mode,
derived-row count, excluded provider-period count, coverage bounds, freshness
status, and materialization version without inferring provenance from individual
bars. Focused derivation/coverage coverage passes `7/7`. At commit `da12b587`,
the exact gate passed backend unit/integration (`1,370`/`387`, `81.06%` combined
coverage), frontend Vitest (`975/975`), build, contracts, probes, stack health,
and functional Playwright (`165` passed, `107` documented skips). Visual parity
remains `98/104` with the six established state-oracle diffs; scoped teardown
was clean. This is an R1 provenance/readiness closure for derived coarse data
only; full family population, point-in-time adjustment provenance/continuity,
and R2-R7 remain open.

## 2026-09-09 — Queue historical bounds are timezone-safe

Canonical history queue payloads now normalize the requested historical end
bound to an explicit UTC ISO value before the worker job is created. Combined
with order-independent timeframe identity, retries using equivalent naive or
timezone-aware bounds cannot split status/idempotence records or silently use
the host's local timezone. Focused history/bootstrap coverage remains `33/33`.
The exact gate at commit `d420350c` passed backend unit/integration
(`1,370`/`387`, `81.06%` combined coverage), frontend Vitest (`975/975`),
build, contracts, probes, stack health, and functional Playwright (`165`
passed, `107` documented skips). Visual parity remains `98/104` with the six
established state-oracle diffs; scoped teardown was clean. This is an R1 queue
identity/serialization closure only; canonical family population,
point-in-time provenance/continuity, and R2-R7 remain open.

## 2026-09-09 — Canonical history queue identity is order-independent

The shared canonical history job key now treats timeframe requests as an
unordered set: retries using `D1,W1,MN` and `MN,W1,D1` resolve to the same
instrument/bound identity, while the worker still receives the caller's
requested order. This prevents duplicate provider work during bounded family
and watchlist maintenance. Focused history/bootstrap coverage passes `33/33`.
At commit `df66cd1f`, the exact gate passed backend unit/integration
(`1,370`/`387`, `81.06%` combined coverage), frontend Vitest (`975/975`),
build, contracts, probes, stack health, and functional Playwright (`165`
passed, `107` documented skips). Visual parity remains `98/104` with the six
established state-oracle diffs; teardown removed all scoped resources. This is
an R1 maintenance-idempotence closure only; canonical family population,
point-in-time provenance/continuity, and R2–R7 remain open.

## 2026-09-08 — Provider-enabled coarse reads share canonical history

The normal provider-enabled range, latest-page, and historical-page OHLCV
paths now reconcile partial provider W1/MN coverage with the complete
materialized cache derived from canonical adjusted D1 evidence. Provider rows
retain calendar-period precedence; uncovered periods expose explicit derived
lineage, and all period comparisons normalize database timestamps to UTC. The
focused service/router/derivation gate passes `25/25`. At commit `7bbca0ea`,
the exact integration gate passed backend unit/integration (`1,370`/`387`,
`81.06%` combined coverage), frontend Vitest (`975/975`), build, contracts,
runner probes, stack health, and functional Playwright (`165` passed, `107`
documented skips). Visual parity remains `98/104` with the six established
watchlist-column-editor and workspace-floating state-oracle diffs. This is an
R1 read-consistency closure only; canonical family population, placeholders,
adjustment/version provenance, raw-versus-derived redesign, rebalance
continuity, and R2–R7 remain open. No visual or provider policy changed.

## 2026-09-08 — Merge partial provider coarse reads with canonical derivations

Local and chart OHLCV reads now reconcile partial provider W1/MN coverage with
derived periods from persisted canonical adjusted D1 evidence. Provider rows
continue to own their calendar periods; derived rows fill only uncovered
periods and retain explicit lineage. The read path avoids rebuilding an
already-materialized derived cache on every request, while still completing a
partial provider cache when no derived periods exist. Focused mixed-source
coverage passes `13/13`, and the exact full gate at commit `2ef85fd0` passes all
non-visual stages and functional Playwright (`165` passed, `107` documented
skips); visual parity remains `98/104` with the six established state-oracle
diffs. This closes a local read-consistency gap only; canonical population,
placeholder disposition, adjustment provenance, rebalance continuity, and
R2–R7 remain open.

## 2026-09-08 — Canonical derived W1/MN materialization policy implemented

The maintenance history path now materializes W1 and MN bars from persisted
canonical adjusted D1 bars when providers do not expose those coarse
timeframes. Aggregation uses XNYS calendar periods, preserves observed source
bounds/counts, never forward-fills missing sessions, and stores explicit
`is_derived`, source-timeframe, derivation-method, and timestamp lineage on each
row. Provider-supplied W1/MN rows take precedence for their calendar period;
derived rows have no provider source ID and are never presented as provider
evidence. The local OHLCV response exposes this metadata.

The migration and service regressions passed the complete backend unit suite
(`1,361/1,361`, `67.40%` unit coverage) and Docker-backed integration suite
(`386/386`), including PostgreSQL migration application. This closes the
implementation seam for cached coarse timeframes but does not claim family
readiness: full canonical population, placeholder disposition, rebalance
continuity, and the R2–R7 gates remain open. No provider, fallback, visual, or
acceptance policy was changed.

## 2026-09-09 — Bounded Nasdaq family fan-out recheck

The exact dated QQQ/QQQE member set was rerun with the configured bounded
history queue. The earlier empty family result was not reproduced: all `54/54`
queued canonical member D1 jobs completed without worker errors, with `53`
meeting the 252-bar floor. The run still has no W1/MN bars and does not prove
rebalance continuity or family-wide readiness; those remain explicit R1 gaps.

## 2026-09-09 — Mixed-timeframe queue reproduction remains healthy

Four concurrent canonical seeded ARQ jobs (`AAPL`, `SPY`, `QQQ`, `NVDA`) ran
`MN/W1/D1` with a dated end and all completed. Expected MN/W1 no-data errors
fell through to the configured chain while D1 remained available; a fresh XLK
mixed-timeframe job returned the same MN/W1 coverage errors and persisted
`2,344` D1 bars. This rules out the mixed-timeframe circuit path as the cause
of the earlier empty family queue. The remaining investigation is specific to
the actual canonical snapshot member set, symbol provenance, or transient
provider conditions; no provider policy change is justified.

## 2026-09-09 — Canonical Nasdaq ARQ worker path confirmed

The same fresh seeded stack was used to enqueue one bounded `task_bulk_fetch_instrument`
job for canonical NVDA (`D1`, end `2025-12-31`). The real ARQ worker returned
`{'D1': 2344}` and persisted the history successfully. Together with the QQQ
service-path probe below, this confirms the worker and provider binding path for
representative symbols; the earlier family queue's empty result still needs a
bounded concurrency/rate-limit investigation and does not establish family
readiness.

## 2026-09-09 — Canonical Nasdaq provider path rechecked through service runtime

After the earlier bounded Nasdaq-100 queue reported provider exhaustion, a
fresh seeded branch-scoped stack was inspected without changing provider
policy. QQQ, SPY, and NVDA each resolved to an active Nasdaq symbol binding,
and Nasdaq ranked first in the price-history chain. A bounded QQQ D1 fetch
through the same `bulk_fetch_instrument` service used by workers persisted
`2,344` adjusted bars through `2025-12-31` successfully. This narrows the
earlier empty-bar result to run-level conditions such as concurrent/rate-limit
exhaustion rather than a missing canonical symbol binding or Docker/network
failure; it does not claim family-wide history, continuity, or readiness.

## 2026-09-08 — Controlled network-scale workstation row-budget oracle

The branch now has an opt-in, explicitly non-canonical dense-universe fixture
(`E2E_SEED_LARGE_UNIVERSE=true`, capped at 10,000 identities) for exercising
real instrument browse, watchlist mutation, and workstation transport. The
first browser run exposed unbounded eager quote fan-out: 10,000 concurrent
requests exhausted browser resources. Quote hydration is now bounded to a
24-worker pool. The rerun passed `1/1` in `7.2s`: all 10,000 rows hydrated
over the network, the virtual watchlist reported `data-row-budget="within"`,
fewer than 100 DOM rows were mounted, and no critical browser diagnostics were
reported. This closes controlled transport/performance evidence only; the
fixture has no canonical provider bars and does not close R1/R2 canonical
history/readiness.

The required full integration gate after this product change passed all
non-visual stages, including backend `1356` unit and `386` integration tests,
frontend Vitest `974/974`, build/compose/provider/runner probes, and functional
Playwright `165` passed with `107` documented skips across `272`. Visual parity
remains `98/104` with the same six unchanged state-oracle diffs; no visual or
acceptance policy changed.

## 2026-09-09 — Isolate dated family refresh transactions

The first bounded all-family dated maintenance pass exposed a transaction-boundary defect:
when one provider/parser leg invalidated its SQLAlchemy transaction, later roles in the same
family reported the misleading `closed transaction inside context manager` error. Each mapped
role now runs inside its own savepoint, so a failed leg is rolled back without suppressing
independent roles. A regression test covers failure-then-success continuation, and the focused
service/worker tests passed (`6/6`).

The live branch worker retry for SP500 completed all four mapped roles (`4` refreshed, `0`
failed), persisted dated SEC snapshots, and queued `491` canonical member-history candidates
(`1` new, `490` already queued; `69` unresolved exclusions). The preceding all-family probe
also persisted SP400 (`3` refreshed, one role explicitly unavailable) and Russell 3000 (`1`
refreshed, three roles explicitly unavailable) snapshots; the remaining failures are not treated
as family readiness until rerun under the corrected boundary. No provider, fallback, credential,
visual, or acceptance policy changed. R1 remains open for complete family/root population,
placeholder disposition, W1/MN floors, and rebalance continuity.

The exact-tip full integration gate at the current documentation checkpoint
repeated the same boundary: backend unit/integration, frontend type-check/build,
compose/provider/runner probes, and functional Playwright all passed
(`165` passed, `107` documented skips across `272`). The four-project visual
matrix remained `98/104`, with only the established column-editor and floating
workspace state-oracle diffs. Teardown removed the scoped stack and generated
resources; no visual, provider, fallback, or acceptance policy changed.

## 2026-09-08 — Canonical Nasdaq-100 dated refresh and queue handoff

With the branch-scoped Docker stack available, a bounded dated `nasdaq100`
refresh ran for `2025-12-31` through the real worker path. The SEC-backed QQQ
and QQQE legs refreshed successfully (snapshot IDs `1` and `2`); value and
growth remained explicitly unavailable because no verified mapped proxy exists.
The committed snapshots queued seven canonical member-history jobs across
`MN`, `W1`, and `D1`, while reporting `197` unresolved/placeholder rows rather
than substituting them. A bounded classifier enriched `30` records with zero
failures and left `174` pending. Worker logs then showed the configured
provider chain exhausted for the requested member bars; no D1/W1/MN bars were
persisted in this fresh stack. This is a successful canonical refresh,
classification, and queue handoff, but it does not establish history,
continuity, or family readiness. No credentials, provider policy, or fallback
was changed.

## 2026-09-08 — Expose workstation dense-row budget telemetry

The virtual watchlist now exposes provider-neutral DOM telemetry for the
filtered row universe (`data-row-count`), mounted virtual window
(`data-rendered-row-count`), and the documented 10,000-row budget state. The
state is observational only: rows are never truncated or substituted, and
over-budget universes remain fully represented in the virtual canvas. Focused
coverage passes `68/68`, frontend type-check/build pass, and the full
branch-scoped gate passes all non-visual stages (`1353` unit, `386` integration,
frontend `974/974`, functional Playwright `165` passed with `106` documented
skips). Visual parity remains `98/104` with the same six unchanged state-oracle
diffs; no visual or acceptance policy changed. This enables a future live
network-hydrated workstation budget oracle but does not itself provide that
canonical 10,000-row evidence.

## 2026-09-08 — Configurable bounded canonical history fan-out

The R1 maintenance path now exposes the per-snapshot canonical member-history
queue ceiling as `BENCHMARK_FAMILY_MEMBER_HISTORY_MAX_INSTRUMENTS_PER_SNAPSHOT`
through Settings and Compose (default `5000`). Scheduled refresh and persisted-
snapshot backfill both pass the bound to the canonical queue; focused unit,
worker, and real-Postgres integration regressions pass. The full integration
gate passed all non-visual stages (backend `1353` unit + `386` integration,
combined coverage `80.98%`, frontend Vitest `974/974`, build/compose/provider and
runner probes, functional Playwright `165` passed with `106` documented skips).
Visual parity remains `98/104` with the same six unchanged state-oracle diffs;
no visual or acceptance policy was changed. Canonical family history/readiness,
development-tool vulnerability remediation, and R2-R7 evidence remain open.

## 2026-09-08 — Frontend dependency security audit

The authoritative npm audit found zero vulnerabilities in the `68` production
dependencies. The development graph has five findings: two critical Vitest /
coverage issues, one high Vite issue, and two moderate Vite/esbuild issues.
Available fixes require major upgrades (Vitest/coverage `5.x`, Vite `8.x`),
which are not being applied without compatibility work and a full gate rerun.
This is an explicit R6 remediation item; production runtime security is clean,
but the branch is not claiming a vulnerability-free development toolchain.

## 2026-09-08 — Bounded canonical Nasdaq-100 member-history queue

The fresh stack first confirmed that a QQQ snapshot containing `101` unresolved
rows queues zero history jobs. After the bounded classifier promoted two rows,
the canonical-only planner selected and queued `27` members while excluding `74`
unresolved/placeholders. Worker completion produced adjusted D1 bars for `23/27`
members (`45,199` bars); every covered member exceeded the `252`-bar floor
(minimum `613` bars), and the newest timestamp was bounded at
`2025-12-31`. W1/MN requests exhausted the configured provider chain with no
usable data, so `history_ready=false` and no continuity or complete-family
readiness is claimed. Cleanup removed all branch-scoped resources.

## 2026-09-08 — Bounded eight-family canonical enrichment pass

The fresh branch-scoped stack exercised all eight configured benchmark-family
refresh paths for the requested dated universe. Nine dated snapshots were
selected across eight profiles; the bounded classifier completed with zero
failures, enriched `181` records, and left `4,144` pending. The readiness query
found zero canonical D1/W1/MN member bars in this fresh stack, so no continuity
or analysis floor is claimed. Optional Massive and Alpha Vantage credentials
remained explicitly absent; cleanup removed all branch-scoped resources.

## 2026-09-08 — Bounded Russell 2000 canonical enrichment

The isolated stack refreshed the three mapped Russell 2000 legs for
`2025-12-31` with zero failures; equal-weight remained explicitly unavailable.
The bounded worker processed three profiles/snapshots, enriched `101` records,
and left `4,376` pending. Post-run classified/placeholder counts were IWM
`77/3`, IWN `34/3`, and IWO `59/3`. No D1/W1/MN bars were present, so
`history_ready=false` and no continuity or analysis floor is claimed. Cleanup
removed all branch-scoped resources.

## 2026-09-08 — Bounded S&P SmallCap 600 canonical enrichment

The isolated stack refreshed the three mapped SP600 legs for `2025-12-31`
with zero failures; equal-weight remained explicitly unavailable. The bounded
worker processed three profiles/snapshots, enriched `76` records, and left
`1,171` pending. Post-run classified/placeholder counts were IJR `60/2`,
SLYV `38/7`, and SLYG `6/114`. No D1/W1/MN bars were present, so
`history_ready=false` and no continuity or analysis floor is claimed. Repeated
missing optional-provider credentials remained explicit; cleanup removed all
branch-scoped resources.

## 2026-09-08 — Seeded authenticated top-down/source workflow slice

The seeded branch-scoped browser run passed `11/11` targeted flows in `44.1s`:
coverage and top-down watchlists (including scoped failure), locked/personal
Market Map handoff, family constituent drill-down and all-eight-family source
matrix, breadth loading/error semantics, role-aware family ratios, and three
recursive Python breadth contracts (series, tree, and comparison). This is
deterministic fixture-backed evidence; canonical live-provider traversal and
history remain separate R1/R2 gates. No critical browser diagnostics were
reported.

## 2026-09-08 — Bounded S&P MidCap 400 canonical enrichment

The isolated stack refreshed all three mapped SP400 legs for the requested
`2025-12-31` date (MDY's latest disclosed composition was `2025-09-30`), with
zero failures; equal-weight remained explicitly unavailable. The bounded
worker processed three profiles/snapshots, enriched `113` records, and left
`824` pending. Post-run classified/placeholder counts were MDY `76/0`, MDYV
`56/9`, and MDYG `47/9`. No D1/W1/MN bars were present, so `history_ready`
remains false and no continuity or analysis floor is claimed. Cleanup removed
all branch-scoped resources.

## 2026-09-08 — Authenticated keyboard/accessibility browser slice

Against the fresh branch-scoped stack, five authenticated Playwright flows
passed: workspace-tab roving focus, watchlist-row keyboard actions, workstation
shell-menu navigation, keyboard-help discovery with editor-focus suppression,
and drawing-flyout menu semantics/focus recovery. The run completed `5/5` in
`9.5s` with no critical browser diagnostics. This closes only the exercised
keyboard/accessibility slice; native-window, broader accessibility/security,
dense live-data, visual-oracle, and canonical history gates remain open.

## 2026-09-08 — Bounded S&P 500 canonical enrichment

After persisting SPY/RSP/SPYV/SPYG dated snapshots, the bounded enrichment
worker processed all four profiles and snapshots with zero failures, enriched
`78` records, and left `1,518` pending under the per-profile cap. Classified
plus placeholder counts were SPY `51/449`, RSP `50/453`, SPYV `40/403`, and
SPYG `25/117`. Missing optional Massive and Alpha Vantage credentials were
reported explicitly. No D1/W1/MN bars were present, so `history_ready=false`
and no continuity or analysis floor is claimed. Cleanup removed all
branch-scoped resources.

## 2026-09-08 — Bounded Russell 1000 canonical enrichment

After persisting IWB/IWD/IWF `2025-12-31` snapshots, the bounded enrichment
worker processed all three profiles and snapshots with zero failures, enriched
100 records, and left `2,176` pending under the configured per-profile cap.
Post-reconciliation classification counts were IWB `70` plus one placeholder,
IWD `39` plus one placeholder, and IWF `50` with no placeholder. No D1/W1/MN
bars were present, so `history_ready=false`; no continuity or analysis floor
is claimed. Cleanup removed all branch-scoped resources.

## 2026-09-08 — 10,000-row virtual watchlist validation

The focused virtual-watchlist suite passed `67/67` tests, including the
10,000-row universe guard and wide-column virtualization checks. This proves
the row-grid virtualization contract in the component harness; live 10,000-row
network hydration remains separate evidence.

## 2026-09-08 — 100,000-point uPlot interaction validation

The real-browser uPlot guard passed: a full 100,000-point history rendered and
survived 40 zoom/pan cycles without replacing the chart element, within the
2,500 ms interaction budget (test runtime `421 ms`). This establishes the
renderer-level dense-history contract only; the separate 10,000-row workstation
budget remains open.

## 2026-09-08 — 100-round pop-out endurance validation

The explicit R6 lifecycle soak passed both workstation performance guards at
`TC2000_POP_OUT_CHURN_ROUNDS=100`: initial two-window recovery and repeated
multi-window churn completed in `1.7` minutes. The oracle preserved tool and
canvas counts, returned to one page after every round, and stayed within its
memory bounds where Chromium exposed them. The isolated stack was torn down
and scoped cleanup removed all generated resources.

## 2026-09-08 — Russell 3000 provider population

The bounded iShares slice persisted the mapped IWV cap-weighted leg for
`2025-12-31` with zero refresh failures and `2602/2605` resolved rows (`2599`
canonical and three placeholders). Equal-weight, value, and growth have no
verified mapped proxies and were reported unavailable. IWV had complete
weights but pending classification, zero D1/W1/MN bars, and `history_ready=false`;
no continuity or analysis floor is claimed. Cleanup removed all branch-scoped
resources.

## 2026-09-08 — Russell 1000 provider population

The bounded iShares slice persisted three Russell 1000 legs for `2025-12-31`
with zero refresh failures: IWB `1014/1017` resolved (`1013` canonical and
one placeholder), IWD `873/876` resolved (`872` canonical and one placeholder),
and IWF `393/396` resolved (`393` canonical and no placeholders). Equal-weight
has no verified mapped proxy and was reported unavailable. Mapped roles had
complete weights but pending classification, zero D1/W1/MN bars, and
`history_ready=false`; no continuity or analysis floor is claimed. Cleanup
removed all branch-scoped resources.

## 2026-09-08 — Russell 2000 provider population

The bounded iShares slice persisted three Russell 2000 legs for `2025-12-31`
with zero refresh failures: IWM `1963/1967` resolved (`1960` canonical and
three placeholders), IWN `1422/1425` resolved (`1419` canonical and three
placeholders), and IWO `1101/1104` resolved (`1098` canonical and three
placeholders). Equal-weight has no verified mapped proxy and was reported
unavailable. Mapped roles had complete weights but pending classification, no
D1/W1/MN bars, and `history_ready=false`; no continuity or analysis floor is
claimed. Cleanup removed all branch-scoped resources.

## 2026-09-08 — S&P Composite 1500 provider population

The bounded provider slice persisted the mapped SPTM cap-weighted leg for
`2025-12-31` with zero refresh failures and `1516/1516` resolved holding
rows. Equal-weight, value, and growth have no verified mapped proxies and were
reported unavailable. The canonical readiness report exposed the remaining
identity boundary: all 1,516 rows are `HOLDING-*` placeholders, with zero
canonical members, zero classified members, and zero member bars. Therefore
`history_ready=false`; no continuity or D1/W1/MN floor is claimed. Cleanup
removed all branch-scoped resources.

## 2026-09-08 — S&P SmallCap 600 provider population

The bounded provider slice persisted three SEC-reconstructed S&P SmallCap 600
legs with zero refresh failures: IJR `636/644` resolved rows (eight remained
unresolved), SLYV `461/461`, and SLYG `142/142`. Equal-weight has no verified
mapped proxy and was reported unavailable. Readiness remains incomplete: the
coverage report retained two IJR placeholders, six SLYV placeholders, and 141
SLYG placeholders; no role was history-ready and no D1/W1/MN member-bar floor
or continuity was claimed. The branch-scoped stack was torn down and cleanup
removed all generated resources.

## 2026-09-08 — Bounded Nasdaq-100 canonical provider-history maintenance

Against the isolated branch-scoped Docker stack, the opt-in dated refresh
persisted four SEC-reconstructed Nasdaq-100 snapshots: QQQ at `2025-12-31`
(`101/101` rows resolved) and QQQE at `2025-10-31`, `2024-10-31`, and
`2024-04-30` (`103/103`, `102/102`, and `102/102` rows resolved). The QQQ
requests for older dates were rejected by the existing SEC identity guard
(`missing_series_id`), and the QQQE `2025-06-30` request was rejected by
existing series/legacy-artifact identity checks; these are explicit route/data
limitations, not substituted current data. The bounded classification pass
selected all four persisted snapshots and completed with `enriched=1,
remaining=407, failed=0` under the configured per-profile budget. The
history planner reports `4` available canonical snapshots, but this stack was
started with `E2E_SEED_MARKET_DATA=false`, so no D1/W1/MN member bars are
claimed. Broader family population, historical continuity, and analysis floors
remain open.

## 2026-09-08 — Exact-tip gate after QQQ identity repair

Product commit `40a67a9c` permits curated SEC filings that omit series/class
IDs to pass identity matching only when their observed series name matches the
route's curated series-name constraint; mismatches and CIK-only inference still
fail closed. The live QQQ `2024-12-31` SEC refresh then persisted one canonical
snapshot with `101/101` rows resolved and no failures. Formatter commit
`ed43faa4` completed the exact-tip gate: backend `1353` unit and `386`
integration tests, combined coverage `80.98%`, frontend Vitest `974/974`,
production build/compose/provider policy, healthy stack and runner probes, and
functional Playwright `165` passed with `106` documented skips across `271`.
The unchanged visual matrix remains `98/104` with exactly six known
state-oracle diffs (watchlist-column-editor-open at visual-1080p-100/125 and
workspace-floating at visual-1080p-100/125, visual-1440p-100, and
visual-1440p-125). No baseline, mask, threshold, skip, fallback, provider, or
acceptance policy changed. Gate cleanup removed branch-scoped resources; a
post-cleanup resource probe was unable to query Docker because the host daemon
socket was permission-denied. Continue broader R1 family population,
continuity, and D1/W1/MN member-bar evidence, then the remaining R2-R7 work.

## 2026-09-08 — S&P MidCap 400 provider population

The next bounded provider slice persisted three SEC-reconstructed S&P MidCap
400 legs with zero failures: MDY `401/401` (latest available composition
`2025-09-30`), MDYV `309/309`, and MDYG `238/238`. Equal-weight has no
verified mapped proxy and was reported unavailable. The readiness report kept
the real gaps visible: MDYV and MDYG each retained nine placeholder members,
all roles had `history_ready=false`, and no family continuity or D1/W1/MN
member-bar floor was claimed. Cleanup removed all branch-scoped resources.

## 2026-09-08 — S&P 500 provider population and PostgreSQL identity repair

Product commit `d9f95faa` fixes a PostgreSQL ordering defect in internal ISIN
reassignment: the old instrument's unique ISIN ownership is flushed clear
before a reconciled instrument receives that same alias. The bounded S&P 500
`2025-12-31` refresh then completed all four mapped SEC legs with zero
failures—SPY `503/503`, RSP `507/507` (latest available `2025-10-31`), SPYV
`446/446`, and SPYG `142/142` resolved rows. Placeholder-member promotion and
D1/W1/MN history remain separate enrichment/data gates.

The exact-tip gate at `d9f95faa` passed backend `1353` unit and `386`
integration tests, coverage `80.98%`, frontend Vitest `974/974`, build,
compose/provider policy, stack/runner probes, and functional Playwright `165`
passed with `106` documented skips across `271`. Visual parity remains
`98/104` with the same six state-oracle diffs; no visual or acceptance policy
changed. Cleanup removed all branch-scoped resources. Continue canonical
placeholder enrichment, family continuity, and D1/W1/MN member-bar floors.

## 2026-09-08 — Seeded member-bar floor probe

An isolated stack with market-data fixtures enabled confirmed the remaining
readiness boundary: the fresh database contains only controlled six-member
QQQ/QQQE fixture snapshots, not the provider-backed dated snapshots. Those
fixture members have 520 D1 bars each and meet the 252-bar D1 floor, while W1
and MN contain zero bars; value/growth mappings are unavailable. This is
fixture evidence only and does not claim family-wide provider population,
continuity, or W1/MN readiness. The stack was torn down with no resources
retained.

## 2026-09-08 — Exact-tip gate after alert-promotion hydration stabilization

Test commit `e227eda8` adds the bounded two-second canonical-instrument
settling window already used by F8u-signal to the suite-order-sensitive
F8u-alert flow. Focused authenticated coverage passed `3/3` on a fresh stack.
The exact-tip gate then completed all non-visual stages: backend `1352` unit
and `386` integration tests, frontend Vitest `974/974`, production
build/compose/provider policy, healthy stack and runner probes, and functional
Playwright `165` passed with `106` documented skips across `271`. The visual
matrix remains `98/104` with exactly the six unchanged state-oracle diffs
(watchlist-column-editor-open at visual-1080p-100/125 and workspace-floating at
visual-1080p-100/125 and visual-1440p-100/125). No product, visual-policy,
fallback, provider-selection, or acceptance rule changed.

The next R1 gate remains opt-in provider maintenance against persisted
snapshots, followed by evidence for resolved populations, historical
continuity, and D1/W1/MN member-bar floors.

## 2026-09-08 — Exact-tip gate after worker Compose wiring

Product commit `abf0bb69` wires the bounded historical-enrichment snapshot cap
into the branch-scoped worker container. The focused F8u-alert reproduction
passed `1/1` after a transient timeout in the preceding full run. The rerun
then completed all non-visual stages: backend `1351` unit and `386` integration
tests, frontend Vitest `974/974`, production build/compose/provider policy,
healthy stack and runner probes, and authenticated functional Playwright `165`
passed with `106` documented skips across `271`. The visual matrix remains
`98/104` with exactly the six unchanged state-oracle diffs (watchlist-column-
editor-open at visual-1080p-100/125 and workspace-floating at
visual-1080p-100/125 and visual-1440p-100/125). No visual policy, fallback,
provider-selection, or acceptance rule changed.

The next R1 gate remains opt-in provider maintenance against persisted
snapshots, followed by evidence for resolved populations, historical
continuity, and D1/W1/MN member-bar floors.

Commit `c9e017e0` hardens the bounded dated-enrichment summary against a
missing `equity_detail` relationship. The exhaustive integration gate then
completed all non-visual stages: backend `1351` unit and `386` integration
tests, frontend Vitest `974/974`, production build/compose/provider policy,
healthy stack and runner probes, and functional Playwright `165` passed with
`106` documented skips across `271`. The visual matrix remains `98/104` with
exactly the six previously recorded state-oracle diffs (watchlist-column-
editor-open at visual-1080p-100/125 and workspace-floating at
visual-1080p-100/125 and visual-1440p-100/125). No visual policy, fallback,
provider-selection, or acceptance rule changed.

The next R1 gate remains opt-in provider maintenance against persisted
snapshots, followed by evidence for resolved populations, historical
continuity, and D1/W1/MN member-bar floors.

## 2026-09-08 — Bound canonical holding enrichment across dated snapshots

Product commit `cb3191fe` closes a bounded R1 maintenance gap in the canonical
ETF holding reconciliation path. The scheduled enrichment pass now visits up
to four persisted non-fixture snapshots per ETF profile (configurable through
`ETF_HOLDINGS_CLASSIFICATION_MAX_SNAPSHOTS_PER_PROFILE`) instead of examining
only the latest snapshot. A single per-profile enrichment budget is carried
across those dates, and the resolver cap applies to every unresolved or
unclassified row, including rows whose source did not materialize an
instrument. Snapshot selection remains canonical-data-only and excludes
`controlled_fixture`/`e2e_reference` records; interactive reads still do not
fan out to providers.

Focused resolution coverage passed `25/25`; the bounded worker/configuration
checks passed `6/6`; Ruff, compile, and diff checks passed. This makes dated
maintenance progress durable and auditable but does not claim that QQQ/QQQE or
the other family legs are fully populated, continuous, or at D1/W1/MN floors;
provider route availability and persisted data still require separate
maintenance execution and live/database evidence. No visual, fallback,
provider-selection, or acceptance policy changed.

## 2026-09-08 — Promote Study Lab thresholds to Strategy signals

Product commit `9352c43a` closes the direct Study Lab R4 threshold-promotion
gap for numeric series and range-center artifacts. Both targets now expose an
explicit `Save as Strategy signal` action, require declared canonical member
IDs and an immutable source, and persist the source run/code/hash, dataset and
member lineage, selected output, threshold operator/value, target, adapter,
and re-evaluation semantics before creating the user-scoped Strategy signal.
The operation fails closed when canonical instrument identity is unavailable.

Focused component coverage passed `27/27`; frontend type-check and
`git diff --check` passed. Test commit `290ff9f7` adds the authenticated F9j
browser proof; the focused live flow passed `1/1` against a seeded,
branch-scoped Docker stack and verified the signal asset, explicit adapter and
visible created-signal message.

The final exact-tip gate at `290ff9f7` passed all non-visual stages: backend
`1350` unit and `385` integration tests, combined coverage `80.96%`, frontend
`972/972`, production build, compose/provider policy, healthy stack,
runner-isolation/resource probes, and functional Playwright `164` passed with
`106` documented skips across `270`. Visual parity remains `98/104` with only
the six known state-oracle diffs: watchlist-column-editor-open at
visual-1080p-100/125 and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125. No visual baseline, mask, threshold, skip, fallback,
provider, or acceptance policy changed; cleanup left no assigned resources.
Continue R1 canonical provider/history readiness and the remaining R2-R7 work.

## 2026-09-07 — Prove chart EasyScan and Market Gauge promotion in the authenticated browser

Test commit `38f7480a` adds the consuming-UI F8u-scan and F8u-gauge Playwright
flows. Each opens a real chart, adds an indicator, selects the corresponding
Chart Plot Library target, and verifies reusable-condition plus EasyScan
creation responses and the user-visible promotion status. Focused live
coverage passed `2/2` against the branch-scoped Docker stack.

The exact-tip gate passed all non-visual stages: backend `1350` unit and `385`
integration tests with combined coverage above the repository floor, frontend
`972/972`, production build/compose/provider policy, stack health,
runner-isolation/resource probes, and authenticated functional Playwright
`164` passed with `106` documented skips across `270`. The unchanged visual
matrix returned `98/104`, exactly the six known state-oracle diffs
(watchlist-column-editor-open at visual-1080p-100/125 and workspace-floating
at visual-1080p-100/125 and visual-1440p-100/125). No visual baseline, mask,
threshold, skip, fallback, provider, or acceptance policy changed. Cleanup
removed four generated images and left no assigned containers, volumes,
sessions, or known bytes. This closes the Chart Plot Library's direct
condition/column/filter/scan/gauge/alert browser fan-out evidence; continue
the remaining Strategy Lab fan-out alongside broader R1 canonical
population/history and R2-R7 work.

## 2026-09-07 — Prove chart indicator-alert promotion in the authenticated browser

Test commit `a7d7915d` adds the consuming-UI F8u-alert Playwright flow. It
waits for canonical SPY instrument hydration, opens the real chart, adds EMA,
selects the indicator-alert promotion target, and verifies the reusable
condition and `/alerts/indicator` creation responses while checking browser
diagnostics. The focused live flow passed `1/1` against the branch-scoped
Docker stack.

The exact-tip gate passed all non-visual stages: backend `1350` unit and `385`
integration tests with combined coverage above the repository floor, frontend
`972/972`, production build/compose/provider policy, stack health,
runner-isolation/resource probes, and authenticated functional Playwright
`162` passed with `106` documented skips across `268`. The unchanged visual
matrix returned `98/104`, exactly the six known state-oracle diffs
(watchlist-column-editor-open at visual-1080p-100/125 and workspace-floating
at visual-1080p-100/125 and visual-1440p-100/125). No visual baseline, mask,
threshold, skip, fallback, provider, or acceptance policy changed. Cleanup
removed four generated images and left no assigned containers, volumes,
sessions, or known bytes. Continue the remaining compatible chart/list/gauge
and Strategy Lab fan-out alongside broader R1 canonical population/history and
R2-R7 work; this closes browser proof for the alert fan-out slice but does not
imply complete promotion fan-out.

## 2026-09-07 — Prove chart watchlist-filter promotion in the authenticated browser

Test commit `91c470dc` adds the consuming-UI F8u-filter Playwright flow. It
opens a real chart, adds RSI, selects the active-filter promotion target and an
existing watchlist, submits the promotion, and verifies the persisted filter
mode and EasyScan identifier in the saved workspace snapshot while checking
browser diagnostics. The focused live flow passed `1/1` against the
branch-scoped Docker stack.

The exact-tip gate passed all non-visual stages: backend `1350` unit and `385`
integration tests with combined coverage above the repository floor, frontend
`972/972`, production build/compose/provider policy, stack health,
runner-isolation/resource probes, and authenticated functional Playwright
`161` passed with `106` documented skips across `267`. The unchanged visual
matrix returned `98/104`, exactly the six known state-oracle diffs
(watchlist-column-editor-open at visual-1080p-100/125 and workspace-floating
at visual-1080p-100/125 and visual-1440p-100/125). No visual baseline, mask,
threshold, skip, fallback, provider, or acceptance policy changed. Cleanup
removed four generated images and left no assigned containers, volumes,
sessions, or known bytes. Continue the remaining compatible chart/list/gauge
and Strategy Lab fan-out alongside broader R1 canonical population/history and
R2-R7 work; this closes browser proof for the filter fan-out slice but does not
imply complete promotion fan-out.

## 2026-09-07 — Prove chart Boolean-column promotion in the authenticated browser

Test commit `a229a145` adds the consuming-UI F8u-boolean Playwright flow. It
opens a real chart, adds RSI, selects the Boolean-column promotion target and
an existing watchlist, submits the promotion, and verifies the persisted
Boolean column is visible in that watchlist while checking browser diagnostics.
The focused live flow passed `1/1` against the branch-scoped Docker stack.

The exact-tip gate passed all non-visual stages: backend `1350` unit and `385`
integration tests with combined coverage above the repository floor, frontend
`972/972`, production build/compose/provider policy, stack health,
runner-isolation/resource probes, and authenticated functional Playwright
`160` passed with `106` documented skips across `266`. The unchanged visual
matrix returned `98/104`, exactly the six known state-oracle diffs
(watchlist-column-editor-open at visual-1080p-100/125 and workspace-floating at
visual-1080p-100/125 and visual-1440p-100/125). No visual baseline, mask,
threshold, skip, fallback, provider, or acceptance policy changed. Cleanup
removed four generated images and left no assigned containers, volumes,
sessions, or known bytes. Continue broader R1 canonical population/history and
the remaining R2-R7 work; this closes browser proof for this fan-out slice but
does not imply complete promotion fan-out.

## 2026-09-07 — Promote chart indicators to Boolean watchlist columns

Product commit `191aa889` completes another compatible R4 fan-out slice in the
Chart Plot Library. An indicator threshold can now be copied into a reusable
condition, a saved EasyScan-backed Boolean column, and a selected watchlist
window. The adapter uses the existing `condition:<key>` and `column_keys`
workspace contract, preserves the chart timeframe, validates the target before
creating the scan, and reports the resulting column without changing provider,
fallback, visual-oracle, or acceptance-policy behavior.

Focused Chart Plot Library coverage passed `23/23`; frontend type-check and
diff checks passed. The exact-tip gate passed all non-visual stages: backend
`1350` unit and `385` integration tests with combined coverage above the
repository floor, frontend `972/972`, production build/compose/provider
policy, stack health, runner isolation/resource probes, and authenticated
functional Playwright (`159` passed, `106` documented skips across `265`). The
unchanged visual matrix returned `98/104`, exactly the six known state-oracle
diffs (watchlist-column-editor-open at visual-1080p-100/125 and
workspace-floating at visual-1080p-100/125 and visual-1440p-100/125). Cleanup
removed four generated images and left no assigned containers, volumes,
sessions, or known bytes. Continue broader R1 canonical population/history and
the remaining R2-R7 work; this slice does not imply complete promotion
fan-out.

## 2026-09-07 — Promote chart indicators to Market Gauges

Product commit `f2dc4a78` completes a compatible R4 fan-out gap in the Chart
Plot Library. An indicator threshold can now be copied into a reusable
condition and its saved EasyScan-backed Market Gauge target, matching the
existing Study Lab gauge contract. The operation keeps the chart timeframe,
condition definition, and existing bounded all-instrument scan semantics; no
new provider, fallback, visual-oracle, or acceptance-policy behavior was
introduced.

Focused Chart Plot Library coverage passed `22/22`; frontend type-check and
diff checks passed. The exact-tip gate passed all non-visual stages: backend
`1350` unit and `385` integration tests with combined coverage above the
repository floor, frontend `971/971`, production build/compose/provider
policy, stack health, runner isolation/resource probes, and authenticated
functional Playwright (`159` passed, `106` documented skips across `265`).
The unchanged visual matrix returned `98/104`, exactly the six known
state-oracle diffs (watchlist-column-editor-open at 1080p-100/125 and
workspace-floating at all four projects). Cleanup removed four generated
images and left no assigned containers, volumes, sessions, or known bytes.
Continue broader R1 canonical population/history and the remaining R2-R7
work; this slice does not imply complete promotion fan-out.

## 2026-09-07 — Continue compatible provider metadata fallback

Product commit `ab9ebe56` tightens the reviewed search-provider enrichment
chain. A provider-owned metadata profile is accepted only after the same
canonical-symbol, placeholder, quote-type, and name-compatibility checks used
by the default path; an incompatible profile no longer blocks a later
configured provider or the safe default fallback. The new regression covers a
first incompatible provider followed by a compatible provider, while the
existing unique-candidate enrichment remains covered. This preserves bounded,
maintenance-only search and rejects weak metadata rather than promoting it.

Focused resolver coverage passed `24/24`; Ruff/format and diff checks passed.
The exact-tip gate at `ab9ebe56` passed all non-visual stages: backend `1350`
unit and `385` integration tests with combined coverage above the repository
floor, frontend `970/970`, build/compose/provider policy, stack health, runner
isolation/resource probes, and authenticated functional Playwright (`159`
passed, `106` documented skips across `265` specs). The unchanged visual
matrix returned `98/104`, with exactly the six known state-oracle diffs
(watchlist-column-editor-open at 1080p-100/125 and workspace-floating at all
four projects). No baseline, mask, threshold, skip, fallback, provider, or
acceptance policy changed. Teardown removed four generated images and left
zero assigned containers, volumes, sessions, or known bytes. Broader canonical
population/history and R2-R7 remain open.

## 2026-09-07 — Let identity search providers complete canonical enrichment

Product commit `53f7b07b` closes a bounded R1 enrichment gap: when a reviewed
instrument-search provider returns a unique candidate, its own metadata
capability is now tried before the deployment default metadata provider. This
allows a self-contained public identity route such as SEC EDGAR to promote a
holding only when the existing full name, canonical-symbol, and equity-like
quote-type checks pass. Search remains maintenance-only, bounded, and
auditable; ambiguous matches, unavailable metadata, symbol guesses, and
interactive provider fan-out remain rejected or explicit.

The exact-tip gate at `53f7b07b` passed all non-visual stages: backend `1349`
unit and `385` integration tests with combined coverage above the repository
floor, frontend `970/970`, build/compose/provider policy, stack health, runner
isolation/resource probes, and authenticated functional Playwright (`159`
passed, `106` documented skips across `265` specs). The unchanged visual matrix
returned `98/104`, with exactly the six known state-oracle diffs (watchlist
column-editor-open at 1080p-100/125 and workspace-floating at all four
projects). No baseline, mask, threshold, skip, fallback, provider, or
acceptance policy changed. Teardown removed four generated images and left zero
assigned containers, volumes, sessions, or known bytes. Broader canonical
population/history and R2-R7 remain open.

## 2026-09-07 — Verify canonical member-history backfill against persisted data

Product/test commit `466b11a3` adds a real-Postgres integration regression for
`backfill_benchmark_family_member_history_task`. The test creates one persisted
canonical `sec_nport` snapshot and one `controlled_fixture`/`e2e_reference`
snapshot, then proves the planner selects only the canonical snapshot, queues
the resolved member through the existing bulk-history path, uses the inclusive
composition-date end bound, and returns the deterministic idempotence key.
This closes the database-backed verification gap for the bounded R1 backfill
mechanism; it does not populate missing provider data or claim complete family
history.

The exact-tip gate at product tip `466b11a3` passed all non-visual stages:
locked dependency/migration/workstream checks, Ruff/format/type-check,
backend `1348` unit and `385` integration tests with combined coverage above
the repository floor, frontend `970/970` tests, build/compose/provider policy,
stack health, runner isolation/resource probes, and authenticated functional
Playwright (`159` passed, `106` documented skips across `265` specs). The
unchanged visual matrix returned `98/104`; exactly the six known state-oracle
diffs remain (watchlist-column-editor-open at 1080p-100/125 and
workspace-floating at all four projects). No baseline, mask, threshold, skip,
fallback, provider, or acceptance policy changed. Stack teardown removed four
generated images and left zero assigned containers, volumes, sessions, or
known bytes. Continue broader canonical provider/history population and R2-R7.

## 2026-09-07 — Backfill existing canonical family member history

Product commit `cb060f56` adds a bounded, provider-neutral scheduled backfill
for member-bar history already represented by persisted canonical benchmark
family snapshots. The planner selects deterministic, mapped-family snapshots
with resolved holdings, excludes controlled/e2e fixtures, and caps work at
`BENCHMARK_FAMILY_MEMBER_HISTORY_BACKFILL_MAX_SNAPSHOTS` (default `512`). The
opt-in worker task queues each selected snapshot through the existing member
history path using an inclusive composition-date end bound, preserving
point-in-time semantics and avoiding future leakage. It is disabled by default
(`BENCHMARK_FAMILY_MEMBER_HISTORY_BACKFILL_ENABLED=false`) and scheduled for
Sunday 09:00 only when enabled; it makes no interactive provider calls and adds
no UI or fallback behavior.

Focused service/task/worker checks passed `56` tests; the selected-only command
reported the repository's expected global coverage warning because it does not
exercise the full suite. Ruff, compile, and diff checks passed. The exact-tip
gate then passed all locked, backend, frontend, build, compose/provider,
stack-health, runner-isolation, and authenticated functional stages (`1348`
unit, `384` integration, frontend `970/970`, and `159` functional passes with
`106` documented skips across `265` specs). The unchanged visual matrix was
`98/104`, with exactly the six known state-oracle diffs in
watchlist-column-editor-open at both 1080p projects and workspace-floating at
all four projects. Cleanup removed four generated images and left zero assigned
containers, volumes, sessions, or known bytes. This closes a bounded R1
mechanical gap only; broad canonical population and R2-R7 remain open.

## 2026-09-07 — Enable SPTM SEC filing-reconstruction history route

Product commit `f30fe002` upgrades the mapped State Street/SPDR SPTM role from
issuer-current-only to `sec_filing_reconstruction` through SEC CIK
`0001064642`, series `S000006973`, class `C000019026`, and fund ticker
`SPTM`. The dated policy is `latest_sec_filing_report_on_or_before_requested_date`
with source `https://data.sec.gov/submissions/CIK0001064642.json`; the issuer
daily workbook route remains available separately for current snapshots. The
adapter uses the bounded 50-filing SEC window because the CIK contains multiple
fund series. All nine mapped SPDR roles now have explicit SEC route identities;
this removes the last issuer-current-only role. Focused regression/static checks
passed (`8` selected tests); the selected family coverage API regression passed
`1/1`; the opt-in live SPTM SEC route probe passed `1/1` on the verified result
(the command's global coverage threshold warning is unrelated to the underlying
test). This proves route identity and bounded dated reconstruction only; it does
not claim complete historical membership, weights, or member-bar history for SPTM.

## 2026-09-07 — Exact-tip gate after SPTM SEC history reconstruction

At exact product tip `f30fe002`, all locked dependency/migration/workstream,
Ruff/format/type-check, backend unit/integration and coverage, frontend
Vitest/build, compose/provider policy, stack health, research-runner
isolation/resource probes, and authenticated functional Playwright stages passed
(`1345` unit, `384` integration, frontend `970/970`, and `159` functional passes
with `106` documented skips across `265` specs). The unchanged visual matrix
completed `104` cases with `98` passes and exactly six known state-oracle diffs:
watchlist-column-editor-open at visual-1080p-100/125 and workspace-floating at
all four visual projects. No baseline, mask, threshold, skip, fallback, provider,
or acceptance policy changed. Docker cleanup removed four generated images and
post-gate resource accounting was clean with zero containers, volumes, sessions,
and known bytes. Continue with broader canonical provider/history population and
the remaining R2-R7 roadmap work while preserving this visual-only boundary.

## 2026-09-07 — Enable SLYG SEC filing-reconstruction history route

Product commit `49d8d98f` upgrades the mapped State Street/SPDR SLYG role from
issuer-current-only to `sec_filing_reconstruction` through SEC CIK
`0001064642`, series `S000006984`, class `C000019037`, and fund ticker
`SLYG`. The dated policy is `latest_sec_filing_report_on_or_before_requested_date`
with source `https://data.sec.gov/submissions/CIK0001064642.json`; the issuer
daily workbook route remains available separately for current snapshots. The
adapter uses the bounded 50-filing SEC window because the CIK contains multiple
fund series. The remaining mapped SPDR role stays explicitly issuer-current-only:
SPTM. Focused regression/static checks passed (`8` selected tests); the selected
family coverage API regression passed `1/1`; the opt-in live SLYG SEC route probe
passed `1/1` on the verified result (the command's global coverage threshold
warning is unrelated to the underlying test). This proves route identity and
bounded dated reconstruction only; it does not claim complete historical
membership, weights, or member-bar history for SLYG.

## 2026-09-07 — Exact-tip gate after SLYG SEC history reconstruction

At exact product tip `49d8d98f`, all locked dependency/migration/workstream,
Ruff/format/type-check, backend unit/integration and coverage, frontend
Vitest/build, compose/provider policy, stack health, research-runner
isolation/resource probes, and authenticated functional Playwright stages passed
(`1344` unit, `384` integration, frontend `970/970`, and `159` functional passes
with `106` documented skips across `265` specs). The unchanged visual matrix
completed `104` cases with `98` passes and exactly six known state-oracle diffs:
watchlist-column-editor-open at visual-1080p-100/125 and workspace-floating at
all four visual projects. No baseline, mask, threshold, skip, fallback, provider,
or acceptance policy changed. Docker cleanup removed four generated images and
post-gate resource accounting was clean with zero containers, volumes, sessions,
and known bytes. Continue the final bounded canonical provider/history slice
while preserving this visual-only boundary.

## 2026-09-07 — Enable SLYV SEC filing-reconstruction history route

Product commit `feded2ca` upgrades the mapped State Street/SPDR SLYV role from
issuer-current-only to `sec_filing_reconstruction` through SEC CIK
`0001064642`, series `S000006974`, class `C000019027`, and fund ticker
`SLYV`. The dated policy is `latest_sec_filing_report_on_or_before_requested_date`
with source `https://data.sec.gov/submissions/CIK0001064642.json`; the issuer
daily workbook route remains available separately for current snapshots. The
adapter uses the bounded 50-filing SEC window because the CIK contains multiple
fund series. The remaining two mapped SPDR roles stay explicitly issuer-current-only:
SLYG and SPTM. Focused regression/static checks passed (`14` selected tests);
the selected family coverage API regression passed `1/1`; the opt-in live SLYV
SEC route probe passed `1/1` on the verified result (the command's global
coverage threshold warning is unrelated to the underlying test). This proves
route identity and bounded dated reconstruction only; it does not claim complete
historical membership, weights, or member-bar history for SLYV.

## 2026-09-07 — Exact-tip gate after SLYV SEC history reconstruction

At exact product tip `feded2ca`, all locked dependency/migration/workstream,
Ruff/format/type-check, backend unit/integration and coverage, frontend
Vitest/build, compose/provider policy, stack health, research-runner
isolation/resource probes, and authenticated functional Playwright stages passed
(`1343` unit, `384` integration, frontend `970/970`, and `159` functional passes
with `106` documented skips across `265` specs). The unchanged visual matrix
completed `104` cases with `98` passes and exactly six known state-oracle diffs:
watchlist-column-editor-open at visual-1080p-100/125 and workspace-floating at
all four visual projects. No baseline, mask, threshold, skip, fallback, provider,
or acceptance policy changed. Docker cleanup removed four generated images and
post-gate resource accounting was clean with zero containers, volumes, sessions,
and known bytes. Continue the next bounded canonical provider/history population
slice while preserving this visual-only boundary.

## 2026-09-07 — Enable SPY SEC filing-reconstruction history route

Product commit `de94e8b1` upgrades the mapped State Street/SPDR SPY role from
issuer-current-only to `sec_filing_reconstruction` through SEC trust CIK
`0000884394`. SPY’s N-PORT filings are trust-level and report `seriesName` as
`N/A`, so the adapter now verifies the curated registrant-name identity
containing `SPDR` alongside the CIK rather than inventing a series/class ID.
The dated policy is `latest_sec_filing_report_on_or_before_requested_date` with
source `https://data.sec.gov/submissions/CIK0000884394.json`; the issuer daily
workbook route remains available separately for current snapshots. The remaining
three mapped SPDR roles stay explicitly issuer-current-only. Focused
regression/static checks passed (`13` selected tests); the selected family
coverage API regression passed `1/1`; the opt-in live SPY SEC route probe passed
`1/1` on the verified result (the command’s global coverage threshold warning is
unrelated to the underlying test). This proves route identity and bounded dated
reconstruction only; it does not claim complete historical membership, weights,
or member-bar history for SPY.

## 2026-09-07 — Exact-tip gate after SPY SEC history reconstruction

At exact product tip `de94e8b1`, all locked dependency/migration/workstream,
Ruff/format/type-check, backend unit/integration and coverage, frontend
Vitest/build, compose/provider policy, stack health, research-runner
isolation/resource probes, and authenticated functional Playwright stages passed
(`1342` unit, `384` integration, frontend `970/970`, and `159` functional passes
with `106` documented skips across `265` specs). The unchanged visual matrix
completed `104` cases with `98` passes and exactly six known state-oracle diffs:
watchlist-column-editor-open at visual-1080p-100/125 and workspace-floating at
all four visual projects. No baseline, mask, threshold, skip, fallback, provider,
or acceptance policy changed. Docker cleanup removed four generated images and
post-gate resource accounting was clean with zero containers, volumes, sessions,
and known bytes. Continue the next bounded canonical provider/history
population slice while preserving this visual-only boundary.

## 2026-09-07 — Enable MDY SEC filing-reconstruction history route

Product commit `ebbb0664` upgrades the mapped State Street/SPDR MDY role from
issuer-current-only to `sec_filing_reconstruction` through SEC CIK
`0000936958` and the legacy N-PORT series-name identity `MidCap 400 ETF Trust`.
The dated policy is `latest_sec_filing_report_on_or_before_requested_date` with
source `https://data.sec.gov/submissions/CIK0000936958.json`; the issuer daily
workbook route remains available separately for current snapshots. The adapter
uses the bounded 50-filing SEC window and substring series-name matching because
legacy MDY filings do not expose the newer series/class identifiers. The
remaining four mapped SPDR roles stay explicitly issuer-current-only. Focused
regression/static checks passed (`11` selected tests); the selected family
coverage API regression passed `1/1`; the opt-in live MDY SEC route probe passed
`1/1` on the verified result (the command's global coverage threshold warning is
unrelated to the underlying test). This proves route identity and bounded dated
reconstruction only; it does not claim complete historical membership, weights,
or member-bar history for MDY.

## 2026-09-07 — Exact-tip gate after MDY SEC history reconstruction

At exact product tip `ebbb0664`, all locked dependency/migration/workstream,
Ruff/format/type-check, backend unit/integration and combined coverage,
frontend Vitest/build, compose/provider policy, stack health, research-runner
isolation/resource probes, and authenticated functional Playwright stages passed
(`1339` unit, `384` integration, frontend `970/970`, and `159` functional passes
with `106` documented skips across `265` specs). The unchanged visual matrix
completed `104` cases with `98` passes and exactly six known state-oracle diffs:
watchlist-column-editor-open at visual-1080p-100/125 (`13,844` pixels each),
and workspace-floating at visual-1080p-100/125, visual-1440p-100, and
visual-1440p-125. No baseline, mask, threshold, skip, fallback, provider, or
acceptance policy changed. Docker cleanup removed four generated images and
post-gate resource accounting was clean with zero containers, volumes, sessions,
and known bytes. Continue the next bounded canonical provider/history
population slice while preserving this visual-only boundary.

## 2026-09-07 — Enable MDYV SEC filing-reconstruction history route

Product commit `f7bd23a3` upgrades the mapped State Street/SPDR MDYV role from
issuer-current-only to `sec_filing_reconstruction` through SEC CIK
`0001064642`, series `S000006988`, class `C000019041`, and fund ticker
`MDYV`. The dated policy is
`latest_sec_filing_report_on_or_before_requested_date` with source
`https://data.sec.gov/submissions/CIK0001064642.json`; the issuer daily
workbook route remains available separately for current snapshots. The adapter
uses the bounded 50-filing SEC window because the shared CIK contains multiple
fund series. The remaining five mapped SPDR roles stay explicitly
issuer-current-only. Focused regression/static checks passed (`8` selected
tests); the opt-in live MDYV SEC route probe passed `1/1` on the verified
result. This proves route identity and bounded dated reconstruction only; it
does not claim complete historical membership, weights, or member-bar history
for MDYV.

## 2026-09-07 — Exact-tip gate after MDYV SEC history reconstruction

At exact product tip `f7bd23a3`, the `full_stack_browser` gate passed all
locked dependency/migration/workstream checks, Ruff/format/type-check,
backend unit and integration phases (`1337` unit and `384` integration tests;
`80.94%` combined coverage), frontend Vitest (`970/970`), production image
build, compose/provider policy, stack health, research-runner isolation and
resource probes, and authenticated functional Playwright (`159` passed with
`106` documented skips across `265` specs). The visual matrix completed `104`
cases with `98` passes and exactly six known state-oracle diffs:
watchlist-column-editor-open at visual-1080p-100/125 (`13,844` pixels each),
and workspace-floating at visual-1080p-100/125 (`12,097` and `12,097` pixels),
visual-1440p-100 (`12,097` pixels), and visual-1440p-125 (`9,770` pixels).
No baseline, mask, threshold, skip, fallback, provider, or acceptance policy
changed. Docker cleanup removed four generated images; post-gate resource
accounting was clean with zero containers, volumes, sessions, and known bytes.
Continue the next bounded canonical provider/history population slice while
preserving this visual-only boundary.

## 2026-09-07 — Enable MDYG SEC filing-reconstruction history route

Product commit `f7a90789` upgrades the mapped State Street/SPDR MDYG role from
issuer-current-only to `sec_filing_reconstruction` through SEC CIK
`0001064642`, series `S000006987`, class `C000019040`, and fund ticker
`MDYG`. The dated policy is
`latest_sec_filing_report_on_or_before_requested_date` with source
`https://data.sec.gov/submissions/CIK0001064642.json`; the issuer daily
workbook route remains available separately for current snapshots. The adapter
uses the bounded 50-filing SEC window because the shared CIK contains multiple
fund series. The remaining six mapped SPDR roles stay explicitly
issuer-current-only. Focused regression/static checks passed (`8` selected
tests); the opt-in live MDYG SEC route probe passed `1/1` after a transient
wrong-filing response was discarded and the verified rerun returned 238 rows.
This proves route identity and bounded dated reconstruction only; it does not
claim complete historical membership, weights, or member-bar history for MDYG.

## 2026-09-07 — Exact-tip gate after MDYG SEC history reconstruction

At exact product tip `f7a90789`, the `full_stack_browser` gate passed all
locked dependency/migration/workstream checks, Ruff/format/type-check,
backend unit and integration phases (`1335` unit and `384` integration tests;
`80.94%` combined coverage), frontend Vitest (`970/970`), production image
build, compose/provider policy, stack health, research-runner isolation and
resource probes, and authenticated functional Playwright (`159` passed with
`106` documented skips across `265` specs). The visual matrix completed `104`
cases with `98` passes and exactly six known state-oracle diffs:
watchlist-column-editor-open at visual-1080p-100/125 (`13,844` pixels each),
and workspace-floating at visual-1080p-100/125 (`11,901` and `9,770` pixels),
visual-1440p-100 (`9,770` pixels), and visual-1440p-125 (`9,770` pixels).
No baseline, mask, threshold, skip, fallback, provider, or acceptance policy
changed. Docker cleanup removed four generated images; post-gate resource
accounting was clean with zero containers, volumes, sessions, and known bytes.
Continue the next bounded canonical provider/history population slice while
preserving this visual-only boundary.

## 2026-09-07 — Enable SPYG SEC filing-reconstruction history route

Product commit `7ee30073` upgrades the mapped State Street/SPDR SPYG role from
issuer-current-only to `sec_filing_reconstruction` through SEC CIK
`0001064642`, series `S000006984`, class `C000019037`, and fund ticker symbol
`SPYG`. The dated policy is
`latest_sec_filing_report_on_or_before_requested_date` with source
`https://data.sec.gov/submissions/CIK0001064642.json`; the issuer daily
workbook route remains available separately for current snapshots. The adapter
uses the bounded 50-filing SEC window because the shared CIK contains multiple
fund series. The remaining seven mapped SPDR roles stay explicitly
issuer-current-only. Focused regression/static checks passed (`9` selected
tests); the opt-in live SPYG SEC route probe passed `1/1`. This proves route
identity and bounded dated reconstruction only; it does not claim complete
historical membership, weights, or member-bar history for SPYG.

## 2026-09-07 — Exact-tip gate after SPYG SEC history reconstruction

At exact product tip `7ee30073`, the `full_stack_browser` gate passed all
locked dependency/migration/workstream checks, Ruff/format/type-check,
backend unit and integration phases (`1333` unit and `384` integration tests;
`80.94%` combined coverage), frontend Vitest (`970/970`), production image
build, compose/provider policy, stack health, research-runner isolation and
resource probes, and authenticated functional Playwright (`159` passed with
`106` documented skips across `265` specs). The visual matrix completed `104`
cases with `98` passes and exactly six known state-oracle diffs:
watchlist-column-editor-open at visual-1080p-100/125 (`13,844` pixels each),
and workspace-floating at visual-1080p-100/125 (`12,097` pixels each),
visual-1440p-100 (`12,097` pixels), and visual-1440p-125 (`13,156` pixels).
No baseline, mask, threshold, skip, fallback, provider, or acceptance policy
changed. Docker cleanup removed four generated images; post-gate resource
accounting was clean with zero containers, volumes, sessions, and known bytes.
Continue the next bounded canonical provider/history population slice while
preserving this visual-only boundary.

## 2026-09-07 — Enable SPYV SEC filing-reconstruction history route

Product commit `2b46d6e5` upgrades the mapped State Street/SPDR SPYV role from
issuer-current-only to `sec_filing_reconstruction` through SEC CIK
`0001064642`, series `S000006985`, class `C000019038`, and fund ticker symbol
`SPYV`. The dated policy is
`latest_sec_filing_report_on_or_before_requested_date` with source
`https://data.sec.gov/submissions/CIK0001064642.json`; the issuer daily
workbook route remains available separately for current snapshots. The adapter
uses a bounded 50-filing SEC window because the shared CIK contains multiple
fund series. The other eight mapped SPDR roles remain explicitly
issuer-current-only. Focused regression/static checks passed (`7` selected
tests); the opt-in live SPYV SEC route probe passed `1/1`. This proves route
identity and bounded dated reconstruction only; it does not claim complete
historical membership, weights, or member-bar history for SPYV.

## 2026-09-07 — Exact-tip gate after SPYV SEC history reconstruction

At exact product tip `2b46d6e5`, the `full_stack_browser` gate passed all
locked dependency/migration/workstream checks, Ruff/format/type-check,
backend unit and integration phases (`1331` unit and `384` integration tests;
`80.94%` combined coverage), frontend Vitest (`970/970`), production image
build, compose/provider policy, stack health, research-runner isolation and
resource probes, and authenticated functional Playwright (`159` passed with
`106` documented skips across `265` specs). The visual matrix completed `104`
cases with `98` passes and exactly six known state-oracle diffs:
watchlist-column-editor-open at visual-1080p-100/125 (`13,844` pixels each),
and workspace-floating at visual-1080p-100/125 (`12,097` pixels each),
visual-1440p-100 (`9,770` pixels), and visual-1440p-125 (`12,097` pixels).
No baseline, mask, threshold, skip, fallback, provider, or acceptance policy
changed. Docker cleanup removed four generated images; post-gate resource
accounting was clean with zero containers, volumes, sessions, and known bytes.
Continue the next bounded canonical provider/history population slice while
preserving this visual-only boundary.

## 2026-09-07 — Enable RSP SEC filing-reconstruction history route

Product commit `e96ef740` upgrades the mapped Invesco RSP role from
issuer-current-only evidence to `sec_filing_reconstruction` through SEC CIK
`0001209466`, series `S000060812`, class `C000197628`, and fund ticker symbol
`RSP`. The dated policy is `latest_sec_filing_report_on_or_before_requested_date`
with source `https://data.sec.gov/submissions/CIK0001209466.json`; the issuer
current/monthly route remains available separately. The adapter now inspects a
bounded 20-filing SEC window because the shared CIK contains multiple fund
series. Focused regression/static checks passed (`24` tests, plus the selected
API regression); opt-in live QQQ/RSP SEC probes passed `2/2`. This proves route
identity and bounded dated reconstruction only; it does not claim complete
historical membership, weights, or member-bar history for RSP.

## 2026-09-07 — Exact-tip gate after RSP SEC history reconstruction

At exact product tip `e96ef740`, the `full_stack_browser` gate passed all
locked dependency/migration/workstream checks, Ruff/format/type-check, backend
unit and integration phases (`1329` unit and `384` integration tests; `80.94%`
combined coverage), frontend Vitest (`970/970`), production image build,
compose/provider policy, stack health, research-runner isolation/resource
probes, and authenticated functional Playwright (`159` passed with `106`
documented skips across `265` specs). The visual matrix completed `104` cases
with `98` passes and exactly six known state-oracle diffs: watchlist-column-
editor-open at visual-1080p-100/125 (`13,844` pixels each), and
workspace-floating at visual-1080p-100/125 (`12,097` pixels each),
visual-1440p-100 (`5,512` pixels), and visual-1440p-125 (`9,770` pixels).
No baseline, mask, threshold, skip, fallback, provider, or acceptance policy
changed. Docker cleanup removed four generated images; post-gate resource
accounting was clean with zero containers, volumes, sessions, and known bytes.
Continue the next bounded canonical provider/history population slice while
preserving this visual-only boundary.

## 2026-09-07 — Expose Invesco current-only history route evidence

Product commit `63d64bfe` declares explicit issuer-current-only route evidence
for the mapped Invesco RSP role. Family-history planning now preserves
`issuer_current_only` / `invesco` /
`issuer_public_json_catalog_current_monthly_only` and the public CUSIP-based
catalog URL. Invesco's current/monthly route is deliberately recorded as
route capability only: no dated replay, curated SEC reconstruction, populated
holdings snapshot, or member-bar history is claimed for RSP. Focused taxonomy,
planner, refresh, and route checks passed `30/30`; the selected family
coverage API regression passed `1/1`; Ruff, format, and diff checks passed.

## 2026-09-07 — Exact-tip gate after Invesco current-only history route evidence

At exact product tip `63d64bfe`, the `full_stack_browser` gate passed locked
dependency/migration/workstream checks, Ruff/format/type-check, backend unit
and integration phases (`1328` unit and `384` integration tests; `80.94%`
combined coverage), frontend Vitest (`970/970`), production image build,
compose/provider policy, stack health, research-runner isolation/resource
probes, and authenticated functional Playwright (`159` passed with `106`
documented skips across `265` specs). The visual matrix completed `104` cases
with `98` passes and exactly the same six state-oracle diffs:
watchlist-column-editor-open at visual-1080p-100/125 (`13,844` pixels each),
and workspace-floating at visual-1080p-100/125 (`12,097` pixels each),
visual-1440p-100 (`9,770`), and visual-1440p-125 (`11,901`). No baseline,
mask, threshold, skip, fallback, provider, or acceptance policy changed. Gate
cleanup removed four generated images and the post-gate resource audit
reported zero containers, volumes, sessions, and known bytes. Continue the
next bounded canonical provider/history population slice while preserving this
visual-only boundary.

## 2026-09-06 — Expose SPDR current-only history route evidence

Product commit `9ec4d498` declares explicit issuer-current-only route evidence
for the nine mapped State Street/SPDR roles SPY, SPYV, SPYG, MDY, MDYV, MDYG,
SLYV, SLYG, and SPTM. Family-history planning now preserves
`issuer_current_only` / `spdr` / `issuer_daily_workbook_current_snapshot_only`
and the symbol-specific daily workbook URL. This is deliberately current
snapshot evidence only: SPDR has no verified dated replay route here, so no
dated holdings snapshot or member-bar history is claimed. Focused taxonomy,
planner, refresh, and route checks passed `28/28`; the selected coverage API
regression passed `1/1`; Ruff, format, and diff checks passed.

## 2026-09-06 — Exact-tip gate after SPDR current-only history route evidence

At exact product tip `9ec4d498`, the `full_stack_browser` gate passed locked
dependency/migration/workstream checks, Ruff/format/type-check, backend unit
and integration phases, combined coverage, frontend Vitest (`970/970`),
production image build, compose/provider policy, stack health, research-runner
isolation/resource probes, and authenticated functional Playwright (`159`
passed with `106` documented skips across `265` specs). The visual matrix
completed `104` cases with `98` passes and exactly the same six state-oracle
diffs: watchlist-column-editor-open at visual-1080p-100/125 (`13,844` pixels
each), and workspace-floating at visual-1080p-100 (`9,770`), visual-1080p-125
(`12,097`), visual-1440p-100 (`9,770`), and visual-1440p-125 (`9,770`). No
baseline, mask, threshold, skip, fallback, provider, or acceptance policy
changed. Gate cleanup removed four generated images and resource accounting
was clean with zero containers, volumes, sessions, and known bytes. Continue
the next bounded canonical provider/history population slice while preserving
this visual-only boundary.

## 2026-09-06 — Expose iShares dated history routes

Product commit `8573d958` declares the verified iShares public `asOfDate`
route for the eight mapped family roles IJR, IWB, IWD, IWF, IWM, IWN, IWO,
and IWV. The route evidence is carried by family-history planning as
`issuer_as_of_date` / `ishares` / `issuer_public_json_api_as_of_date` with the
BlackRock product-data endpoint. This records route capability only; it does
not claim that any dated snapshot, membership population, or member-bar history
has been fetched or is complete. Focused route, planner, dated-refresh, and
adapter checks passed `5/5`; Ruff, format, and diff checks passed. The exact-tip
gate at this product tip is recorded immediately below.

## 2026-09-06 — Exact-tip gate after iShares dated history routes

At exact product tip `704e5c8b` (documentation tip `e2d3ce9a`), the
`full_stack_browser` gate passed locked dependency/migration/workstream checks,
Ruff/format/type-check, backend unit and integration phases (`1324` unit and
`384` integration tests; `80.94%` combined coverage), frontend Vitest
(`970/970`), production image build, compose/provider policy, stack health,
research-runner isolation/resource probes, and authenticated functional
Playwright (`159` passed with `106` documented skips across `265` specs). The
visual matrix completed `104` cases with `98` passes and exactly the same six
state-oracle diffs: watchlist-column-editor-open at visual-1080p-100/125
(`13,844` pixels each), and workspace-floating at visual-1080p-100 (`9,770`),
visual-1080p-125 (`11,901`), visual-1440p-100 (`12,097`), and
visual-1440p-125 (`9,770`). No baseline, mask, threshold, skip, fallback,
provider, or acceptance policy changed. Gate cleanup removed four generated
images and resource accounting was clean with zero containers, volumes,
sessions, and known bytes. Continue the next bounded canonical provider/history
population slice while preserving this visual-only boundary.

## 2026-09-06 — Carry history routes into dated family refreshes

Product commit `1888f358` (formatter-only follow-up `bf550e0f`) carries each benchmark-family mapping's declared
historical route status, provider, policy, and source URL into the provider-
backed dated refresh response. Refreshed, route-not-ready, failed, and
unmapped legs all retain explicit route evidence, so QQQ/QQQE SEC filing
reconstruction remains distinguishable from local population failures or
unsupported roles. Focused service coverage passed `12/12`, the selected
dated-family API regression passed `1/1`, and Ruff/format/diff checks passed.
No provider selection, fallback, visual, or acceptance policy changed. The
exact-tip gate at corrected product tip `bf550e0f` is recorded immediately
below.

## 2026-09-06 — Exact-tip gate after dated family refresh route evidence

At exact product tip `bf550e0f` (documentation tip `fec088cf`), the
`full_stack_browser` gate passed locked dependency/migration/workstream checks,
Ruff/format/type-check, backend unit and integration phases (the unit phase
passed `1322` tests; combined coverage passed the configured gate threshold),
frontend Vitest, production image build, compose/provider policy, stack health,
and research-runner isolation/resource probes. Authenticated functional
Playwright passed `159` with `106` documented skips across `265` specs. The
visual matrix completed `104` cases with `98` passes and exactly the same six
state-oracle diffs: watchlist-column-editor-open at visual-1080p-100/125
(`13,844` pixels each), and workspace-floating at visual-1080p-100/125
(`9,770` pixels each) and visual-1440p-100/125 (`12,097` pixels each). No
baseline, mask, threshold, skip, fallback, provider, or acceptance policy
changed. Gate cleanup removed four generated images and the post-gate resource
audit reported zero containers, volumes, sessions, and known bytes. Continue
the next bounded canonical provider/history population slice while preserving
this visual-only boundary.

## 2026-09-06 — Carry canonical history routes into refresh plans

Product commit `97a144bd` carries each benchmark-family history-refresh leg's
canonical route status, provider, historical policy, and source URL into the
administrative queue response. Nasdaq QQQ/QQQE therefore remain visibly
`sec_filing_reconstruction` through both family coverage and refresh planning,
while pending local membership and OHLCV population stay distinct from route
readiness. The focused history planner passed `11/11`, the two admin refresh
API regressions passed `2/2`, Ruff/format/diff checks passed, and no provider
selection, fallback, visual, or acceptance policy changed. The exact-tip gate
at this product tip is the next required validation step.

## 2026-09-06 — Exact-tip gate after carrying history routes into refresh plans

At exact product tip `97a144bd` (`feat(tc2000): carry history routes into
refresh plans`), the `full_stack_browser` gate passed all locked dependency/
migration/workstream, Ruff/format/type-check, backend unit/integration,
frontend Vitest, production-build, compose/provider, stack-health,
research-runner isolation/resource, and authenticated functional-browser
stages. The backend unit phase passed `1321` tests; authenticated functional
Playwright passed `159` with `106` documented skips across `265` specs. The
visual matrix returned `98/104`, with the same six state-oracle diffs:
watchlist-column-editor-open at visual-1080p-100/125 (`13,844` pixels each),
and workspace-floating at visual-1080p-100 (`12,097`), visual-1080p-125
(`12,097`), visual-1440p-100 (`11,901`), and visual-1440p-125 (`12,097`).
No baseline, mask, threshold, skip, fallback, provider, or acceptance policy
changed. Gate cleanup removed four generated images and the post-gate resource
audit reported zero containers, volumes, sessions, and known bytes. Continue
the next bounded canonical provider/history population slice while preserving
this visual-only boundary.

## 2026-09-06 — Exact-tip gate after Nasdaq family history-route evidence

At exact product tip `3a3e5bc1` (`feat(tc2000): expose Nasdaq family history
route evidence`), the `full_stack_browser` gate passed locked dependency/
migration and workstream checks, Ruff/format/type-check, backend unit and
integration coverage (`1320` unit, `384` integration; `80.93%` combined),
frontend Vitest (`970/970`), production image build, compose/provider policy,
stack health, research-runner isolation/resource probes, and authenticated
functional Playwright (`159` passed with `106` documented skips across `265`
specs). The visual matrix returned `98/104`, with exactly the six known
state-oracle diffs: watchlist-column-editor-open at visual-1080p-100/125
(`13,844` pixels each), and workspace-floating at visual-1080p-100 (`12,097`),
visual-1080p-125 (`9,770`), visual-1440p-100 (`12,097`), and
visual-1440p-125 (`12,097`). No baseline, mask, threshold, skip, fallback,
provider, or acceptance policy changed. Gate cleanup removed four generated
images and the post-gate resource audit reported zero containers, volumes,
sessions, and known bytes. Continue the next bounded canonical provider/history
slice while preserving this visual-only boundary.

## 2026-09-06 — Expose Nasdaq family history-route evidence

Product commit `3a3e5bc1` adds explicit canonical `history_route` metadata to
the QQQ and QQQE Nasdaq-100 family mappings and exposes that route status,
provider, policy, and source URL through the backend family coverage/readiness
contracts and visual-neutral accessible Market Map/Market Breadth evidence.
The route records SEC historical-filing reconstruction readiness
(`sec_filing_reconstruction`) and does not claim that dated holdings snapshots
or member bars are already populated. Focused Market Map coverage passed
`36/36`, full frontend Vitest passed `970/970`, type-check/build passed, and
targeted backend integration, Ruff, compile, and diff checks passed. The exact
gate receipt is recorded immediately above; the next action remains a bounded
canonical provider/history population slice.

## 2026-09-06 — Exact-tip gate after canonical family provenance evidence

At exact product tip `0147aded` (documentation tip `a3841089`), the
`full_stack_browser` gate passed locked dependency/migration and workstream
checks, Ruff/format/type-check, backend unit/integration and combined coverage
(`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production image build, compose/provider policy, stack health,
research-runner isolation/resource probes, and authenticated functional
Playwright (`159` passed with `106` documented skips across `265` specs). The
visual matrix completed `104` cases with `98` passes and exactly the six known
state-oracle diffs: watchlist-column-editor-open at visual-1080p-100/125
(`13,844` pixels each), and workspace-floating at visual-1080p-100 (`9,770`),
visual-1080p-125 (`12,097`), visual-1440p-100 (`9,770`), and
visual-1440p-125 (`12,097`). No baseline, mask, threshold, skip, fallback,
provider, or acceptance policy changed. Gate cleanup removed four generated
images and the post-gate resource audit reported zero containers, volumes,
sessions, and known bytes. Continue the next bounded canonical provider/history
slice while preserving this visual-only boundary.

## 2026-09-06 — Expose canonical family provenance evidence

Product commit `0147aded` (`feat(tc2000): expose benchmark family provenance
evidence`) extends the visual-neutral accessible canonical evidence in Market
Map and Market Breadth with family identity, official index name, point-in-time
as-of, membership version, primitive universe-provenance fields, coverage,
freshness, and exclusion codes. The frontend contract now mirrors the
backend's canonical family coverage envelope; values are formatted only when
returned and no provider selection, readiness inference, refresh retry, role
substitution, fallback, visual, or acceptance policy changed. Market Map
focused unit coverage passed `36/36`, full frontend Vitest passed `970/970`,
type-check and production build passed. The exact-tip gate receipt is recorded
immediately above; next action is the next bounded canonical provider/history
slice.

## 2026-09-06 — Exact-tip gate after canonical readiness lineage evidence

At exact product tip `ab09cc60` (documentation tip `7c2d076f`), the
`full_stack_browser` gate passed locked dependency/migration and workstream
checks, Ruff/format/type-check, backend unit/integration and combined coverage
(`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production image build, compose/provider policy, stack health,
research-runner isolation/resource probes, and authenticated functional
Playwright (`159` passed with `106` documented skips across `265` specs). The
visual matrix completed `104` cases with `98` passes and exactly the six known
state-oracle diffs: watchlist-column-editor-open at visual-1080p-100/125
(`13,844` pixels each), and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125 (`12,097` pixels each). No baseline, mask, threshold,
skip, fallback, provider, or acceptance policy changed. Gate cleanup removed
four generated images and the post-gate resource audit reported zero
containers, volumes, sessions, and known bytes. Continue the next bounded
canonical provider/history slice while preserving this visual-only boundary.

## 2026-09-06 — Expose canonical readiness lineage evidence

Product commit `ab09cc60` (`feat(tc2000): expose readiness lineage evidence`)
extends the visual-neutral accessible canonical role evidence in Market Map and
Market Breadth with the API's remaining readiness lineage: availability and
role status, member/placeholder/weighted/classified counts, point-in-time and
history state, per-timeframe analysis-ready counts/bar floors/date ranges,
holdings route, refresh outcome/timestamps/reason, entitlement lifecycle, and
composite readiness reasons. It only formats returned canonical fields; no
provider selection, readiness inference, refresh retry, role substitution,
fallback, visual, or acceptance policy changed. Market Map focused unit
coverage passed `36/36`, full frontend Vitest passed `970/970`, type-check and
production build passed, and authenticated Chromium
`F8s-breadth-family-ratio` passed `1/1`. Teardown removed four generated
images and resource accounting reported zero containers, volumes, sessions,
and known bytes. The next exact-tip gate is required at the next documentation
tip.

## 2026-09-06 — Exact-tip gate after canonical entitlement capability evidence

At exact product tip `de4ab370` (documentation tip `4ed2b533`), the
`full_stack_browser` gate passed locked dependency/migration and workstream
checks, Ruff/format/type-check, backend unit/integration and combined coverage
(`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production image build, compose/provider policy, stack health,
research-runner isolation/resource probes, and authenticated functional
Playwright (`159` passed with `106` documented skips across `265` specs). The
visual matrix completed `104` cases with `98` passes and exactly the six known
state-oracle diffs: watchlist-column-editor-open at visual-1080p-100/125
(`13,844` pixels each), and workspace-floating at visual-1080p-100 (`12,097`),
visual-1080p-125 (`12,097`), visual-1440p-100 (`12,097`), and
visual-1440p-125 (`9,770`). No baseline, mask, threshold, skip, fallback,
provider, or acceptance policy changed. Gate cleanup removed four generated
images and the post-gate resource audit reported zero containers, volumes,
sessions, and known bytes. Continue the next bounded canonical provider/history
slice while preserving this visual-only boundary.

## 2026-09-06 — Expose canonical entitlement capability evidence

Product commit `de4ab370` (`feat(tc2000): expose entitlement capability
evidence`) extends the visual-neutral accessible canonical role evidence in
Market Breadth and Market Map with the API's per-role entitlement capability
map (sorted, human-readable key/value states). Missing maps explicitly report
`capabilities not reported`; no provider selection, readiness inference,
refresh retry, role substitution, fallback, visual, or acceptance policy
changed. Market Map focused unit coverage passed `36/36`, full frontend
Vitest passed `970/970`, type-check/build passed, and rebuilt authenticated
Chromium `F8s-breadth-family-ratio` passed `1/1`. Teardown removed four
generated images and resource accounting reported zero containers, volumes,
sessions, and known bytes. The next exact-tip gate is required at the next
documentation tip.

## 2026-09-06 — Exact-tip gate after canonical continuity evidence

At exact product tip `3a9f89e2` (documentation tip `11b8265d`), the
`full_stack_browser` gate passed locked dependency/migration and workstream
checks, Ruff/format/type-check, backend unit/integration and combined coverage
(`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production image build, compose/provider policy, stack health,
research-runner isolation/resource probes, and authenticated functional
Playwright (`159` passed with `106` documented skips across `265` specs). The
visual matrix completed `104` cases with `98` passes and exactly the six known
state-oracle diffs: watchlist-column-editor-open at visual-1080p-100/125
(`13,844` pixels each), and workspace-floating at visual-1080p-100 (`9,770`),
visual-1080p-125 (`12,097`), visual-1440p-100 (`11,901`), and
visual-1440p-125 (`11,901`). No baseline, mask, threshold, skip, fallback,
provider, or acceptance policy changed. Gate cleanup removed four generated
images and left no containers, volumes, sessions, or known bytes. Continue the
next bounded canonical provider/history slice while preserving this
visual-only boundary.

## 2026-09-06 — Expose canonical continuity gap evidence

Product commit `3a9f89e2` (`feat(tc2000): expose continuity gap evidence`)
extends the visual-neutral accessible canonical role evidence in Market
Breadth and Market Map with continuity status, observed gap count, maximum
interval, dated gap intervals, and snapshot-window capping. When the API does
not report continuity, the evidence explicitly says `continuity not reported`;
no provider selection, readiness inference, refresh retry, role substitution,
fallback, visual, or acceptance policy changed. Market Map focused unit
coverage passed `36/36`, full frontend Vitest passed `970/970`, type-check and
production build passed, and rebuilt authenticated Chromium
`F8s-breadth-family-ratio` passed `1/1`. Teardown removed four generated
images and resource accounting reported zero containers, volumes, sessions,
and known bytes. The next exact-tip gate is required at the next documentation
tip.

## 2026-09-06 — Exact-tip gate after canonical snapshot lineage evidence

At exact product tip `97efe1ea` (documentation tip `86733d42`), the
`full_stack_browser` gate passed locked dependency/migration and workstream
checks, Ruff/format/type-check, backend unit/integration and combined
coverage (`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production image build, compose/provider policy, stack health,
research-runner isolation/resource probes, and authenticated functional
Playwright (`159` passed with `106` documented skips across `265` specs).
The visual matrix completed `104` cases with `98` passes and exactly the six
known state-oracle diffs: watchlist-column-editor-open at visual-1080p-100/125
(`13,844` pixels each), workspace-floating at visual-1080p-100 (`12,097`),
visual-1080p-125 (`12,097`), visual-1440p-100 (`9,770`), and
visual-1440p-125 (`12,097`). No baseline, mask, threshold, skip, fallback,
provider, or acceptance policy changed. Gate cleanup removed four generated
images and left no containers, volumes, sessions, or known bytes. Continue
the next bounded canonical provider/history slice while preserving this
visual-only boundary.

## 2026-09-06 — Expose canonical snapshot lineage evidence

Product commit `97efe1ea` (`feat(tc2000): expose snapshot lineage evidence`)
extends the visual-neutral accessible role evidence in Market Breadth and
Market Map with the selected latest canonical snapshot's composition, as-of,
and known dates, provenance, row count, resolved count, and unresolved count.
Missing values remain explicitly not reported and roles without snapshots
retain unavailable snapshot evidence. The consumers only format returned API
fields; provider selection, readiness inference, refresh retry, role
substitution, fallback, visual, and acceptance policy remain unchanged.
Market Map unit coverage passed `36/36`, full frontend Vitest passed
`970/970`, type-check and production build passed, and authenticated Chromium
`F8s-breadth-family-ratio` passed `1/1` with the lineage fields asserted.
Teardown removed four generated images and resource accounting reported zero
containers, volumes, sessions, and known bytes. The next exact-tip gate is
required at the next documentation tip.

## 2026-09-06 — Exact-tip gate after canonical snapshot quality evidence

At exact product tip `d3547dfd` (documentation tip `a037ea56`), the
`full_stack_browser` gate passed locked dependency/migration and workstream
checks, Ruff/format/type-check, backend unit/integration and combined
coverage (`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production image build, compose/provider policy, stack health,
research-runner isolation/resource probes, and authenticated functional
Playwright (`159` passed with `106` documented skips across `265` specs).
The visual matrix completed `104` cases with `98` passes and exactly the six
known state-oracle diffs: watchlist-column-editor-open at visual-1080p-100/125
(`13,844` pixels each), workspace-floating at visual-1080p-100 (`12,097`),
visual-1080p-125 (`9,770`), visual-1440p-100 (`12,097`), and
visual-1440p-125 (`12,097`). No baseline, mask, threshold, skip, fallback,
provider, or acceptance policy changed. Gate cleanup removed four generated
images and left no containers, volumes, sessions, or known bytes. Continue
the next bounded canonical provider/history slice while preserving this
visual-only boundary.

## 2026-09-06 — Expose canonical snapshot quality evidence

Product commit `d3547dfd` (`feat(tc2000): expose snapshot quality evidence`)
extends the visual-neutral accessible role evidence in Market Breadth and
Market Map with the latest canonical holdings snapshot's source quality and
completeness status. Roles without a snapshot explicitly report unavailable
snapshot evidence; missing quality/completeness fields report not reported.
The consumers format returned API fields only and do not select providers,
infer readiness, retry refreshes, substitute roles, or alter fallback,
visual, or acceptance policy. Market Map unit coverage passed `36/36`, full
frontend Vitest passed `970/970`, type-check and production build passed,
and authenticated Chromium `F8s-breadth-family-ratio` passed `1/1` with the
new evidence asserted. Teardown removed four generated images and resource
accounting reported zero containers, volumes, sessions, and known bytes. The
next exact-tip gate is required at the next documentation tip.

## 2026-09-06 — Exact-tip gate after canonical role identity evidence

At exact product tip `6209b55f` (documentation tip before this receipt
update `4da0f688`), the `full_stack_browser` gate passed locked
dependency/migration and workstream checks, Ruff/format/type-check, backend
unit/integration and combined coverage (`80.93%`; `1320` unit and `384`
integration tests), frontend Vitest (`970/970`), production image build,
compose/provider policy, stack health, research-runner isolation/resource
probes, and authenticated functional Playwright (`159` passed with `106`
documented skips across `265` specs). The visual matrix completed `104`
cases with `98` passes and exactly the six known state-oracle diffs:
watchlist-column-editor-open at visual-1080p-100/125 (`13,844` pixels each),
and workspace-floating at visual-1080p-100/125 and visual-1440p-100/125
(`12,097`, `12,097`, `12,097`, `12,097` pixels in this run). No baseline,
mask, threshold, skip, fallback, provider rule, or acceptance policy changed.
Teardown removed the assigned stack and four generated images; resource
accounting reported zero containers, volumes, sessions, and known bytes.
Preserve the visual-only boundary and continue the next bounded canonical
provider/history slice.

## 2026-09-06 — Expose canonical role identity evidence

Product commit `6209b55f` (`feat(tc2000): expose canonical role identity
evidence`) adds visual-neutral accessible identity evidence to both Market
Breadth and Market Map. Each returned role now reports its verification state,
mapping adapter key/status/confidence, and explicit unmapped/not-reported
states. The consumers only format existing canonical API fields; they do not
select providers, infer readiness, retry refreshes, substitute roles, or alter
fallback, visual, or acceptance policy. Market Map unit coverage passed
`36/36`, full frontend Vitest passed `970/970`, the production image
type-check/build passed, and rebuilt authenticated Chromium
`F8s-breadth-family-ratio` passed `1/1`. Teardown removed four generated
images and resource accounting reported zero containers, volumes, sessions,
and known bytes. The next exact-tip gate is required at the next
documentation tip.

## 2026-09-06 — Exact-tip gate after canonical role evidence

At branch tip `2baa19a0` (product commit `eccae95e`, documentation tip
`2baa19a0`), the exact-tip `full_stack_browser` gate passed the locked
dependency/migration and workstream checks, Ruff/format/type-check, backend
unit/integration and combined coverage (`80.93%`; `1320` unit and `384`
integration tests), frontend Vitest (`970/970`), production build,
compose/provider policy, stack health, research-runner isolation/resource
probes, and authenticated functional Playwright (`159` passed with `106`
documented skips across `265` specs). The visual matrix completed `104`
cases with `98` passes and exactly the six known state-oracle diffs:
watchlist-column-editor-open at visual-1080p-100/125 (`13,844` pixels each),
and workspace-floating at visual-1080p-100/125 and visual-1440p-100/125
(`12,097`, `12,097`, `11,901`, `9,770` pixels in this run). No baseline,
mask, threshold, skip, fallback oracle, provider rule, or acceptance policy
changed. Teardown removed the assigned stack and four generated images;
resource accounting reported zero containers, volumes, sessions, and known
bytes. Preserve the visual-only boundary and continue the next bounded
canonical provider/history slice.

## 2026-09-06 — Expose canonical role evidence in Market Breadth

Product commit `eccae95e` (`feat(tc2000): expose canonical role evidence`)
adds a visual-neutral, accessible labelled status to the Market Breadth family
coverage panel. It formats each returned role's canonical member and
placeholder counts, weighted/classified counts with their statuses,
point-in-time support, history readiness, and composite readiness without
selecting providers, inferring readiness, retrying refreshes, substituting
roles, or changing fallback, visual, or acceptance policy. Full frontend
Vitest passed `970/970`, type-check and production build passed, and rebuilt
authenticated Chromium `F8s-breadth-family-ratio` passed `1/1` with covered
role evidence asserted. Teardown removed four generated images and resource
accounting reported zero containers, volumes, sessions, and known bytes. The
next exact-tip gate is required at the next documentation tip.

## 2026-09-06 — Keep provider-probe evidence visual-neutral

Product commit `da417508` (`fix(tc2000): keep provider probe evidence
visual-neutral`) retains the canonical provider-probe evidence as an
accessible labelled status without adding layout pixels to the benchmark
header. The focused workspace store suite passed `71/71`, type-check and
production build passed, the provider-probe browser assertion passed `1/1`,
and focused board-guided visual cases passed `22/28`; the only six failures
were the pre-existing watchlist-column-editor-open and workspace-floating
state-oracle diffs. No baseline, mask, threshold, skip, fallback, provider,
or acceptance policy changed. The full exact-tip gate must be rerun at the
next documentation tip.

## 2026-09-06 — Exact-tip gate after visual-neutral provider-probe evidence

At product tip `da417508` (documentation tip `4b16ddc1`), the exact-tip
`full_stack_browser` gate passed all locked dependency/migration checks,
workstream validation, Ruff/format/type-check, backend unit/integration and
combined coverage (`80.93%`; `1320` unit and `384` integration tests),
frontend Vitest (`970/970`), production build, compose/provider policy, stack
health, research-runner isolation, and authenticated functional Playwright
(`158` passed with `106` documented skips across `264` specs). The visual
matrix completed `104` cases with `98` passes and exactly the six known
state-oracle diffs: watchlist-column-editor-open at visual-1080p-100/125
(`13,844` pixels each), and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125 (`11,901`, `11,901`, `9,770`, `12,097` pixels in this
run). No baseline, mask, threshold, skip, fallback oracle, provider rule, or
acceptance policy changed. Teardown removed four generated images and resource
accounting reported zero containers, volumes, sessions, and known bytes. The
visual-only boundary is restored; continue the next bounded canonical
provider/history slice.

## 2026-09-06 — Expose canonical universe provenance evidence

Product commit `80f7f266` (`feat(tc2000): expose universe provenance evidence`)
adds an accessible labelled readiness status for the backend's canonical
universe provenance: registry, family count, point-in-time/latest mode,
missing-family count, and explicit provider-call boundary. It formats returned
metadata only; it does not call providers, select routes, infer readiness, or
change fallback, visual, or acceptance policy. Full frontend Vitest passed
`970/970`, type-check and production build passed, and rebuilt authenticated
Chromium passed both canonical evidence assertions (`2/2`). Teardown removed
four generated images and resource accounting reported zero containers,
volumes, sessions, and known bytes. The next exact-tip gate is required at the
following documentation tip.

## 2026-09-06 — Exact-tip gate after canonical universe provenance evidence

At product tip `80f7f266` (documentation tip `b57e5893`), the exact-tip
`full_stack_browser` gate passed all locked dependency/migration checks,
workstream validation, Ruff/format/type-check, backend unit/integration and
combined coverage (`80.93%`; `1320` unit and `384` integration tests),
frontend Vitest (`970/970`), production build, compose/provider policy, stack
health, research-runner isolation, and authenticated functional Playwright
(`159` passed with `106` documented skips across `265` specs). The visual
matrix completed `104` cases with `98` passes and exactly the six known
state-oracle diffs: watchlist-column-editor-open at visual-1080p-100/125
(`13,844` pixels each), and workspace-floating at visual-1080p-100/125 and
visual-1440p-100/125 (`11,901`, `12,097`, `9,770`, `12,097` pixels in this
run). No baseline, mask, threshold, skip, fallback oracle, provider rule, or
acceptance policy changed. Teardown removed four generated images and resource
accounting reported zero containers, volumes, sessions, and known bytes. The
visual-only boundary remains unchanged; continue the next bounded canonical
provider/history slice.

## 2026-09-06 — Exact-tip gate after canonical provider-probe evidence

At product tip `901f56e5` (documentation tip `04661fcb`), the exact-tip
`full_stack_browser` gate passed every locked/non-visual stage and the
functional browser suite (`158` passed, `106` documented skips across `264`
specs), including backend unit/integration and combined coverage (`1320`,
`384`, `80.93%`), frontend Vitest (`970/970`), build, compose/provider
policy, stack health, and runner isolation. The visual matrix completed
`104` cases but failed `27` because the newly visible provider-probe line
changed existing board screenshots in addition to the six known state-oracle
diffs. That line was subsequently made visual-neutral in `da417508`; no
visual baseline, mask, threshold, skip, fallback oracle, provider rule, or
acceptance policy was changed. Teardown removed four generated images and
resource accounting reported zero containers, volumes, sessions, and known
bytes. Rerun the exact-tip gate at `da417508` after the parity fix.

## 2026-09-05 — Surface canonical provider-probe evidence

Product commit `901f56e5` (`feat(tc2000): surface provider probe evidence`)
now renders the backend's provider-neutral readiness probe count, pass count,
recovery count, and latest observation date in the benchmark workstation. The
consumer only formats returned evidence; it does not call providers, choose a
route, infer entitlement, retry refreshes, or change fallback or acceptance
policy. The store suite passed `71/71`; full frontend Vitest passed `970/970`;
type-check and production build passed; rebuilt authenticated Chromium passed
the provider-probe evidence assertion `1/1`. Teardown removed four generated
images and resource accounting reported zero containers, volumes, sessions,
and known bytes. The next exact-tip gate is required at the following
documentation tip.

## 2026-09-05 — Exact-tip gate after canonical holdings-route adapter identity

At product tip `1ca7569d` (documentation tip `5936a6ed`), the exact-tip
`full_stack_browser` gate passed locked dependency/migration checks (migration
compatibility skipped because no migration changes), workstream validation,
Ruff/format/type-check, backend unit/integration and combined coverage
(`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production build, compose/provider policy, stack health,
research-runner isolation, and authenticated functional Playwright (`157`
passed with `106` documented skips across `263` specs). The unchanged visual
matrix completed `104` cases with `98` passes and six state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` pixels each),
and `workspace-floating` at visual-1080p-100 (`11,901`), visual-1080p-125
(`12,097`), visual-1440p-100 (`12,097`), and visual-1440p-125 (`12,097`). No
baseline, mask, threshold, skip, fallback oracle, provider rule, or acceptance
policy changed. Teardown removed the assigned stack and four generated images;
resource accounting reported zero containers, volumes, sessions, and known
bytes. The reproducible blocker remains visual-only; continue the next bounded
canonical provider/history slice.

## 2026-09-05 — Expose canonical holdings-route adapter identity

Product commit `1ca7569d` (`feat(tc2000): expose holdings route adapter`) now
renders the returned holdings-route adapter key beside route status/provider in
both the Market Map canonical-readiness list and the Market Breadth family
coverage strip. Missing adapter metadata remains omitted; the consumers do not
select providers, infer readiness, retry refreshes, alter fallback behavior, or
change visual/acceptance policy. Focused Market Map Vitest passed `36/36`; full
frontend Vitest passed `970/970`; type-check and production build passed. The
first browser invocation was denied by the restricted Chromium sandbox before
assertions; the elevated rerun of authenticated `F8s-breadth-family-ratio`
passed `1/1` with `fixture_holdings` asserted. Teardown removed the assigned
stack and four generated images; resource accounting reported zero containers,
volumes, sessions, and known bytes. The next exact-tip gate is required at the
following documentation tip.

## 2026-09-05 — Exact-tip gate after canonical entitlement audit metadata

At product tip `bd2b14d2` (documentation tip `52fa058f`), the exact-tip
`full_stack_browser` gate passed locked dependency/migration checks (migration
compatibility skipped because no migration changes), workstream validation,
Ruff/format/type-check, backend unit/integration and combined coverage
(`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production build, compose/provider policy, stack health,
research-runner isolation, and authenticated functional Playwright (`157`
passed with `106` documented skips across `263` specs). The unchanged visual
matrix completed `104` cases with `98` passes and six state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` pixels each),
and `workspace-floating` at visual-1080p-100 (`9,770`), visual-1080p-125
(`12,097`), visual-1440p-100 (`12,097`), and visual-1440p-125 (`12,097`). No
baseline, mask, threshold, skip, fallback oracle, provider rule, or acceptance
policy changed. Teardown removed the assigned stack and four generated images;
resource accounting reported zero containers, volumes, sessions, and known
bytes. The reproducible blocker remains visual-only; continue the next bounded
canonical provider/history slice.

## 2026-09-05 — Expose canonical entitlement audit metadata

Product commit `bd2b14d2` (`feat(tc2000): expose entitlement audit metadata`)
now renders the returned entitlement provider, live-probe status, revision,
effective date, and review-due date in both the Market Breadth family coverage
strip and Market Map canonical-readiness list. Missing metadata remains omitted;
the consumer does not infer entitlement, renew credentials, fan out to another
provider, or change fallback or acceptance policy. Focused Market Map Vitest
passed `36/36`; full frontend Vitest passed `970/970`; type-check and
production build passed. Rebuilt authenticated Chromium
`F8s-breadth-family-ratio` passed `1/1` with the entitlement audit label
asserted. The first browser invocation targeted port 80 instead of the
branch-scoped port 28083 and failed before assertions; the corrected rerun
passed. Teardown removed the assigned stack and four generated images;
resource accounting reported zero containers, volumes, sessions, and known
bytes. The next exact-tip gate is required at the following documentation tip.

## 2026-09-05 — Exact-tip gate after canonical holdings-refresh timestamps

At product tip `3c44b2de` (documentation tip `dcd4b4bf`), the exact-tip
`full_stack_browser` gate passed all locked dependency/migration checks
(migration compatibility skipped because no migration changes), workstream
validation, Ruff/format/type-check, backend unit/integration and combined
coverage (`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production build, compose/provider policy, stack health,
research-runner isolation, and authenticated functional Playwright (`157`
passed with `106` documented skips across `263` specs). The unchanged visual
matrix completed `104` cases with `98` passes and six state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` pixels each),
and `workspace-floating` at visual-1080p-100 (`9,770`), visual-1080p-125
(`12,097`), visual-1440p-100 (`12,097`), and visual-1440p-125 (`9,770`). No
baseline, mask, threshold, skip, fallback oracle, provider rule, or acceptance
policy changed. Teardown removed the assigned stack and four generated images;
resource accounting reported zero containers, volumes, sessions, and known
bytes. The result remains visual-only and reproducible; continue the next
bounded canonical provider/history slice while preserving this boundary.

## 2026-09-05 — Expose canonical holdings-refresh timestamps

Product commit `3c44b2de` (`feat(tc2000): expose refresh timestamps`) now
surfaces returned holdings-refresh `checked`, `failed`, and `composition` dates
in the Market Breadth family coverage strip and Market Map canonical readiness
list. Existing status/provider/reason labels remain stable; missing timestamps
remain omitted, and the consumer does not infer readiness, retry providers, or
change fallback or acceptance policy. Focused Market Map coverage passed
`36/36`; full frontend Vitest passed `970/970`; type-check and production
build passed; rebuilt authenticated Chromium `F8s-breadth-family-ratio` passed
`1/1` with `checked 2026-07-03`, `failed 2026-07-04`, and composition dates
asserted. The first retry attempt found no listening stack before assertions;
cleanup was complete, the healthy rebuild passed, and final teardown removed
four generated images with zero containers, volumes, sessions, and known
bytes. The next exact-tip gate is required at the following documentation tip.

## 2026-09-05 — Exact-tip gate after canonical holdings-refresh diagnostics

At product tip `347602f3` (documentation tip `def196bc`), the exact-tip
`full_stack_browser` gate passed all locked dependency/migration checks
(migration compatibility skipped because no migration changes), workstream
validation, Ruff/format/type-check, backend unit/integration and combined
coverage (`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production build, compose/provider policy, stack health,
research-runner isolation, and authenticated functional Playwright (`157`
passed with `106` documented skips across `263` specs). The unchanged visual
matrix completed `104` cases with `98` passes and six state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` pixels each),
and `workspace-floating` at visual-1080p-100 (`9,770`), visual-1080p-125
(`12,097`), visual-1440p-100 (`9,770`), and visual-1440p-125 (`12,097`). No
baseline, mask, threshold, skip, fallback oracle, provider rule, or acceptance
policy changed. Teardown removed the assigned stack and four generated images;
resource accounting reported zero containers, volumes, sessions, and known
bytes. The result is visual-only and reproducible; continue the next bounded
canonical provider/history slice while preserving this boundary.

## 2026-09-05 — Expose canonical holdings-refresh diagnostics

Product commit `347602f3` (`feat(tc2000): expose canonical refresh diagnostics`)
now keeps the backend's holdings-refresh provider and failure reason visible in
both the Market Breadth benchmark-family coverage strip and Market Map's
canonical readiness list. A partial/failed refresh is no longer reduced to a
status-only label; absent provider/timestamp/reason fields remain absent, and
the consumer does not retry providers, infer readiness, or change fallback
policy. Focused Market Map coverage passed `36/36`; full frontend Vitest passed
`970/970`; type-check and production build passed; rebuilt authenticated
Chromium `F8s-breadth-family-ratio` passed `1/1` with the refresh diagnostic
assertion. The first stack startup was interrupted before browser execution;
cleanup restored zero resources, and the clean retry passed. The next exact-tip
gate is required at the following documentation tip.

## 2026-09-05 — Exact-tip gate after canonical composite-readiness reasons

At product tip `606d67ba` (documentation tip `a25f8497`), the exact-tip
`full_stack_browser` gate passed locked dependency/migration checks (migration
compatibility skipped because no migration changes), workstream validation,
Ruff/format/type-check, backend unit/integration and combined coverage
(`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production build, compose/provider policy, stack health,
research-runner isolation, and authenticated functional Playwright (`157`
passed with `106` documented skips across `263` specs). The unchanged visual
matrix completed `104` cases with `98` passes and six state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` pixels each),
and `workspace-floating` at visual-1080p-100 (`5,512`), visual-1080p-125
(`11,901`), visual-1440p-100 (`12,097`), and visual-1440p-125 (`11,901`).
No baseline, mask, threshold, skip, fallback oracle, provider rule, or
acceptance policy changed. Teardown removed the assigned stack and four
generated images; no containers or volumes remained and resource accounting
reported zero known bytes. Preserve this visual-only boundary and continue the
next bounded canonical provider/history slice.

## 2026-09-05 — Surface canonical composite-readiness reasons

The Market Breadth benchmark-family coverage strip now renders the backend's
returned `composite_readiness_reasons` beside each role's readiness status.
Reasons are displayed only when supplied by the canonical coverage contract;
the consumer does not infer readiness, fan out to providers, or alter fallback
or acceptance policy. Product commit `606d67ba` (`feat(tc2000): surface
canonical readiness reasons`) is committed locally. Frontend Vitest passed
`970/970`, type-check and production build passed, and rebuilt authenticated
Chromium `F8s-breadth-family-ratio` passed `1/1` with ready and unavailable
reason labels asserted. Teardown removed the assigned stack and four images;
resource accounting reported zero containers, volumes, and known bytes. The
next exact-tip gate is required at the following documentation tip.

## 2026-09-05 — Exact-tip gate after disclosure effective times

At product tip `e96b081a` (documentation tip `d82ff2ec`), the exact-tip
`full_stack_browser` gate passed locked dependency/migration checks (migration
compatibility skipped because no migration changes), workstream validation,
Ruff/format/type-check, backend unit/integration and combined coverage
(`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production build, compose/provider policy, stack health,
research-runner isolation, and authenticated functional Playwright (`157`
passed with `106` documented skips across `263` specs). The unchanged visual
matrix completed `104` cases with `98` passes and six state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` pixels each),
and `workspace-floating` at visual-1080p-100/125 (`9,770` pixels each),
visual-1440p-100 (`9,770`), and visual-1440p-125 (`12,097`). No baseline,
mask, threshold, skip, fallback oracle, provider rule, or acceptance policy
changed. Teardown removed the assigned stack and four generated images; no
containers or volumes remained and resource accounting was clean. Preserve
this visual-only boundary and continue the next bounded canonical
provider/history slice.

## 2026-09-05 — Surface canonical disclosure effective times

The workstation’s benchmark-family coverage strip now surfaces the returned
snapshot `as_of_date` and `known_at` alongside the latest composition date,
resolution counts, and source provider. These fields are rendered only when
the canonical snapshot supplies them; the consumer does not infer freshness,
substitute roles, or change provider/fallback behavior. Product commit
`e96b081a` (`feat(tc2000): surface disclosure effective times`) is pushed.
Frontend Vitest passed `970/970`, type-check and production build passed, and
the rebuilt authenticated Chromium `F8s-breadth-family-ratio` flow passed `1/1`
with `as of 2026-06-30 · known 2026-06-28T20:00:00Z` asserted. The initial
browser run exposed and the same slice corrected a stale expectation for the
new label ordering. Teardown removed four generated images and all assigned
resources; no provider, fallback, visual-oracle, or acceptance policy changed.
The next exact-tip gate remains required.

## 2026-09-05 — Exact-tip gate after canonical member-history floors

At product tip `2f7c1d84` (documentation tip `f4498c80`), the exact-tip
`full_stack_browser` gate passed locked dependency/migration checks (migration
compatibility skipped because no migration changes), workstream validation,
lint/format/type-check, backend unit/integration and combined coverage
(`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production build, compose/provider policy, stack health,
research-runner isolation, and authenticated functional Playwright (`157`
passed with `106` documented skips across `263` specs). The unchanged visual
matrix completed `104` cases with `98` passes and six state-oracle diffs:
`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` pixels each),
and `workspace-floating` at visual-1080p-100 (`9,770`), visual-1080p-125
(`9,770`), visual-1440p-100 (`9,770`), and visual-1440p-125 (`12,097`).
No baseline, mask, threshold, skip, fallback oracle, provider rule, or
acceptance policy changed. Teardown removed the assigned stack and four
generated images; no containers or volumes remained and resource accounting
was clean. Preserve this visual-only boundary and continue the next bounded
canonical provider/history slice.

## 2026-09-05 — Show canonical member-history floors

The workstation’s family coverage strip now includes each timeframe’s backend
`required_bar_count` floor beside its covered and analysis-ready member counts.
This makes the D1/W1/MN readiness contract explicit in the consumer without
changing history computation, provider selection, fallback, or acceptance
policy. Product commit `2f7c1d84` (`feat(tc2000): show family history floors`)
is pushed. Frontend Vitest passed `970/970`, type-check and production build
passed, and rebuilt authenticated Chromium `F8s-breadth-family-ratio` passed
`1/1` with floors `252/52/24` asserted. Teardown removed four generated
images and all assigned resources. The next exact-tip gate remains required;
preserve the six visual state-oracle diffs and unchanged provider/fallback
policy.

## 2026-09-05 — Surface latest family disclosure provenance

The workstation’s benchmark-family coverage strip now reports the newest
returned disclosure date, resolved/total row counts, unresolved count when
non-zero, and source provider for each role. It selects only the returned
canonical snapshot metadata and does not infer coverage, substitute another
role, or trigger provider fan-out. Product commit `38178e12`
(`feat(tc2000): surface family disclosure provenance`) is pushed. Frontend
Vitest passed `970/970`, type-check and production build passed, and the
rebuilt authenticated Chromium `F8s-breadth-family-ratio` flow passed `1/1`
with the provenance label asserted. Teardown removed four generated images and
all assigned resources. The next exact-tip gate remains required; preserve the
six visual state-oracle diffs and unchanged provider/fallback policy.

## 2026-09-05 — Exact-tip gate after member-bar timeframe readiness

At product tip `a456d7c8` (documentation tip `493c2b66`), the exact-tip
`full_stack_browser` gate passed locked dependency/migration checks (migration
compatibility skipped because no migration changes), workstream validation,
lint/format/type-check, backend unit/integration and combined coverage
(`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production build, compose/provider policy, stack health,
research-runner isolation, and authenticated functional Playwright (`157`
passed with `106` documented skips across `263` specs). The unchanged visual
matrix completed `104` cases with `98` passes and the same six state-oracle
diffs: `watchlist-column-editor-open` at 1080p 100/125 (`13,844` pixels each),
and `workspace-floating` at 1080p 100/125 (`12,097`/`11,901`) and 1440p
100/125 (`12,097`/`11,901`). Teardown removed the assigned stack and four
generated images; no containers or volumes remained and resource accounting
was clean. No baseline, mask, threshold, skip, fallback, provider, or
acceptance policy changed. Preserve this visual-only boundary and continue the
next canonical provider/history slice.

## 2026-09-05 — Surface every canonical member-bar timeframe in family readiness

The Market Breadth benchmark-family coverage summary now reports the canonical
member-bar readiness for each declared analysis timeframe (`D1`, `W1`, and
`MN`), including both covered and analysis-ready member counts. A missing
timeframe is explicit as unavailable; the consumer does not infer readiness
from the daily leg or request provider data. The authenticated
`F8s-breadth-family-ratio` flow now supplies and asserts all three timeframe
contracts. Product commit `a456d7c8` (`feat(tc2000): surface all family bar
timeframes`) is pushed. Frontend Vitest passed `970/970`, type-check and
production build passed, and the rebuilt authenticated Chromium flow passed
`1/1`; stack teardown removed four generated images and all assigned resources.
The exact-tip gate at the next documentation tip remains required; preserve the
six existing visual state-oracle diffs and unchanged provider/fallback policy.

## 2026-09-05 — Assert selected ranking-period values end to end

The authenticated `F8s-breadth-family-ratio` flow now uses period-specific mock
values and asserts the rendered `3M` role-ranking value (`RSP · 34% · Δ 8%`),
not only the request parameter and panel label. This closes the test gap that
could have allowed a hard-coded `1M` summary consumer to pass while the request
was period-aware. The change is test-only; no product, provider, fallback,
membership, provenance, visual-oracle, or acceptance policy changed.

On a rebuilt branch-scoped stack, the focused Chromium flow passed `1/1` after
the initial assertion-format correction; teardown and resource accounting were
clean. Test commit `4302a9a6` (`test(tc2000): assert ranking period values end
to end`) is pushed. The exact-tip gate below was rerun at this product tip.

## 2026-09-05 — Exact-tip gate after ranking-period value assertion

At product tip `4302a9a6` (documentation tip `5962f592`), the exact-tip
`full_stack_browser` gate passed locked dependency/migration checks (migration
compatibility skipped because no migration changes), workstream validation,
lint/format/type-check, backend unit/integration and combined coverage
(`80.93%`; `1320` unit and `384` integration tests), frontend Vitest
(`970/970`), production build, compose/provider policy, stack health,
research-runner isolation, and authenticated functional Playwright (`157/157`
with `106` documented skips across `263` specs). The four-project visual matrix
completed `104` cases with `98` passes and the same six state-oracle diffs:
`watchlist-column-editor-open` at both 1080p scales (`13,844` pixels each),
and `workspace-floating` at 1080p 100/125 (`12,097`/`11,901`) and 1440p
100/125 (`12,097`/`11,901`). Teardown removed the assigned stack and generated
resources; resource accounting was clean. No baseline, mask, threshold, skip,
fallback, provider, or acceptance policy changed. Preserve this visual-only
boundary and continue the next canonical provider/history slice.

## 2026-09-05 — Honor the selected ranking period in summaries

The role-ranking and cross-family ranking summary rows now read the selected
`family_rank_period` value instead of retaining a hard-coded `1M` lookup. The
request/cache horizon and the rendered summary values therefore stay aligned
for every supported period; no provider, fallback, membership, provenance,
visual-oracle, or acceptance policy changed.

Focused frontend coverage passes `136/136`, TypeScript and production build
pass, and authenticated Chromium `F8s-breadth-family-ratio` passes `1/1` on a
rebuilt branch-scoped stack with the `3M` request/render assertions. Teardown
and resource accounting were clean. Product commit `cdcef088`
(`fix(tc2000): honor selected ranking period in summaries`) is pushed to
`origin/feat/tc2000-frontend-rework`; rerun the exact-tip gate at the next
coherent documentation tip, preserving the six known visual state-oracle
diffs and unchanged provider/fallback policy.

## 2026-09-05 — Exact-tip gate after period-aware summary correction

The exact-tip `full_stack_browser` gate at metadata tip `20c750a2` (product tip
`cdcef088`) passed locked dependency/migration checks (migration compatibility
skipped because no migration changes), workstream validation, lint/format/type-
check, backend unit/integration and combined coverage (`80.93%`; `1320` unit
and `384` integration tests), frontend Vitest (`970/970`), production build,
compose/provider policy, stack health, research-runner isolation, and functional
Playwright (`157/157` with `106` documented skips across `263` specs). The
visual matrix completed `104` cases with `98` passes and the same six state-
oracle diffs: `watchlist-column-editor-open` at 1080p 100% and 125%, and
`workspace-floating` at 1080p 100%/125% and 1440p 100%/125%. Teardown removed
the assigned stack and generated resources; resource accounting was clean. No
baseline, mask, threshold, skip, fallback, provider, or acceptance policy
changed. Preserve this visual-only boundary and continue the next canonical
analytics/provider slice.

## 2026-09-05 — Exact-tip gate after configurable family ranking horizons

The exact-tip `full_stack_browser` gate at metadata tip `d64c9c78` (product tip `bbe011db`)
passed locked dependency/migration checks (migration compatibility skipped because no migration
changes), workstream validation, lint/format/type-check, backend unit/integration and combined
coverage (`80.93%`; `1320` unit and `384` integration tests), frontend Vitest (`970/970`),
production build, compose/provider policy, stack health, research-runner isolation, and functional
Playwright (`157/157` with `106` documented skips across `263` specs). The visual matrix completed
`104` cases with `98` passes and the same six state-oracle diffs: `watchlist-column-editor-open`
at 1080p 100% and 125%, and `workspace-floating` at 1080p 100%/125% and 1440p 100%/125%.
Teardown removed the assigned stack and generated resources; resource accounting was clean. No
baseline, mask, threshold, skip, fallback, provider, or acceptance policy changed. Preserve the
visual-only boundary and continue the next canonical analytics/provider slice.

## 2026-09-05 — Expose configurable family ranking horizons

The benchmark-family relative-strength surface now exposes the backend's canonical ranking-period
contract (`1D`, `1W`, `1M`, `3M`, `6M`, `YTD`, `1Y`) as the persisted
`family_rank_period` workstation setting. The selected horizon drives role ranking, concentration
current/history, and cross-family ranking current/history requests and cache keys, and is visible
in each affected panel label. Invalid persisted values safely fall back to `1M`; no provider,
fallback, membership, provenance, visual-oracle, or acceptance policy changed.

Focused frontend coverage passes `136/136`, TypeScript and production build pass, and authenticated
Chromium `F8s-breadth-family-ratio` passes `1/1` with the `3M` request and rendered labels asserted
on a rebuilt branch-scoped stack. Teardown and resource accounting were clean. The exact-tip gate
at this documentation/product tip is recorded above; preserve the six existing visual state-oracle
diffs and continue the next canonical analytics/provider slice.

## 2026-09-05 — Exact-tip gate after cross-family rank history

The exact-tip `full_stack_browser` gate at metadata tip `228af958` (product tip `1ae69113`)
passed locked dependency/migration checks (migration compatibility skipped because no migration
changes), workstream validation, lint/format/type-check, backend unit/integration and combined
coverage (`80.93%`), frontend Vitest (`970/970`), production build, compose/provider policy,
stack health, research-runner isolation, and functional Playwright (`157/157` with `106`
documented skips across `263` specs). The visual matrix completed `104` cases with `98` passes
and the same six state-oracle diffs: `watchlist-column-editor-open` at 1080p 100% and 125%,
and `workspace-floating` at 1080p 100%/125% and 1440p 100%/125%. Teardown removed the assigned
stack and generated resources; resource accounting was clean. No baseline, mask, threshold, skip,
fallback, provider, or acceptance policy changed; preserve the visual-only boundary and continue
canonical analytics/provider work.

## 2026-09-05 — Render cross-family rank history

The cross-family ranking panel now renders canonical historical `rank` values as a separate
inverted-axis, family-labelled uPlot chart alongside relative-performance history. Timestamps are
aligned across available families, missing observations remain `null`, and malformed/non-finite
timestamps or ranks fail closed with an explicit unavailable state. The current ranking summary,
performance history, coverage, warnings, and provenance remain unchanged.

Lifecycle/alignment coverage passes `32/32`, TypeScript and production build pass, and authenticated
Chromium `F8s-breadth-family-ratio` passes `1/1` with the rank chart asserted visible on a rebuilt
branch-scoped stack. Teardown removed all assigned resources. The exact-tip gate at this product tip
is pending; preserve the six existing visual state-oracle diffs and unchanged provider/fallback and
acceptance policy.

Product commit `1ae69113` (`feat(tc2000): render cross-family rank history`) is pushed to
`origin/feat/tc2000-frontend-rework`; the durable receipt records the focused and authenticated
checks above.

## 2026-09-05 — Exact-tip gate after concentration metrics history

The exact-tip `full_stack_browser` gate at metadata tip `a399697a` (product tip `d9b9de95`)
passed locked dependency/migration checks (migration compatibility skipped because no migration
changes), workstream validation, lint/format/type-check, backend unit/integration and combined
coverage (`80.93%`), frontend Vitest (`967/967`), production build, compose/provider policy,
stack health, research-runner isolation, and functional Playwright (`157/157` with `106`
documented skips across `263` specs). The visual matrix completed `104` cases with `98` passes
and the same six state-oracle diffs: `watchlist-column-editor-open` at 1080p 100% and 125%,
and `workspace-floating` at 1080p 100%/125% and 1440p 100%/125%. Teardown removed the assigned
stack and generated resources; resource accounting was clean. No baseline, mask, threshold, skip,
fallback, provider, or acceptance policy changed; preserve the visual-only boundary and continue
canonical analytics/provider work.

## 2026-09-05 — Render benchmark-family concentration metrics history

The concentration panel now renders canonical point-in-time `top_n_weight` and `hhi` history for
each available benchmark-family role alongside the existing dispersion history. Both metrics use
the aligned timestamp union, preserve missing observations as `null`, validate finite values, and
fail closed with an explicit unavailable state. Role colours identify the family leg and dashed
lines identify HHI; the latest concentration values, coverage, warnings, membership semantics, and
provenance remain unchanged.

Lifecycle/alignment coverage passes `29/29`, TypeScript and production build pass, and authenticated
Chromium `F8s-breadth-family-ratio` passes `1/1` with the metrics chart asserted visible on a rebuilt
branch-scoped stack. Teardown removed all assigned resources. The exact-tip gate at this product
tip is pending; preserve the six existing visual state-oracle diffs and unchanged provider,
fallback, and acceptance policy.

Product commit `d9b9de95` (`feat(tc2000): render concentration metrics history`) is now pushed to
`origin/feat/tc2000-frontend-rework`; the durable receipt records the focused and authenticated
checks above. The exact-tip gate remains pending at the next documentation tip.

## 2026-09-05 — Exact-tip gate after family ratio history

The exact-tip `full_stack_browser` gate at metadata tip `f6607ad7` (product tip `852c1613`)
passed locked dependency/migration checks, workstream validation, lint/format/type-check, backend
unit/integration and combined coverage (`80.93%`), frontend Vitest (`964/964`), production build,
compose/provider policy, stack health, runner isolation, and functional Playwright (`157/157` with
`106` documented skips). The four-project visual matrix completed `104` cases with `98` passes and
the same six state-oracle diffs: `watchlist-column-editor-open` at both 1080p scales and
`workspace-floating` at all four scales. Teardown and resource accounting were clean. No baseline,
mask, threshold, skip, fallback, provider, or acceptance policy changed; preserve this visual-only
boundary and continue the next canonical analytics/provider slice.

## 2026-09-05 — Render family relative-strength history

The Market Map family relative-strength surface now renders the canonical batch ratio points as
an aligned role-coloured uPlot history chart. Missing timestamps remain `null` and malformed or
non-finite points fail closed with an explicit unavailable state; the existing latest ratio values,
coverage, warnings, and provenance remain visible.

Lifecycle/alignment coverage passes `26/26`, TypeScript and production build pass, and authenticated
Chromium `F8s-breadth-family-ratio` passes `1/1` with the history chart asserted visible on a rebuilt
branch-scoped stack. Teardown removed all assigned resources. The exact-tip gate at this product tip
is pending; preserve the six existing visual state-oracle diffs and unchanged provider/fallback policy.

## 2026-09-05 — Exact-tip gate after cross-family ranking history

The exact-tip `full_stack_browser` gate at metadata tip `a9f7451c` (product tip `335992cd`)
passed locked dependency/migration checks, workstream validation, lint/format/type-check, backend
unit/integration and combined coverage (`80.93%`), frontend Vitest, production build,
compose/provider policy, stack health, runner isolation, and the visual matrix execution. Functional
Playwright completed `156/157` with `106` documented skips; `F8s-market-map-watchlist` timed out
once on a detached Study Lab button during a re-render. A fresh isolated retry passed `1/1`, so
the failure is recorded as a transient DOM-detach flake rather than a reproducible regression.
Teardown and resource accounting were clean. No baseline, mask, threshold, skip, fallback, provider,
or acceptance policy changed; preserve the six existing visual state-oracle diffs and continue the
next canonical analytics/provider slice.

## 2026-09-05 — Render cross-family ranking history

The workstation now renders the canonical cross-family ranking-history `relative_performance`
series as family-labelled uPlot lines beneath the ranking summary. Timestamps are aligned across
available families and missing observations remain `null`; no rank or performance values are
forward-filled. Invalid or unavailable rows fail closed with an explicit unavailable state, and
the existing family ranking/history text remains visible.

Lifecycle/alignment coverage passes `23/23`, TypeScript and production build pass, and authenticated
Chromium `F8s-breadth-family-ratio` passes `1/1` with the historical relative-performance chart
asserted visible on a rebuilt branch-scoped stack. Teardown removed all assigned resources. The
exact-tip gate at this new product tip is pending; preserve the six existing visual state-oracle
diffs and unchanged provider/fallback policy.

## 2026-09-05 — Exact-tip gate after concentration history

The exact-tip `full_stack_browser` gate at metadata tip `6590c2b1` (product tip `8697e7b8`)
passed locked dependency/migration checks, workstream validation, lint/format/type-check, backend
unit/integration and combined coverage, frontend Vitest, production build, compose/provider policy,
stack health, runner isolation, and functional Playwright (`157/157`, with `106` documented skips
across `263` specs). The visual matrix remains `98/104`; the same six state-oracle assertions fail:
`watchlist-column-editor-open` at both 1080p scales and `workspace-floating` at all four scales.
Teardown removed the assigned stack and generated resources. No baseline, mask, threshold, skip,
fallback, provider, or acceptance rule changed. Continue the next canonical analytics/provider slice.

## 2026-09-05 — Render benchmark-family concentration history

The workstation now renders the canonical benchmark-family concentration-history `dispersion`
series as role-coloured uPlot lines beneath the point-in-time concentration summary. Timestamps
are aligned across available roles and missing observations remain `null`; the chart never
forward-fills membership, returns, or weights. Invalid or unavailable dispersion remains an
explicit unavailable state, and no provider fallback, fabricated data, visual oracle, or
acceptance rule changed.

Lifecycle/alignment coverage passes `20/20`, TypeScript and production build pass, and authenticated
Chromium `F8s-breadth-family-ratio` passes `1/1` with the dispersion chart asserted visible on a
rebuilt branch-scoped stack. Teardown removed all assigned resources. The exact-tip gate at this
new product tip is pending; preserve the six existing visual state-oracle diffs and rerun it at
the next coherent documentation tip.

## 2026-09-05 — Exact-tip gate after breadth-history chart

The exact-tip `full_stack_browser` gate at metadata tip `9c230fd5` (product tip `45ae7e9b`)
passed locked dependency/migration checks, workstream validation, lint/format/type-check, backend
unit/integration and combined coverage, frontend Vitest, production build, compose/provider policy,
stack health, runner isolation, and functional Playwright (`157/157`, with `106` documented skips
across `263` specs). The visual matrix remains `98/104`; the same six state-oracle assertions fail:
`watchlist-column-editor-open` at both 1080p scales and `workspace-floating` at all four scales.
Teardown removed the assigned stack and generated resources. No baseline, mask, threshold, skip,
fallback, provider, or acceptance rule changed. Continue the next canonical provider/history slice.

## 2026-09-05 — Render benchmark-family breadth history

The workstation now renders the canonical per-role benchmark-family breadth-history series as a
role-coloured uPlot chart, using each role's `above_ma.ma20` observations on the aligned timestamp
union. Missing timestamps remain `null` (no forward fill), while the existing aligned-point and
role-local analysis-readiness summaries remain visible. Invalid or unavailable history destroys
the chart cleanly; no provider fallback, fabricated data, visual oracle, or acceptance rule
changed.

Focused lifecycle coverage passes `17/17`, TypeScript and production build pass, and authenticated
Chromium `F8s-breadth-family-ratio` passes `1/1` on a rebuilt branch-scoped stack. Teardown removed
all assigned resources and the temporary builder. The exact-tip exhaustive gate at this new
product tip remains pending; preserve the six existing visual state-oracle diffs and rerun the gate
at the next coherent documentation tip.

## 2026-09-05 — Exact-tip gate after per-role breadth-history readiness

The exact-tip `full_stack_browser` gate at `437e35b8` passed every non-visual stage and the
functional Playwright suite (`157/157`, with `106` documented skips across `263` specs). Backend
combined coverage, frontend Vitest (`952/952` across `109` files), build, compose/provider policy,
stack health, and runner-isolation probes all passed. The four-project visual matrix remains
`98/104`; the same six state-oracle assertions fail: `watchlist-column-editor-open` at 1080p-100
and 1080p-125 (`13,844` pixels each), and `workspace-floating` at 1080p-100/125/1440p-100/1440p-125
(`9,770`/`5,512`/`9,770`/`12,097` pixels in this run). Diff counts vary with the existing
floating-window capture timing, but the failing assertion set is unchanged. Teardown removed all
assigned resources and no baseline, mask, threshold, skip, fallback, provider, or acceptance rule
changed. Continue the next canonical provider/history slice while preserving this visual boundary.

## 2026-09-05 — Expose per-role benchmark breadth-history analysis readiness

Benchmark-family breadth history now reports role-local readiness instead of exposing only
aligned-point coverage. Each available role includes its member count, count and percentage of
members meeting the canonical D1/W1/MN analysis floors (252/52/24 bars), the required floor, and a
`ready`/`partial`/`pending`/`unavailable` status. The workstation keeps the aligned-point summary
and adds the per-role analysis-ready summary, so partial historical coverage is visible without
claiming that the family is study-ready. Missing roles remain explicit and no provider fallback or
fabricated history was introduced.

Product commit `6b4d47d1` (`feat(tc2000): expose family breadth history readiness`) is pushed to
`origin/feat/tc2000-frontend-rework`. Ruff/format, TypeScript, focused Market Map component
coverage (`36/36`), and the focused benchmark-family history integration assertion (`1/1`) pass;
authenticated Chromium `F8s-breadth-family-ratio` passes `1/1` on a rebuilt branch-scoped stack.
Teardown removed the assigned containers, volumes, network, images, and temporary builder. The
exact-tip exhaustive gate after this product commit is pending; preserve the six unchanged visual
state-oracle diffs and rerun that gate at the next coherent tip.

## 2026-09-05 — Promote compatible structured Study outputs to Strategy signals

R4 now closes the structured-result Strategy-signal fan-out for compatible shapes. Persisted
Research Results offers `Save Strategy signal` for Boolean artifacts and for finite thresholded
`series`/range-center artifacts; each promotion creates a typed Boolean signal asset, preserves
the selected output, canonical member IDs/source/membership, Study/run/dataset lineage, and an
explicit adapter/threshold where required, then hands the immutable version to Strategy Lab.
The isolated Strategy runner now carries promotion adapters, series targets, and selected output
names from immutable CodeVersion lineage into the queued canonical-data run, so threshold semantics
are applied outside user code at current observations. Unsupported shapes and missing canonical
members remain unavailable; event signal handling is unchanged.

Product commit `9080e4de` (`feat(tc2000): promote structured studies to strategy signals`) is pushed
to `origin/feat/tc2000-frontend-rework`. Focused Research Results/capability coverage passes `33/33`,
the Strategy Lab service/job tests pass `16/16` with `--no-cov`, focused Strategy Lab API signal
integration passes `2/2` with Docker, frontend type-check/build and `git diff --check` pass, and the
authenticated F8t Results flows (structured matrix plus series threshold) pass `2/2` on a rebuilt
branch-scoped Docker stack with clean teardown/resource accounting. The exact-tip exhaustive gate
after the follow-up capability-matrix test correction at tip `a5dc4957` passed every non-visual
stage and functional Playwright (`157/157`, with `106` documented skips across `263` specs).
Combined backend coverage was `80.92%` (unit/integration `1320` and `384` respectively), frontend
Vitest was `952/952` across `109` files, and the four-project visual matrix was `98/104`. The six
unchanged state-oracle diffs are `watchlist-column-editor-open` at visual-1080p-100/125 (`13,844`
pixels each) and `workspace-floating` at visual-1080p-100 (`12,097`), visual-1080p-125 (`9,770`),
visual-1440p-100 (`12,097`), and visual-1440p-125 (`12,097`). Stack teardown and resource
accounting were clean; no visual/provider fallback policy changed. Continue with the next
canonical provider/history slice.

## 2026-09-05 — Aggregate readiness gate receipt

The authenticated focused Market Map history flow passed `1/1` on a rebuilt branch-scoped
stack. The exact-tip `full_stack_browser` gate at metadata tip `4932fbc2` (product tip
`ea4514fa`) passed all locked dependency/migration, workstream, lint/format/type-check,
backend unit/integration and combined coverage (`80.92%`), frontend Vitest (`952/952`),
build, compose/provider, stack-health, runner-isolation, and functional Playwright stages
(`157/157` with `106` documented skips across `263` specs). The four-project visual matrix
remains `98/104`: the six unchanged state-oracle diffs are `watchlist-column-editor-open`
at visual-1080p-100/125 (`13,844` pixels each) and `workspace-floating` at
visual-1080p-100/125/1440p-100/1440p-125 (`12,097`/`12,097`/`9,770`/`9,770` pixels).
No baseline, mask, threshold, skip, fallback oracle, provider rule, or acceptance policy
changed; teardown removed all assigned resources. The gate is explicitly blocked only by
those existing visual diffs, while canonical provider/history breadth and remaining R2-R6
gaps stay open.

This is the concise, branch-owned execution map for the TC2000 frontend rework. The chronological
records in `docs/project-todos.md`, `docs/tc2000-parity.md`,
`docs/tc2000-acceptance-governance.md`, and `docs/tc2000-visual-parity.md` remain the detailed
evidence ledgers. If a summary here conflicts with a dated test receipt or the current code, the
current code and fresh evidence win.

## 2026-09-05 — Separate aggregate analysis readiness from covered history

The generic watchlist source-history response now includes an aggregate `analysis_ready` boolean
and `analysis_ready_status` across every requested timeframe. The existing `overall_status` remains
the compatibility-oriented covered/worker state, while the new aggregate applies the declared
D1/W1/MN floors (252/52/24 bars) to prevent daily-only or one-bar coverage from being presented as
study-ready. Market Map renders both states. Product commit `ea4514fa` (`feat(tc2000): expose
aggregate history readiness`) is committed on the feature branch. Backend watchlist-history units
pass `6/6`, full backend units pass `1,319/1,319` with the existing `34` warnings, focused Market
Map component coverage passes `36/36`, full frontend Vitest remains `952/952` across `109` files,
TypeScript, Ruff, format, and `git diff --check` pass. The exhaustive gate and authenticated
browser recheck at this new product tip remain pending; the prior gate's six unchanged visual
state-oracle diffs remain explicit.

## 2026-09-05 — Generic source history exposes analysis-ready floors

The shared watchlist source-history status now reports analysis-ready members and percentages for
the canonical D1/W1/MN floors (252/52/24 bars), alongside the existing covered-member, bar-count,
date-range, and worker-progress fields. Market Map labels surface the distinction without changing
the compatibility-oriented overall status or any provider entitlement/fallback behavior. Product
commit `8490f2dd` (`feat(tc2000): expose history analysis-ready floors`) is pushed to
`origin/feat/tc2000-frontend-rework`.
Backend units passed `1,318/1,318`; the focused history unit/API checks passed `5/5` and `1/1` (the
selected API invocation has the expected coverage-floor caveat); frontend component coverage passed
`36/36`, full frontend Vitest `952/952` across `109` files, TypeScript, Ruff/format, and diff checks
passed, and authenticated F8s-market-map-watchlist passed `1/1` on a rebuilt branch-scoped stack
with clean teardown. The exact-tip exhaustive gate then ran at metadata tip `0af0bed5` (product tip
`8490f2dd`): all non-visual stages and functional Playwright passed (`157/157` with `106` documented
skips across `263` specs). The unchanged visual matrix completed `104` cases with `98` passes and
six failures: `watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` pixels each), and
`workspace-floating` at visual-1080p-100/125/1440p-100/1440p-125 (`9,770`/`11,901`/`11,901`/
`12,097` pixels). Teardown and resource accounting were clean; existing visual acceptance remains
unchanged and the six state-oracle diffs are the only gate blocker.

The current product slice is `8490f2dd` (`feat(tc2000): expose history analysis-ready floors`).

The preceding product slice is `7f672897` (`feat(tc2000): promote range centers through thresholds`).
The primary Study Lab and persisted Research Results now expose explicit finite comparison controls
for completed structured `range` artifacts with aligned center values. A user can save a typed
Boolean column or reuse the condition for a watchlist filter, scan, Market Gauge, or alert. The
immutable code asset and screener provenance retain the selected output, canonical members/source/
membership, timeframe, dataset/run lineage, `range_center_target_to_boolean` adapter, and
`study_range_center_threshold_as_boolean` semantics; lower/upper bands remain source-only. The
prepared-universe runner requests the range output, extracts each member's latest finite center, and
applies the supported relation outside user code. Backend runner coverage passed `113/113`, code API
`24/24`, screener integration `27/27`, focused frontend coverage `63/63`, full frontend Vitest
`952/952` across `109` files, TypeScript/build/Ruff/workstream/diff checks passed, and authenticated
F8t-results browser proof passed `1/1` on a rebuilt branch-scoped Docker stack with clean teardown.
The commit is pushed to `origin/feat/tc2000-frontend-rework`. The exact-tip gate then ran at metadata
tip `93883674` after formatter correction `c2f3a588` (product tip `7f672897`): all non-visual stages
and functional Playwright passed (`157/157` with `106` documented skips across `263` specs), while
the visual matrix remained `98/104` with six unchanged state-oracle failures. The six diffs are
`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` pixels each) and
`workspace-floating` at visual-1080p-100/125/1440p-100/1440p-125
(`11,901`/`11,901`/`12,097`/`9,770` pixels). No visual policy, provider fallback rule, or
acceptance policy changed; teardown and resource accounting were clean. Canonical provider/history,
richer Study, native-window/accessibility/security, dense-data, and visual-oracle gaps remain open.

The preceding product slice is `928bf8ae` (`feat(tc2000): promote range centers to watchlist columns`).
The primary Study Lab and persisted Research Results now expose a typed latest-value watchlist-column
promotion for completed structured `range` artifacts with aligned finite `center` values. Lower/upper
band values remain source-only; the saved code asset declares scalar output plus the explicit
`range_center_to_scalar` adapter and `study_range_center_result_as_latest_watchlist_column` lineage.
The immutable research job envelope carries that adapter into prepared-universe batch execution,
which requests the range output and extracts the latest finite center as each member's scalar cell
outside user code. Backend runner coverage passed `112/112`, job-envelope coverage `5/5`, code API
integration `24/24`, focused frontend coverage `61/61`, full frontend Vitest `950/950` across `109`
files, type-check/build/diff checks passed, and authenticated F8t-results plus the adjacent primary
threshold flow passed `1/1` each on a rebuilt branch-scoped Docker stack. The commit is pushed to
`origin/feat/tc2000-frontend-rework`; focused teardown/resource accounting was clean. The exact-tip
gate then passed every non-visual stage and functional Playwright (`157` passed, `106` documented
skips across `263` specs). The unchanged four-project visual matrix completed `104` cases with
`98` passes and six state-oracle failures: `watchlist-column-editor-open` at visual-1080p-100/125
(`13,844` pixels each), and `workspace-floating` at visual-1080p-100/125/1440p-100/125 (`12,097`
pixels each). No visual baseline, mask, threshold, skip, fallback oracle, provider rule, or
acceptance policy changed; assigned stack teardown and resource accounting were clean. Canonical
provider/history, richer Study, native-window/accessibility/security, dense-data, and visual-oracle
gaps remain open.

The preceding product slice is `b6316871` (`feat(tc2000): promote Study Lab series thresholds`). The
primary Study Lab now exposes the same safe threshold fan-out as persisted Research Results for
completed single-output finite numeric `series` runs: an explicit operator (`gt`, `gte`, `lt`,
`lte`, `eq`, or `ne`) and finite threshold can produce a typed Boolean column or one reusable
current-data condition for a watchlist filter, scan, Market Gauge, or alert. The selected output,
canonical member IDs/source/membership, timeframe, dataset/run lineage, and
`series_target_to_boolean` adapter remain explicit; the immutable Study source is not rewritten and
unsupported/non-finite runs remain unavailable. Focused Study Lab coverage passed `26/26`; full
frontend Vitest passed `949/949` across `109` files; TypeScript, production build, and diff checks
passed; authenticated F9j passed `1/1` on a rebuilt branch-scoped Docker stack. The exact-tip gate
at this product tip passed every non-visual stage, including backend units `1,315/1,315`, backend
integration `384/384` with the existing `54` warnings, combined coverage `80.91%`, and functional
Playwright `157` passed with `106` documented skips across `263` specs. The four-project visual
matrix remains `98/104` with the same six state-oracle diffs; teardown and resource accounting were
clean, and no visual policy or provider fallback rule changed. The preceding persisted-results
slice is `225ab93f`, which supplies the same adapter contract at the Research Results boundary.
Primary provider/history, richer Study, native-window/accessibility/security, dense-data, and
visual-oracle gaps remain open.

The preceding product slice was `225ab93f` (`feat(tc2000): promote Study series thresholds`). Persisted
Research Results now exposes an explicit operator/threshold control for finite numeric `series`
artifacts and promotes the selected output into a typed Boolean column, watchlist filter, scan,
Market Gauge, or alert. The source run/code/output identity, declared canonical members, timeframe,
dataset lineage, threshold relation, and `series_target_to_boolean` adapter remain explicit; the
immutable Study source is never rewritten. The backend validates that the source actually declares a
numeric series and that the relation uses a finite supported threshold, then carries the metadata
through the screener into the isolated runner. Focused Results/capability coverage passed `34/34`,
full frontend Vitest passed `948/948` across `109` files, type-check/build/diff checks passed, and
backend code+screener integration passed `51/51` with the existing NumPy deprecation warnings.
The authenticated `F8t-results-series-threshold` flow passed `1/1` on a rebuilt branch-scoped
Docker stack with the operator/threshold, Boolean asset lineage, canonical member universe, and
screener provenance assertions. Exact-tip gate evidence is now recorded below: the first functional
pass had one transient `F8j` timeout, isolated `F8j` passed `1/1`, and the complete rerun passed
`153/153` with `109` documented skips; the visual-only matrix remains `98/104` with the same six
state-oracle diffs. The primary Study
Lab direct threshold controls, canonical provider/history enrichment, native-window/accessibility/
security, dense-data, and visual-oracle gaps remain open; no visual policy or provider fallback rule
changes.

The latest product slice is `ad90b988` (`feat(tc2000): surface source history ranges`). Market
Map's canonical source-history readiness strip now renders every returned timeframe, not only the
first, with covered/member counts, observed bar totals, and oldest/newest dates; missing bounds
remain explicit as `unknown` and no date is inferred or substituted. Focused Market Map coverage
passed `36/36`, the full frontend suite passed `947/947` across `109` files, TypeScript/type-check,
production build, and diff checks passed, and the authenticated F8s family-matrix check passed
`1/1` with the range assertion on a rebuilt branch-scoped Docker stack. Teardown removed all
assigned resources. The preceding product slice `6fa41b81` added the same observed date bounds to
the benchmark-family role labels; this follow-on generalizes the visibility to all source-history
timeframes without changing provider or fallback policy.

The latest exact-tip exhaustive gate ran at metadata tip `70d99baf` (product tip `ad90b988`, with
the source-history readiness records committed). Locked dependency/migration checks, Ruff/format,
TypeScript, backend units `1,315/1,315`, integration `383/383` with the existing `54` warnings,
combined coverage `80.90%`, frontend Vitest `947/947` across `109` files, production build,
compose/provider policy, stack health, runner isolation, and authenticated functional Playwright
(`155` passed, `106` documented skips across `261` specs) all passed. The four-project visual
matrix remains the only failing stage at `98/104`: `watchlist-column-editor-open` differs by
`13,844` pixels at 1080p-100/125, and `workspace-floating` differs by
`11,901`/`12,097`/`12,097`/`5,512` pixels at 1080p-100/125 and 1440p-100/125. No visual baseline,
mask, threshold, skip, fallback oracle, provider rule, or acceptance policy changed; the
workspace-floating actual still intentionally contains canonical benchmark rows after late-popout
hydration. The first full rerun had one transient F8r Python Library narrow-window discovery
failure; a fresh-stack isolated retry passed `1/1` and `3/3` repeats, and the subsequent full
functional rerun passed. Teardown and resource accounting were clean. The goal remains active while
canonical provider/history, richer Study, native-window, accessibility/security, dense-data, and
visual-oracle gaps remain open.

The preceding product slice is `22fd676e` (`feat(tc2000): promote structured study events to signals`).
Research Results now offers `Save Strategy signal` for a named event artifact from a completed
multi-output Study run. It creates an explicit `events` signal asset for the selected output and
hands that immutable version to Strategy Lab with source run/code/dataset/output lineage,
`events_to_signal` semantics, and an explicit current-data re-evaluation boundary. Focused
Research Results/capability tests passed `33/33`; full frontend Vitest passed `947/947` across
`109` files; type-check, production build, and diff checks passed; authenticated F8t-results passed
`1/1` on the rebuilt branch-scoped stack with clean teardown/resource accounting. This closes the
structured-event signal cell without coercing event lists into Boolean values or widening the
declared universe.

The latest product fix is `3a7e4861` (`feat(tc2000): preserve Study event signal lineage`). The
primary Study Lab now routes both single-output and named multi-output `events` artifacts through
an explicit `events_to_signal` asset adapter before creating a Strategy Lab signal. The selected
artifact name, immutable source/run/dataset lineage, current-data re-evaluation semantics, and
point-in-time limitation are preserved; the raw Study version is no longer reused without a
promotion contract. Focused Study Lab coverage passed `25/25`, full frontend Vitest passed
`947/947` across `109` files, type-check/build/diff checks passed, and authenticated F8o passed
`1/1` on the rebuilt branch-scoped stack with clean teardown/resource accounting.

The backend contract for this path is now covered by
`test_multi_output_study_event_output_promotes_to_strategy_signal`. It verifies that the selected
named event output is persisted as an `events` signal asset with the explicit `events_to_signal`
adapter and source/output lineage, then promoted through Strategy Lab without changing the
immutable source. The focused test passed `1/1` with `--no-cov`; the full backend integration
suite passed `383/383` with the existing `54` warnings. The integration-only coverage report is
`48.09%` and hits the configured `55%` floor because the normal threshold is measured across the
combined unit/integration gate; this is recorded as an invocation-scope caveat.

The preceding exact-tip exhaustive gate ran at metadata tip `aa8fbd0b` (product tip `3a7e4861`, with
the durable Study event-lineage records committed). All non-visual stages and authenticated
functional Playwright passed: backend units `1,315/1,315`, integration `383/383` with the existing
`54` warnings, combined coverage `80.90%`, frontend Vitest `947/947` across `109` files, and
functional E2E `155` passed with `106` documented skips across `261` specs. The four-project visual
matrix remains the only failing stage at `98/104`: `watchlist-column-editor-open` differs by
`13,844` pixels at 1080p-100/125, and `workspace-floating` differs by
`11,901`/`9,770`/`9,770`/`12,097` pixels at 1080p-100/125 and 1440p-100/125. No visual
baseline, mask, threshold, skip, fallback oracle, provider rule, or acceptance policy changed;
assigned stack teardown and resource accounting were clean. The goal therefore remains active while
canonical provider/history, richer Study, native-window, accessibility/security, dense-data, and
visual-oracle gaps remain open.

The preceding exact-tip gate ran at metadata tip `df95b3c5` before the primary Study Lab event-lineage
fix and is retained below as historical evidence.

The latest product commit is `0712951` (`feat(tc2000): expose complete benchmark history readiness`).
Market Map's provider-neutral benchmark-family readiness panel now renders every D1/W1/MN
member-bar timeframe returned by the canonical API for each role, including analysis-ready versus
covered members, observed bar totals, and the declared analysis floor. A missing weekly or monthly
leg is visible as incomplete rather than inferred from daily coverage. Focused Market Map coverage
passed `36/36`; full frontend Vitest passed `946/946` across `109` files`; TypeScript type-check,
production build, and diff checks passed. Authenticated F8s passed `1/1` on a rebuilt
branch-scoped Docker stack with clean teardown and resource accounting. This product commit is
committed locally on the feature branch.

The preceding product commit is `2ee80c3` (`fix(tc2000): preserve single-output series promotion contract`).
The primary Study Lab's single-output numeric-series promotion now derives the explicit output
name from the returned series artifact, so the persisted scalar watchlist column satisfies the
backend's declared-output contract for both structured timestamp/value payloads and raw numeric
series arrays. The `latest_series_to_scalar` adapter, selected output, and immutable Study/run
lineage remain explicit; validation still rejects incompatible shapes and does not add a
latest-only fallback. Focused Study Lab coverage passed `25/25`; the full frontend suite passed
`946/946` across `109` files; TypeScript type-check, production build, and diff checks passed.
The authenticated F9i direct Study Lab flow passed `1/1` on a rebuilt branch-scoped Docker stack;
teardown and resource accounting reported zero containers, volumes, known image bytes, and
test-container sessions. This product fix is committed locally on the feature branch.

The preceding product commit is `a12c428c` (`feat(tc2000): promote Study range centers`).
The primary Study Lab now aligns with the persisted-result capability matrix for structured
`range` artifacts: a named range with aligned finite center values offers `Save center plot` and
persists a chart-compatible `series` asset through the explicit `range_center_to_series` adapter.
The immutable source/run lineage is preserved and lower/upper bounds remain source-only; invalid
centers and unsupported shapes stay view/export-only. Focused Study Lab coverage passed `24/24`;
the full frontend suite passed `945/945` across `109` files; TypeScript type-check, production
build, and diff checks passed. The product commit is pushed to the feature branch. The preceding
direct Study Lab latest-series-column slice is `ec17b0fb`; its updated F9i browser assertion and
the branch-scoped exhaustive gate remain pending at the new tip. The existing exhaustive receipt
still has the unchanged `98/104` visual blocker.

The preceding product commit is `ec17b0fb` (`feat(tc2000): expose latest Study series column`).
The primary Study Lab now offers the same safe latest-value target already available from Study
Results: a completed numeric `series` with at least one finite observation can be saved as a typed
watchlist column through the explicit `latest_series_to_scalar` adapter. The selected output name
and immutable Study/run lineage are preserved, while the chart-plot action and unsupported-shape
boundaries remain unchanged. Focused Study Lab coverage passed `24/24`; the full frontend suite
passed `945/945` across `109` files at this product boundary; TypeScript type-check, production
build, and diff checks passed. The authenticated F9i flow now exercises both direct Study Lab
promotions; the product commit is pushed to the feature branch. The next coherent validation batch
should rerun the branch-scoped browser/gate receipts at this tip; the existing exhaustive receipt
still has the unchanged `98/104` visual blocker.

The preceding product commit is `37af72fa` (`feat(tc2000): expose canonical readiness evidence`).
Market Map now surfaces the existing provider-neutral benchmark role evidence alongside each
family source: member/weighted/classified counts and statuses, point-in-time support, entitlement
provider and live-probe state, latest disclosed composition/as-of/known-at dates with resolved-row
counts, and observed continuity gaps. This is a truthful readiness display only; interactive reads
remain local-contract reads with no provider fan-out or neighboring-role substitution. Focused
Market Map coverage passed `36/36`; full frontend Vitest passed `945/945` across `109` files;
TypeScript type-check, production build, and diff checks passed. The commit is pushed to the feature
branch.

The preceding product commit is `a6301f0f` (`feat(tc2000): promote latest study series values`).
Persisted Research Results now offers a latest-value watchlist-column target for numeric `series`
artifacts when a finite observation exists. The frontend sends an explicit
`latest_series_to_scalar` adapter with the selected output name and complete Study run lineage;
the API accepts that adapter only when source validation observes a series contract, and the
isolated runner projects the latest finite observation into the typed scalar column. Series plots
remain available, unsupported shapes are unchanged, and no lossy promotion or provider fallback is
introduced. Focused Results/capability coverage passed `32/32`; the targeted backend runner/API
slice passed `135/135` with two existing NumPy warnings; full frontend Vitest passed `945/945`
across `109` files; type-check, production build, and diff checks passed. Authenticated
`F8t-results` browser coverage passed `1/1` against the rebuilt branch-scoped Docker stack,
including the latest-column action, with clean teardown and complete resource accounting.

The exact-tip exhaustive gate then reran at metadata tip `c8dee130` (product tip `a6301f0f`). All
non-visual stages and authenticated functional Playwright passed: backend units `1,315/1,315`,
integration `382/382` with the existing `54` warnings, combined coverage `80.90%`, frontend
Vitest `945/945` across `109` files, and functional E2E `155` passed with `106` documented skips
across `261` specs. The unchanged four-project visual matrix remains the only blocker at `98/104`,
with `watchlist-column-editor-open` diffs of `13,844` pixels at 1080p-100/125 and
`workspace-floating` diffs of `9,770`/`12,097`/`9,770`/`12,097` pixels at 1080p-100/125 and
1440p-100/125. No visual baseline, mask, threshold, skip, fallback, provider rule, or acceptance
policy changed; teardown and resource accounting were clean.

The preceding product commit is `4026d8d3` (`fix(tc2000): show benchmark route readiness`).
Market Map now surfaces the existing provider-neutral canonical readiness contract for each
benchmark-family source: all four independently mapped roles, dated-holdings coverage, route and
member-history state, selected-timeframe analysis-ready counts, and explicit pending/unavailable
reasons. The frontend makes no interactive provider calls and never substitutes a neighboring
proxy. Focused Market Map, Research Results, and capability coverage passed `67/67`; full frontend
Vitest passed `944/944` across `109` files; type-check, production build, and diff checks passed.
Authenticated `F8s-family-map-drilldown` browser coverage passed `1/1` against the seeded
branch-scoped Docker stack, with clean teardown and complete resource accounting. Product commit
`19896f1e` adds the browser regression.
The follow-up `4026d8d3` refinement renders each role's route/provider and holdings-refresh state
explicitly, with the focused Market Map suite still green (`36/36`).

The preceding range-center product commit is `397c554a` (`feat(tc2000): promote structured range centers`).
Persisted Research Results now exposes named `Save filter: <artifact>` and `Promote alert:
<artifact>` actions for events artifacts, `Save column: <artifact>` and `Save chart plot:
<artifact>` actions for scalar and numeric-series artifacts, the complete Boolean matrix
(`Save column`, `Save filter`, `Promote scan`, `Use Gauge`, `Promote alert`), and an explicit
`Save center chart plot: <artifact>` action for structured range artifacts in completed multi-output
Study runs. The range adapter projects aligned finite center values only; lower/upper bounds stay
in the immutable source and unsupported shapes are not coerced. The focused Research Results
component suite passed `27/27`, the full frontend suite passed `939/939` across `108` files,
TypeScript type-check and production build passed, and the authenticated `F8t-results` browser
flow passed `1/1` against the rebuilt branch-scoped Docker stack with clean teardown and resource
accounting. The exact-tip exhaustive gate has now rerun at product tip `397c554a`: all non-visual
and functional stages passed, while the unchanged visual matrix remains `98/104` with the same
six diffs recorded below.

The preceding capability-matrix product commit is `95b12a0f` (`feat(tc2000): expose study artifact capability matrix`).
Persisted Research Results now makes the compatible promotion matrix explicit: scalar, Boolean,
numeric-series, range-center, and structured-event artifacts state their safe workstation targets;
table, categorical bar, histogram, scatter, heatmap, dashboard, and historical-breadth shapes are
marked view/export-only. Range-center promotion is offered only when the artifact contains an
aligned finite center series, while lower/upper bounds remain source-only. Focused capability and
Research Results coverage passed `31/31`; full frontend Vitest passed `943/943` across `109` files;
type-check, production build, and diff checks passed. Authenticated `F8t-results` browser coverage
passed `1/1` against the seeded branch-scoped Docker stack, with clean teardown and complete
resource accounting. This slice does not alter the backend contract,
visual policy, provider fallback rules, or the unchanged exact-tip visual result (`98/104`).

The prior exact-tip gate at product tip `6f575a34` passed all non-visual stages and the functional
browser suite (`155` passed, `106` documented skips across `261` specs). A first invocation's single
F8t-results-open lookup failure was not reproducible in an isolated `3/3` rerun and did not recur
in the complete gate.

The unchanged visual matrix remains the only failing stage: `98/104` passed and six screenshot
diffs remain—`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844` differing pixels
each), and `workspace-floating` at visual-1080p-100 (`9,770`), visual-1080p-125 (`5,512`),
visual-1440p-100 (`12,097`), and visual-1440p-125 (`12,097`). No visual oracle, provider fallback,
or acceptance policy changed. The branch remains active while the visual review blocker and the
remaining canonical provider/history, richer promotion, native-window, accessibility/security,
and dense-data gaps are addressed.

The latest exhaustive gate ran at product commit `7c930fd1` (`fix(tc2000): scope event adapter by
instrument`). Event rows carrying a symbol or canonical instrument ID can no longer match a
different candidate. The focused event suite passed `8/8`, the full runner unit suite `107/107`,
event-promotion integration passed `2/2`, and compileall/Ruff/diff checks passed. The exhaustive
gate passed locked dependencies/migrations, Ruff/format, TypeScript, backend units `1,310/1,310`,
integration `381/381` with the existing `54` warnings, combined coverage `80.90%`, frontend
Vitest `934/934` across `108` files, production build, compose/provider policy, stack health,
runner isolation, and authenticated functional Playwright `155` passes with `106` documented
skips across `261` specs. The unchanged visual matrix is the only gate failure: `98/104` passed
and six screenshot diffs remain—`watchlist-column-editor-open` at visual-1080p-100/125 (`13,844`
differing pixels each), and `workspace-floating` at visual-1080p-100 (`9,770`), visual-1080p-125
(`12,097`), visual-1440p-100 (`9,770`), and visual-1440p-125 (`12,097`). Docker stack teardown
and resource accounting were clean; no visual oracle, provider fallback, or acceptance policy
was changed.

The exact-tip exhaustive gate was then rerun at product commit `1918ca81` (`feat(tc2000): promote
structured study events`). Backend units passed `1,311/1,311`, integration `382/382` with the
existing `54` warnings, combined coverage remained `80.90%`, frontend Vitest passed `934/934`,
and all static/build/compose/provider/runner and functional Playwright stages passed (`155` with
`106` documented skips across `261`). The unchanged visual matrix remains the only failure:
`98/104` passed and six screenshot diffs remain—`watchlist-column-editor-open` at
visual-1080p-100/125 (`13,844` each), and `workspace-floating` at visual-1080p-100 (`12,097`),
visual-1080p-125 (`11,901`), visual-1440p-100 (`12,097`), and visual-1440p-125 (`5,512`).
Docker teardown and resource accounting were clean; no visual oracle, provider fallback, or
acceptance policy was changed.

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

## TC branch scope and ownership boundary

This is a frontend-led TC2000 workstation rework. Its product end state remains
the V25-inspired workflow above, but ownership is divided across the active
parallel branches: `feat/market-data-provider-platform` owns generic market-data
identity, listings, provider routing/capability, coverage and refresh; and
`feat/etf-holdings-constituents` owns ETF holdings adapters, acquisition,
constituent resolution, refresh and audit. TC consumes both through staging and
may build only the consumer/read-side composition needed by the workstation.

TC continues to own its existing Python/DSL/Study/Strategy engine and its
frontend workflows. Earlier provider-population and ETF-adapter work in this
roadmap remains historical branch context and is retained in the workstream
ledger; it is not authorization to duplicate those responsibilities going
forward. Path intersections require line-level review after upstream branches
reach staging. See the TC workstream's
`ops/workstreams/feat-tc2000-frontend-rework/ownership-reconciliation.md` for
the measured overlap inventory, contracts, and promotion order.

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
| Visual regression | Exact-tip four-project run at `7c930fd1` passed 98/104; six board-state diffs remain: `watchlist-column-editor-open` at both 1080p projects (`13,844` pixels each) and `workspace-floating` at all four projects (`9,770`, `12,097`, `9,770`, `12,097` by viewport) | Board-guided product baseline, not exact V25 approval; canonical late-popout hydration now makes the floating state data-bearing; do not weaken or silently rewrite the visual policy |
| Frontend static/unit checks | Exact-tip gate passed 934/934 Vitest across 108 files, plus type-check and build | Fresh receipt at `7c930fd1`; existing large-chunk build warning remains |
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

## Current dependency-ordered workstreams — 2026-09-15 replan

These are the active branch tasks and supersede the historical decomposition
below. Provider and ETF data readiness are explicit product dependencies, but
their implementation remains owned by their parallel branches.

### R0 — Lock scope, dependencies, and historical evidence

- Keep the TC plan, measured overlap ledger, scope guard, roadmap and exact
  `e93de4af` gate receipt aligned.
- Record the Dreyfus N-PORT classification finding for ETF-owner handoff, then
  remove the uncommitted parser experiment from TC.
- Continue frontend-led TC implementation and the existing TC Study/Strategy
  engine without duplicating upstream responsibilities.

Exit: workstream validation and scope guard pass; dependencies, exclusions and
known overlaps are durable and reviewable.

### R1 — Advance independent workstation UI and interaction work

- Close mapped V25 reference-state gaps in shell, tools, charts, linking,
  keyboard interaction, layout persistence and pop-outs.
- Continue TC-owned Study/Strategy UI and compatible artifact promotion.
- Preserve seeded-flow labels, reference-authority distinctions and every
  unchanged screenshot oracle.

Exit: focused and authenticated browser coverage protects each changed flow;
visual oracles are not weakened.

Current focused receipt at product/test tip `74b049c6` (2026-09-15): Chart
Templates and Chart Plot Library now open at their last enabled visible control
on Arrow-Up, while click and Arrow-Down retain first-control entry. Focused
component tests passed `43/43`; the full frontend Vitest suite, type-check, and
production build passed (the existing large-chunk warning remains). The
authenticated headless F9c/F9e browser flows passed `2/2` against the isolated
branch stack, including Escape focus recovery. Teardown/resource accounting
found no retained containers, volumes, or test sessions. This is a focused R1
receipt, not a fresh exact-tip gate; the latest exact gate remains `e93de4af`,
with `98/104` visual assertions and the same six protected diffs. No screenshot
baseline, mask, threshold, skip, or acceptance policy changed.

Latest R1/R6 accessibility receipt at product/test tip
`27698c9608f89d480f609df2d716e75eaa34a292`: Study Lab event occurrences are
semantic list items containing named native buttons; Enter and Space both
activate the linked event without triggering symbol traversal. Authenticated
F8o passed 1/1, full frontend Vitest passed 1,074/1,074, component coverage
31/31, `vue-tsc` and the Docker production build passed. Scope validation and
the 6/6 scope self-tests passed. No visual oracle changed. This does not resolve
the six protected screenshot diffs or refresh the exact-tip integration gate.

Latest persisted Research Results receipt at product/test tip
`03bd5b103d84fcd8e03b0ce74ec944abfa711a88`: event and historical-breadth
occurrences preserve list/listitem semantics and expose named native buttons.
Headless F8t passed 1/1, including Enter/Space linked symbol and timestamp
navigation; full frontend Vitest passed 1,074/1,074, component coverage 39/39,
type-check/build and scope validation passed, and the branch stack was removed
with zero retained resources. No visual oracle changed. This does not resolve
the six protected screenshot diffs or refresh the exact-tip integration gate.

### R2 — Consume the market-data provider platform

- After `feat/market-data-provider-platform` reaches staging, synchronize TC
  using the repository workflow and consume identity/listing, OHLCV coverage,
  capability, entitlement, health and evaluator-preflight evidence.
- Preserve preflight states `full`, `partial`, `deferred`, `stale-blocked`,
  `provider-unavailable` and `empty`, with source, freshness and reasons.
- Compose TC readiness only from explicit upstream evidence and TC analytic
  requirements; do not add provider routing, probes, credentials, retries,
  ingestion or refresh workers.

Exit: every consumed status has consumer contract tests and workstation reads
do not initiate provider work.

### R3 — Consume ETF holdings/constituent capability

- After ETF holdings synchronizes with the provider branch and reaches staging,
  consume its capability, provenance and audit contracts.
- Preserve availability, `usable_for_current_analysis`, `displayable_last_known`,
  source tier, identity, provider, dates, completeness and failure details.
- Permit last-known display only with an explicit label; never use it as current
  analysis input. Reconcile adapter/parser overlaps with the ETF owner.

Exit: current, degraded, stale, unavailable, not-applicable, unknown and partial
states have consumer coverage without TC-owned adapter/probe/refresh behavior.

### R4 — Complete TC workflows and read-side analytics

- Retain benchmark → style → sector → optional industry/proxy → constituent
  navigation, linked symbol/timeframe, ratios, indicators, drawings, source
  lock/edit and save/restore behavior.
- Advance Market Map, breadth, rotation, ranking and historical consumers only
  over persisted inputs; preserve denominators, exclusions, provenance and
  effective/known time.
- Surface unsupported and incomplete inputs rather than adding acquisition or
  backfill logic.

Exit: deterministic and authenticated consumer evidence agrees with upstream
status and available persisted data; gaps remain explicit.

### R5 — Preserve TC Python/Study/Strategy capabilities

- Preserve the single Python-native model, immutable definitions and code/run/
  dataset/output lineage.
- Complete shape-compatible promotions across columns, filters, scans, gauges,
  alerts, chart plots and Strategy signals; return explicit errors otherwise.

Exit: compatibility-matrix cells have unit/API/persistence/consumer evidence.

Current focused receipt at product tip `3c14a03f` (2026-09-15): Market Map
lists every compatible immutable Boolean or numeric-series CodeVersion from
active Python conditions, identifies its output name/contract/version, and
submits the exact selected version rather than accepting a free-form output
name. Completed-map responses now retain run/version/output lineage; named
snapshots preserve that lineage and restore the selected version. Boolean
outputs remain ineligible for numeric tile area. The Market Map component
tests passed `52/52`, full frontend Vitest passed `1,078/1,078`, type-check and
production build passed (the existing large-chunk warning remains), the full
watchlist/Market Map integration file passed `53/53`, and authenticated
headless F8s-market-map-python-output passed `1/1`. Ruff, format, scope guard
(`40` changed paths), and its six self-tests passed. The isolated Compose stack
and four task-built images were removed; resource accounting found zero
containers, volumes, test sessions, known bytes, or unknown components. This
is focused R5 evidence, not a fresh exact-tip gate: the six protected visual
diffs and upstream provider/ETF staging boundary remain open. No output can
cause Market Map to acquire data, and no visual oracle or acceptance policy
changed.

Updated focused receipt at product tip `61c4ae34a` (2026-09-16): historical
Python breadth now has a dedicated Strategy-signal fan-out. Research Results
creates a separate immutable `signal` asset and Strategy definition atomically,
rather than reusing the EasyScan `condition` asset. The promotion retains the
source run/member IDs, dataset-manifest fingerprint/summary, source output
name, threshold adapter, recursive member tree, and point-in-time lineage;
cross-sectional trees remain aggregate-only. Strategy queue normalization reads
both canonical and legacy promotion diagnostics and carries adapter, target,
tree, and output identity into the isolated runner. Research Results passed
`48/48`, full frontend Vitest `1,102/1,102`, type-check/build, Strategy Lab API
`29/29`, breadth workspace integration `2/2` across Boolean/numeric/tree paths,
and Strategy queue unit coverage `16/16`; Ruff, formatting, and diff checks
passed. The exact full-stack/browser gate receipt for this product tip follows
below. No provider-platform, ETF, visual-baseline, threshold, mask, skip,
V25-media, or acceptance-policy behavior changed.

Exact full-stack/browser receipt at the same R5 product tip (2026-09-16): the
first run stopped only on a transient F8k popup-recovery assertion after 169
functional passes and 107 documented skips; a fresh-stack retry passed F8k
`1/1`, and the exact rerun passed backend unit/integration `1,619`, frontend
Vitest `1,102/1,102`, authenticated Chromium `170` with `107` documented
skips, and all four visual projects `104/104`. Docker teardown and exact
TC2000-builder cleanup were branch-scoped and clean. No provider-platform,
ETF, visual-oracle, baseline, threshold, mask, skip, V25-media, or
acceptance-policy behavior changed.

### R6 — Close visual, resilience, accessibility and performance evidence

- Validate missing/partial/stale/error/loading, dense treemap, Study, tools,
  keyboard, pop-outs, layout restoration and native/browser-window limitations.
- Keep endurance, accessibility, security/sandbox, dense-data and performance
  budgets explicit and repeatable.
- Preserve the unchanged 104-case four-project matrix and protected diffs.

Exit: each state has an honest manifest disposition and no visual or functional
acceptance oracle is weakened.

### R7 — Reconcile staging and hand off at review

- Promote provider-platform to staging, then ETF holdings to staging through
  their coordinator workflow; TC does not directly merge either branch.
- Synchronize TC from resulting staging and assign a line-level semantic
  disposition to every measured overlap, transferring ETF-owned behavior via
  its owner when needed.
- Run focused/full suites, authenticated flows, all visual projects and the
  exact-tip integration gate; update TC-only durable records.

Exit: clean, synchronized TC records, current exact-tip evidence and
`ready_for_human_review`; no deployment or direct branch integration.

## Historical workstreams from prior scope — preserved, superseded

The following decomposition records the prior TC branch plan and remains useful
as history. Its provider-population, provider-operations and ETF-adapter tasks
are no longer forward ownership for TC; use the current replan above.

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

- the canonical live-data version of the top-down workflow passes for all supported roots/roles,
  using identity/listing/OHLCV and ETF evidence supplied by the owning upstream branches;
- unsupported or unentitled roots/roles are explicit and evidence-backed, not silently replaced;
- historical universe, weights, classifications, bars, and analytical results respect effective
  and known-time boundaries;
- arbitrary source-polymorphic Market Map and breadth workflows preserve immutable source lineage;
- Python/visual definitions and all compatible promotions are reproducible and round-trip safely;
- persisted, linked, cross-window, keyboard, drawing, and dense-workstation behavior survives the
  declared endurance matrix;
- every required visual state has an honest manifest disposition and all applicable visual gates
  pass unchanged;
- full automated, upstream live-provider/ETF, security, migration, performance, and exhaustive
  integration evidence is current at the exact feature tip;
- no hidden fixture, paid-provider assumption, acceptance waiver, or stale historical claim is
  presented as product completion.

## Immediate next checkpoint

Continue with the next bounded TC-owned workstation, Study, or Strategy gap
after checking the candidate against this branch's ownership boundary and the
upstream workstreams. Add focused regression evidence and run the relevant
frontend/browser checks. Keep the unchanged visual references and 0.5%
threshold intact; the ten screenshot-only differences at `a78812d` remain
open for the review specified in this document. Do not add provider routing,
ETF adapters, live probes, generic ingestion, or refresh workers to TC.

Provider and ETF consumer integration and semantic shared-path reconciliation
remain deferred until their work reaches staging. Do not consume their branch
tips directly or mutate another worktree. After both dependencies reach
staging, use the prescribed coordinator workflow, reconcile every shared path,
and rerun the exact-tip full gate before recording `ready_for_human_review`.

## 2026-09-08 — Chart Plot Library Strategy-signal adapter

The Chart Plot Library now exposes an explicit `Strategy signal` target for compatible
single-output indicators. Promotion requires a canonical active instrument, emits an immutable
chart-plot lineage record (instrument, timeframe, indicator, output, operator, threshold, and
current-data re-evaluation semantics), and creates the user-scoped Strategy Lab signal through
the existing code-version endpoint. Multi-output indicators refuse promotion with an explicit
capability error rather than silently choosing one series. The backend preserves chart-origin
metadata and tags without changing the existing Study Lab contract.

Focused component coverage passed `25/25`; type-check passed. At exact product tip `b53873c1`,
the exhaustive integration gate passed all non-visual stages: backend `1,350` unit and `385`
integration tests, combined coverage, frontend Vitest `974/974`, build/compose/provider policy,
stack health, runner isolation, and authenticated Playwright `164` passed with `106` documented
skips across `270` specs. The unchanged 104-case visual matrix was `98` passed with exactly the
six previously recorded state-oracle diffs (watchlist-column-editor-open at both 1080p scales;
workspace-floating at all four projects). No visual baseline, mask, threshold, skip, provider,
fallback, or acceptance policy changed; Docker stack teardown and resource audit were clean.

R4 still has compatible fan-out gaps for some artifact shapes and R1-R3/R5-R6 remain open,
especially complete provider-backed family population/history, exact visual evidence, native
window/accessibility/security proof, and dense-data budgets.

## 2026-09-08 — Authenticated browser proof for chart Strategy-signal promotion

Test commit `4361fa5c` adds the consuming-UI F8u-signal Playwright flow. It hydrates a canonical
SPY instrument, adds RSI to the real chart, selects the Chart Plot Library Strategy-signal target,
submits a `>= 70` threshold, and verifies both code-asset and Strategy Lab signal responses plus
the visible created-signal status. The bounded instrument-attach wait covers the real hydration
race without weakening the product's fail-closed canonical-instrument guard. Focused live coverage
passed `1/1` against the seeded branch-scoped Docker stack with clean diagnostics and teardown.

The exact-tip gate at `4361fa5c` passed all non-visual stages: backend `1,350` unit and `385`
integration tests, frontend `974/974`, production build, compose/provider policy, healthy stack,
runner-isolation/resource probes, and authenticated functional Playwright `165` passed with `106`
documented skips across `271`. The unchanged visual matrix completed `104` cases with `98` passes
and exactly the six known state-oracle diffs (watchlist-column-editor-open at visual-1080p-100/125;
workspace-floating at visual-1080p-100/125 and visual-1440p-100/125). No baseline, mask, threshold,
skip, fallback, provider, or acceptance policy changed; cleanup left no assigned resources. Continue
the remaining R4 fan-out and R1-R7 roadmap gaps.

## 2026-09-08 — Refresh Nasdaq provider-route probes

The opt-in live provider checks were rerun with network access for the canonical Nasdaq-100
legs: QQQ SEC historical reconstruction, QQQE current Direxion holdings CSV, and QQQE SEC
historical reconstruction. All three probes passed (`3/3`, `413` unrelated cases deselected),
including route/provider/date assertions and parseable holdings rows. This is current route
evidence only; it does not persist snapshots, resolve the remaining member placeholders, or prove
D1/W1/MN analysis floors. R1 therefore remains open for durable population, continuity, and
member-bar history.

## 2026-09-08 — Extend workstation pop-out endurance evidence

The R6 workstation performance guard was rerun against a fresh branch-scoped stack with
`TC2000_POP_OUT_CHURN_ROUNDS=250`. Both Chromium specs passed (`2/2` in 3.8 minutes): initial
multi-window recovery stayed within the existing canvas/tool and elapsed-time bounds, and the
extended churn completed without source-workspace growth or convergence failures. Teardown and
resource accounting were clean (`0` containers, volumes, sessions, and known bytes). This
strengthens browser-simulation evidence only; native multi-monitor, dense-data, accessibility,
security, and other R6 requirements remain open.

## 2026-09-09 — Exact Nasdaq snapshot-member history rerun

The exact dated `nasdaq100` refresh was rerun on a fresh seeded stack and every queued canonical
member job was awaited to completion. SEC-backed QQQ/QQQE snapshots selected seven canonical
QQQE members and excluded `197` unresolved/placeholders; value/growth remained explicitly
unavailable. BIIB, CDW, LULU, and ON each persisted `2,344` adjusted D1 bars through
`2025-12-31`; SOLS persisted `51`, TTD `2,333`, and GFS `1,048`. Each job retained the
expected MN/W1 no-data outcomes. Although the member rows had no explicit provider-symbol
relationship, the governed canonical-symbol fallback succeeded. The earlier empty family result
was not reproduced, so no provider, fallback, credential, or acceptance policy change is
justified. Family-wide readiness remains open pending auditable placeholder enrichment, MN/W1
coverage, rebalance continuity, and broader family/root coverage.

## 2026-09-09 — Reject foreign identifier listings during Nasdaq enrichment

The ETF constituent resolver now applies a conservative US-listing compatibility
check when a US ISIN resolves through an identifier provider. Foreign OpenFIGI
listings are rejected before promotion, while the existing bounded
provider-backed name bridge remains available after stable-identifier candidates
are exhausted.
This preserves the existing provider/search order and acceptance thresholds while
preventing non-US listings from becoming canonical US holdings. Focused resolver
coverage passed `26/26` tests and Ruff passed on the changed files.

On the rebuilt seeded stack, the dated QQQ/QQQE maintenance path promoted the
representative AZN, TEAM, and HON rows, then queued `54` canonical members for
history. All `54` D1 jobs completed; `53` met the 252-bar floor (range `51–2344`),
with no W1/MN bars. The exact two snapshots now contain `55` distinct canonical
symbols and `115` placeholder rows; this is bounded identity/history evidence,
not complete family readiness. Auditable enrichment, W1/MN coverage, rebalance
continuity, and R2–R7 requirements remain open.

The required exact-tip integration gate then passed all non-visual stages:
backend `1,357` unit and `386` integration tests (combined coverage `67%`),
frontend type-check/build, compose/provider/runner checks, and functional
Playwright `165/272` with `107` documented skips. Visual parity remained
`98/104` with the same six state-oracle diffs; teardown and resource cleanup
were clean.

The resolver follow-up retained the stable-identifier duplicate-collapse path:
the name bridge is enabled for a ticker-bearing row only when an identifier
profile was rejected (such as a foreign listing). The corrected implementation
again passed the exact gate with backend `1,357` unit and `386` integration tests,
functional `165/272`, and unchanged visual `98/104` with the same six diffs.

## 2026-09-09 — Bounded Nasdaq canonical enrichment and history audit

The fresh seeded stack reran the dated QQQ/QQQE maintenance path and completed
bounded classification without failures. The exact snapshots contain `101` and
`103` resolved rows, of which `99` and `101` are non-placeholder canonical rows;
their union is `106` canonical instruments. The two placeholder rows in each
snapshot remain explicit and are not treated as usable members. Value and growth
roles remain unavailable because no verified proxy is configured.

All `106` queued canonical-member ARQ jobs returned results. Adjusted D1 history
is present for `100` instruments (`99` meet the `252`-bar floor; the observed
range is `51–2,344` bars), ending at `2025-12-31`; no W1 or MN bars were returned.
The queue reported `4` unresolved member exclusions. This is stronger bounded
history evidence, not family readiness: auditable placeholder enrichment,
W1/MN floors, rebalance continuity across multiple dated snapshots, and the
remaining families/roots are still open. No provider, fallback, credential,
visual, or acceptance policy changed.

## 2026-09-09 — SEC issuer-name normalization and canonical history follow-up

The SEC issuer search bridge now normalizes punctuation and legal-name separators
for bounded title matching (for example, `Insmed, Inc.` against `INSMED Inc`) while
retaining exact ticker matching and the existing profile/listing acceptance gates.
Focused provider coverage passed `2/2`; Ruff and diff checks passed. This is a
search-precision fix only: it does not guess symbols or relax the US-listing guard.

On the rebuilt branch stack, follow-up reconciliation promoted `INSMED` from its
placeholder instrument. The exact SEC snapshots now contain `100` and `101`
non-placeholder canonical rows (`102` canonical instruments in the union); three
rows remain explicit placeholders. The two Electronic Arts rows are now explicitly
dispositioned as historical equities with CUSIP/ISIN identity but no accepted
current US listing; they remain outside canonical counts pending point-in-time
listing lifecycle support. The Dreyfus government-cash row is still unclassified.
The queue selected `107` canonical instruments, queued one new member job, and
reported three unresolved exclusions; the new INSM D1 job returned `2,344` adjusted
bars through `2025-12-31`, with expected MN/W1 no-data outcomes. Aggregate D1
coverage is `102` instruments / `220,106` bars; W1/MN remain unavailable. This is
bounded R1 evidence, not family readiness: cash-row disposition, W1/MN floors,
rebalance continuity, and remaining families/roots remain open. No visual or
acceptance policy changed.

## 2026-09-08 — Family refresh failure telemetry boundary

Family refreshes now defer failure-state writes until after each role's SQLAlchemy savepoint has
rolled back, preserving the provider/parser root exception and preventing a misleading closed-
transaction error. Focused service/bootstrap coverage passed `17/17`; a serial rebuilt-stack run
across all eight configured families produced `18` refreshed roles, `10` explicitly unavailable
roles, and `0` failed roles. This is transaction-boundary evidence only: canonical population,
placeholder disposition, D1/W1/MN floors, rebalance continuity, and R2–R7 acceptance remain open.

## 2026-09-08 — Exact-tip functional and visual gate after browser-context correction

The two functional cases that previously stopped at Chromium startup both pass (`2/2`) under the
permitted host browser context. The complete exact-tip gate at `80977234` passes all non-visual
stages, backend `1,359` unit plus `386` integration tests (`80.98%` combined coverage), frontend
Vitest/build, compose/provider/runner and health probes, and functional Playwright `165/272` with
`107` documented skips. Visual parity remains `98/104`, with exactly the six established
watchlist-column-editor-open and workspace-floating state-oracle diffs. No visual baseline,
threshold, skip, provider, fallback, or acceptance policy changed; canonical family/history
readiness and the remaining R2–R7 evidence remain open.

## 2026-09-08 — Bounded real ARQ canonical-history handoff

The branch-local stack was rebuilt with `BENCHMARK_FAMILY_MEMBER_HISTORY_MAX_INSTRUMENTS_PER_SNAPSHOT=32`
applied to the worker service. A real ARQ `sp400` dated refresh for `2025-12-31` completed with
three refreshed SEC-backed roles (`MDY`, `MDYV`, `MDYG`), one explicitly unavailable equal-weight
role, and zero failed roles. The committed snapshots exposed `401` resolved member rows; the
worker selected exactly `32` canonical members, marked the queue as limited, and enqueued `32`
member-history jobs. After the queue drained, the selected set had adjusted D1 history for `31`
instruments (`68,431` bars, newest `2025-12-31`); W1/MN remained unavailable with zero bars.
The worker's effective cap was verified as `32`, and teardown removed all branch resources.

This is the first bounded real worker handoff receipt for a non-Nasdaq family, not complete R1
readiness: placeholder disposition, full-family population, W1/MN floors, rebalance continuity,
and R2–R7 evidence remain open. The earlier uncapped attempt was interrupted and discarded as
non-qualifying evidence; no provider, fallback, credential, visual, or acceptance policy changed.

## 2026-09-08 — Bounded eight-family ARQ handoff

All eight configured family/date units were then run serially for `2025-12-31` with the worker
cap fixed at `8` canonical members per snapshot. The real ARQ path refreshed `20` mapped roles,
reported `12` roles explicitly unavailable because no verified proxy is configured, and reported
`0` failed roles. Every bounded selection stayed at or below eight members: the run selected `56`
member slots in total, with idempotent reuse for overlapping canonical instruments. After the
handoff, no active ARQ queue key remained; aggregate local coverage across the refreshed snapshots
was `44` instruments / `94,540` adjusted D1 bars through `2025-12-31`. W1/MN remained at zero.

This strengthens bounded family/provider evidence but is not full R1 readiness: the selected
history is intentionally capped, placeholder and rebalance disposition remain incomplete, W1/MN
floors are unavailable, and canonical top-down/R2–R7 evidence remains open. No provider,
fallback, credential, visual, or acceptance policy changed.
