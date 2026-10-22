from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.forward_worker_handoff import (
    ForwardEventDispatchPayload,
    ForwardEventWorkItem,
)
from app.strategy_lab_v2.forward_worker_service import ForwardEventWorkerService
from app.strategy_lab_v2.postgres_forward_dispatch import ForwardEventDispatchRecord
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport, RedisStreamEntry
from app.strategy_lab_v2.tests.test_worker_consumer import FakeRedis, _stream_response
from app.strategy_lab_v2.worker_consumer import (
    RedisDispatchWorker,
    RedisDispatchWorkerScheduler,
    WorkerHandleDecision,
    WorkerHandleResult,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


class Loader:
    def __init__(self, payload: DispatchPayload) -> None:
        self.payload = payload

    async def load_payload(self, payload_digest: str) -> DispatchPayload | None:
        return self.payload if payload_digest == self.payload.payload_digest else None


def _work() -> tuple[RedisStreamEntry, DispatchPayload, ForwardEventWorkItem]:
    event_fingerprint = content_digest("event")
    payload = DispatchPayload.from_mapping(
        {"event_fingerprint": event_fingerprint, "replay_plan_fingerprint": None}
    )
    request = DispatchRequest(
        "forward-key", "forward-instance", payload.payload_digest, "forward-events", NOW
    )
    record = ForwardEventDispatchRecord(
        "owner-1", "forward-instance", event_fingerprint, request
    )
    entry = RedisStreamEntry(
        "strategy-lab:v2:stream:forward-events",
        "1-0",
        content_digest("message"),
        request.attempt_id,
        request.payload_digest,
        request.fingerprint,
    )
    return entry, payload, ForwardEventWorkItem(
        record, ForwardEventDispatchPayload(event_fingerprint)
    )


def _service(
    handler: Any,
) -> tuple[ForwardEventWorkerService, RedisStreamEntry, DispatchPayload, FakeRedis]:
    entry, payload, work_item = _work()
    redis = FakeRedis()
    worker = RedisDispatchWorker(
        RedisDispatchTransport(redis),
        queue_name="forward-events",
        group_name="forward-workers",
        consumer_name="forward-1",
    )
    scheduler = RedisDispatchWorkerScheduler(worker, interval_seconds=1, sleep=_sleep)

    async def materializer(
        received_entry: RedisStreamEntry, received_payload: DispatchPayload
    ) -> ForwardEventWorkItem:
        assert received_entry == entry
        assert received_payload == payload
        return work_item

    return (
        ForwardEventWorkerService(scheduler, Loader(payload), materializer, handler),
        entry,
        payload,
        redis,
    )


async def _sleep(_: float) -> None:
    return None


@pytest.mark.asyncio
async def test_forward_worker_handler_receipt_is_acknowledged_after_host_commit() -> None:
    async def handler(
        entry: RedisStreamEntry, _work_item: ForwardEventWorkItem
    ) -> WorkerHandleResult:
        return WorkerHandleResult(
            entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest("durable-forward-receipt"),
        )

    service, entry, payload, _redis = _service(handler)
    result = await service.handle(entry, payload)
    assert result.decision is WorkerHandleDecision.COMPLETE


@pytest.mark.asyncio
async def test_forward_worker_retries_handler_failures_without_acknowledgement() -> None:
    async def handler(
        _entry: RedisStreamEntry, _work_item: ForwardEventWorkItem
    ) -> WorkerHandleResult:
        raise RuntimeError("host unavailable")

    service, entry, payload, _redis = _service(handler)
    result = await service.handle(entry, payload)
    assert result.decision is WorkerHandleDecision.RETRY
    assert result.rejection_reason == "forward event handler failed: RuntimeError"


@pytest.mark.asyncio
async def test_forward_worker_scheduler_acknowledges_only_completed_receipt() -> None:
    async def handler(
        entry: RedisStreamEntry, _work_item: ForwardEventWorkItem
    ) -> WorkerHandleResult:
        return WorkerHandleResult(
            entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest("durable-forward-receipt"),
        )

    service, entry, _payload, redis = _service(handler)
    redis.fresh = _stream_response(entry)

    class Stop:
        def is_set(self) -> bool:
            return False

    cycles = await service.run(Stop(), max_cycles=1)
    assert cycles[0].entries[0].decision.value == "acknowledged"
