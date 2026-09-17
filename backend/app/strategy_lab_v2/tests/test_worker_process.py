from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.tests.test_execution_orchestration import _fixtures
from app.strategy_lab_v2.tests.test_worker_execution import _lease, _plan, _pool
from app.strategy_lab_v2.worker_process import (
    SerialWorkerProcessExecutor,
    WorkerExecutionRequest,
    WorkerProcessDecision,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _request(tmp_path: Path, *, body: str = "printf 'ok'") -> WorkerExecutionRequest:
    values = _fixtures()
    return WorkerExecutionRequest(
        _plan(values),
        values[0],
        values[1],
        values[2],
        values[3],
        values[4],
        values[5],
        values[6],
        _pool(values),
        _lease(values),
        NOW,
        NOW,
        _fake_binary(tmp_path, body),
    )


def _fake_binary(tmp_path: Path, body: str) -> str:
    path = tmp_path / "fake-docker"
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return os.fspath(path)


def test_worker_process_runs_one_handoff_in_a_spawned_child(tmp_path: Path) -> None:
    request = _request(tmp_path)
    result = SerialWorkerProcessExecutor(timeout_seconds=10).run(request)

    assert result.decision is WorkerProcessDecision.COMPLETED
    assert result.process_id is not None
    assert result.execution is not None
    assert result.execution.decision.value == "succeeded"
    assert result.fingerprint.startswith("sha256:")


def test_worker_process_preserves_typed_child_failure(tmp_path: Path) -> None:
    result = SerialWorkerProcessExecutor(timeout_seconds=10).run(
        _request(tmp_path, body="exit 7")
    )

    assert result.decision is WorkerProcessDecision.COMPLETED
    assert result.execution is not None
    assert result.execution.decision.value == "failed"
    assert result.error_digest is None


def test_worker_process_reaps_a_timed_out_child(tmp_path: Path) -> None:
    result = SerialWorkerProcessExecutor(timeout_seconds=0.2).run(
        _request(tmp_path, body="sleep 5")
    )

    assert result.decision is WorkerProcessDecision.TIMED_OUT
    assert result.execution is None
    assert result.error_digest == content_digest("strategy lab worker process timed out")


def test_worker_process_rejects_concurrent_use_and_invalid_inputs(tmp_path: Path) -> None:
    request = _request(tmp_path)
    with pytest.raises(ValueError, match="timeout_seconds"):
        SerialWorkerProcessExecutor(timeout_seconds=0)
    with pytest.raises(TypeError, match="WorkerExecutionRequest"):
        SerialWorkerProcessExecutor().run("bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(request, started_at=datetime(2024, 1, 1))

