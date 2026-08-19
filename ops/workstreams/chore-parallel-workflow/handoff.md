# Parallel worktree and RPi deployment workflow

Implementation starts from the locally promoted TC2000 boundary
`8a9c26a872ce02e69817b119885a0dfe0aedcb0d`. The TC2000 browser gate currently
has documented failures; this workstream must not describe that baseline as
fully green until the independent replay is clean.

The deployment path is deliberately manual. No target, credential, image
bundle, or secret belongs in this branch or in a validation receipt.

Implementation commit: `b23f8a110af05646b9132d1839fb5d38695c20eb` (pushed to
`origin/chore/parallel-workflow`). Focused validation passed: Python compile,
Ruff on changed Python, locked dependency check, RPi Compose config, workstream
validation, provider/runtime tests (3/3 with the repository-wide coverage
threshold disabled for the focused invocation), frontend type-check, and
production build. Full integration remains intentionally red until the TC2000
browser baseline gaps are resolved.
