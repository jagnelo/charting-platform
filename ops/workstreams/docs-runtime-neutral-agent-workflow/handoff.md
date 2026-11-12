# docs/runtime-neutral-agent-workflow

Created from `staging` at `139b350238b5e1c8a170dce5af09a805301d857e`.

## Human authorization

- Recorded at: 2026-11-10T00:00:59.517083+00:00
- Request: Human request 2026-11-09: 'Any repo documentation MUST be updated to now also encompass Claude Code's semantics and environment too, as beforehand this was all done through Codex alone ... I do not want to care too much about whether Codex or Claude Code or something else is being used'; activated 2026-11-10: 'ok handle this ... do whatever you must, i authorize you'.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: draft; the implementation agent must complete scope, acceptance criteria, tests, and local validation profile before creating a goal.

Update this handoff at each coherent boundary.

## Implementation checkpoint (2026-11-10, Claude Code session 071334ca-c0f2-4cf6-850e-6a45949e8a9f)

Context: `runtime-neutral-agent-workflow` — complete; status `ready_for_human_review` (RN1–RN4, 4/4).

Planning: schema-4 plan completed and accepted by `make agent-session-plan-ready`
under the repository's scoped local bootstrap exception (no plan-only push, per the
human's no-metadata-only-push preference). Goal state recorded `unavailable`: the
work ran as a delegated Claude Code subagent, which has no session-local `/goal`;
it followed the recorded objective and `next_action` instead.

Delivered:
- `CLAUDE.md` (new): `@AGENTS.md` import plus three Claude Code pointers.
- `AGENTS.md`: runtime-neutral (interactive sessions under any runtime; session-local
  goal via the runtime's mechanism; Codex/Claude Code/others discover it, Claude Code via
  `CLAUDE.md`); every rule kept.
- `docs/agent-orchestration.md`: runtime-neutral wording for entry discovery, session
  windows, goal/budget contract, goal updates, setup order (now "at least one supported
  runtime CLI, optionally a second for switching" instead of requiring both Codex and
  Claude Code — decision under the runtime-agnostic direction), worker model, sandboxed Git
  recovery ("Codex execution rule" heading → "Sandboxed execution rule"; no in-repo links
  to the old anchor), prompting rule, root discovery and architecture; new
  `## Runtime adapters` section (concept → Codex / Claude Code / fallback table,
  `crossSessionInbound` note, Switching runtimes procedure, model tiers by role).
  Every rule preserved.
- `docs/development.md`: budget wording names both adapters.
- `docs/feature-integration-coordination.md`: "replaced session goal"; the October
  saved-goal section is labelled "(Codex era)" with a pointer to the adapters; its
  historical audit text is unchanged.
- `scripts/agent-session.py`: module docstring, `make_goal_request` docstring and the
  plan-ready `next_action` message only; no behaviour or JSON key change
  (`token_budget` stays the stored key; adapters map it).

Remaining tracked "Codex" mentions (justified):
- Adapter/neutral enumerations: `AGENTS.md`, `docs/agent-orchestration.md`,
  `docs/development.md`, `docs/feature-integration-coordination.md` (Codex-era label and
  historical audit lines).
- Quoted human statement: `docs/provider-integration-checkpoint.md` line 10.
- Dated historical records: `docs/feature-integration-reconciliation.md` (Oct queue
  receipt), `docs/project-todos.md` (2026-08-08 active-goal alignment; earlier workflow
  discussion), `docs/tc2000-roadmap.md` (prior rollout ID),
  `docs/tc2000-acceptance-governance.md` ("active Codex goal" describes the goal that
  adopted the policy; it prescribes no Codex mechanic, and the file is owned by the
  TC2000 workstream, so editing it here would only add cross-branch merge risk).
- Historical evidence, intentionally untouched: `ops/run-report.md`, `ops/handoff.md`,
  `ops/state.json`, `ops/tasks.yaml`, `ops/feature-session-goals-2026-10-15.json`,
  `ops/workflow-validation.jsonl`, `docs/session-exports/*`, other branches'
  `ops/workstreams/*`, and this workstream's own quoted human request.

Not changed (decision): `scripts/ci-change-scope.py` still classifies `AGENTS.md`,
`CLAUDE.md` and the non-workflow docs as broad, so this branch's push runs the broad
CI lane once. Narrowing the classifier is a separate workflow topic.

Validation: see `validation.jsonl` (unit profile; 67 focused workflow tests passed,
48 workstream records validated, branch-test manifest valid, py_compile, diff check,
plan YAML, profile classifier = unit). No Docker/browser/product suites; no Docker
resources created.

Commit/push: the implementation commit containing this handoff is verified externally
with `git rev-parse HEAD` / `origin/docs/runtime-neutral-agent-workflow`; a session
record follow-up may refresh `session.json` only.

Next action: human review. Do not integrate, promote, or deploy; closure needs an
explicit human closure statement.

## Records follow-up

Implementation commit `9071339127b3427e82a6ddccf4efc86e215e5ed2` is pushed and
matches `origin/docs/runtime-neutral-agent-workflow`. After it, plan-ready, goal-state
`unavailable` and checkpoint refreshed
`ops/workstreams/docs-runtime-neutral-agent-workflow/session.json`; this records-only
follow-up commits that file and this note (its own SHA is verified externally).
Status remains `ready_for_human_review`.

## Single-orchestrator extension (2026-11-12, Claude Code Desktop, claim 6f8f10e1)

On 2026-11-12 the human directed that one orchestrator chat run at a time, using cheaper subagents, as quoted in `plan.yaml`. Claim taken over from `071334ca` under that request. Context `single-orchestrator-default-mode`, RN5:

- `docs/agent-orchestration.md` has a new section, § Orchestrator and subagents (default operating mode), covering:
  - work contexts, and the git-ignored `.ai/contexts/<slug>.md` index;
  - the orchestrator holds every claim and runs commands with each worktree as its cwd;
  - one writing subagent per worktree; the subagent prohibitions, including the human-authorization fields and the worktree lifecycle commands;
  - commits stay with the orchestrator by default, and it verifies subagent reports before recording them;
  - background commands need timeouts; at most 2 Docker-backed suites run concurrently;
  - the orchestrator coordinates staging integration under the integration lock, without replacing any human closure, promotion or deployment decision;
  - continuity; the retired multi-chat transport.
- Other edits in the same file:
  - Operating modes, Control/implementation sessions, Worker model, Stop-before-expiry and Orchestrator checkpoint rules: updated for the new mode.
  - Runtime adapters table: rebuilt around subagents.
  - Model tiers table: Opus as orchestrator, Sonnet and Haiku as subagents.
- `AGENTS.md` and `CLAUDE.md` point to the default mode. `.gitignore` adds `.ai/contexts/`. `scripts/agent-turn.py` is removed; it was the retired transport, never merged, with no references.
- An independent subagent review found contradictions, two bypass gaps and stale VS Code/worker wording. All are fixed. Anchors were verified.

Validation: 67 focused workflow tests passed and 48 workstream records validated. The diff check is clean.

Next action: human review. Closure needs an explicit human closure statement. Do not integrate, promote or deploy.
