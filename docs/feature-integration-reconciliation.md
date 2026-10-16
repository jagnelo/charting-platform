# Four-feature reconciliation handoff

Coordinator audit: 2026-10-15. This is an execution handoff for the existing
feature owners, not checkpoint acceptance or permission to modify another
worktree. The human directed the central session to coordinate integration and
proceed until a genuine blocker or human decision. Preserve the existing order:
Provider → ETF → TC2000 → Strategy Lab v2.

## Observed source boundaries

| Source | Observed HEAD | State at inspection |
| --- | --- | --- |
| Provider | `65a467b43d7830b0875d9c3ad538e47a06d4a6db` | Active staged candidate; seven local commits ahead of the last fetched remote; not frozen or review-ready. |
| ETF | `d1040b41b99b3ece8e25e777ef51a300393c7429` | Clean; point-in-time basket repair and preparation tests published. |
| TC2000 | `f39a0d5da97969154cf09a9d195d6583c52deff6` | Clean; pointer repair proposal available; browser/visual environment validation unfinished. |
| Strategy Lab v2 | `b85a4b9cb6a1bde93605f8f91c53add466782834` | Clean; independent consumer preparation complete; waiting for combined staging. |

These observations are not source freezes. Read current refs and owner records
again before acting. Worktree cleanliness alone does not establish remote CI.

Published workflow staging is `98f0b888817c461fa00e6e310c5b378b0c4c512f`.
GitHub run `38770968246` has passed frontend and backend jobs; its exhaustive
integration and Playwright jobs were still running at the audit. It contains
workflow changes, not accepted Provider/ETF/TC/Strategy product integrations.
No combined baseline has been released.

## Migration identifier collisions: Strategy-owned preparation now

A read-only AST audit of all four migration directories found 111 distinct
revision IDs and these four identifiers assigned to different migrations:

| Identifier | Earlier integration owner | Strategy Lab v2 migration |
| --- | --- | --- |
| `ff0a1b2c3d4e` | TC: `add_ohlcv_derivation_provenance` | `add_strategy_lab_v2_storage` |
| `ff1a2b3c4d5e` | TC: `add_adjustment_factor_observations` | `add_strategy_lab_v2_dispatch_payloads` |
| `ff2a3b4c5d6e` | TC: `add_provider_adjustment_factor_fields` | `add_strategy_lab_v2_worker_settlements` |
| `ff5a6b7c8d9e` | Provider: `make_provider_limits_explicit` | `strategy_lab_forward_lifecycle_idempotency` |

The first three TC/Strategy definitions have overlapping parent identifiers as
well. The Provider definition of `ff5a6b7c8d9e` follows `4d5e6f708192`, whereas
Strategy's follows `ff4a5b6c7d8e`. A textual Git merge could retain both files
without resolving this semantic collision. A merge revision alone cannot make
two different migrations sharing one revision ID unambiguous.

Strategy's existing session owns the repair investigation. Preserve the earlier
owners' definitions and plan unique identifiers for Strategy-owned migrations,
including every dependent parent/reference/test update. Before changing any
identifier, establish whether a retained database already records it and how to
preserve that database's history. Do not blindly rename an applied migration,
stamp revisions, reset/drop a database, or infer that a revision string proves
which of the colliding schemas exists. If compatibility requires a human choice,
publish the exact alternatives and stop that part. A safe identifier repair and
regression evidence can proceed before upstream product branches are merged;
actual combined upgrade/startup validation still follows staged reconciliation.

The coordinator queued this task to existing Strategy session
`01a0a4ae-c3eb-7bf0-b3f3-ecc833f2c00b`, message
`01a1407a-642b-7012-be6f-6e0e68c947a5`, using the installed Codex queue command.
Queue acceptance alone is not evidence of execution. At 16:53Z the owning
session acknowledged the collisions and began a seven-revision Strategy
namespace repair with a read-only ambiguity guard. Its stated rule is to stop
ambiguous installed histories without changing schema or version rows. Verify
its eventual code/tests and durable receipt; the repair is not yet accepted.

The same native queue mechanism delivered contract handoffs to Provider
(`01a1407c-71a5-7af2-8190-37566da3d5ce`), ETF
(`01a1407c-716b-7f22-8829-00ee34cfee27`) and TC
(`01a1407c-7182-7e52-9125-a5bcd182c841`). They were not interrupted or forked.

## Shared provider migration divergence: preserve the fail-closed contract

All four branches contain
`b6c7d8e9f0a1_add_provider_runtime_and_observation_tables.py`, but Provider's
definition differs. Its quota/concurrency/cooldown columns are nullable without
guessed defaults, rather than the inherited generic 2/60/15/30 values.
Provider also has the later `ff5a6b7c8d9e_make_provider_limits_explicit.py`
migration, which alters existing columns and clears unverified legacy values.

Do not choose the old defaults while reconciling shared paths. Provider owns
fresh-install versus existing-database equivalence evidence and must confirm
that both migration paths yield the same fail-closed behavior. Downstream owners
retain that accepted contract during their staging merges. A source hash
difference here is intentional behavior requiring semantic validation, not an
automatic reason to discard either migration's history.

## ETF bridge: resolve the shared cost-governance contract before review

ETF has prepared real persisted-consumer success, denial, stale/unavailable,
retention and historical-knowledge-time tests. Its owning record reports all
1,536 backend unit tests green, including 611 adapter cases. That does not prove
the future Provider bridge: the combined Docker/browser profile remains open.

Its contract map at
`ops/workstreams/feat-etf-holdings-constituents/integration-checkpoint.md`
identifies two important boundaries:

- ETF owns `ETF_HOLDINGS`, the additive capability migration, registry/native
  adapter bridge, and issuer transport wiring after Provider reaches green
  staging. No duplicate ETF-only governance runtime is permitted.
- ETF could not locate a shared aggregate recurring-subscription budget
  admission contract. Provider owns shared cost governance; jointly specify
  how all active subscriptions count toward the approved 20 EUR/USD-equivalent
  monthly ceiling, how currency equivalence is reviewed, and how free/already
  entitled sources are admitted. Paid activation still needs explicit approval.
  Do not invent an exchange rate or silently waive this ETF requirement.

Before adding a new subsystem, Provider should identify an existing applicable
contract or demonstrate a tested free-only checkpoint boundary that makes paid
activation impossible. Any remainder must have explicit ownership and human
checkpoint acceptance; an unlocated interface is not proof that it is absent.
ETF's eventual bridge must account for actual requests/pages/retries/redirects,
not reserve one request for an arbitrarily large multi-fetch operation. Unknown
quota or operation cost denies before transport. Read operations spend no quota.

## Shared browser blocker: narrow repair needs its own topic authority

The Provider browser receipt has 153 passed, 106 skipped and one failure:
F9c-template-comparison, where Plots intercepts Remove RSP. TC's proposal is
`ops/workstreams/feat-tc2000-frontend-rework/chart-template-repair-proposal.md`.
It isolates comparison z-index 12 → 14, a pointer-transparent wrapper and
pointer-active input/direct buttons; TC's focused comparison and adjacent
toolbar evidence passes. The historical TC commit also changes geometry and
must not be imported wholesale.

The human has now explicitly authorized an independent narrow repair topic and
delegated its technical acceptance/closure to the coordinator, without per-fix
human signoff. See the subsequent authorization in the coordination document.
Create its own assigned worktree from synchronized staging through the guarded
workflow. Do not modify frontend from the backend-only Provider session, skip
the browser case, or import all of TC early. The repair still needs its own
before/after evidence, normal validation, recorded closure, coordinator
integration and green staging result. It is separate from the broader feature
checkpoint; the human has not declared any unfinished checkpoint complete.

TC's wider visual failures additionally involve incompatible font environments
in existing snapshots and stale retained fixture freshness. Preserve screenshot
oracles, tolerances, existing assigned data and active tests. Fresh isolated
fixture preparation is TC-owned; it is not permission to relabel stale data
current or start a second competing browser matrix.

## Next coordinator boundary

Verify owner acknowledgement, finish current staging CI observation, review the
Provider's exact-source checkpoint/dispositions, and execute the authorized
narrow repair. Do not merge a dirty candidate or fabricate checkpoint readiness
from the instruction merely to coordinate. No sources are frozen and no product
checkpoints have been accepted. Promotion, deployment, provider activation and
the post-integration 30-day trial remain separately unauthorized.
