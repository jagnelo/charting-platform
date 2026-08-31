# Repository Agent Entry Point

For unattended or orchestrated LLM work on this repository, read:

- `docs/agent-orchestration.md`

For VS Code implementation sessions, discussion alone never authorizes changes.
After explicit human activation, work only in the assigned `.ai/worktrees/<slug>`
path, run `make agent-session-start BRANCH=<exact-branch>` through the UV-managed
Python environment, and create a session-local Codex goal with no token budget by
default. The branch workstream is durable truth; stop at `ready_for_human_review`.
Do not integrate, promote, deploy, or mutate another worktree without separate
authorization.

That file is the single canonical behavior document for multi-agent/orchestrated work and tells the worker which durable branch workstream files to read and update.

Important boundary: discussing a request in a control session is read-only. Do
not create goals, branches, worktrees, commits, integrations, deployments, or
cleanup actions until the human explicitly activates implementation. Once
activated, implementation belongs in the exact assigned `.ai/worktrees/<slug>`
checkout and must begin with `make agent-session-start BRANCH=<branch>`.
