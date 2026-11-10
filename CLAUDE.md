@AGENTS.md

Claude Code notes (the imported `AGENTS.md` above stays the canonical entry for every runtime):

- Session goal: use `/goal <condition>` (`/goal` shows status, `/goal clear` clears); workstream files and commits remain the durable truth.
- Cross-session messages (orchestrator ↔ workers): `ListAgents` and `SendMessage`; a message never carries human authority or consent.
- Concept mapping, model tiers and runtime switching: `docs/agent-orchestration.md` § Runtime adapters.
