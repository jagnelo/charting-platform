"""Dedicated serial OS-process boundary for one Strategy Lab execution.

Redis remains a transport concern and FastAPI/the general ARQ worker must not
run Nautilus jobs inline.  This module gives a dedicated worker entrypoint a
small, spawn-based process adapter: one immutable handoff is sent to one fresh
child, the child returns only typed execution evidence, and the parent owns
join/timeout/termination.  It deliberately does not acquire leases, persist
state, or decide whether a result is authoritative.
"""

from __future__ import annotations

import multiprocessing
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from typing import Any

from app.strategy_lab_v2.admission import ExecutionAdmission
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.engine_execution import NautilusExecutionPlan
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.execution_orchestration import ExecutionOrchestrationPlan
from app.strategy_lab_v2.lease_observations import LeaseObservationState
from app.strategy_lab_v2.runtime_execution import (
    RuntimeExecutionState,
    StrategyRuntimePreflight,
    StrategyRuntimeRequest,
)
from app.strategy_lab_v2.sandbox import SandboxCommandPlan
from app.strategy_lab_v2.worker_execution import (
    WorkerExecutionResolution,
    execute_worker_handoff,
)
from app.strategy_lab_v2.workers import WorkerPoolState


@dataclass(frozen=True, slots=True)
class WorkerExecutionRequest:
    """Pickle-safe immutable input for one fresh worker process."""

    orchestration_plan: ExecutionOrchestrationPlan
    authorization: ExecutionAuthorization
    admission: ExecutionAdmission
    runtime_request: StrategyRuntimeRequest
    runtime_preflight: StrategyRuntimePreflight
    runtime_state: RuntimeExecutionState
    sandbox_plan: SandboxCommandPlan
    execution_plan: NautilusExecutionPlan
    worker_pool: WorkerPoolState
    lease_state: LeaseObservationState
    started_at: datetime
    observed_at: datetime
    docker_binary: str = "docker"

    def __post_init__(self) -> None:
        expected = {
            "orchestration_plan": ExecutionOrchestrationPlan,
            "authorization": ExecutionAuthorization,
            "admission": ExecutionAdmission,
            "runtime_request": StrategyRuntimeRequest,
            "runtime_preflight": StrategyRuntimePreflight,
            "runtime_state": RuntimeExecutionState,
            "sandbox_plan": SandboxCommandPlan,
            "execution_plan": NautilusExecutionPlan,
            "worker_pool": WorkerPoolState,
            "lease_state": LeaseObservationState,
        }
        for name, value_type in expected.items():
            if not isinstance(getattr(self, name), value_type):
                raise TypeError(f"{name} must be a {value_type.__name__}")
        for name in ("started_at", "observed_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if not isinstance(self.docker_binary, str) or not self.docker_binary.strip():
            raise ValueError("docker_binary must not be empty")
        if any(character in self.docker_binary for character in "\x00\r\n"):
            raise ValueError("docker_binary must not contain control characters")

    @property
    def request_fingerprint(self) -> str:
        return content_digest(self)


class WorkerProcessDecision(StrEnum):
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    START_FAILED = "start_failed"
    CHILD_FAILED = "child_failed"


@dataclass(frozen=True, slots=True)
class WorkerProcessResolution:
    """Parent-observed lifecycle and typed child evidence."""

    request_fingerprint: str
    decision: WorkerProcessDecision
    execution: WorkerExecutionResolution | None = None
    process_id: int | None = None
    error_digest: str | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        if not isinstance(self.decision, WorkerProcessDecision):
            raise TypeError("decision must be a WorkerProcessDecision")
        if self.process_id is not None and (
            not isinstance(self.process_id, int)
            or isinstance(self.process_id, bool)
            or self.process_id < 0
        ):
            raise ValueError("process_id must be a non-negative integer or None")
        if self.error_digest is not None:
            require_sha256_digest(self.error_digest, field_name="error_digest")
        if self.decision is WorkerProcessDecision.COMPLETED:
            if self.execution is None or self.error_digest is not None:
                raise ValueError("completed worker processes require execution evidence only")
        elif self.execution is not None or self.error_digest is None:
            raise ValueError("failed worker processes require an error digest only")
        if self.execution is not None and not isinstance(
            self.execution, WorkerExecutionResolution
        ):
            raise TypeError("execution must be a WorkerExecutionResolution")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


ProcessFactory = Callable[..., Any]
PipeFactory = Callable[[bool], tuple[Any, Any]]


class SerialWorkerProcessExecutor:
    """Run one handoff in one fresh ``spawn`` child at a time."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 300.0,
        process_factory: ProcessFactory | None = None,
        pipe_factory: PipeFactory | None = None,
    ) -> None:
        if (
            not isinstance(timeout_seconds, int | float)
            or isinstance(timeout_seconds, bool)
            or not isfinite(float(timeout_seconds))
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a finite positive number")
        context = multiprocessing.get_context("spawn")
        self._process_factory = process_factory or context.Process
        self._pipe_factory = pipe_factory or context.Pipe
        if not callable(self._process_factory):
            raise TypeError("process_factory must be callable")
        if not callable(self._pipe_factory):
            raise TypeError("pipe_factory must be callable")
        self._timeout_seconds = float(timeout_seconds)
        self._run_lock = threading.Lock()

    def run(
        self,
        request: WorkerExecutionRequest,
        *,
        timeout_seconds: float | None = None,
    ) -> WorkerProcessResolution:
        """Execute a single handoff and always reap/terminate its child."""

        if not isinstance(request, WorkerExecutionRequest):
            raise TypeError("request must be a WorkerExecutionRequest")
        timeout = self._timeout_seconds if timeout_seconds is None else timeout_seconds
        if (
            not isinstance(timeout, int | float)
            or isinstance(timeout, bool)
            or not isfinite(float(timeout))
            or timeout <= 0
        ):
            raise ValueError("timeout_seconds must be a finite positive number")
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("serial worker process executor is already running")
        receiver = sender = process = None
        try:
            receiver, sender = self._pipe_factory(False)
            process = self._process_factory(target=_child_main, args=(request, sender))
            try:
                process.start()
            except BaseException as error:
                return WorkerProcessResolution(
                    request.request_fingerprint,
                    WorkerProcessDecision.START_FAILED,
                    process_id=None,
                    error_digest=_error_digest(error),
                )
            sender.close()
            sender = None
            process.join(float(timeout))
            process_id = getattr(process, "pid", None)
            if process.is_alive():
                process.terminate()
                process.join(1.0)
                return WorkerProcessResolution(
                    request.request_fingerprint,
                    WorkerProcessDecision.TIMED_OUT,
                    process_id=process_id,
                    error_digest=content_digest("strategy lab worker process timed out"),
                )
            if not receiver.poll():
                return WorkerProcessResolution(
                    request.request_fingerprint,
                    WorkerProcessDecision.CHILD_FAILED,
                    process_id=process_id,
                    error_digest=content_digest("strategy lab worker exited without evidence"),
                )
            message = receiver.recv()
            if not isinstance(message, tuple) or len(message) != 2:
                return WorkerProcessResolution(
                    request.request_fingerprint,
                    WorkerProcessDecision.CHILD_FAILED,
                    process_id=process_id,
                    error_digest=content_digest("strategy lab worker returned malformed evidence"),
                )
            tag, value = message
            if tag == "completed" and isinstance(value, WorkerExecutionResolution):
                return WorkerProcessResolution(
                    request.request_fingerprint,
                    WorkerProcessDecision.COMPLETED,
                    execution=value,
                    process_id=process_id,
                )
            if tag == "failed" and isinstance(value, str):
                require_sha256_digest(value, field_name="child error digest")
                return WorkerProcessResolution(
                    request.request_fingerprint,
                    WorkerProcessDecision.CHILD_FAILED,
                    process_id=process_id,
                    error_digest=value,
                )
            return WorkerProcessResolution(
                request.request_fingerprint,
                WorkerProcessDecision.CHILD_FAILED,
                process_id=process_id,
                error_digest=content_digest("strategy lab worker returned invalid evidence"),
            )
        finally:
            if sender is not None:
                sender.close()
            if receiver is not None:
                receiver.close()
            self._run_lock.release()


def _child_main(request: WorkerExecutionRequest, sender: Any) -> None:
    try:
        result = execute_worker_handoff(
            request.orchestration_plan,
            request.authorization,
            request.admission,
            request.runtime_request,
            request.runtime_preflight,
            request.runtime_state,
            request.sandbox_plan,
            request.execution_plan,
            worker_pool=request.worker_pool,
            lease_state=request.lease_state,
            started_at=request.started_at,
            observed_at=request.observed_at,
            docker_binary=request.docker_binary,
        )
        sender.send(("completed", result))
    except BaseException as error:  # pragma: no cover - child process boundary
        sender.send(("failed", _error_digest(error)))
    finally:
        sender.close()


def _error_digest(error: BaseException) -> str:
    return content_digest(
        {
            "type": f"{type(error).__module__}.{type(error).__qualname__}",
            "version": "strategy-lab.worker-process.error.v1",
        }
    )


__all__ = [
    "SerialWorkerProcessExecutor",
    "WorkerExecutionRequest",
    "WorkerProcessDecision",
    "WorkerProcessResolution",
]
