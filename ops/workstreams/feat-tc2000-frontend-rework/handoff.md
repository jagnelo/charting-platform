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

The provider-evidence follow-up is published at `4ffe02a5eb6f843a50057dbe791669ae7f9036a7`.
The readiness matrix now includes the latest persisted availability observation for each
provider/capability pair, reduced to safe classification/success/timestamp fields and a bounded
count in `universe_provenance`; raw provider errors and request payloads are intentionally omitted.
This makes the no-provider-call read path able to show the difference between declared terms and
an actually observed probe without weakening the source-lock or fallback rules.

The metadata-readiness checkpoint is `30f0e792433f410f94910e57bf79b82118875cd9`. Each selected
holdings snapshot now reports resolved member count, non-null weight coverage, and classification
coverage. Historical classification counts require field-level industry evidence observed on or
before the requested `as_of`; current-only detail is not reused to fill a historical gap. The
role composite status remains conservative until weights, classification, member bars, point-in-
time support, and persisted entitlement/probe evidence are all ready. The workstation coverage
row exposes the weight and classification states beside continuity and history.

The historical-cutoff regression is published at `9019a04f52c85235cec0820eab9c3de12299ad4f`.
It uses a snapshot known before the requested evaluation date but classification observations learned
later: the current read reports classified members, while the historical read reports zero eligible
classification evidence. This protects the R1 point-in-time boundary independently of holdings
composition selection and member-bar truncation.

The adapter-maintenance evidence checkpoint is `8ca6cb48c8d7944e1e37430ede1f41fb94f13f54`.
Coverage roles now surface the latest persisted `ETFHoldingAdapterState` attempt (status, source,
checked/success/failure times, composition date, and bounded failure reason) without contacting a
provider. When a selected snapshot has no linked source, the most recent adapter state can still
identify the attempted source and entitlement context; absent state remains explicitly
`not_attempted`. This keeps scheduled refresh evidence actionable while interactive reads stay
provider-neutral.

The branch-owned session metadata at `ops/workstreams/feat-tc2000-frontend-rework/session.json` is
refreshed at each implementation checkpoint and records the active goal, exact implementation tip,
validation profile, and next action.

This handoff is the branch-owned `ops/workstreams/feat-tc2000-frontend-rework/handoff.md` record;
its updates are committed alongside validation receipts and session metadata.

The 2026-09-03 session checkpoint remains blocked by the required local runtime: the repository
`agent-session docker-ready` helper waited 180 seconds but Docker Desktop's socket stayed
inaccessible (`permission denied` on `~/.docker/run/docker.sock`). This is recorded as an
environment blocker only; no Docker images, containers, visual baselines, or validation thresholds
were changed. The branch remains in `R1_provider_readiness` and is not marked ready for human review
until the required profile can be checkpointed with a usable daemon.

The scheduled fan-out hardening checkpoint is `8e68b8fce5ad937ef506367fab73dcd9bcf42c9d`.
Redis enqueue exceptions are now retained as bounded per-family/date `queue_errors` while the
remaining deterministic units continue to be submitted. This complements the per-unit
`queue_error` evidence and keeps one transient queue failure from suppressing other benchmark roots.

The scheduled family/date worker hardening checkpoint is `e503afe11297180ebd1af5e3887c8c8e518e2b8e`.
Its history handoff now retains a structured `queue_error` result (including snapshot IDs and a
bounded error string) when member-history enqueueing fails, then commits and returns the completed
holdings refresh evidence. A regression test covers this failure path so one queue failure remains
local evidence and cannot erase the rest of the unit result or suppress later scheduled roots.

At the fan-out checkpoint tip `ebd03f3a6cf91eec42d2361f4bf7266afb19735f`, the complete backend
unit suite passed (`1281` tests, `67.31%` coverage against the `55%` gate). The suite includes the
new scheduler failure-isolation tests; warnings remain limited to existing NumPy/Pandas deprecations.

At the session tip `df08b269b6064b1afd46b5c3c8e95a5c8ee7e046`, the non-Docker repository contracts
remain green: 42 workflow tests, the 48-primary-source uPlot numerical-renderer audit, all 26
visual-acceptance policy assertions, and the TC2000 V25 visual manifest validator passed. The
Docker-backed stack/browser/exhaustive integration profile remains blocked by the inaccessible
Docker Desktop socket recorded above.

The fan-out receipt shape was tightened at `7ddb76339d6443826a1b7099ab07bb6caa9776fd`: each
per-family/date queue failure now includes an explicit `status: queue_error`, alongside its family,
requested date, and bounded error message. The 25-test scheduled task/worker regression remains green.

## 2026-09-03 — seeded Chromium contract repair and clean runtime checkpoint

The browser stack was rebuilt after the prior seeded run exposed one established-text compatibility
regression in the family coverage row. The readiness fields are now rendered after the legacy
`symbol · status · N date · continuity · bars` phrase, preserving existing authenticated flow
selectors while retaining the new R1 readiness detail. The focused `F8s-breadth-family-ratio`
regression passed `1/1` after the rebuilt frontend was recreated.

Fresh branch-scoped evidence at `fa97580a27777dff7c5cfe5a58fc31acc4d5bda5`:

- Seeded full Chromium flow suite: `148 passed, 0 failed` in `408.9s` against
  `STACK_URL=http://127.0.0.1:28083`; this includes the repaired F8s contract and the prior
  147 passing flows.
- Frontend type-check: passed (`npm run type-check`).
- The exact branch-scoped stack was stopped with `make test-stack-down`; its containers, volumes,
  network, and four generated images were removed by the prescribed cleanup, with no host-wide
  prune. Docker accounting is now zero known bytes, zero containers, and zero volumes.

This receipt validates the deterministic seeded browser path only. It does not close the remaining
R1 provider-population/history gaps or establish live entitlement evidence. The earlier Docker
socket-access failure remains retained as historical evidence; the daemon was subsequently
restored sufficiently for the rebuilt stack and cleanup.

The point-in-time readiness follow-up is `09eca9de46dd7f6ea72d3deda2c2891d35673f81`. A role with
only a canonical ETF profile and no dated holdings snapshot now remains
`point_in_time_supported=false` even when a caller supplies an `as_of` cutoff; the cutoff is a
query boundary, not evidence. The focused regression passes, the complete benchmark-family
integration contract remains green, and Ruff/diff checks pass. This prevents the readiness matrix
from overstating historical support while leaving provider-free reads and explicit pending states
unchanged.

The follow-up `eba8bcda7e1b1dc08ae0164c05dcb468d8fbc369` applies the same guard to unresolved
holdings: a snapshot with zero resolved canonical members is not point-in-time support. The
benchmark-family integration contract remains `20/20`, including this unresolved-snapshot
assertion, with Ruff and diff checks green.

At the same implementation tip, the full backend unit suite passed `1281` tests with `67.29%`
coverage (above the repository `55%` gate). Frontend coverage passed `108` files / `924` tests,
and the production build plus type-check passed with only the existing large-chunk warning.
These are deterministic local checks; they do not substitute for live provider population or
historical continuity evidence.

The bootstrap follow-up is `4bfd3e783fa5eb8cea561c73ae7179cd8d8fd94b`. Core ETF identity bootstrap
now applies the registry's explicit symbol-to-issuer adapter metadata (merging existing aliases)
so readiness and maintenance can disclose the known free route immediately; it still creates
identity-only profiles and performs no provider request or holdings fabrication. Workstation
bootstrap units pass `7/7`, and the bootstrap API integration slice passes `7/7`, with Ruff and
diff checks green.

The history queue-error follow-up is `9a636c5094a07a43b72722186eb2f9109a05b0bc`. The shared
snapshot-to-member-history service and admin benchmark-family history endpoint now isolate each
Redis enqueue attempt, retain bounded per-instrument `queue_error` evidence, continue later
members, and expose `queue_error_count` in the response. The service regression passes `6/6`; the
admin history-refresh integration slice passes `2/2`; Ruff and diff checks are green. A whole-pool
failure remains an explicit `queue_unavailable` outcome.

The route-matrix regression is `798f32577bacb0ed49f1a663a19ff51dc8e3a146`: all 20 configured
benchmark-family proxy symbols now have explicit local adapter metadata and a `ready` adapter
probe (SPDR, iShares, Invesco, or Direxion as configured). This is route-selection evidence only;
it performs no network request and does not claim that any holdings artifact or historical member
bars have been populated.

## 2026-09-03 — Core bootstrap member-history queue resilience

The core workstation bootstrap handoff is now aligned with the shared family-history queue
contract at `ad5740893f7b07a8a381ae9e5b2bfb6bb75b43e4`. Per-instrument Redis enqueue failures are
retained as bounded `queue_errors` with `queue_error_count`, later members continue to queue, and
the aggregate status becomes `queue_error` without discarding the provider-backed bootstrap result.
Redis-unavailable results now expose the same zero-count queue fields for a stable diagnostic shape.

The focused workstation-bootstrap unit suite passes `9/9`, including a regression where the middle
member fails and the first/last members still queue. Ruff and `git diff --check` pass. This closes a
worker fan-out integrity gap only; it does not claim canonical holdings/history population,
provider entitlements, point-in-time continuity, or live-source readiness.

The current-tip bounded readiness rerun is also green: benchmark-family coverage/readiness and
related ratios, breadth, ranking, rotation, and derived-equal integration tests pass `20/20` with
Docker access. The unprivileged retry remains a setup-only Docker socket permission failure; no
application assertion failed. The existing two NumPy deprecation warnings remain non-blocking.

The scheduled core bootstrap registration follow-up is `c1e16f4b1f0eec5513fb4e92e37bde7b5de8ed8a`.
The 01:00 opt-in core bootstrap cron function is now included in `WorkerSettings.functions`, with a
worker regression asserting both the scheduled wrapper and underlying bootstrap task are
registered. The complete ARQ worker unit slice passes `21/21`; Ruff and diff checks pass. This
ensures the existing bounded bootstrap can execute when enabled; it does not enable the schedule or
claim provider-backed population.

The startup queue resilience follow-up is `6997d6d81453062b65c1959b9aebb920b55ad86d`.
`worker_startup` now catches a transient Redis enqueue exception, logs the bounded failure, and
returns without taking the ARQ worker down. The worker unit slice passes `22/22`, including the
failure regression; Ruff and diff checks pass. This keeps opt-in bootstrap availability explicit
under queue outage and does not enable provider calls or alter schedule flags.

The full backend unit suite at the current implementation tip passes `1285/1285` with `67.32%`
coverage, above the repository `55%` gate. Existing NumPy/Pandas deprecation warnings remain the
only warnings reported. This is deterministic local evidence; canonical provider population,
historical continuity, and live entitlement proof remain open R1 requirements.

The durable family-refresh queue-shape follow-up is `e764027a21dcaf3dcf347d4d16106a2d19c73095`.
The multi-unit family refresh worker now returns the same bounded `queue_errors` and
`queue_error_count` fields for whole history-queue exceptions and explicit no-snapshot units,
while retaining the legacy error text for compatibility. Its worker unit slice passes `23/23`;
Ruff and diff checks pass. The refresh run remains completed with provider/holdings outcomes intact.

The complete backend unit suite was rerun after this worker change: `1286/1286` passed in `58.88s`
with `67.33%` coverage, above the `55%` gate. The warning set remains limited to existing
NumPy/Pandas deprecations.

Fresh opt-in provider evidence at the current tip is `11/11` in `12.24s`: iShares IWV/IJR/IWB/
IWD/IWF/IWN/IWO historical routes, Invesco QQQ SEC historical fallback, and Direxion QQQE current
and SEC historical fallback all returned parseable, identity-checked holdings. This confirms the
reviewed issuer/SEC routes, not complete database hydration, all-family population, member-bar
continuity, entitlement verification, or live top-down browser readiness.

The complementary SPDR route probe passed `16/16` in `5.86s`, including the nine mapped family
proxies SPY/SPYG/SPYV/MDY/MDYG/MDYV/SLYG/SLYV/SPTM. Combined with the preceding 11/11 iShares,
Invesco, and Direxion probe set, all 20 configured family proxy symbols now have fresh public-route
evidence; this still does not establish persisted multi-date snapshots or complete member history.

Two final mapped-symbol probes close the remaining route-evidence holes at this tip: the direct
iShares IWM route and direct Invesco RSP route each passed `1/1` with parseable, identity-checked
holdings. Together with the preceding SPDR/iShares/Invesco/Direxion runs, this gives a fresh
public-route probe for every one of the 20 configured family proxy symbols. This remains provider
route evidence only; persisted multi-date snapshots, entitlement verification, member-history
continuity, and live authenticated workstation readiness are still open R1 requirements.

The scheduled family/date worker now uses the same bounded queue-error shape as the durable run
worker at `745501566ab1f6acefd8b7f88677bedf5b6e5d34`: a broad member-history enqueue exception
retains `queue_errors`, `queue_error_count`, bounded snapshot IDs, and legacy error text while
preserving the refreshed holdings result. The focused ARQ worker suite remains green at `23/23`,
with Ruff and `git diff --check` passing. This is queue-evidence consistency only; it does not
claim persisted member-bar hydration or historical continuity.

The dated holdings refresh now preserves adapter-declared evidence at
`7cc2bf6c4d88a6e1d1145d63d818e74eb02ebf1e`: snapshot provenance, source quality, completeness,
parser version, and SEC-filing notes flow into the canonical snapshot instead of being replaced
by dated-route defaults. A focused bootstrap/service regression passes `15/15`, with Ruff and
`git diff --check` green. This keeps filing-reconstructed and issuer-dated snapshots
machine-readable; it does not claim that those snapshots or member bars have been populated in
the deployment database.

The post-provenance full backend unit gate is green at the current implementation boundary:
`1287/1287` passed in `61.84s` with `67.49%` total coverage, above the repository `55%` gate.
The warning set remains limited to the existing NumPy/Pandas deprecations. This deterministic
receipt validates the worker and dated-refresh changes; it does not convert route evidence into
persisted all-family population, member-bar continuity, or entitlement verification.

The bounded API integration rerun at the exact branch tip passes `2/2` for the dated issuer
refresh paths (`test_admin_can_refresh_issuer_holdings_for_specific_date` and
`test_admin_dated_ishares_refresh_preserves_returned_composition_date`) with the two existing
NumPy deprecation warnings. The assigned TC2000 Docker project remains clean; an unrelated
ETF-worktree BuildKit container was observed and was not touched.

The benchmark-family coverage response now reports the selected canonical snapshot's provider
provenance (falling back to the ready adapter key or source label only when no snapshot provider
is available) at `19b6e494b734af28ca3b96ee2426f54b8ef97a60`. The focused Docker-backed coverage
integration passes `1/1` (`test_benchmark_family_coverage_exposes_role_dates_and_point_in_time_filter`)
with the two existing NumPy deprecation warnings; Ruff and `git diff --check` are clean. This
corrects provider display provenance only and does not claim persisted family population,
entitlement verification, member-history continuity, or live authenticated readiness.

The family coverage contract now exposes curated route readiness separately from persisted profile,
snapshot, and entitlement state at `dfd82b63ed8680bcbb6b4a6296e6fa6306721ca4`. A mapped canonical
instrument without an ETF profile reports its registered adapter/provider as `configured`, while
profile probe outcomes may report `ready` or an explicit failure state; no route is presented as
hydrated merely because its metadata is configured. The focused Docker-backed coverage slice
passes `5/5`, the analysis-router unit slice passes `21/21`, frontend type-check passes, and Ruff
plus `git diff --check` are clean. This closes route-state observability only; snapshots, member
bars, historical continuity, entitlements, and authenticated live readiness remain open.

The complete benchmark-family integration matrix remains green after the additive route fields:
`20/20` tests passed in `11.09s` at the same product tip, with only the existing two NumPy
deprecation warnings. This confirms the route-readiness disclosure is compatible with the family
overview, coverage, point-in-time, breadth, ratios, ranking, rotation, concentration, and
derived-equal contracts; it does not convert seeded/local evidence into provider-backed population.

Provider entitlement reconciliation now follows the snapshot's declared `source_provider` (or the
configured route provider when no snapshot exists) to locate persisted entitlement rows, instead
of treating the internal holdings-ingestion source as the provider of record, at
`50c614dd9ae13da89c4b404c8b70248f72d6dedd`. The API remains provider-free: missing provider rows
remain `unknown`, while persisted free-source probe evidence can now report `verified` for both
snapshot-backed and route-only roles. The focused entitlement regression passes `1/1`, the full
benchmark-family matrix passes `21/21`, the exact-tip backend unit suite passes `1287/1287` with
`67.44%` coverage, and Ruff plus `git diff --check` are clean. This closes entitlement lineage
observability only; it does not populate snapshots, member bars, or historical continuity.

The family coverage entitlement classifier now applies persisted `effective_at` and
`review_due_at` validity windows at the requested evaluation cutoff (or current UTC time for
latest reads), at `9962ab2ad3de4ff1ff470f99f15f8d37e181e6de`. Future-effective and review-expired
terms remain `unreviewed` even when their stored probe says `passed`, matching the provider-chain
eligibility policy and preventing historical views from using future entitlement evidence. The
focused analysis-router entitlement tests pass `2/2`, the Docker-backed benchmark-family matrix
passes `21/21`, and Ruff plus `git diff --check` are clean. This closes entitlement time-window
classification only; it does not establish live entitlement records or canonical family
population/member-history continuity.

The exact-tip backend unit gate was rerun after the entitlement-window change: `1288/1288`
passed in `59.40s` with `67.45%` total coverage, above the repository `55%` gate. The warning set
remains limited to the existing NumPy/Pandas deprecations; no provider calls or fixture data were
added.

The branch-scoped authenticated Chromium flow gate was run against the assigned full stack at
`STACK_URL=http://127.0.0.1:28083` with `E2E_SEED_MARKET_DATA=true`: `151` tests passed and `2`
tests were skipped in `7.0m`. This covers the current workstation, top-down family surfaces,
Study Lab, promotion, layout, alerts, screener, drawing, dashboard, legacy, and radar flows at
the exact implementation tip `9364748d30d3350d810190e0aa8fdb8d7014c026`; the stack was then
torn down with its branch-owned volumes and containers removed. The receipt proves browser
workflow compatibility for the seeded local runtime only; it does not establish live provider
population, member-history continuity, entitlement records, or the four visual projects.

Point-in-time readiness now normalizes both offset-aware and offset-less ISO cutoffs before
comparing them with persisted UTC provenance at `06054df7d8dc0b72d5ea88e6a14d05bac67a5e19`.
This prevents historical family coverage from raising on a valid offset-less `as_of` query and
keeps future membership/classification evidence excluded. The focused Docker-backed coverage
regression passes `1/1`, the analysis-router cutoff/entitlement unit slice passes `5/5`, the
benchmark-family matrix passes `21/21`, and the full backend unit gate passes `1289/1289` in
`64.42s` with `67.43%` coverage; Ruff and `git diff --check` are clean. This closes timestamp
normalization only; it does not establish persisted provider population, member-history
continuity, or live entitlement evidence.

The canonical holding-maintenance slice now has three additional safeguards. Dated refresh failure
handling reuses a matching pending adapter-state row in the async session, preventing a duplicate
unique-key insert after a ready probe; `test_admin_dated_refresh_reuses_probe_state_when_fetch_fails`
passes alongside the two existing dated-refresh regressions (`3/3` in `12.20s`). Classification
maintenance no longer refreshes the parent snapshot after flushing scalar counters, preserving the
eagerly loaded holdings relationship and avoiding an async `MissingGreenlet` during bounded
reconciliation. The focused resolution/history unit slice remains green (`46` tests with the
normalization additions), and Ruff plus `git diff --check` pass.

Issuer holding labels are now normalized at the eligibility boundary while their raw values remain
persisted for provenance. Invesco `common stock` and `real estate investment trust` rows therefore
participate in canonical family membership/history and market-group/watchlist classification instead
of being silently excluded as non-equities. The new history unit regression accepts both labels and
rejects a money-market label. On the branch-scoped canonical runtime, the RSP equal-weight planner
reports `503` usable members and `8` explicit exclusions, selecting `50` bounded history jobs
(`44` newly queued, `6` already queued) with zero queue errors; the combined cap/equal plan reports
the same canonical counts without fabricated fallback. The RSP industry composition endpoint also
returns `13` classified industries with source `invesco` and persisted issuer-snapshot provenance.

The rebuilt branch-local runtime contains non-fixture canonical snapshots for SPY (`505/505`
resolved), RSP (`511/509`), XLK (`76/75`), and all ten mapped SPDR sector proxies; a bounded
classification pass processed `13` profiles and persisted SEC-SIC details. The authenticated
canonical browser gates `F8e.live-membership` and `F8e.live-sector-drilldown` pass `2/2` in `6.4s`
against `http://127.0.0.1:28083`, and the frontend type-check passes. This is bounded local runtime
evidence only: full all-family provider hydration, multi-date member-bar continuity, entitlement
verification, and the remaining R2-R7 workflow/visual/performance gates remain open.

The exact-tip backend unit gate after these fixes passes `1290/1290` in `59.58s` with `67.45%`
coverage (above the repository `55%` threshold); the warning set remains the existing NumPy/Pandas
deprecations. The assigned Docker project was used exclusively; its disposable local volumes will
be removed after the final evidence checkpoint. No other worktree, staging, master, integration,
promotion, or deployment action was performed.

## 2026-09-03 — durable refresh progress serialization and bounded live outcome

The provider-backed family refresh worker had a concrete persistence defect: adapter leg
provenance includes Python `date`/`datetime` values, and writing that raw structure into the
PostgreSQL JSON progress document aborted the worker after a unit completed, leaving the durable
run stuck in `running`. Commit `9d1ff3532fc1ef50f9331cc9b9b40678069ec60a` encodes leg provenance and
history-queue metadata with FastAPI's JSON encoder before persistence, with a regression test that
round-trips a dated composition field and verifies `json.dumps` succeeds.

The rebuilt assigned stack accepted an authenticated, bounded SP500 month-end refresh for
`2026-08-31`. Run 2 reached terminal `completed` with one completed unit and four explicit failed
legs: SPY, SPYV, and SPYG report that the SPDR adapter has no configured dated holdings URL
template, while RSP reports no SEC filing at or before the requested date. No latest-data fallback,
proxy substitution, or fabricated snapshot was used; the run persisted zero snapshots and no
member-history queue work. This proves durable completion/error isolation, but it does not close
the R1 historical-population gap. State Street's [public fund finder](https://www.ssga.com/us/en/intermediary/fund-finder)
exposes current daily/month-end downloads, while its [authorized-participant resources](https://www.ssga.com/us/en/intermediary/resources/authorized-participants)
describe daily holdings as an SFTP resource; no authoritative public dated route was established
here, so the SPDR historical route remains an explicit provider-readiness gap rather than a
speculative URL implementation.

The full backend unit suite passed 1,291/1,291 with 67.45% coverage, the complete worker unit file
passed 24/24, Ruff and `git diff --check` passed, and the worker log contained no serialization
exception after rebuild. The stack remained live only for this validation boundary and was then
torn down with the prescribed branch-scoped helper. Cleanup reported zero containers and zero
retained volumes, removed four generated images, and performed no host-wide prune. The disposable
validation token was removed from `/tmp`.

## 2026-09-03 — committed-snapshot history enqueue verified with QQQ

The next R1 defect was a transaction-visibility race: the durable and scheduled workers queued
member-history jobs before the holdings refresh transaction committed. Commit `000b1705b1a8246fbdef2012267bd0f49abebb2e`
commits the refreshed snapshot and materialized constituent rows before enqueueing independent
bulk-history jobs in both paths. Ordering regressions assert that queueing observes the committed
boundary.

The assigned runtime then ran a bounded Nasdaq-100 refresh for `2025-12-31` (the date used by the
existing SEC-backed QQQ/QQQE provider evidence). QQQ refreshed as snapshot `1` with `101/101`
resolved rows; a direct database assertion found `0` dangling constituent IDs. The durable run
completed with `history_queue.status=queued`, `101` selected/queued jobs, and the equal-weight
QQQE leg retained an explicit SEC identity/no-parseable-filing failure. All `101/101` member jobs
drained from Redis, every progress record reached `complete`, and the worker log contained `0`
missing-instrument warnings. This proves the snapshot-to-history handoff and idempotent queue
lifecycle, not member-bar readiness: the local free-provider runtime returned zero MN/W1/D1 bars
for all 101 jobs, so no OHLCV bars were persisted. That remains an explicit R1 data-availability
gap; no paid credential, latest-only fallback, or fabricated bar was introduced.
