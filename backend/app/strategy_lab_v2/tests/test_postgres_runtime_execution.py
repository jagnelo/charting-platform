from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_runtime_execution import (
    PostgresRuntimeExecutionAdapter,
    PostgresRuntimeExecutionSchema,
    RuntimeStateDecision,
)
from app.strategy_lab_v2.runtime_execution import (
    RuntimeExecutionPhase,
    RuntimeExecutionUpdate,
)
from app.strategy_lab_v2.sandbox_execution import SandboxRunStatus
from app.strategy_lab_v2.tests.test_runtime_result_adapter import _fixtures, _result

NOW = datetime(2024, 1, 1, tzinfo=UTC)


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
        self.states: dict[tuple[str, str], dict[str, Any]] = {}
        self.updates: dict[tuple[str, str, int], dict[str, Any]] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        sql = str(statement)
        values = dict(params or {})
        normalized = sql.lstrip()
        if normalized.startswith("SELECT owner_id") and "runtime_updates" not in sql:
            lookup = values["lookup_key"]
            rows = [
                row
                for (owner, attempt), row in self.states.items()
                if owner == values["owner_id"]
                and (
                    row["request_fingerprint"] == lookup
                    if "request_fingerprint = :lookup_key" in sql
                    else attempt == lookup
                )
            ]
            return FakeResult(rows)
        if normalized.startswith("SELECT owner_id") and "runtime_updates" in sql:
            rows = [
                row
                for (owner, attempt, sequence), row in self.updates.items()
                if owner == values["owner_id"]
                and attempt == values["attempt_id"]
                and (
                    "sequence = :sequence" not in sql
                    or sequence == values["sequence"]
                )
            ]
            return FakeResult(sorted(rows, key=lambda row: row["sequence"]))
        if normalized.startswith("INSERT INTO") and "runtime_execution" in sql:
            key = (values["owner_id"], values["attempt_id"])
            if key in self.states:
                return FakeResult(rowcount=0)
            self.states[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO") and "runtime_updates" in sql:
            key = (values["owner_id"], values["attempt_id"], values["sequence"])
            if key in self.updates:
                return FakeResult(rowcount=0)
            self.updates[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("UPDATE") and "runtime_execution" in sql:
            key = (values["owner_id"], values["attempt_id"])
            row = self.states[key]
            if row["state_fingerprint"] != values["expected_state_fingerprint"]:
                return FakeResult(rowcount=0)
            self.states[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.asyncio
async def test_runtime_adapter_initializes_replays_and_scopes_state() -> None:
    state, _ = _fixtures()
    session = FakeSession()
    adapter = PostgresRuntimeExecutionAdapter(lambda: session)
    registered = await adapter.initialize(principal="owner-a", state=state)
    assert registered.decision is RuntimeStateDecision.REGISTERED
    replay = await adapter.initialize(principal="owner-a", state=state)
    assert replay.decision is RuntimeStateDecision.REPLAY_EXISTING
    assert await adapter.load(principal="owner-a", attempt_id=state.attempt_id) == state
    assert await adapter.load_for_request(
        principal="owner-a", request_fingerprint=state.request_fingerprint
    ) == state
    assert await adapter.load(principal="owner-b", attempt_id=state.attempt_id) is None


@pytest.mark.asyncio
async def test_runtime_adapter_applies_exact_updates_and_retains_history() -> None:
    state, plan = _fixtures()
    session = FakeSession()
    adapter = PostgresRuntimeExecutionAdapter(lambda: session)
    await adapter.initialize(principal="owner-a", state=state)
    running = RuntimeExecutionUpdate(
        state.request_fingerprint,
        state.attempt_id,
        1,
        RuntimeExecutionPhase.RUNNING,
        NOW + timedelta(seconds=1),
    )
    applied = await adapter.apply_update(principal="owner-a", update=running)
    assert applied.decision is RuntimeStateDecision.APPLIED
    replay = await adapter.apply_update(principal="owner-a", update=running)
    assert replay.decision is RuntimeStateDecision.REPLAY_EXISTING
    conflict = await adapter.apply_update(
        principal="owner-a",
        update=RuntimeExecutionUpdate(
            state.request_fingerprint,
            state.attempt_id,
            1,
            RuntimeExecutionPhase.CANCELLED,
            NOW + timedelta(seconds=2),
        ),
    )
    assert conflict.decision is RuntimeStateDecision.CONFLICT
    terminal = RuntimeExecutionUpdate(
        state.request_fingerprint,
        state.attempt_id,
        2,
        RuntimeExecutionPhase.SUCCEEDED,
        NOW + timedelta(seconds=2),
        content_digest("stdout"),
        6,
    )
    assert (await adapter.apply_update(principal="owner-a", update=terminal)).decision is RuntimeStateDecision.APPLIED
    assert await adapter.load_updates(principal="owner-a", attempt_id=state.attempt_id) == (
        running,
        terminal,
    )
    missing = await adapter.apply_update(principal="owner-b", update=running)
    assert missing.decision is RuntimeStateDecision.NOT_FOUND


@pytest.mark.asyncio
async def test_runtime_adapter_materializes_sandbox_result_atomically_and_replays() -> None:
    state, plan = _fixtures()
    result = _result(plan, SandboxRunStatus.SUCCEEDED)
    session = FakeSession()
    adapter = PostgresRuntimeExecutionAdapter(lambda: session)
    await adapter.initialize(principal="owner-a", state=state)
    materialized = await adapter.materialize_sandbox_result(
        principal="owner-a", sandbox_plan=plan, sandbox_result=result, observed_at=NOW
    )
    assert materialized.decision is RuntimeStateDecision.APPLIED
    assert materialized.state is not None
    assert materialized.state.phase is RuntimeExecutionPhase.SUCCEEDED
    assert materialized.state.sequence == 2
    assert len(session.updates) == 2
    replay = await adapter.materialize_sandbox_result(
        principal="owner-a", sandbox_plan=plan, sandbox_result=result, observed_at=NOW
    )
    assert replay.decision is RuntimeStateDecision.REPLAY_EXISTING
    drift = type(result)(
        result.plan_fingerprint,
        result.request_fingerprint,
        result.status,
        result.exit_code,
        content_digest("different-stdout"),
        result.stderr_digest,
        result.stdout_bytes,
        result.stderr_bytes,
    )
    rejected = await adapter.materialize_sandbox_result(
        principal="owner-a", sandbox_plan=plan, sandbox_result=drift, observed_at=NOW
    )
    assert rejected.decision is RuntimeStateDecision.REJECT
    assert len(session.updates) == 2


@pytest.mark.asyncio
async def test_runtime_adapter_authenticates_tampered_state_and_update_rows() -> None:
    state, _ = _fixtures()
    session = FakeSession()
    adapter = PostgresRuntimeExecutionAdapter(lambda: session)
    await adapter.initialize(principal="owner-a", state=state)
    session.states[("owner-a", state.attempt_id)]["state_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load(principal="owner-a", attempt_id=state.attempt_id)

    session = FakeSession()
    adapter = PostgresRuntimeExecutionAdapter(lambda: session)
    await adapter.initialize(principal="owner-a", state=state)
    update = RuntimeExecutionUpdate(
        state.request_fingerprint,
        state.attempt_id,
        1,
        RuntimeExecutionPhase.RUNNING,
        NOW,
    )
    await adapter.apply_update(principal="owner-a", update=update)
    session.updates[("owner-a", state.attempt_id, 1)]["update_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load_updates(principal="owner-a", attempt_id=state.attempt_id)


def test_runtime_execution_schema_is_explicit_and_validated() -> None:
    schema = PostgresRuntimeExecutionSchema()
    assert len(schema.statements) == 2
    assert "PRIMARY KEY (owner_id, attempt_id)" in schema.statements[0]
    assert "UNIQUE (owner_id, attempt_id, update_fingerprint)" in schema.statements[1]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresRuntimeExecutionSchema(state_table="unsafe;drop")
