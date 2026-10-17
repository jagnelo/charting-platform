# fix/chart-template-key-generation

Created from `staging` at `79c8623fb122ccdd7c86e4b45e03b7e2c6708e7b`.

## Human authorization

- Recorded at: 2026-10-17T06:12:20.371918+00:00
- Request: Human-authorized narrow browser repair: replace unsupported crypto.randomUUID calls in chart-template and column-set key generation with crypto.getRandomValues, preserving the eight-hex key suffix and adding regressions. This unblocks Provider validation; do not bring in the full TC2000 feature or alter its roadmap.
- Closure authorization: the human delegated careful technical-fix review and closure without individual acceptance for every small fix. This applies only to this narrow compatibility repair; exact-source CI and the guarded staging gate remain mandatory. It does not authorize feature-checkpoint acceptance, provider/quota activity, paid/trial operations, deployment, promotion, or data cleanup.
- Planning state: ready; the existing coordinator goal owns this implementation, so no separate feature-session prompt is needed.

## 2026-10-17 — browser crypto compatibility repair

The specific browser defect was that this test origin exposes `crypto.getRandomValues()` but not `crypto.randomUUID()`. Both chart-template and saved-column-set key generation called `randomUUID()` before their save request, so the UI could error before issuing the PUT. The two key generators now use a random 32-bit word rendered as the same eight-character lowercase hexadecimal suffix; normalized prefixes and saved payloads are unchanged.

Added regressions that stub a browser crypto object with `getRandomValues` and no `randomUUID`, then verify each save request and absence of a visible save error. The two affected Vitest suites pass 78/78; `vue-tsc --noEmit`, workstream validation, and `git diff --check` pass. The exact source hunks match the two changes in the TC candidate used for the coordinator's unchanged five-flow browser rerun: F9c, transform restore, comparison restore, F9e, and F9f passed 5/5. That receipt is [tc2000-five-flow-rerun-20261017T0554Z.md](/home/m920q/charting-platform/.ai/staging-attempts/tc2000-five-flow-rerun-20261017T0554Z.md); it is focused compatibility evidence, not full TC checkpoint acceptance.

No Provider/issuer calls, quotas, assigned feature services, screenshots, visual oracles, tolerance, or TC worktree files were changed. Remaining gates are a clean committed/pushed repair tip, exact-source required CI, then guarded integration and a green Exhaustive Integration Gate on the exact staging SHA. No human action is currently needed; the full TC feature checkpoint and all its roadmap gates remain open.

The first exact-source CI run (`39009427308`, commit `8c39c8c`) exposed a workstream-command formatting error: CI executes `branch_tests` as shell, and the prose descriptor was interpreted as a command (`frontend:: not found`). Backend and frontend jobs were still running at the initial audit. This is a coordinator-authored validation-record error, not a product test failure; the plan now contains the actual runnable npm command, and the repository's own branch-tests runner has passed locally (78 tests plus `vue-tsc`). A fresh exact-source run is still required; the failed run remains recorded rather than erased.

Update this handoff at each coherent boundary.
