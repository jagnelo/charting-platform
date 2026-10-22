from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.outcomes import (
    OutcomeStatus,
    OutcomeUpdate,
    new_execution_outcome,
)
from app.strategy_lab_v2.postgres_execution_state import (
    PostgresExecutionStateAdapter,
    PostgresExecutionStateSchema,
    StateMutationDecision,
)
from app.strategy_lab_v2.progress import (
    CancellationRequest,
    ExecutionProgressUpdate,
    ProgressPhase,
    new_progress_state,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
ATTEMPT = "attempt-1"


class FakeResult:
    def __init__(self, rows=(), rowcount: int = 0) -> None:
        self._rows = list(rows)
        self.rowcount = rowcount

    def mappings(self):
        return iter(self._rows)


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    def __init__(self) -> None:
        self.outcomes: dict[tuple[str, str], dict[str, Any]] = {}
        self.progress: dict[tuple[str, str], dict[str, Any]] = {}
        self.calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        sql = str(statement)
        values = dict(params or {})
        self.calls.append(sql)
        key = (values.get("owner_id"), values.get("attempt_id"))
        if sql.lstrip().startswith("SELECT") and "execution_outcomes" in sql:
            row = self.outcomes.get(key)
            return FakeResult([] if row is None else [row])
        if sql.lstrip().startswith("SELECT") and "execution_progress" in sql:
            row = self.progress.get(key)
            return FakeResult([] if row is None else [row])
        if sql.lstrip().startswith("INSERT") and "execution_outcomes" in sql:
            if key in self.outcomes:
                return FakeResult(rowcount=0)
            self.outcomes[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT") and "execution_progress" in sql:
            if key in self.progress:
                return FakeResult(rowcount=0)
            self.progress[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("UPDATE") and "execution_outcomes" in sql:
            row = self.outcomes.get(key)
            if row is None or row["state_fingerprint"] != values["expected_state_fingerprint"]:
                return FakeResult(rowcount=0)
            row.update(values)
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("UPDATE") and "execution_progress" in sql:
            row = self.progress.get(key)
            if row is None or row["checkpoint_fingerprint"] != values["expected_checkpoint_fingerprint"]:
                return FakeResult(rowcount=0)
            row.update(values)
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _states() -> tuple[Any, Any]:
    return (
        new_execution_outcome(content_digest("submission"), ATTEMPT, accepted_at=NOW),
        new_progress_state(ATTEMPT, total_units=10, now=NOW),
    )


@pytest.mark.asyncio
async def test_execution_state_adapter_initializes_reads_and_replays_updates() -> None:
    session = FakeSession()
    adapter = PostgresExecutionStateAdapter(lambda: session)
    outcome, progress = _states()
    created = await adapter.initialize(principal="alice", outcome=outcome, progress=progress)
    assert created.decision is StateMutationDecision.APPLIED
    context = await adapter.read_context(principal="alice", attempt_id=ATTEMPT)
    assert context is not None
    assert context.outcome == outcome
    assert context.progress == progress

    outcome_update = OutcomeUpdate(
        outcome.submission_id,
        ATTEMPT,
        1,
        OutcomeStatus.RUNNING,
        NOW + timedelta(seconds=1),
    )
    progress_update = ExecutionProgressUpdate(
        ATTEMPT,
        1,
        ProgressPhase.RUNNING,
        1,
        10,
        NOW + timedelta(seconds=1),
        "started",
    )
    applied = await adapter.transition(
        principal="alice",
        outcome_update=outcome_update,
        progress_update=progress_update,
    )
    assert applied.decision is StateMutationDecision.APPLIED
    replay = await adapter.transition(
        principal="alice",
        outcome_update=outcome_update,
        progress_update=progress_update,
    )
    assert replay.decision is StateMutationDecision.REPLAY_EXISTING
    assert replay.outcome == applied.outcome
    assert replay.progress == applied.progress


@pytest.mark.asyncio
async def test_execution_state_adapter_scopes_owner_and_cancellation() -> None:
    session = FakeSession()
    adapter = PostgresExecutionStateAdapter(lambda: session)
    outcome, progress = _states()
    await adapter.initialize(principal="alice", outcome=outcome, progress=progress)
    assert await adapter.read_context(principal="bob", attempt_id=ATTEMPT) is None
    missing = await adapter.transition(
        principal="bob",
        cancellation=CancellationRequest("request", ATTEMPT, NOW, "stop"),
    )
    assert missing.decision is StateMutationDecision.NOT_FOUND

    cancelled = await adapter.transition(
        principal="alice",
        cancellation=CancellationRequest("request", ATTEMPT, NOW + timedelta(seconds=1), "stop"),
    )
    assert cancelled.decision is StateMutationDecision.APPLIED
    assert cancelled.progress is not None
    assert cancelled.progress.cancellation_requested is True
    replay = await adapter.transition(
        principal="alice",
        cancellation=CancellationRequest("request", ATTEMPT, NOW + timedelta(seconds=1), "stop"),
    )
    assert replay.decision is StateMutationDecision.REPLAY_EXISTING


@pytest.mark.asyncio
async def test_execution_state_adapter_rejects_gaps_and_tampered_rows() -> None:
    session = FakeSession()
    adapter = PostgresExecutionStateAdapter(lambda: session)
    outcome, progress = _states()
    await adapter.initialize(principal="alice", outcome=outcome, progress=progress)
    gap = await adapter.transition(
        principal="alice",
        progress_update=ExecutionProgressUpdate(
            ATTEMPT,
            3,
            ProgressPhase.RUNNING,
            3,
            10,
            NOW + timedelta(seconds=3),
        ),
    )
    assert gap.decision is StateMutationDecision.REJECT
    session.outcomes[("alice", ATTEMPT)]["state_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="outcome fingerprint"):
        await adapter.read_context(principal="alice", attempt_id=ATTEMPT)


def test_execution_state_schema_is_explicit_but_not_applied() -> None:
    schema = PostgresExecutionStateSchema()
    assert len(schema.statements) == 2
    assert all("CREATE TABLE" in statement for statement in schema.statements)
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresExecutionStateSchema(progress_table="unsafe;drop")
