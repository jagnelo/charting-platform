# Visual environment diagnosis — 2026-10-15

Checkpoint `tc2000-workstation-integration-1`, source `9d78e1d9b` plus
documentation-only checkpoints. No image, threshold, mask or skip changed.

The host Playwright1.62.1 run passes all four Help profiles (40.0s), but the
wider host run immediately fails unrelated default/menu/column screenshots
with roughly 3% differences dominated by text. It was interrupted after four
recorded screenshot failures and a fifth case starting. This is not a full
matrix receipt. Host fontconfig resolves Arial to Nimbus Sans and Segoe UI to
DejaVu Sans.

The exact pinned image `mcr.microsoft.com/playwright:v1.62.1-noble`
(digest sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e)
was fetched. With source mounted read-only, its two-case probe passes default
workspace but fails Help by 55,032 pixels against the unchanged 0.5% limit.
State/content assertions pass. The Help image also differs in documented
shortcut rows, placement and freshness state; font correction alone does not
establish complete screenshot parity.

An exact RGB comparison using the installed Playwright PNG decoder proves
the tracked Linux default/Help baselines disagree even in the invariant brand
region (x0..169,y0..27), far from the Help overlay:

| Comparison | Different pixels |
| --- | ---: |
| Tracked default vs tracked Help | 1,205 |
| Noble Help capture vs tracked default | 0 |
| Host default capture vs tracked Help | 0 |

Both tracked images are 1920x1080. Opening Help does not change the brand text
or its CSS. Thus at least these baseline regions encode distinct rendering
environments. A product patch that merely switches the global font to satisfy
one baseline would break the other. This finding narrows the historical vague
geometry/oracle blocker; it is not permission to regenerate either baseline.

Canonical full matrix completed93passed/11failed in21.9m, terminal exit1.
It ran in a separate labelled, automatically removed
browser container `tc2000-checkpoint-visual-matrix`, tool process handle 11617.
Artifacts: `/tmp/tc-checkpoint-pinned/full`. Temporary current-source Vite is
handle2397, port15190, using assigned backend28008; Vite is now stopped.
Failures: four Help screenshots, four stale floating-fixture freshness
assertions, default login-navigation timeout, drag-target ERR_NETWORK_CHANGED
diagnostics and Study-running workstation visibility timeout.

Fresh isolated fixture initialized from current source subsequently passes all
16 four-profile replays of floating/default/drag-target/Study-running cases
(2.8m), including unchanged screenshots and browser diagnostics. Artifacts:
/tmp/tc-checkpoint-pinned/fresh-focused-matrix. This proves a safe fixture
initialization path and clears those focused categories, not the earlier full
matrix result. Four Help font-baseline failures remain unresolved. Original
assigned stack and its data are preserved; temporary fixture cleanup is scoped
to tc2000-checkpoint-fresh-9d78e1 only.

Coordinator action: review this reproducible environment discrepancy alongside
the missing V25 reference states and narrow chart-template repair proposal.
Any baseline repair must follow the existing reference/acceptance policy and
receive the appropriate review; no policy waiver is proposed. Combined
Provider/ETF consumer acceptance remains gated on their green staging delivery.

## 2026-10-15 — Fresh-fixture Help replay isolates the remaining mismatch

To separate the stale retained-fixture state from font/content differences, the
existing Help visual assertion was run by itself in all four protected browser
profiles against a newly seeded, isolated fixture. The current `Current ·
canonical` freshness state now matches the expected capture. The unchanged
pixel oracle still fails all four profiles:

| Profile | Differing pixels | Ratio |
| --- | ---: | ---: |
| 1920x1080 at 100% | 55,010 | 2.7% |
| 1920x1080 at 125% | 56,397 | 2.8% |
| 2560x1440 at 100% | 63,934 | 1.7% |
| 2560x1440 at 125% | 65,625 | 1.8% |

The popover still renders the currently implemented shortcut list and clipping
at its existing size. This differs from the checked-in Help screenshots in
content, text wrapping/metrics and other shell pixels. The earlier stale
freshness mismatch is therefore removed, but it was not the cause of the
remaining visual failure. No screenshot, threshold, mask or test assertion was
changed. Artifacts are retained under
`/tmp/tc-checkpoint-pinned/fresh-help/results`.

The reference manifest still marks `application-shell-default/keyboard_help`
as `required_missing`; its official Version 25 hotkeys source confirms
behavior but provides no deterministic visual capture. The controlled media
pack is present in this worktree at
`.ai/runtime/tc2000-v25-reference-pack/` (ignored by Git): its index contains
230 images across 26 source groups. Inspection confirms that it contains no
hotkeys/keyboard-shortcuts source group or in-app keyboard Help dialog capture;
the sole official Version 25 product-page image is a perspective-composited
laptop mockup, not a deterministic workstation capture. The manifest's
`/private/tmp/tc2000-v25-reference-pack` path is stale for this Linux checkout,
but correcting that path would not supply the missing state. Consequently the
checked-in platform screenshots cannot be treated as evidence of the intended
V25 Help appearance: the tracked default and Help images already differ in
1,205 pixels in the invariant top-left brand region, while the pinned Noble
capture matches the default image there and the host capture matches the Help
image there.

The unresolved human decision is limited to the visual authority for this
required-missing Help state: provide/mount a permission-cleared, provenance-
verifiable V25 Help-dialog capture for review, or review and explicitly accept a
deterministic local-only interim baseline disposition. The local media pack is
useful for its represented states but is not a substitute for that uncovered
state. Until a decision is made, preserve the current snapshots and `0.5%`
oracle; do not claim Help visual acceptance. This does not block independent TC
work, but TCP2 cannot close on current evidence. The full roadmap and downstream
Provider/ETF staging dependency remain open.

## 2026-10-15 — Pinned-image font fallback check

A read-only fontconfig comparison adds a concrete environment difference:
the host resolves Arial to Nimbus Sans and Segoe UI to DejaVu Sans. The pinned
Playwright 1.62.1 Noble image resolves Arial to Liberation Sans and Segoe UI
(and its generic sans-serif fallback) to WenQuanYi Zen Hei. A diagnostic run
with the host `/usr/share/fonts` and `/etc/fonts` mounted read-only exposed the
host DejaVu and Nimbus font files to the image, but still did not resolve Arial
to Nimbus Sans; that is not a demonstrated screenshot-normalization route.
No screenshot was captured in this experiment, and no oracle, app CSS, system
font configuration, or assigned data was changed. This supports the mixed
environment diagnosis but does not explain all Help pixel differences: the
current Help rows/content and placement still diverge, and the authoritative
V25 Help capture remains missing.

## 2026-10-15 — Read-only visual review of retained fresh-fixture captures

Inspected the retained 1920x1080 expected/actual PNG pair from the four-profile
fresh-fixture replay. The mismatch is structural as well as typographic: the
Help popover is anchored at a different horizontal position, the workstation's
main vertical pane divisions differ, and the displayed shortcut rows diverge
(the checked-in image shows Shift+L/Shift+F/Shift+N in its visible lower rows,
while the current capture shows Shift+F/Ctrl+M and continues with different
content). This confirms the pixel delta is not explained by the earlier font
fallback difference alone, nor by the now-reset freshness label. These
retained artifacts are diagnostic only; no screenshot, layout fixture, mask,
threshold, or product CSS was changed. Because the tracked image set already
mixes render environments and there is still no authority-grade V25 Help
capture, this comparison cannot determine which layout/content is intended.

## 2026-10-15 — Exact-source hosted CI comparison

On source `de3a6210de7e3b9919b6762715f0962e50d92dee`, the GitHub Actions
stack-backed Playwright job completed successfully. Its run log enumerates all
four `application shell keyboard help state` profiles, and the job concluded
success with no visual failures. In contrast, the retained pinned-Noble
fresh-fixture replay failed those four protected comparisons at 55,010 / 56,397
/ 63,934 / 65,625 pixels. The exact-source hosted pass establishes that the
checked-in local oracle is satisfiable in that hosted browser environment; it
does not establish V25 visual authority, nor explain the geometry/content/font
differences in the retained local capture. Keep the missing V25 reference and
the 0.5% oracle unchanged.

## 2026-10-15 — Human-approved local-only Help reference adopted

The human approved the reviewed fresh-fixture Help captures as a local-only
interim reference. Reviewed all four Linux profiles (1920x1080 at 100% and
125%; 2560x1440 at 100% and 125%). The shortcut text visible in the popover is
legible at each scale. The dialog extends below the viewport, so a static image
does not expose every row; retain the existing keyboard/scroll functional
checks as part of acceptance.

Adopted the exact retained `*-actual.png` files from
`/tmp/tc-checkpoint-pinned/fresh-help/results/` into only the four Linux
`application-shell-help-open` snapshots. The four Darwin snapshots are
unchanged. This local reference is not derived from or asserted to match TC2000
V25 and is not a product-parity claim. The official V25 `keyboard_help` visual
reference remains `required_missing`; obtaining and reconciling authoritative
V25 visual evidence remains unfinished roadmap work.

No test behavior, content assertion, visual mask, snapshot tolerance, or skip
changed: the screenshot assertion still uses `maxDiffPixelRatio: 0.005`. The
existing `F9e-shell-menus-keyboard` flow still requires the Help dialog to take
focus, proves its scroll height exceeds its client height, checks PageDown and
PageUp change and restore `scrollTop`, verifies Tab reaches Close, and verifies
Escape restores focus to the Help trigger. Its source is unchanged. Exact-tip
hosted Playwright evidence is being awaited before this local checkpoint is
reported as verified; the currently running run does not include these local
snapshot bytes. Preserve the captures under the local ignored runtime/artifact
area if this worktree is discarded; the `/tmp` artifacts are not a durable
repository source.

### Focused adoption verification

The required build passed (`vue-tsc` plus Vite, 520 modules). In the isolated
fresh seeded fixture, `F9e-shell-menus-keyboard` passed 1/1, including dialog
focus, PageDown/PageUp scroll movement and reset, Tab-to-Close, and Escape
focus restoration. The first combined invocation omitted the visual suite's
opt-in flag and skipped its four visual cases; it is not counted as visual
evidence. The corrected invocation used `RUN_BOARD_VISUAL_PARITY=1` and
`E2E_SEED_MARKET_DATA=true`; all four adopted Linux Help screenshot profiles
passed in 32.6s with the unchanged content assertions and 0.5% tolerance.

GitHub run `38799367031` completed success for exact full SHA
`87b9e3ab77d5356408b25b73b086a8fc7f062400`: backend, frontend-unit,
branch-declared, and stack-backed E2E jobs passed; Exhaustive Integration Gate
was skipped for this feature branch. The E2E command did not set
`RUN_APPROVED_VISUAL_PARITY` or `RUN_BOARD_VISUAL_PARITY`; the suite's visual
skip guard therefore excluded all 104 visual cases (26 cases across four
profiles). The 104 progress messages at 20:33:54Z were emitted as skips, not
executions. This run did not execute or pass Help screenshots and is not pixel
acceptance evidence. The focused, opted-in local run above is the valid Help
visual evidence.
The disposable six-service fixture, four volumes, and network were removed by
exact project name; post-cleanup inspection confirmed the assigned TC stack's
six services and four volumes remain. Official V25 visual parity remains open.

## 2026-10-15 — Repaired Help layout and reviewed interim captures

The actual Help row layout now uses a 96px key column with a 7px gap. This
resolves the measured `Shift+wheel` text/description collision and gives the
longest labels additional separation. The unchanged four-profile visual test
now also checks every rendered key text range against its description and
asserts that both stay within the Help dialog's horizontal bounds.

In isolated seeded project `tc2000-help-interim-20261016`, the focused keyboard
flow passed 1/1 and all four Linux Help visual profiles passed 4/4 using pinned
Playwright 1.62.1 Chromium. The same screenshot tolerance remains 0.5%. The
four captures were rederived only after the geometry assertions passed and
reviewed at both resolutions and both scale settings; shortcut labels and
descriptions are readable and separate, with remaining rows accessible by
PageDown/PageUp. The assigned service stack/data and listener 15190 were
preserved. Official V25 `keyboard_help` remains `required_missing`; these
human-authorized captures are an interim local-only staging reference, not
official V25 evidence.
