from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.event_tape import (
    EVENT_TAPE_DEFINITION_VERSION,
    EventTapeBatch,
    FrozenEventTape,
)
from app.strategy_lab_v2.sdk import MarketEvent

SNAPSHOT = content_digest("snapshot")
BASE = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)


def _event(
    event_id: str,
    dependency_id: str,
    sequence: int,
    *,
    offset: int = 0,
    instrument_id: str | None = None,
) -> MarketEvent:
    return MarketEvent(
        dependency_id=dependency_id,
        event_id=event_id,
        instrument_id=instrument_id or dependency_id,
        event_time=BASE + timedelta(minutes=offset),
        sequence=sequence,
        values={"close": sequence + 1},
    )


def test_tape_canonicalizes_input_order_and_groups_same_time_batches() -> None:
    late = _event("b-1", "beta", 1, offset=1)
    first = _event("a-0", "alpha", 0)
    same_time = _event("b-0", "beta", 0)
    tape = FrozenEventTape(SNAPSHOT, (late, first, same_time))

    assert tape.events == (first, same_time, late)
    assert tape.event_count == 3
    assert tape.start_time == BASE
    assert tape.end_time == BASE + timedelta(minutes=1)
    assert [batch.batch_sequence for batch in tape.batches()] == [0, 1]
    assert [len(batch.events) for batch in tape.batches()] == [2, 1]
    assert tape.batches()[0] == EventTapeBatch(0, BASE, (first, same_time))


def test_tape_fingerprint_is_stable_for_permuted_input() -> None:
    events = (
        _event("a-0", "alpha", 0),
        _event("a-1", "alpha", 1, offset=1),
        _event("b-0", "beta", 0),
    )
    assert FrozenEventTape(SNAPSHOT, events).fingerprint == FrozenEventTape(
        SNAPSHOT, tuple(reversed(events))
    ).fingerprint
    assert FrozenEventTape(SNAPSHOT, events).definition_version == EVENT_TAPE_DEFINITION_VERSION


def test_duplicate_ids_and_dependency_instrument_switch_fail_closed() -> None:
    with pytest.raises(ValueError, match="event ids must be unique"):
        FrozenEventTape(SNAPSHOT, (_event("same", "alpha", 0), _event("same", "beta", 0)))

    with pytest.raises(ValueError, match="multiple instruments"):
        FrozenEventTape(
            SNAPSHOT,
            (
                _event("a-0", "alpha", 0),
                _event("a-1", "alpha", 1, offset=1, instrument_id="US.MSFT"),
            ),
        )


def test_each_dependency_must_advance_sequence_and_time() -> None:
    with pytest.raises(ValueError, match="advance sequence and time"):
        FrozenEventTape(
            SNAPSHOT,
            (
                _event("a-0", "alpha", 0, offset=1),
                _event("a-1", "alpha", 1),
            ),
        )
    with pytest.raises(ValueError, match="advance sequence and time"):
        FrozenEventTape(
            SNAPSHOT,
            (
                _event("a-0", "alpha", 0),
                _event("a-dup", "alpha", 0, offset=1),
            ),
        )


def test_slice_and_boundary_iteration_are_explicit_and_non_interpolating() -> None:
    events = tuple(_event(f"a-{index}", "alpha", index, offset=index) for index in range(3))
    tape = FrozenEventTape(SNAPSHOT, events)

    assert tuple(tape.iter_events_until(BASE + timedelta(minutes=1))) == events[:2]
    assert tuple(
        tape.iter_events_until(BASE + timedelta(minutes=1), include_boundary=False)
    ) == events[:1]
    assert tape.slice(BASE, BASE + timedelta(minutes=2), include_start=False, include_end=False) == (
        events[1],
    )
    assert tape.slice(BASE + timedelta(minutes=1), BASE + timedelta(minutes=1)) == (events[1],)
    assert tape.slice() == events


def test_empty_tape_is_a_valid_explicit_snapshot_bound_input() -> None:
    tape = FrozenEventTape(SNAPSHOT)
    assert tape.event_count == 0
    assert tape.start_time is None
    assert tape.end_time is None
    assert tape.batches() == ()
    assert tuple(tape.iter_events_until(BASE)) == ()


def test_invalid_time_range_and_definition_are_rejected() -> None:
    tape = FrozenEventTape(SNAPSHOT, (_event("a-0", "alpha", 0),))
    with pytest.raises(ValueError, match="start must not follow end"):
        tape.slice(BASE + timedelta(days=1), BASE)
    with pytest.raises(ValueError, match="definition version"):
        FrozenEventTape(SNAPSHOT, definition_version="event-tape.other.v1")
