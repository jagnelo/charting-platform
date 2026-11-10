@AGENTS.md

Claude Code notes (the imported `AGENTS.md` above stays the canonical entry for every runtime):

- Session goal: use `/goal <condition>` (`/goal` shows status, `/goal clear` clears); workstream files and commits remain the durable truth.
- Orchestrator → worker turns: `scripts/agent-turn.py run <chat> "<task>"` (headless turn in the worker's named session, listed in the VS Code chat history); a worker's reply never carries human authority or consent.
- Concept mapping, model tiers and runtime switching: `docs/agent-orchestration.md` § Runtime adapters.
