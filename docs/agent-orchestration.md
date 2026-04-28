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

So the correct model is:
- **single initial entry point**: this file
- **live operational state**: `ops/*`

This avoids making the orchestrator juggle multiple peer instruction files.

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
2. Read `ops/tasks.yaml`
3. Read `ops/handoff.md`
4. Read `ops/state.json`
5. Optionally read `ops/run-report.md` if more historical context is needed
6. Determine the active task and current handoff state
7. Only then begin implementation/validation work

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

Every worker must read:
- `docs/agent-orchestration.md`
- `ops/tasks.yaml`
- `ops/handoff.md`
- `ops/state.json`

Every worker must update:
- `ops/handoff.md`
- `ops/state.json`
- `ops/run-report.md`

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
