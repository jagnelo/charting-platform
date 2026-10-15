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
behavior but provides no deterministic visual capture. The manifest registers
230 images at `/private/tmp/tc2000-v25-reference-pack`, but that controlled
storage path is absent in this Linux runtime, so its images could not be
inspected here. Consequently the checked-in platform screenshots cannot be
treated as evidence of the intended V25 Help appearance: the tracked default
and Help images already differ in 1,205 pixels in the invariant top-left brand
region, while the pinned Noble capture matches the default image there and the
host capture matches the Help image there.

The unresolved human decision is limited to the visual authority for this
required-missing Help state: provide/mount a permission-cleared, provenance-
verifiable V25 Help capture for review, or review and explicitly accept a
deterministic local-only interim baseline disposition. Until that decision is
made, preserve the current snapshots and `0.5%` oracle; do not claim Help visual
acceptance. This does not block independent TC work, but TCP2 cannot close on
the current evidence. The full roadmap and downstream Provider/ETF staging
dependency remain open.

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
