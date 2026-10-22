from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.forward_corrections import ForwardCorrectionCommand
from app.strategy_lab_v2.forward_event_transaction import (
    ForwardEventTransactionDecision,
    resolve_forward_event_transaction,
)
from app.strategy_lab_v2.lifecycle import ForwardCursor, observe_forward_event
from app.strategy_lab_v2.tests.test_forward_corrections import _event, _state

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _command(base_checkpoint_fingerprint: str, *, reason: str = "audit correction") -> ForwardCorrectionCommand:
    return ForwardCorrectionCommand(
        content_digest("correction-command"),
        "forward-1",
        "correction-1",
        "live-0",
        base_checkpoint_fingerprint,
        NOW + timedelta(minutes=3),
        reason,
    )


def _original_and_correction():
    state = _state()
    original = _event("live-0", 0)
    original_observation = observe_forward_event(ForwardCursor(), original)
    accepted = resolve_forward_event_transaction(state, original, original_observation)
    correction = _event("correction-1", 1, correction_of="live-0")
    correction_observation = observe_forward_event(
        ForwardCursor(last_sequence=0, last_event_id="live-0", last_event_time=original.event_time),
        correction,
    )
    return state, accepted.state, correction, correction_observation


def test_ordinary_event_and_exact_retry_are_admitted_idempotently() -> None:
    state, _, _, _ = _original_and_correction()
    event = _event("live-0", 0)
    observation = observe_forward_event(ForwardCursor(), event)
    accepted = resolve_forward_event_transaction(state, event, observation)
    assert accepted.decision is ForwardEventTransactionDecision.ACCEPTED
    replay = resolve_forward_event_transaction(accepted.state, event, observation)
    assert replay.decision is ForwardEventTransactionDecision.REPLAY_EXISTING
    assert replay.state == accepted.state


def test_correction_requires_replay_command_and_rolls_back_when_missing() -> None:
    original_state, base_state, correction, observation = _original_and_correction()
    rejected = resolve_forward_event_transaction(base_state, correction, observation)
    assert rejected.decision is ForwardEventTransactionDecision.REJECT
    assert rejected.rejection_reason == "correction events require a counterfactual replay command"
    assert rejected.state == base_state
    assert original_state.checkpoint.instance.correction_count == 0


def test_correction_admission_and_replay_plan_are_staged_together() -> None:
    _, base_state, correction, observation = _original_and_correction()
    command = _command(base_state.checkpoint.fingerprint)
    accepted = resolve_forward_event_transaction(
        base_state,
        correction,
        observation,
        correction_command=command,
    )
    assert accepted.decision is ForwardEventTransactionDecision.CORRECTION_ACCEPTED
    assert accepted.replay_plan is not None
    assert accepted.state.checkpoint.instance.correction_count == 1

    replay = resolve_forward_event_transaction(
        accepted.state,
        correction,
        observation,
        correction_command=command,
        existing_replay_plan=accepted.replay_plan,
    )
    assert replay.decision is ForwardEventTransactionDecision.CORRECTION_REPLAY
    assert replay.replay_plan == accepted.replay_plan
    assert replay.state == accepted.state


def test_correction_conflicts_and_wrong_commands_leave_live_state_unchanged() -> None:
    _, base_state, correction, observation = _original_and_correction()
    command = _command(base_state.checkpoint.fingerprint)
    accepted = resolve_forward_event_transaction(
        base_state,
        correction,
        observation,
        correction_command=command,
    )
    assert accepted.replay_plan is not None
    changed = _event("correction-1", 1, correction_of="other")
    conflict = resolve_forward_event_transaction(
        accepted.state,
        changed,
        observation,
        correction_command=command,
        existing_replay_plan=accepted.replay_plan,
    )
    assert conflict.decision is ForwardEventTransactionDecision.CONFLICT
    assert conflict.state == accepted.state

    wrong_command = _command(base_state.checkpoint.fingerprint, reason="different")
    changed_plan = resolve_forward_event_transaction(
        accepted.state,
        correction,
        observation,
        correction_command=wrong_command,
        existing_replay_plan=accepted.replay_plan,
    )
    assert changed_plan.decision is ForwardEventTransactionDecision.CONFLICT
    assert changed_plan.state == accepted.state


def test_gap_is_preserved_and_replay_evidence_is_rejected_for_noncorrections() -> None:
    state, _, _, _ = _original_and_correction()
    gap = _event("live-2", 2)
    gap_resolution = resolve_forward_event_transaction(
        state,
        gap,
        observe_forward_event(ForwardCursor(), gap),
    )
    assert gap_resolution.decision is ForwardEventTransactionDecision.GAP
    assert gap_resolution.state.checkpoint.buffered_event_ids == frozenset({"live-2"})

    noncorrection = resolve_forward_event_transaction(
        state,
        _event("live-0", 0),
        observe_forward_event(ForwardCursor(), _event("live-0", 0)),
        correction_command=_command(state.checkpoint.fingerprint),
    )
    assert noncorrection.decision is ForwardEventTransactionDecision.REJECT
    assert noncorrection.rejection_reason == "replay evidence is only valid for correction events"
