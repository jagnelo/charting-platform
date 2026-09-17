from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport, RedisStreamEntry
from app.strategy_lab_v2.tests.test_worker_consumer import (
    FakeRedis,
    _stream_response,
)
from app.strategy_lab_v2.tests.test_worker_process import _request
from app.strategy_lab_v2.worker_consumer import (
    RedisDispatchWorker,
    RedisDispatchWorkerScheduler,
    WorkerHandleDecision,
    WorkerHandleResult,
)
from app.strategy_lab_v2.worker_process import (
    WorkerExecutionRequest,
    WorkerProcessResolution,
)
from app.strategy_lab_v2.worker_service import DedicatedStrategyWorkerService


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

    return DedicatedStrategyWorkerService(
        scheduler,
        _Loader(payload),
        materializer,
        completion,
    ), payload, entry


async def test_service_materializes_runs_and_delegates_durable_completion(tmp_path: Path) -> None:
    service, payload, entry = _service(tmp_path)

    result = await service.handle(entry, payload)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert result.entry_fingerprint == entry.fingerprint


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
