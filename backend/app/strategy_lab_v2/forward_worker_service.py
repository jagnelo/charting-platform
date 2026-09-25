"""Bounded Redis service for persistent broker-free forward events.

The service owns transport acknowledgement and authenticated handoff
materialization.  A host-owned handler receives only a validated
``RedisStreamEntry`` plus a validated ``ForwardEventWorkItem`` and must persist the event/engine receipt before
returning ``COMPLETE``.  Provider event acquisition, worker reservation, and
Nautilus process execution stay outside this registration-neutral seam.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from app.strategy_lab_v2.dispatch_payload import DispatchPayload, DispatchPayloadLoader
from app.strategy_lab_v2.forward_worker_handoff import (
    ForwardEventWorkItem,
)
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.worker_consumer import (
    RedisDispatchWorkerScheduler,
    WorkerCycleResolution,
    WorkerHandleDecision,
    WorkerHandleResult,
)

ForwardEventMaterializer = Callable[
    [RedisStreamEntry, DispatchPayload],
    Awaitable[ForwardEventWorkItem] | ForwardEventWorkItem,
]
ForwardEventHandler = Callable[
    [RedisStreamEntry, ForwardEventWorkItem],
    Awaitable[WorkerHandleResult] | WorkerHandleResult,
]


class ForwardEventWorkerService:
    """Bind one bounded Redis scheduler to a forward-event handler."""

    def __init__(
        self,
        scheduler: RedisDispatchWorkerScheduler,
        payload_loader: DispatchPayloadLoader,
        materializer: ForwardEventMaterializer,
        handler: ForwardEventHandler,
    ) -> None:
        if not isinstance(scheduler, RedisDispatchWorkerScheduler):
            raise TypeError("scheduler must be a RedisDispatchWorkerScheduler")
        if not callable(getattr(payload_loader, "load_payload", None)):
            raise TypeError("payload_loader must expose an async load_payload method")
        if not callable(materializer):
            raise TypeError("materializer must be callable")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._scheduler = scheduler
        self._payload_loader = payload_loader
        self._materializer = materializer
        self._handler = handler

    @property
    def scheduler(self) -> RedisDispatchWorkerScheduler:
        return self._scheduler

    @property
    def materializer(self) -> ForwardEventMaterializer:
        return self._materializer

    async def handle(
        self, entry: RedisStreamEntry, payload: DispatchPayload
    ) -> WorkerHandleResult:
        """Process one authenticated forward event and return its ack receipt."""

        try:
            resolved = self._materializer(entry, payload)
            work_item = await resolved if inspect.isawaitable(resolved) else resolved
        except Exception as error:  # pragma: no cover - adapter boundary
            return _retry(entry, f"forward handoff materialization failed: {type(error).__name__}")
        if not isinstance(work_item, ForwardEventWorkItem):
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.REJECT,
                rejection_reason="forward handoff materializer returned an invalid work item",
            )
        try:
            resolved_result = self._handler(entry, work_item)
            result = (
                await resolved_result
                if inspect.isawaitable(resolved_result)
                else resolved_result
            )
        except Exception as error:  # pragma: no cover - host handler boundary
            return _retry(entry, f"forward event handler failed: {type(error).__name__}")
        if not isinstance(result, WorkerHandleResult):
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.REJECT,
                rejection_reason="forward event handler returned an invalid receipt",
            )
        if result.entry_fingerprint != entry.fingerprint:
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.REJECT,
                rejection_reason="forward event receipt references a different entry",
            )
        return result

    async def run(
        self,
        stop_event: object,
        *,
        max_cycles: int | None = None,
    ) -> tuple[WorkerCycleResolution, ...]:
        """Run bounded polling until cancellation or an explicit test cap."""

        return await self._scheduler.run(
            stop_event,
            self.handle,
            payload_loader=self._payload_loader,
            max_cycles=max_cycles,
        )


def _retry(entry: RedisStreamEntry, reason: str) -> WorkerHandleResult:
    return WorkerHandleResult(
        entry.fingerprint,
        WorkerHandleDecision.RETRY,
        rejection_reason=reason,
    )


__all__ = [
    "ForwardEventHandler",
    "ForwardEventMaterializer",
    "ForwardEventWorkerService",
]
