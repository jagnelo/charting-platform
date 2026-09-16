from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.strategy_lab_v2.admission import ExecutionAdmission
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.execution_orchestration import plan_execution_orchestration
from app.strategy_lab_v2.tests.test_execution_orchestration import _fixtures
from app.strategy_lab_v2.tests.test_worker_execution import _fake_binary
from app.strategy_lab_v2.worker_execution import (
    WorkerExecutionResolution,
    execute_worker_handoff,
)
from app.strategy_lab_v2.worker_settlement import (
    WorkerSettlementDecision,
    WorkerSettlementLedger,
    settle_worker_execution,
)
from app.strategy_lab_v2.workers import (
    WorkerKind,
    WorkerPoolState,
    WorkerProfile,
    WorkerReservation,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _admitted_pool(values: tuple) -> tuple[WorkerPoolState, ExecutionAdmission]:
    _, admission, request, *_ = values
    reservation = WorkerReservation(
        admission.reservation_id,
        admission.worker_id,
        WorkerKind.BACKTEST,
        admission.attempt_id,
        NOW,
    )
    pool = WorkerPoolState(
        WorkerProfile(
            admission.worker_id,
            WorkerKind.BACKTEST,
            request.runtime_profile_fingerprint,
        ),
        (reservation,),
    )
    return pool, admission


def _execution(values: tuple, tmp_path: Path) -> WorkerExecutionResolution:
    orchestration = plan_execution_orchestration(*values)
    return execute_worker_handoff(
        orchestration,
        *values,
        observed_at=NOW + timedelta(seconds=1),
        docker_binary=_fake_binary(tmp_path, "printf 'ok'"),
    )


def test_settlement_releases_serial_slot_and_exact_retry_replays(tmp_path: Path) -> None:
    values = _fixtures()
    pool, admission = _admitted_pool(values)
    execution = _execution(values, tmp_path)

    settled = settle_worker_execution(
        WorkerSettlementLedger(),
        pool,
        admission,
        execution,
        released_at=NOW + timedelta(seconds=2),
    )
    assert settled.decision is WorkerSettlementDecision.RELEASED
    assert settled.record is not None
    assert not settled.pool.active_reservations

    replay = settle_worker_execution(
        settled.ledger,
        settled.pool,
        admission,
        execution,
        released_at=NOW + timedelta(seconds=2),
    )
    assert replay.decision is WorkerSettlementDecision.REPLAY_EXISTING
    assert replay.record == settled.record
    assert replay.pool == settled.pool

    inconsistent = settle_worker_execution(
        settled.ledger,
        pool,
        admission,
        execution,
        released_at=NOW + timedelta(seconds=2),
    )
    assert inconsistent.decision is WorkerSettlementDecision.REJECT
    assert inconsistent.rejection_reason == (
        "settlement receipt exists but worker reservation is still active"
    )


def test_settlement_conflicts_on_changed_release_evidence(tmp_path: Path) -> None:
    values = _fixtures()
    pool, admission = _admitted_pool(values)
    execution = _execution(values, tmp_path)
    settled = settle_worker_execution(
        WorkerSettlementLedger(),
        pool,
        admission,
        execution,
        released_at=NOW + timedelta(seconds=2),
    )

    conflict = settle_worker_execution(
        settled.ledger,
        settled.pool,
        admission,
        execution,
        released_at=NOW + timedelta(seconds=3),
    )
    assert conflict.decision is WorkerSettlementDecision.CONFLICT
    assert conflict.pool == settled.pool
    assert "different worker settlement content" in (conflict.rejection_reason or "")


def test_settlement_rejects_unbound_or_missing_reservations(tmp_path: Path) -> None:
    values = _fixtures()
    pool, admission = _admitted_pool(values)
    execution = _execution(values, tmp_path)
    unbound = replace(
        execution,
        orchestration_plan=replace(
            execution.orchestration_plan,
            admission_fingerprint=content_digest("different-admission"),
        ),
    )
    rejected = settle_worker_execution(
        WorkerSettlementLedger(),
        pool,
        admission,
        unbound,
        released_at=NOW + timedelta(seconds=2),
    )
    assert rejected.decision is WorkerSettlementDecision.REJECT
    assert rejected.rejection_reason == "orchestration plan is not bound to the admission"

    missing = settle_worker_execution(
        WorkerSettlementLedger(),
        WorkerPoolState(pool.profile),
        admission,
        execution,
        released_at=NOW + timedelta(seconds=2),
    )
    assert missing.decision is WorkerSettlementDecision.REJECT
    assert missing.rejection_reason == "admission has no matching worker reservation"


def test_settlement_rejects_release_before_acquisition(tmp_path: Path) -> None:
    values = _fixtures()
    pool, admission = _admitted_pool(values)
    execution = _execution(values, tmp_path)
    rejected = settle_worker_execution(
        WorkerSettlementLedger(),
        pool,
        admission,
        execution,
        released_at=NOW - timedelta(seconds=1),
    )
    assert rejected.decision is WorkerSettlementDecision.REJECT
    assert rejected.rejection_reason == "release cannot precede reservation acquisition"
