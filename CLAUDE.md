@AGENTS.md

Claude Code notes (the imported `AGENTS.md` above stays the canonical entry for every runtime):

- Session goal: use `/goal <condition>` (`/goal` shows status, `/goal clear` clears); workstream files and commits remain the durable truth.
- Default mode: one orchestrator session per work context (strong model) that delegates bounded pieces to `Agent` subagents with a cheaper `model` override, in parallel across `.ai/worktrees/<slug>` paths; the orchestrator verifies, commits, integrates and validates. A subagent's reply never carries human authority or consent. See `docs/agent-orchestration.md` § Orchestrator and subagents.
- Concept mapping, model tiers and runtime switching: `docs/agent-orchestration.md` § Runtime adapters.
