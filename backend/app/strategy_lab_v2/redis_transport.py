"""Redis Streams transport for idempotent Strategy Lab dispatch envelopes.

PostgreSQL remains authoritative for state and the transactional outbox. This
adapter only publishes a content-addressed dispatch envelope to a Redis Stream.
The Lua script records the idempotency key and stream entry atomically, so a
retry cannot publish a second message or leave an idempotency marker behind
when ``XADD`` fails.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.dispatch import DispatchEnvelope


class AsyncRedisClient(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> Any: ...

    async def xgroup_create(self, **kwargs: Any) -> Any: ...

    async def xreadgroup(self, **kwargs: Any) -> Any: ...

    async def xautoclaim(self, **kwargs: Any) -> Any: ...

    async def xack(self, *args: str) -> Any: ...


class RedisTransportDecision(StrEnum):
    ENQUEUED = "enqueued"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


class RedisGroupDecision(StrEnum):
    CREATED = "created"
    EXISTING = "existing"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class RedisGroupResolution:
    decision: RedisGroupDecision
    stream_key: str
    group_name: str
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RedisGroupDecision):
            raise TypeError("decision must be a RedisGroupDecision")
        if not self.stream_key.strip() or not self.group_name.strip():
            raise ValueError("stream_key and group_name must not be empty")
        if self.decision is RedisGroupDecision.REJECT and not self.rejection_reason:
            raise ValueError("rejected group resolutions require a reason")
        if self.decision is not RedisGroupDecision.REJECT and self.rejection_reason:
            raise ValueError("successful group resolutions cannot contain a reason")


@dataclass(frozen=True, slots=True)
class RedisStreamEntry:
    """Decoded dispatch fields delivered from a Redis Stream."""

    stream_key: str
    stream_id: str
    message_id: str
    attempt_id: str
    payload_digest: str
    request_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("stream_key", "stream_id", "attempt_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        for name in ("message_id", "payload_digest", "request_fingerprint"):
            require_sha256_digest(getattr(self, name), field_name=name)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class RedisAckResolution:
    stream_key: str
    group_name: str
    stream_id: str
    acknowledged: bool
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("stream_key", "group_name", "stream_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.acknowledged, bool):
            raise TypeError("acknowledged must be a boolean")
        if self.acknowledged and self.rejection_reason:
            raise ValueError("acknowledged entries cannot contain a rejection reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


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

    def __init__(self, redis: AsyncRedisClient, *, namespace: str = "strategy-lab:v2") -> None:
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

    @staticmethod
    def _group_name(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("group_name must not be empty")
        if any(character in value for character in "\x00\r\n"):
            raise ValueError("group_name must not contain control characters")
        return value

    @staticmethod
    def _consumer_name(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("consumer_name must not be empty")
        if any(character in value for character in "\x00\r\n"):
            raise ValueError("consumer_name must not contain control characters")
        return value

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

    async def ensure_group(
        self,
        queue_name: str,
        group_name: str,
        *,
        start_id: str = "0",
    ) -> RedisGroupResolution:
        """Create a consumer group idempotently, materializing the stream if needed."""

        stream_key = self.stream_key(queue_name)
        group = self._group_name(group_name)
        if not isinstance(start_id, str) or not start_id.strip():
            raise ValueError("start_id must not be empty")
        try:
            await self._redis.xgroup_create(
                name=stream_key,
                groupname=group,
                id=start_id,
                mkstream=True,
            )
        except Exception as error:  # pragma: no cover - client-specific exception
            if "BUSYGROUP" in str(error).upper():
                return RedisGroupResolution(RedisGroupDecision.EXISTING, stream_key, group)
            return RedisGroupResolution(
                RedisGroupDecision.REJECT,
                stream_key,
                group,
                f"Redis consumer-group creation failed: {type(error).__name__}",
            )
        return RedisGroupResolution(RedisGroupDecision.CREATED, stream_key, group)

    async def read_group(
        self,
        queue_name: str,
        group_name: str,
        consumer_name: str,
        *,
        count: int = 1,
        block_ms: int = 0,
    ) -> tuple[RedisStreamEntry, ...]:
        """Read new entries for one consumer group and decode required fields."""

        stream_key = self.stream_key(queue_name)
        group = self._group_name(group_name)
        consumer = self._consumer_name(consumer_name)
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError("count must be a positive integer")
        if not isinstance(block_ms, int) or isinstance(block_ms, bool) or block_ms < 0:
            raise ValueError("block_ms must be a non-negative integer")
        raw = await self._redis.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream_key: ">"},
            count=count,
            block=block_ms,
        )
        return self._decode_entries(stream_key, raw)

    async def reclaim_pending(
        self,
        queue_name: str,
        group_name: str,
        consumer_name: str,
        *,
        min_idle_ms: int,
        start_id: str = "0-0",
        count: int = 1,
    ) -> tuple[RedisStreamEntry, ...]:
        """Claim idle pending entries after a worker restart or lease expiry."""

        stream_key = self.stream_key(queue_name)
        group = self._group_name(group_name)
        consumer = self._consumer_name(consumer_name)
        if not isinstance(min_idle_ms, int) or isinstance(min_idle_ms, bool) or min_idle_ms < 0:
            raise ValueError("min_idle_ms must be a non-negative integer")
        if not isinstance(start_id, str) or not start_id.strip():
            raise ValueError("start_id must not be empty")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError("count must be a positive integer")
        raw = await self._redis.xautoclaim(
            name=stream_key,
            groupname=group,
            consumername=consumer,
            min_idle_time=min_idle_ms,
            start_id=start_id,
            count=count,
        )
        entries = raw[1] if isinstance(raw, Sequence) and len(raw) >= 2 else ()
        return self._decode_entry_items(stream_key, entries)

    async def acknowledge(
        self,
        queue_name: str,
        group_name: str,
        stream_id: str,
    ) -> RedisAckResolution:
        """Acknowledge one delivered entry without mutating authoritative state."""

        stream_key = self.stream_key(queue_name)
        group = self._group_name(group_name)
        if not isinstance(stream_id, str) or not stream_id.strip():
            raise ValueError("stream_id must not be empty")
        try:
            result = await self._redis.xack(stream_key, group, stream_id)
        except Exception as error:  # pragma: no cover - client-specific exception
            return RedisAckResolution(
                stream_key,
                group,
                stream_id,
                False,
                f"Redis acknowledgement failed: {type(error).__name__}",
            )
        try:
            count = int(result)
        except (TypeError, ValueError):
            return RedisAckResolution(
                stream_key, group, stream_id, False, "Redis acknowledgement returned an invalid result"
            )
        return RedisAckResolution(stream_key, group, stream_id, count == 1)

    @classmethod
    def _decode_entries(cls, stream_key: str, raw: Any) -> tuple[RedisStreamEntry, ...]:
        if raw is None:
            return ()
        if not isinstance(raw, Sequence):
            raise ValueError("Redis stream response is malformed")
        decoded: list[RedisStreamEntry] = []
        for stream_name, entries in raw:
            del stream_name
            decoded.extend(cls._decode_entry_items(stream_key, entries))
        return tuple(decoded)

    @staticmethod
    def _decode_entry_items(stream_key: str, entries: Any) -> tuple[RedisStreamEntry, ...]:
        if entries is None:
            return ()
        if not isinstance(entries, Sequence):
            raise ValueError("Redis stream entries are malformed")
        decoded: list[RedisStreamEntry] = []
        for stream_id, values in entries:
            if isinstance(stream_id, bytes):
                stream_id = stream_id.decode("utf-8")
            if not isinstance(stream_id, str) or not isinstance(values, Mapping):
                raise ValueError("Redis stream entry fields are malformed")
            normalized: dict[str, str] = {}
            for key, value in values.items():
                if isinstance(key, bytes):
                    key = key.decode("utf-8")
                if isinstance(value, bytes):
                    value = value.decode("utf-8")
                if not isinstance(key, str) or not isinstance(value, str):
                    raise ValueError("Redis stream entry fields must be text")
                normalized[key] = value
            required = {"message_id", "attempt_id", "payload_digest", "request_fingerprint"}
            if set(normalized) != required:
                raise ValueError("Redis stream entry fields are incomplete")
            decoded.append(
                RedisStreamEntry(
                    stream_key,
                    stream_id,
                    normalized["message_id"],
                    normalized["attempt_id"],
                    normalized["payload_digest"],
                    normalized["request_fingerprint"],
                )
            )
        return tuple(decoded)
