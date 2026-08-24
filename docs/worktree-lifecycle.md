# Worktree lifecycle and cleanup policy

## Human controls

- A human authorizes work, chooses validation scope where required, and explicitly closes a topic.
- Agents may plan, implement, test, and report readiness only within that authorization.
- Integration/deployment never follows from green tests alone.

## Local storage lifecycle

- A merged, clean, stopped branch worktree is closed with `make worktree-close`.
- An unmerged abandoned branch is never force-removed automatically; archive it only after explicit human approval and a recorded reason.
- An integration candidate is a **temporary combined test copy**, never a source of truth. Its identity includes the exact `master` SHA, source branch, and source SHA. There can be only one candidate for that immutable input set.
- Every candidate receives a generated lifecycle record under `.ai/integration/ledger/`. The record names its inputs, state, conflict paths or failure reason, and final disposition. This is the durable local audit trail for a disposable copy.
- `make worktree-cleanup-report` is read-only. It classifies every candidate individually and flags historical copies with no lifecycle record as `unaccounted_legacy_candidate`; those copies cannot be removed automatically.
- `make worktree-cleanup-reconcile` is safe and non-destructive: it creates a local `legacy_needs_reconciliation` lifecycle record for each previously unaccounted copy. It does not approve deletion; it ensures no old copy is invisible while a named-source or explicit-discard decision is still pending.
- `make worktree-cleanup CONFIRM=published-integration-candidates` removes only clean, registered candidates whose exact HEAD is already reachable from `master` **and** which have a lifecycle record.
- A successful publication records `published`, then removes the temporary copy immediately.
- Integration has no preview mode: a candidate is created only by a close-and-publish operation. If publication becomes uncertain after master may have advanced, it is marked `publication_incomplete` for explicit reconciliation rather than silently removed.
- An ordinary merge or validation failure records `failed_discarded`, preserves the error in the lifecycle record, and removes the temporary copy immediately. A retry always starts a fresh candidate from the exact current inputs.
- A semantic conflict may remain only when the integrator explicitly passes `--keep-paused`. Its lifecycle record is `paused`, and the resolving agent must write the intended combined behaviour and affected tests into the source workstream before `--continue --keep-paused`. The candidate must then publish or be discarded; it may not be left as a dormant investigation.
- Active branch worktrees, remote branches, Docker resources, runtime allocations, validation receipts, and deployment bundles are outside candidate cleanup and remain protected by their own lifecycle rules.

## Integration batches

An integration batch must name every source branch explicitly, freeze each source SHA, preserve a merge boundary per branch, run every branch's declared tests and the complete candidate gate, then publish one tested master update. Batch membership is never inferred from readiness alone.

## Remaining guardrails to retain

- Recheck source/master synchronization after validation and before publication.
- Record semantic conflict decisions and affected tests.
- Keep database migration compatibility and ARM64 validation in the exhaustive gate.
- Do not delete Docker resources through worktree cleanup; use separately scoped tooling.
