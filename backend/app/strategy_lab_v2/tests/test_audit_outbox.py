from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.audit import AuditEntry, AuditEntryType, AuditJournal
from app.strategy_lab_v2.audit_outbox import (
    AuditOutboxDecision,
    stage_audit_outbox,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.outbox import OutboxMessage, OutboxState

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _entry() -> AuditEntry:
    return AuditEntry(
        "run_attempt", "attempt-1", 1, AuditEntryType.OUTCOME_RECORDED,
        content_digest("outcome"), NOW, "worker-1",
    )


def _message(entry: AuditEntry, *, request: str = "request") -> OutboxMessage:
    return OutboxMessage(
        content_digest(request), "run_attempt", "attempt-1", entry.entry_id,
        "strategy-lab.events", content_digest("audit-payload"), NOW, NOW,
    )


def test_linked_audit_and_outbox_commit_together() -> None:
    entry = _entry()
    result = stage_audit_outbox(
        AuditJournal("run_attempt", "attempt-1"), entry,
        OutboxState(), _message(entry),
    )
    assert result.decision is AuditOutboxDecision.COMMIT
    assert result.journal.entries == (entry,)
    assert result.outbox.messages[0].event_id == entry.entry_id


def test_exact_pair_retry_replays_without_state_change() -> None:
    entry = _entry()
    journal = AuditJournal("run_attempt", "attempt-1")
    outbox = OutboxState()
    applied = stage_audit_outbox(journal, entry, outbox, _message(entry))
    replay = stage_audit_outbox(applied.journal, entry, applied.outbox, _message(entry))
    assert replay.decision is AuditOutboxDecision.REPLAY_EXISTING
    assert replay.journal == applied.journal
    assert replay.outbox == applied.outbox


def test_audit_gap_keeps_outbox_unchanged() -> None:
    entry = AuditEntry(
        "run_attempt", "attempt-1", 2, AuditEntryType.OUTCOME_RECORDED,
        content_digest("outcome"), NOW, "worker-1",
    )
    outbox = OutboxState()
    result = stage_audit_outbox(AuditJournal("run_attempt", "attempt-1"), entry, outbox, _message(entry))
    assert result.decision is AuditOutboxDecision.GAP
    assert result.journal.entries == ()
    assert result.outbox == outbox


def test_outbox_request_conflict_keeps_journal_unchanged() -> None:
    entry = _entry()
    applied = stage_audit_outbox(AuditJournal("run_attempt", "attempt-1"), entry, OutboxState(), _message(entry))
    changed = OutboxMessage(
        _message(entry).request_id, "run_attempt", "attempt-1", entry.entry_id,
        "strategy-lab.events", content_digest("different-payload"), NOW, NOW,
    )
    result = stage_audit_outbox(applied.journal, entry, applied.outbox, changed)
    assert result.decision is AuditOutboxDecision.CONFLICT
    assert result.journal == applied.journal
    assert result.outbox == applied.outbox


def test_identity_mismatch_rejects_before_either_resolution() -> None:
    entry = _entry()
    foreign = OutboxMessage(
        content_digest("request"), "run_attempt", "attempt-1", content_digest("other-event"),
        "strategy-lab.events", content_digest("audit-payload"), NOW, NOW,
    )
    result = stage_audit_outbox(AuditJournal("run_attempt", "attempt-1"), entry, OutboxState(), foreign)
    assert result.decision is AuditOutboxDecision.REJECT
    assert result.journal.entries == ()
    assert result.outbox.messages == ()


def test_types_and_resolution_contract_fail_closed() -> None:
    entry = _entry()
    with pytest.raises(TypeError, match="journal"):
        stage_audit_outbox("bad", entry, OutboxState(), _message(entry))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-committing resolutions"):
        from app.strategy_lab_v2.audit_outbox import AuditOutboxResolution

        AuditOutboxResolution(
            AuditOutboxDecision.REJECT,
            AuditJournal("run_attempt", "attempt-1"),
            OutboxState(), entry.entry_id, _message(entry).message_id,
        )
