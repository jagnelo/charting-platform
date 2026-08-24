# fix/integration-candidate-lifecycle

Created from `feat/workflow-unification` at `803d05acda9af22255f6c4ae7c020829e02e0f8a` because this is a direct refinement of the unmerged workflow interface. The dependent structure is explicitly authorized and documented in `plan.yaml`.

## Intent

The human asked that temporary integration test copies are never forgotten: every one must have an accountable lifecycle, be retained only for a clear active purpose, and otherwise be removed after preserving sufficient failure evidence.

## Current context

Implement the candidate ledger and automatic disposal rules, then run focused helper/documentation validation. Existing historical candidates remain protected until reconciled individually; this change prevents the same accumulation from recurring.

## Validation

- `make validate-focused-integration INTEGRATION_BRANCH=fix/integration-candidate-lifecycle` passed after repairing the inherited Python 3.9 incompatibility in `scripts/integrate.py`.
- `python3 scripts/integrate-set.py --help` passed.
- `make worktree-cleanup-report` now classifies the fourteen historical temporary copies as `unaccounted_legacy_candidate`; none is eligible for automatic removal.

## Published implementation boundary

- Implementation commit `2d813d7b0c980d97d1b477a6e407d421b8c5ead3` is pushed to `origin/fix/integration-candidate-lifecycle` and the worktree was clean immediately afterwards.
- This branch is ready for human review only. It depends on `feat/workflow-unification`, which must reach `master` first; integration remains prohibited until a human explicitly closes this topic.
- The fourteen pre-policy temporary copies remain deliberately retained and explicitly reported as legacy/unaccounted. They require a separate reconciliation decision; this branch prevents new copies from becoming the same kind of orphaned residue.
