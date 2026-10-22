# TC2000 ownership and integration reconciliation

This is the TC branch's durable boundary ledger. The machine-readable, complete
path intersection is in [ownership-reconciliation.yaml](ownership-reconciliation.yaml).
The counts below are path intersections against the common staging base, not
claims that every overlapping file contains duplicate behavior.

## Branch ownership and current state

| Branch | Owner boundary | Observed state at snapshot | TC action |
| --- | --- | --- | --- |
| `feat/market-data-provider-platform` | Generic instrument identity/listings, OHLCV, provider capability, entitlement, health, preflight, coverage and refresh dispatch | `da06e560`; `ready_for_human_review`, not in staging | Consume its stable contracts only after coordinator promotion to staging |
| `feat/etf-holdings-constituents` | ETF holdings adapters, acquisition, constituent resolution, refresh, audit and holdings capability | `52814f95`; waiting for provider-platform to reach staging | Consume its capability and source lineage after it synchronizes with staging and completes |
| `feat/tc2000-frontend-rework` | TC workstation UI, V25 interaction/visual parity, TC read-side analysis, Python/DSL/Study/Strategy, lineage and compatible artifact promotion | Product tip `e93de4af`; staging-derived | Continue independent TC UI and Study/Strategy work; reconcile upstream paths after promotion |
| `feat/strategy-lab` | Separate/stale strategy workstream | No changed-path intersection in the snapshot; user explicitly chose not to depend on it | Do not block TC or replace TC's existing Study/Strategy work |

The authorized dependency sequence is provider-platform → staging, ETF
holdings → staging, then TC synchronizes from staging through the repository's
prescribed workflow. TC does not merge either feature branch directly and does
not edit their worktrees. If an upstream owner has not promoted a dependency,
TC continues independent frontend and TC-owned Study/Strategy work; it does not
fill the gap with local provider or ETF implementations.

## Consumer contracts

The provider-platform branch is the authority for `EvaluatorPreflightStatus`
(`full`, `partial`, `deferred`, `stale-blocked`, `provider-unavailable`,
`empty`) and persisted coverage, provider, capability, entitlement and health
evidence. TC may compose those facts with its own analytic requirements and
display the resulting workstation state. It must retain the source status and
reasons; it must not select/probe providers, manage credentials, retry/repair,
or start generic ingestion from an interactive TC read path.

The ETF branch is the authority for holdings capability availability
(`current`, `degraded`, `stale`, `unavailable`, `not_applicable`, `unknown`) and
its audit/source lineage. `usable_for_current_analysis` is the eligibility
input; `displayable_last_known` allows explicitly labelled historical display
only. Preserve source tier, provider, identity verification, completeness,
composition/published/freshness dates and failure details. TC must not add
holdings adapters, provider probes, refresh routes/workers or constituent
resolution.

Contract names and enum values are a snapshot from the two branch worktrees,
not a substitute for re-verification after they reach staging. The exact
staging schema and behavior are the integration authority.

## Measured path intersections

At common base `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`, the branch diffs
intersect in 78 paths for provider-platform ↔ TC and 35 paths for ETF ↔ TC.
These complete intersections are recorded individually in the YAML ledger.
The provisional disposition for each is `shared_reconciliation` until a
line-level semantic review can be made against the promoted staging tip; a
common path alone does not make all TC edits redundant. The ledger calls out
the currently evidenced exception below rather than prejudging every overlap.

The ETF adapter service `backend/app/services/etf_holdings_adapters.py` and its
unit-test module need owner-level reconciliation. TC history has modified the
adapter in 93 commits, including the dated-source hardening in `bb70fff14` and
`b375a4782`. Preserve that history, but do not keep advancing the ETF provider
implementation in TC. After ETF reaches staging, compare behavior and tests,
transfer any still-needed TC-only behavior through the ETF owner/coordinator,
and remove or adapt only the redundant TC-side behavior in the normal staging
synchronization workflow.

The 2026-09-15 uncommitted SEC investigation also found the QQQE N-PORT Dreyfus
Government Cash Management row. SEC Item C.4 labels DGCXX a “short-term
investment vehicle,” Item C.1 identifies a registered fund, and the reported
percentage `0.8313234437` is percent (`0.008313234437` as a fraction). The
existing exploratory parser test passed 9/9, but parser/test edits are not
retained in this TC branch. This is an ETF-domain finding requiring handoff and
owner acceptance; the handoff has not yet been sent or acknowledged. The finding
does not create new TC data-readiness scope.

## Reconciliation rules after staging promotion

For each intersecting file, inspect the actual changed lines and tests against
the synchronized staging version, then assign one disposition in the YAML
ledger:

- `tc_owned`: the overlapping code is exclusively a TC consumer/UI/Study/Strategy
  behavior and remains in this branch.
- `upstream_duplicate`: the same behavior is already supplied by its owning
  branch and the TC copy can be removed/adapted without loss.
- `upstream_transfer_required`: needed behavior is still absent upstream and
  must be agreed with and landed through that owning branch/workstream.
- `shared_reconciliation`: the file contains both upstream contract and TC
  consumer behavior; retain narrow shared seams and test both sides after sync.

Record evidence (staging commit, relevant code/tests, disposition and any
transfer decision) per path. Do not rewrite branch history to make the overlap
look smaller. If an upstream branch changes its contract while TC is still
independently progressing, update only this TC consumer plan/ledger and defer
code integration until staging contains the dependency.

## Exact pre-replan validation receipt

At TC product tip `e93de4af43766a85242958e30702d32f231df8ee`, all pre-visual
stages of the exhaustive gate passed: backend unit tests 1,619/1,619,
integration tests 405/405 at 82.23% combined coverage, frontend Vitest
1,067/1,067, type-check/build, Compose/provider/research-runner checks and
functional Playwright 165 passed with 107 documented skips. Visual E2E was
98/104; the six established protected screenshot diffs remain. The optional
branch-test suffix was not reached. Cleanup was clean. This is preserved
historical evidence at that exact product tip, not a fresh validation of the
replan commit. Do not change baselines, thresholds, masks, skips or acceptance
policy to hide the six diffs.
