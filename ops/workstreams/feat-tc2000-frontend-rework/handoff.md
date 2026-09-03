# feat/tc2000-frontend-rework

Created from `staging` at `89bb5c05ad1635156285d392b7c39b3c341ad8f1`.

## Human authorization

- Recorded at: 2026-08-30T18:48:28.951896+00:00
- Request: Continue the existing TC2000 workstation V25 parity, provider population, and history gaps from current green staging.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.

Update this handoff at each coherent boundary.

## 2026-09-03 — Prior session and media reconciled

The prior Codex rollout `019fa949-e419-77c1-8d7d-188b5235029c` was streamed and reconciled rather
than imported wholesale. It contains 78 canonical user turns. Replayed compactions account for the
hundreds of `input_image` occurrences; the user intent contains four distinct shared visual
subjects: one breadth-over-price example and three Finviz-style hierarchical maps. The separately
fetched public TC2000 reference corpus was reconstructed as 230 hash-indexed images across 26 source
groups, its board was rebuilt, and its manifest/policy checks passed. The reconstructed copy lives
under `/private/tmp` and is deliberately not treated as a durable or exact-build authority.

The concise reconciled roadmap is now `docs/tc2000-roadmap.md`. It preserves the user's one-stint
delivery intent, the eight benchmark-family roots, canonical free-source-first data rules,
source-polymorphic Market Map and breadth contracts, single Python-native authoring model, visual
authority boundaries, promotion goals, and explicit exclusions.

No product source, branch ancestry, integration, deployment, or visual baseline was changed during
this reconciliation. At inspection time the clean branch head was `4668e342`, with two branch-only
workstream commits and 14 commits on local `staging` not yet in the branch. The first execution
checkpoint is therefore R0: synchronize through the repository workflow, rerun the current
baseline, and specifically reproduce the ambiguous late-session Golden Layout activation concern.
The later durable 2026-08-19 evidence already supersedes the older Market Map → Breadth/Study
failure: that flow was repaired and passed `1/1`, so it is not listed as an open defect.

## 2026-08-30 — Staging-based continuation

The former master-based branch was fully represented in green staging before its remote ref was
removed. Its prior implementation history remains reachable through master; this worktree is a
new branch with the same name created from staging. The inherited TC2000 records still identify
exact V25 visuals, canonical provider population/history, entitlement evidence, and final-audit
gaps. Continue those documented gaps without treating the prior branch's closed context as overall
feature completion.

## 2026-09-03 — R0 synchronized implementation baseline

Implementation session `e225ac6d-5c97-4805-bb18-9bb433431092` is active in the assigned
worktree. The previously authorized roadmap commit `49fae6314bd29d4c1fbc69058ee425b681a169d9`
was pushed to `origin/feat/tc2000-frontend-rework`, then current green staging
`8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35` was merged with `--no-ff` as
`da78591c0f75626d584e0bc691cd939f80addc27` and pushed. No other worktree was changed.

The workstream is now schema 4, `planning_state: ready`, and uses the required
`full_stack_browser` local validation profile. The session-local goal is active and unbudgeted.

R0 baseline receipts from the synchronized tip:

- Backend focused canonical taxonomy/coverage/history/Market Map/breadth/bootstrap suite: 66 passed.
- Frontend type-check: passed after installing the lockfile dependencies locally.
- Frontend unit coverage: 108 files and 923 tests passed (81.99% statements, 72.26% branches).
- Frontend production build: passed; Vite emitted only the existing large-chunk warning.
- Workflow helpers: 42 passed; uPlot contract audited 48 primary sources; visual policy and manifest valid.
- Isolated Docker stack: built and all six services became healthy under the branch-scoped project.
- Corrected Chromium flow baseline against `STACK_URL=http://127.0.0.1:28083`: 137 passed, 11 failed.
  The failures are concentrated in chart transform/uPlot surfaces and Study Lab history/result
  rendering; authentication, workspace lifecycle, popout lifecycle, source/link behavior, and
  most workstation flows passed. The initial default-URL attempt was rejected by connection
  refusal and is not a product result.
- Opted-in `RUN_BOARD_VISUAL_PARITY=1` visual baseline for `visual-1080p-100`: 5 passed, 21
  screenshot assertions failed with small but policy-exceeding diffs. Existing screenshot
  thresholds and masks were not changed. The other three visual projects remain pending.
- Golden Layout lifecycle coverage was exercised within the 137 passing Chromium flows and the
  existing unit suite; no isolated late-activation teardown defect was reproduced. The missing
  chart surfaces above remain a separate baseline gap.

The next product boundary is R1: inspect the existing family coverage contracts and add the
provider-neutral canonical readiness matrix without weakening current role/source semantics.

## 2026-09-03 — R1 provider-neutral readiness matrix

The first R1 product slice is published at `5eec07edcb2b1bb0b443e4b95f4e432c5c871f58`.
Coverage roles now retain persisted provider entitlement/probe fields, point-in-time support,
member-history readiness, and conservative composite status/reasons. The additive authenticated
`GET /api/v1/analysis/benchmark-families/readiness` contract enumerates every registry family and
all four independent roles without provider calls, proxy substitution, or fabricated data. Missing
market groups remain visible as registry-only unavailable roles. The benchmark-list surface loads
and displays the all-family readiness counts, while the family coverage rows show role readiness
and entitlement states.

Fresh evidence at this checkpoint:

- Backend unit suite: `1278 passed` with `67.35%` total coverage (`backend/.venv/bin/pytest backend/tests/unit --no-header -q`).
- Benchmark-family integration contract: `19 passed` (`uv run --project backend pytest -q backend/tests/integration/api/test_workspaces.py -k benchmark_family --override-ini addopts=`).
- Backend Ruff on changed files: pass.
- Frontend type-check and production build: pass; Vite retained only the existing large-chunk warning.
- Frontend Vitest: `108` files, `924 passed`, `0 failed`; the readiness store test is included.

The matrix is intentionally a readiness/lineage surface, not proof that provider-backed population
or historical continuity is complete. Session progress is now `R1_provider_readiness`; the next
slice is bounded provider/history readiness evidence and family-specific worker coverage for roles
that remain pending. No visual threshold, baseline, mask, provider entitlement, integration, or
deployment policy was changed.

The follow-up hardening checkpoint is `33fbe404ed52f75ba02a5ebdd87dfbcecf665ffb`: an entitlement
is now classified as `verified` only after a persisted successful live-probe status. Seeded or
operator-declared terms with `not_run` remain `unreviewed`, and failed probes remain
`probe_failed`; this prevents a configured provider from being presented as live-ready before an
actual bounded probe receipt exists. The focused analysis-router regression covers `not_run`,
`passed`, and `failure` transitions.
