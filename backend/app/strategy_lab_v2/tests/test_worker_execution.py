from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.execution_orchestration import plan_execution_orchestration
from app.strategy_lab_v2.nautilus_runner import NautilusRunStatus
from app.strategy_lab_v2.tests.test_execution_orchestration import _fixtures
from app.strategy_lab_v2.worker_execution import (
    WorkerExecutionDecision,
    execute_worker_handoff,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _fake_binary(tmp_path: Path, body: str) -> str:
    path = tmp_path / "fake-docker"
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return os.fspath(path)


def _plan(values: tuple):
    return plan_execution_orchestration(*values)


def test_worker_handoff_revalidates_then_runs_gated_nautilus(tmp_path: Path) -> None:
    values = _fixtures()
    orchestration = _plan(values)
    result = execute_worker_handoff(
        orchestration,
        *values,
        observed_at=NOW,
        docker_binary=_fake_binary(tmp_path, "printf 'ok'"),
    )
    assert result.decision is WorkerExecutionDecision.SUCCEEDED
    assert result.nautilus_result is not None
    assert result.nautilus_result.status is NautilusRunStatus.SUCCEEDED
    assert result.runtime_result is not None
    assert result.runtime_result.state.sequence == 2


def test_worker_handoff_returns_typed_failure_evidence(tmp_path: Path) -> None:
    values = _fixtures()
    result = execute_worker_handoff(
        _plan(values),
        *values,
        observed_at=NOW,
        docker_binary=_fake_binary(tmp_path, "exit 7"),
    )
    assert result.decision is WorkerExecutionDecision.FAILED
    assert result.nautilus_result is not None
    assert result.runtime_result is not None
    assert result.runtime_result.state.error_digest is not None


def test_worker_handoff_rejects_stale_or_mismatched_plan_before_spawn(tmp_path: Path) -> None:
    values = _fixtures()
    orchestration = _plan(values)
    stale = replace(orchestration, execution_plan_fingerprint=content_digest("stale-plan"))
    rejected = execute_worker_handoff(
        stale,
        *values,
        observed_at=NOW,
        docker_binary=os.fspath(tmp_path / "missing"),
    )
    assert rejected.decision is WorkerExecutionDecision.REJECTED
    assert rejected.nautilus_result is None
    assert rejected.runtime_result is None
    assert rejected.rejection_reason == "orchestration plan fingerprint drift"


def test_worker_handoff_requires_explicit_observation_time() -> None:
    values = _fixtures()
    with pytest.raises(ValueError, match="timezone-aware"):
        execute_worker_handoff(_plan(values), *values, observed_at=datetime(2024, 1, 1))
