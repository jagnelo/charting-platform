"""Atomic, storage-neutral staging of a search candidate dispatch."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.admission import (
    ExecutionAdmissionDecision,
    ExecutionAdmissionLedger,
    resolve_execution_admission,
)
from app.strategy_lab_v2.dispatch import (
    DispatchDecision,
    DispatchEnvelope,
    DispatchRequest,
    DispatchResolution,
    build_dispatch_envelope,
    resolve_idempotent_dispatch,
)
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.runtime_execution import (
    StrategyRuntimePreflight,
    StrategyRuntimeRequest,
)
from app.strategy_lab_v2.search_state import (
    SearchExecutionState,
    SearchStateDecision,
    start_search_candidate,
)
from app.strategy_lab_v2.workers import WorkerPoolState


class SearchDispatchDecision(StrEnum):
    ENQUEUE = "enqueue"
    REPLAY_EXISTING = "replay_existing"
    SATURATED = "saturated"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class SearchDispatchResolution:
    """Candidate, admission, and dispatch states returned as one decision."""

    decision: SearchDispatchDecision
    search_state: SearchExecutionState
    admission_ledger: ExecutionAdmissionLedger
    pool: WorkerPoolState
    dispatch_resolution: DispatchResolution | None = None
    envelope: DispatchEnvelope | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, SearchDispatchDecision):
            raise TypeError("decision must be a SearchDispatchDecision")
        if not isinstance(self.search_state, SearchExecutionState):
            raise TypeError("search_state must be a SearchExecutionState")
        if not isinstance(self.admission_ledger, ExecutionAdmissionLedger):
            raise TypeError("admission_ledger must be an ExecutionAdmissionLedger")
        if not isinstance(self.pool, WorkerPoolState):
            raise TypeError("pool must be a WorkerPoolState")
        if self.dispatch_resolution is not None and not isinstance(
            self.dispatch_resolution, DispatchResolution
        ):
            raise TypeError("dispatch_resolution must be a DispatchResolution")
        if self.envelope is not None and not isinstance(self.envelope, DispatchEnvelope):
            raise TypeError("envelope must be a DispatchEnvelope")
        if self.decision in {
            SearchDispatchDecision.ENQUEUE,
            SearchDispatchDecision.REPLAY_EXISTING,
        }:
            if self.dispatch_resolution is None or self.envelope is None:
                raise ValueError("successful dispatch resolutions require dispatch evidence")
            expected = (
                DispatchDecision.ENQUEUE
                if self.decision is SearchDispatchDecision.ENQUEUE
                else DispatchDecision.REPLAY_EXISTING
            )
            if self.dispatch_resolution.decision is not expected:
                raise ValueError("search dispatch decision must match dispatch evidence")
        if self.decision in {
            SearchDispatchDecision.CONFLICT,
            SearchDispatchDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("conflicting and rejected dispatches require a reason")
        if (
            self.decision
            not in {SearchDispatchDecision.REJECT, SearchDispatchDecision.CONFLICT}
            and self.rejection_reason
        ):
            raise ValueError("successful or saturated dispatches cannot contain a reason")


def resolve_search_dispatch(
    state: SearchExecutionState,
    *,
    candidate_index: int,
    attempt_id: str,
    authorization: ExecutionAuthorization,
    runtime_request: StrategyRuntimeRequest,
    runtime_preflight: StrategyRuntimePreflight,
    admission_ledger: ExecutionAdmissionLedger,
    pool: WorkerPoolState,
    reservation_id: str,
    dispatch_request: DispatchRequest,
    prior_dispatches: Sequence[DispatchRequest],
    now: datetime,
) -> SearchDispatchResolution:
    """Stage a candidate start, worker admission, and idempotent queue message.

    No returned state is committed by this function. If any later gate fails,
    the original search state, admission ledger, and worker pool are returned so
    a persistence adapter cannot leave a running candidate without a dispatch.
    """

    if not isinstance(state, SearchExecutionState):
        raise TypeError("state must be a SearchExecutionState")
    if not isinstance(admission_ledger, ExecutionAdmissionLedger):
        raise TypeError("admission_ledger must be an ExecutionAdmissionLedger")
    if not isinstance(pool, WorkerPoolState):
        raise TypeError("pool must be a WorkerPoolState")
    if not isinstance(dispatch_request, DispatchRequest):
        raise TypeError("dispatch_request must be a DispatchRequest")
    if not isinstance(prior_dispatches, Sequence):
        raise TypeError("prior_dispatches must be a sequence")
    if dispatch_request.attempt_id != attempt_id:
        return _reject(state, admission_ledger, pool, "dispatch request references a different attempt")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("dispatch time must be timezone-aware")
    if now < dispatch_request.created_at:
        return _reject(state, admission_ledger, pool, "dispatch time cannot precede request creation")

    started = start_search_candidate(state, candidate_index, attempt_id=attempt_id, now=now)
    if started.decision is SearchStateDecision.REJECT:
        return _reject(state, admission_ledger, pool, started.rejection_reason or "search candidate rejected")

    admitted = resolve_execution_admission(
        admission_ledger,
        authorization,
        runtime_request,
        runtime_preflight,
        pool,
        reservation_id=reservation_id,
        now=now,
    )
    if admitted.decision is ExecutionAdmissionDecision.SATURATED:
        return SearchDispatchResolution(
            SearchDispatchDecision.SATURATED,
            state,
            admission_ledger,
            pool,
        )
    if admitted.decision is ExecutionAdmissionDecision.CONFLICT:
        return _reject(
            state,
            admission_ledger,
            pool,
            admitted.rejection_reason or "execution admission conflicts",
            decision=SearchDispatchDecision.CONFLICT,
        )
    if admitted.decision is ExecutionAdmissionDecision.REJECT:
        return _reject(
            state,
            admission_ledger,
            pool,
            admitted.rejection_reason or "execution admission rejected",
        )
    if admitted.admission is None:
        raise AssertionError("accepted execution admission must include a receipt")

    dispatch = resolve_idempotent_dispatch(dispatch_request, prior_dispatches)
    if dispatch.decision is DispatchDecision.IDEMPOTENCY_CONFLICT:
        return _reject(
            state,
            admission_ledger,
            pool,
            "dispatch idempotency key is bound to different content",
            decision=SearchDispatchDecision.CONFLICT,
        )
    if (
        admitted.decision is ExecutionAdmissionDecision.ADMIT
        and dispatch.decision is DispatchDecision.REPLAY_EXISTING
    ):
        return _reject(
            state,
            admission_ledger,
            pool,
            "dispatch exists without an execution admission receipt",
            decision=SearchDispatchDecision.CONFLICT,
        )

    envelope = build_dispatch_envelope(dispatch_request)
    final_decision = (
        SearchDispatchDecision.ENQUEUE
        if dispatch.decision is DispatchDecision.ENQUEUE
        else SearchDispatchDecision.REPLAY_EXISTING
    )
    return SearchDispatchResolution(
        final_decision,
        started.state,
        admitted.ledger,
        admitted.pool,
        dispatch,
        envelope,
    )


def _reject(
    state: SearchExecutionState,
    admission_ledger: ExecutionAdmissionLedger,
    pool: WorkerPoolState,
    reason: str,
    *,
    decision: SearchDispatchDecision = SearchDispatchDecision.REJECT,
) -> SearchDispatchResolution:
    return SearchDispatchResolution(
        decision,
        state,
        admission_ledger,
        pool,
        rejection_reason=reason,
    )
