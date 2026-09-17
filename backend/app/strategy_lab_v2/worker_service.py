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

from app.strategy_lab_v2.dispatch_payload import DispatchPayload, DispatchPayloadLoader
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
        self._scheduler = scheduler
        self._payload_loader = payload_loader
        self._materializer = materializer
        self._completion_writer = completion_writer
        self._process_executor = process_executor or SerialWorkerProcessExecutor()

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
        try:
            result = await asyncio.to_thread(self._process_executor.run, request)
        except Exception as error:  # pragma: no cover - process adapter boundary
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.RETRY,
                rejection_reason=f"worker process execution failed: {type(error).__name__}",
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


__all__ = [
    "DedicatedStrategyWorkerService",
    "WorkerCompletionWriter",
    "WorkerHandoffMaterializer",
]
