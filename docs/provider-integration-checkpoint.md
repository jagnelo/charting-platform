# Provider-led integration checkpoint

## Human direction and authorization boundary

Recorded 2026-10-15. The human requested a useful integration point before the
market-data feature reaches full completion so that dependent feature sessions
can reconcile and continue. The human then instructed this coordinator:

> You update the underlying plan, docs, whatever else is necessary, I'll share
> this prompt with that session's Codex agent and have it update its own ongoing
> goal to correctly account for this slight adjustment in direction

This authorizes checkpoint planning and the corresponding workflow guidance.
It does not accept an implementation checkpoint, authorize a feature merge,
promote master, deploy, activate providers, or start the operational trial.
The full market-data objective and all outstanding requirements remain in force
as the roadmap. The implementation percentage previously discussed is advisory
and is not acceptance evidence.

This coordinator update is confined to workflow documentation in the persistent
staging worktree under the scoped workflow-maintenance exception. Authorization
and validation are recorded in `ops/workflow-validation.jsonl`. No active
feature session's claimed worktree or operational records are edited here.

## Integration objective

Checkpoint ID: `provider-platform-integration-1`.

Deliver a tested backend foundation that ETF holdings, TC2000, and Strategy Lab
v2 can consume without duplicating provider governance or waiting for the whole
market-data roadmap. Each supported operation must have truthful availability,
identity, coverage, source provenance, and provider-specific quota behavior.
Unsupported or unfinished operations remain explicit and non-routable.

The source branch contains all of its accumulated changes. Deferring an operation
does not exempt its shipped code, migrations, defaults, or compatibility paths
from regression tests and integration validation.

## Required checkpoint acceptance

The market-data owning session incorporates these requirements into its plan,
defines executable checks for each, and fills in the exact consumer contract
locations and evidence. These are the checkpoint's minimum requirements, not a
claim that they have already passed.

| ID | Required outcome | Evidence needed before review |
| --- | --- | --- |
| ICP1 | Stable security/issuer/listing/provider-symbol contracts preserve identity, provenance, and history. Missing or ambiguous identities remain explicit. | Fixture and database tests for mapping, conflicts, symbol changes, unresolved identity, and legacy compatibility; a precise account of unresolved cross-provider identity work. |
| ICP2 | Shared capabilities, entitlements, quotas, usage, health, and routing expose usable contracts to consumers. | Restart/concurrent-worker accounting tests, request/credit/byte/symbol dimensions as applicable, and rejection of unknown/exhausted quotas. No generic guessed limits. |
| ICP3 | Canonical market series, calendars, coverage, refresh jobs, and missing-data behavior are usable by consumers. | API/worker/database tests proving provenance, freshness, gap handling, scheduling/lease recovery, and no provider calls hidden inside analytic evaluation loops. |
| ICP4 | The checkpoint's enabled provider operations have bounded live evidence for the final source; all excluded operations have explicit, tested unavailable/disabled behavior. | An operation-level inventory distinguishing enabled-and-verified, disabled/deferred, temporary quota wait, and failed. Quota waits and historical receipts do not count as current success. A failing required operation must be fixed or proposed for explicit human-approved deferral before acceptance. |
| ICP5 | Additive migrations, application startup, secret boundaries, defaults, and existing callers remain compatible. | Required migration and full-stack validation, source branch CI, backend-only credential exposure, and explicit configuration requirements. Missing deployment credentials are not a claim of deployment readiness. |
| ICP6 | Downstream agents can identify and consume the delivered contract without guessing. | A contract map for each consumer below, example success and unavailable responses, ownership boundaries, and remaining consumer wiring/tests. Required consumer capabilities cannot be silently deferred. |
| ICP7 | The checkpoint is reviewable and its unfinished roadmap is durable. | Clean pushed source, normal declared validation profile, exact-source evidence, full original-criterion disposition, and closure summary prepared for later human acceptance. Closure authorization remains pending until acceptance. |

Retain `full_integration` and the currently required local profile. This direction
does not approve `focused_only` for application changes, waive browser failures,
refresh screenshot oracles, weaken tolerances, or treat partial live suites as
complete. Any unrelated failing gate must be repaired through its proper owner
or an explicitly authorized repair topic.

## Consumer contract map and integration order

| Order | Source | Required reconciliation and next step |
| --- | --- | --- |
| 1 | `feat/market-data-provider-platform` | Establish ICP1-ICP7 and obtain human checkpoint acceptance. The coordinator integrates and waits for green staging CI. |
| 2 | `feat/etf-holdings-constituents` | Consume the staged provider capability, entitlement, quota/budget, health, identity, and availability contracts. ETF owns the `ETF_HOLDINGS` bridge and holdings provenance/freshness semantics. Test the real shared runtime rather than a duplicate ETF-only runtime. |
| 3 | `feat/tc2000-frontend-rework` | Consume the staged provider coverage/preflight and ETF capability/lineage contracts. Resolve intersecting paths semantically; stale or unavailable data cannot become current analytic input. Validate the usable workstation before its own acceptance. |
| 4 | `feat/strategy-lab-v2` | Consume staged canonical identity/series/coverage, point-in-time ETF membership, and immutable TC CodeVersion/Study outputs. Reconcile shared API/router, migrations, configuration, and worker contracts before its own acceptance. |

The coordinator performs one accepted integration at a time. A green staging
receipt releases downstream reconciliation; a source push or passing unit suite
does not. These branches are not authorized as a single batch by this document.
The existing dormant `feat/strategy-lab` is outside this integration sequence;
no deletion, archival, or supersession action is authorized here.

## Preserve the full roadmap

The market-data agent must preserve the exact original goal and all original
acceptance criteria, including IDs and text, in `roadmap_goal` and
`roadmap_acceptance_criteria`. Keep append-only validation and historical handoffs.
Use an `integration_checkpoint` section for this checkpoint ID, this direction,
consumer contracts, and an exhaustive disposition of the original criteria.
Use checkpoint criteria for the current goal/progress; do not transfer old
completion marks without re-verifying the corresponding requirement.

For every original criterion, record what is delivered now, what remains, who
owns it, and the acceptance evidence required in the continuation. In particular,
do not drop any of the following merely to obtain a merge:

- Full provider/capability coverage and unresolved provider-specific contracts,
  quotas, account baselines, pagination costs, entitlements, and live evidence.
- Complete US-listed/OTC universe and lifecycle evidence, cross-provider canonical
  identity reconciliation, SEC admission/materialization, historical coverage,
  and the required continuous refresh performance.
- Lossless queried-response retention, resumable pagination, durable usage,
  provenance, current-versus-stale semantics, and compatibility behavior.
- Separate environment secret-store verification, target deployment validation,
  operational discrepancy reporting, and the complete operational trial.

The checkpoint must deliver the subset genuinely required by downstream
consumers. A larger coverage/performance promise may remain open only when the
limitations are explicit and the accepted consumers function correctly within
the delivered bounds. Safety, identity integrity, and truthfulness of available
data are required now, not deferred promises.

## Operational trial and later releases

The 30-day operational trial is a post-integration operational acceptance gate
on a separately authorized combined test deployment. It is no longer a
prerequisite for accepting this development integration checkpoint. This
supersedes the earlier provider plan wording in `AC-SHADOW-FINAL-PHASE` and any
other wording placing the trial before staging integration. Preserve its full
duration, daily/final reports, 99% eligible D1 coverage target, discrepancy
analysis, and zero silent identity/quota violations as outstanding requirements.

Trial preparation does not start the trial, activate routing, or deploy anything.
Do not infer that a staged build is operationally qualified, ready for production,
or approved for promotion. Human testing can start on a separately authorized
combined test environment once the required provider, ETF, and TC contracts are
integrated and validated; Strategy Lab v2 may follow later. Promotion to master,
deployment, and trial activation each retain their required human authorization.

## Handoff to the running market-data agent

Read this document and the accepted-integration-checkpoint section of the
coordinator's `docs/agent-orchestration.md`. Until published through the normal
workflow, use the local canonical copy at
`/home/m920q/charting-platform/.ai/worktrees/staging/docs/provider-integration-checkpoint.md`.
Reading this direction does not authorize pulling the coordinator checkout or
editing it from a feature session.

Update only your own branch plan/handoff/session evidence, then update your own
ongoing goal as the human requested. Preserve all existing source work and
quotas. Prioritize the checkpoint's blocking contracts, and bring the concrete
delivered checkpoint to human review. Record any proposed deferral that prevents
an existing downstream requirement from working rather than assuming approval.
Keep `human_closure_authorization: pending`; the planning instruction is not the
later statement accepting the implementation.

Once the human accepts a named checkpoint, the existing closure fields record
that checkpoint scope and the outstanding roadmap. The coordinator then uses
the existing guarded merge path. After green integration and coordinator release
of the frozen source, the existing feature session may merge green staging into
its own branch, validate the combined contracts, and continue the original
authorized roadmap in that same worktree. Preserve the accepted source SHA and
checkpoint receipt; subsequent integrations need a fresh acceptance. See
[`feature-integration-coordination.md`](feature-integration-coordination.md) for
the central-first sequence and each session's task. The original feature's
completion must never be inferred from its branch having been integrated.
