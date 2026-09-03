# Worktree, staging, and cleanup lifecycle

## Human authority

- A human explicitly authorizes a topic before an agent creates a branch/worktree or edits it.
- `full_integration` is the normal validation tier; the agent derives the minimum
  local profile from the declared scope and runtime impact. `focused_only` is
  permitted only when that exception is already recorded by the human in the
  workstream.
- Green validation means ready for review, not permission to close.
- The human explicitly closes a topic before it may enter staging. Deployment is a separate request.
- A human may grant standing authorization for CI/CD-only housekeeping. That lets agents finish
  and validate workflow/documentation/test tooling, reconcile stale records, and archive local
  duplicates without asking for each mechanical step. It does not authorize product changes,
  provider behaviour, deployment changes, live-provider calls, remote branch deletion, or any
  action while a required gate is red, flaky, or inconclusive.

## Branch lifecycle

1. Independent work starts from synchronized, green `staging` with
   `make worktree-create BRANCH=<prefix/topic> REQUEST='<human request>'`.
2. Feedback continues on the same unmerged branch. A dependent branch requires explicit human
   authorization naming its parent and records that decision in its workstream.
3. The agent maintains `ops/workstreams/<branch-slug>/`, commits and pushes coherent changes,
   and reports `ready_for_human_review` after the authorized validation tier passes.
4. Human closure changes the record to `ready_for_integration` and adds a PR-equivalent closure
   summary. The summary records the validated implementation SHA; if the final closure checkpoint
   is a docs-only commit, it uses `integration_capture: exact branch HEAD` because a commit cannot
   contain its own hash. `make integrate` then captures and merges that exact pushed SHA into staging.
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
- If master's independent replay is red or unresolved, the recorded `master-degraded.json`
  marker blocks staging bootstrap and new ordinary work. The exact master revision must first
  be repaired or replayed green; agents must never create staging from a known-broken master.
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
- Before `staging` exists, a published local duplicate can be removed with
  `make worktree-archive-pre-staging BRANCH=<name> CONFIRM=<name> REASON='published local duplicate'`.
  The command is deliberately separate from normal close: it requires a clean, stopped,
  synchronized branch whose exact tip is already reachable from synchronized `master`, and it
  retains the remote branch and tracked workstream record. It is not evidence that the topic was
  accepted into staging. Dirty, unpushed, unmerged, root, or out-of-scope worktrees are refused.
- For a dependency chain whose cumulative parent worktree is still active, use
  `make worktree-archive-subsumed BRANCH=<name> PARENT=<parent> CONFIRM=<name> REASON='subsumed by cumulative branch'`.
  This proves the child tip is contained in the named synchronized parent, removes only the child
  checkout/local branch, and retains both the remote child branch and its tracked workstream
  record. It is not an alternative merge path and refuses dirty, running, unpushed, or out-of-scope
  worktrees.
- When a branch's implementation is already present in synchronized `master` but its final
  commit is only its own closure/evidence record, use
  `make worktree-archive-operational-tail BRANCH=<name> CONFIRM=<name> REASON='implementation already integrated; closure record retained remotely'`.
  This is not a merge. It requires a clean, synchronized branch, a clean synchronized `master`,
  stopped managed Compose projects, a `closed` or `superseded` workstream, and proves that every
  unmerged path is under that branch's own `ops/workstreams/<slug>/` directory. It removes only
  the local checkout and local branch with a guarded local-ref deletion; the remote branch and
  tracked record remain the audit trail. Any product, deployment, or unrelated documentation path
  makes the command refuse.
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
