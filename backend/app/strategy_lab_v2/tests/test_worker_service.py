from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.lease_observations import (
    LeaseObservation,
    LeaseObservationDecision,
    LeaseObservationKind,
    LeaseObservationResolution,
    apply_lease_observation,
)
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport, RedisStreamEntry
from app.strategy_lab_v2.tests.test_worker_consumer import (
    FakeRedis,
    _stream_response,
)
from app.strategy_lab_v2.tests.test_worker_process import NOW, _request
from app.strategy_lab_v2.worker_consumer import (
    RedisDispatchWorker,
    RedisDispatchWorkerScheduler,
    WorkerHandleDecision,
    WorkerHandleResult,
)
from app.strategy_lab_v2.worker_process import (
    SerialWorkerProcessExecutor,
    WorkerExecutionRequest,
    WorkerProcessDecision,
    WorkerProcessResolution,
)
from app.strategy_lab_v2.worker_service import (
    DedicatedStrategyWorkerService,
    WorkerCompletionContext,
    WorkerRecoveryContext,
)


def _entry(payload: DispatchPayload) -> RedisStreamEntry:
    return RedisStreamEntry(
        "strategy-lab:v2:stream:backtest",
        "1-0",
        content_digest("message"),
        "attempt-1",
        payload.payload_digest,
        content_digest("request"),
    )


class _Loader:
    def __init__(self, payload: DispatchPayload) -> None:
        self.payload = payload

    async def load_payload(self, payload_digest: str) -> DispatchPayload | None:
        if payload_digest != self.payload.payload_digest:
            return None
        return self.payload


async def _sleep(_: float) -> None:
    return None


def _service(
    tmp_path: Path,
    redis: FakeRedis | None = None,
) -> tuple[DedicatedStrategyWorkerService, DispatchPayload, RedisStreamEntry]:
    payload = DispatchPayload.from_mapping({"attempt_id": "attempt-1"})
    entry = _entry(payload)
    client = redis or FakeRedis()
    worker = RedisDispatchWorker(
        RedisDispatchTransport(client),
        queue_name="backtest",
        group_name="workers",
        consumer_name="worker-1",
    )
    scheduler = RedisDispatchWorkerScheduler(worker, interval_seconds=1, sleep=_sleep)

    async def materializer(
        received_entry: RedisStreamEntry, received_payload: DispatchPayload
    ) -> WorkerExecutionRequest:
        assert received_entry is entry or received_payload is payload
        return _request(tmp_path)

    async def completion(
        received_entry: RedisStreamEntry, result: WorkerProcessResolution
    ) -> WorkerHandleResult:
        assert result.process_id is not None
        return WorkerHandleResult(
            received_entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest("durable-receipt"),
        )

    return (
        DedicatedStrategyWorkerService(
            scheduler,
            _Loader(payload),
            materializer,
            completion,
        ),
        payload,
        entry,
    )


async def test_service_materializes_runs_and_delegates_durable_completion(tmp_path: Path) -> None:
    service, payload, entry = _service(tmp_path)

    result = await service.handle(entry, payload)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert result.entry_fingerprint == entry.fingerprint


async def test_service_recovers_expired_persisted_lease_before_starting_process(
    tmp_path: Path,
) -> None:
    service, payload, entry = _service(tmp_path)
    request = _request(tmp_path)
    observed_at = request.lease_state.lease.expires_at + timedelta(seconds=1)
    recovered: list[WorkerRecoveryContext] = []

    async def materializer(
        _entry: RedisStreamEntry, _payload: DispatchPayload
    ) -> WorkerExecutionRequest:
        return request

    async def lease_state_reader(_request: WorkerExecutionRequest):
        return request.lease_state

    async def recovery_writer(context: WorkerRecoveryContext) -> WorkerHandleResult:
        recovered.append(context)
        return WorkerHandleResult(
            entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest("recovery-scheduled"),
        )

    guarded = DedicatedStrategyWorkerService(
        service.scheduler,
        _Loader(payload),
        materializer,
        service._completion_writer,
        clock=lambda: observed_at,
        recovery_writer=recovery_writer,
        lease_state_reader=lease_state_reader,
    )
    result = await guarded.handle(entry, payload)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert len(recovered) == 1
    assert recovered[0].reason.value == "lease_expired"
    assert recovered[0].observed_at == observed_at


async def test_service_does_not_run_a_dispatch_with_an_advanced_active_lease(
    tmp_path: Path,
) -> None:
    service, payload, entry = _service(tmp_path)
    request = _request(tmp_path)
    heartbeat_at = NOW + timedelta(seconds=1)
    lease = request.lease_state.lease
    observation = LeaseObservation(
        content_digest("another-worker-heartbeat"),
        lease.lease_id,
        lease.worker_id,
        lease.attempt_id,
        1,
        LeaseObservationKind.HEARTBEAT,
        heartbeat_at,
        heartbeat_at + timedelta(seconds=30),
    )
    advanced = apply_lease_observation(request.lease_state, observation).state

    async def materializer(
        _entry: RedisStreamEntry, _payload: DispatchPayload
    ) -> WorkerExecutionRequest:
        return request

    async def lease_state_reader(_request: WorkerExecutionRequest):
        return advanced

    async def recovery_writer(_context: WorkerRecoveryContext) -> WorkerHandleResult:
        raise AssertionError("an active lease owned by another worker must not be recovered")

    guarded = DedicatedStrategyWorkerService(
        service.scheduler,
        _Loader(payload),
        materializer,
        service._completion_writer,
        clock=lambda: NOW + timedelta(seconds=2),
        recovery_writer=recovery_writer,
        lease_state_reader=lease_state_reader,
    )
    result = await guarded.handle(entry, payload)

    assert result.decision is WorkerHandleDecision.RETRY
    assert "lease advanced" in (result.rejection_reason or "")


async def test_service_delegates_child_failure_to_durable_recovery_writer(
    tmp_path: Path,
) -> None:
    service, payload, entry = _service(tmp_path)
    request = _request(tmp_path)
    recovered: list[WorkerRecoveryContext] = []

    class FailedExecutor(SerialWorkerProcessExecutor):
        async def run_async(
            self,
            received: WorkerExecutionRequest,
            *,
            timeout_seconds: float | None = None,
            poll_interval_seconds: float = 0.1,
        ) -> WorkerProcessResolution:
            del timeout_seconds, poll_interval_seconds
            return WorkerProcessResolution(
                received.request_fingerprint,
                WorkerProcessDecision.CHILD_FAILED,
                error_digest=content_digest("child-failed"),
            )

    async def materializer(
        _entry: RedisStreamEntry, _payload: DispatchPayload
    ) -> WorkerExecutionRequest:
        return request

    async def recovery_writer(context: WorkerRecoveryContext) -> WorkerHandleResult:
        recovered.append(context)
        return WorkerHandleResult(
            entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest("retry-outbox-committed"),
        )

    recovering = DedicatedStrategyWorkerService(
        service.scheduler,
        _Loader(payload),
        materializer,
        service._completion_writer,
        process_executor=FailedExecutor(timeout_seconds=1),
        clock=lambda: NOW + timedelta(seconds=2),
        recovery_writer=recovery_writer,
    )
    result = await recovering.handle(entry, payload)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert len(recovered) == 1
    assert recovered[0].reason.value == "worker_crash"
    assert recovered[0].request == request


async def test_service_rejects_invalid_materialization_without_starting_process(
    tmp_path: Path,
) -> None:
    service, payload, entry = _service(tmp_path)

    async def invalid_materializer(
        received_entry: RedisStreamEntry, received_payload: DispatchPayload
    ) -> str:
        del received_entry, received_payload
        return "bad"

    service = DedicatedStrategyWorkerService(
        service.scheduler,
        _Loader(payload),
        cast(Any, invalid_materializer),
        service._completion_writer,
    )
    result = await service.handle(entry, payload)

    assert result.decision is WorkerHandleDecision.REJECT
    assert result.rejection_reason == "worker handoff materializer returned an invalid request"


async def test_service_run_acks_only_after_completion_writer(tmp_path: Path) -> None:
    redis = FakeRedis()
    service, payload, entry = _service(tmp_path, redis)
    redis.fresh = _stream_response(entry)

    class Stop:
        def is_set(self) -> bool:
            return False

    cycles = await service.run(Stop(), max_cycles=1)

    assert len(cycles) == 1
    assert cycles[0].entries[0].decision.value == "acknowledged"
    assert any(call[0] == "xack" for call in redis.calls)


async def test_service_emits_ordered_lease_heartbeat_during_process_handoff(
    tmp_path: Path,
) -> None:
    service, payload, entry = _service(tmp_path)
    initial_request = _request(tmp_path)
    observations = []
    state = initial_request.lease_state

    class BlockingExecutor(SerialWorkerProcessExecutor):
        def run(
            self,
            request: WorkerExecutionRequest,
            *,
            timeout_seconds: float | None = None,
        ) -> WorkerProcessResolution:
            del timeout_seconds
            time.sleep(0.05)
            return WorkerProcessResolution(
                request.request_fingerprint,
                WorkerProcessDecision.CHILD_FAILED,
                error_digest=content_digest("child-failed"),
            )

    async def materializer(
        _entry: RedisStreamEntry, _payload: DispatchPayload
    ) -> WorkerExecutionRequest:
        return initial_request

    async def heartbeat(observation):
        nonlocal state
        observations.append(observation)
        resolution = apply_lease_observation(state, observation)
        assert resolution.decision is LeaseObservationDecision.APPLY
        state = resolution.state
        return resolution

    async def completion(
        received_entry: RedisStreamEntry, _result: WorkerProcessResolution
    ) -> WorkerHandleResult:
        return WorkerHandleResult(
            received_entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest("durable-receipt"),
        )

    service = DedicatedStrategyWorkerService(
        service.scheduler,
        _Loader(payload),
        materializer,
        completion,
        process_executor=BlockingExecutor(timeout_seconds=1),
        heartbeat_writer=heartbeat,
        heartbeat_interval_seconds=0.005,
        heartbeat_extension_seconds=0.1,
        clock=lambda: NOW,
    )
    result = await service.handle(entry, payload)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert observations
    assert observations[0].sequence == 1
    assert observations[0].kind.value == "heartbeat"
    assert state.last_sequence == len(observations)


async def test_service_leaves_entry_pending_when_heartbeat_is_rejected(tmp_path: Path) -> None:
    service, payload, entry = _service(tmp_path)
    initial_request = _request(tmp_path)

    class BlockingExecutor(SerialWorkerProcessExecutor):
        def run(
            self,
            request: WorkerExecutionRequest,
            *,
            timeout_seconds: float | None = None,
        ) -> WorkerProcessResolution:
            del timeout_seconds
            time.sleep(0.02)
            return WorkerProcessResolution(
                request.request_fingerprint,
                WorkerProcessDecision.CHILD_FAILED,
                error_digest=content_digest("child-failed"),
            )

    async def materializer(
        _entry: RedisStreamEntry, _payload: DispatchPayload
    ) -> WorkerExecutionRequest:
        return initial_request

    async def heartbeat(observation):
        return LeaseObservationResolution(
            LeaseObservationDecision.REJECT,
            initial_request.lease_state,
            observation.sequence,
            rejection_reason="lease expired",
        )

    async def completion(*_args):
        raise AssertionError("completion must not run after heartbeat rejection")

    service = DedicatedStrategyWorkerService(
        service.scheduler,
        _Loader(payload),
        materializer,
        completion,
        process_executor=BlockingExecutor(timeout_seconds=1),
        heartbeat_writer=heartbeat,
        heartbeat_interval_seconds=0.005,
        heartbeat_extension_seconds=0.1,
        clock=lambda: NOW,
    )
    result = await service.handle(entry, payload)

    assert result.decision is WorkerHandleDecision.RETRY
    assert result.rejection_reason == "worker lease heartbeat rejected: reject"


async def test_service_cancels_execution_when_heartbeat_fails(tmp_path: Path) -> None:
    service, payload, entry = _service(tmp_path)
    initial_request = _request(tmp_path)

    class CancellationAwareExecutor(SerialWorkerProcessExecutor):
        def __init__(self) -> None:
            super().__init__(timeout_seconds=1)
            self.cancelled = False

        async def run_async(
            self,
            request: WorkerExecutionRequest,
            *,
            timeout_seconds: float | None = None,
            poll_interval_seconds: float = 0.005,
        ) -> WorkerProcessResolution:
            del request, timeout_seconds, poll_interval_seconds
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            raise AssertionError("execution should be cancelled after heartbeat failure")

    executor = CancellationAwareExecutor()

    async def materializer(
        _entry: RedisStreamEntry, _payload: DispatchPayload
    ) -> WorkerExecutionRequest:
        return initial_request

    async def heartbeat(_observation):
        return LeaseObservationResolution(
            LeaseObservationDecision.REJECT,
            initial_request.lease_state,
            1,
            rejection_reason="lease expired",
        )

    async def completion(*_args: Any) -> WorkerHandleResult:
        raise AssertionError("completion must not run after heartbeat failure")

    service = DedicatedStrategyWorkerService(
        service.scheduler,
        _Loader(payload),
        materializer,
        completion,
        process_executor=executor,
        heartbeat_writer=heartbeat,
        heartbeat_interval_seconds=0.001,
        heartbeat_extension_seconds=0.1,
        heartbeat_sleep=asyncio.sleep,
        clock=lambda: NOW,
    )
    result = await service.handle(entry, payload)

    assert result.decision is WorkerHandleDecision.RETRY
    assert result.rejection_reason == "worker lease heartbeat rejected: reject"
    assert executor.cancelled


async def test_service_cancellation_cancels_execution_task(tmp_path: Path) -> None:
    service, payload, entry = _service(tmp_path)

    class CancellationAwareExecutor(SerialWorkerProcessExecutor):
        def __init__(self) -> None:
            super().__init__(timeout_seconds=1)
            self.cancelled = False

        async def run_async(
            self,
            request: WorkerExecutionRequest,
            *,
            timeout_seconds: float | None = None,
            poll_interval_seconds: float = 0.005,
        ) -> WorkerProcessResolution:
            del request, timeout_seconds, poll_interval_seconds
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            raise AssertionError("execution should be cancelled with the service")

    executor = CancellationAwareExecutor()
    initial_request = _request(tmp_path)

    async def materializer(
        _entry: RedisStreamEntry, _payload: DispatchPayload
    ) -> WorkerExecutionRequest:
        return initial_request

    async def completion(*_args: Any) -> WorkerHandleResult:
        raise AssertionError("completion must not run after service cancellation")

    service = DedicatedStrategyWorkerService(
        service.scheduler,
        _Loader(payload),
        materializer,
        completion,
        process_executor=executor,
    )
    task = asyncio.create_task(service.handle(entry, payload))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert executor.cancelled


async def test_persisted_search_cancellation_terminates_child_and_records_terminal_cancel(
    tmp_path: Path,
) -> None:
    service, payload, entry = _service(tmp_path)
    request = _request(tmp_path)
    process_started = asyncio.Event()

    class CancellationAwareExecutor(SerialWorkerProcessExecutor):
        def __init__(self) -> None:
            super().__init__(timeout_seconds=1)
            self.cancelled = False

        async def run_async(
            self,
            _request: WorkerExecutionRequest,
            *,
            timeout_seconds: float | None = None,
            poll_interval_seconds: float = 0.005,
        ) -> WorkerProcessResolution:
            del timeout_seconds, poll_interval_seconds
            process_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            raise AssertionError("child should stop after durable search cancellation")

    executor = CancellationAwareExecutor()
    recoveries: list[WorkerRecoveryContext] = []

    async def materializer(
        _entry: RedisStreamEntry, _payload: DispatchPayload
    ) -> WorkerExecutionRequest:
        return request

    async def cancellation_reader(
        _entry: RedisStreamEntry, _request: WorkerExecutionRequest
    ) -> bool:
        return process_started.is_set()

    async def recovery_writer(context: WorkerRecoveryContext) -> WorkerHandleResult:
        recoveries.append(context)
        return WorkerHandleResult(
            entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest("durable-cancelled-attempt"),
        )

    async def completion(*_args: Any) -> WorkerHandleResult:
        raise AssertionError("cancelled process must not publish a result")

    cancelled = DedicatedStrategyWorkerService(
        service.scheduler,
        _Loader(payload),
        materializer,
        completion,
        process_executor=executor,
        recovery_writer=recovery_writer,
        cancellation_reader=cancellation_reader,
        heartbeat_interval_seconds=0.001,
        clock=lambda: NOW,
    )
    result = await cancelled.handle(entry, payload)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert executor.cancelled
    assert len(recoveries) == 1
    assert recoveries[0].reason.value == "cancelled"


async def test_cancellation_state_read_failure_stops_process_for_durable_recovery(
    tmp_path: Path,
) -> None:
    service, payload, entry = _service(tmp_path)
    request = _request(tmp_path)
    process_started = asyncio.Event()

    class CancellationAwareExecutor(SerialWorkerProcessExecutor):
        def __init__(self) -> None:
            super().__init__(timeout_seconds=1)
            self.cancelled = False

        async def run_async(
            self,
            _request: WorkerExecutionRequest,
            *,
            timeout_seconds: float | None = None,
            poll_interval_seconds: float = 0.005,
        ) -> WorkerProcessResolution:
            del timeout_seconds, poll_interval_seconds
            process_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            raise AssertionError("unknown cancellation state must stop the child")

    executor = CancellationAwareExecutor()
    recoveries: list[WorkerRecoveryContext] = []

    async def materializer(
        _entry: RedisStreamEntry, _payload: DispatchPayload
    ) -> WorkerExecutionRequest:
        return request

    async def cancellation_reader(
        _entry: RedisStreamEntry, _request: WorkerExecutionRequest
    ) -> bool:
        if process_started.is_set():
            raise RuntimeError("search state unavailable")
        return False

    async def recovery_writer(context: WorkerRecoveryContext) -> WorkerHandleResult:
        recoveries.append(context)
        return WorkerHandleResult(
            entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest("durable-retry-after-cancel-state-error"),
        )

    async def completion(*_args: Any) -> WorkerHandleResult:
        raise AssertionError("unknown cancellation state must not publish a result")

    guarded = DedicatedStrategyWorkerService(
        service.scheduler,
        _Loader(payload),
        materializer,
        completion,
        process_executor=executor,
        recovery_writer=recovery_writer,
        cancellation_reader=cancellation_reader,
        heartbeat_interval_seconds=0.001,
        clock=lambda: NOW,
    )
    result = await guarded.handle(entry, payload)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert executor.cancelled
    assert len(recoveries) == 1
    assert recoveries[0].reason.value == "worker_crash"


async def test_service_can_delegate_terminal_context_before_acknowledgement(
    tmp_path: Path,
) -> None:
    service, payload, entry = _service(tmp_path)
    initial_request = _request(tmp_path)
    seen: list[WorkerCompletionContext] = []

    class BlockingExecutor(SerialWorkerProcessExecutor):
        def run(
            self,
            request: WorkerExecutionRequest,
            *,
            timeout_seconds: float | None = None,
        ) -> WorkerProcessResolution:
            del timeout_seconds
            return WorkerProcessResolution(
                request.request_fingerprint,
                WorkerProcessDecision.CHILD_FAILED,
                error_digest=content_digest("child-failed"),
            )

    async def materializer(
        _entry: RedisStreamEntry, _payload: DispatchPayload
    ) -> WorkerExecutionRequest:
        return initial_request

    async def completion(*_args: Any) -> WorkerHandleResult:
        raise AssertionError("legacy completion writer must not run with terminal_writer")

    async def terminal(context: WorkerCompletionContext) -> WorkerHandleResult:
        seen.append(context)
        return WorkerHandleResult(
            context.entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest("terminal-receipt"),
        )

    service = DedicatedStrategyWorkerService(
        service.scheduler,
        _Loader(payload),
        materializer,
        completion,
        process_executor=BlockingExecutor(timeout_seconds=1),
        terminal_writer=terminal,
    )
    result = await service.handle(entry, payload)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert len(seen) == 1
    assert seen[0].entry == entry
    assert seen[0].request == initial_request
    assert seen[0].process.request_fingerprint == initial_request.request_fingerprint
