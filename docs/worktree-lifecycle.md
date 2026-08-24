# Worktree lifecycle and cleanup policy

## Human controls

- A human authorizes work, chooses validation scope where required, and explicitly closes a topic.
- Agents may plan, implement, test, and report readiness only within that authorization.
- Integration/deployment never follows from green tests alone.

## Local storage lifecycle

- A merged, clean, stopped branch worktree is closed with `make worktree-close`.
- An unmerged abandoned branch is never force-removed automatically; archive it only after explicit human approval and a recorded reason.
- `make worktree-cleanup-report` is read-only. It classifies integration candidates individually.
- `make worktree-cleanup CONFIRM=published-integration-candidates` removes only clean, registered detached candidates whose exact HEAD is already reachable from `master`.
- Failed/conflicted/unpublished candidates, active branch worktrees, remote branches, Docker resources, runtime allocations, validation receipts, and deployment bundles are retained.

## Integration batches

An integration batch must name every source branch explicitly, freeze each source SHA, preserve a merge boundary per branch, run every branch's declared tests and the complete candidate gate, then publish one tested master update. Batch membership is never inferred from readiness alone.

## Remaining guardrails to retain

- Recheck source/master synchronization after validation and before publication.
- Record semantic conflict decisions and affected tests.
- Keep database migration compatibility and ARM64 validation in the exhaustive gate.
- Do not delete Docker resources through worktree cleanup; use separately scoped tooling.
