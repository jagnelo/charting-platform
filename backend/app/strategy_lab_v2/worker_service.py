"""Application-owned dedicated worker service composition.

This module is the seam a future Compose worker entrypoint can call.  It keeps
Redis polling and acknowledgement in :mod:`worker_consumer`, materializes a
durable payload into a typed handoff, and delegates the actual Nautilus work to
the fresh-process executor.  Completion persistence is injected so a Redis
acknowledgement is impossible until authoritative state has been committed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload, DispatchPayloadLoader
from app.strategy_lab_v2.lease_observations import (
    LeaseObservation,
    LeaseObservationDecision,
    LeaseObservationKind,
    LeaseObservationResolution,
    LeaseObservationState,
)
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.worker_consumer import (
    RedisDispatchWorkerScheduler,
    WorkerCycleResolution,
    WorkerHandleDecision,
    WorkerHandleResult,
)
from app.strategy_lab_v2.worker_process import (
    SerialWorkerProcessExecutor,
    WorkerExecutionRequest,
    WorkerProcessResolution,
)

WorkerHandoffMaterializer = Callable[
    [RedisStreamEntry, DispatchPayload], Awaitable[WorkerExecutionRequest]
]
WorkerCompletionWriter = Callable[
    [RedisStreamEntry, WorkerProcessResolution], Awaitable[WorkerHandleResult]
]
WorkerLeaseHeartbeatWriter = Callable[[LeaseObservation], Awaitable[LeaseObservationResolution]]


@dataclass(frozen=True, slots=True)
class WorkerServiceCallbacks:
    """Application callbacks used by one dedicated worker service."""

    materializer: WorkerHandoffMaterializer
    completion_writer: WorkerCompletionWriter
    heartbeat_writer: WorkerLeaseHeartbeatWriter | None = None

    def __post_init__(self) -> None:
        if not callable(self.materializer):
            raise TypeError("materializer must be callable")
        if not callable(self.completion_writer):
            raise TypeError("completion_writer must be callable")
        if self.heartbeat_writer is not None and not callable(self.heartbeat_writer):
            raise TypeError("heartbeat_writer must be callable")


class DedicatedStrategyWorkerService:
    """Bind one Redis scheduler to one serial process executor."""

    def __init__(
        self,
        scheduler: RedisDispatchWorkerScheduler,
        payload_loader: DispatchPayloadLoader,
        materializer: WorkerHandoffMaterializer,
        completion_writer: WorkerCompletionWriter,
        *,
        process_executor: SerialWorkerProcessExecutor | None = None,
        heartbeat_writer: WorkerLeaseHeartbeatWriter | None = None,
        heartbeat_interval_seconds: float = 5.0,
        heartbeat_extension_seconds: float = 30.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        heartbeat_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not isinstance(scheduler, RedisDispatchWorkerScheduler):
            raise TypeError("scheduler must be a RedisDispatchWorkerScheduler")
        if not callable(getattr(payload_loader, "load_payload", None)):
            raise TypeError("payload_loader must expose an async load_payload method")
        if not callable(materializer):
            raise TypeError("materializer must be callable")
        if not callable(completion_writer):
            raise TypeError("completion_writer must be callable")
        if process_executor is not None and not isinstance(
            process_executor, SerialWorkerProcessExecutor
        ):
            raise TypeError("process_executor must be a SerialWorkerProcessExecutor")
        if heartbeat_writer is not None and not callable(heartbeat_writer):
            raise TypeError("heartbeat_writer must be callable")
        for name, value in (
            ("heartbeat_interval_seconds", heartbeat_interval_seconds),
            ("heartbeat_extension_seconds", heartbeat_extension_seconds),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not isfinite(float(value))
                or value <= 0
            ):
                raise ValueError(f"{name} must be a finite positive number")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if not callable(heartbeat_sleep):
            raise TypeError("heartbeat_sleep must be callable")
        self._scheduler = scheduler
        self._payload_loader = payload_loader
        self._materializer = materializer
        self._completion_writer = completion_writer
        self._process_executor = process_executor or SerialWorkerProcessExecutor()
        self._heartbeat_writer = heartbeat_writer
        self._heartbeat_interval_seconds = float(heartbeat_interval_seconds)
        self._heartbeat_extension_seconds = float(heartbeat_extension_seconds)
        self._clock = clock
        self._heartbeat_sleep = heartbeat_sleep

    @property
    def scheduler(self) -> RedisDispatchWorkerScheduler:
        return self._scheduler

    @property
    def process_executor(self) -> SerialWorkerProcessExecutor:
        return self._process_executor

    async def handle(
        self, entry: RedisStreamEntry, payload: DispatchPayload
    ) -> WorkerHandleResult:
        """Materialize and execute one entry, then ask persistence for a receipt."""

        try:
            request = await self._materializer(entry, payload)
        except Exception as error:  # pragma: no cover - adapter boundary
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.RETRY,
                rejection_reason=f"worker handoff materialization failed: {type(error).__name__}",
            )
        if not isinstance(request, WorkerExecutionRequest):
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.REJECT,
                rejection_reason="worker handoff materializer returned an invalid request",
            )
        heartbeat_task: asyncio.Task[None] | None = None
        heartbeat_failure: list[str] = []
        if self._heartbeat_writer is not None:
            heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(request.lease_state, heartbeat_failure)
            )
        try:
            try:
                result = await asyncio.to_thread(self._process_executor.run, request)
            except Exception as error:  # pragma: no cover - process adapter boundary
                return WorkerHandleResult(
                    entry.fingerprint,
                    WorkerHandleDecision.RETRY,
                    rejection_reason=f"worker process execution failed: {type(error).__name__}",
                )
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
        if heartbeat_failure:
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.RETRY,
                rejection_reason=heartbeat_failure[0],
            )
        receipt = await self._completion_writer(entry, result)
        if not isinstance(receipt, WorkerHandleResult):
            raise TypeError("completion_writer must return a WorkerHandleResult")
        if receipt.entry_fingerprint != entry.fingerprint:
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.REJECT,
                rejection_reason="completion receipt references a different entry",
            )
        return receipt

    async def run(
        self,
        stop_event: object,
        *,
        max_cycles: int | None = None,
    ) -> tuple[WorkerCycleResolution, ...]:
        """Run the bounded Redis scheduler until cancellation or a test cap."""

        return await self._scheduler.run(
            stop_event,
            self.handle,
            payload_loader=self._payload_loader,
            max_cycles=max_cycles,
        )

    async def _heartbeat_loop(
        self,
        initial_state: LeaseObservationState,
        failures: list[str],
    ) -> None:
        """Emit ordered lease heartbeats until the process handoff ends."""

        assert self._heartbeat_writer is not None
        state = initial_state
        while True:
            await self._heartbeat_sleep(self._heartbeat_interval_seconds)
            observed_at = self._clock()
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                failures.append("worker lease heartbeat clock was not timezone-aware")
                return
            expires_at = observed_at + timedelta(seconds=self._heartbeat_extension_seconds)
            sequence = state.last_sequence + 1
            observation = LeaseObservation(
                observation_id=content_digest(
                    {
                        "lease_id": state.lease.lease_id,
                        "worker_id": state.lease.worker_id,
                        "attempt_id": state.lease.attempt_id,
                        "sequence": sequence,
                        "kind": LeaseObservationKind.HEARTBEAT.value,
                        "observed_at": observed_at,
                        "expires_at": expires_at,
                    }
                ),
                lease_id=state.lease.lease_id,
                worker_id=state.lease.worker_id,
                attempt_id=state.lease.attempt_id,
                sequence=sequence,
                kind=LeaseObservationKind.HEARTBEAT,
                observed_at=observed_at,
                expires_at=expires_at,
            )
            try:
                resolution = await self._heartbeat_writer(observation)
            except Exception as error:  # pragma: no cover - persistence boundary
                failures.append(f"worker lease heartbeat failed: {type(error).__name__}")
                return
            if not isinstance(resolution, LeaseObservationResolution):
                failures.append("worker lease heartbeat returned an invalid resolution")
                return
            if resolution.expected_sequence != sequence:
                failures.append("worker lease heartbeat returned an unexpected sequence")
                return
            if resolution.decision not in {
                LeaseObservationDecision.APPLY,
                LeaseObservationDecision.REPLAY_EXISTING,
            }:
                failures.append(
                    "worker lease heartbeat rejected: "
                    + resolution.decision.value
                )
                return
            if resolution.state.last_sequence < sequence:
                failures.append("worker lease heartbeat returned stale lease state")
                return
            state = resolution.state


__all__ = [
    "DedicatedStrategyWorkerService",
    "WorkerCompletionWriter",
    "WorkerHandoffMaterializer",
    "WorkerLeaseHeartbeatWriter",
    "WorkerServiceCallbacks",
]
