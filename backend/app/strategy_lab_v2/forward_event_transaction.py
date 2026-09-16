"""Atomic live-event admission with mandatory correction replay evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.forward_admission import (
    ForwardAdmissionDecision,
    ForwardLiveAdmissionState,
    admit_forward_event,
)
from app.strategy_lab_v2.forward_corrections import (
    CounterfactualReplayPlan,
    ForwardCorrectionCommand,
    ForwardCorrectionDecision,
    resolve_forward_correction,
)
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardEventDisposition,
    ForwardEventObservation,
)


class ForwardEventTransactionDecision(StrEnum):
    ACCEPTED = "accepted"
    REPLAY_EXISTING = "replay_existing"
    GAP = "gap"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    CORRECTION_ACCEPTED = "correction_accepted"
    CORRECTION_REPLAY = "correction_replay"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ForwardEventTransactionResolution:
    """One event and optional correction-plan decision over a live checkpoint."""

    decision: ForwardEventTransactionDecision
    state: ForwardLiveAdmissionState
    event_fingerprint: str
    replay_plan: CounterfactualReplayPlan | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ForwardEventTransactionDecision):
            raise TypeError("decision must be a ForwardEventTransactionDecision")
        if not isinstance(self.state, ForwardLiveAdmissionState):
            raise TypeError("state must be a ForwardLiveAdmissionState")
        require_sha256_digest(self.event_fingerprint, field_name="event_fingerprint")
        if self.replay_plan is not None and not isinstance(
            self.replay_plan, CounterfactualReplayPlan
        ):
            raise TypeError("replay_plan must be a CounterfactualReplayPlan")
        if self.decision in {
            ForwardEventTransactionDecision.CORRECTION_ACCEPTED,
            ForwardEventTransactionDecision.CORRECTION_REPLAY,
        } and self.replay_plan is None:
            raise ValueError("correction decisions require a replay plan")
        if self.decision in {
            ForwardEventTransactionDecision.CONFLICT,
            ForwardEventTransactionDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if self.decision not in {
            ForwardEventTransactionDecision.CONFLICT,
            ForwardEventTransactionDecision.REJECT,
        } and self.rejection_reason:
            raise ValueError("successful event decisions cannot contain a reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def resolve_forward_event_transaction(
    state: ForwardLiveAdmissionState,
    event: CanonicalForwardEvent,
    observation: ForwardEventObservation,
    *,
    correction_command: ForwardCorrectionCommand | None = None,
    existing_replay_plan: CounterfactualReplayPlan | None = None,
) -> ForwardEventTransactionResolution:
    """Resolve one event and correction replay as one all-or-nothing transition.

    Ordinary events use the existing admission decision. Correction events must
    also resolve a replay command; if that second gate fails, the original live
    state is returned instead of leaving a correction admitted without a replay
    identity. The function performs no engine, broker, queue, or persistence I/O.
    """

    if not isinstance(state, ForwardLiveAdmissionState):
        raise TypeError("state must be a ForwardLiveAdmissionState")
    if not isinstance(event, CanonicalForwardEvent):
        raise TypeError("event must be a CanonicalForwardEvent")
    if not isinstance(observation, ForwardEventObservation):
        raise TypeError("observation must be a ForwardEventObservation")
    if correction_command is not None and not isinstance(
        correction_command, ForwardCorrectionCommand
    ):
        raise TypeError("correction_command must be a ForwardCorrectionCommand")
    if existing_replay_plan is not None and not isinstance(
        existing_replay_plan, CounterfactualReplayPlan
    ):
        raise TypeError("existing_replay_plan must be a CounterfactualReplayPlan")
    event_fingerprint = content_digest(event)
    if observation.disposition is ForwardEventDisposition.CORRECTION:
        if correction_command is None:
            return _reject(
                state,
                event_fingerprint,
                "correction events require a counterfactual replay command",
            )
    elif correction_command is not None or existing_replay_plan is not None:
        return _reject(
            state,
            event_fingerprint,
            "replay evidence is only valid for correction events",
        )

    admission = admit_forward_event(state, event, observation)
    if admission.decision is ForwardAdmissionDecision.CONFLICT:
        return _reject(
            state,
            event_fingerprint,
            admission.rejection_reason or "forward event admission conflicts",
            decision=ForwardEventTransactionDecision.CONFLICT,
        )
    if admission.decision is ForwardAdmissionDecision.REJECT:
        return _reject(
            state,
            event_fingerprint,
            admission.rejection_reason or "forward event admission rejected",
        )
    if observation.disposition is ForwardEventDisposition.CORRECTION:
        assert correction_command is not None
        correction = resolve_forward_correction(
            admission.state,
            correction_command,
            event,
            observation,
            existing_plan=existing_replay_plan,
        )
        if correction.decision is ForwardCorrectionDecision.CONFLICT:
            return _reject(
                state,
                event_fingerprint,
                correction.rejection_reason or "forward correction conflicts",
                decision=ForwardEventTransactionDecision.CONFLICT,
            )
        if correction.decision is ForwardCorrectionDecision.REJECT:
            return _reject(
                state,
                event_fingerprint,
                correction.rejection_reason or "forward correction rejected",
            )
        assert correction.plan is not None
        decision = (
            ForwardEventTransactionDecision.CORRECTION_REPLAY
            if correction.decision is ForwardCorrectionDecision.REPLAY_EXISTING
            else ForwardEventTransactionDecision.CORRECTION_ACCEPTED
        )
        return ForwardEventTransactionResolution(
            decision,
            admission.state,
            event_fingerprint,
            correction.plan,
        )

    decisions = {
        ForwardAdmissionDecision.ACCEPTED: ForwardEventTransactionDecision.ACCEPTED,
        ForwardAdmissionDecision.REPLAY_EXISTING: ForwardEventTransactionDecision.REPLAY_EXISTING,
        ForwardAdmissionDecision.GAP: ForwardEventTransactionDecision.GAP,
        ForwardAdmissionDecision.DUPLICATE: ForwardEventTransactionDecision.DUPLICATE,
        ForwardAdmissionDecision.OUT_OF_ORDER: ForwardEventTransactionDecision.OUT_OF_ORDER,
    }
    return ForwardEventTransactionResolution(
        decisions[admission.decision],
        admission.state,
        event_fingerprint,
    )


def _reject(
    state: ForwardLiveAdmissionState,
    event_fingerprint: str,
    reason: str,
    *,
    decision: ForwardEventTransactionDecision = ForwardEventTransactionDecision.REJECT,
) -> ForwardEventTransactionResolution:
    return ForwardEventTransactionResolution(
        decision,
        state,
        event_fingerprint,
        rejection_reason=reason,
    )
