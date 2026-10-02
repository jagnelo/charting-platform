from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.nautilus_runtime_bundle import (
    NAUTILUS_RUNTIME_ARTIFACT_MEDIA_TYPE,
    NAUTILUS_RUNTIME_ARTIFACT_SCHEMA,
    NautilusRuntimeInputArtifactReference,
)
from app.strategy_lab_v2.tests.test_execution_orchestration import _fixtures
from app.strategy_lab_v2.tests.test_worker_execution import _lease, _plan, _pool
from app.strategy_lab_v2.worker_process import (
    SerialWorkerProcessExecutor,
    WorkerExecutionRequest,
    WorkerProcessDecision,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _request(tmp_path: Path, *, body: str = "printf 'ok'") -> WorkerExecutionRequest:
    mutable_values = list(_fixtures())
    input_path = tmp_path / "runtime-input.json"
    input_bytes = b"worker-process-fixture"
    input_path.write_bytes(input_bytes)
    input_digest = artifact_content_digest(input_bytes)
    artifact = ArtifactManifest(
        content_digest=input_digest,
        byte_length=len(input_bytes),
        media_type=NAUTILUS_RUNTIME_ARTIFACT_MEDIA_TYPE,
        schema_version=NAUTILUS_RUNTIME_ARTIFACT_SCHEMA,
        storage_key=input_digest,
        retention_class=ArtifactRetention.PINNED_INPUT,
    )
    input_artifact = NautilusRuntimeInputArtifactReference(
        mutable_values[2].attempt_id,
        mutable_values[2].input_bundle_digest,
        artifact,
    )
    sandbox_argv = list(mutable_values[5].argv)
    sandbox_argv[15] = f"--mount=type=bind,src={input_path},dst=/inputs/bundle,readonly"
    mutable_values[5] = replace(mutable_values[5], argv=tuple(sandbox_argv))
    mutable_values[6] = replace(
        mutable_values[6], sandbox_plan_fingerprint=mutable_values[5].fingerprint
    )
    values = tuple(mutable_values)
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
        runtime_input_artifact=input_artifact,
        docker_binary=_fake_binary(tmp_path, body),
    )


def _fake_binary(tmp_path: Path, body: str) -> str:
    path = tmp_path / "fake-docker"
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return os.fspath(path)


class _PipeEnd:
    def close(self) -> None:
        return None


class _StubbornProcess:
    pid = 42

    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self._alive = True

    def start(self) -> None:
        return None

    def is_alive(self) -> bool:
        return self._alive

    def join(self, _timeout: float | None = None) -> None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self._alive = False


def test_worker_process_runs_one_handoff_in_a_spawned_child(tmp_path: Path) -> None:
    request = _request(tmp_path)
    result = SerialWorkerProcessExecutor(timeout_seconds=10).run(request)

    assert result.decision is WorkerProcessDecision.COMPLETED
    assert result.process_id is not None
    assert result.execution is not None
    assert result.execution.decision.value == "succeeded"
    assert result.fingerprint.startswith("sha256:")


def test_worker_request_rejects_an_artifact_for_different_input_bytes(tmp_path: Path) -> None:
    request = _request(tmp_path)
    drifted_artifact = replace(
        request.runtime_input_artifact,
        input_bundle_digest=content_digest("different inputs"),
    )

    with pytest.raises(ValueError, match="must match the runtime request digest"):
        replace(request, runtime_input_artifact=drifted_artifact)


@pytest.mark.asyncio
async def test_worker_process_async_runs_spawned_child_without_thread_bootstrap(
    tmp_path: Path,
) -> None:
    result = await SerialWorkerProcessExecutor(timeout_seconds=10).run_async(_request(tmp_path))

    assert result.decision is WorkerProcessDecision.COMPLETED
    assert result.process_id is not None
    assert result.execution is not None
    assert result.execution.decision.value == "succeeded"


def test_worker_process_preserves_typed_child_failure(tmp_path: Path) -> None:
    result = SerialWorkerProcessExecutor(timeout_seconds=10).run(_request(tmp_path, body="exit 7"))

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


@pytest.mark.asyncio
async def test_worker_process_async_reaps_a_timed_out_child(tmp_path: Path) -> None:
    result = await SerialWorkerProcessExecutor(timeout_seconds=0.2).run_async(
        _request(tmp_path, body="sleep 5")
    )

    assert result.decision is WorkerProcessDecision.TIMED_OUT
    assert result.execution is None
    assert result.error_digest == content_digest("strategy lab worker process timed out")


@pytest.mark.asyncio
async def test_worker_process_async_timeout_cleanup_yields_to_event_loop(
    tmp_path: Path,
) -> None:
    process = _StubbornProcess()

    def process_factory(**_kwargs: object) -> _StubbornProcess:
        return process

    def pipe_factory(_duplex: bool) -> tuple[_PipeEnd, _PipeEnd]:
        return _PipeEnd(), _PipeEnd()

    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.001)

    ticker_task = asyncio.create_task(ticker())
    try:
        result = await SerialWorkerProcessExecutor(
            timeout_seconds=0.001,
            process_factory=process_factory,
            pipe_factory=pipe_factory,
        ).run_async(_request(tmp_path), poll_interval_seconds=0.001)
    finally:
        ticker_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await ticker_task

    assert result.decision is WorkerProcessDecision.TIMED_OUT
    assert process.terminated
    assert process.killed
    assert ticks > 10


@pytest.mark.asyncio
async def test_worker_process_async_cancellation_reaps_child(tmp_path: Path) -> None:
    process = _StubbornProcess()

    def process_factory(**_kwargs: object) -> _StubbornProcess:
        return process

    def pipe_factory(_duplex: bool) -> tuple[_PipeEnd, _PipeEnd]:
        return _PipeEnd(), _PipeEnd()

    task = asyncio.create_task(
        SerialWorkerProcessExecutor(
            timeout_seconds=10,
            process_factory=process_factory,
            pipe_factory=pipe_factory,
        ).run_async(_request(tmp_path), poll_interval_seconds=0.001)
    )
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.terminated
    assert process.killed


def test_worker_process_rejects_concurrent_use_and_invalid_inputs(tmp_path: Path) -> None:
    request = _request(tmp_path)
    with pytest.raises(ValueError, match="timeout_seconds"):
        SerialWorkerProcessExecutor(timeout_seconds=0)
    with pytest.raises(TypeError, match="WorkerExecutionRequest"):
        SerialWorkerProcessExecutor().run("bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(request, started_at=datetime(2024, 1, 1))
