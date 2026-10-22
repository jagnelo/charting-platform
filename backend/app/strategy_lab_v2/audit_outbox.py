"""Atomic audit-journal and transactional-outbox staging contract."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.audit import (
    AuditAppendDecision,
    AuditEntry,
    AuditJournal,
    append_audit_entry,
)
from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.outbox import (
    OutboxEnqueueDecision,
    OutboxMessage,
    OutboxState,
    resolve_outbox_enqueue,
)


class AuditOutboxDecision(StrEnum):
    COMMIT = "commit"
    REPLAY_EXISTING = "replay_existing"
    GAP = "gap"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class AuditOutboxResolution:
    """Pure result for one atomic journal-plus-outbox staging operation."""

    decision: AuditOutboxDecision
    journal: AuditJournal
    outbox: OutboxState
    audit_entry_id: str
    message_id: str
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, AuditOutboxDecision):
            raise TypeError("decision must be an AuditOutboxDecision")
        if not isinstance(self.journal, AuditJournal):
            raise TypeError("journal must be an AuditJournal")
        if not isinstance(self.outbox, OutboxState):
            raise TypeError("outbox must be an OutboxState")
        require_sha256_digest(self.audit_entry_id, field_name="audit_entry_id")
        require_sha256_digest(self.message_id, field_name="message_id")
        if self.decision in {
            AuditOutboxDecision.GAP,
            AuditOutboxDecision.CONFLICT,
            AuditOutboxDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("non-committing resolutions require a reason")
        if self.decision in {
            AuditOutboxDecision.COMMIT,
            AuditOutboxDecision.REPLAY_EXISTING,
        } and self.rejection_reason:
            raise ValueError("successful resolutions cannot contain a reason")


def _failed(decision: AuditAppendDecision | OutboxEnqueueDecision) -> AuditOutboxDecision | None:
    if decision in {AuditAppendDecision.GAP, OutboxEnqueueDecision.REJECT}:
        return AuditOutboxDecision.GAP if decision is AuditAppendDecision.GAP else AuditOutboxDecision.REJECT
    if decision is AuditAppendDecision.CONFLICT or decision is OutboxEnqueueDecision.CONFLICT:
        return AuditOutboxDecision.CONFLICT
    if decision is AuditAppendDecision.REJECT:
        return AuditOutboxDecision.REJECT
    return None


def stage_audit_outbox(
    journal: AuditJournal,
    entry: AuditEntry,
    outbox: OutboxState,
    message: OutboxMessage,
    *,
    prior_entries: Sequence[AuditEntry] = (),
    prior_messages: Sequence[OutboxMessage] = (),
) -> AuditOutboxResolution:
    """Resolve linked audit and outbox changes as one adapter transaction.

    The envelope's event identity must be the audit entry identity.  Any gap,
    conflict, or rejection returns the original pair of states so a database
    transaction cannot accidentally persist only one side of the link.
    """

    if not isinstance(journal, AuditJournal):
        raise TypeError("journal must be an AuditJournal")
    if not isinstance(entry, AuditEntry):
        raise TypeError("entry must be an AuditEntry")
    if not isinstance(outbox, OutboxState):
        raise TypeError("outbox must be an OutboxState")
    if not isinstance(message, OutboxMessage):
        raise TypeError("message must be an OutboxMessage")
    if message.event_id != entry.entry_id:
        return AuditOutboxResolution(
            AuditOutboxDecision.REJECT,
            journal,
            outbox,
            entry.entry_id,
            message.message_id,
            "outbox event identity must match the audit entry",
        )
    audit = append_audit_entry(journal, entry, prior_entries)
    staged = resolve_outbox_enqueue(outbox, message, prior_messages)
    failed_audit = _failed(audit.decision)
    failed_outbox = _failed(staged.decision)
    failure = failed_audit or failed_outbox
    if failure is not None:
        reason = (
            "audit append cannot be staged"
            if failed_audit is not None
            else "outbox enqueue cannot be staged"
        )
        return AuditOutboxResolution(
            failure, journal, outbox, entry.entry_id, message.message_id, reason
        )
    if (
        audit.decision is AuditAppendDecision.REPLAY_EXISTING
        and staged.decision is OutboxEnqueueDecision.REPLAY_EXISTING
    ):
        return AuditOutboxResolution(
            AuditOutboxDecision.REPLAY_EXISTING,
            journal,
            outbox,
            entry.entry_id,
            message.message_id,
        )
    return AuditOutboxResolution(
        AuditOutboxDecision.COMMIT,
        audit.journal,
        staged.state,
        entry.entry_id,
        message.message_id,
    )
