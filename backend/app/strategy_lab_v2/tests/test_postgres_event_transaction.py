from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.audit import AuditEntry, AuditEntryType
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.events import (
    EventAppendDecision,
    EventStreamCursor,
    ExecutionEvent,
    ExecutionEventType,
)
from app.strategy_lab_v2.execution_event_transaction import (
    ExecutionEventTransactionDecision,
)
from app.strategy_lab_v2.outbox import (
    OutboxAcknowledgeDecision,
    OutboxMessage,
)
from app.strategy_lab_v2.postgres_event_transaction import (
    PostgresExecutionEventSchema,
    PostgresExecutionEventTransactionAdapter,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
TRIAL = "trial-1"
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
        self.events: dict[str, dict[str, Any]] = {}
        self.cursors: dict[tuple[str, str], dict[str, Any]] = {}
        self.audit: dict[str, dict[str, Any]] = {}
        self.outbox: dict[str, dict[str, Any]] = {}
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
        if sql.lstrip().startswith("SELECT trial_id"):
            key = (values["trial_id"], values["attempt_id"])
            row = self.cursors.get(key)
            return FakeResult([] if row is None else [row])
        if sql.lstrip().startswith("SELECT event_id"):
            rows = [
                row
                for row in self.events.values()
                if row["trial_id"] == values["trial_id"] and row["attempt_id"] == values["attempt_id"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["sequence"]))
        if sql.lstrip().startswith("SELECT entry_id"):
            rows = [
                row
                for row in self.audit.values()
                if row["aggregate_type"] == values["aggregate_type"]
                and row["aggregate_id"] == values["aggregate_id"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["sequence"]))
        if sql.lstrip().startswith("SELECT message_id"):
            return FakeResult(sorted(self.outbox.values(), key=lambda row: row["message_id"]))
        if sql.lstrip().startswith("INSERT INTO") and "event_fingerprint" in sql:
            key = values["event_id"]
            if key in self.events:
                return FakeResult(rowcount=0)
            self.events[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT INTO") and "entry_fingerprint" in sql:
            key = values["entry_id"]
            if key in self.audit:
                return FakeResult(rowcount=0)
            self.audit[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT INTO") and "message_fingerprint" in sql:
            key = values["message_id"]
            if key in self.outbox or any(
                row["request_id"] == values["request_id"] for row in self.outbox.values()
            ):
                return FakeResult(rowcount=0)
            self.outbox[key] = {**values, "published": False}
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT INTO") and "cursor_fingerprint" in sql:
            key = (values["trial_id"], values["attempt_id"])
            if key in self.cursors:
                return FakeResult(rowcount=0)
            self.cursors[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("UPDATE") and "cursor_fingerprint" in sql:
            key = (values["trial_id"], values["attempt_id"])
            row = self.cursors.get(key)
            if row is None or row["sequence"] != values["expected_sequence"]:
                return FakeResult(rowcount=0)
            row.update(
                sequence=values["sequence"],
                last_event_id=values["last_event_id"],
                cursor_fingerprint=values["cursor_fingerprint"],
            )
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("UPDATE") and "published = TRUE" in sql:
            row = self.outbox.get(values["message_id"])
            if row is None or row["published"]:
                return FakeResult(rowcount=0)
            row["published"] = True
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _records(sequence: int = 1) -> tuple[ExecutionEvent, AuditEntry, OutboxMessage]:
    event = ExecutionEvent(
        TRIAL,
        ATTEMPT,
        sequence,
        ExecutionEventType.ATTEMPT_CREATED,
        content_digest({"event": sequence}),
        NOW + timedelta(seconds=sequence),
        "worker",
    )
    entry = AuditEntry(
        "attempt",
        ATTEMPT,
        sequence,
        AuditEntryType.OUTCOME_RECORDED,
        content_digest({"audit": sequence}),
        event.occurred_at,
        "worker",
        correlation_id=event.event_id,
    )
    message = OutboxMessage(
        content_digest({"request": sequence}),
        "attempt",
        ATTEMPT,
        entry.entry_id,
        "strategy-lab.execution",
        event.payload_digest,
        event.occurred_at,
        event.occurred_at,
    )
    return event, entry, message


@pytest.mark.asyncio
async def test_postgres_event_adapter_commits_linked_rows_and_replays_exactly() -> None:
    session = FakeSession()
    adapter = PostgresExecutionEventTransactionAdapter(lambda: session)
    event, entry, message = _records()
    first = await adapter.append(event=event, entry=entry, message=message)
    assert first.decision is ExecutionEventTransactionDecision.COMMITTED
    assert len(session.events) == len(session.audit) == len(session.outbox) == 1
    assert session.cursors[(TRIAL, ATTEMPT)]["sequence"] == 1
    writes = len(session.calls)

    replay = await adapter.append(event=event, entry=entry, message=message)
    assert replay.decision is ExecutionEventTransactionDecision.REPLAY_EXISTING
    assert replay.event_id == first.event_id
    assert replay.audit_entry_id == first.audit_entry_id
    assert replay.message_id == first.message_id
    assert len(session.calls) == writes + 4  # four locked reads, no writes


@pytest.mark.asyncio
async def test_postgres_event_adapter_preserves_state_on_gap_and_cursor_drift() -> None:
    session = FakeSession()
    adapter = PostgresExecutionEventTransactionAdapter(lambda: session)
    first_event, first_entry, first_message = _records()
    await adapter.append(event=first_event, entry=first_entry, message=first_message)
    gap_event, gap_entry, gap_message = _records(3)
    gap = await adapter.append(event=gap_event, entry=gap_entry, message=gap_message)
    assert gap.decision is ExecutionEventTransactionDecision.GAP
    assert len(session.events) == len(session.audit) == len(session.outbox) == 1

    stale = await adapter.append(
        event=_records(2)[0],
        entry=_records(2)[1],
        message=_records(2)[2],
        expected_cursor=EventStreamCursor(TRIAL, ATTEMPT, 9, content_digest("stale")),
    )
    assert stale.decision is ExecutionEventTransactionDecision.CONFLICT
    assert stale.event_append_decision is EventAppendDecision.CONFLICT
    assert len(session.events) == len(session.audit) == len(session.outbox) == 1


@pytest.mark.asyncio
async def test_postgres_event_adapter_fails_closed_on_tampered_rows() -> None:
    session = FakeSession()
    adapter = PostgresExecutionEventTransactionAdapter(lambda: session)
    event, entry, message = _records()
    await adapter.append(event=event, entry=entry, message=message)
    session.events[event.event_id]["event_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="execution event row is malformed"):
        await adapter.append(event=event, entry=entry, message=message)


@pytest.mark.asyncio
async def test_postgres_event_adapter_loads_and_acknowledges_outbox_with_cas() -> None:
    session = FakeSession()
    adapter = PostgresExecutionEventTransactionAdapter(lambda: session)
    event, entry, message = _records()
    await adapter.append(event=event, entry=entry, message=message)

    state = await adapter.load_outbox()
    assert state.pending_messages == (message,)
    acknowledged = await adapter.acknowledge_outbox(
        message.message_id,
        expected_state_fingerprint=state.fingerprint,
    )
    assert acknowledged.decision is OutboxAcknowledgeDecision.ACKNOWLEDGED
    assert acknowledged.state.published_message_ids == frozenset({message.message_id})

    replay = await adapter.acknowledge_outbox(
        message.message_id,
        expected_state_fingerprint=acknowledged.state.fingerprint,
    )
    assert replay.decision is OutboxAcknowledgeDecision.REPLAY_EXISTING

    stale = await adapter.acknowledge_outbox(
        message.message_id,
        expected_state_fingerprint=state.fingerprint,
    )
    assert stale.decision is OutboxAcknowledgeDecision.REJECT


def test_postgres_event_schema_is_explicit_but_not_applied() -> None:
    schema = PostgresExecutionEventSchema()
    assert len(schema.statements) == 4
    assert all("CREATE TABLE" in statement for statement in schema.statements)
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresExecutionEventSchema(event_table="unsafe;drop")
