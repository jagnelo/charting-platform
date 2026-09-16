from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.strategy_lab_v2.admission import (
    ExecutionAdmissionDecision,
    ExecutionAdmissionLedger,
    resolve_execution_admission,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.execution import authorize_execution
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import (
    StrategyRuntimeRequest,
    preflight_strategy_runtime,
)
from app.strategy_lab_v2.tests.test_execution import _execution_fixture
from app.strategy_lab_v2.tests.test_runtime_execution import _profile
from app.strategy_lab_v2.workers import WorkerKind, WorkerPoolState, WorkerProfile

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _request(
    attempt_id: str,
    profile: RuntimeIsolationProfile,
    *,
    source_digest: str,
    network: bool = False,
) -> StrategyRuntimeRequest:
    return StrategyRuntimeRequest(
        content_digest({"request": attempt_id}),
        attempt_id,
        content_digest("package"),
        source_digest,
        content_digest("inputs"),
        profile.fingerprint,
        "strategy.main:run",
        RuntimeIsolationRequest(attempt_id, network_requested=network),
        NOW + timedelta(seconds=2),
    )


def _fixture(*, network: bool = False):
    trial, attempt, validation, capability, lease = _execution_fixture()
    authorization = authorize_execution(
        trial,
        attempt,
        validation,
        capability,
        lease,
        now=NOW + timedelta(seconds=3),
    )
    profile = _profile()
    request = _request(
        attempt.attempt_id,
        profile,
        source_digest=authorization.source_digest,
        network=network,
    )
    preflight = preflight_strategy_runtime(request, profile)
    pool = WorkerPoolState(WorkerProfile("worker-1", WorkerKind.BACKTEST, profile.fingerprint))
    return authorization, request, preflight, pool


def _reservation(value: str) -> str:
    return content_digest({"reservation": value})


def test_admission_composes_authorization_runtime_and_serial_capacity() -> None:
    authorization, request, preflight, pool = _fixture()
    resolution = resolve_execution_admission(
        ExecutionAdmissionLedger(),
        authorization,
        request,
        preflight,
        pool,
        reservation_id=_reservation("one"),
        now=NOW + timedelta(seconds=4),
    )

    assert resolution.decision is ExecutionAdmissionDecision.ADMIT
    assert resolution.admission is not None
    assert resolution.admission.attempt_id == authorization.attempt_id
    assert resolution.admission.worker_id == "worker-1"
    assert resolution.admission.reservation_id == _reservation("one")
    assert resolution.admission.authoritative == authorization.authoritative
    assert len(resolution.pool.active_reservations) == 1
    assert len(resolution.ledger.admissions) == 1


def test_exact_admission_replays_only_with_a_live_matching_reservation() -> None:
    authorization, request, preflight, pool = _fixture()
    first = resolve_execution_admission(
        ExecutionAdmissionLedger(), authorization, request, preflight, pool,
        reservation_id=_reservation("one"), now=NOW + timedelta(seconds=4)
    )
    replay = resolve_execution_admission(
        first.ledger, authorization, request, preflight, first.pool,
        reservation_id=_reservation("one"), now=NOW + timedelta(seconds=5)
    )
    assert replay.decision is ExecutionAdmissionDecision.REPLAY_EXISTING
    assert replay.admission == first.admission
    assert replay.pool == first.pool

    released = replace(
        first.pool,
        reservations=(replace(first.pool.reservations[0], released_at=NOW + timedelta(seconds=6)),),
    )
    missing = resolve_execution_admission(
        first.ledger, authorization, request, preflight, released,
        reservation_id=_reservation("one"), now=NOW + timedelta(seconds=7)
    )
    assert missing.decision is ExecutionAdmissionDecision.REJECT
    assert missing.rejection_reason == "admission receipt is missing its active worker reservation"


def test_admission_reports_capacity_and_conflicting_attempt_content() -> None:
    authorization, request, preflight, pool = _fixture()
    first = resolve_execution_admission(
        ExecutionAdmissionLedger(), authorization, request, preflight, pool,
        reservation_id=_reservation("one"), now=NOW + timedelta(seconds=4)
    )
    saturated_request = _request(
        "attempt-2",
        _profile(),
        source_digest=authorization.source_digest,
    )
    saturated_preflight = preflight_strategy_runtime(saturated_request, _profile())
    other_authorization = replace(authorization, attempt_id="attempt-2")
    saturated = resolve_execution_admission(
        ExecutionAdmissionLedger(), other_authorization, saturated_request, saturated_preflight,
        first.pool, reservation_id=_reservation("two"), now=NOW + timedelta(seconds=5)
    )
    assert saturated.decision is ExecutionAdmissionDecision.SATURATED
    conflict = resolve_execution_admission(
        first.ledger, authorization, request, preflight, first.pool,
        reservation_id=_reservation("different"), now=NOW + timedelta(seconds=5)
    )
    assert conflict.decision is ExecutionAdmissionDecision.CONFLICT
    assert conflict.rejection_reason == "attempt is already bound to different admission content"


def test_admission_fails_closed_for_runtime_or_worker_identity_mismatches() -> None:
    authorization, request, preflight, pool = _fixture(network=True)
    rejected = resolve_execution_admission(
        ExecutionAdmissionLedger(), authorization, request, preflight, pool,
        reservation_id=_reservation("one"), now=NOW + timedelta(seconds=4)
    )
    assert rejected.decision is ExecutionAdmissionDecision.REJECT
    assert rejected.rejection_reason == "runtime preflight is not accepted"

    good_authorization, good_request, good_preflight, good_pool = _fixture()
    wrong_worker = WorkerPoolState(
        WorkerProfile("worker-2", WorkerKind.BACKTEST, good_pool.profile.runtime_profile_fingerprint)
    )
    worker_rejected = resolve_execution_admission(
        ExecutionAdmissionLedger(), good_authorization, good_request, good_preflight, wrong_worker,
        reservation_id=_reservation("one"), now=NOW + timedelta(seconds=4)
    )
    assert worker_rejected.decision is ExecutionAdmissionDecision.REJECT
    assert worker_rejected.rejection_reason == "authorization lease is bound to a different worker"


def test_admission_requires_monotonic_time_and_active_worker_reservation() -> None:
    authorization, request, preflight, pool = _fixture()
    early = resolve_execution_admission(
        ExecutionAdmissionLedger(), authorization, request, preflight, pool,
        reservation_id=_reservation("one"), now=NOW + timedelta(seconds=1)
    )
    assert early.decision is ExecutionAdmissionDecision.REJECT
    assert early.rejection_reason == "admission time cannot precede authorization"

    accepted = resolve_execution_admission(
        ExecutionAdmissionLedger(), authorization, request, preflight, pool,
        reservation_id=_reservation("one"), now=NOW + timedelta(seconds=4)
    )
    inconsistent = resolve_execution_admission(
        ExecutionAdmissionLedger(), authorization, request, preflight, accepted.pool,
        reservation_id=_reservation("different"), now=NOW + timedelta(seconds=5)
    )
    assert inconsistent.decision is ExecutionAdmissionDecision.REJECT
    assert inconsistent.rejection_reason == "worker reservation exists without an admission receipt"
