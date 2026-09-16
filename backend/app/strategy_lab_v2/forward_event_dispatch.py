"""Atomic dispatch of broker-free forward-event work."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import (
    DispatchDecision,
    DispatchEnvelope,
    DispatchRequest,
    DispatchResolution,
    build_dispatch_envelope,
    resolve_idempotent_dispatch,
)
from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState
from app.strategy_lab_v2.forward_corrections import (
    CounterfactualReplayPlan,
    ForwardCorrectionCommand,
)
from app.strategy_lab_v2.forward_event_transaction import (
    ForwardEventTransactionDecision,
    ForwardEventTransactionResolution,
    resolve_forward_event_transaction,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent, ForwardEventObservation


class ForwardEventDispatchDecision(StrEnum):
    ENQUEUE = "enqueue"
    REPLAY_EXISTING = "replay_existing"
    BUFFERED = "buffered"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    CORRECTION_ENQUEUE = "correction_enqueue"
    CORRECTION_REPLAY = "correction_replay"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ForwardEventDispatchResolution:
    """Forward state and optional queue evidence returned as one decision."""

    decision: ForwardEventDispatchDecision
    state: ForwardLiveAdmissionState
    event_transaction: ForwardEventTransactionResolution
    dispatch_resolution: DispatchResolution | None = None
    envelope: DispatchEnvelope | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ForwardEventDispatchDecision):
            raise TypeError("decision must be a ForwardEventDispatchDecision")
        if not isinstance(self.state, ForwardLiveAdmissionState):
            raise TypeError("state must be a ForwardLiveAdmissionState")
        if not isinstance(self.event_transaction, ForwardEventTransactionResolution):
            raise TypeError("event_transaction must be a ForwardEventTransactionResolution")
        if self.dispatch_resolution is not None and not isinstance(
            self.dispatch_resolution, DispatchResolution
        ):
            raise TypeError("dispatch_resolution must be a DispatchResolution")
        if self.envelope is not None and not isinstance(self.envelope, DispatchEnvelope):
            raise TypeError("envelope must be a DispatchEnvelope")
        if self.decision in {
            ForwardEventDispatchDecision.ENQUEUE,
            ForwardEventDispatchDecision.REPLAY_EXISTING,
            ForwardEventDispatchDecision.CORRECTION_ENQUEUE,
            ForwardEventDispatchDecision.CORRECTION_REPLAY,
            ForwardEventDispatchDecision.BUFFERED,
        } and self.dispatch_resolution is None:
            raise ValueError("dispatching decisions require dispatch evidence")
        if self.decision in {
            ForwardEventDispatchDecision.ENQUEUE,
            ForwardEventDispatchDecision.CORRECTION_ENQUEUE,
        } and self.envelope is None:
            raise ValueError("enqueue decisions require a dispatch envelope")
        if self.decision in {
            ForwardEventDispatchDecision.CONFLICT,
            ForwardEventDispatchDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if self.decision not in {
            ForwardEventDispatchDecision.CONFLICT,
            ForwardEventDispatchDecision.REJECT,
        } and self.rejection_reason:
            raise ValueError("successful dispatch decisions cannot contain a reason")


def resolve_forward_event_dispatch(
    state: ForwardLiveAdmissionState,
    event: CanonicalForwardEvent,
    observation: ForwardEventObservation,
    *,
    dispatch_request: DispatchRequest,
    prior_dispatches: tuple[DispatchRequest, ...] = (),
    correction_command: ForwardCorrectionCommand | None = None,
    existing_replay_plan: CounterfactualReplayPlan | None = None,
) -> ForwardEventDispatchResolution:
    """Stage forward admission and worker dispatch without partial state writes."""

    if not isinstance(state, ForwardLiveAdmissionState):
        raise TypeError("state must be a ForwardLiveAdmissionState")
    if not isinstance(dispatch_request, DispatchRequest):
        raise TypeError("dispatch_request must be a DispatchRequest")
    if not isinstance(prior_dispatches, tuple):
        raise TypeError("prior_dispatches must be a tuple")
    instance_id = state.checkpoint.instance.instance_id
    if dispatch_request.attempt_id != instance_id:
        return _reject(state, event, observation, "dispatch request must reference the forward instance")
    transaction = resolve_forward_event_transaction(
        state,
        event,
        observation,
        correction_command=correction_command,
        existing_replay_plan=existing_replay_plan,
    )
    if transaction.decision in {
        ForwardEventTransactionDecision.CONFLICT,
        ForwardEventTransactionDecision.REJECT,
    }:
        return ForwardEventDispatchResolution(
            ForwardEventDispatchDecision.CONFLICT
            if transaction.decision is ForwardEventTransactionDecision.CONFLICT
            else ForwardEventDispatchDecision.REJECT,
            state,
            transaction,
            rejection_reason=transaction.rejection_reason or "forward event transaction rejected",
        )
    if transaction.decision in {
        ForwardEventTransactionDecision.DUPLICATE,
        ForwardEventTransactionDecision.OUT_OF_ORDER,
    }:
        return ForwardEventDispatchResolution(
            ForwardEventDispatchDecision(
                transaction.decision.value
            ),
            transaction.state,
            transaction,
        )

    expected_payload = content_digest(
        {
            "event_fingerprint": transaction.event_fingerprint,
            "replay_plan_fingerprint": (
                transaction.replay_plan.fingerprint if transaction.replay_plan is not None else None
            ),
        }
    )
    if dispatch_request.payload_digest != expected_payload:
        return ForwardEventDispatchResolution(
            ForwardEventDispatchDecision.REJECT,
            state,
            transaction,
            rejection_reason="dispatch payload does not match forward event evidence",
        )
    dispatch = resolve_idempotent_dispatch(dispatch_request, prior_dispatches)
    if dispatch.decision is DispatchDecision.IDEMPOTENCY_CONFLICT:
        return ForwardEventDispatchResolution(
            ForwardEventDispatchDecision.CONFLICT,
            state,
            transaction,
            dispatch,
            rejection_reason="forward dispatch idempotency key is bound to different content",
        )
    if (
        transaction.decision is ForwardEventTransactionDecision.CORRECTION_ACCEPTED
        and dispatch.decision is DispatchDecision.REPLAY_EXISTING
    ):
        return ForwardEventDispatchResolution(
            ForwardEventDispatchDecision.CONFLICT,
            state,
            transaction,
            dispatch,
            rejection_reason="dispatch exists without a correction replay receipt",
        )
    envelope = build_dispatch_envelope(dispatch_request)
    if transaction.decision is ForwardEventTransactionDecision.CORRECTION_ACCEPTED:
        decision = ForwardEventDispatchDecision.CORRECTION_ENQUEUE
    elif transaction.decision is ForwardEventTransactionDecision.CORRECTION_REPLAY:
        decision = ForwardEventDispatchDecision.CORRECTION_REPLAY
    elif transaction.decision is ForwardEventTransactionDecision.GAP:
        decision = ForwardEventDispatchDecision.BUFFERED
    elif dispatch.decision is DispatchDecision.ENQUEUE:
        decision = ForwardEventDispatchDecision.ENQUEUE
    else:
        decision = ForwardEventDispatchDecision.REPLAY_EXISTING
    return ForwardEventDispatchResolution(
        decision,
        transaction.state,
        transaction,
        dispatch,
        envelope,
    )


def _reject(
    state: ForwardLiveAdmissionState,
    event: CanonicalForwardEvent,
    observation: ForwardEventObservation,
    reason: str,
) -> ForwardEventDispatchResolution:
    transaction = resolve_forward_event_transaction(state, event, observation)
    return ForwardEventDispatchResolution(
        ForwardEventDispatchDecision.REJECT,
        state,
        transaction,
        rejection_reason=reason,
    )
