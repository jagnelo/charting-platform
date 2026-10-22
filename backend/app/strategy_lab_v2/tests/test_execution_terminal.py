from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.api_contracts import ApiError, ApiErrorCode
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.execution_terminal import (
    ExecutionTerminalDecision,
    materialize_execution_terminal,
)
from app.strategy_lab_v2.progress import ProgressPhase
from app.strategy_lab_v2.runtime_execution import RuntimeExecutionPhase, RuntimeExecutionState
from app.strategy_lab_v2.tests.test_execution_summary import _outcome, _progress, _receipt
from app.strategy_lab_v2.tests.test_result_publication import _result as result_fixture

NOW = datetime(2024, 1, 1, tzinfo=UTC)
ATTEMPT = "attempt-1"


def _runtime(phase: RuntimeExecutionPhase) -> RuntimeExecutionState:
    return RuntimeExecutionState(
        content_digest("runtime-request"),
        ATTEMPT,
        content_digest("profile"),
        1024,
        1,
        phase,
        NOW + timedelta(seconds=1),
        content_digest("stdout") if phase is RuntimeExecutionPhase.SUCCEEDED else None,
        6 if phase is RuntimeExecutionPhase.SUCCEEDED else None,
        content_digest("runtime-error") if phase is RuntimeExecutionPhase.FAILED else None,
    )


def test_success_projects_manifest_digest_and_progress_atomically() -> None:
    receipt = _receipt()
    outcome = _outcome()
    progress = _progress()
    result, *_ = result_fixture()
    resolved = materialize_execution_terminal(
        receipt,
        _runtime(RuntimeExecutionPhase.SUCCEEDED),
        outcome,
        progress,
        result=result,
        observed_at=NOW + timedelta(seconds=2),
    )
    assert resolved.decision is ExecutionTerminalDecision.SUCCEEDED
    assert resolved.outcome.status.value == "succeeded"
    assert resolved.outcome.result_digest == result.fingerprint
    assert resolved.progress.phase is ProgressPhase.SUCCEEDED
    assert resolved.progress.completed_units == resolved.progress.total_units

    replay = materialize_execution_terminal(
        receipt,
        _runtime(RuntimeExecutionPhase.SUCCEEDED),
        resolved.outcome,
        resolved.progress,
        result=result,
        observed_at=NOW + timedelta(seconds=3),
    )
    assert replay.decision is ExecutionTerminalDecision.REPLAY_EXISTING
    assert replay.outcome == resolved.outcome
    assert replay.progress == resolved.progress


def test_failure_and_cancellation_project_typed_terminal_states() -> None:
    receipt = _receipt()
    failure = materialize_execution_terminal(
        receipt,
        _runtime(RuntimeExecutionPhase.FAILED),
        _outcome(),
        _progress(),
        error=ApiError(ApiErrorCode.INTERNAL_ERROR, "worker failed", "request-1", 500, True),
        observed_at=NOW + timedelta(seconds=2),
    )
    assert failure.decision is ExecutionTerminalDecision.FAILED
    assert failure.outcome.status.value == "failed"
    assert failure.outcome.error is not None
    assert failure.progress.phase is ProgressPhase.FAILED

    cancelled_progress = replace(_progress(), cancellation_requested=True)
    cancelled = materialize_execution_terminal(
        receipt,
        _runtime(RuntimeExecutionPhase.CANCELLED),
        _outcome(),
        cancelled_progress,
        observed_at=NOW + timedelta(seconds=2),
    )
    assert cancelled.decision is ExecutionTerminalDecision.CANCELLED
    assert cancelled.outcome.status.value == "cancelled"
    assert cancelled.progress.phase is ProgressPhase.CANCELLED


def test_terminal_projection_rejects_missing_result_drift_and_half_terminal_state() -> None:
    receipt = _receipt()
    rejected = materialize_execution_terminal(
        receipt,
        _runtime(RuntimeExecutionPhase.SUCCEEDED),
        _outcome(),
        _progress(),
        observed_at=NOW + timedelta(seconds=2),
    )
    assert rejected.decision is ExecutionTerminalDecision.REJECT
    assert rejected.rejection_reason == "successful runtime requires a result and no error"

    result, *_ = result_fixture()
    terminal_outcome = _outcome()
    terminal_progress = _progress()
    applied = materialize_execution_terminal(
        receipt,
        _runtime(RuntimeExecutionPhase.SUCCEEDED),
        terminal_outcome,
        terminal_progress,
        result=result,
        observed_at=NOW + timedelta(seconds=2),
    )
    conflict = materialize_execution_terminal(
        receipt,
        _runtime(RuntimeExecutionPhase.FAILED),
        applied.outcome,
        applied.progress,
        error=ApiError(ApiErrorCode.INTERNAL_ERROR, "different", "request-1", 500),
        observed_at=NOW + timedelta(seconds=3),
    )
    assert conflict.decision is ExecutionTerminalDecision.REJECT
    assert "terminal outcome and progress conflict" in (conflict.rejection_reason or "")


def test_terminal_projection_validates_types_and_time() -> None:
    receipt = _receipt()
    with pytest.raises(TypeError, match="receipt"):
        materialize_execution_terminal(
            "bad",  # type: ignore[arg-type]
            _runtime(RuntimeExecutionPhase.FAILED),
            _outcome(),
            _progress(),
            error=ApiError(ApiErrorCode.INTERNAL_ERROR, "failed", "request-1", 500),
            observed_at=NOW,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        materialize_execution_terminal(
            receipt,
            _runtime(RuntimeExecutionPhase.FAILED),
            _outcome(),
            _progress(),
            error=ApiError(ApiErrorCode.INTERNAL_ERROR, "failed", "request-1", 500),
            observed_at=datetime(2024, 1, 1),
        )
