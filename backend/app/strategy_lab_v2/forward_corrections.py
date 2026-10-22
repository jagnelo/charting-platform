"""Counterfactual replay commands for forward corrections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardEventDisposition,
    ForwardEventObservation,
)


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ForwardCorrectionCommand:
    """Intent to replay a correction without altering the live decision path."""

    command_id: str
    instance_id: str
    correction_event_id: str
    original_event_id: str
    base_checkpoint_fingerprint: str
    requested_at: datetime
    reason: str

    def __post_init__(self) -> None:
        require_sha256_digest(self.command_id, field_name="command_id")
        for name in ("instance_id", "correction_event_id", "original_event_id"):
            _nonempty(getattr(self, name), name)
        require_sha256_digest(
            self.base_checkpoint_fingerprint,
            field_name="base_checkpoint_fingerprint",
        )
        _aware(self.requested_at, "requested_at")
        _nonempty(self.reason, "reason")
        object.__setattr__(self, "requested_at", self.requested_at.astimezone(UTC))

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "base_checkpoint_fingerprint": self.base_checkpoint_fingerprint,
                "command_id": self.command_id,
                "correction_event_id": self.correction_event_id,
                "instance_id": self.instance_id,
                "original_event_id": self.original_event_id,
                "reason": self.reason,
            }
        )


@dataclass(frozen=True, slots=True)
class CounterfactualReplayPlan:
    """Immutable replay basis; execution is a separate worker responsibility."""

    replay_id: str
    instance_id: str
    correction_event_id: str
    original_event_id: str
    base_checkpoint_fingerprint: str
    warmup_receipt_fingerprint: str
    planned_at: datetime

    def __post_init__(self) -> None:
        require_sha256_digest(self.replay_id, field_name="replay_id")
        for name in ("instance_id", "correction_event_id", "original_event_id"):
            _nonempty(getattr(self, name), name)
        for name in ("base_checkpoint_fingerprint", "warmup_receipt_fingerprint"):
            require_sha256_digest(getattr(self, name), field_name=name)
        _aware(self.planned_at, "planned_at")
        object.__setattr__(self, "planned_at", self.planned_at.astimezone(UTC))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ForwardCorrectionDecision(StrEnum):
    ACCEPT = "accept"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ForwardCorrectionResolution:
    decision: ForwardCorrectionDecision
    state: ForwardLiveAdmissionState
    plan: CounterfactualReplayPlan | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ForwardCorrectionDecision):
            raise TypeError("decision must be a ForwardCorrectionDecision")
        if not isinstance(self.state, ForwardLiveAdmissionState):
            raise TypeError("state must be a ForwardLiveAdmissionState")
        if self.plan is not None and not isinstance(self.plan, CounterfactualReplayPlan):
            raise TypeError("plan must be a CounterfactualReplayPlan")
        if self.decision in {
            ForwardCorrectionDecision.ACCEPT,
            ForwardCorrectionDecision.REPLAY_EXISTING,
        } and self.plan is None:
            raise ValueError("accepted correction resolutions require a replay plan")
        if self.decision in {
            ForwardCorrectionDecision.CONFLICT,
            ForwardCorrectionDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if self.decision not in {
            ForwardCorrectionDecision.CONFLICT,
            ForwardCorrectionDecision.REJECT,
        } and self.rejection_reason:
            raise ValueError("successful correction resolutions cannot contain a reason")


def resolve_forward_correction(
    state: ForwardLiveAdmissionState,
    command: ForwardCorrectionCommand,
    event: CanonicalForwardEvent,
    observation: ForwardEventObservation,
    *,
    existing_plan: CounterfactualReplayPlan | None = None,
) -> ForwardCorrectionResolution:
    """Resolve one additive correction replay command without running a replay."""

    if not isinstance(state, ForwardLiveAdmissionState):
        raise TypeError("state must be a ForwardLiveAdmissionState")
    if not isinstance(command, ForwardCorrectionCommand):
        raise TypeError("command must be a ForwardCorrectionCommand")
    if not isinstance(event, CanonicalForwardEvent):
        raise TypeError("event must be a CanonicalForwardEvent")
    if not isinstance(observation, ForwardEventObservation):
        raise TypeError("observation must be a ForwardEventObservation")
    if existing_plan is not None and not isinstance(existing_plan, CounterfactualReplayPlan):
        raise TypeError("existing_plan must be a CounterfactualReplayPlan")
    replay_id = content_digest(
        {
            "base_checkpoint_fingerprint": command.base_checkpoint_fingerprint,
            "command_fingerprint": command.fingerprint,
            "correction_event_id": command.correction_event_id,
            "instance_id": command.instance_id,
            "original_event_id": command.original_event_id,
            "warmup_receipt_fingerprint": state.warmup_receipt_fingerprint,
        }
    )
    if existing_plan is not None:
        if existing_plan.replay_id == replay_id:
            return ForwardCorrectionResolution(
                ForwardCorrectionDecision.REPLAY_EXISTING, state, existing_plan
            )
        return ForwardCorrectionResolution(
            ForwardCorrectionDecision.CONFLICT,
            state,
            rejection_reason="replay identity is already bound to different content",
        )
    if command.instance_id != state.checkpoint.instance.instance_id:
        return ForwardCorrectionResolution(
            ForwardCorrectionDecision.REJECT,
            state,
            rejection_reason="correction command instance does not match live state",
        )
    if event.event_id != command.correction_event_id:
        return ForwardCorrectionResolution(
            ForwardCorrectionDecision.REJECT,
            state,
            rejection_reason="correction event does not match command identity",
        )
    seen_event = next(
        (item for item in state.seen_events if item.event_id == event.event_id), None
    )
    if event.event_id not in state.checkpoint.correction_event_ids or seen_event is None:
        return ForwardCorrectionResolution(
            ForwardCorrectionDecision.REJECT,
            state,
            rejection_reason="correction must be admitted before replay is planned",
        )
    if seen_event.event_fingerprint != content_digest(event):
        return ForwardCorrectionResolution(
            ForwardCorrectionDecision.CONFLICT,
            state,
            rejection_reason="correction event id is already bound to different content",
        )
    if event.correction_of != command.original_event_id:
        return ForwardCorrectionResolution(
            ForwardCorrectionDecision.REJECT,
            state,
            rejection_reason="correction original event does not match command identity",
        )
    if observation.disposition is not ForwardEventDisposition.CORRECTION:
        return ForwardCorrectionResolution(
            ForwardCorrectionDecision.REJECT,
            state,
            rejection_reason="correction replay requires a correction observation",
        )
    plan = CounterfactualReplayPlan(
        replay_id=replay_id,
        instance_id=command.instance_id,
        correction_event_id=command.correction_event_id,
        original_event_id=command.original_event_id,
        base_checkpoint_fingerprint=command.base_checkpoint_fingerprint,
        warmup_receipt_fingerprint=state.warmup_receipt_fingerprint,
        planned_at=command.requested_at,
    )
    return ForwardCorrectionResolution(ForwardCorrectionDecision.ACCEPT, state, plan)
