"""Active forward-event admission with content-addressed replay protection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import ForwardInstance, ForwardState
from app.strategy_lab_v2.forward_state import ForwardStateCheckpoint, apply_checkpoint_observation
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardCursor,
    ForwardEventDisposition,
    ForwardEventObservation,
)


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class ForwardSeenEvent:
    """Content identity retained for every newly admitted event observation."""

    event_id: str
    event_fingerprint: str
    sequence: int

    def __post_init__(self) -> None:
        _nonempty(self.event_id, "event_id")
        require_sha256_digest(self.event_fingerprint, field_name="event_fingerprint")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 0:
            raise ValueError("event sequence must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ForwardLiveAdmissionState:
    """Active instance checkpoint plus event content identities for replay safety."""

    checkpoint: ForwardStateCheckpoint
    warmup_receipt_fingerprint: str
    seen_events: tuple[ForwardSeenEvent, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.checkpoint, ForwardStateCheckpoint):
            raise TypeError("checkpoint must be a ForwardStateCheckpoint")
        if self.checkpoint.instance.state is not ForwardState.ACTIVE:
            raise ValueError("live admission requires an active forward instance")
        require_sha256_digest(
            self.warmup_receipt_fingerprint,
            field_name="warmup_receipt_fingerprint",
        )
        seen = tuple(self.seen_events)
        if any(not isinstance(item, ForwardSeenEvent) for item in seen):
            raise TypeError("seen_events must contain ForwardSeenEvent values")
        ids = [item.event_id for item in seen]
        if len(ids) != len(set(ids)):
            raise ValueError("seen event ids must be unique")
        object.__setattr__(self, "seen_events", tuple(sorted(seen, key=lambda item: item.event_id)))

    @classmethod
    def from_warmup(
        cls, instance: ForwardInstance, receipt: ForwardWarmupReceipt
    ) -> ForwardLiveAdmissionState:
        """Build live state from the exact completed warm-up handoff."""

        if not isinstance(instance, ForwardInstance):
            raise TypeError("instance must be a ForwardInstance")
        if not isinstance(receipt, ForwardWarmupReceipt):
            raise TypeError("receipt must be a ForwardWarmupReceipt")
        if instance.state is not ForwardState.ACTIVE:
            raise ValueError("warm-up must complete before live admission")
        if receipt.instance_id != instance.instance_id:
            raise ValueError("warm-up receipt instance does not match live instance")
        if receipt.warmup_snapshot_fingerprint != instance.warmup_snapshot_fingerprint:
            raise ValueError("warm-up receipt snapshot does not match live instance")
        if receipt.carry_in_mode is not instance.carry_in_mode:
            raise ValueError("warm-up receipt carry-in mode does not match live instance")
        if (
            receipt.final_event_id != instance.last_event_id
            or receipt.final_event_sequence != instance.last_event_sequence
        ):
            raise ValueError("warm-up receipt cursor does not match live instance")
        processed = (
            frozenset({receipt.final_event_id})
            if receipt.final_event_id is not None
            else frozenset()
        )
        seen = (
            (ForwardSeenEvent(receipt.final_event_id, receipt.final_event_fingerprint, receipt.final_event_sequence),)
            if receipt.final_event_id is not None and receipt.final_event_fingerprint is not None
            else ()
        )
        return cls(
            checkpoint=ForwardStateCheckpoint(instance, processed_event_ids=processed),
            warmup_receipt_fingerprint=receipt.fingerprint,
            seen_events=seen,
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ForwardAdmissionDecision(StrEnum):
    ACCEPTED = "accepted"
    REPLAY_EXISTING = "replay_existing"
    GAP = "gap"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    CORRECTION = "correction"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ForwardAdmissionResolution:
    decision: ForwardAdmissionDecision
    state: ForwardLiveAdmissionState
    event_fingerprint: str
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ForwardAdmissionDecision):
            raise TypeError("decision must be a ForwardAdmissionDecision")
        if not isinstance(self.state, ForwardLiveAdmissionState):
            raise TypeError("state must be a ForwardLiveAdmissionState")
        require_sha256_digest(self.event_fingerprint, field_name="event_fingerprint")
        if self.decision in {
            ForwardAdmissionDecision.CONFLICT,
            ForwardAdmissionDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if self.decision not in {
            ForwardAdmissionDecision.CONFLICT,
            ForwardAdmissionDecision.REJECT,
        } and self.rejection_reason:
            raise ValueError("successful admission resolutions cannot contain a reason")


def admit_forward_event(
    state: ForwardLiveAdmissionState,
    event: CanonicalForwardEvent,
    observation: ForwardEventObservation,
) -> ForwardAdmissionResolution:
    """Admit one classified live event, retaining exact content for replay."""

    if not isinstance(state, ForwardLiveAdmissionState):
        raise TypeError("state must be a ForwardLiveAdmissionState")
    if not isinstance(event, CanonicalForwardEvent):
        raise TypeError("event must be a CanonicalForwardEvent")
    if not isinstance(observation, ForwardEventObservation):
        raise TypeError("observation must be a ForwardEventObservation")
    event_fingerprint = content_digest(event)
    existing = next((item for item in state.seen_events if item.event_id == event.event_id), None)
    if existing is not None:
        if existing.event_fingerprint != event_fingerprint:
            return ForwardAdmissionResolution(
                ForwardAdmissionDecision.CONFLICT,
                state,
                event_fingerprint,
                rejection_reason="event id is already bound to different content",
            )
        if event.event_id not in state.checkpoint.buffered_event_ids:
            return ForwardAdmissionResolution(
                ForwardAdmissionDecision.REPLAY_EXISTING, state, event_fingerprint
            )
    try:
        _validate_observation(state, event, observation)
        checkpoint = apply_checkpoint_observation(state.checkpoint, event, observation)
    except ValueError as error:
        return ForwardAdmissionResolution(
            ForwardAdmissionDecision.REJECT,
            state,
            event_fingerprint,
            rejection_reason=str(error),
        )
    seen_events = (
        state.seen_events
        if existing is not None
        else state.seen_events
        + (ForwardSeenEvent(event.event_id, event_fingerprint, event.sequence),)
    )
    next_state = ForwardLiveAdmissionState(
        checkpoint=checkpoint,
        warmup_receipt_fingerprint=state.warmup_receipt_fingerprint,
        seen_events=seen_events,
    )
    decisions = {
        ForwardEventDisposition.ACCEPTED: ForwardAdmissionDecision.ACCEPTED,
        ForwardEventDisposition.GAP: ForwardAdmissionDecision.GAP,
        ForwardEventDisposition.DUPLICATE: ForwardAdmissionDecision.DUPLICATE,
        ForwardEventDisposition.OUT_OF_ORDER: ForwardAdmissionDecision.OUT_OF_ORDER,
        ForwardEventDisposition.CORRECTION: ForwardAdmissionDecision.CORRECTION,
    }
    return ForwardAdmissionResolution(decisions[observation.disposition], next_state, event_fingerprint)


def _validate_observation(
    state: ForwardLiveAdmissionState,
    event: CanonicalForwardEvent,
    observation: ForwardEventObservation,
) -> None:
    """Verify caller-supplied classification against the persisted cursor."""

    instance = state.checkpoint.instance
    current_id = instance.last_event_id
    current_sequence = instance.last_event_sequence if current_id is not None else -1
    processed = state.checkpoint.processed_event_ids

    if event.correction_of is not None:
        expected = ForwardEventDisposition.CORRECTION
    elif event.event_id in processed or event.event_id == current_id:
        expected = ForwardEventDisposition.DUPLICATE
    elif event.sequence <= current_sequence:
        expected = ForwardEventDisposition.OUT_OF_ORDER
    elif event.sequence > current_sequence + 1:
        expected = ForwardEventDisposition.GAP
    else:
        expected = ForwardEventDisposition.ACCEPTED
    if observation.disposition is not expected:
        raise ValueError("forward event observation disposition does not match live cursor")

    if expected is ForwardEventDisposition.GAP:
        if (
            observation.missing_sequence_start != current_sequence + 1
            or observation.missing_sequence_end != event.sequence - 1
        ):
            raise ValueError("gap observation missing sequence bounds do not match live cursor")
        return

    if expected is ForwardEventDisposition.ACCEPTED:
        expected_cursor = ForwardCursor(event.sequence, event.event_id, event.event_time)
        if observation.next_cursor != expected_cursor:
            raise ValueError("accepted observation cursor does not match the event")
        return

    cursor = observation.next_cursor
    if current_id is None:
        unchanged = (
            cursor.last_sequence == -1
            and cursor.last_event_id is None
            and cursor.last_event_time is None
        )
    else:
        unchanged = (
            cursor.last_sequence == current_sequence
            and cursor.last_event_id == current_id
            and cursor.last_event_time is not None
        )
    if not unchanged:
        raise ValueError("non-accepted observation must preserve the live cursor")
