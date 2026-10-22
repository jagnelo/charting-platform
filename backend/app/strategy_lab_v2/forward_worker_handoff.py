"""Authenticated worker handoff for broker-free forward-event dispatches.

Redis carries only dispatch identities.  The worker first rehydrates the
owner-scoped PostgreSQL dispatch row and then authenticates the content-
addressed payload before a host-owned event-stream adapter resolves the
canonical event bytes.  This keeps event acquisition outside the transport
and prevents a forged stream entry from selecting another forward instance.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.postgres_forward_dispatch import (
    ForwardEventDispatchRecord,
)
from app.strategy_lab_v2.redis_transport import RedisStreamEntry


class ForwardDispatchRecordLoader(Protocol):
    """Worker-facing lookup contract for durable forward dispatch identities."""

    async def load_by_request_fingerprint(
        self, request_fingerprint: str
    ) -> ForwardEventDispatchRecord | None: ...


@dataclass(frozen=True, slots=True)
class ForwardEventDispatchPayload:
    """Authenticated payload identity for one canonical forward event."""

    event_fingerprint: str
    replay_plan_fingerprint: str | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.event_fingerprint, field_name="event_fingerprint")
        if self.replay_plan_fingerprint is not None:
            require_sha256_digest(
                self.replay_plan_fingerprint,
                field_name="replay_plan_fingerprint",
            )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    @classmethod
    def from_payload(cls, payload: DispatchPayload) -> ForwardEventDispatchPayload:
        if not isinstance(payload, DispatchPayload):
            raise TypeError("payload must be a DispatchPayload")
        value = payload.value
        if set(value) != {"event_fingerprint", "replay_plan_fingerprint"}:
            raise ValueError("forward event payload fields are invalid")
        event_fingerprint = value["event_fingerprint"]
        replay_plan_fingerprint = value["replay_plan_fingerprint"]
        if not isinstance(event_fingerprint, str):
            raise ValueError("forward event fingerprint is malformed")
        if replay_plan_fingerprint is not None and not isinstance(
            replay_plan_fingerprint, str
        ):
            raise ValueError("forward replay-plan fingerprint is malformed")
        parsed = cls(event_fingerprint, replay_plan_fingerprint)
        if payload.payload_digest != content_digest(
            {
                "event_fingerprint": parsed.event_fingerprint,
                "replay_plan_fingerprint": parsed.replay_plan_fingerprint,
            }
        ):
            raise ValueError("forward event payload identity drifted")
        return parsed


@dataclass(frozen=True, slots=True)
class ForwardEventWorkItem:
    """Authenticated transport handoff awaiting host event-stream resolution."""

    dispatch: ForwardEventDispatchRecord
    payload: ForwardEventDispatchPayload

    def __post_init__(self) -> None:
        if not isinstance(self.dispatch, ForwardEventDispatchRecord):
            raise TypeError("dispatch must be a ForwardEventDispatchRecord")
        if not isinstance(self.payload, ForwardEventDispatchPayload):
            raise TypeError("payload must be a ForwardEventDispatchPayload")
        if self.dispatch.event_fingerprint != self.payload.event_fingerprint:
            raise ValueError("forward dispatch event identity does not match payload")
        if self.dispatch.replay_plan_fingerprint != self.payload.replay_plan_fingerprint:
            raise ValueError("forward dispatch replay identity does not match payload")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


ForwardEventHandoffDecoder = Callable[
    [RedisStreamEntry, DispatchPayload, ForwardEventDispatchRecord],
    Awaitable[ForwardEventWorkItem] | ForwardEventWorkItem,
]


class AuthenticatedForwardEventDispatchMaterializer:
    """Bind one Redis entry to its authenticated PostgreSQL forward dispatch."""

    def __init__(
        self,
        dispatch_store: ForwardDispatchRecordLoader,
        *,
        queue_name: str,
        decoder: ForwardEventHandoffDecoder | None = None,
    ) -> None:
        if not callable(getattr(dispatch_store, "load_by_request_fingerprint", None)):
            raise TypeError(
                "dispatch_store must expose an async load_by_request_fingerprint method"
            )
        if not isinstance(queue_name, str) or not queue_name.strip():
            raise ValueError("queue_name must not be empty")
        if any(character in queue_name for character in "\x00\r\n"):
            raise ValueError("queue_name must not contain control characters")
        if decoder is not None and not callable(decoder):
            raise TypeError("decoder must be callable")
        self._dispatch_store = dispatch_store
        self._queue_name = queue_name.strip()
        self._decoder = decoder or materialize_forward_event_handoff

    @property
    def dispatch_store(self) -> ForwardDispatchRecordLoader:
        return self._dispatch_store

    @property
    def queue_name(self) -> str:
        return self._queue_name

    async def __call__(
        self, entry: RedisStreamEntry, payload: DispatchPayload
    ) -> ForwardEventWorkItem:
        if not isinstance(entry, RedisStreamEntry):
            raise TypeError("entry must be a RedisStreamEntry")
        if not isinstance(payload, DispatchPayload):
            raise TypeError("payload must be a DispatchPayload")
        record = await self._dispatch_store.load_by_request_fingerprint(
            entry.request_fingerprint
        )
        if record is None:
            raise ValueError("forward dispatch record is not available")
        if not isinstance(record, ForwardEventDispatchRecord):
            raise TypeError("dispatch store returned an invalid forward dispatch record")
        request = record.request
        if request.fingerprint != entry.request_fingerprint:
            raise ValueError("Redis request identity does not match PostgreSQL dispatch")
        if request.attempt_id != entry.attempt_id:
            raise ValueError("Redis forward instance identity does not match PostgreSQL dispatch")
        if request.payload_digest != entry.payload_digest:
            raise ValueError("Redis payload identity does not match PostgreSQL dispatch")
        if request.payload_digest != payload.payload_digest:
            raise ValueError("materialized payload identity does not match PostgreSQL dispatch")
        if request.queue_name != self._queue_name:
            raise ValueError("Redis queue identity does not match PostgreSQL dispatch")
        resolved = self._decoder(entry, payload, record)
        work_item = await resolved if isinstance(resolved, Awaitable) else resolved
        if not isinstance(work_item, ForwardEventWorkItem):
            raise TypeError("forward event handoff decoder returned an invalid work item")
        return work_item


def materialize_forward_event_handoff(
    _entry: RedisStreamEntry,
    payload: DispatchPayload,
    record: ForwardEventDispatchRecord,
) -> ForwardEventWorkItem:
    """Decode the authenticated payload without acquiring event data."""

    return ForwardEventWorkItem(record, ForwardEventDispatchPayload.from_payload(payload))


def create_authenticated_forward_event_materializer(
    dispatch_store: ForwardDispatchRecordLoader,
    *,
    queue_name: str,
    decoder: ForwardEventHandoffDecoder | None = None,
) -> AuthenticatedForwardEventDispatchMaterializer:
    """Create the explicit worker callback for forward-event queues."""

    return AuthenticatedForwardEventDispatchMaterializer(
        dispatch_store,
        queue_name=queue_name,
        decoder=decoder,
    )


__all__ = [
    "AuthenticatedForwardEventDispatchMaterializer",
    "ForwardDispatchRecordLoader",
    "ForwardEventDispatchPayload",
    "ForwardEventHandoffDecoder",
    "ForwardEventWorkItem",
    "create_authenticated_forward_event_materializer",
    "materialize_forward_event_handoff",
]
