from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import CarryInMode, ForwardInstance, ForwardState
from app.strategy_lab_v2.forward_state import (
    ForwardStateCheckpoint,
    apply_checkpoint_observation,
)
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardCursor,
    ForwardEventDisposition,
    observe_forward_event,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
SOURCE_DIGEST = content_digest("forward-source")


def _instance(*, event_id: str | None = None, sequence: int = 0, corrections: int = 0) -> ForwardInstance:
    return ForwardInstance(
        instance_id="forward-1",
        portfolio_fingerprint=content_digest("portfolio"),
        warmup_snapshot_fingerprint=content_digest("snapshot"),
        carry_in_mode=CarryInMode.FLAT,
        state=ForwardState.ACTIVE,
        last_event_id=event_id,
        last_event_sequence=sequence,
        correction_count=corrections,
        created_at=NOW,
        updated_at=NOW,
    )


def _event(event_id: str, sequence: int, *, correction_of: str | None = None) -> CanonicalForwardEvent:
    return CanonicalForwardEvent(
        event_id,
        sequence,
        NOW + timedelta(seconds=sequence),
        NOW + timedelta(seconds=sequence),
        SOURCE_DIGEST,
        correction_of=correction_of,
    )


def test_checkpoint_advances_accepted_event_once_and_is_idempotent() -> None:
    checkpoint = ForwardStateCheckpoint(_instance())
    event = _event("e0", 0)
    observation = observe_forward_event(ForwardCursor(), event)

    advanced = apply_checkpoint_observation(checkpoint, event, observation)
    replayed = apply_checkpoint_observation(advanced, event, observation)

    assert observation.disposition is ForwardEventDisposition.ACCEPTED
    assert advanced.instance.last_event_id == "e0"
    assert advanced.processed_event_ids == frozenset({"e0"})
    assert replayed == advanced


def test_checkpoint_buffers_gaps_then_removes_them_when_contiguous_event_arrives() -> None:
    checkpoint = ForwardStateCheckpoint(_instance())
    gap_event = _event("e2", 2)
    gap_observation = observe_forward_event(ForwardCursor(), gap_event)
    buffered = apply_checkpoint_observation(checkpoint, gap_event, gap_observation)

    assert buffered.buffered_event_ids == frozenset({"e2"})
    assert apply_checkpoint_observation(buffered, gap_event, gap_observation) == buffered

    event0 = _event("e0", 0)
    observation0 = observe_forward_event(ForwardCursor(), event0)
    advanced0 = apply_checkpoint_observation(buffered, event0, observation0)
    event1 = _event("e1", 1)
    observation1 = observe_forward_event(observation0.next_cursor, event1)
    advanced = apply_checkpoint_observation(advanced0, event1, observation1)
    event2_observation = observe_forward_event(observation1.next_cursor, gap_event)
    reconciled = apply_checkpoint_observation(advanced, gap_event, event2_observation)

    assert reconciled.instance.last_event_sequence == 2
    assert reconciled.buffered_event_ids == frozenset()


def test_checkpoint_records_corrections_and_anomaly_counts_without_cursor_rewrite() -> None:
    event1 = _event("e1", 1)
    instance = _instance(event_id="e1", sequence=1)
    checkpoint = ForwardStateCheckpoint(instance, processed_event_ids=frozenset({"e1"}))
    correction_event = _event("e1-correction", 2, correction_of="e1")
    correction_observation = observe_forward_event(
        ForwardCursor(last_sequence=1, last_event_id="e1", last_event_time=NOW + timedelta(seconds=1)),
        correction_event,
    )
    corrected = apply_checkpoint_observation(checkpoint, correction_event, correction_observation)

    assert corrected.instance.last_event_sequence == 1
    assert corrected.correction_event_ids == frozenset({"e1-correction"})
    assert apply_checkpoint_observation(corrected, correction_event, correction_observation) == corrected

    duplicate_observation = observe_forward_event(
        ForwardCursor(last_sequence=1, last_event_id="e1", last_event_time=NOW + timedelta(seconds=1)),
        event1,
        processed_event_ids=frozenset({"e1"}),
    )
    duplicated = apply_checkpoint_observation(corrected, event1, duplicate_observation)
    assert duplicated.duplicate_count == 1


def test_checkpoint_rejects_overlapping_event_sets() -> None:
    instance = _instance()
    ForwardStateCheckpoint(instance)
    try:
        ForwardStateCheckpoint(instance, processed_event_ids=frozenset({"same"}), buffered_event_ids=frozenset({"same"}))
    except ValueError as error:
        assert "disjoint" in str(error)
    else:
        raise AssertionError("overlapping event sets should be rejected")


def test_forward_event_and_cursor_times_normalize_to_utc_for_identity() -> None:
    offset = timezone(timedelta(hours=2))
    event = CanonicalForwardEvent(
        "offset-event",
        0,
        NOW,
        NOW,
        SOURCE_DIGEST,
    )
    offset_event = CanonicalForwardEvent(
        "offset-event",
        0,
        (NOW + timedelta(hours=2)).replace(tzinfo=offset),
        (NOW + timedelta(hours=2)).replace(tzinfo=offset),
        SOURCE_DIGEST,
    )
    cursor = ForwardCursor(0, "offset-event", (NOW + timedelta(hours=2)).replace(tzinfo=offset))

    assert event.event_time == NOW
    assert offset_event.event_time == NOW
    assert cursor.last_event_time == NOW
    assert content_digest(offset_event) == content_digest(event)


def test_forward_instance_times_normalize_to_utc_for_identity() -> None:
    offset = timezone(timedelta(hours=2))
    instance = _instance()
    offset_instance = _instance()
    offset_instance = replace(
        offset_instance,
        created_at=(NOW + timedelta(hours=2)).replace(tzinfo=offset),
        updated_at=(NOW + timedelta(hours=2)).replace(tzinfo=offset),
    )

    assert offset_instance.created_at == instance.created_at
    assert offset_instance.updated_at == instance.updated_at
    assert content_digest(offset_instance) == content_digest(instance)
