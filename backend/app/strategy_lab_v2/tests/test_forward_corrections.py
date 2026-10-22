from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import CarryInMode, ForwardInstance, ForwardState
from app.strategy_lab_v2.forward_admission import admit_forward_event
from app.strategy_lab_v2.forward_corrections import (
    CounterfactualReplayPlan,
    ForwardCorrectionCommand,
    ForwardCorrectionDecision,
    resolve_forward_correction,
)
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt, resolve_forward_warmup
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardCursor,
    observe_forward_event,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
SNAPSHOT = content_digest("snapshot")
SOURCE = content_digest("source")


def _state():
    warming = ForwardInstance(
        "forward-1", content_digest("portfolio"), SNAPSHOT, CarryInMode.FLAT,
        ForwardState.WARMING_UP, None, 0, 0, NOW, NOW,
    )
    receipt = ForwardWarmupReceipt(
        "forward-1", SNAPSHOT, CarryInMode.FLAT, content_digest("warmup"), NOW + timedelta(minutes=1)
    )
    active = resolve_forward_warmup(warming, receipt).instance
    from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState

    return ForwardLiveAdmissionState.from_warmup(active, receipt)


def _event(event_id: str, sequence: int, *, correction_of: str | None = None):
    return CanonicalForwardEvent(
        event_id,
        sequence,
        NOW + timedelta(minutes=2, seconds=sequence),
        NOW + timedelta(minutes=2, seconds=sequence),
        SOURCE,
        correction_of=correction_of,
    )


def _admitted_correction():
    state = _state()
    original = _event("live-0", 0)
    accepted = admit_forward_event(state, original, observe_forward_event(ForwardCursor(), original))
    correction = _event("correction-1", 1, correction_of="live-0")
    observation = observe_forward_event(
        ForwardCursor(last_sequence=0, last_event_id="live-0", last_event_time=original.event_time),
        correction,
    )
    admitted = admit_forward_event(accepted.state, correction, observation)
    return admitted.state, correction, observation, accepted.state


def _command(base_checkpoint_fingerprint: str) -> ForwardCorrectionCommand:
    return ForwardCorrectionCommand(
        content_digest("correction-command"),
        "forward-1",
        "correction-1",
        "live-0",
        base_checkpoint_fingerprint,
        NOW + timedelta(minutes=3),
        "audit correction",
    )


def test_admitted_correction_creates_additive_replay_plan() -> None:
    state, event, observation, prior_state = _admitted_correction()
    command = _command(prior_state.checkpoint.fingerprint)
    result = resolve_forward_correction(state, command, event, observation)
    assert result.decision is ForwardCorrectionDecision.ACCEPT
    assert result.plan is not None
    assert result.plan.base_checkpoint_fingerprint == prior_state.checkpoint.fingerprint
    assert result.state == state


def test_exact_existing_replay_plan_replays_without_state_change() -> None:
    state, event, observation, prior_state = _admitted_correction()
    command = _command(prior_state.checkpoint.fingerprint)
    accepted = resolve_forward_correction(state, command, event, observation)
    assert accepted.plan is not None
    replay = resolve_forward_correction(
        state, command, event, observation, existing_plan=accepted.plan
    )
    assert replay.decision is ForwardCorrectionDecision.REPLAY_EXISTING
    assert replay.state == state


def test_changed_command_with_existing_plan_conflicts() -> None:
    state, event, observation, prior_state = _admitted_correction()
    command = _command(prior_state.checkpoint.fingerprint)
    accepted = resolve_forward_correction(state, command, event, observation)
    assert accepted.plan is not None
    changed = ForwardCorrectionCommand(
        command.command_id,
        command.instance_id,
        command.correction_event_id,
        command.original_event_id,
        command.base_checkpoint_fingerprint,
        command.requested_at,
        "different reason",
    )
    conflict = resolve_forward_correction(
        state, changed, event, observation, existing_plan=accepted.plan
    )
    assert conflict.decision is ForwardCorrectionDecision.CONFLICT


def test_unadmitted_or_mismatched_correction_is_rejected() -> None:
    state = _state()
    correction = _event("correction-1", 1, correction_of="live-0")
    observation = observe_forward_event(ForwardCursor(), correction)
    rejected = resolve_forward_correction(
        state, _command(content_digest("base")), correction, observation
    )
    assert rejected.decision is ForwardCorrectionDecision.REJECT
    assert "admitted" in (rejected.rejection_reason or "")

    admitted, event, observation, prior_state = _admitted_correction()
    mismatched = _event("correction-2", 1, correction_of="live-0")
    result = resolve_forward_correction(
        admitted, _command(prior_state.checkpoint.fingerprint), mismatched, observation
    )
    assert result.decision is ForwardCorrectionDecision.REJECT
    assert "event" in (result.rejection_reason or "")


def test_wrong_original_and_noncorrection_observation_fail_closed() -> None:
    state, event, observation, prior_state = _admitted_correction()
    wrong_original = _event("correction-1", 1, correction_of="other")
    wrong = resolve_forward_correction(
        state, _command(prior_state.checkpoint.fingerprint), wrong_original, observation
    )
    assert wrong.decision is ForwardCorrectionDecision.CONFLICT
    assert "different content" in (wrong.rejection_reason or "")
    original = _event("live-0", 0)
    noncorrection = observe_forward_event(ForwardCursor(), original)
    rejected = resolve_forward_correction(
        state, _command(prior_state.checkpoint.fingerprint), event, noncorrection
    )
    assert rejected.decision is ForwardCorrectionDecision.REJECT
    assert "correction observation" in (rejected.rejection_reason or "")


def test_correction_command_requires_valid_digest_and_reason() -> None:
    with pytest.raises(ValueError, match="command_id"):
        ForwardCorrectionCommand("bad", "forward-1", "correction", "original", content_digest("base"), NOW, "reason")
    with pytest.raises(ValueError, match="base_checkpoint"):
        ForwardCorrectionCommand(content_digest("command"), "forward-1", "correction", "original", "bad", NOW, "reason")


def test_correction_command_and_plan_times_normalize_to_utc() -> None:
    offset = timezone(timedelta(hours=2))
    command = _command(content_digest("base"))
    offset_command = replace(
        command,
        requested_at=(command.requested_at + timedelta(hours=2)).replace(tzinfo=offset),
    )
    assert offset_command.requested_at == command.requested_at
    assert offset_command.fingerprint == command.fingerprint

    plan = CounterfactualReplayPlan(
        replay_id=content_digest("replay"),
        instance_id="forward-1",
        correction_event_id="correction-1",
        original_event_id="live-0",
        base_checkpoint_fingerprint=content_digest("base"),
        warmup_receipt_fingerprint=content_digest("warmup"),
        planned_at=NOW + timedelta(minutes=4),
    )
    offset_plan = replace(
        plan,
        planned_at=(plan.planned_at + timedelta(hours=2)).replace(tzinfo=offset),
    )
    assert offset_plan.planned_at == plan.planned_at
    assert offset_plan.fingerprint == plan.fingerprint
