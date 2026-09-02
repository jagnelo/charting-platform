# Repository Agent Entry Point

For unattended or orchestrated LLM work on this repository, the automatically
discovered repository guidance is:

- `docs/agent-orchestration.md`

For VS Code sessions, discussion, questions, review, and planning remain
read-only. An unambiguous human request to fix, build, implement, start, or
continue a named topic activates implementation; ambiguous intent must receive
one short confirmation. The human is not expected to repeat these rules or name
the files containing them.

After activation, a control session creates or resumes the exact assigned
`.ai/worktrees/<slug>` path. The implementation session automatically runs the
UV-managed session preflight, completes the branch-owned plan, and creates a
session-local Codex goal with no token budget unless an exact budget was
explicitly authorized by the human. Workstream files and commits are durable
truth; goals are execution aids. The goal stops at `ready_for_human_review`.

Feature sessions must not integrate, promote, deploy, or mutate another
worktree. `master` and `staging` are protected coordinator roles and reject
ordinary feature implementation. A separately authorized workflow-maintenance
exception may operate in the persistent `staging` worktree only for the exact
workflow scope recorded by the human.

That file is the single canonical behavior document for multi-agent/orchestrated
work and tells the worker which durable branch workstream files to read and
update. Supported Codex sessions discover this entry point automatically.

Important boundary: discussing a request in a control session is read-only. Do
not create goals, branches, worktrees, commits, integrations, deployments, or
cleanup actions until activation is clear. Once activated, implementation
belongs in the exact assigned `.ai/worktrees/<slug>` checkout and begins with
the repository's automatic session preflight. The human only supplies intent;
the agent supplies the workflow mechanics.
