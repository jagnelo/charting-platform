"""Bounded Redis worker-pump orchestration for Strategy Lab dispatches.

The pump owns transport mechanics only.  A handler is responsible for loading
authoritative state and performing the isolated execution work; it must return
``COMPLETE`` only after that state is durable.  The pump then acknowledges the
Redis entry.  Retry and rejection results remain pending for recovery or a
separate poison-message policy.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload, DispatchPayloadLoader
from app.strategy_lab_v2.redis_transport import (
    RedisAckResolution,
    RedisDispatchTransport,
    RedisGroupResolution,
    RedisStreamEntry,
)


class WorkerHandleDecision(StrEnum):
    COMPLETE = "complete"
    RETRY = "retry"
    REJECT = "reject"


class WorkerPollDecision(StrEnum):
    READY = "ready"
    REJECT = "reject"


class WorkerEntryDecision(StrEnum):
    ACKNOWLEDGED = "acknowledged"
    RETRY = "retry"
    REJECT = "reject"
    ACKNOWLEDGEMENT_FAILED = "acknowledgement_failed"


@dataclass(frozen=True, slots=True)
class WorkerHandleResult:
    """Handler receipt for one exact stream entry."""

    entry_fingerprint: str
    decision: WorkerHandleDecision
    receipt_digest: str | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.entry_fingerprint, field_name="entry_fingerprint")
        if not isinstance(self.decision, WorkerHandleDecision):
            raise TypeError("decision must be a WorkerHandleDecision")
        if self.receipt_digest is not None:
            require_sha256_digest(self.receipt_digest, field_name="receipt_digest")
        if self.decision is WorkerHandleDecision.COMPLETE and self.receipt_digest is None:
            raise ValueError("completed handler results require a receipt digest")
        if self.decision is not WorkerHandleDecision.COMPLETE and not self.rejection_reason:
            raise ValueError("retry and reject handler results require a reason")
        if self.decision is not WorkerHandleDecision.COMPLETE and self.receipt_digest:
            raise ValueError("retry and reject handler results cannot contain a receipt digest")
        if self.decision is WorkerHandleDecision.COMPLETE and self.rejection_reason:
            raise ValueError("completed handler results cannot contain a rejection reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WorkerPollResolution:
    """Group setup and bounded entries returned by one poll."""

    decision: WorkerPollDecision
    group: RedisGroupResolution
    entries: tuple[RedisStreamEntry, ...] = ()
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WorkerPollDecision):
            raise TypeError("decision must be a WorkerPollDecision")
        if not isinstance(self.group, RedisGroupResolution):
            raise TypeError("group must be a RedisGroupResolution")
        if not isinstance(self.entries, tuple) or any(
            not isinstance(item, RedisStreamEntry) for item in self.entries
        ):
            raise TypeError("entries must contain RedisStreamEntry values")
        if self.decision is WorkerPollDecision.REJECT:
            if self.entries:
                raise ValueError("rejected polls cannot contain entries")
            if not self.rejection_reason:
                raise ValueError("rejected polls require a reason")
        elif self.rejection_reason:
            raise ValueError("ready polls cannot contain a rejection reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WorkerEntryResolution:
    """Handler and acknowledgement evidence for one delivered entry."""

    decision: WorkerEntryDecision
    entry: RedisStreamEntry
    handler: WorkerHandleResult
    acknowledgement: RedisAckResolution | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WorkerEntryDecision):
            raise TypeError("decision must be a WorkerEntryDecision")
        if not isinstance(self.entry, RedisStreamEntry):
            raise TypeError("entry must be a RedisStreamEntry")
        if not isinstance(self.handler, WorkerHandleResult):
            raise TypeError("handler must be a WorkerHandleResult")
        if self.acknowledgement is not None and not isinstance(
            self.acknowledgement, RedisAckResolution
        ):
            raise TypeError("acknowledgement must be a RedisAckResolution")
        if self.decision is WorkerEntryDecision.ACKNOWLEDGED:
            if self.acknowledgement is None or not self.acknowledgement.acknowledged:
                raise ValueError("acknowledged results require a successful acknowledgement")
        if self.decision is WorkerEntryDecision.ACKNOWLEDGEMENT_FAILED:
            if self.acknowledgement is None or self.acknowledgement.acknowledged:
                raise ValueError("failed acknowledgements require unsuccessful evidence")
        if self.decision in {
            WorkerEntryDecision.RETRY,
            WorkerEntryDecision.REJECT,
        } and self.acknowledgement is not None:
            raise ValueError("retry and reject entries cannot contain acknowledgement evidence")
        if self.decision in {
            WorkerEntryDecision.RETRY,
            WorkerEntryDecision.REJECT,
            WorkerEntryDecision.ACKNOWLEDGEMENT_FAILED,
        } and not self.rejection_reason:
            raise ValueError("non-acknowledged entries require a reason")
        if self.decision is WorkerEntryDecision.ACKNOWLEDGED and self.rejection_reason:
            raise ValueError("acknowledged entries cannot contain a rejection reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WorkerCycleResolution:
    """Evidence for one bounded poll-and-handle cycle."""

    poll: WorkerPollResolution
    entries: tuple[WorkerEntryResolution, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.poll, WorkerPollResolution):
            raise TypeError("poll must be a WorkerPollResolution")
        if not isinstance(self.entries, tuple) or any(
            not isinstance(item, WorkerEntryResolution) for item in self.entries
        ):
            raise TypeError("entries must contain WorkerEntryResolution values")
        if self.poll.decision is WorkerPollDecision.REJECT and self.entries:
            raise ValueError("rejected polls cannot have handled entries")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class WorkerEntryHandler(Protocol):
    async def __call__(self, entry: RedisStreamEntry) -> WorkerHandleResult: ...


class MaterializedWorkerEntryHandler(Protocol):
    async def __call__(
        self, entry: RedisStreamEntry, payload: DispatchPayload
    ) -> WorkerHandleResult: ...


class RedisDispatchWorker:
    """One bounded consumer for a queue/group/consumer identity."""

    def __init__(
        self,
        transport: RedisDispatchTransport,
        *,
        queue_name: str,
        group_name: str,
        consumer_name: str,
        reclaim_idle_ms: int = 30_000,
        batch_size: int = 1,
        block_ms: int = 0,
    ) -> None:
        if not isinstance(transport, RedisDispatchTransport):
            raise TypeError("transport must be a RedisDispatchTransport")
        if not isinstance(queue_name, str) or not queue_name.strip():
            raise ValueError("queue_name must not be empty")
        if not isinstance(reclaim_idle_ms, int) or isinstance(reclaim_idle_ms, bool) or reclaim_idle_ms < 0:
            raise ValueError("reclaim_idle_ms must be a non-negative integer")
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        if not isinstance(block_ms, int) or isinstance(block_ms, bool) or block_ms < 0:
            raise ValueError("block_ms must be a non-negative integer")
        self._transport = transport
        self._queue_name = queue_name
        self._group_name = group_name
        self._consumer_name = consumer_name
        self._reclaim_idle_ms = reclaim_idle_ms
        self._batch_size = batch_size
        self._block_ms = block_ms

    async def poll(self) -> WorkerPollResolution:
        """Ensure the group, reclaim pending work, then read new work."""

        group = await self._transport.ensure_group(self._queue_name, self._group_name)
        if group.decision.value == "reject":
            return WorkerPollResolution(
                WorkerPollDecision.REJECT,
                group,
                rejection_reason=group.rejection_reason or "consumer-group setup rejected",
            )
        try:
            reclaimed = await self._transport.reclaim_pending(
                self._queue_name,
                self._group_name,
                self._consumer_name,
                min_idle_ms=self._reclaim_idle_ms,
                count=self._batch_size,
            )
            remaining = self._batch_size - len(reclaimed)
            fresh = (
                await self._transport.read_group(
                    self._queue_name,
                    self._group_name,
                    self._consumer_name,
                    count=remaining,
                    block_ms=self._block_ms,
                )
                if remaining
                else ()
            )
        except Exception as error:  # pragma: no cover - adapter boundary
            return WorkerPollResolution(
                WorkerPollDecision.REJECT,
                group,
                rejection_reason=f"Redis poll failed: {type(error).__name__}",
            )
        return WorkerPollResolution(
            WorkerPollDecision.READY,
            group,
            tuple((*reclaimed, *fresh)),
        )

    async def handle_once(self, handler: WorkerEntryHandler) -> WorkerCycleResolution:
        """Handle at most one bounded batch and ack only completed entries."""

        if not callable(handler):
            raise TypeError("handler must be callable")
        poll = await self.poll()
        if poll.decision is WorkerPollDecision.REJECT:
            return WorkerCycleResolution(poll)
        results: list[WorkerEntryResolution] = []
        for entry in poll.entries:
            result = await handler(entry)
            if not isinstance(result, WorkerHandleResult):
                raise TypeError("handler must return a WorkerHandleResult")
            if result.entry_fingerprint != entry.fingerprint:
                results.append(
                    WorkerEntryResolution(
                        WorkerEntryDecision.REJECT,
                        entry,
                        result,
                        rejection_reason="handler result references different entry content",
                    )
                )
                continue
            if result.decision is not WorkerHandleDecision.COMPLETE:
                results.append(
                    WorkerEntryResolution(
                        WorkerEntryDecision(
                            result.decision.value
                        ),
                        entry,
                        result,
                        rejection_reason=result.rejection_reason,
                    )
                )
                continue
            acknowledgement = await self._transport.acknowledge(
                self._queue_name,
                self._group_name,
                entry.stream_id,
            )
            if not acknowledgement.acknowledged:
                results.append(
                    WorkerEntryResolution(
                        WorkerEntryDecision.ACKNOWLEDGEMENT_FAILED,
                        entry,
                        result,
                        acknowledgement,
                        acknowledgement.rejection_reason
                        or "Redis acknowledgement was not accepted",
                    )
                )
                continue
            results.append(
                WorkerEntryResolution(
                    WorkerEntryDecision.ACKNOWLEDGED,
                    entry,
                    result,
                    acknowledgement,
                )
            )
        return WorkerCycleResolution(poll, tuple(results))

    async def handle_materialized_once(
        self,
        payload_loader: DispatchPayloadLoader,
        handler: MaterializedWorkerEntryHandler,
    ) -> WorkerCycleResolution:
        """Resolve durable payload bytes before invoking a worker handler.

        Payload lookup failures remain unacknowledged so a relay/database
        visibility race can be retried.  A malformed or digest-mismatched
        record is rejected fail-closed and likewise remains pending for an
        explicit poison-message policy.
        """

        if not callable(getattr(payload_loader, "load_payload", None)):
            raise TypeError("payload_loader must expose an async load_payload method")
        if not callable(handler):
            raise TypeError("handler must be callable")

        async def materialized(entry: RedisStreamEntry) -> WorkerHandleResult:
            try:
                payload = await payload_loader.load_payload(entry.payload_digest)
            except Exception as error:  # pragma: no cover - adapter boundary
                return WorkerHandleResult(
                    entry.fingerprint,
                    WorkerHandleDecision.RETRY,
                    rejection_reason=f"dispatch payload lookup failed: {type(error).__name__}",
                )
            if payload is None:
                return WorkerHandleResult(
                    entry.fingerprint,
                    WorkerHandleDecision.RETRY,
                    rejection_reason="dispatch payload is not available",
                )
            if not isinstance(payload, DispatchPayload):
                return WorkerHandleResult(
                    entry.fingerprint,
                    WorkerHandleDecision.REJECT,
                    rejection_reason="dispatch payload loader returned an invalid record",
                )
            if payload.payload_digest != entry.payload_digest:
                return WorkerHandleResult(
                    entry.fingerprint,
                    WorkerHandleDecision.REJECT,
                    rejection_reason="dispatch payload digest does not match the stream entry",
                )
            try:
                payload.value
            except (TypeError, ValueError):
                return WorkerHandleResult(
                    entry.fingerprint,
                    WorkerHandleDecision.REJECT,
                    rejection_reason="dispatch payload failed authentication",
                )
            return await handler(entry, payload)

        return await self.handle_once(materialized)


class RedisDispatchWorkerScheduler:
    """Run bounded worker cycles until an explicit cancellation signal."""

    def __init__(
        self,
        worker: RedisDispatchWorker,
        *,
        interval_seconds: float = 1.0,
        sleep: Callable[[float], Awaitable[None]],
    ) -> None:
        if not isinstance(worker, RedisDispatchWorker):
            raise TypeError("worker must be a RedisDispatchWorker")
        if (
            not isinstance(interval_seconds, int | float)
            or isinstance(interval_seconds, bool)
            or not isfinite(interval_seconds)
            or interval_seconds <= 0
        ):
            raise ValueError("interval_seconds must be a finite positive number")
        if not callable(sleep):
            raise TypeError("sleep must be callable")
        self._worker = worker
        self._interval_seconds = float(interval_seconds)
        self._sleep = sleep

    @property
    def worker(self) -> RedisDispatchWorker:
        return self._worker

    async def run(
        self,
        stop_event: Any,
        handler: WorkerEntryHandler | MaterializedWorkerEntryHandler,
        *,
        payload_loader: DispatchPayloadLoader | None = None,
        max_cycles: int | None = None,
    ) -> tuple[WorkerCycleResolution, ...]:
        """Execute one bounded cycle at a time until stopped or capped."""

        if not callable(getattr(stop_event, "is_set", None)):
            raise TypeError("stop_event must expose is_set()")
        if not callable(handler):
            raise TypeError("handler must be callable")
        if max_cycles is not None and (
            not isinstance(max_cycles, int) or isinstance(max_cycles, bool) or max_cycles < 1
        ):
            raise ValueError("max_cycles must be a positive integer when provided")
        cycles: list[WorkerCycleResolution] = []
        while not stop_event.is_set() and (max_cycles is None or len(cycles) < max_cycles):
            cycle = (
                await self._worker.handle_materialized_once(payload_loader, handler)  # type: ignore[arg-type]
                if payload_loader is not None
                else await self._worker.handle_once(handler)  # type: ignore[arg-type]
            )
            cycles.append(cycle)
            if stop_event.is_set() or (max_cycles is not None and len(cycles) >= max_cycles):
                break
            await self._sleep(self._interval_seconds)
        return tuple(cycles)


HandlerCallable = Callable[[RedisStreamEntry], Awaitable[WorkerHandleResult]]
