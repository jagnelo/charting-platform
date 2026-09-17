from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.outbox import (
    OutboxAcknowledgeDecision,
    OutboxAcknowledgeResolution,
    OutboxMessage,
    OutboxState,
    acknowledge_outbox_message,
)
from app.strategy_lab_v2.outbox_application import OutboxRelayScheduler, OutboxRelayService
from app.strategy_lab_v2.redis_application import RedisDispatchRuntime
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


class FakeRedis:
    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> int:
        del script, numkeys, keys_and_args
        return 1


class MemoryOutbox:
    def __init__(self, state: OutboxState, *, reject_acknowledgement: bool = False) -> None:
        self.state = state
        self.reject_acknowledgement = reject_acknowledgement
        self.acknowledgement_calls: list[tuple[str, str]] = []

    async def load_outbox(self) -> OutboxState:
        return self.state

    async def acknowledge_outbox(
        self,
        message_id: str,
        *,
        expected_state_fingerprint: str,
    ) -> OutboxAcknowledgeResolution:
        self.acknowledgement_calls.append((message_id, expected_state_fingerprint))
        if self.reject_acknowledgement:
            return OutboxAcknowledgeResolution(
                OutboxAcknowledgeDecision.REJECT,
                self.state,
                message_id,
                "simulated compare-and-set rejection",
            )
        if expected_state_fingerprint != self.state.fingerprint:
            return OutboxAcknowledgeResolution(
                OutboxAcknowledgeDecision.REJECT,
                self.state,
                message_id,
                "stale outbox state",
            )
        resolution = acknowledge_outbox_message(self.state, message_id)
        self.state = resolution.state
        return resolution


class CloseableRedis(FakeRedis):
    def __init__(self) -> None:
        self.close_calls = 0

    async def aclose(self) -> None:
        self.close_calls += 1


def _message(label: str, *, available_at: datetime = NOW) -> OutboxMessage:
    return OutboxMessage(
        content_digest({"request": label}),
        "attempt",
        f"attempt-{label}",
        content_digest({"event": label}),
        "strategy-lab.execution",
        content_digest({"payload": label}),
        NOW,
        available_at,
    )


@pytest.mark.asyncio
async def test_relay_pending_publishes_available_messages_and_persists_acknowledgement() -> None:
    available = _message("available")
    future = _message("future", available_at=NOW + timedelta(minutes=5))
    persistence = MemoryOutbox(OutboxState(tuple(sorted((available, future), key=lambda item: item.message_id))))
    service = OutboxRelayService(
        persistence,
        RedisDispatchTransport(cast(Any, FakeRedis())),
    )

    results = await service.relay_pending(now=NOW)

    assert len(results) == 1
    assert results[0].decision.value == "published"
    assert persistence.state.published_message_ids == frozenset({available.message_id})
    assert persistence.acknowledgement_calls == [
        (available.message_id, OutboxState(tuple(sorted((available, future), key=lambda item: item.message_id))).fingerprint)
    ]
    assert await service.relay_pending(now=NOW) == ()


@pytest.mark.asyncio
async def test_relay_pending_preserves_retryable_state_when_acknowledgement_rejected() -> None:
    message = _message("cas")
    persistence = MemoryOutbox(OutboxState((message,)), reject_acknowledgement=True)
    service = OutboxRelayService(
        persistence,
        RedisDispatchTransport(cast(Any, FakeRedis())),
    )

    results = await service.relay_pending(now=NOW)

    assert len(results) == 1
    assert results[0].decision.value == "conflict"
    assert persistence.state.pending_messages == (message,)


@pytest.mark.asyncio
async def test_relay_scheduler_runs_bounded_cycles_until_cancelled() -> None:
    message = _message("scheduled")
    persistence = MemoryOutbox(OutboxState((message,)))
    service = OutboxRelayService(
        persistence,
        RedisDispatchTransport(cast(Any, FakeRedis())),
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

    scheduler = OutboxRelayScheduler(
        service,
        clock=lambda: NOW,
        interval_seconds=2,
        limit=1,
        sleep=sleep,
    )
    await scheduler.run(stop)

    assert sleeps == [2.0]
    assert persistence.state.published_message_ids == frozenset({message.message_id})


def test_relay_scheduler_rejects_invalid_configuration() -> None:
    service = OutboxRelayService(
        MemoryOutbox(OutboxState()),
        RedisDispatchTransport(cast(Any, FakeRedis())),
    )
    with pytest.raises(ValueError, match="interval_seconds"):
        OutboxRelayScheduler(service, clock=lambda: NOW, interval_seconds=0)


@pytest.mark.asyncio
async def test_redis_runtime_composes_transport_relay_and_closes_once() -> None:
    client = CloseableRedis()
    runtime = RedisDispatchRuntime(client, RedisDispatchTransport(cast(Any, client)))
    relay = runtime.outbox_relay(MemoryOutbox(OutboxState()))
    worker = runtime.worker(
        queue_name="backtest",
        group_name="workers",
        consumer_name="worker-1",
    )

    assert isinstance(relay, OutboxRelayService)
    assert worker._queue_name == "backtest"
    await runtime.aclose()
    await runtime.aclose()
    assert client.close_calls == 1


def test_redis_runtime_requires_closeable_client() -> None:
    with pytest.raises(TypeError, match="aclose"):
        RedisDispatchRuntime(object(), RedisDispatchTransport(cast(Any, FakeRedis())))
