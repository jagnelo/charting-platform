from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import DispatchRequest, build_dispatch_envelope
from app.strategy_lab_v2.redis_transport import (
    RedisDispatchTransport,
    RedisTransportDecision,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


class FakeRedis:
    def __init__(self, result=1, *, stream_response=None, claim_response=None, ack_result=1) -> None:
        self.result = result
        self.stream_response = stream_response
        self.claim_response = claim_response
        self.ack_result = ack_result
        self.calls: list[tuple] = []

    async def eval(self, *args):
        self.calls.append(args)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def xgroup_create(self, **kwargs):
        self.calls.append(("xgroup_create", kwargs))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def xreadgroup(self, **kwargs):
        self.calls.append(("xreadgroup", kwargs))
        return self.stream_response

    async def xautoclaim(self, **kwargs):
        self.calls.append(("xautoclaim", kwargs))
        return self.claim_response

    async def xack(self, *args):
        self.calls.append(("xack", args))
        if isinstance(self.result, Exception):
            raise self.result
        return self.ack_result


def _envelope(*, key: str = "dispatch-1"):
    request = DispatchRequest(
        key,
        "attempt-1",
        content_digest("payload"),
        "backtest",
        NOW,
    )
    return build_dispatch_envelope(request)


@pytest.mark.asyncio
async def test_enqueue_uses_atomic_lua_and_returns_enqueued() -> None:
    redis = FakeRedis(1)
    transport = RedisDispatchTransport(redis)
    envelope = _envelope()
    result = await transport.enqueue(envelope)
    assert result.decision is RedisTransportDecision.ENQUEUED
    assert result.stream_key == "strategy-lab:v2:stream:backtest"
    assert result.fingerprint.startswith("sha256:")
    assert len(redis.calls) == 1
    script, key_count, idempotency_key, stream_key, *args = redis.calls[0]
    assert key_count == 2
    assert idempotency_key == "strategy-lab:v2:idempotency"
    assert stream_key == result.stream_key
    assert args == [
        envelope.request.idempotency_key,
        envelope.message_id,
        envelope.request.attempt_id,
        envelope.request.payload_digest,
        envelope.request.fingerprint,
    ]
    assert "XADD" in script and "HDEL" in script


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "decision"),
    [
        (0, RedisTransportDecision.REPLAY_EXISTING),
        (-1, RedisTransportDecision.CONFLICT),
        (-2, RedisTransportDecision.REJECT),
    ],
)
async def test_enqueue_maps_lua_idempotency_outcomes(code, decision) -> None:
    result = await RedisDispatchTransport(FakeRedis(code)).enqueue(_envelope())
    assert result.decision is decision
    if decision in {RedisTransportDecision.CONFLICT, RedisTransportDecision.REJECT}:
        assert result.rejection_reason


@pytest.mark.asyncio
async def test_redis_errors_and_invalid_results_fail_closed() -> None:
    error = await RedisDispatchTransport(FakeRedis(RuntimeError("down"))).enqueue(_envelope())
    assert error.decision is RedisTransportDecision.REJECT
    assert "RuntimeError" in (error.rejection_reason or "")
    invalid = await RedisDispatchTransport(FakeRedis("unexpected")).enqueue(_envelope())
    assert invalid.decision is RedisTransportDecision.REJECT
    with pytest.raises(TypeError, match="envelope"):
        await RedisDispatchTransport(FakeRedis()).enqueue("bad")  # type: ignore[arg-type]


def test_transport_keys_and_namespace_are_validated() -> None:
    with pytest.raises(ValueError, match="namespace"):
        RedisDispatchTransport(FakeRedis(), namespace="\n")
    transport = RedisDispatchTransport(FakeRedis())
    with pytest.raises(ValueError, match="queue_name"):
        transport.stream_key("")
    with pytest.raises(ValueError, match="control"):
        transport.stream_key("bad\nqueue")


@pytest.mark.asyncio
async def test_consumer_group_creation_is_idempotent_and_decodes_entries() -> None:
    fields = {
        b"message_id": _envelope().message_id.encode(),
        b"attempt_id": b"attempt-1",
        b"payload_digest": content_digest("payload").encode(),
        b"request_fingerprint": _envelope().request.fingerprint.encode(),
    }
    redis = FakeRedis(
        stream_response=[(b"strategy-lab:v2:stream:backtest", [(b"1-0", fields)])],
        claim_response=[b"2-0", [(b"1-1", fields)], []],
    )
    transport = RedisDispatchTransport(redis)
    created = await transport.ensure_group("backtest", "workers")
    assert created.decision.value == "created"
    entries = await transport.read_group("backtest", "workers", "worker-1")
    assert len(entries) == 1
    assert entries[0].message_id == _envelope().message_id
    assert entries[0].stream_id == "1-0"
    reclaimed = await transport.reclaim_pending(
        "backtest", "workers", "worker-1", min_idle_ms=1000
    )
    assert reclaimed[0].stream_id == "1-1"
    ack = await transport.acknowledge("backtest", "workers", "1-0")
    assert ack.acknowledged


@pytest.mark.asyncio
async def test_group_busy_and_acknowledgement_failures_are_typed() -> None:
    existing = await RedisDispatchTransport(
        FakeRedis(RuntimeError("BUSYGROUP Consumer Group name already exists"))
    ).ensure_group("backtest", "workers")
    assert existing.decision.value == "existing"
    failed = await RedisDispatchTransport(FakeRedis(RuntimeError("down"))).acknowledge(
        "backtest", "workers", "1-0"
    )
    assert not failed.acknowledged
    assert failed.rejection_reason
    not_ack = await RedisDispatchTransport(FakeRedis(ack_result=0)).acknowledge(
        "backtest", "workers", "1-0"
    )
    assert not not_ack.acknowledged


@pytest.mark.asyncio
async def test_malformed_stream_response_fails_closed() -> None:
    transport = RedisDispatchTransport(
        FakeRedis(stream_response=[("stream", [("1-0", {"missing": "field"})])])
    )
    with pytest.raises(ValueError, match="incomplete"):
        await transport.read_group("backtest", "workers", "worker-1")
