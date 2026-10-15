# Central coordination of the four feature checkpoints

## Authorized direction

Recorded 2026-10-15. The human wants the existing Provider, ETF, TC2000, and
Strategy Lab v2 work integrated into staging, reconciled and tested together,
then the same feature sessions/branches updated from green staging so development
can continue with the formerly missing parallel features. The human requested
updates to durable guidance and the existing extension-visible session goals,
and asked that the central session choose the merge/reconciliation sequence.

This authorizes preparation and coordination, same-source staging reconciliation
by each owning feature agent, and continued work within each existing roadmap.
It does not assert that a branch is ready, accept an unreviewed checkpoint,
waive tests, authorize promotion/deployment, or transfer writer claims. Preserve
the later human acceptance of each concrete integration checkpoint. The trial
remains a separately authorized post-integration operational gate.

The coordinator's working copy is
`/home/m920q/charting-platform/.ai/worktrees/staging`. Until published, feature
sessions read this local document without modifying or pulling that checkout.
The workflow checkpoint is published at staging
`98f0b888817c461fa00e6e310c5b378b0c4c512f`; its exact staging CI must pass
before any subsequent product integration. This is not a product baseline.
Live coordinator decisions, the queue and source freezes are recorded in
`ops/feature-integration-status.yaml` in that same checkout. Source owners should
read it at coherent checkpoints when an upstream dependency is still pending.

The current cross-branch migration, cost-governance and browser-repair tasks are
in [the reconciliation handoff](feature-integration-reconciliation.md). Strategy
has independent migration work available before the combined baseline arrives.

### Subsequent human authorization: close validated technical repairs

Later on 2026-10-15, in response to the coordinator's explicit request to open
the narrow chart-template pointer repair, the human stated:

> Yes I approve, and you do not need my acceptance to close it off, it's a waste
> of time for me to individually verify each individual fix in all the 4 parallel
> development branches - do this yourself, with care, I just want to get to the
> merged-into-staging state to finally try this out

This explicitly activates the narrow repair topic and authorizes the coordinator
to review and close validated technical fixes needed for these four integrations
without asking for per-fix signoff. Record this exact decision in the applicable
closure record together with the delivered scope, exact source and evidence.
It does not mark an unfinished feature checkpoint ready, weaken a required gate,
approve an unreviewed product-scope reduction, discard data, authorize deployment
or activate providers/the operational trial. The coordinator owns technical
review and staging mechanics; ask the human only when a material product choice
or another action beyond this authorization is actually required. Earlier
references below to obtaining human acceptance per technical repair are
superseded by this recorded authorization, not by an invented acceptance.

## Order of action

1. **Central analysis first.** Read the four current source/workstream records,
   inspect overlapping behavior and migration/API/configuration contracts, and
   maintain the dependency order Provider → ETF → TC2000 → Strategy Lab v2.
   Identify the smallest required shared repairs and give their owning sessions
   concrete tasks. Do not create disposable combined merge checkouts or bypass
   the single persistent staging path.
2. **Prepare sources in parallel within ownership.** Source sessions adopt the
   checkpoint policy while retaining the full roadmap. Fix independent defects,
   prepare contract evidence, and commit/push coherent changes. Only merge a
   dependency from synchronized green staging after the coordinator has made it
   available. No direct feature-to-feature imports, cherry-picks, or staging
   writes from feature agents.
3. **Review and integrate Provider first.** Resolve required shared-gate failures
   through a suitable source owner or a separately authorized narrow repair.
   Present ICP1-ICP7 evidence and proposed operation deferrals to the human.
   After the required checkpoint closure, freeze the exact clean pushed source and use the guarded
   staging integration command. Wait for exact staging CI.
4. **Reconcile and integrate ETF, then TC2000, then Strategy Lab v2.** For each,
   its owning agent merges the latest synchronized green staging into its own
   clean unfrozen source, resolves combined behavior, implements missing consumer
   wiring, and validates. Human acceptance precedes the coordinator's next merge.
   A green independent test suite does not substitute for this reconciliation.
5. **Validate the joint result.** Require exact staging exhaustive CI and actual
   combined-contract acceptance for the delivered scopes: provider selection and
   quota/coverage, current/unavailable ETF lineage in the workstation, immutable
   Study/Code outputs consumed by v2, versioned migrations, and application/worker
   startup. Test negative paths as well as success. Missing upstream data must
   remain explicit; no broker or live-capital activity is part of this gate.
6. **Release the common baseline to the existing sessions.** Record the exact
   final green staging SHA and the source receipts. Release all frozen sources.
   Each owning session merges that SHA into its same feature branch, revalidates
   the affected contracts, updates its handoff and goal, and continues its complete
   original roadmap. If the source advanced after the accepted checkpoint,
   reconcile those commits explicitly; never discard or reset them.

There is one staging writer. Central knowledge supports cross-feature decisions;
it does not make the coordinator a simultaneous product writer in four claimed
worktrees. Branch agents can prepare independent repairs before upstream merges.
Do not leave all three downstream agents idle merely because consumer wiring is
gated. Conversely, a blocked upstream gate is not permission to repeatedly spend
scarce provider quota or invent an alternate merge path.

## Resume task for each existing feature session

At the next user resume/play action, first read this document, the
[checkpoint contract](agent-orchestration.md#accepted-integration-checkpoints-and-continued-feature-development),
and the [provider checkpoint](provider-integration-checkpoint.md), then inspect
your actual source and branch-owned records. Preserve the current exclusive
claim. A stale/foreign claim requires the repository's explicit takeover process;
this directive does not replace it. Update your own plan/handoff/session evidence
to distinguish the current integration checkpoint from the full roadmap. Follow
the canonical UV-managed preflight. Do not treat a stale completed-criteria list
or a replaced Codex goal as product acceptance.

### Provider — `feat/market-data-provider-platform`

Prepare `provider-platform-integration-1` under ICP1-ICP7. Prioritize the shared
identity, provider, quota, series, coverage, API, and migration contracts needed
by downstream consumers. Classify provider operations as verified/enabled,
disabled/deferred, quota-held, or failed with exact current-source evidence.
Finish required tests and a clean pushed review receipt; preserve queried data,
pagination, and the private shared quota ledger. Keep unsupported operations
non-routable. Do not mistake temporary quota waits for proof or silently omit a
capability needed by consumers. The chart-template click failure recorded by the
latest browser run needs a centrally coordinated owner repair; do not rewrite
frontend code from this backend-only session. Stop at human checkpoint review.

### ETF — `feat/etf-holdings-constituents`

Prepare `etf-holdings-integration-1`. Preserve native/fallback truthfulness and
issuer live evidence. First reconcile the recorded green checkpoint with actual
HEAD and refresh only evidence made stale by new source changes. Identify exact
provider runtime interfaces needed by holdings and document the ETF-owned
`ETF_HOLDINGS` bridge. After the provider merge is green, merge staging into this
source, implement/reconcile that bridge, integrate entitlement/quota/budget/health
and identity behavior, and test current/degraded/stale/unavailable lineage through
the actual shared runtime. Keep unavailable routes explicit. Prepare the clean
pushed review checkpoint; retain the full issuer roadmap and later observation
work. Do not wait for the entire provider feature or its 30-day trial.

### TC2000 — `feat/tc2000-frontend-rework`

Prepare `tc2000-workstation-integration-1`. Diagnose the independent chart-template
pointer-interception failure and remaining functional/visual differences now,
without waiting for upstream contracts. Distinguish product defects, stale
oracles, missing reference evidence, and execution problems. Preserve the visual
policy; a fix inside this broad branch does not reach the provider branch until
the coordinator delivers an independently accepted repair to staging if needed.
Propose that narrow repair to the coordinator rather than importing TC into the
provider branch. After Provider and ETF are green in staging, merge staging into
this source, reconcile ownership intersections and actual capability/coverage/
lineage consumers, and validate a usable combined workstation. Preserve the full
V25 roadmap and unresolved reference contracts. Stop at human checkpoint review.

### Strategy — `feat/strategy-lab-v2`

Prepare `strategy-lab-v2-integration-1`. Reconcile stale session summaries with
the later RC6/package/backend/API evidence; do not repeat already closed engine
work merely because an old progress field mentions it. Preserve exact-pinned
scope-qualified Nautilus RC conformance; a stable-release label is not a new
gate. Prepare API/migration/worker consumer evidence and negative paths now.
After Provider, ETF, and TC2000 are green in staging, merge staging into this
source, reconcile canonical identity/series/coverage, point-in-time holdings,
immutable CodeVersion/Study lineage, routers, migrations, and Compose workers,
then run the required combined profile. Preserve engine-neutral contracts and
the complete roadmap; no broker connection or real-capital execution. Stop at
human checkpoint review.

## Coordinator handoff and source-freeze protocol

Use the existing workstreams as durable truth. The coordinator records the
expected source SHA, accepted checkpoint, starting staging SHA, merge/CI receipt,
and source release before asking an owner to continue. During a freeze the source
owner must not commit, push, merge staging, or switch scope under that source.
Conflicts abort staging unchanged; the owner repairs combined behavior on its
source, pushes and revalidates before a new attempt. Red staging pauses further
integrations until the authorized repair workflow restores it.

Preparing or updating these directions does not create a merge acceptance.
The coordinator should present one concrete, concise acceptance summary per
checkpoint rather than require the human to reconstruct all branch internals.
Keep old source receipts and full goals as history. The staged build becomes a
development baseline; production qualification is a separate decision.

## Saved Codex goals and extension resume

The four feature goals point to these resume tasks and their owning workstream.
They are updated through `thread/goal/set` and read back through `thread/goal/get`,
without starting turns or changing current paused/blocked states. Official API
documentation describes accounting reset on a new objective; this installed
version preserved all four usage totals, independently verified after the update.
The old objective/status/usage receipt is retained
in `ops/feature-session-goals-2026-10-15.json`. That file is audit/handoff metadata,
not an alternative goal database. No Codex SQLite or rollout is edited directly.

Each session adopts its own branch-plan changes when the user resumes it; this
coordinator does not overwrite a running writer's plan or claim. Updating a goal
does not update stale branch progress automatically. Read current evidence and
record the new checkpoint before implementing. The existing conversation and
worktree context are retained. If upstream reconciliation is genuinely blocked,
report the exact next coordinator dependency rather than claiming completion.

The provider goal was shortened after the human still saw a cropped old label.
Saved API state was independently verified, but a separate App Server connection
does not prove that an already-open extension view refreshed. Preserve running
turns and distinguish saved-goal verification from visible UI verification.
