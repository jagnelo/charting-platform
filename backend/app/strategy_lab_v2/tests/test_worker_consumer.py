from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport, RedisStreamEntry
from app.strategy_lab_v2.worker_consumer import (
    RedisDispatchWorker,
    RedisDispatchWorkerScheduler,
    WorkerEntryDecision,
    WorkerHandleDecision,
    WorkerHandleResult,
    WorkerPollDecision,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


class FakeRedis:
    def __init__(
        self,
        *,
        group_result=1,
        reclaimed=(),
        fresh=(),
        ack_result=1,
    ) -> None:
        self.group_result = group_result
        self.reclaimed = reclaimed
        self.fresh = fresh
        self.ack_result = ack_result
        self.calls: list[tuple] = []

    async def eval(self, *args):
        self.calls.append(("eval", args))
        return 1

    async def xgroup_create(self, **kwargs):
        self.calls.append(("xgroup_create", kwargs))
        if isinstance(self.group_result, Exception):
            raise self.group_result
        return self.group_result

    async def xautoclaim(self, **kwargs):
        self.calls.append(("xautoclaim", kwargs))
        return ["0-0", list(self.reclaimed), []]

    async def xreadgroup(self, **kwargs):
        self.calls.append(("xreadgroup", kwargs))
        return list(self.fresh)

    async def xack(self, *args):
        self.calls.append(("xack", args))
        return self.ack_result


def _entry(stream_id: str = "1-0") -> RedisStreamEntry:
    return RedisStreamEntry(
        "strategy-lab:v2:stream:backtest",
        stream_id,
        content_digest("message"),
        "attempt-1",
        content_digest("payload"),
        content_digest("request"),
    )


def _raw_entry(entry: RedisStreamEntry) -> tuple[str, dict[str, str]]:
    return (
        entry.stream_id,
        {
            "message_id": entry.message_id,
            "attempt_id": entry.attempt_id,
            "payload_digest": entry.payload_digest,
            "request_fingerprint": entry.request_fingerprint,
        },
    )


def _stream_response(*entries: RedisStreamEntry):
    return [(entries[0].stream_key, [_raw_entry(entry) for entry in entries])]


def _handler_result(entry: RedisStreamEntry, decision=WorkerHandleDecision.COMPLETE):
    return WorkerHandleResult(
        entry.fingerprint,
        decision,
        content_digest("receipt") if decision is WorkerHandleDecision.COMPLETE else None,
        None if decision is WorkerHandleDecision.COMPLETE else "retry later",
    )


async def _complete_handler(entry: RedisStreamEntry) -> WorkerHandleResult:
    return _handler_result(entry)


async def _retry_handler(entry: RedisStreamEntry) -> WorkerHandleResult:
    return _handler_result(entry, WorkerHandleDecision.RETRY)


class PayloadLoader:
    def __init__(self, payload: DispatchPayload | None) -> None:
        self.payload = payload
        self.calls: list[str] = []

    async def load_payload(self, payload_digest: str) -> DispatchPayload | None:
        self.calls.append(payload_digest)
        return self.payload


@pytest.mark.asyncio
async def test_poll_reclaims_before_reading_new_entries_and_bounds_batch() -> None:
    reclaimed = (_raw_entry(_entry("1-0")),)
    fresh = _stream_response(_entry("2-0"))
    redis = FakeRedis(reclaimed=reclaimed, fresh=fresh)
    worker = RedisDispatchWorker(
        RedisDispatchTransport(redis),
        queue_name="backtest",
        group_name="workers",
        consumer_name="worker-1",
        batch_size=2,
    )
    result = await worker.poll()
    assert result.decision is WorkerPollDecision.READY
    assert [item.stream_id for item in result.entries] == ["1-0", "2-0"]
    assert [call[0] for call in redis.calls] == ["xgroup_create", "xautoclaim", "xreadgroup"]
    assert redis.calls[-1][1]["count"] == 1


@pytest.mark.asyncio
async def test_completed_handler_is_acked_after_authoritative_receipt() -> None:
    entry = _entry()
    redis = FakeRedis(fresh=_stream_response(entry))
    worker = RedisDispatchWorker(
        RedisDispatchTransport(redis),
        queue_name="backtest",
        group_name="workers",
        consumer_name="worker-1",
    )
    result = await worker.handle_once(_complete_handler)
    assert result.entries[0].decision is WorkerEntryDecision.ACKNOWLEDGED
    assert redis.calls[-1][0] == "xack"


@pytest.mark.asyncio
async def test_retry_result_is_not_acked() -> None:
    entry = _entry()
    redis = FakeRedis(fresh=_stream_response(entry))
    worker = RedisDispatchWorker(
        RedisDispatchTransport(redis),
        queue_name="backtest",
        group_name="workers",
        consumer_name="worker-1",
    )
    result = await worker.handle_once(_retry_handler)
    assert result.entries[0].decision is WorkerEntryDecision.RETRY
    assert not any(call[0] == "xack" for call in redis.calls)


@pytest.mark.asyncio
async def test_ack_failure_preserves_pending_evidence() -> None:
    entry = _entry()
    redis = FakeRedis(
        fresh=_stream_response(entry),
        ack_result=0,
    )
    worker = RedisDispatchWorker(
        RedisDispatchTransport(redis),
        queue_name="backtest",
        group_name="workers",
        consumer_name="worker-1",
    )
    result = await worker.handle_once(_complete_handler)
    assert result.entries[0].decision is WorkerEntryDecision.ACKNOWLEDGEMENT_FAILED
    assert result.entries[0].rejection_reason


@pytest.mark.asyncio
async def test_materialized_handler_receives_authenticated_payload_before_ack() -> None:
    entry = _entry()
    redis = FakeRedis(fresh=_stream_response(entry))
    payload = DispatchPayload.from_mapping({"symbol": "AAPL", "side": "buy"})
    entry = RedisStreamEntry(
        entry.stream_key,
        entry.stream_id,
        entry.message_id,
        entry.attempt_id,
        payload.payload_digest,
        entry.request_fingerprint,
    )
    redis = FakeRedis(fresh=_stream_response(entry))
    loader = PayloadLoader(payload)
    seen: list[dict[str, object]] = []

    async def handler(received_entry, received_payload):
        seen.append(dict(received_payload.value))
        return _handler_result(received_entry)

    worker = RedisDispatchWorker(
        RedisDispatchTransport(redis),
        queue_name="backtest",
        group_name="workers",
        consumer_name="worker-1",
    )
    result = await worker.handle_materialized_once(loader, handler)

    assert result.entries[0].decision is WorkerEntryDecision.ACKNOWLEDGED
    assert seen == [{"symbol": "AAPL", "side": "buy"}]
    assert loader.calls == [payload.payload_digest]


@pytest.mark.asyncio
async def test_missing_materialized_payload_remains_pending_for_retry() -> None:
    entry = _entry()
    redis = FakeRedis(fresh=_stream_response(entry))
    worker = RedisDispatchWorker(
        RedisDispatchTransport(redis),
        queue_name="backtest",
        group_name="workers",
        consumer_name="worker-1",
    )
    async def handler(received_entry, received_payload):
        del received_payload
        return _handler_result(received_entry)

    result = await worker.handle_materialized_once(PayloadLoader(None), handler)

    assert result.entries[0].decision is WorkerEntryDecision.RETRY
    assert not any(call[0] == "xack" for call in redis.calls)


@pytest.mark.asyncio
async def test_group_setup_failure_returns_typed_empty_poll() -> None:
    worker = RedisDispatchWorker(
        RedisDispatchTransport(
            FakeRedis(group_result=RuntimeError("Redis unavailable"))
        ),
        queue_name="backtest",
        group_name="workers",
        consumer_name="worker-1",
    )
    result = await worker.poll()
    assert result.decision is WorkerPollDecision.REJECT
    assert result.entries == ()
    assert result.rejection_reason


@pytest.mark.asyncio
async def test_worker_scheduler_runs_bounded_cycles_and_stops_explicitly() -> None:
    entry = _entry()
    redis = FakeRedis(fresh=_stream_response(entry))
    worker = RedisDispatchWorker(
        RedisDispatchTransport(redis),
        queue_name="backtest",
        group_name="workers",
        consumer_name="worker-1",
    )
    sleeps: list[float] = []

    class StopEvent:
        def __init__(self) -> None:
            self.stopped = False

        def is_set(self) -> bool:
            return self.stopped

    stop = StopEvent()

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        stop.stopped = True

    scheduler = RedisDispatchWorkerScheduler(worker, interval_seconds=2, sleep=sleep)
    cycles = await scheduler.run(stop, _complete_handler)

    assert len(cycles) == 1
    assert cycles[0].entries[0].decision is WorkerEntryDecision.ACKNOWLEDGED
    assert sleeps == [2.0]


def test_worker_scheduler_rejects_invalid_configuration() -> None:
    worker = RedisDispatchWorker(
        RedisDispatchTransport(FakeRedis()),
        queue_name="backtest",
        group_name="workers",
        consumer_name="worker-1",
    )
    async def sleep(_: float) -> None:
        return None

    with pytest.raises(ValueError, match="interval_seconds"):
        RedisDispatchWorkerScheduler(worker, interval_seconds=0, sleep=sleep)


def test_handler_result_requires_terminal_receipt_or_reason() -> None:
    with pytest.raises(ValueError, match="receipt digest"):
        WorkerHandleResult(content_digest("entry"), WorkerHandleDecision.COMPLETE)
    with pytest.raises(ValueError, match="reason"):
        WorkerHandleResult(content_digest("entry"), WorkerHandleDecision.RETRY)
    with pytest.raises(ValueError, match="cannot contain a receipt"):
        WorkerHandleResult(
            content_digest("entry"),
            WorkerHandleDecision.RETRY,
            content_digest("receipt"),
            "retry later",
        )
