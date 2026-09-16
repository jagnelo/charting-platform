from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.audit import (
    AuditAppendDecision,
    AuditEntry,
    AuditEntryType,
    AuditJournal,
    append_audit_entry,
)
from app.strategy_lab_v2.canonical import content_digest

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _entry(sequence: int, value: str = "one", *, occurred_at: datetime | None = None) -> AuditEntry:
    return AuditEntry(
        aggregate_type="run_attempt",
        aggregate_id="attempt-1",
        sequence=sequence,
        entry_type=AuditEntryType.PROGRESS_RECORDED,
        payload_digest=content_digest({"value": value}),
        occurred_at=occurred_at or NOW + timedelta(seconds=sequence),
        actor="worker-1",
        correlation_id=content_digest("correlation"),
    )


def test_append_is_contiguous_and_exact_retry_replays() -> None:
    journal = AuditJournal("run_attempt", "attempt-1")
    first = _entry(1)
    applied = append_audit_entry(journal, first)
    assert applied.decision is AuditAppendDecision.APPEND
    assert applied.expected_sequence == 1
    assert applied.journal.entries == (first,)
    replay = append_audit_entry(applied.journal, first, (first,))
    assert replay.decision is AuditAppendDecision.REPLAY_EXISTING
    assert replay.journal == applied.journal
    assert first.entry_id == first.fingerprint


def test_gaps_and_sequence_content_conflicts_are_explicit() -> None:
    first = _entry(1)
    journal = append_audit_entry(AuditJournal("run_attempt", "attempt-1"), first).journal
    gap = append_audit_entry(journal, _entry(3))
    assert gap.decision is AuditAppendDecision.GAP
    assert gap.expected_sequence == 2
    stale = append_audit_entry(journal, _entry(1, "changed"))
    assert stale.decision is AuditAppendDecision.CONFLICT
    assert stale.journal == journal


def test_same_sequence_different_content_conflicts_without_mutation() -> None:
    first = _entry(1)
    journal = append_audit_entry(AuditJournal("run_attempt", "attempt-1"), first).journal
    changed = _entry(1, "changed")
    conflict = append_audit_entry(journal, changed)
    assert conflict.decision is AuditAppendDecision.CONFLICT
    assert conflict.journal == journal


def test_foreign_aggregate_is_rejected_without_mutation() -> None:
    journal = AuditJournal("run_attempt", "attempt-1")
    foreign = AuditEntry(
        "forward_instance", "forward-1", 1, AuditEntryType.REPLAY_PLANNED,
        content_digest("payload"), NOW, "operator",
    )
    rejected = append_audit_entry(journal, foreign)
    assert rejected.decision is AuditAppendDecision.REJECT
    assert "aggregate" in (rejected.rejection_reason or "")
    assert rejected.journal == journal


def test_timestamp_regression_is_rejected() -> None:
    first = _entry(1)
    journal = append_audit_entry(AuditJournal("run_attempt", "attempt-1"), first).journal
    regressed = append_audit_entry(journal, _entry(2, occurred_at=NOW))
    assert regressed.decision is AuditAppendDecision.REJECT
    assert "occurred_at" in (regressed.rejection_reason or "")


def test_journal_validates_identity_order_and_types() -> None:
    first = _entry(1)
    with pytest.raises(ValueError, match="contiguous"):
        AuditJournal("run_attempt", "attempt-1", (_entry(2),))
    with pytest.raises(ValueError, match="aggregate"):
        AuditJournal("run_attempt", "attempt-1", (AuditEntry(
            "other", "attempt-1", 1, AuditEntryType.PROGRESS_RECORDED,
            first.payload_digest, NOW, "worker-1",
        ),))
    with pytest.raises(TypeError, match="entries"):
        AuditJournal("run_attempt", "attempt-1", [first])  # type: ignore[arg-type]


def test_entry_requires_digest_timezone_and_actor() -> None:
    with pytest.raises(ValueError, match="payload_digest"):
        AuditEntry("run_attempt", "attempt-1", 1, AuditEntryType.OUTCOME_RECORDED, "bad", NOW, "worker")
    with pytest.raises(ValueError, match="timezone-aware"):
        AuditEntry("run_attempt", "attempt-1", 1, AuditEntryType.OUTCOME_RECORDED, content_digest("p"), datetime(2024, 1, 1), "worker")
    with pytest.raises(ValueError, match="actor"):
        AuditEntry("run_attempt", "attempt-1", 1, AuditEntryType.OUTCOME_RECORDED, content_digest("p"), NOW, "")
