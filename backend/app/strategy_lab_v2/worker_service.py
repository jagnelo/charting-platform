"""Application-owned dedicated worker service composition.

This module is the seam a future Compose worker entrypoint can call.  It keeps
Redis polling and acknowledgement in :mod:`worker_consumer`, materializes a
durable payload into a typed handoff, and delegates the actual Nautilus work to
the fresh-process executor. The async executor starts the spawn child on this
worker's event-loop thread and polls cooperatively so lease heartbeats remain
schedulable. Completion persistence is injected so a Redis acknowledgement is
impossible until authoritative state has been committed.
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
from app.strategy_lab_v2.lifecycle import AttemptLeaseStatus
from app.strategy_lab_v2.recovery import RecoveryReason
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
WorkerTerminalWriter = Callable[["WorkerCompletionContext"], Awaitable[WorkerHandleResult]]
WorkerRecoveryWriter = Callable[["WorkerRecoveryContext"], Awaitable[WorkerHandleResult]]
WorkerLeaseStateReader = Callable[[WorkerExecutionRequest], Awaitable[LeaseObservationState | None]]
WorkerCancellationReader = Callable[[RedisStreamEntry, WorkerExecutionRequest], Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class WorkerCompletionContext:
    """Immutable context handed to an authoritative terminal/result adapter."""

    entry: RedisStreamEntry
    request: WorkerExecutionRequest
    process: WorkerProcessResolution
    observed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.entry, RedisStreamEntry):
            raise TypeError("entry must be a RedisStreamEntry")
        if not isinstance(self.request, WorkerExecutionRequest):
            raise TypeError("request must be a WorkerExecutionRequest")
        if not isinstance(self.process, WorkerProcessResolution):
            raise TypeError("process must be a WorkerProcessResolution")
        if self.process.request_fingerprint != self.request.request_fingerprint:
            raise ValueError("process resolution references a different request")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WorkerRecoveryContext:
    """Authenticated execution coordinates for one infrastructure recovery."""

    entry: RedisStreamEntry
    request: WorkerExecutionRequest
    reason: RecoveryReason
    observed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.entry, RedisStreamEntry):
            raise TypeError("entry must be a RedisStreamEntry")
        if not isinstance(self.request, WorkerExecutionRequest):
            raise TypeError("request must be a WorkerExecutionRequest")
        if not isinstance(self.reason, RecoveryReason):
            raise TypeError("reason must be a RecoveryReason")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WorkerServiceCallbacks:
    """Application callbacks used by one dedicated worker service."""

    materializer: WorkerHandoffMaterializer
    completion_writer: WorkerCompletionWriter
    heartbeat_writer: WorkerLeaseHeartbeatWriter | None = None
    terminal_writer: WorkerTerminalWriter | None = None
    recovery_writer: WorkerRecoveryWriter | None = None
    lease_state_reader: WorkerLeaseStateReader | None = None
    cancellation_reader: WorkerCancellationReader | None = None

    def __post_init__(self) -> None:
        if not callable(self.materializer):
            raise TypeError("materializer must be callable")
        if not callable(self.completion_writer):
            raise TypeError("completion_writer must be callable")
        if self.heartbeat_writer is not None and not callable(self.heartbeat_writer):
            raise TypeError("heartbeat_writer must be callable")
        if self.terminal_writer is not None and not callable(self.terminal_writer):
            raise TypeError("terminal_writer must be callable")
        if self.recovery_writer is not None and not callable(self.recovery_writer):
            raise TypeError("recovery_writer must be callable")
        if self.lease_state_reader is not None and not callable(self.lease_state_reader):
            raise TypeError("lease_state_reader must be callable")
        if self.cancellation_reader is not None and not callable(self.cancellation_reader):
            raise TypeError("cancellation_reader must be callable")


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
        terminal_writer: WorkerTerminalWriter | None = None,
        recovery_writer: WorkerRecoveryWriter | None = None,
        lease_state_reader: WorkerLeaseStateReader | None = None,
        cancellation_reader: WorkerCancellationReader | None = None,
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
        if terminal_writer is not None and not callable(terminal_writer):
            raise TypeError("terminal_writer must be callable")
        if recovery_writer is not None and not callable(recovery_writer):
            raise TypeError("recovery_writer must be callable")
        if lease_state_reader is not None and not callable(lease_state_reader):
            raise TypeError("lease_state_reader must be callable")
        if cancellation_reader is not None and not callable(cancellation_reader):
            raise TypeError("cancellation_reader must be callable")
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
        self._terminal_writer = terminal_writer
        self._recovery_writer = recovery_writer
        self._lease_state_reader = lease_state_reader
        self._cancellation_reader = cancellation_reader

    @property
    def scheduler(self) -> RedisDispatchWorkerScheduler:
        return self._scheduler

    @property
    def process_executor(self) -> SerialWorkerProcessExecutor:
        return self._process_executor

    async def handle(self, entry: RedisStreamEntry, payload: DispatchPayload) -> WorkerHandleResult:
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
        lease_preflight = await self._lease_preflight(entry, request)
        if lease_preflight is not None:
            return lease_preflight
        if self._cancellation_reader is not None:
            try:
                cancellation_preflight_requested = await asyncio.wait_for(
                    self._cancellation_reader(entry, request),
                    timeout=self._heartbeat_interval_seconds,
                )
            except Exception as error:  # pragma: no cover - persistence boundary
                return WorkerHandleResult(
                    entry.fingerprint,
                    WorkerHandleDecision.RETRY,
                    rejection_reason=f"worker cancellation preflight failed: {type(error).__name__}",
                )
            if not isinstance(cancellation_preflight_requested, bool):
                return WorkerHandleResult(
                    entry.fingerprint,
                    WorkerHandleDecision.RETRY,
                    rejection_reason="worker cancellation preflight returned an invalid state",
                )
            if cancellation_preflight_requested:
                return await self._recover_or_retry(
                    entry,
                    request,
                    RecoveryReason.CANCELLED,
                    "search cancellation was already requested before execution",
                )
        heartbeat_task: asyncio.Task[None] | None = None
        cancellation_task: asyncio.Task[None] | None = None
        heartbeat_failure: list[str] = []
        cancellation_requested: list[bool] = []
        cancellation_failure: list[str] = []
        if self._heartbeat_writer is not None:
            heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(request.lease_state, heartbeat_failure)
            )
        if self._cancellation_reader is not None:
            cancellation_task = asyncio.create_task(
                self._cancellation_loop(
                    entry,
                    request,
                    cancellation_requested,
                    cancellation_failure,
                )
            )
        execution_task = asyncio.create_task(self._process_executor.run_async(request))
        try:
            try:
                monitors = tuple(
                    task for task in (heartbeat_task, cancellation_task) if task is not None
                )
                if not monitors:
                    result = await execution_task
                else:
                    done, _ = await asyncio.wait(
                        (execution_task, *monitors),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if cancellation_task is not None and cancellation_task in done:
                        execution_task.cancel()
                        try:
                            await execution_task
                        except asyncio.CancelledError:
                            pass
                        if cancellation_requested:
                            return await self._recover_or_retry(
                                entry,
                                request,
                                RecoveryReason.CANCELLED,
                                "search cancellation requested during execution",
                            )
                        if cancellation_failure:
                            return await self._recover_or_retry(
                                entry,
                                request,
                                RecoveryReason.WORKER_CRASH,
                                cancellation_failure[0],
                            )
                    if heartbeat_task in done and heartbeat_failure:
                        execution_task.cancel()
                        try:
                            await execution_task
                        except asyncio.CancelledError:
                            pass
                        return await self._recover_or_retry(
                            entry,
                            request,
                            RecoveryReason.WORKER_CRASH,
                            heartbeat_failure[0],
                        )
                    result = await execution_task
            except Exception as error:  # pragma: no cover - process adapter boundary
                return await self._recover_or_retry(
                    entry,
                    request,
                    RecoveryReason.WORKER_CRASH,
                    f"worker process execution failed: {type(error).__name__}",
                )
        finally:
            if not execution_task.done():
                execution_task.cancel()
            try:
                await execution_task
            except (asyncio.CancelledError, Exception):
                pass
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            if cancellation_task is not None:
                cancellation_task.cancel()
                try:
                    await cancellation_task
                except asyncio.CancelledError:
                    pass
        if heartbeat_failure:
            return await self._recover_or_retry(
                entry,
                request,
                RecoveryReason.WORKER_CRASH,
                heartbeat_failure[0],
            )
        if result.decision.value != "completed":
            return await self._recover_or_retry(
                entry,
                request,
                RecoveryReason.WORKER_CRASH,
                f"worker process ended with {result.decision.value}",
            )
        if self._terminal_writer is not None:
            try:
                context = WorkerCompletionContext(entry, request, result, self._clock())
                receipt = await self._terminal_writer(context)
            except Exception as error:  # pragma: no cover - persistence boundary
                return WorkerHandleResult(
                    entry.fingerprint,
                    WorkerHandleDecision.RETRY,
                    rejection_reason=f"worker terminal completion failed: {type(error).__name__}",
                )
        else:
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

    async def _lease_preflight(
        self,
        entry: RedisStreamEntry,
        request: WorkerExecutionRequest,
    ) -> WorkerHandleResult | None:
        """Prevent duplicate/stale dispatches from running under old leases."""

        if self._lease_state_reader is None:
            return None
        try:
            state = await self._lease_state_reader(request)
        except Exception as error:  # pragma: no cover - persistence boundary
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.RETRY,
                rejection_reason=f"worker lease preflight failed: {type(error).__name__}",
            )
        if not isinstance(state, LeaseObservationState):
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.RETRY,
                rejection_reason="persisted worker lease is unavailable",
            )
        if (
            state.lease.lease_id != request.lease_state.lease.lease_id
            or state.lease.attempt_id != request.runtime_request.attempt_id
            or state.lease.worker_id != request.admission.worker_id
        ):
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.RETRY,
                rejection_reason="persisted worker lease differs from its authenticated dispatch",
            )
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.RETRY,
                rejection_reason="worker lease preflight clock was not timezone-aware",
            )
        status = state.lease.status_at(now)
        if status is AttemptLeaseStatus.EXPIRED:
            return await self._recover_or_retry(
                entry,
                request,
                RecoveryReason.LEASE_EXPIRED,
                "persisted worker lease expired before execution",
            )
        if status is AttemptLeaseStatus.RELEASED:
            return await self._recover_or_retry(
                entry,
                request,
                RecoveryReason.WORKER_CRASH,
                "persisted worker lease was already released",
            )
        if state != request.lease_state:
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.RETRY,
                rejection_reason="worker lease advanced after this dispatch was materialized",
            )
        return None

    async def _recover_or_retry(
        self,
        entry: RedisStreamEntry,
        request: WorkerExecutionRequest,
        reason: RecoveryReason,
        fallback_reason: str,
    ) -> WorkerHandleResult:
        """Use durable recovery when configured; otherwise keep the entry pending."""

        if self._recovery_writer is None:
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.RETRY,
                rejection_reason=fallback_reason,
            )
        observed_at = self._clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.RETRY,
                rejection_reason="worker recovery clock was not timezone-aware",
            )
        try:
            result = await self._recovery_writer(
                WorkerRecoveryContext(entry, request, reason, observed_at)
            )
        except Exception as error:  # pragma: no cover - persistence boundary
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.RETRY,
                rejection_reason=f"worker recovery failed: {type(error).__name__}",
            )
        if not isinstance(result, WorkerHandleResult):
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.RETRY,
                rejection_reason="worker recovery returned an invalid receipt",
            )
        if result.entry_fingerprint != entry.fingerprint:
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.RETRY,
                rejection_reason="worker recovery receipt references a different entry",
            )
        return result

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
                failures.append("worker lease heartbeat rejected: " + resolution.decision.value)
                return
            if resolution.state.last_sequence < sequence:
                failures.append("worker lease heartbeat returned stale lease state")
                return
            state = resolution.state

    async def _cancellation_loop(
        self,
        entry: RedisStreamEntry,
        request: WorkerExecutionRequest,
        cancellation_requested: list[bool],
        cancellation_failure: list[str],
    ) -> None:
        """Poll durable search state and stop the child when cancellation lands."""

        if self._cancellation_reader is None:
            return
        while True:
            try:
                requested = await asyncio.wait_for(
                    self._cancellation_reader(entry, request),
                    timeout=self._heartbeat_interval_seconds,
                )
            except Exception as error:  # pragma: no cover - persistence boundary
                cancellation_failure.append(
                    f"worker cancellation state read failed: {type(error).__name__}"
                )
                return
            if not isinstance(requested, bool):
                cancellation_failure.append("worker cancellation state read was invalid")
                return
            if requested:
                cancellation_requested.append(True)
                return
            await self._heartbeat_sleep(self._heartbeat_interval_seconds)


__all__ = [
    "DedicatedStrategyWorkerService",
    "WorkerCancellationReader",
    "WorkerCompletionWriter",
    "WorkerHandoffMaterializer",
    "WorkerLeaseHeartbeatWriter",
    "WorkerLeaseStateReader",
    "WorkerTerminalWriter",
    "WorkerCompletionContext",
    "WorkerRecoveryContext",
    "WorkerRecoveryWriter",
    "WorkerServiceCallbacks",
]
