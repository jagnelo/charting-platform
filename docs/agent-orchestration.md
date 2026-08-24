# Agent Orchestration

This is the **single canonical entry point** for unattended or multi-agent development on this repository.

If an orchestrator, agent runner, or human operator needs to tell an LLM what to do, it should point the LLM to **this file first**.

This file is intentionally the top-level behavior document. An LLM should not need a second initial instruction file. This document tells it:
- what tooling model to assume
- which state files to read
- which files it must update before stopping
- how validation must work
- how handoffs between models must work

Use this setup for overnight or unattended development with multiple LLM coding agents.

## Recommended orchestrator

Use **LangGraph** as the orchestrator.

Why this one:
- good fit for long-running, stateful agent workflows
- easy to implement in Python
- supports explicit control over handoffs, validation, and retries
- flexible enough to switch between Codex and Claude as workers

Do **not** use the VS Code extensions as the automation surface.

Use:
- Codex CLI
- Claude Code CLI

If stronger crash-resume guarantees are needed later, add **Temporal** under the LangGraph workflow. Do not start there.

## Single entry-point rule

The orchestrator should point every worker to exactly one initial file:

- `docs/agent-orchestration.md`

That is the only initial documentation path the orchestrator needs to inject.

From this file, the worker must then read the live state/memory files under `ops/`.

For a checked-out feature/fix/chore/docs/test branch, the worker must also read
the branch-owned durable record at `ops/workstreams/<branch-slug>/`:

- `plan.yaml` is the scope and acceptance contract;
- `handoff.md` is the current human/agent handoff;
- `validation.jsonl` is append-only command/result evidence.

The global `ops/tasks.yaml`, `ops/handoff.md`, `ops/state.json`, and
`ops/run-report.md` remain legacy integration evidence. A branch must not edit
another branch's workstream directory; proposed shared-document changes belong
in its own record until an integration agent reconciles them.

So the correct model is:
- **single initial entry point**: this file
- **live operational state**: global `ops/*` plus the current branch's
  `ops/workstreams/<branch-slug>/` record

This avoids making the orchestrator juggle multiple peer instruction files.

## Human intent boundary (non-negotiable)

The human developer owns **whether a topic may start, whether it is accepted,
and whether it may be deployed**. Agents own the mechanics once that intent is
explicit. Do not infer authorization from an old task, a TODO, a failing test,
or an opportunity noticed during other work.

- Before creating a worktree or changing any product/workflow code, obtain an
  explicit human request to address that named topic. Create the worktree with
  `make worktree-create BRANCH=<prefix/topic> REQUEST='<human request>'`; this
  records the request in its schema-2 workstream plan and handoff.
- Work autonomously inside that authorized branch: plan, implement, test,
  document, commit, push, and make the result available for human review.
- Before deciding the final verification path, ask the human whether to use the
  default `full_integration` gate or an explicitly approved `focused_only`
  documentation/workflow-helper gate. Record the exact answer in
  `human_validation_authorization`. Do not infer that a change is “small”.
  `focused_only` is mechanically limited to documentation/workflow-helper paths
  and runs its own focused gate; all other changes require the full gate.
- Green validation means `ready_for_human_review`; it is never implicit merge,
  close, or deployment permission. Preserve the branch for feedback iterations.
- Only after an explicit human statement such as “close this topic” may an
  agent record the exact closure instruction in `human_closure_authorization`,
  set `status: ready_for_integration`, and write `closure_summary` with the
  delivered scope, exact source SHA, validation evidence, migration/deployment
  impact, conflict decisions, and remaining gaps. That committed branch record
  is the PR-equivalent narrative preserved by the non-fast-forward merge. Only
  then may it invoke `make integrate`.
- Only after a separate explicit human deployment request may an agent invoke
  deployment tooling. A closure request does not authorize deployment.

This is a written contract, not a suggestion. Tooling rejects new worktrees
without a recorded request and rejects integration unless the recorded closure
authorization, validation decision, and status are present. It cannot prove who
typed prose, so an agent must quote or faithfully record the human instruction
and never invent it.

This section supersedes older text in this document that refers to mandatory
global `ops/handoff.md`, `ops/state.json`, or `ops/run-report.md` updates for
feature workers. Those files are historical integration evidence. The current
branch's workstream is the durable coordination record.

## Integration-candidate lifecycle (non-negotiable)

An integration candidate is one **temporary combined test copy** made from one
exact `master` commit and one exact source-branch commit. It is not a second
branch, not an alternate version of `master`, and never a durable source of
truth. The named source branch/workstream and the resulting merge commit on
`master` are the only source changes an agent may rely on.

1. Use only `make integrate` or `make integrate-set`; never create ad-hoc
   candidates. The helper identity includes the frozen master SHA and every
   frozen source SHA, so superseded inputs cannot reuse a previous test copy.
2. The helper writes a generated local lifecycle record in
   `.ai/integration/ledger/` before it creates the copy. It records inputs,
   state, error/conflict paths, and the final disposition.
3. On success, publish the tested merge commit, write `published` to the
   lifecycle record, and immediately remove the copy.
4. On an ordinary merge or validation failure, write
   `failed_discarded`, keep the error evidence in the lifecycle record, and
   immediately remove the copy. A later retry starts fresh from the then-exact
   inputs; it never reuses a failed copy.
5. Retention is exceptional: pass `--keep-paused` only for an active semantic
   conflict resolution. Before continuing it, record the intended combined
   behaviour and affected tests in the source workstream. A paused candidate
   must either publish or be discarded; it cannot become a forgotten local
   investigation.
6. Run `make worktree-cleanup-report` before storage cleanup. It flags old
   copies that predate the lifecycle rule as `unaccounted_legacy_candidate`.
   Run `make worktree-cleanup-reconcile` to make each one an explicit local
   `legacy_needs_reconciliation` record. Do not delete those automatically:
   first reconcile them to a named source, a published merge, or an explicitly
   documented discard decision.

This rule prevents a pile of unnamed historical test copies while retaining
enough failure evidence to diagnose a real integration problem.

## Workflow Python runtime

Workflow helpers are part of the application toolchain. They must run through
the backend's UV-managed interpreter, whose declared requirement is Python
3.12 or newer; macOS's system `python3` is never the supported runtime. Use
the Make targets, or explicitly use:

```bash
uv run --project backend python scripts/<helper>.py
```

When adding a branch test, use that same command form. Do not make a helper
silently compatible with an older system Python instead of enforcing the
repository's declared runtime.

## Install / setup order

1. Install and verify **Codex CLI**
2. Install and verify **Claude Code CLI**
3. Install and verify **LangGraph** in a dedicated Python orchestration environment
4. Ensure the project can be fully controlled from terminal commands:
   - docker compose (with the repo's branch-scoped `COMPOSE_PROJECT_NAME` convention)
   - alembic
   - backend tests
   - frontend tests/build
   - Playwright
5. Use the files in `ops/` as the only durable handoff memory between agents

## Worker bootstrap sequence

After being pointed to this file, every worker must do the following before making any code changes:

1. Read `docs/agent-orchestration.md`
2. Determine whether the checkout is the root `master` integration checkout or a feature worktree
3. In a feature worktree, read its `ops/workstreams/<branch-slug>/plan.yaml`, `handoff.md`, and `validation.jsonl`; confirm the recorded human request before acting
4. In the root `master` checkout, read the relevant global `ops/*` integration evidence before integration or deployment work
5. Optionally consult global `ops/*` legacy history when it materially helps a feature worker, but do not edit it as routine branch coordination
6. Only then begin authorized implementation/validation work

This means the orchestrator only needs to say:

> Read `docs/agent-orchestration.md` and obey it.

Everything else flows from this file.

## Non-negotiable rule

**Session continuity must come from repository files, not from chat/session memory.**

**Workers must assume that their usable session budget can disappear far earlier than the nominal session limit.**

This means:
- do not assume a long uninterrupted working window
- do not assume a 5h session will actually remain usable for anything close to 5h
- do not leave important context only in transient model memory
- do not postpone handoff writing until the very end of a session

If a worker waits until the final moments of its remaining budget to externalize context, that worker has failed the contract.

Every worker must read `docs/agent-orchestration.md`. A feature worker must
read and maintain only its branch-owned workstream record; the `master`
integration worker reads the relevant global `ops/*` integration evidence.

Every feature/fix/chore/docs/test worker must update its own
`ops/workstreams/<branch-slug>/handoff.md` and append its own
`validation.jsonl`. The old global files are legacy integration evidence and
must not become a cross-branch coordination hotspot.

If a worker stops without updating those files, it has failed the handoff contract.

## Worker model

Treat Codex and Claude as interchangeable workers.

The orchestrator must:
- choose the current worker
- give it the current task and repo rules
- let it work
- stop it before session exhaustion
- force a structured handoff
- switch to the next available worker

The worker must behave as if interruption can happen at any time.

## Stop-before-expiry rule

The orchestrator must not let a worker run until hard exhaustion.

Use a **soft stop**:
- stop at **4h 30m** of a 5h session, even if work is still in progress
- or stop earlier if token/rate telemetry indicates the session is close to exhaustion

However, a worker must not interpret this as permission to delay checkpointing until the soft stop.

Because practical exhaustion may happen much earlier, the worker must actively preserve continuity during the session, not only at the end.

At soft stop, the worker must:
- finish the current small action if possible
- update `ops/handoff.md`
- update `ops/state.json`
- append to `ops/run-report.md`
- record exact next step
- stop cleanly

This is required so the next worker does not need to guess.

If the orchestrator can observe token/session telemetry, it should stop even earlier when risk is high.

If the orchestrator cannot observe token/session telemetry, then the **4h 30m soft stop is mandatory**.

## Frequent checkpoint rule

This rule is mandatory.

Workers must not rely on a single final handoff.

They must write or refresh handoff state during the session whenever meaningful progress occurs, especially after:
- understanding/scoping the task
- choosing an implementation direction
- completing a substantial code edit
- discovering a blocker
- running tests
- validating frontend behavior
- finding errors in browser console or backend logs
- determining the next concrete action

Minimum expectation:
- if meaningful work has happened, refresh handoff/state before moving into a new risky phase
- if a session is long-running, refresh handoff/state periodically even without explicit interruption

The purpose is to make sudden session loss survivable.

## Changeset commit and push hygiene

A completed changeset context must not be carried into the next context as an
uncommitted worktree. This is a repository-integrity rule, not an optional
end-of-session convenience:

### Required changeset-closure protocol

Treat each meaningful implementation or documentation unit as a named
`changeset context`. Before starting another context, close the current one in
this order:

1. State the context's scope and the files it owns in the handoff. If a file is
   shared with another unfinished context, stop and split or finish that work;
   do not silently carry mixed edits forward.
2. Run the focused validation for the context, then inspect `git status
   --short --branch`, `git diff --check`, `git diff --stat`, and the complete
   unstaged diff. Resolve or explicitly record every failure before staging.
3. Stage only the files belonging to this context. Inspect
   `git diff --cached --name-status` and `git diff --cached` before committing;
   never use a broad add that can absorb another context's work without
   reviewing it.
4. Create one self-contained conventional commit for the completed context.
   A context is not complete merely because its tests pass while its changes
   remain unstaged or uncommitted.
5. Push that commit immediately. Verify the local commit hash and
   `origin/<branch>` hash are identical and verify a clean worktree.
6. Only after the implementation commit is synchronized, update `ops/handoff.md`,
   `ops/state.json`, and `ops/run-report.md` with the exact commit hash,
   validation evidence, remaining gaps, acceptance flexibility, and the next
   context. Commit and push this operational record as a separate small
   checkpoint, then verify clean status and matching hashes again. The state
   files cannot contain the final SHA of the commit that contains them; record
   the last known pre-record checkpoint and explicitly state that the enclosing
   commit is verified externally with `git rev-parse`.
7. Begin the next context only after the second verification. The first command
   for a new context must confirm the clean, synchronized boundary; if it does
   not, return to closure rather than adding more work.

- Before changing implementation context, inspect `git status --short --branch`,
  `git diff --check`, and the staged/unstaged diff.
- Once the current context is complete and its focused validation passes, make a
  self-contained commit with a conventional message. Keep unrelated or still-
  experimental edits out of that commit; either finish them in the same context
  or record them explicitly in the handoff before starting a new one.
- Push the commit immediately after the checkpoint whenever the remote is
  available. Verify that `HEAD` and the remote branch resolve to the same hash
  and that the worktree is clean.
- Refresh `ops/handoff.md`, `ops/state.json`, and `ops/run-report.md` with the
  commit/push result, validation evidence, and the exact next context. Do not
  leave a stale statement that a commit or push is pending after it succeeds.
- At minimum, perform this checkpoint after each substantial feature/fix,
  before a risky or long-running validation, before handoff, and before moving
  to a different changeset context. A dirty tree is acceptable only when the
  current context is explicitly still in progress and the handoff identifies
  every outstanding file and reason.
- If a context is intentionally still in progress, record its context name,
  outstanding files, current validation, and exact next action in the handoff;
  do not start a different context until that context is closed. An unlabelled
  dirty tree is always treated as an operational defect.
- “No changes” is also a closure result: record the no-op audit and leave the
   tree clean instead of creating placeholder edits or carrying a stale dirty
   state forward.
- Never chase a self-referential state hash by making another commit solely to
  update `last_commit` to the hash of the commit that contains that update. The
  recorded prior checkpoint plus the post-push `HEAD`/origin comparison is the
  durable, reproducible proof of closure.

### `.git/index.lock` recovery

If Git reports `Unable to create .../.git/index.lock: Operation not permitted`,
first verify that this is not a real repository problem:

1. Check ownership and writability of `.git`, `.git/index`, and `.git/refs`, and
   check for an actual stale lock. Never delete a lock blindly while another
   Git process may be active.
2. Retry the same Git operation sequentially (never run `git add` and `git
   commit` in parallel). Do not use destructive index resets or broad cleanup.
3. If repository permissions are normal and the failure is the Codex sandbox
   boundary, rerun the required `git add`, `git commit`, and `git push` through
   the permitted elevated Git execution boundary, requesting approval with a
   narrow Git prefix when needed. This is the approved workaround for the
   sandbox restriction; do not report the work as blocked merely because the
   unprivileged attempt failed.
4. Re-run `git status --short --branch`, `git diff --check`, and compare
   `git rev-parse HEAD` with `git rev-parse origin/<branch>` after the operation.
   Record any remaining external failure (authentication, network, remote hook,
   or actual filesystem problem) in the handoff and keep the current changeset
   context explicit.

The successful elevated retry is the normal resolution for this sandbox boundary: once the
repository is confirmed healthy, use the permitted `rtk git add`/`rtk git commit` path rather than
leaving completed work uncommitted. A failed unprivileged attempt is setup evidence, not a product
defect and not a reason to block the active goal.

### Codex execution rule

The worker is responsible for performing this recovery; it must not hand a normal
commit or push back to the user merely because the default sandbox cannot write
`.git`. After the read-only checks above, request the narrow elevated Git boundary
and run the operation itself, sequentially:

```text
rtk git add <reviewed-context-files>
rtk git commit -m "<conventional message>"
rtk git push origin <branch>
```

The worker must verify the result with `git status --short --branch`, `git
rev-parse HEAD`, and `git rev-parse origin/<branch>`. If the elevated push is
rejected by the environment's private-repository egress safeguard, this is a
transport-only hold: keep the clean local commit, record the exact range and
command in the operational files, and continue independent work. Do not retry
through an indirect shell/API/plugin, do not leave files uncommitted, and do not
mark the product goal blocked. A later continuation may retry the same exact
payload through the approved elevated Git path after explicit authorization.

The worker must not move on to a new changeset while a completed context is
waiting for a normal terminal commit. If the elevated retry genuinely fails,
preserve a precise handoff and make the next action the first priority of the
next worker.

Git handling is never a reason to stop the product goal. A worker that has
completed and validated a context owns the complete recovery: perform the
sequential elevated `add`/`commit`/`push` retry in the same continuation, keep
the resulting commits isolated, and update the operational record immediately.
Only an actual repository, authentication, or remote-hook failure may require
an external decision; a sandbox index-lock denial or private-repository egress
refusal is recorded as transport state and must not be represented as a goal
blocker. The user must not be handed an instruction to finish ordinary Git
staging or committing that the worker can perform through the approved path.

### External push-egress safeguard

An elevated `git push` can be rejected before Git starts when the execution
environment detects a newly-created private-repository payload. This is not an
index, Git, authentication, or repository-integrity failure. Do not retry the
same payload through an indirect command, alternate shell, API, or plugin.

When this occurs:

1. Verify the repository is clean and record `HEAD`, `origin/<branch>`, the
   exact commit range, remote, branch, and the full push command.
2. Keep every completed changeset as a separate local commit; never amend,
   squash, reset, stash, or create a metadata-only loop to hide the ahead
   state.
3. Record `committed_locally_pending_push` and the rejection in the operational
   files. This is a transport hold, not a product blocker, so independently
   scoped contexts may continue from the clean boundary.
4. Retry only through the same approved elevated Git path after the user has
   explicitly authorized that exact current payload (remote, branch, and commit
   range). If authorization is unavailable, leave the clean local commits in
   place and report the precise command needed; do not claim synchronization.
5. Once accepted, verify `git rev-parse HEAD` equals
   `git rev-parse origin/<branch>` and then close the operational record in a
   separate commit. The goal must not be marked blocked solely for this
   safeguard.

For a later retry, the user authorization must identify the exact export rather
than merely saying “push it”. Use this shape in the approval request and wait
for trusted acceptance: `I authorize pushing commit <HEAD> (range
<origin_sha>..<HEAD>) to <remote>/<branch>`. If the execution boundary still
reports that trusted authorization is unavailable, do not retry or change
transport; record the rejection and continue from the clean local boundary.

### No-loop rule for push authorization

The worker must attempt the exact elevated push once for the completed context,
including the full remote, branch, and commit range in the approval request. If
the execution boundary rejects that request before Git starts, a second attempt
is allowed only when the tool reports newly available trusted authorization for
the same exact payload. Repeating the command, changing shells, wrapping it in
another command, or trying a different transport cannot grant that authorization
and is prohibited. The worker must immediately:

1. verify the worktree is clean and the local commit is intact;
2. record `committed_locally_pending_push`, the exact command, range, and
   rejection category in `ops/handoff.md`, `ops/state.json`, and the run report;
3. continue the next independently scoped implementation context from the clean
   local boundary; and
4. retry the same push only when a later continuation presents an approved
   exact-payload authorization.

Natural-language insistence that a push should succeed does not override the
execution boundary. This is an operational transport state, not a product
failure, and it must never be represented as a blocked goal or used to justify
leaving completed work unstaged or uncommitted.

### User-facing transport rule

When the exact elevated push is rejected by the private-origin egress safeguard,
the worker must report the situation plainly as:

- the repository is healthy;
- the changeset is committed locally and the worktree is clean;
- the remote is behind because export authorization was rejected before Git; and
- the product goal is continuing from the clean local commit boundary.

The worker must not describe this as “Git is broken”, “the goal is blocked”, or
ask the user to run ordinary `git add`, `git commit`, or `git push` commands.
Those actions remain the worker's responsibility. The only permitted retry is
the same exact elevated command for the same remote, branch, and commit range
when the execution environment reports newly accepted trusted authorization.
Until then, independently scoped implementation contexts may be validated and
committed locally, with each transport hold recorded in the operational files.

### Context-transition guard

The first action after selecting any new context is a repository-boundary check,
before opening or editing implementation files:

```text
git status --short --branch
git diff --check
git rev-parse HEAD
git rev-parse origin/<branch>
```

The expected result is an empty worktree and matching local/remote commit hashes.
If any file is dirty, or the hashes differ, the worker must not begin the new
context. It must instead classify every changed path as belonging to the prior
context, the proposed context, or an unrelated pre-existing change; finish or
handoff the prior context; and run the changeset-closure protocol above. No
blanket `git add -A`, stash, reset, discard, or broad cleanup may be used to make
the boundary appear clean. A deliberately unfinished context must remain named
in `ops/handoff.md` with its owned files and exact next action, and the next
worker must resume that context rather than selecting a different one.

### Context ledger and completion boundary

The active changeset context is a ledger item, not merely a label in chat. At
the moment a context is selected, the worker must record its name, intent, and
owned paths in `ops/handoff.md` (and, when it is a substantial unit, in
`ops/tasks.yaml`). Every subsequent edit must belong to that ledger item. A
file that is shared by two contexts must be finished and committed in the
first context, or the work must be split into independently reviewable files;
it must not be carried forward implicitly.

The context remains **in progress** until its implementation and focused
validation are complete. Passing tests, a working browser session, or a
plausible diff does not make it complete while any owned path is unstaged,
uncommitted, or unpushed. Before selecting, discussing, or implementing the
next feature/repair theme, the worker must either:

1. close the current context through the full changeset-closure protocol above;
   or
2. explicitly hand it off as unfinished, with every dirty path, the reason it
   remains dirty, the last validation result, and one exact next action. The
   next worker must resume that same context first.

An unlabelled dirty tree, a stale `git_ready_to_commit` flag, or a handoff that
says a commit/push is pending after it succeeded is an operational defect.
The repair is to stop new implementation, classify every changed path, close
the prior context with scoped staging, and refresh the operational record.
Never use a broad add, stash, reset, discard, or metadata-only commit loop to
hide accumulated work. This rule exists specifically to preserve fine-grained,
self-contained, logically reviewable commits across long-running goals.

This guard applies even when the previous tests already passed: passing tests do
not make an unstaged or unpushed changeset complete. When a context is complete,
commit and push it before starting another feature or repair theme. If staging,
commit, or push is denied only by the Codex filesystem boundary, follow the
`.git/index.lock` recovery procedure above immediately and record the result;
do not accumulate additional work while waiting for Git recovery.

### No-accumulation synchronization exception

Remote synchronization is part of changeset closure, but a remote or execution-environment
failure must never be allowed to turn a completed context back into an uncommitted context:

1. If implementation and focused validation are complete, commit the context locally even when
   `git push` is unavailable. A clean local commit is preferable to leaving completed files
   unstaged or uncommitted.
2. Mark the context `committed_locally_pending_push` in the handoff/state, including the exact
   commit, branch, remote hash, push command, and failure category. Do not describe it as
   synchronized.
3. Do not leave the context dirty, but do not block the goal solely because transport is
   unavailable: after the context is committed locally, a clean, separately committed next
   context may proceed while the pending push is retried through the approved elevated Git path.
   Never mix the pending context with the next one, and preserve exact local/remote hashes in the
   handoff. A product/implementation push rejection is an operational transport hold, not a
   product failure or a reason to mark the goal blocked.
4. If a worker discovers a dirty tree from an earlier context, stop immediately and inventory it:
   run `git status --short`, `git diff --name-status`, and `git diff --cached --name-status`, then
   map every path to its owning context. Finish and commit each self-contained context separately,
   or explicitly hand it off as unfinished. Never use `git add -A`, a stash, reset, discard, or a
   metadata-only commit to make the boundary appear clean.
5. Once pushing is available, push locally committed contexts in dependency order, verify each
   hash against its remote, then close the separate operational record. The matching-hash check
   remains required for synchronization and handoff, but it is not a prerequisite for starting
   independently scoped work when every preceding context is clean and committed.

This prevents both accumulation modes: completed work left uncommitted while unrelated work is
added, and multiple completed contexts silently mixed into one later commit. A dirty tree is an
active-context defect; an ahead-of-remote clean tree is a synchronization hold, not permission to
continue feature work.

### Browser-stack freshness recovery

Browser acceptance must execute against the code that was just validated and committed, not merely
against a container that happens to be healthy. A green service health check does not prove that its
frontend bundle is current. When a browser test cannot see a newly added route, control, label, or
factory option:

1. Treat the first failure as an environment/bundle diagnosis, preserve the unchanged browser
   oracle, and inspect the served `index.html` asset name.
2. Compare the running frontend container image ID and creation time with the current branch image.
   Do not weaken, skip, or reclassify the test while this comparison is unresolved.
3. Rebuild the branch-scoped stack with the repository target, which uses
   `docker compose up -d --build --force-recreate --wait`, or force-recreate only the identified
   branch-scoped service when the image is already current. Never stop or recreate an unrelated
   compose project.
4. Verify the served asset changed to the freshly built asset, then rerun the same focused test and
   the nearest regression slice. Record the stale-container diagnosis, rebuild/recreate command,
   served-asset verification, and both results in the active handoff and project TODO entry.

This procedure is a fix for a test-environment defect, not a product acceptance relaxation. The
`--force-recreate` flag is intentionally part of `make test-stack-up` so future branch validation
does not silently reuse an older frontend container after a successful build.

#### Operational-record egress exception

The freeze above applies to implementation commits, not to an already-committed operational record
whose push is independently rejected by an external egress safeguard. If all implementation commits
from the previous context are already synchronized, the worktree is clean, and the only local
ahead commit is a clearly labelled `docs(ops)` checkpoint, the worker may open the next implementation
context. It must:

- keep the operational checkpoint as a separate commit and never amend feature files into it;
- record the exact pending SHA, remote SHA, and push failure in `ops/handoff.md`/`ops/state.json`;
- attempt the checkpoint push again through the approved elevated Git path, without indirect
  workarounds;
- commit the next implementation context separately, attempt its push, and continue only with
  clean, independently scoped commits if that implementation push is rejected. Never accumulate
  dirty files or silently combine contexts.

This exception exists because an operational-only egress refusal has no effect on product source
integrity once the prior implementation commit is synchronized. It prevents a metadata transport
failure from blocking independent goal work while preserving fine-grained implementation commits.

### Mandatory context-closure checklist

Before writing “next context” anywhere, record a short closure entry containing:

- context name and owned paths;
- focused validation and any broader gates run;
- staged path review and commit hash;
- push result (`synchronized`, `committed_locally_pending_push`, or a precise failure);
- `HEAD` and `origin/<branch>` hashes plus worktree status;
- the one permitted next action.

If any field is missing, the context is not closed and the worker must not begin another feature
theme. This applies even when all tests pass and the only remaining issue is external push access.

## Worker self-preservation rule

Every worker must self-monitor for signs that its current session or token budget may be nearing exhaustion.

If the worker believes exhaustion risk is rising, it must immediately shift from implementation mode into preservation mode:
- stop starting new substantial work
- record what was completed
- record what remains
- record exact next step
- record validation state
- update `ops/handoff.md`
- update `ops/state.json`
- append to `ops/run-report.md`

The worker must prefer leaving a clean handoff over squeezing in one more edit.

In other words:
- final budget should be spent on continuity, not ambition
- when in doubt, checkpoint first

## Orchestrator checkpoint rule

The orchestrator must not assume the worker will always stop gracefully on its own.

It should force periodic continuity opportunities, such as:
- heartbeat prompts
- checkpoint prompts
- max-turn or bounded-run segments
- forced handoff requests before long validations or risky implementation phases

Recommended behavior:
- request/check for a checkpoint every 10-20 minutes of active work, or after a meaningful task phase
- if the worker appears close to exhaustion, force handoff mode immediately

The combination required for reliability is:
- worker self-awareness
- worker frequent checkpointing
- orchestrator-enforced fallback checkpoints

## Definition of done for each task

A task is not done just because code was written.

It is only done when:
- code changes are complete
- relevant tests were run
- relevant frontend flows were checked when UI was affected
- browser console and backend logs were checked when applicable
- handoff/state/report files were updated

## Validation requirements

When relevant, the orchestrator must be able to run:
- Docker infra start/stop
- migrations
- backend unit/integration tests
- frontend build/tests
- Playwright flows
- browser console capture
- backend log capture

## Handoff contract

Every handoff must include:
- current task
- completed work
- pending work
- exact next step
- files touched
- tests run
- validation status
- errors/logs seen
- assumptions made
- whether the tree is ready to commit

This contract applies both:
- at final handoff
- at intermediate checkpoints

## Prompting rule for any LLM

When launching a worker, always provide:
- the task to work on
- the instruction to read `docs/agent-orchestration.md` first
- the instruction to obey the stop-before-expiry rule
- the instruction to obey the frequent checkpoint rule
- the instruction to prioritize continuity if exhaustion risk is suspected
- the instruction to update handoff/state/report before stopping
- the validation requirements for the current task

The orchestrator does **not** need to separately enumerate the `ops/*` files in its initial prompt if it already points the worker to this file, because this file already instructs the worker to load them.

## Recommended orchestrator prompt shape

Use a short launch instruction shaped like this:

> You are the current worker on this repository. Read `docs/agent-orchestration.md` first and obey it fully. Then continue the active task from the repository handoff/state files. Before stopping, update the required handoff/state/report files and record exact next steps.

In practice, the orchestrator should prefer a slightly expanded version:

> You are the current worker on this repository. Read `docs/agent-orchestration.md` first and obey it fully. Then continue the active task from the repository handoff/state files. Assume your usable session budget may end much earlier than expected. Checkpoint frequently. If exhaustion risk increases, stop new implementation work and preserve continuity first. Before stopping, update the required handoff/state/report files and record exact next steps.

That is enough as the generic prompt wrapper.

## Root repository discovery

To make this repository easier for many coding agents to understand, the repo should also expose a root-level `AGENTS.md` that points to this file.

That root file should not compete with this one. It should simply redirect agents here.

## Minimal target architecture

- **LangGraph**: workflow/orchestration
- **Codex CLI / Claude Code CLI**: workers
- **Repo files under `ops/`**: durable memory
- **Terminal tooling**: tests, docker, alembic, Playwright, logs

## Later upgrade path

If the overnight system proves useful and needs stronger recovery:
- keep LangGraph
- add Temporal for durable workflow execution

Do not delay initial setup for this.
