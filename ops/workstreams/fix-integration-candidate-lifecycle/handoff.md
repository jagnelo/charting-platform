# fix/integration-candidate-lifecycle

Created from `feat/workflow-unification` at `803d05acda9af22255f6c4ae7c020829e02e0f8a` because this is a direct refinement of the unmerged workflow interface. The dependent structure is explicitly authorized and documented in `plan.yaml`.

## Intent

The human asked that temporary integration test copies are never forgotten: every one must have an accountable lifecycle, be retained only for a clear active purpose, and otherwise be removed after preserving sufficient failure evidence.

## Current context

Implement the candidate ledger and automatic disposal rules, then run focused helper/documentation validation. Existing historical candidates remain protected until reconciled individually; this change prevents the same accumulation from recurring.

## Validation

- The workflow runtime was audited after an initial incorrect system-Python compatibility attempt. The implementation enforces the repository's declared UV-managed Python 3.12+ runtime; `datetime.UTC` remains a valid required API.
- `make validate-focused-integration INTEGRATION_BRANCH=fix/integration-candidate-lifecycle`, UV-managed CLI checks, Ruff check, and Ruff format check all passed after enforcing that runtime.
- The non-destructive reconciliation command was run after the lifecycle change: all fourteen now have individual local ledger records with state `legacy_needs_reconciliation`. They remain retained; the record makes their status and deletion precondition visible to future agents.

## Published implementation boundary

- Implementation commit `2d813d7b0c980d97d1b477a6e407d421b8c5ead3` is pushed to `origin/fix/integration-candidate-lifecycle` and the worktree was clean immediately afterwards.
- This branch is ready for human review only. It depends on `feat/workflow-unification`, which must reach `master` first; integration remains prohibited until a human explicitly closes this topic.
- The fourteen pre-policy temporary copies remain deliberately retained as individually recorded legacy items. They require a separate reconciliation decision; this branch prevents new copies from becoming the same kind of orphaned residue.

## Follow-up correction

- The initial implementation briefly attempted to make the helper run on macOS system Python. That was corrected before closure: all workflow helper Make targets now use `uv run --project backend python`, which resolves to the repository's declared Python 3.12.4 environment.
- The reconciliation report now excludes its own `ledger/` directory and is valid JSON. A direct parse verified exactly fourteen candidates, each with `legacy_needs_reconciliation`.
