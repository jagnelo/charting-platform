from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import CarryInMode, ForwardInstance, ForwardState
from app.strategy_lab_v2.forward_admission import (
    ForwardAdmissionDecision,
    ForwardLiveAdmissionState,
    admit_forward_event,
)
from app.strategy_lab_v2.forward_state import ForwardStateCheckpoint
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt, resolve_forward_warmup
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardCursor,
    observe_forward_event,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
SNAPSHOT = content_digest("snapshot")
SOURCE = content_digest("source")


def _warming() -> ForwardInstance:
    return ForwardInstance(
        "forward-1",
        content_digest("portfolio"),
        SNAPSHOT,
        CarryInMode.FLAT,
        ForwardState.WARMING_UP,
        None,
        0,
        0,
        NOW,
        NOW,
    )


def _live_state() -> ForwardLiveAdmissionState:
    receipt = ForwardWarmupReceipt(
        "forward-1",
        SNAPSHOT,
        CarryInMode.FLAT,
        content_digest("warmup"),
        NOW + timedelta(minutes=1),
    )
    active = resolve_forward_warmup(_warming(), receipt).instance
    return ForwardLiveAdmissionState.from_warmup(active, receipt)


def _event(event_id: str, sequence: int, *, correction_of: str | None = None) -> CanonicalForwardEvent:
    return CanonicalForwardEvent(
        event_id,
        sequence,
        NOW + timedelta(minutes=2, seconds=sequence),
        NOW + timedelta(minutes=2, seconds=sequence),
        SOURCE,
        correction_of=correction_of,
    )


def test_live_admission_accepts_contiguous_event_and_replays_exact_content() -> None:
    state = _live_state()
    event = _event("live-1", 0)
    observation = observe_forward_event(ForwardCursor(), event)
    accepted = admit_forward_event(state, event, observation)
    assert accepted.decision is ForwardAdmissionDecision.ACCEPTED
    replay = admit_forward_event(accepted.state, event, observation)
    assert replay.decision is ForwardAdmissionDecision.REPLAY_EXISTING
    assert replay.state == accepted.state


def test_changed_event_content_with_same_id_is_a_conflict() -> None:
    state = _live_state()
    event = _event("live-1", 0)
    observation = observe_forward_event(ForwardCursor(), event)
    accepted = admit_forward_event(state, event, observation)
    changed = _event("live-1", 1, correction_of="other")
    conflict = admit_forward_event(accepted.state, changed, observation)
    assert conflict.decision is ForwardAdmissionDecision.CONFLICT
    assert conflict.state == accepted.state


def test_gap_is_buffered_and_late_event_can_reconcile() -> None:
    state = _live_state()
    event2 = _event("live-2", 2)
    gap = admit_forward_event(state, event2, observe_forward_event(ForwardCursor(), event2))
    assert gap.decision is ForwardAdmissionDecision.GAP
    event0 = _event("live-0", 0)
    first = admit_forward_event(gap.state, event0, observe_forward_event(ForwardCursor(), event0))
    event1 = _event("live-1", 1)
    second = admit_forward_event(
        first.state,
        event1,
        observe_forward_event(
            ForwardCursor(last_sequence=0, last_event_id="live-0", last_event_time=event0.event_time),
            event1,
        ),
    )
    event2_observation = observe_forward_event(
        ForwardCursor(last_sequence=1, last_event_id="live-1", last_event_time=event1.event_time),
        event2,
    )
    reconciled = admit_forward_event(second.state, event2, event2_observation)
    assert reconciled.decision is ForwardAdmissionDecision.ACCEPTED
    assert reconciled.state.checkpoint.instance.last_event_sequence == 2


def test_duplicate_out_of_order_and_correction_decisions_remain_observable() -> None:
    state = _live_state()
    event1 = _event("live-1", 0)
    accepted = admit_forward_event(state, event1, observe_forward_event(ForwardCursor(), event1))
    duplicate = _event("duplicate", 0)
    duplicate_result = admit_forward_event(
        accepted.state,
        duplicate,
        observe_forward_event(
            ForwardCursor(last_sequence=0, last_event_id="live-1", last_event_time=event1.event_time),
            duplicate,
        ),
    )
    assert duplicate_result.decision is ForwardAdmissionDecision.OUT_OF_ORDER
    correction = _event("correction", 1, correction_of="live-1")
    correction_result = admit_forward_event(
        duplicate_result.state,
        correction,
        observe_forward_event(
            ForwardCursor(last_sequence=0, last_event_id="live-1", last_event_time=event1.event_time),
            correction,
        ),
    )
    assert correction_result.decision is ForwardAdmissionDecision.CORRECTION
    assert correction_result.state.checkpoint.instance.correction_count == 1


def test_admission_requires_active_instance_and_warmup_cursor_binding() -> None:
    receipt = ForwardWarmupReceipt(
        "forward-1", SNAPSHOT, CarryInMode.FLAT, content_digest("warmup"), NOW + timedelta(minutes=1)
    )
    with pytest.raises(ValueError, match="active"):
        ForwardLiveAdmissionState(ForwardStateCheckpoint(_warming()), receipt.fingerprint)
    active = resolve_forward_warmup(_warming(), receipt).instance
    mismatched = ForwardWarmupReceipt(
        "forward-1",
        SNAPSHOT,
        CarryInMode.FLAT,
        content_digest("other"),
        NOW + timedelta(minutes=1),
        final_event_id="other-event",
        final_event_fingerprint=content_digest("other-event"),
    )
    with pytest.raises(ValueError, match="cursor"):
        ForwardLiveAdmissionState.from_warmup(active, mismatched)


def test_state_sorts_seen_event_ids_and_rejects_invalid_identity() -> None:
    state = _live_state()
    assert state.seen_events == ()
    with pytest.raises(ValueError, match="event_fingerprint"):
        from app.strategy_lab_v2.forward_admission import ForwardSeenEvent

        ForwardSeenEvent("event", "bad", 1)
