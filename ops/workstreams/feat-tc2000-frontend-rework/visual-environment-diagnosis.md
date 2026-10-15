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
