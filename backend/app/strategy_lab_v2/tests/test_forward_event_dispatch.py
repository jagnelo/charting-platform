from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import DispatchDecision, DispatchRequest
from app.strategy_lab_v2.forward_event_dispatch import (
    ForwardEventDispatchDecision,
    resolve_forward_event_dispatch,
)
from app.strategy_lab_v2.forward_event_transaction import resolve_forward_event_transaction
from app.strategy_lab_v2.lifecycle import ForwardCursor, observe_forward_event
from app.strategy_lab_v2.tests.test_forward_corrections import _event, _state

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _payload(event_fingerprint: str, replay_plan_fingerprint: str | None = None) -> str:
    return content_digest(
        {
            "event_fingerprint": event_fingerprint,
            "replay_plan_fingerprint": replay_plan_fingerprint,
        }
    )


def _dispatch(payload_digest: str, *, key: str = "forward-dispatch") -> DispatchRequest:
    return DispatchRequest(
        key,
        "forward-1",
        payload_digest,
        "forward-events",
        NOW + timedelta(minutes=3),
    )


def test_forward_event_dispatch_enqueues_and_replays_exactly() -> None:
    state = _state()
    event = _event("live-0", 0)
    observation = observe_forward_event(ForwardCursor(), event)
    dispatch = _dispatch(_payload(content_digest(event)))
    accepted = resolve_forward_event_dispatch(
        state,
        event,
        observation,
        dispatch_request=dispatch,
    )
    assert accepted.decision is ForwardEventDispatchDecision.ENQUEUE
    assert accepted.state.checkpoint.instance.last_event_sequence == 0
    assert accepted.dispatch_resolution is not None
    assert accepted.dispatch_resolution.decision is DispatchDecision.ENQUEUE

    replay = resolve_forward_event_dispatch(
        accepted.state,
        event,
        observation,
        dispatch_request=dispatch,
        prior_dispatches=(dispatch,),
    )
    assert replay.decision is ForwardEventDispatchDecision.REPLAY_EXISTING
    assert replay.state == accepted.state
    assert replay.dispatch_resolution is not None
    assert replay.dispatch_resolution.decision is DispatchDecision.REPLAY_EXISTING


def test_gap_dispatch_preserves_buffered_state_and_dispatch_evidence() -> None:
    state = _state()
    event = _event("live-2", 2)
    observation = observe_forward_event(ForwardCursor(), event)
    dispatch = _dispatch(_payload(content_digest(event)), key="gap-dispatch")
    resolution = resolve_forward_event_dispatch(
        state,
        event,
        observation,
        dispatch_request=dispatch,
    )
    assert resolution.decision is ForwardEventDispatchDecision.BUFFERED
    assert resolution.state.checkpoint.buffered_event_ids == frozenset({"live-2"})
    assert resolution.envelope is not None


def test_correction_dispatch_binds_replay_plan_and_replays_without_duplication() -> None:
    state = _state()
    original = _event("live-0", 0)
    original_observation = observe_forward_event(ForwardCursor(), original)
    admitted_original = resolve_forward_event_dispatch(
        state,
        original,
        original_observation,
        dispatch_request=_dispatch(_payload(content_digest(original)), key="original"),
    )
    correction = _event("correction-1", 1, correction_of="live-0")
    observation = observe_forward_event(
        ForwardCursor(last_sequence=0, last_event_id="live-0", last_event_time=original.event_time),
        correction,
    )
    from app.strategy_lab_v2.forward_corrections import ForwardCorrectionCommand

    command = ForwardCorrectionCommand(
        content_digest("correction-command"),
        "forward-1",
        "correction-1",
        "live-0",
        admitted_original.state.checkpoint.fingerprint,
        NOW + timedelta(minutes=3),
        "audit correction",
    )
    transaction = resolve_forward_event_transaction(
        admitted_original.state,
        correction,
        observation,
        correction_command=command,
    )
    assert transaction.replay_plan is not None
    dispatch = _dispatch(
        _payload(content_digest(correction), transaction.replay_plan.fingerprint),
        key="correction",
    )
    accepted = resolve_forward_event_dispatch(
        admitted_original.state,
        correction,
        observation,
        dispatch_request=dispatch,
        correction_command=command,
    )
    assert accepted.decision is ForwardEventDispatchDecision.CORRECTION_ENQUEUE
    assert accepted.state.checkpoint.instance.correction_count == 1

    replay = resolve_forward_event_dispatch(
        accepted.state,
        correction,
        observation,
        dispatch_request=dispatch,
        prior_dispatches=(dispatch,),
        correction_command=command,
        existing_replay_plan=accepted.event_transaction.replay_plan,
    )
    assert replay.decision is ForwardEventDispatchDecision.CORRECTION_REPLAY
    assert replay.state == accepted.state


def test_dispatch_conflict_or_payload_mismatch_rolls_back_forward_state() -> None:
    state = _state()
    event = _event("live-0", 0)
    observation = observe_forward_event(ForwardCursor(), event)
    dispatch = _dispatch(_payload(content_digest(event)))
    conflicting = resolve_forward_event_dispatch(
        state,
        event,
        observation,
        dispatch_request=dispatch,
        prior_dispatches=(
            DispatchRequest(
                dispatch.idempotency_key,
                dispatch.attempt_id,
                content_digest("different"),
                dispatch.queue_name,
                dispatch.created_at,
            ),
        ),
    )
    assert conflicting.decision is ForwardEventDispatchDecision.CONFLICT
    assert conflicting.state == state

    wrong_payload = resolve_forward_event_dispatch(
        state,
        event,
        observation,
        dispatch_request=_dispatch(content_digest("wrong"), key="wrong-payload"),
    )
    assert wrong_payload.decision is ForwardEventDispatchDecision.REJECT
    assert wrong_payload.rejection_reason == "dispatch payload does not match forward event evidence"
    assert wrong_payload.state == state
