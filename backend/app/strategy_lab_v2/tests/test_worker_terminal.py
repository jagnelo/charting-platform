from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.strategy_lab_v2.api_contracts import ApiError, ApiErrorCode
from app.strategy_lab_v2.lease_observations import LeaseObservationState
from app.strategy_lab_v2.lifecycle import ExecutionAttemptLease
from app.strategy_lab_v2.tests.test_execution_summary import _outcome, _progress, _receipt
from app.strategy_lab_v2.tests.test_result_publication import _result as result_fixture
from app.strategy_lab_v2.tests.test_worker_execution import (
    _fake_binary,
    _fixtures,
    _lease,
    _plan,
    _pool,
)
from app.strategy_lab_v2.worker_execution import execute_worker_handoff
from app.strategy_lab_v2.worker_settlement import WorkerSettlementDecision, WorkerSettlementLedger
from app.strategy_lab_v2.worker_terminal import (
    WorkerTerminalDecision,
    materialize_worker_terminal,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _execution(values: tuple, tmp_path: Path):
    return execute_worker_handoff(
        _plan(values),
        *values,
        worker_pool=_pool(values),
        lease_state=_lease(values),
        started_at=NOW,
        observed_at=NOW + timedelta(seconds=1),
        docker_binary=_fake_binary(tmp_path, "printf 'ok'"),
    )


def test_worker_terminal_commits_public_state_and_worker_release(tmp_path: Path) -> None:
    values = _fixtures()
    execution = _execution(values, tmp_path)
    _, admission, *_ = values
    result, *_ = result_fixture()
    resolved = materialize_worker_terminal(
        WorkerSettlementLedger(),
        _pool(values),
        _lease(values),
        admission,
        execution,
        _receipt(),
        _outcome(),
        _progress(),
        result=result,
        observed_at=NOW + timedelta(seconds=2),
        released_at=NOW + timedelta(seconds=3),
    )
    assert resolved.decision is WorkerTerminalDecision.COMMITTED
    assert resolved.terminal_resolution.outcome.result_digest == result.fingerprint
    assert not resolved.pool.active_reservations
    assert resolved.lease_state.lease.released_at == NOW + timedelta(seconds=3)
    assert resolved.settlement_resolution is not None
    assert resolved.settlement_resolution.decision is WorkerSettlementDecision.RELEASED

    replay = materialize_worker_terminal(
        resolved.settlement_ledger,
        resolved.pool,
        resolved.lease_state,
        admission,
        execution,
        _receipt(),
        resolved.outcome,
        resolved.progress,
        result=result,
        observed_at=NOW + timedelta(seconds=4),
        released_at=NOW + timedelta(seconds=3),
    )
    assert replay.decision is WorkerTerminalDecision.REPLAY_EXISTING
    assert replay.outcome == resolved.outcome
    assert replay.progress == resolved.progress
    assert replay.pool == resolved.pool
    assert replay.lease_state == resolved.lease_state


def test_worker_terminal_rejects_without_result_or_when_settlement_fails(tmp_path: Path) -> None:
    values = _fixtures()
    execution = _execution(values, tmp_path)
    _, admission, *_ = values
    rejected = materialize_worker_terminal(
        WorkerSettlementLedger(),
        _pool(values),
        _lease(values),
        admission,
        execution,
        _receipt(),
        _outcome(),
        _progress(),
        observed_at=NOW + timedelta(seconds=2),
        released_at=NOW + timedelta(seconds=3),
    )
    assert rejected.decision is WorkerTerminalDecision.REJECT
    assert rejected.settlement_resolution is None
    assert rejected.pool == _pool(values)

    expired = LeaseObservationState(
        ExecutionAttemptLease(
            admission.attempt_id,
            admission.worker_id,
            "lease-1",
            NOW,
            NOW,
            NOW + timedelta(seconds=1),
        )
    )
    result, *_ = result_fixture()
    settlement_rejected = materialize_worker_terminal(
        WorkerSettlementLedger(),
        _pool(values),
        expired,
        admission,
        execution,
        _receipt(),
        _outcome(),
        _progress(),
        result=result,
        observed_at=NOW + timedelta(seconds=2),
        released_at=NOW + timedelta(seconds=3),
    )
    assert settlement_rejected.decision is WorkerTerminalDecision.REJECT
    assert settlement_rejected.settlement_resolution is not None
    assert settlement_rejected.rejection_reason == "expired leases require worker recovery"
    assert settlement_rejected.outcome == _outcome()
    assert settlement_rejected.pool == _pool(values)


def test_worker_terminal_failed_runtime_requires_typed_error(tmp_path: Path) -> None:
    values = _fixtures()
    execution = execute_worker_handoff(
        _plan(values),
        *values,
        worker_pool=_pool(values),
        lease_state=_lease(values),
        started_at=NOW,
        observed_at=NOW + timedelta(seconds=1),
        docker_binary=_fake_binary(tmp_path, "exit 7"),
    )
    _, admission, *_ = values
    failed = materialize_worker_terminal(
        WorkerSettlementLedger(),
        _pool(values),
        _lease(values),
        admission,
        execution,
        _receipt(),
        _outcome(),
        _progress(),
        error=ApiError(ApiErrorCode.INTERNAL_ERROR, "worker failed", "request-1", 500, True),
        observed_at=NOW + timedelta(seconds=2),
        released_at=NOW + timedelta(seconds=3),
    )
    assert failed.decision is WorkerTerminalDecision.COMMITTED
    assert failed.terminal_resolution.outcome.error is not None
    assert failed.terminal_resolution.progress.phase.value == "failed"


def test_worker_terminal_rejects_release_before_terminal_observation(tmp_path: Path) -> None:
    values = _fixtures()
    execution = _execution(values, tmp_path)
    _, admission, *_ = values
    result, *_ = result_fixture()
    resolved = materialize_worker_terminal(
        WorkerSettlementLedger(),
        _pool(values),
        _lease(values),
        admission,
        execution,
        _receipt(),
        _outcome(),
        _progress(),
        result=result,
        observed_at=NOW + timedelta(seconds=3),
        released_at=NOW + timedelta(seconds=2),
    )
    assert resolved.decision is WorkerTerminalDecision.REJECT
    assert resolved.rejection_reason == "worker release cannot precede terminal observation"
    assert resolved.pool == _pool(values)
    assert resolved.lease_state == _lease(values)
    assert resolved.settlement_ledger == WorkerSettlementLedger()
