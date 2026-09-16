from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.audit import AuditEntry, AuditEntryType, AuditJournal
from app.strategy_lab_v2.audit_outbox import AuditOutboxDecision
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.events import (
    EventAppendDecision,
    EventStreamCursor,
    ExecutionEvent,
    ExecutionEventType,
)
from app.strategy_lab_v2.execution_event_transaction import (
    ExecutionEventTransactionDecision,
    resolve_execution_event_transaction,
)
from app.strategy_lab_v2.outbox import OutboxMessage, OutboxState

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _event(sequence: int = 1, *, payload: str = "progress") -> ExecutionEvent:
    return ExecutionEvent(
        "trial-1",
        "attempt-1",
        sequence,
        ExecutionEventType.PROGRESS_UPDATED,
        content_digest(payload),
        NOW + timedelta(minutes=sequence),
        "worker-1",
    )


def _evidence(event: ExecutionEvent, *, request: str = "request") -> tuple[AuditEntry, OutboxMessage]:
    entry = AuditEntry(
        "run_attempt",
        event.attempt_id,
        event.sequence,
        AuditEntryType.PROGRESS_RECORDED,
        event.payload_digest,
        event.occurred_at,
        event.producer,
        event.event_id,
    )
    message = OutboxMessage(
        content_digest(request),
        "run_attempt",
        event.attempt_id,
        entry.entry_id,
        "strategy-lab.execution-events",
        event.payload_digest,
        event.occurred_at,
        event.occurred_at,
    )
    return entry, message


def _resolve(event: ExecutionEvent, **kwargs):
    entry, message = _evidence(event, **kwargs.pop("evidence", {}))
    return resolve_execution_event_transaction(
        event,
        EventStreamCursor(event.trial_id, event.attempt_id),
        AuditJournal("run_attempt", event.attempt_id),
        entry,
        OutboxState(),
        message,
        **kwargs,
    )


def test_event_audit_and_outbox_commit_together() -> None:
    event = _event()
    result = _resolve(event)
    assert result.decision is ExecutionEventTransactionDecision.COMMITTED
    assert result.event_append_decision is EventAppendDecision.APPEND
    assert result.audit_outbox_decision is AuditOutboxDecision.COMMIT
    assert result.cursor.sequence == 1
    assert result.journal.entries[0].correlation_id == event.event_id
    assert result.outbox.messages[0].event_id == result.journal.entries[0].entry_id
    assert result.fingerprint.startswith("sha256:")


def test_exact_retry_replays_without_changing_any_stream() -> None:
    event = _event()
    first = _resolve(event)
    entry, message = _evidence(event)
    replay = resolve_execution_event_transaction(
        event,
        first.cursor,
        first.journal,
        entry,
        first.outbox,
        message,
        prior_events=(event,),
    )
    assert replay.decision is ExecutionEventTransactionDecision.REPLAY_EXISTING
    assert replay.event_append_decision is EventAppendDecision.REPLAY_EXISTING
    assert replay.audit_outbox_decision is AuditOutboxDecision.REPLAY_EXISTING
    assert replay.cursor == first.cursor
    assert replay.journal == first.journal
    assert replay.outbox == first.outbox


def test_event_gap_rolls_back_audit_and_outbox() -> None:
    event = _event(sequence=2)
    result = _resolve(event)
    assert result.decision is ExecutionEventTransactionDecision.GAP
    assert result.event_append_decision is EventAppendDecision.GAP
    assert result.journal.entries == ()
    assert result.outbox.messages == ()
    assert result.rejection_reason == "execution event sequence has a gap"


def test_audit_gap_rolls_back_event_cursor() -> None:
    event = _event()
    entry, message = _evidence(event)
    gap_entry = AuditEntry(
        entry.aggregate_type,
        entry.aggregate_id,
        3,
        entry.entry_type,
        entry.payload_digest,
        entry.occurred_at,
        entry.actor,
        entry.correlation_id,
    )
    result = resolve_execution_event_transaction(
        event,
        EventStreamCursor(event.trial_id, event.attempt_id),
        AuditJournal(entry.aggregate_type, entry.aggregate_id, (entry,)),
        gap_entry,
        OutboxState(),
        OutboxMessage(
            message.request_id,
            message.aggregate_type,
            message.aggregate_id,
            gap_entry.entry_id,
            message.topic,
            message.payload_digest,
            message.created_at,
            message.available_at,
        ),
    )
    assert result.decision is ExecutionEventTransactionDecision.GAP
    assert result.cursor.sequence == 0
    assert result.journal.entries == (entry,)
    assert result.outbox.messages == ()
    assert result.audit_outbox_decision is AuditOutboxDecision.GAP


def test_outbox_conflict_rolls_back_event_and_audit() -> None:
    event = _event()
    entry, message = _evidence(event)
    existing = resolve_execution_event_transaction(
        event,
        EventStreamCursor(event.trial_id, event.attempt_id),
        AuditJournal("run_attempt", event.attempt_id),
        entry,
        OutboxState(),
        message,
    )
    changed_entry = AuditEntry(
        entry.aggregate_type,
        entry.aggregate_id,
        entry.sequence,
        entry.entry_type,
        content_digest("changed-payload"),
        entry.occurred_at,
        entry.actor,
        entry.correlation_id,
    )
    _, changed_message = _evidence(event, request="changed")
    conflict_message = OutboxMessage(
        message.request_id,
        changed_message.aggregate_type,
        changed_message.aggregate_id,
        changed_entry.entry_id,
        changed_message.topic,
        changed_message.payload_digest,
        changed_message.created_at,
        changed_message.available_at,
    )
    result = resolve_execution_event_transaction(
        event,
        EventStreamCursor(event.trial_id, event.attempt_id),
        AuditJournal("run_attempt", event.attempt_id),
        changed_entry,
        OutboxState(messages=(message,)),
        conflict_message,
    )
    assert existing.decision is ExecutionEventTransactionDecision.COMMITTED
    assert result.decision is ExecutionEventTransactionDecision.CONFLICT
    assert result.cursor.sequence == 0
    assert result.journal.entries == ()
    assert result.outbox.messages == (message,)


def test_identity_mismatch_is_rejected_before_any_append() -> None:
    event = _event()
    entry, message = _evidence(event)
    foreign_entry = AuditEntry(
        entry.aggregate_type,
        "other-attempt",
        entry.sequence,
        entry.entry_type,
        entry.payload_digest,
        entry.occurred_at,
        entry.actor,
        entry.correlation_id,
    )
    result = resolve_execution_event_transaction(
        event,
        EventStreamCursor(event.trial_id, event.attempt_id),
        AuditJournal("run_attempt", event.attempt_id),
        foreign_entry,
        OutboxState(),
        message,
    )
    assert result.decision is ExecutionEventTransactionDecision.REJECT
    assert result.cursor.sequence == 0
    assert result.journal.entries == ()
    assert result.outbox.messages == ()
    assert "event attempt" in (result.rejection_reason or "")


def test_invalid_types_fail_closed() -> None:
    event = _event()
    entry, message = _evidence(event)
    with pytest.raises(TypeError, match="cursor"):
        resolve_execution_event_transaction(
            event,
            "bad",  # type: ignore[arg-type]
            AuditJournal("run_attempt", event.attempt_id),
            entry,
            OutboxState(),
            message,
        )
