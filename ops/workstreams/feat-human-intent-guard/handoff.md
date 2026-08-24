# feat/human-intent-guard

Created from `master` at `cb475db01d412c201c2be2b1bfaeea3387bc3860`.

## Authorization

The human explicitly authorized this workflow refinement on 2026-08-24. They did not authorize integration or deployment of this branch; keep it available for review when implementation is ready.

The human also explicitly authorized the focused-only verification tier for this
documentation/workflow-helper branch. It may not be repurposed for application,
dependency, migration, Compose, CI, or product-test changes.

## Current state

Ready for human review. The schema-2 contract now records separate human intent,
validation-tier, and closure decisions. New worktree creation requires a
recorded request. Integration rejects workstreams without explicit closure,
closure summary, and validation authorization; focused-only integration is
limited to documentation/workflow-helper paths. Schema-1 records remain valid
legacy evidence.

Focused verification passed: workstream validation (all 22 records and this
record), Python syntax compilation for changed helpers, branch-declared tests,
and `git diff --check`. No full integration gate was run because the human
explicitly approved the focused-only tier for this workflow-only change.

Next human decision: try/review the workflow, then either provide feedback on
this branch or explicitly authorize closure. Do not integrate or deploy until
that later authorization is recorded.
