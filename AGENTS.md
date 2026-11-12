# Repository Agent Entry Point

For unattended or orchestrated LLM work on this repository, the automatically
discovered repository guidance is:

- `docs/agent-orchestration.md`

For interactive sessions (desktop app, VS Code, or terminal; any supported agent runtime),
discussion, questions, review, and planning remain read-only. An unambiguous
human request to fix, build, implement, start, or continue a named topic
activates implementation; ambiguous intent must receive one short confirmation.
The human is not expected to repeat these rules or name the files containing
them.

The default operating mode is one orchestrator session per work context: a
strong-model chat with the human present that delegates bounded pieces to
cheaper in-session subagents (in parallel across worktrees where independent)
and itself verifies, commits, merges, reconciles and validates the combined
result through staging. A new work context gets a new orchestrator session
under the same rules. See `docs/agent-orchestration.md` § Orchestrator and
subagents.

After activation, a control session creates or resumes the exact assigned
`.ai/worktrees/<slug>` path. The implementation session automatically runs the
UV-managed session preflight, completes the branch-owned plan, and creates a
session-local goal (the runtime's own goal/continuation mechanism) with no
budget unless an exact budget was explicitly authorized by the human. Workstream
files and commits are durable truth; goals are execution aids. The goal stops
at `ready_for_human_review`. In the default orchestrator mode the goal is optional while
the human is present.

Feature sessions and subagents must not integrate, promote, deploy, or mutate
another worktree; only a context's orchestrator acts as its staging
coordinator. `master` and `staging` are protected coordinator roles and reject
ordinary feature implementation. A separately authorized workflow-maintenance
exception may operate in the persistent `staging` worktree only for the exact
workflow scope recorded by the human.

That file is the single canonical behavior document for multi-agent/orchestrated
work and tells the worker which durable branch workstream files to read and
update. Supported agent runtimes (Codex, Claude Code, and others) discover this
entry point automatically; Claude Code does so through the root `CLAUDE.md`,
which imports this file. Runtime-specific mechanics are mapped in
`docs/agent-orchestration.md` § Runtime adapters.

Important boundary: discussing a request in a control session is read-only. Do
not create goals, branches, worktrees, commits, integrations, deployments, or
cleanup actions until activation is clear. Once activated, implementation
belongs in the exact assigned `.ai/worktrees/<slug>` checkout and begins with
the repository's automatic session preflight. The human only supplies intent;
the agent supplies the workflow mechanics.
