from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.api_contracts import ApiErrorCode
from app.strategy_lab_v2.api_router import ApiAdapterError
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.commands import (
    CommandEffect,
    ExecutionCommand,
    ExecutionCommandDecision,
    ExecutionCommandKind,
)
from app.strategy_lab_v2.outcomes import (
    OutcomeStatus,
    OutcomeUpdate,
    apply_outcome_update,
    new_execution_outcome,
)
from app.strategy_lab_v2.postgres_commands import (
    ExecutionCommandContext,
    PostgresCommandAdapter,
    PostgresCommandSchema,
)
from app.strategy_lab_v2.progress import (
    ExecutionProgressState,
    ExecutionProgressUpdate,
    ProgressPhase,
    apply_progress_update,
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
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
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
        if sql.lstrip().startswith("SELECT"):
            owner_id = values["owner_id"]
            attempt_id = values["attempt_id"]
            rows = [
                row
                for (row_owner, _), row in sorted(self.rows.items())
                if row_owner == owner_id and row["attempt_id"] == attempt_id
            ]
            return FakeResult(rows)
        if sql.lstrip().startswith("INSERT"):
            key = (values["owner_id"], values["idempotency_key"])
            if key in self.rows or any(
                row["owner_id"] == values["owner_id"]
                and row["command_id"] == values["command_id"]
                for row in self.rows.values()
            ):
                return FakeResult(rowcount=0)
            self.rows[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


class StateReader:
    def __init__(self, context: ExecutionCommandContext | None) -> None:
        self.context = context

    async def __call__(self, **_: Any) -> ExecutionCommandContext | None:
        return self.context


def _context(status: OutcomeStatus = OutcomeStatus.RUNNING) -> ExecutionCommandContext:
    outcome = new_execution_outcome(content_digest("submission"), ATTEMPT, accepted_at=NOW)
    progress = new_progress_state(ATTEMPT, total_units=10, now=NOW)
    if status is not OutcomeStatus.ACCEPTED:
        outcome = apply_outcome_update(
            outcome,
            OutcomeUpdate(
                outcome.submission_id,
                ATTEMPT,
                1,
                status,
                NOW + timedelta(seconds=1),
                result_digest=content_digest("result") if status is OutcomeStatus.SUCCEEDED else None,
            ),
        ).state
        phase = ProgressPhase.FAILED if status is OutcomeStatus.FAILED else ProgressPhase.RUNNING
        progress = apply_progress_update(
            progress,
            ExecutionProgressUpdate(ATTEMPT, 1, phase, 1, 10, NOW + timedelta(seconds=1)),
        )
    return ExecutionCommandContext(outcome, progress)


def _command(value: str, kind: ExecutionCommandKind = ExecutionCommandKind.CANCEL) -> ExecutionCommand:
    return ExecutionCommand(content_digest(value), ATTEMPT, kind, NOW, "operator request")


@pytest.mark.asyncio
async def test_command_adapter_persists_acceptance_and_replays_exact_retry() -> None:
    session = FakeSession()
    adapter = PostgresCommandAdapter(
        lambda: session, StateReader(_context()), clock=lambda: NOW + timedelta(minutes=1)
    )
    command = _command("cancel")
    accepted = await adapter.command(
        principal="alice", request_id="request-1", idempotency_key="command-key", command=command
    )
    assert accepted.decision is ExecutionCommandDecision.ACCEPT
    assert accepted.receipt is not None
    assert accepted.receipt.effect is CommandEffect.CANCELLATION_REQUESTED
    assert len(session.rows) == 1

    replay = await adapter.command(
        principal="alice", request_id="request-2", idempotency_key="command-key", command=command
    )
    assert replay.decision is ExecutionCommandDecision.REPLAY_EXISTING
    assert replay.receipt == accepted.receipt
    assert len(session.rows) == 1


@pytest.mark.asyncio
async def test_command_adapter_scopes_owner_and_rejects_idempotency_drift() -> None:
    session = FakeSession()
    adapter = PostgresCommandAdapter(lambda: session, StateReader(_context()), clock=lambda: NOW)
    command = _command("cancel")
    await adapter.command(
        principal="alice", request_id="request-1", idempotency_key="command-key", command=command
    )
    other_owner = await adapter.command(
        principal="bob", request_id="request-2", idempotency_key="command-key", command=command
    )
    assert other_owner.decision is ExecutionCommandDecision.ACCEPT

    with pytest.raises(ApiAdapterError) as conflict:
        await adapter.command(
            principal="alice",
            request_id="request-3",
            idempotency_key="command-key",
            command=_command("changed"),
        )
    assert conflict.value.error.code is ApiErrorCode.IDEMPOTENCY_CONFLICT


@pytest.mark.asyncio
async def test_command_adapter_returns_typed_precondition_and_not_found_errors() -> None:
    session = FakeSession()
    failed_context = _context(OutcomeStatus.FAILED)
    failed_context = ExecutionCommandContext(
        failed_context.outcome,
        ExecutionProgressState(ATTEMPT, 1, ProgressPhase.FAILED, 10, 10, False, NOW + timedelta(seconds=1)),
    )
    adapter = PostgresCommandAdapter(lambda: session, StateReader(failed_context), clock=lambda: NOW)
    with pytest.raises(ApiAdapterError) as precondition:
        await adapter.command(
            principal="alice", request_id="request-1", idempotency_key="key", command=_command("cancel")
        )
    assert precondition.value.error.code is ApiErrorCode.PRECONDITION_FAILED

    missing = PostgresCommandAdapter(lambda: FakeSession(), StateReader(None), clock=lambda: NOW)
    with pytest.raises(ApiAdapterError) as not_found:
        await missing.command(
            principal="alice", request_id="request-2", idempotency_key="key", command=_command("cancel")
        )
    assert not_found.value.error.code is ApiErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_command_adapter_fails_closed_on_tampered_receipt_or_unauthorized_principal() -> None:
    session = FakeSession()
    adapter = PostgresCommandAdapter(lambda: session, StateReader(_context()), clock=lambda: NOW)
    command = _command("cancel")
    await adapter.command(
        principal="alice", request_id="request-1", idempotency_key="key", command=command
    )
    session.rows[("alice", "key")]["command_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="command row is malformed"):
        await adapter.command(
            principal="alice", request_id="request-2", idempotency_key="key", command=command
        )
    with pytest.raises(ApiAdapterError) as unauthorized:
        await adapter.command(
            principal=object(), request_id="request-3", idempotency_key="key", command=command
        )
    assert unauthorized.value.error.code is ApiErrorCode.AUTHORIZATION_REQUIRED


def test_command_schema_is_explicit_but_not_applied() -> None:
    schema = PostgresCommandSchema()
    assert "CREATE TABLE" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresCommandSchema(command_table="unsafe;drop")
