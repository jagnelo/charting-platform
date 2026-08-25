# Worktree, staging, and cleanup lifecycle

## Human authority

- A human explicitly authorizes a topic before an agent creates a branch/worktree or edits it.
- The human explicitly chooses `full_integration` or the restricted `focused_only` path.
- Green validation means ready for review, not permission to close.
- The human explicitly closes a topic before it may enter staging. Deployment is a separate request.

## Branch lifecycle

1. Independent work starts from synchronized, green `staging` with
   `make worktree-create BRANCH=<prefix/topic> REQUEST='<human request>'`.
2. Feedback continues on the same unmerged branch. A dependent branch requires explicit human
   authorization naming its parent and records that decision in its workstream.
3. The agent maintains `ops/workstreams/<branch-slug>/`, commits and pushes coherent changes,
   and reports `ready_for_human_review` after the authorized validation tier passes.
4. Human closure changes the record to `ready_for_integration` and adds a PR-equivalent closure
   summary. `make integrate` then merges the exact pushed SHA into staging.
5. After staging contains the branch, `make worktree-close` may remove only its clean, stopped
   local worktree/branch. The remote branch and merge boundary preserve its history and record.
6. An abandoned, unmerged topic is never removed automatically. Explicit archive confirmation
   requires a recorded `blocked` or `closed` reason and retains the remote branch.

## Staging and master lifecycle

- `staging` is one persistent branch/worktree, not a disposable clone. All accepted branch merges
  go there through `make integrate` or an explicitly named `make integrate-set` batch.
- Source SHAs are frozen before merging. Each source keeps a non-fast-forward merge boundary.
- A conflict aborts the merge and restores the exact starting staging SHA. The conflict is resolved
  once on the source branch with documented combined behaviour and affected tests, then retested.
- GitHub runs the exhaustive gate on the exact pushed staging SHA. A red gate marks staging
  degraded and blocks ordinary integration/promotion; an exact-base remediation is required.
- `make promote-staging COMMIT=<sha> CONFIRM=<sha>` fast-forwards master only to the current green
  staging SHA. Master independently replays the exhaustive gate and remains the deployable line.
- No normal workflow creates `.ai/integration` candidates or retains alternate merge results.

## Storage and cleanup

- `make worktree-overview` reports active worktrees relative to staging, including dirtiness,
  ahead/behind counts, goal/status, running services, and whether closure is safe. During the
  one-time bootstrap, before `staging` exists, it explicitly reports relative to `master` instead;
  it does not pretend the branches are already staging-integrated.
- Closing a worktree never uses force and never removes Docker resources belonging to another
  worktree. Stop only the exact current worktree project before closure.
- `.ai/staging-attempts/` contains small ignored JSON diagnostics, not repository copies.
- Existing `.ai/integration/` directories are historical artifacts from the retired candidate
  workflow. `worktree-cleanup-report`, `worktree-cleanup-reconcile`, and the explicit cleanup
  confirmation exist only to account for those old copies before removal. New integration must
  never write there.
- Runtime allocations, validation receipts, deployment bundles, active branch worktrees, remote
  branches, and Docker data have separate lifecycles and are never swept by integration cleanup.

## CI and deployment architecture

- Work branches run deterministic application checks plus their declared tests.
- Staging and master run the exhaustive architecture-neutral gate on GitHub Linux runners.
- Normal CI must not install QEMU or build ARM images.
- Target architecture belongs to the explicit deployment workflow. RPi operations require
  `RPI_DOCKER_PLATFORM=linux/arm/v7` or `linux/arm64`, verified by preflight against the actual Pi.
