"""Append-only execution audit journal contracts.

The journal is a storage-neutral boundary for durable audit records.  It does
not write PostgreSQL, publish an outbox message, or infer an execution result;
an adapter must atomically persist the resolution returned here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class AuditEntryType(StrEnum):
    AUTHORIZATION_GRANTED = "authorization_granted"
    WORKER_RESERVED = "worker_reserved"
    LEASE_OBSERVED = "lease_observed"
    PROGRESS_RECORDED = "progress_recorded"
    OUTCOME_RECORDED = "outcome_recorded"
    ARTIFACT_COMMITTED = "artifact_committed"
    REPLAY_PLANNED = "replay_planned"


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One immutable audit observation in an aggregate's append-only stream."""

    aggregate_type: str
    aggregate_id: str
    sequence: int
    entry_type: AuditEntryType
    payload_digest: str
    occurred_at: datetime
    actor: str
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        _nonempty(self.aggregate_type, "aggregate_type")
        _nonempty(self.aggregate_id, "aggregate_id")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("audit sequence must be a positive integer")
        if not isinstance(self.entry_type, AuditEntryType):
            raise TypeError("entry_type must be an AuditEntryType")
        require_sha256_digest(self.payload_digest, field_name="payload_digest")
        _aware(self.occurred_at, "occurred_at")
        _nonempty(self.actor, "actor")
        if self.correlation_id is not None:
            require_sha256_digest(self.correlation_id, field_name="correlation_id")

    @property
    def entry_id(self) -> str:
        """Stable identity over the complete audit content."""

        return content_digest(self)

    @property
    def fingerprint(self) -> str:
        return self.entry_id


@dataclass(frozen=True, slots=True)
class AuditJournal:
    """Validated immutable journal for exactly one aggregate."""

    aggregate_type: str
    aggregate_id: str
    entries: tuple[AuditEntry, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.aggregate_type, "aggregate_type")
        _nonempty(self.aggregate_id, "aggregate_id")
        if not isinstance(self.entries, tuple):
            raise TypeError("entries must be a tuple")
        previous: AuditEntry | None = None
        identities: set[str] = set()
        for expected, entry in enumerate(self.entries, start=1):
            if not isinstance(entry, AuditEntry):
                raise TypeError("entries must contain AuditEntry values")
            if entry.aggregate_type != self.aggregate_type or entry.aggregate_id != self.aggregate_id:
                raise ValueError("journal entries must reference the journal aggregate")
            if entry.sequence != expected:
                raise ValueError("journal entries must be contiguous")
            if entry.entry_id in identities:
                raise ValueError("journal entries must have unique identities")
            if previous is not None and entry.occurred_at < previous.occurred_at:
                raise ValueError("journal entries must not regress occurred_at")
            identities.add(entry.entry_id)
            previous = entry

    @property
    def next_sequence(self) -> int:
        return len(self.entries) + 1

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class AuditAppendDecision(StrEnum):
    APPEND = "append"
    REPLAY_EXISTING = "replay_existing"
    GAP = "gap"
    STALE = "stale"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class AuditAppendResolution:
    """Pure result for an adapter's atomic journal append operation."""

    decision: AuditAppendDecision
    journal: AuditJournal
    entry_id: str
    expected_sequence: int
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, AuditAppendDecision):
            raise TypeError("decision must be an AuditAppendDecision")
        if not isinstance(self.journal, AuditJournal):
            raise TypeError("journal must be an AuditJournal")
        require_sha256_digest(self.entry_id, field_name="entry_id")
        if not isinstance(self.expected_sequence, int) or isinstance(self.expected_sequence, bool):
            raise ValueError("expected_sequence must be an integer")
        if self.expected_sequence < 1:
            raise ValueError("expected_sequence must be positive")
        if self.decision is AuditAppendDecision.REJECT and not self.rejection_reason:
            raise ValueError("rejected audit appends require a reason")
        if self.decision is not AuditAppendDecision.REJECT and self.rejection_reason:
            raise ValueError("successful or sequencing resolutions cannot contain a reason")


def append_audit_entry(
    journal: AuditJournal,
    entry: AuditEntry,
    prior_entries: Sequence[AuditEntry] = (),
) -> AuditAppendResolution:
    """Resolve one append against the current journal without mutating storage.

    ``prior_entries`` lets an adapter prove exact replay or identity collision
    without making the pure contract own persistence.  The journal itself is
    always the returned state, and only the expected contiguous next sequence
    can advance it.
    """

    if not isinstance(journal, AuditJournal):
        raise TypeError("journal must be an AuditJournal")
    if not isinstance(entry, AuditEntry):
        raise TypeError("entry must be an AuditEntry")
    if not isinstance(prior_entries, Sequence) or isinstance(prior_entries, str | bytes):
        raise TypeError("prior_entries must be a sequence")
    prior = tuple(prior_entries)
    if any(not isinstance(item, AuditEntry) for item in prior):
        raise TypeError("prior_entries must contain AuditEntry values")
    if entry.aggregate_type != journal.aggregate_type or entry.aggregate_id != journal.aggregate_id:
        return AuditAppendResolution(
            AuditAppendDecision.REJECT,
            journal,
            entry.entry_id,
            journal.next_sequence,
            "entry must reference the journal aggregate",
        )
    scoped = tuple(
        item
        for item in (*journal.entries, *prior)
        if item.aggregate_type == journal.aggregate_type and item.aggregate_id == journal.aggregate_id
    )
    matches = tuple(item for item in scoped if item.entry_id == entry.entry_id)
    if matches:
        if any(item != entry for item in matches):
            return AuditAppendResolution(
                AuditAppendDecision.CONFLICT,
                journal,
                entry.entry_id,
                journal.next_sequence,
            )
        return AuditAppendResolution(
            AuditAppendDecision.REPLAY_EXISTING,
            journal,
            entry.entry_id,
            journal.next_sequence,
        )
    same_sequence = tuple(item for item in scoped if item.sequence == entry.sequence)
    if same_sequence:
        return AuditAppendResolution(
            AuditAppendDecision.CONFLICT,
            journal,
            entry.entry_id,
            journal.next_sequence,
        )
    expected = journal.next_sequence
    if entry.sequence > expected:
        return AuditAppendResolution(AuditAppendDecision.GAP, journal, entry.entry_id, expected)
    if entry.sequence < expected:
        return AuditAppendResolution(AuditAppendDecision.STALE, journal, entry.entry_id, expected)
    if journal.entries and entry.occurred_at < journal.entries[-1].occurred_at:
        return AuditAppendResolution(
            AuditAppendDecision.REJECT,
            journal,
            entry.entry_id,
            expected,
            "audit occurred_at regresses the journal",
        )
    return AuditAppendResolution(
        AuditAppendDecision.APPEND,
        AuditJournal(journal.aggregate_type, journal.aggregate_id, (*journal.entries, entry)),
        entry.entry_id,
        expected,
    )
