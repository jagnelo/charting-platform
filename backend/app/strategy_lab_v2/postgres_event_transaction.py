"""PostgreSQL adapter for atomic execution-event/audit/outbox staging.

The package-owned :mod:`execution_event_transaction` contract resolves an
execution event, its append-only audit entry, and its transactional-outbox
message as one immutable proposal.  This module supplies the persistence
boundary: it locks the attempt stream, re-authenticates every stored digest,
applies a committed proposal in one SQLAlchemy async transaction, and leaves
Redis publication and worker effects to later adapters.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.strategy_lab_v2.audit import AuditEntry, AuditEntryType, AuditJournal
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.events import (
    EventAppendDecision,
    EventStreamCursor,
    ExecutionEvent,
    ExecutionEventType,
)
from app.strategy_lab_v2.execution_event_transaction import (
    ExecutionEventTransactionDecision,
    ExecutionEventTransactionResolution,
    resolve_execution_event_transaction,
)
from app.strategy_lab_v2.outbox import OutboxMessage, OutboxState


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class PostgresExecutionEventSchema:
    """Explicit additive DDL for event, audit, cursor, and outbox rows."""

    event_table: str = "strategy_lab_v2_execution_events"
    cursor_table: str = "strategy_lab_v2_execution_event_cursors"
    audit_table: str = "strategy_lab_v2_execution_audit"
    outbox_table: str = "strategy_lab_v2_execution_outbox"

    def __post_init__(self) -> None:
        for name, value in (
            ("event_table", self.event_table),
            ("cursor_table", self.cursor_table),
            ("audit_table", self.audit_table),
            ("outbox_table", self.outbox_table),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
                raise ValueError(f"{name} must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.event_table} (
                event_id TEXT PRIMARY KEY,
                event_fingerprint TEXT NOT NULL,
                trial_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                sequence BIGINT NOT NULL,
                event_type TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                producer TEXT NOT NULL,
                causation_id TEXT NULL,
                UNIQUE (trial_id, attempt_id, sequence)
            )
            """,
            f"""
            CREATE TABLE {self.cursor_table} (
                trial_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                sequence BIGINT NOT NULL,
                last_event_id TEXT NULL,
                cursor_fingerprint TEXT NOT NULL,
                PRIMARY KEY (trial_id, attempt_id)
            )
            """,
            f"""
            CREATE TABLE {self.audit_table} (
                entry_id TEXT PRIMARY KEY,
                entry_fingerprint TEXT NOT NULL,
                aggregate_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                sequence BIGINT NOT NULL,
                entry_type TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                correlation_id TEXT NULL,
                UNIQUE (aggregate_type, aggregate_id, sequence)
            )
            """,
            f"""
            CREATE TABLE {self.outbox_table} (
                message_id TEXT PRIMARY KEY,
                message_fingerprint TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                aggregate_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                available_at TEXT NOT NULL,
                published BOOLEAN NOT NULL DEFAULT FALSE
            )
            """,
        )


class PostgresExecutionEventTransactionAdapter:
    """Persist one linked execution event, audit entry, and outbox message."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresExecutionEventSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresExecutionEventSchema()

    @property
    def schema(self) -> PostgresExecutionEventSchema:
        return self._schema

    async def append(
        self,
        *,
        event: ExecutionEvent,
        entry: AuditEntry,
        message: OutboxMessage,
        expected_cursor: EventStreamCursor | None = None,
    ) -> ExecutionEventTransactionResolution:
        """Resolve and atomically persist one event transaction.

        ``expected_cursor`` is an optional caller-side compare-and-set witness.
        When omitted, the locked database cursor is authoritative.  Exact
        event retries replay the existing event/audit/outbox rows and perform
        no writes.  Any malformed stored identity raises instead of exposing
        untrusted state.
        """

        if not isinstance(event, ExecutionEvent):
            raise TypeError("event must be an ExecutionEvent")
        if not isinstance(entry, AuditEntry):
            raise TypeError("entry must be an AuditEntry")
        if not isinstance(message, OutboxMessage):
            raise TypeError("message must be an OutboxMessage")
        if expected_cursor is not None and not isinstance(expected_cursor, EventStreamCursor):
            raise TypeError("expected_cursor must be an EventStreamCursor")

        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                cursor, cursor_exists = await self._load_cursor(
                    session, event.trial_id, event.attempt_id
                )
                events = await self._load_events(session, event.trial_id, event.attempt_id)
                _validate_cursor_against_events(cursor, events)
                journal = await self._load_journal(
                    session, entry.aggregate_type, entry.aggregate_id
                )
                outbox = await self._load_outbox(session)
                if expected_cursor is not None and expected_cursor != cursor:
                    return _reject(
                        event,
                        entry,
                        message,
                        cursor,
                        journal,
                        outbox,
                        "execution event cursor compare-and-set precondition failed",
                    )
                resolution = resolve_execution_event_transaction(
                    event,
                    cursor,
                    journal,
                    entry,
                    outbox,
                    message,
                    prior_events=events,
                    prior_entries=journal.entries,
                    prior_messages=outbox.messages,
                )
                if resolution.decision is ExecutionEventTransactionDecision.COMMITTED:
                    await self._persist(
                        session,
                        event,
                        entry,
                        message,
                        resolution,
                        cursor_exists=cursor_exists,
                    )
                return resolution

    async def _load_cursor(
        self, session: AsyncSessionLike, trial_id: str, attempt_id: str
    ) -> tuple[EventStreamCursor, bool]:
        result = await session.execute(
            _statement(
                f"""
                SELECT trial_id, attempt_id, sequence, last_event_id, cursor_fingerprint
                FROM {self._schema.cursor_table}
                WHERE trial_id = :trial_id AND attempt_id = :attempt_id
                FOR UPDATE
                """
            ),
            {"trial_id": trial_id, "attempt_id": attempt_id},
        )
        rows = list(result.mappings())
        if not rows:
            return EventStreamCursor(trial_id, attempt_id), False
        if len(rows) != 1:
            raise ValueError("PostgreSQL execution cursor query returned duplicate keys")
        return _decode_cursor(rows[0]), True

    async def _load_events(
        self, session: AsyncSessionLike, trial_id: str, attempt_id: str
    ) -> tuple[ExecutionEvent, ...]:
        result = await session.execute(
            _statement(
                f"""
                SELECT event_id, event_fingerprint, trial_id, attempt_id, sequence,
                       event_type, payload_digest, occurred_at, producer, causation_id
                FROM {self._schema.event_table}
                WHERE trial_id = :trial_id AND attempt_id = :attempt_id
                ORDER BY sequence ASC
                FOR UPDATE
                """
            ),
            {"trial_id": trial_id, "attempt_id": attempt_id},
        )
        rows = list(result.mappings())
        events = tuple(_decode_event(row) for row in rows)
        if tuple(sorted(events, key=lambda item: item.sequence)) != events:
            raise ValueError("PostgreSQL execution events are not deterministically ordered")
        if tuple(item.sequence for item in events) != tuple(range(1, len(events) + 1)):
            raise ValueError("PostgreSQL execution event sequence is not contiguous")
        return events

    async def _load_journal(
        self, session: AsyncSessionLike, aggregate_type: str, aggregate_id: str
    ) -> AuditJournal:
        result = await session.execute(
            _statement(
                f"""
                SELECT entry_id, entry_fingerprint, aggregate_type, aggregate_id, sequence,
                       entry_type, payload_digest, occurred_at, actor, correlation_id
                FROM {self._schema.audit_table}
                WHERE aggregate_type = :aggregate_type AND aggregate_id = :aggregate_id
                ORDER BY sequence ASC
                FOR UPDATE
                """
            ),
            {"aggregate_type": aggregate_type, "aggregate_id": aggregate_id},
        )
        entries = tuple(_decode_audit(row) for row in result.mappings())
        if tuple(sorted(entries, key=lambda item: item.sequence)) != entries:
            raise ValueError("PostgreSQL execution audit is not deterministically ordered")
        return AuditJournal(aggregate_type, aggregate_id, entries)

    async def _load_outbox(self, session: AsyncSessionLike) -> OutboxState:
        result = await session.execute(
            _statement(
                f"""
                SELECT message_id, message_fingerprint, request_id, aggregate_type,
                       aggregate_id, event_id, topic, payload_digest, created_at,
                       available_at, published
                FROM {self._schema.outbox_table}
                ORDER BY message_id ASC
                FOR UPDATE
                """
            )
        )
        rows = list(result.mappings())
        messages: list[OutboxMessage] = []
        published: set[str] = set()
        for row in rows:
            message = _decode_outbox(row)
            if row["message_id"] != message.message_id:
                raise ValueError("PostgreSQL outbox message identity drifted")
            if row["message_fingerprint"] != message.fingerprint:
                raise ValueError("PostgreSQL outbox message fingerprint does not match bytes")
            if not isinstance(row["published"], bool):
                raise ValueError("PostgreSQL outbox published flag is malformed")
            messages.append(message)
            if row["published"]:
                published.add(message.message_id)
        ordered = tuple(sorted(messages, key=lambda item: item.message_id))
        if tuple(messages) != ordered:
            raise ValueError("PostgreSQL outbox is not deterministically ordered")
        return OutboxState(ordered, frozenset(published))

    async def _persist(
        self,
        session: AsyncSessionLike,
        event: ExecutionEvent,
        entry: AuditEntry,
        message: OutboxMessage,
        resolution: ExecutionEventTransactionResolution,
        *,
        cursor_exists: bool,
    ) -> None:
        event_result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.event_table}
                    (event_id, event_fingerprint, trial_id, attempt_id, sequence,
                     event_type, payload_digest, occurred_at, producer, causation_id)
                VALUES (:event_id, :event_fingerprint, :trial_id, :attempt_id, :sequence,
                        :event_type, :payload_digest, :occurred_at, :producer, :causation_id)
                ON CONFLICT (event_id) DO NOTHING
                """
            ),
            {
                "event_id": event.event_id,
                "event_fingerprint": event.fingerprint,
                "trial_id": event.trial_id,
                "attempt_id": event.attempt_id,
                "sequence": event.sequence,
                "event_type": event.event_type.value,
                "payload_digest": event.payload_digest,
                "occurred_at": _encode_datetime(event.occurred_at),
                "producer": event.producer,
                "causation_id": event.causation_id,
            },
        )
        if getattr(event_result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL execution event insert lost a uniqueness race")

        audit_result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.audit_table}
                    (entry_id, entry_fingerprint, aggregate_type, aggregate_id, sequence,
                     entry_type, payload_digest, occurred_at, actor, correlation_id)
                VALUES (:entry_id, :entry_fingerprint, :aggregate_type, :aggregate_id, :sequence,
                        :entry_type, :payload_digest, :occurred_at, :actor, :correlation_id)
                ON CONFLICT (entry_id) DO NOTHING
                """
            ),
            {
                "entry_id": entry.entry_id,
                "entry_fingerprint": entry.fingerprint,
                "aggregate_type": entry.aggregate_type,
                "aggregate_id": entry.aggregate_id,
                "sequence": entry.sequence,
                "entry_type": entry.entry_type.value,
                "payload_digest": entry.payload_digest,
                "occurred_at": _encode_datetime(entry.occurred_at),
                "actor": entry.actor,
                "correlation_id": entry.correlation_id,
            },
        )
        if getattr(audit_result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL execution audit insert lost a uniqueness race")

        outbox_result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.outbox_table}
                    (message_id, message_fingerprint, request_id, aggregate_type,
                     aggregate_id, event_id, topic, payload_digest, created_at,
                     available_at, published)
                VALUES (:message_id, :message_fingerprint, :request_id, :aggregate_type,
                        :aggregate_id, :event_id, :topic, :payload_digest, :created_at,
                        :available_at, FALSE)
                ON CONFLICT (message_id) DO NOTHING
                """
            ),
            {
                "message_id": message.message_id,
                "message_fingerprint": message.fingerprint,
                "request_id": message.request_id,
                "aggregate_type": message.aggregate_type,
                "aggregate_id": message.aggregate_id,
                "event_id": message.event_id,
                "topic": message.topic,
                "payload_digest": message.payload_digest,
                "created_at": _encode_datetime(message.created_at),
                "available_at": _encode_datetime(message.available_at),
            },
        )
        if getattr(outbox_result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL execution outbox insert lost a uniqueness race")

        next_cursor = resolution.cursor
        params = {
            "trial_id": next_cursor.trial_id,
            "attempt_id": next_cursor.attempt_id,
            "sequence": next_cursor.sequence,
            "last_event_id": next_cursor.last_event_id,
            "cursor_fingerprint": _cursor_fingerprint(next_cursor),
            "expected_sequence": next_cursor.sequence - 1,
        }
        if cursor_exists:
            cursor_result = await session.execute(
                _statement(
                    f"""
                    UPDATE {self._schema.cursor_table}
                    SET sequence = :sequence, last_event_id = :last_event_id,
                        cursor_fingerprint = :cursor_fingerprint
                    WHERE trial_id = :trial_id AND attempt_id = :attempt_id
                      AND sequence = :expected_sequence
                    """
                ),
                params,
            )
        else:
            cursor_result = await session.execute(
                _statement(
                    f"""
                    INSERT INTO {self._schema.cursor_table}
                        (trial_id, attempt_id, sequence, last_event_id, cursor_fingerprint)
                    VALUES (:trial_id, :attempt_id, :sequence, :last_event_id, :cursor_fingerprint)
                    ON CONFLICT (trial_id, attempt_id) DO NOTHING
                    """
                ),
                params,
            )
        if getattr(cursor_result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL execution cursor compare-and-set lost a race")


def _validate_cursor_against_events(
    cursor: EventStreamCursor, events: tuple[ExecutionEvent, ...]
) -> None:
    if cursor.sequence != len(events):
        raise ValueError("PostgreSQL execution cursor sequence does not match events")
    if cursor.last_event_id != (events[-1].event_id if events else None):
        raise ValueError("PostgreSQL execution cursor identity does not match events")


def _decode_cursor(row: Mapping[str, Any]) -> EventStreamCursor:
    try:
        cursor = EventStreamCursor(
            row["trial_id"],
            row["attempt_id"],
            int(row["sequence"]),
            row["last_event_id"],
        )
        if row["cursor_fingerprint"] != _cursor_fingerprint(cursor):
            raise ValueError("cursor fingerprint does not match bytes")
        return cursor
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL execution cursor row is malformed") from error


def _decode_event(row: Mapping[str, Any]) -> ExecutionEvent:
    try:
        event = ExecutionEvent(
            row["trial_id"],
            row["attempt_id"],
            int(row["sequence"]),
            ExecutionEventType(row["event_type"]),
            row["payload_digest"],
            _decode_datetime(row["occurred_at"], "occurred_at"),
            row["producer"],
            row["causation_id"],
        )
        if row["event_id"] != event.event_id or row["event_fingerprint"] != event.fingerprint:
            raise ValueError("event fingerprint does not match bytes")
        return event
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL execution event row is malformed") from error


def _decode_audit(row: Mapping[str, Any]) -> AuditEntry:
    try:
        entry = AuditEntry(
            row["aggregate_type"],
            row["aggregate_id"],
            int(row["sequence"]),
            AuditEntryType(row["entry_type"]),
            row["payload_digest"],
            _decode_datetime(row["occurred_at"], "occurred_at"),
            row["actor"],
            row["correlation_id"],
        )
        if row["entry_id"] != entry.entry_id or row["entry_fingerprint"] != entry.fingerprint:
            raise ValueError("audit fingerprint does not match bytes")
        return entry
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL execution audit row is malformed") from error


def _decode_outbox(row: Mapping[str, Any]) -> OutboxMessage:
    try:
        return OutboxMessage(
            row["request_id"],
            row["aggregate_type"],
            row["aggregate_id"],
            row["event_id"],
            row["topic"],
            row["payload_digest"],
            _decode_datetime(row["created_at"], "created_at"),
            _decode_datetime(row["available_at"], "available_at"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL execution outbox row is malformed") from error


def _cursor_fingerprint(cursor: EventStreamCursor) -> str:
    return content_digest(cursor)


def _encode_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _decode_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} is malformed") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


def _reject(
    event: ExecutionEvent,
    entry: AuditEntry,
    message: OutboxMessage,
    cursor: EventStreamCursor,
    journal: AuditJournal,
    outbox: OutboxState,
    reason: str,
) -> ExecutionEventTransactionResolution:
    return ExecutionEventTransactionResolution(
        ExecutionEventTransactionDecision.CONFLICT,
        cursor,
        journal,
        outbox,
        event.event_id,
        entry.entry_id,
        message.message_id,
        # The append was not attempted because the caller's cursor was stale.
        # CONFLICT is the only transaction decision that accurately preserves
        # the original states while exposing the compare-and-set failure.
        event_append_decision=EventAppendDecision.CONFLICT,
        rejection_reason=reason,
    )


__all__ = ["PostgresExecutionEventSchema", "PostgresExecutionEventTransactionAdapter"]
