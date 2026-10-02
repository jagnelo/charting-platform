"""Atomic PostgreSQL staging for broker-free forward-event dispatches.

Forward admission and counterfactual replay remain owned by the existing
forward-state adapter.  This adapter adds the transport boundary: authenticated
payload bytes, idempotent dispatch identity, and the shared transactional
outbox are committed only after the pure forward-event dispatch resolver
accepts the event.  Worker authorization/capacity is intentionally supplied by
the host before this boundary is called.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.forward_corrections import ForwardCorrectionCommand
from app.strategy_lab_v2.forward_event_dispatch import (
    ForwardEventDispatchDecision,
    ForwardEventDispatchResolution,
    resolve_forward_event_dispatch,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent, ForwardEventObservation
from app.strategy_lab_v2.outbox import OutboxMessage
from app.strategy_lab_v2.postgres_forward_state import (
    PostgresForwardStateAdapter,
    _principal_id,
    _replay_id,
    _statement,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class PostgresForwardEventDispatchSchema:
    """Additive table contract for forward dispatch identities."""

    dispatch_table: str = "strategy_lab_v2_forward_event_dispatches"
    payload_table: str = "strategy_lab_v2_dispatch_payloads"
    outbox_table: str = "strategy_lab_v2_execution_outbox"

    def __post_init__(self) -> None:
        for name, value in (
            ("dispatch_table", self.dispatch_table),
            ("payload_table", self.payload_table),
            ("outbox_table", self.outbox_table),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
                raise ValueError(f"{name} must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.dispatch_table} (
                owner_id TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                event_fingerprint TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                queue_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                replay_plan_fingerprint TEXT NULL,
                dispatch_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, idempotency_key),
                UNIQUE (owner_id, instance_id, event_fingerprint),
                UNIQUE (owner_id, request_fingerprint)
            )
            """,
        )


@dataclass(frozen=True, slots=True)
class ForwardEventDispatchRecord:
    owner_id: str
    instance_id: str
    event_fingerprint: str
    request: DispatchRequest
    replay_plan_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("owner_id must not be empty")
        if not isinstance(self.instance_id, str) or not self.instance_id.strip():
            raise ValueError("instance_id must not be empty")
        require_sha256_digest(self.event_fingerprint, field_name="event_fingerprint")
        if not isinstance(self.request, DispatchRequest):
            raise TypeError("request must be a DispatchRequest")
        if self.request.attempt_id != self.instance_id:
            raise ValueError("forward dispatch request must reference its instance")
        if self.replay_plan_fingerprint is not None:
            require_sha256_digest(
                self.replay_plan_fingerprint, field_name="replay_plan_fingerprint"
            )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class PostgresForwardEventDispatchAdapter:
    """Persist accepted forward events and their worker queue intent atomically."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresForwardEventDispatchSchema | None = None,
        forward_state: PostgresForwardStateAdapter | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresForwardEventDispatchSchema()
        self._forward_state = forward_state or PostgresForwardStateAdapter(session_factory)

    @property
    def schema(self) -> PostgresForwardEventDispatchSchema:
        return self._schema

    async def dispatch(
        self,
        *,
        principal: Any,
        instance_id: str,
        event: CanonicalForwardEvent,
        observation: ForwardEventObservation,
        dispatch_request: DispatchRequest,
        payload: Mapping[str, Any],
        correction_command: ForwardCorrectionCommand | None = None,
    ) -> ForwardEventDispatchResolution:
        """Resolve and persist one forward event, payload, dispatch, and outbox."""

        owner_id = _principal_id(principal)
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        if not isinstance(event, CanonicalForwardEvent):
            raise TypeError("event must be a CanonicalForwardEvent")
        if not isinstance(observation, ForwardEventObservation):
            raise TypeError("observation must be a ForwardEventObservation")
        if not isinstance(dispatch_request, DispatchRequest):
            raise TypeError("dispatch_request must be a DispatchRequest")
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        payload_record = DispatchPayload.from_mapping(payload)
        if payload_record.payload_digest != dispatch_request.payload_digest:
            raise ValueError("forward dispatch payload does not match its content digest")
        if correction_command is not None and not isinstance(
            correction_command, ForwardCorrectionCommand
        ):
            raise TypeError("correction_command must be a ForwardCorrectionCommand")

        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                state = await self._forward_state._load_live_state(session, owner_id, instance_id)
                if state is None:
                    raise ValueError("active forward instance was not found")
                prior_records = await self._load_dispatches(session, owner_id, instance_id)
                prior_dispatches = tuple(record.request for record in prior_records)
                existing_plan = None
                if correction_command is not None:
                    replay_id = _replay_id(state, correction_command)
                    plans = await self._forward_state._load_replays(session, owner_id, instance_id)
                    existing_plan = next((plan for plan in plans if plan.replay_id == replay_id), None)
                resolution = resolve_forward_event_dispatch(
                    state,
                    event,
                    observation,
                    dispatch_request=dispatch_request,
                    prior_dispatches=prior_dispatches,
                    correction_command=correction_command,
                    existing_replay_plan=existing_plan,
                )
                if resolution.decision in {
                    ForwardEventDispatchDecision.CONFLICT,
                    ForwardEventDispatchDecision.REJECT,
                    ForwardEventDispatchDecision.DUPLICATE,
                    ForwardEventDispatchDecision.OUT_OF_ORDER,
                    ForwardEventDispatchDecision.REPLAY_EXISTING,
                    ForwardEventDispatchDecision.CORRECTION_REPLAY,
                }:
                    return resolution
                if resolution.dispatch_resolution is None or resolution.envelope is None:
                    raise ValueError("forward dispatch resolution omitted dispatch evidence")
                prior_payload = await self._load_payload(session, payload_record.payload_digest)
                if prior_payload is not None and prior_payload != payload_record:
                    raise ValueError("forward dispatch payload identity is already bound to different content")
                if resolution.state != state:
                    await self._persist_state(session, owner_id, state, resolution)
                if prior_payload is None:
                    await self._insert_payload(session, payload_record)
                await self._insert_dispatch(
                    session,
                    owner_id,
                    instance_id,
                    resolution,
                )
                await self._insert_outbox(
                    session,
                    _forward_outbox_message(owner_id, instance_id, resolution),
                )
                return resolution

    async def load_by_request_fingerprint(
        self, request_fingerprint: str
    ) -> ForwardEventDispatchRecord | None:
        """Resolve one authenticated forward dispatch from Redis identity."""

        require_sha256_digest(request_fingerprint, field_name="request_fingerprint")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, instance_id, event_fingerprint, idempotency_key,
                               request_fingerprint, attempt_id, payload_digest, queue_name,
                               created_at, replay_plan_fingerprint, dispatch_fingerprint
                        FROM {self._schema.dispatch_table}
                        WHERE request_fingerprint = :request_fingerprint
                        ORDER BY owner_id ASC, instance_id ASC
                        FOR SHARE
                        """
                    ),
                    {"request_fingerprint": request_fingerprint},
                )
                rows = list(result.mappings())
                if len(rows) > 1:
                    raise ValueError("PostgreSQL forward dispatch identity is ambiguous")
                if not rows:
                    return None
                return _decode_dispatch_record(rows[0])

    async def load_payload(self, payload_digest: str) -> DispatchPayload | None:
        """Load one content-addressed forward dispatch payload for a worker.

        The Redis entry is authenticated against :meth:`load_by_request_fingerprint`
        before a forward worker consumes this payload.  Keeping the payload lookup
        on the same adapter prevents the forward entrypoint from reaching into a
        submission-owned table or inventing a second payload source.
        """

        require_sha256_digest(payload_digest, field_name="payload_digest")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_payload(session, payload_digest)

    async def _persist_state(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        current: Any,
        resolution: ForwardEventDispatchResolution,
    ) -> None:
        await self._forward_state._update_instance(
            session,
            owner_id,
            current.checkpoint,
            resolution.state.checkpoint.instance,
            checkpoint_override=resolution.state.checkpoint,
        )
        existing_ids = {item.event_id for item in current.seen_events}
        for item in resolution.state.seen_events:
            if item.event_id not in existing_ids:
                await self._forward_state._insert_seen_event(
                    session, owner_id, current.checkpoint.instance.instance_id, item
                )
        if (
            resolution.event_transaction.replay_plan is not None
            and resolution.event_transaction.replay_plan.fingerprint
            not in {item.fingerprint for item in await self._forward_state._load_replays(
                session, owner_id, current.checkpoint.instance.instance_id
            )}
        ):
            await self._forward_state._insert_replay(
                session, owner_id, resolution.event_transaction.replay_plan
            )

    async def _load_dispatches(
        self, session: AsyncSessionLike, owner_id: str, instance_id: str
    ) -> tuple[ForwardEventDispatchRecord, ...]:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, instance_id, event_fingerprint, idempotency_key,
                       request_fingerprint, attempt_id, payload_digest, queue_name,
                       created_at, replay_plan_fingerprint, dispatch_fingerprint
                FROM {self._schema.dispatch_table}
                WHERE owner_id = :owner_id AND instance_id = :instance_id
                ORDER BY request_fingerprint ASC
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "instance_id": instance_id},
        )
        records: list[ForwardEventDispatchRecord] = []
        for row in result.mappings():
            records.append(_decode_dispatch_record(row))
        return tuple(sorted(records, key=lambda item: item.request.fingerprint))

    async def _load_payload(
        self, session: AsyncSessionLike, payload_digest: str
    ) -> DispatchPayload | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT payload_digest, payload_json, byte_length, payload_fingerprint
                FROM {self._schema.payload_table}
                WHERE payload_digest = :payload_digest
                FOR SHARE
                """
            ),
            {"payload_digest": payload_digest},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("forward dispatch payload query returned duplicate rows")
        row = rows[0]
        payload = DispatchPayload(row["payload_digest"], row["payload_json"], int(row["byte_length"]))
        if row.get("payload_fingerprint") not in (None, payload.fingerprint):
            raise ValueError("forward dispatch payload fingerprint does not match bytes")
        return payload

    async def _insert_payload(self, session: AsyncSessionLike, payload: DispatchPayload) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.payload_table}
                    (payload_digest, payload_json, byte_length, payload_fingerprint)
                VALUES (:payload_digest, :payload_json, :byte_length, :payload_fingerprint)
                ON CONFLICT (payload_digest) DO NOTHING
                """
            ),
            {
                "payload_digest": payload.payload_digest,
                "payload_json": payload.payload_json,
                "byte_length": payload.byte_length,
                "payload_fingerprint": payload.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("forward dispatch payload insert lost a uniqueness race")

    async def _insert_dispatch(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        instance_id: str,
        resolution: ForwardEventDispatchResolution,
    ) -> None:
        assert resolution.envelope is not None
        request = resolution.envelope.request
        replay_plan = resolution.event_transaction.replay_plan
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.dispatch_table}
                    (owner_id, instance_id, event_fingerprint, idempotency_key,
                     request_fingerprint, attempt_id, payload_digest, queue_name,
                     created_at, replay_plan_fingerprint, dispatch_fingerprint)
                VALUES (:owner_id, :instance_id, :event_fingerprint, :idempotency_key,
                        :request_fingerprint, :attempt_id, :payload_digest, :queue_name,
                        :created_at, :replay_plan_fingerprint, :dispatch_fingerprint)
                ON CONFLICT (owner_id, idempotency_key) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "instance_id": instance_id,
                "event_fingerprint": resolution.event_transaction.event_fingerprint,
                "idempotency_key": request.idempotency_key,
                "request_fingerprint": request.fingerprint,
                "attempt_id": request.attempt_id,
                "payload_digest": request.payload_digest,
                "queue_name": request.queue_name,
                "created_at": _encode_datetime(request.created_at),
                "replay_plan_fingerprint": replay_plan.fingerprint if replay_plan else None,
                "dispatch_fingerprint": request.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("forward dispatch insert lost a uniqueness race")

    async def _insert_outbox(self, session: AsyncSessionLike, message: OutboxMessage) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.outbox_table}
                    (message_id, message_fingerprint, request_id, aggregate_type,
                     aggregate_id, event_id, topic, payload_digest, created_at,
                     available_at, published)
                VALUES (:message_id, :message_fingerprint, :request_id, :aggregate_type,
                        :aggregate_id, :event_id, :topic, :payload_digest, :created_at,
                        :available_at, FALSE)
                ON CONFLICT (message_id) DO NOTHING
                """
            ),
            {
                "message_id": message.message_id,
                "message_fingerprint": message.fingerprint,
                "request_id": message.request_id,
                "aggregate_type": message.aggregate_type,
                "aggregate_id": message.aggregate_id,
                "event_id": message.event_id,
                "topic": message.topic,
                "payload_digest": message.payload_digest,
                "created_at": _encode_datetime(message.created_at),
                "available_at": _encode_datetime(message.available_at),
            },
        )
        if getattr(result, "rowcount", 0) not in (0, 1):
            raise ValueError("forward dispatch outbox insert failed")


def _forward_outbox_message(
    owner_id: str, instance_id: str, resolution: ForwardEventDispatchResolution
) -> OutboxMessage:
    assert resolution.envelope is not None
    request = resolution.envelope.request
    event_id = content_digest(
        {
            "owner_id": owner_id,
            "instance_id": instance_id,
            "event_fingerprint": resolution.event_transaction.event_fingerprint,
            "dispatch_fingerprint": request.fingerprint,
        }
    )
    request_id = content_digest(
        {
            "owner_id": owner_id,
            "instance_id": instance_id,
            "dispatch_fingerprint": request.fingerprint,
            "kind": "forward-event-dispatch-outbox",
        }
    )
    return OutboxMessage(
        request_id=request_id,
        aggregate_type="strategy_forward_instance",
        aggregate_id=instance_id,
        event_id=event_id,
        topic=request.queue_name,
        payload_digest=request.payload_digest,
        created_at=request.created_at,
        available_at=request.created_at,
    )


def _encode_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _decode_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("created_at must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    return parsed


def _decode_dispatch_record(row: Mapping[str, Any]) -> ForwardEventDispatchRecord:
    try:
        request = DispatchRequest(
            row["idempotency_key"],
            row["attempt_id"],
            row["payload_digest"],
            row["queue_name"],
            _decode_datetime(row["created_at"]),
        )
        record = ForwardEventDispatchRecord(
            row["owner_id"],
            row["instance_id"],
            row["event_fingerprint"],
            request,
            row.get("replay_plan_fingerprint"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL forward dispatch row is malformed") from error
    if row.get("request_fingerprint") != request.fingerprint:
        raise ValueError("forward dispatch request fingerprint does not match bytes")
    if row.get("dispatch_fingerprint") != request.fingerprint:
        raise ValueError("forward dispatch fingerprint does not match bytes")
    return record


__all__ = [
    "ForwardEventDispatchRecord",
    "PostgresForwardEventDispatchAdapter",
    "PostgresForwardEventDispatchSchema",
]
