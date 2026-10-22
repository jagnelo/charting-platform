from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.outbox import OutboxMessage, OutboxState, resolve_outbox_enqueue
from app.strategy_lab_v2.outbox_relay import (
    OutboxRelayDecision,
    build_outbox_dispatch_envelope,
    relay_outbox_message,
)
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport

NOW = datetime(2024, 1, 1, tzinfo=UTC)


class FakeRedis:
    def __init__(self, result=1) -> None:
        self.result = result
        self.calls: list[tuple] = []

    async def eval(self, *args):
        self.calls.append(args)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def xgroup_create(self, **kwargs):
        return None

    async def xreadgroup(self, **kwargs):
        return None

    async def xautoclaim(self, **kwargs):
        return None

    async def xack(self, *args):
        return 1


def _message(value: str = "one") -> OutboxMessage:
    return OutboxMessage(
        content_digest("request"),
        "run_attempt",
        "attempt-1",
        content_digest("event-1"),
        "strategy-lab.events",
        content_digest({"value": value}),
        NOW,
        NOW,
    )


def _state(message: OutboxMessage) -> OutboxState:
    return resolve_outbox_enqueue(OutboxState(), message).state


def test_outbox_envelope_uses_content_identity_as_transport_idempotency_key() -> None:
    message = _message()
    envelope = build_outbox_dispatch_envelope(message)
    assert envelope.request.idempotency_key == message.message_id
    assert envelope.request.attempt_id == message.event_id
    assert envelope.request.payload_digest == message.payload_digest
    assert envelope.request.queue_name == message.topic


@pytest.mark.asyncio
async def test_successful_enqueue_proposes_published_outbox_state() -> None:
    message = _message()
    state = _state(message)
    redis = FakeRedis(1)
    result = await relay_outbox_message(state, message, RedisDispatchTransport(redis))
    assert result.decision is OutboxRelayDecision.PUBLISHED
    assert result.transport is not None
    assert result.transport.decision.value == "enqueued"
    assert result.state.published_message_ids == frozenset({message.message_id})
    assert result.state.pending_messages == ()


@pytest.mark.asyncio
async def test_transport_replay_recovers_crash_before_outbox_ack() -> None:
    message = _message()
    state = _state(message)
    result = await relay_outbox_message(
        state, message, RedisDispatchTransport(FakeRedis(0))
    )
    assert result.decision is OutboxRelayDecision.REPLAY_EXISTING
    assert result.state.published_message_ids == frozenset({message.message_id})


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [-1, -2, "bad"])
async def test_conflict_or_transport_failure_preserves_pending_state(code) -> None:
    message = _message()
    state = _state(message)
    result = await relay_outbox_message(
        state, message, RedisDispatchTransport(FakeRedis(code))
    )
    assert result.decision in {OutboxRelayDecision.CONFLICT, OutboxRelayDecision.REJECT}
    assert result.state == state
    assert message.message_id in {item.message_id for item in result.state.pending_messages}
    assert result.rejection_reason


@pytest.mark.asyncio
async def test_exact_relay_retry_replays_without_transport_call() -> None:
    message = _message()
    state = _state(message)
    first = await relay_outbox_message(
        state, message, RedisDispatchTransport(FakeRedis(1))
    )
    redis = FakeRedis(RuntimeError("must not be called"))
    replay = await relay_outbox_message(
        first.state, message, RedisDispatchTransport(redis)
    )
    assert replay.decision is OutboxRelayDecision.REPLAY_EXISTING
    assert replay.state == first.state
    assert redis.calls == []


@pytest.mark.asyncio
async def test_unknown_message_and_invalid_arguments_fail_closed() -> None:
    message = _message()
    result = await relay_outbox_message(
        OutboxState(), message, RedisDispatchTransport(FakeRedis())
    )
    assert result.decision is OutboxRelayDecision.REJECT
    assert "not present" in (result.rejection_reason or "")
    with pytest.raises(TypeError, match="transport"):
        await relay_outbox_message(_state(message), message, "bad")  # type: ignore[arg-type]
