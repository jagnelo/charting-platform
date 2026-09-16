"""Canonical execution event envelopes and append decisions.

Workers and adapters may transport these records through an outbox, Redis, or
an event store.  This module only defines deterministic identity and cursor
semantics; it performs no I/O and cannot turn an event into a simulator call.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


class ExecutionEventType(StrEnum):
    ATTEMPT_CREATED = "attempt_created"
    ATTEMPT_STATE_CHANGED = "attempt_state_changed"
    PROGRESS_UPDATED = "progress_updated"
    CANCELLATION_REQUESTED = "cancellation_requested"
    RECOVERY_PLANNED = "recovery_planned"
    ARTIFACT_VERIFIED = "artifact_verified"
    RESULT_PUBLISHED = "result_published"
    FORWARD_EVENT_APPLIED = "forward_event_applied"


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    """One immutable, content-addressed observation in an attempt stream."""

    trial_id: str
    attempt_id: str
    sequence: int
    event_type: ExecutionEventType
    payload_digest: str
    occurred_at: datetime
    producer: str
    causation_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("trial_id", "attempt_id", "producer"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"event {name} must not be empty")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("event sequence must be a positive integer")
        if not isinstance(self.event_type, ExecutionEventType):
            raise TypeError("event_type must be an ExecutionEventType")
        require_sha256_digest(self.payload_digest, field_name="payload_digest")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("event occurred_at must be timezone-aware")
        if self.causation_id is not None:
            require_sha256_digest(self.causation_id, field_name="causation_id")

    @property
    def event_id(self) -> str:
        """Stable identity over all event content, excluding no user field."""

        return content_digest(self)

    @property
    def fingerprint(self) -> str:
        return self.event_id


@dataclass(frozen=True, slots=True)
class EventStreamCursor:
    """Last committed event in one trial/attempt stream."""

    trial_id: str
    attempt_id: str
    sequence: int = 0
    last_event_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("trial_id", "attempt_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"cursor {name} must not be empty")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 0:
            raise ValueError("cursor sequence must be non-negative")
        if self.sequence == 0 and self.last_event_id is not None:
            raise ValueError("an empty cursor cannot contain a last event")
        if self.sequence > 0 and self.last_event_id is None:
            raise ValueError("a non-empty cursor requires the last event identity")
        if self.last_event_id is not None:
            require_sha256_digest(self.last_event_id, field_name="last_event_id")


class EventAppendDecision(StrEnum):
    APPEND = "append"
    REPLAY_EXISTING = "replay_existing"
    GAP = "gap"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class EventAppendResolution:
    """Pure result for an adapter's atomic append/replay operation."""

    decision: EventAppendDecision
    event_id: str
    cursor: EventStreamCursor
    expected_sequence: int

    def __post_init__(self) -> None:
        if not isinstance(self.decision, EventAppendDecision):
            raise TypeError("decision must be an EventAppendDecision")
        require_sha256_digest(self.event_id, field_name="event_id")
        if not isinstance(self.cursor, EventStreamCursor):
            raise TypeError("cursor must be an EventStreamCursor")
        if not isinstance(self.expected_sequence, int) or isinstance(self.expected_sequence, bool):
            raise ValueError("expected_sequence must be an integer")
        if self.expected_sequence < 1:
            raise ValueError("expected_sequence must be positive")


def resolve_event_append(
    event: ExecutionEvent,
    cursor: EventStreamCursor,
    prior_events: Sequence[ExecutionEvent] = (),
) -> EventAppendResolution:
    """Resolve one event against a committed cursor without mutating storage.

    An exact prior event is replayable.  A new event must be the next
    contiguous sequence; missing or stale sequences are surfaced instead of
    silently advancing state.  Adapters must perform the final atomic
    compare-and-set using this resolution.
    """

    if not isinstance(event, ExecutionEvent):
        raise TypeError("event must be an ExecutionEvent")
    if not isinstance(cursor, EventStreamCursor):
        raise TypeError("cursor must be an EventStreamCursor")
    if not isinstance(prior_events, Sequence) or isinstance(prior_events, str | bytes):
        raise TypeError("prior_events must be a sequence")
    previous = tuple(prior_events)
    if any(not isinstance(item, ExecutionEvent) for item in previous):
        raise TypeError("prior_events must contain ExecutionEvent values")
    if event.trial_id != cursor.trial_id or event.attempt_id != cursor.attempt_id:
        raise ValueError("event must reference the cursor trial and attempt")
    scoped = tuple(
        item
        for item in previous
        if item.trial_id == cursor.trial_id and item.attempt_id == cursor.attempt_id
    )
    if any(item.event_id == event.event_id for item in scoped):
        if any(item != event for item in scoped if item.event_id == event.event_id):
            raise ValueError("event identity collides with different event content")
        return EventAppendResolution(
            EventAppendDecision.REPLAY_EXISTING,
            event.event_id,
            cursor,
            cursor.sequence + 1,
        )
    expected = cursor.sequence + 1
    if event.sequence < expected:
        return EventAppendResolution(EventAppendDecision.CONFLICT, event.event_id, cursor, expected)
    if event.sequence > expected:
        return EventAppendResolution(EventAppendDecision.GAP, event.event_id, cursor, expected)
    next_cursor = EventStreamCursor(
        trial_id=cursor.trial_id,
        attempt_id=cursor.attempt_id,
        sequence=event.sequence,
        last_event_id=event.event_id,
    )
    return EventAppendResolution(
        EventAppendDecision.APPEND,
        event.event_id,
        next_cursor,
        expected,
    )
