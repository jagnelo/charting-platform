from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import DispatchRequest, build_dispatch_envelope
from app.strategy_lab_v2.redis_transport import (
    RedisDispatchTransport,
    RedisStreamEntry,
    RedisTransportDecision,
)
from app.strategy_lab_v2.worker_consumer import (
    RedisDispatchWorker,
    WorkerEntryDecision,
    WorkerHandleDecision,
    WorkerHandleResult,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_second_redis_consumer_reclaims_and_acknowledges_abandoned_dispatch(
    redis_url: str,
) -> None:
    redis = Redis.from_url(redis_url, decode_responses=True)
    namespace = f"strategy-lab:v2:integration:{uuid4().hex}"
    transport = RedisDispatchTransport(redis, namespace=namespace)
    stream_key = transport.stream_key("backtest")
    idempotency_key = f"{namespace}:idempotency"
    request = DispatchRequest(
        f"integration-{uuid4().hex}",
        f"attempt-{uuid4().hex}",
        content_digest("integration payload"),
        "backtest",
        datetime.now(UTC),
    )
    envelope = build_dispatch_envelope(request)

    try:
        queued = await transport.enqueue(envelope)
        assert queued.decision is RedisTransportDecision.ENQUEUED

        first_consumer = RedisDispatchWorker(
            transport,
            queue_name="backtest",
            group_name="workers",
            consumer_name="worker-crashed",
            reclaim_idle_ms=0,
        )
        first_poll = await first_consumer.poll()
        assert len(first_poll.entries) == 1
        assert first_poll.entries[0].message_id == envelope.message_id

        second_consumer = RedisDispatchWorker(
            transport,
            queue_name="backtest",
            group_name="workers",
            consumer_name="worker-restarted",
            reclaim_idle_ms=0,
        )
        handled: list[str] = []

        async def complete(entry: RedisStreamEntry) -> WorkerHandleResult:
            handled.append(entry.fingerprint)
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.COMPLETE,
                content_digest("durable completion receipt"),
            )

        cycle = await second_consumer.handle_once(complete)
        assert len(cycle.poll.entries) == 1
        assert cycle.poll.entries[0].message_id == envelope.message_id
        assert handled == [cycle.poll.entries[0].fingerprint]
        assert [result.decision for result in cycle.entries] == [WorkerEntryDecision.ACKNOWLEDGED]
        assert await redis.xpending(queued.stream_key, "workers") == {
            "pending": 0,
            "min": None,
            "max": None,
            "consumers": [],
        }
    finally:
        try:
            await redis.delete(stream_key, idempotency_key)
        finally:
            await redis.aclose()
