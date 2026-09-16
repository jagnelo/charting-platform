from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.events import (
    EventAppendDecision,
    EventStreamCursor,
    ExecutionEvent,
    ExecutionEventType,
    resolve_event_append,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
PAYLOAD_DIGEST = content_digest({"payload": "state"})


def _event(sequence: int, *, attempt_id: str = "attempt-1") -> ExecutionEvent:
    return ExecutionEvent(
        trial_id="trial-1",
        attempt_id=attempt_id,
        sequence=sequence,
        event_type=ExecutionEventType.PROGRESS_UPDATED,
        payload_digest=PAYLOAD_DIGEST,
        occurred_at=NOW + timedelta(seconds=sequence),
        producer="worker-1",
    )


def test_event_identity_and_contiguous_append_are_deterministic() -> None:
    cursor = EventStreamCursor("trial-1", "attempt-1")
    first = _event(1)
    result = resolve_event_append(first, cursor)
    assert result.decision is EventAppendDecision.APPEND
    assert result.expected_sequence == 1
    assert result.cursor.sequence == 1
    assert result.cursor.last_event_id == first.event_id
    assert first.event_id.startswith("sha256:")

    replay = resolve_event_append(first, result.cursor, (first,))
    assert replay.decision is EventAppendDecision.REPLAY_EXISTING
    assert replay.cursor == result.cursor
    assert replay == resolve_event_append(first, result.cursor, (first,))


def test_event_gaps_are_reported_until_the_missing_sequence_is_supplied() -> None:
    first = _event(1)
    cursor = resolve_event_append(first, EventStreamCursor("trial-1", "attempt-1")).cursor
    third = _event(3)
    gap = resolve_event_append(third, cursor, (first,))
    assert gap.decision is EventAppendDecision.GAP
    assert gap.expected_sequence == 2
    assert gap.cursor == cursor

    second = _event(2)
    accepted = resolve_event_append(second, cursor, (first,))
    assert accepted.decision is EventAppendDecision.APPEND
    assert accepted.cursor.sequence == 2
    recovered = resolve_event_append(third, accepted.cursor, (first, second))
    assert recovered.decision is EventAppendDecision.APPEND
    assert recovered.cursor.sequence == 3


def test_stale_or_foreign_events_fail_closed() -> None:
    first = _event(1)
    second = _event(2)
    cursor = resolve_event_append(first, EventStreamCursor("trial-1", "attempt-1")).cursor
    cursor = resolve_event_append(second, cursor, (first,)).cursor
    stale = resolve_event_append(first, cursor, ())
    assert stale.decision is EventAppendDecision.CONFLICT
    assert stale.cursor == cursor

    with pytest.raises(ValueError, match="trial and attempt"):
        resolve_event_append(_event(1, attempt_id="other-attempt"), cursor)

    with pytest.raises(TypeError, match="prior_events"):
        resolve_event_append(first, cursor, "not-events")  # type: ignore[arg-type]


def test_event_contract_rejects_invalid_identity_and_cursor_values() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ExecutionEvent(
            trial_id="trial-1",
            attempt_id="attempt-1",
            sequence=1,
            event_type=ExecutionEventType.ATTEMPT_CREATED,
            payload_digest=PAYLOAD_DIGEST,
            occurred_at=datetime(2024, 1, 1),
            producer="worker-1",
        )
    with pytest.raises(ValueError, match="empty cursor"):
        EventStreamCursor("trial-1", "attempt-1", last_event_id="sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="positive"):
        resolve_event_append(
            _event(0), EventStreamCursor("trial-1", "attempt-1")
        )
