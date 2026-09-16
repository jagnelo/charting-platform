"""Redis Streams transport for idempotent Strategy Lab dispatch envelopes.

PostgreSQL remains authoritative for state and the transactional outbox. This
adapter only publishes a content-addressed dispatch envelope to a Redis Stream.
The Lua script records the idempotency key and stream entry atomically, so a
retry cannot publish a second message or leave an idempotency marker behind
when ``XADD`` fails.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.dispatch import DispatchEnvelope


class AsyncRedisEval(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> Any: ...


class RedisTransportDecision(StrEnum):
    ENQUEUED = "enqueued"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class RedisTransportResolution:
    """Typed result of one Redis Stream publication attempt."""

    decision: RedisTransportDecision
    message_id: str
    request_fingerprint: str
    stream_key: str
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RedisTransportDecision):
            raise TypeError("decision must be a RedisTransportDecision")
        require_sha256_digest(self.message_id, field_name="message_id")
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        if not isinstance(self.stream_key, str) or not self.stream_key.strip():
            raise ValueError("stream_key must not be empty")
        if self.decision in {
            RedisTransportDecision.CONFLICT,
            RedisTransportDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("failed Redis resolutions require a reason")
        if self.decision in {
            RedisTransportDecision.ENQUEUED,
            RedisTransportDecision.REPLAY_EXISTING,
        } and self.rejection_reason:
            raise ValueError("successful Redis resolutions cannot contain a reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


_ENQUEUE_SCRIPT = """
local existing = redis.call('HGET', KEYS[1], ARGV[1])
if existing then
  if existing == ARGV[2] then
    return 0
  end
  return -1
end
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
local ok = pcall(redis.call, 'XADD', KEYS[2], '*',
  'message_id', ARGV[2],
  'attempt_id', ARGV[3],
  'payload_digest', ARGV[4],
  'request_fingerprint', ARGV[5])
if not ok then
  redis.call('HDEL', KEYS[1], ARGV[1])
  return -2
end
return 1
"""


class RedisDispatchTransport:
    """Minimal Redis Streams publisher for already-authorized envelopes."""

    def __init__(self, redis: AsyncRedisEval, *, namespace: str = "strategy-lab:v2") -> None:
        if not isinstance(namespace, str) or not namespace.strip():
            raise ValueError("Redis transport namespace must not be empty")
        if any(character in namespace for character in "\x00\r\n"):
            raise ValueError("Redis transport namespace must not contain control characters")
        self._redis = redis
        self._namespace = namespace.rstrip(":")

    def stream_key(self, queue_name: str) -> str:
        if not isinstance(queue_name, str) or not queue_name.strip():
            raise ValueError("queue_name must not be empty")
        if any(character in queue_name for character in "\x00\r\n"):
            raise ValueError("queue_name must not contain control characters")
        return f"{self._namespace}:stream:{queue_name}"

    async def enqueue(self, envelope: DispatchEnvelope) -> RedisTransportResolution:
        """Atomically enqueue/replay/conflict one envelope in Redis."""

        if not isinstance(envelope, DispatchEnvelope):
            raise TypeError("envelope must be a DispatchEnvelope")
        stream_key = self.stream_key(envelope.request.queue_name)
        idempotency_key = f"{self._namespace}:idempotency"
        try:
            result = await self._redis.eval(
                _ENQUEUE_SCRIPT,
                2,
                idempotency_key,
                stream_key,
                envelope.request.idempotency_key,
                envelope.message_id,
                envelope.request.attempt_id,
                envelope.request.payload_digest,
                envelope.request.fingerprint,
            )
        except Exception as error:  # pragma: no cover - adapter boundary
            return RedisTransportResolution(
                RedisTransportDecision.REJECT,
                envelope.message_id,
                envelope.request.fingerprint,
                stream_key,
                f"Redis enqueue failed: {type(error).__name__}",
            )
        try:
            code = int(result)
        except (TypeError, ValueError):
            return RedisTransportResolution(
                RedisTransportDecision.REJECT,
                envelope.message_id,
                envelope.request.fingerprint,
                stream_key,
                "Redis enqueue returned an invalid result",
            )
        if code == 1:
            return RedisTransportResolution(
                RedisTransportDecision.ENQUEUED,
                envelope.message_id,
                envelope.request.fingerprint,
                stream_key,
            )
        if code == 0:
            return RedisTransportResolution(
                RedisTransportDecision.REPLAY_EXISTING,
                envelope.message_id,
                envelope.request.fingerprint,
                stream_key,
            )
        if code == -1:
            return RedisTransportResolution(
                RedisTransportDecision.CONFLICT,
                envelope.message_id,
                envelope.request.fingerprint,
                stream_key,
                "Redis idempotency key is already bound to different content",
            )
        return RedisTransportResolution(
            RedisTransportDecision.REJECT,
            envelope.message_id,
            envelope.request.fingerprint,
            stream_key,
            "Redis could not atomically append the dispatch envelope",
        )
