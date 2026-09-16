"""Atomic execution-event, audit, and outbox staging contract.

An execution event is only considered committed when its canonical stream
append and the linked audit/outbox records can be staged together.  This
module deliberately returns immutable proposed states: a persistence adapter
must still apply the result with one compare-and-set transaction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.audit import AuditEntry, AuditJournal
from app.strategy_lab_v2.audit_outbox import (
    AuditOutboxDecision,
    AuditOutboxResolution,
    stage_audit_outbox,
)
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.events import (
    EventAppendDecision,
    EventStreamCursor,
    ExecutionEvent,
    resolve_event_append,
)
from app.strategy_lab_v2.outbox import OutboxMessage, OutboxState


class ExecutionEventTransactionDecision(StrEnum):
    """Result of the linked event/audit/outbox resolution."""

    COMMITTED = "committed"
    REPLAY_EXISTING = "replay_existing"
    GAP = "gap"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ExecutionEventTransactionResolution:
    """All proposed states and decisions for one execution event transaction."""

    decision: ExecutionEventTransactionDecision
    cursor: EventStreamCursor
    journal: AuditJournal
    outbox: OutboxState
    event_id: str
    audit_entry_id: str
    message_id: str
    event_append_decision: EventAppendDecision
    audit_outbox_decision: AuditOutboxDecision | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ExecutionEventTransactionDecision):
            raise TypeError("decision must be an ExecutionEventTransactionDecision")
        if not isinstance(self.cursor, EventStreamCursor):
            raise TypeError("cursor must be an EventStreamCursor")
        if not isinstance(self.journal, AuditJournal):
            raise TypeError("journal must be an AuditJournal")
        if not isinstance(self.outbox, OutboxState):
            raise TypeError("outbox must be an OutboxState")
        require_sha256_digest(self.event_id, field_name="event_id")
        require_sha256_digest(self.audit_entry_id, field_name="audit_entry_id")
        require_sha256_digest(self.message_id, field_name="message_id")
        if not isinstance(self.event_append_decision, EventAppendDecision):
            raise TypeError("event_append_decision must be an EventAppendDecision")
        if self.audit_outbox_decision is not None and not isinstance(
            self.audit_outbox_decision, AuditOutboxDecision
        ):
            raise TypeError("audit_outbox_decision must be an AuditOutboxDecision")
        if self.decision in {
            ExecutionEventTransactionDecision.GAP,
            ExecutionEventTransactionDecision.CONFLICT,
            ExecutionEventTransactionDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("failed resolutions require a rejection reason")
        if self.decision in {
            ExecutionEventTransactionDecision.COMMITTED,
            ExecutionEventTransactionDecision.REPLAY_EXISTING,
        } and self.rejection_reason:
            raise ValueError("successful resolutions cannot contain a rejection reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def resolve_execution_event_transaction(
    event: ExecutionEvent,
    cursor: EventStreamCursor,
    journal: AuditJournal,
    entry: AuditEntry,
    outbox: OutboxState,
    message: OutboxMessage,
    *,
    prior_events: Sequence[ExecutionEvent] = (),
    prior_entries: Sequence[AuditEntry] = (),
    prior_messages: Sequence[OutboxMessage] = (),
) -> ExecutionEventTransactionResolution:
    """Resolve one event and its audit/outbox evidence as one all-or-nothing change.

    The audit entry's correlation identity must point at the canonical event,
    while the outbox message remains linked to the audit entry as required by
    :func:`stage_audit_outbox`.  If either stream has a gap, conflict, or
    rejection, every returned state is the original state.
    """

    values = (event, cursor, journal, entry, outbox, message)
    expected_types = (
        ExecutionEvent,
        EventStreamCursor,
        AuditJournal,
        AuditEntry,
        OutboxState,
        OutboxMessage,
    )
    names = ("event", "cursor", "journal", "entry", "outbox", "message")
    for name, value, expected in zip(names, values, expected_types, strict=True):
        if not isinstance(value, expected):
            raise TypeError(f"{name} must be a {expected.__name__}")

    event_id = event.event_id
    audit_entry_id = entry.entry_id
    message_id = message.message_id

    def reject(reason: str, *, decision: ExecutionEventTransactionDecision = ExecutionEventTransactionDecision.REJECT,
               append_decision: EventAppendDecision = EventAppendDecision.CONFLICT,
               outbox_decision: AuditOutboxDecision | None = None) -> ExecutionEventTransactionResolution:
        return ExecutionEventTransactionResolution(
            decision,
            cursor,
            journal,
            outbox,
            event_id,
            audit_entry_id,
            message_id,
            append_decision,
            outbox_decision,
            reason,
        )

    if entry.aggregate_id != event.attempt_id:
        return reject("audit entry must reference the event attempt")
    if entry.correlation_id != event_id:
        return reject("audit entry correlation_id must match the canonical event")
    if message.event_id != audit_entry_id:
        return reject("outbox event identity must match the audit entry")

    try:
        appended = resolve_event_append(event, cursor, prior_events)
    except (TypeError, ValueError) as error:
        return reject(str(error))
    if appended.decision is EventAppendDecision.GAP:
        return reject(
            "execution event sequence has a gap",
            decision=ExecutionEventTransactionDecision.GAP,
            append_decision=appended.decision,
        )
    if appended.decision is EventAppendDecision.CONFLICT:
        return reject(
            "execution event sequence conflicts with the cursor",
            decision=ExecutionEventTransactionDecision.CONFLICT,
            append_decision=appended.decision,
        )

    try:
        staged: AuditOutboxResolution = stage_audit_outbox(
            journal,
            entry,
            outbox,
            message,
            prior_entries=prior_entries,
            prior_messages=prior_messages,
        )
    except (TypeError, ValueError) as error:
        return reject(str(error), append_decision=appended.decision)
    if staged.decision in {
        AuditOutboxDecision.GAP,
        AuditOutboxDecision.CONFLICT,
        AuditOutboxDecision.REJECT,
    }:
        transaction_decision = (
            ExecutionEventTransactionDecision.GAP
            if staged.decision is AuditOutboxDecision.GAP
            else ExecutionEventTransactionDecision.CONFLICT
            if staged.decision is AuditOutboxDecision.CONFLICT
            else ExecutionEventTransactionDecision.REJECT
        )
        return reject(
            "audit and outbox evidence cannot be staged",
            decision=transaction_decision,
            append_decision=appended.decision,
            outbox_decision=staged.decision,
        )

    replay = (
        appended.decision is EventAppendDecision.REPLAY_EXISTING
        and staged.decision is AuditOutboxDecision.REPLAY_EXISTING
    )
    return ExecutionEventTransactionResolution(
        ExecutionEventTransactionDecision.REPLAY_EXISTING
        if replay
        else ExecutionEventTransactionDecision.COMMITTED,
        appended.cursor,
        staged.journal,
        staged.outbox,
        event_id,
        audit_entry_id,
        message_id,
        appended.decision,
        staged.decision,
    )
