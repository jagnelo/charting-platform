from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import DispatchDecision, DispatchRequest
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile
from app.strategy_lab_v2.runtime_execution import preflight_strategy_runtime
from app.strategy_lab_v2.search_dispatch import SearchDispatchDecision, resolve_search_dispatch
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchExecutionState,
    new_search_execution_state,
    request_search_cancellation,
)
from app.strategy_lab_v2.tests.test_admission import _fixture, _request, _reservation

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _dispatch(attempt_id: str, *, key: str = "dispatch-one", payload: str = "payload") -> DispatchRequest:
    return DispatchRequest(
        key,
        attempt_id,
        content_digest(payload),
        "strategy-backtest",
        NOW + timedelta(seconds=3),
    )


def _state() -> SearchExecutionState:
    return new_search_execution_state(
        content_digest("experiment"),
        (content_digest("trial-one"),),
        now=NOW,
    )


def test_search_dispatch_stages_candidate_admission_and_queue_message() -> None:
    authorization, request, preflight, pool = _fixture()
    state = _state()
    dispatch = _dispatch("attempt-1")
    resolution = resolve_search_dispatch(
        state,
        candidate_index=0,
        attempt_id="attempt-1",
        authorization=authorization,
        runtime_request=request,
        runtime_preflight=preflight,
        admission_ledger=ExecutionAdmissionLedger(),
        pool=pool,
        reservation_id=_reservation("one"),
        dispatch_request=dispatch,
        prior_dispatches=(),
        now=NOW + timedelta(seconds=4),
    )

    assert resolution.decision is SearchDispatchDecision.ENQUEUE
    assert resolution.search_state.candidates[0].phase is SearchCandidatePhase.RUNNING
    assert resolution.admission_ledger.admissions[0].attempt_id == "attempt-1"
    assert resolution.pool.active_reservations[0].attempt_id == "attempt-1"
    assert resolution.dispatch_resolution is not None
    assert resolution.dispatch_resolution.decision is DispatchDecision.ENQUEUE
    assert resolution.envelope is not None
    assert resolution.envelope.message_id == dispatch.fingerprint


def test_exact_search_dispatch_replays_without_mutating_any_state() -> None:
    authorization, request, preflight, pool = _fixture()
    state = _state()
    dispatch = _dispatch("attempt-1")
    first = resolve_search_dispatch(
        state,
        candidate_index=0,
        attempt_id="attempt-1",
        authorization=authorization,
        runtime_request=request,
        runtime_preflight=preflight,
        admission_ledger=ExecutionAdmissionLedger(),
        pool=pool,
        reservation_id=_reservation("one"),
        dispatch_request=dispatch,
        prior_dispatches=(),
        now=NOW + timedelta(seconds=4),
    )
    replay = resolve_search_dispatch(
        first.search_state,
        candidate_index=0,
        attempt_id="attempt-1",
        authorization=authorization,
        runtime_request=request,
        runtime_preflight=preflight,
        admission_ledger=first.admission_ledger,
        pool=first.pool,
        reservation_id=_reservation("one"),
        dispatch_request=dispatch,
        prior_dispatches=(dispatch,),
        now=NOW + timedelta(seconds=5),
    )

    assert replay.decision is SearchDispatchDecision.REPLAY_EXISTING
    assert replay.search_state == first.search_state
    assert replay.admission_ledger == first.admission_ledger
    assert replay.pool == first.pool
    assert replay.dispatch_resolution is not None
    assert replay.dispatch_resolution.decision is DispatchDecision.REPLAY_EXISTING


def test_saturation_and_dispatch_conflict_roll_back_candidate_and_admission() -> None:
    authorization, request, preflight, pool = _fixture()
    state = new_search_execution_state(
        content_digest("experiment"),
        (content_digest("trial-one"), content_digest("trial-two")),
        now=NOW,
    )
    dispatch = _dispatch("attempt-1")
    first = resolve_search_dispatch(
        state,
        candidate_index=0,
        attempt_id="attempt-1",
        authorization=authorization,
        runtime_request=request,
        runtime_preflight=preflight,
        admission_ledger=ExecutionAdmissionLedger(),
        pool=pool,
        reservation_id=_reservation("one"),
        dispatch_request=dispatch,
        prior_dispatches=(),
        now=NOW + timedelta(seconds=4),
    )
    profile = RuntimeIsolationProfile(
        content_digest("image"),
        "python-3.12",
        allowed_dependency_digests=frozenset({content_digest("dep")}),
        output_limit_bytes=100,
    )
    authorization_two = replace(authorization, attempt_id="attempt-2")
    request_two = _request("attempt-2", profile, source_digest=authorization.source_digest)
    preflight_two = preflight_strategy_runtime(request_two, profile)
    saturated = resolve_search_dispatch(
        first.search_state,
        candidate_index=1,
        attempt_id="attempt-2",
        authorization=authorization_two,
        runtime_request=request_two,
        runtime_preflight=preflight_two,
        admission_ledger=first.admission_ledger,
        pool=first.pool,
        reservation_id=_reservation("two"),
        dispatch_request=_dispatch("attempt-2", key="dispatch-two"),
        prior_dispatches=(),
        now=NOW + timedelta(seconds=5),
    )
    assert saturated.decision is SearchDispatchDecision.SATURATED
    assert saturated.search_state == first.search_state
    assert saturated.admission_ledger == first.admission_ledger
    assert saturated.pool == first.pool

    conflict = resolve_search_dispatch(
        state,
        candidate_index=0,
        attempt_id="attempt-1",
        authorization=authorization,
        runtime_request=request,
        runtime_preflight=preflight,
        admission_ledger=ExecutionAdmissionLedger(),
        pool=pool,
        reservation_id=_reservation("one"),
        dispatch_request=dispatch,
        prior_dispatches=(replace(dispatch, payload_digest=content_digest("different")),),
        now=NOW + timedelta(seconds=4),
    )
    assert conflict.decision is SearchDispatchDecision.CONFLICT
    assert conflict.search_state == state
    assert conflict.admission_ledger == ExecutionAdmissionLedger()
    assert conflict.pool == pool


def test_search_dispatch_rejects_cancelled_or_mismatched_dispatch_without_side_effects() -> None:
    authorization, request, preflight, pool = _fixture()
    state = _state()
    cancelled = request_search_cancellation(
        state,
        request_id=content_digest("cancel"),
        now=NOW + timedelta(seconds=1),
    ).state
    rejected = resolve_search_dispatch(
        cancelled,
        candidate_index=0,
        attempt_id="attempt-1",
        authorization=authorization,
        runtime_request=request,
        runtime_preflight=preflight,
        admission_ledger=ExecutionAdmissionLedger(),
        pool=pool,
        reservation_id=_reservation("one"),
        dispatch_request=_dispatch("attempt-1"),
        prior_dispatches=(),
        now=NOW + timedelta(seconds=4),
    )
    assert rejected.decision is SearchDispatchDecision.REJECT
    assert rejected.rejection_reason == "search cancellation has been requested"
    assert rejected.search_state == cancelled
    assert not rejected.admission_ledger.admissions

    mismatch = resolve_search_dispatch(
        state,
        candidate_index=0,
        attempt_id="attempt-1",
        authorization=authorization,
        runtime_request=request,
        runtime_preflight=preflight,
        admission_ledger=ExecutionAdmissionLedger(),
        pool=pool,
        reservation_id=_reservation("one"),
        dispatch_request=_dispatch("attempt-2"),
        prior_dispatches=(),
        now=NOW + timedelta(seconds=4),
    )
    assert mismatch.decision is SearchDispatchDecision.REJECT
    assert mismatch.rejection_reason == "dispatch request references a different attempt"
    assert mismatch.search_state == state
