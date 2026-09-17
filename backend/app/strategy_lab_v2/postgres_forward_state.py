"""PostgreSQL persistence for broker-free forward instance state.

The forward lifecycle itself remains pure in :mod:`forward_state`,
:mod:`forward_warmup`, and :mod:`forward_admission`.  This adapter provides the
durable owner-scoped boundary: instance checkpoints, one-time warm-up receipts,
and content-addressed event identities are locked and compare-and-set in one
transaction.  It deliberately does not consume providers, submit broker
orders, or start a worker.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ForwardInstance, ForwardState
from app.strategy_lab_v2.forward_admission import (
    ForwardAdmissionResolution,
    ForwardLiveAdmissionState,
    ForwardSeenEvent,
    admit_forward_event,
)
from app.strategy_lab_v2.forward_state import ForwardStateCheckpoint
from app.strategy_lab_v2.forward_warmup import (
    ForwardWarmupDecision,
    ForwardWarmupReceipt,
    ForwardWarmupResolution,
    resolve_forward_warmup,
)
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardEventObservation,
    transition_forward_instance,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class ForwardInstanceDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class ForwardInstanceResolution:
    decision: ForwardInstanceDecision
    instance: ForwardInstance | None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ForwardInstanceDecision):
            raise TypeError("decision must be a ForwardInstanceDecision")
        if self.instance is not None and not isinstance(self.instance, ForwardInstance):
            raise TypeError("instance must be a ForwardInstance")
        if self.decision in {
            ForwardInstanceDecision.CONFLICT,
            ForwardInstanceDecision.NOT_FOUND,
        } and not self.rejection_reason:
            raise ValueError("failed instance resolutions require a reason")
        if self.decision in {
            ForwardInstanceDecision.REGISTERED,
            ForwardInstanceDecision.REPLAY_EXISTING,
        } and self.rejection_reason:
            raise ValueError("successful instance resolutions cannot contain a reason")


class ForwardStateMutationDecision(StrEnum):
    APPLIED = "applied"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class ForwardStateMutationResolution:
    decision: ForwardStateMutationDecision
    instance: ForwardInstance | None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ForwardStateMutationDecision):
            raise TypeError("decision must be a ForwardStateMutationDecision")
        if self.instance is not None and not isinstance(self.instance, ForwardInstance):
            raise TypeError("instance must be a ForwardInstance")
        if self.decision in {
            ForwardStateMutationDecision.CONFLICT,
            ForwardStateMutationDecision.NOT_FOUND,
        } and not self.rejection_reason:
            raise ValueError("failed forward mutations require a reason")
        if self.decision in {
            ForwardStateMutationDecision.APPLIED,
            ForwardStateMutationDecision.REPLAY_EXISTING,
        } and self.rejection_reason:
            raise ValueError("successful forward mutations cannot contain a reason")


@dataclass(frozen=True, slots=True)
class PostgresForwardStateSchema:
    """Explicit additive DDL for forward instances, warm-ups, and seen events."""

    instance_table: str = "strategy_lab_v2_forward_instances"
    warmup_table: str = "strategy_lab_v2_forward_warmups"
    event_table: str = "strategy_lab_v2_forward_seen_events"

    def __post_init__(self) -> None:
        for name, value in (
            ("instance_table", self.instance_table),
            ("warmup_table", self.warmup_table),
            ("event_table", self.event_table),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
                raise ValueError(f"{name} must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.instance_table} (
                owner_id TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                portfolio_fingerprint TEXT NOT NULL,
                warmup_snapshot_fingerprint TEXT NOT NULL,
                carry_in_mode TEXT NOT NULL,
                state TEXT NOT NULL,
                last_event_id TEXT NULL,
                last_event_sequence BIGINT NOT NULL,
                correction_count BIGINT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                processed_event_ids_json TEXT NOT NULL,
                buffered_event_ids_json TEXT NOT NULL,
                correction_event_ids_json TEXT NOT NULL,
                duplicate_count BIGINT NOT NULL,
                out_of_order_count BIGINT NOT NULL,
                instance_fingerprint TEXT NOT NULL,
                checkpoint_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, instance_id)
            )
            """,
            f"""
            CREATE TABLE {self.warmup_table} (
                owner_id TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                warmup_snapshot_fingerprint TEXT NOT NULL,
                carry_in_mode TEXT NOT NULL,
                warmup_result_fingerprint TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                final_event_id TEXT NULL,
                final_event_sequence BIGINT NOT NULL,
                final_event_fingerprint TEXT NULL,
                receipt_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, instance_id)
            )
            """,
            f"""
            CREATE TABLE {self.event_table} (
                owner_id TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_fingerprint TEXT NOT NULL,
                sequence BIGINT NOT NULL,
                seen_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, instance_id, event_id)
            )
            """,
        )


class PostgresForwardStateAdapter:
    """Persist restart-safe forward checkpoints and event admission evidence."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresForwardStateSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresForwardStateSchema()

    @property
    def schema(self) -> PostgresForwardStateSchema:
        return self._schema

    async def ensure_instance(
        self, *, principal: Any, instance: ForwardInstance
    ) -> ForwardInstanceResolution:
        """Register one owner-scoped instance or replay its exact identity."""

        if not isinstance(instance, ForwardInstance):
            raise TypeError("instance must be a ForwardInstance")
        owner_id = _principal_id(principal)
        checkpoint = _initial_checkpoint(instance)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_checkpoint(session, owner_id, instance.instance_id)
                if current is not None:
                    existing_instance, _ = current
                    if existing_instance == instance:
                        return ForwardInstanceResolution(
                            ForwardInstanceDecision.REPLAY_EXISTING, existing_instance
                        )
                    return ForwardInstanceResolution(
                        ForwardInstanceDecision.CONFLICT,
                        existing_instance,
                        "forward instance identity is already bound to different content",
                    )
                await self._insert_instance(session, owner_id, checkpoint)
                return ForwardInstanceResolution(ForwardInstanceDecision.REGISTERED, instance)

    async def load_instance(
        self, *, principal: Any, instance_id: str
    ) -> ForwardInstance | None:
        """Read and authenticate one instance without requiring warm-up completion."""

        _validate_instance_id(instance_id)
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_checkpoint(session, owner_id, instance_id)
                return current[0] if current is not None else None

    async def transition(
        self,
        *,
        principal: Any,
        instance_id: str,
        target: ForwardState,
        now: datetime,
    ) -> ForwardStateMutationResolution:
        """Apply one lifecycle transition with an instance compare-and-set."""

        _validate_instance_id(instance_id)
        if not isinstance(target, ForwardState):
            raise TypeError("target must be a ForwardState")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_checkpoint(session, owner_id, instance_id)
                if current is None:
                    return ForwardStateMutationResolution(
                        ForwardStateMutationDecision.NOT_FOUND,
                        None,
                        "forward instance was not found",
                    )
                instance, checkpoint = current
                if instance.state is target:
                    return ForwardStateMutationResolution(
                        ForwardStateMutationDecision.REPLAY_EXISTING, instance
                    )
                try:
                    next_instance = transition_forward_instance(instance, target, now=now)
                except (TypeError, ValueError) as error:
                    return ForwardStateMutationResolution(
                        ForwardStateMutationDecision.CONFLICT, instance, str(error)
                    )
                await self._update_instance(session, owner_id, checkpoint, next_instance)
                return ForwardStateMutationResolution(
                    ForwardStateMutationDecision.APPLIED, next_instance
                )

    async def complete_warmup(
        self, *, principal: Any, receipt: ForwardWarmupReceipt
    ) -> ForwardWarmupResolution:
        """Persist the one-time warm-up handoff and activate the instance."""

        if not isinstance(receipt, ForwardWarmupReceipt):
            raise TypeError("receipt must be a ForwardWarmupReceipt")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_checkpoint(session, owner_id, receipt.instance_id)
                if current is None:
                    raise ValueError("forward instance was not found")
                instance, checkpoint = current
                existing = await self._load_warmup(session, owner_id, receipt.instance_id)
                resolution = resolve_forward_warmup(
                    instance, receipt, existing_receipt=existing
                )
                if resolution.decision is ForwardWarmupDecision.COMPLETE:
                    if resolution.receipt is None:  # pragma: no cover - pure guard
                        raise ValueError("warm-up resolution omitted its receipt")
                    next_checkpoint = ForwardLiveAdmissionState.from_warmup(
                        resolution.instance, resolution.receipt
                    ).checkpoint
                    await self._update_instance(
                        session, owner_id, checkpoint, next_checkpoint.instance,
                        checkpoint_override=next_checkpoint,
                    )
                    await self._insert_warmup(session, owner_id, resolution.receipt)
                return resolution

    async def load_state(
        self, *, principal: Any, instance_id: str
    ) -> ForwardLiveAdmissionState | None:
        """Read one active admission state with all seen event identities."""

        _validate_instance_id(instance_id)
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_live_state(session, owner_id, instance_id)

    async def admit(
        self,
        *,
        principal: Any,
        instance_id: str,
        event: CanonicalForwardEvent,
        observation: ForwardEventObservation,
    ) -> ForwardAdmissionResolution:
        """Admit one canonical event and persist its resulting checkpoint."""

        _validate_instance_id(instance_id)
        if not isinstance(event, CanonicalForwardEvent):
            raise TypeError("event must be a CanonicalForwardEvent")
        if not isinstance(observation, ForwardEventObservation):
            raise TypeError("observation must be a ForwardEventObservation")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                state = await self._load_live_state(session, owner_id, instance_id)
                if state is None:
                    raise ValueError("active forward instance was not found")
                resolution = admit_forward_event(state, event, observation)
                if resolution.state != state:
                    current = await self._load_checkpoint(
                        session, owner_id, state.checkpoint.instance.instance_id
                    )
                    if current is None:  # pragma: no cover - locked row cannot disappear
                        raise ValueError("forward instance disappeared during admission")
                    _, checkpoint = current
                    next_checkpoint = resolution.state.checkpoint
                    await self._update_instance(
                        session,
                        owner_id,
                        checkpoint,
                        next_checkpoint.instance,
                        checkpoint_override=next_checkpoint,
                    )
                    existing_ids = {item.event_id for item in state.seen_events}
                    for item in resolution.state.seen_events:
                        if item.event_id not in existing_ids:
                            await self._insert_seen_event(
                                session, owner_id, state.checkpoint.instance.instance_id, item
                            )
                return resolution

    async def _load_checkpoint(
        self, session: AsyncSessionLike, owner_id: str, instance_id: str
    ) -> tuple[ForwardInstance, ForwardStateCheckpoint] | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, instance_id, portfolio_fingerprint,
                       warmup_snapshot_fingerprint, carry_in_mode, state,
                       last_event_id, last_event_sequence, correction_count,
                       created_at, updated_at, processed_event_ids_json,
                       buffered_event_ids_json, correction_event_ids_json,
                       duplicate_count, out_of_order_count, instance_fingerprint,
                       checkpoint_fingerprint
                FROM {self._schema.instance_table}
                WHERE owner_id = :owner_id AND instance_id = :instance_id
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "instance_id": instance_id},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL forward instance query returned duplicate keys")
        row = rows[0]
        instance, checkpoint = _decode_checkpoint(row)
        if row.get("owner_id") != owner_id or row.get("instance_id") != instance_id:
            raise ValueError("PostgreSQL forward instance owner/identity drifted")
        if row.get("instance_fingerprint") != content_digest(instance):
            raise ValueError("PostgreSQL forward instance fingerprint does not match bytes")
        if row.get("checkpoint_fingerprint") != checkpoint.fingerprint:
            raise ValueError("PostgreSQL forward checkpoint fingerprint does not match bytes")
        return instance, checkpoint

    async def _load_warmup(
        self, session: AsyncSessionLike, owner_id: str, instance_id: str
    ) -> ForwardWarmupReceipt | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, instance_id, warmup_snapshot_fingerprint,
                       carry_in_mode, warmup_result_fingerprint, completed_at,
                       final_event_id, final_event_sequence, final_event_fingerprint,
                       receipt_fingerprint
                FROM {self._schema.warmup_table}
                WHERE owner_id = :owner_id AND instance_id = :instance_id
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "instance_id": instance_id},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL warm-up query returned duplicate keys")
        row = rows[0]
        receipt = _decode_receipt(row)
        if row.get("owner_id") != owner_id or row.get("instance_id") != instance_id:
            raise ValueError("PostgreSQL warm-up owner/identity drifted")
        if row.get("receipt_fingerprint") != receipt.fingerprint:
            raise ValueError("PostgreSQL warm-up fingerprint does not match bytes")
        return receipt

    async def _load_live_state(
        self, session: AsyncSessionLike, owner_id: str, instance_id: str
    ) -> ForwardLiveAdmissionState | None:
        current = await self._load_checkpoint(session, owner_id, instance_id)
        if current is None:
            return None
        instance, checkpoint = current
        receipt = await self._load_warmup(session, owner_id, instance_id)
        if receipt is None:
            raise ValueError("active forward instance is missing its warm-up receipt")
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, instance_id, event_id, event_fingerprint,
                       sequence, seen_fingerprint
                FROM {self._schema.event_table}
                WHERE owner_id = :owner_id AND instance_id = :instance_id
                ORDER BY event_id ASC
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "instance_id": instance_id},
        )
        events: list[ForwardSeenEvent] = []
        for row in result.mappings():
            seen = _decode_seen_event(row)
            if row.get("owner_id") != owner_id or row.get("instance_id") != instance_id:
                raise ValueError("PostgreSQL seen event owner/identity drifted")
            if row.get("event_id") != seen.event_id:
                raise ValueError("PostgreSQL seen event identity does not match bytes")
            if row.get("seen_fingerprint") != content_digest(seen):
                raise ValueError("PostgreSQL seen event fingerprint does not match bytes")
            events.append(seen)
        ordered = tuple(sorted(events, key=lambda item: item.event_id))
        if tuple(events) != ordered:
            raise ValueError("PostgreSQL seen events are not deterministically ordered")
        return ForwardLiveAdmissionState(
            checkpoint=checkpoint,
            warmup_receipt_fingerprint=receipt.fingerprint,
            seen_events=ordered,
        )

    async def _insert_instance(
        self, session: AsyncSessionLike, owner_id: str, checkpoint: ForwardStateCheckpoint
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.instance_table}
                    (owner_id, instance_id, portfolio_fingerprint,
                     warmup_snapshot_fingerprint, carry_in_mode, state,
                     last_event_id, last_event_sequence, correction_count,
                     created_at, updated_at, processed_event_ids_json,
                     buffered_event_ids_json, correction_event_ids_json,
                     duplicate_count, out_of_order_count, instance_fingerprint,
                     checkpoint_fingerprint)
                VALUES (:owner_id, :instance_id, :portfolio_fingerprint,
                        :warmup_snapshot_fingerprint, :carry_in_mode, :state,
                        :last_event_id, :last_event_sequence, :correction_count,
                        :created_at, :updated_at, :processed_event_ids_json,
                        :buffered_event_ids_json, :correction_event_ids_json,
                        :duplicate_count, :out_of_order_count, :instance_fingerprint,
                        :checkpoint_fingerprint)
                ON CONFLICT (owner_id, instance_id) DO NOTHING
                """
            ),
            _checkpoint_values(owner_id, checkpoint),
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL forward instance insert lost a uniqueness race")

    async def _update_instance(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        current: ForwardStateCheckpoint,
        next_instance: ForwardInstance,
        *,
        checkpoint_override: ForwardStateCheckpoint | None = None,
    ) -> None:
        next_checkpoint = checkpoint_override or ForwardStateCheckpoint(
            next_instance,
            current.processed_event_ids,
            current.buffered_event_ids,
            current.correction_event_ids,
            current.duplicate_count,
            current.out_of_order_count,
        )
        values = _checkpoint_values(owner_id, next_checkpoint)
        values.update(
            expected_checkpoint_fingerprint=current.fingerprint,
            expected_instance_fingerprint=content_digest(current.instance),
        )
        result = await session.execute(
            _statement(
                f"""
                UPDATE {self._schema.instance_table}
                SET portfolio_fingerprint = :portfolio_fingerprint,
                    warmup_snapshot_fingerprint = :warmup_snapshot_fingerprint,
                    carry_in_mode = :carry_in_mode, state = :state,
                    last_event_id = :last_event_id,
                    last_event_sequence = :last_event_sequence,
                    correction_count = :correction_count,
                    created_at = :created_at, updated_at = :updated_at,
                    processed_event_ids_json = :processed_event_ids_json,
                    buffered_event_ids_json = :buffered_event_ids_json,
                    correction_event_ids_json = :correction_event_ids_json,
                    duplicate_count = :duplicate_count,
                    out_of_order_count = :out_of_order_count,
                    instance_fingerprint = :instance_fingerprint,
                    checkpoint_fingerprint = :checkpoint_fingerprint
                WHERE owner_id = :owner_id AND instance_id = :instance_id
                  AND instance_fingerprint = :expected_instance_fingerprint
                  AND checkpoint_fingerprint = :expected_checkpoint_fingerprint
                """
            ),
            values,
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL forward instance compare-and-set lost a race")

    async def _insert_warmup(
        self, session: AsyncSessionLike, owner_id: str, receipt: ForwardWarmupReceipt
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.warmup_table}
                    (owner_id, instance_id, warmup_snapshot_fingerprint, carry_in_mode,
                     warmup_result_fingerprint, completed_at, final_event_id,
                     final_event_sequence, final_event_fingerprint, receipt_fingerprint)
                VALUES (:owner_id, :instance_id, :warmup_snapshot_fingerprint, :carry_in_mode,
                        :warmup_result_fingerprint, :completed_at, :final_event_id,
                        :final_event_sequence, :final_event_fingerprint, :receipt_fingerprint)
                ON CONFLICT (owner_id, instance_id) DO NOTHING
                """
            ),
            _receipt_values(owner_id, receipt),
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL warm-up insert lost a uniqueness race")
        if receipt.final_event_id is not None and receipt.final_event_fingerprint is not None:
            await self._insert_seen_event(
                session,
                owner_id,
                receipt.instance_id,
                ForwardSeenEvent(
                    receipt.final_event_id,
                    receipt.final_event_fingerprint,
                    receipt.final_event_sequence,
                ),
            )

    async def _insert_seen_event(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        instance_id: str,
        seen: ForwardSeenEvent,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.event_table}
                    (owner_id, instance_id, event_id, event_fingerprint,
                     sequence, seen_fingerprint)
                VALUES (:owner_id, :instance_id, :event_id, :event_fingerprint,
                        :sequence, :seen_fingerprint)
                ON CONFLICT (owner_id, instance_id, event_id) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "instance_id": instance_id,
                "event_id": seen.event_id,
                "event_fingerprint": seen.event_fingerprint,
                "sequence": seen.sequence,
                "seen_fingerprint": content_digest(seen),
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL seen event insert lost a uniqueness race")


def _initial_checkpoint(instance: ForwardInstance) -> ForwardStateCheckpoint:
    processed = (
        frozenset({instance.last_event_id}) if instance.last_event_id is not None else frozenset()
    )
    if instance.correction_count:
        raise ValueError("a new persisted instance cannot infer prior correction event identities")
    return ForwardStateCheckpoint(instance, processed_event_ids=processed)


def _checkpoint_values(owner_id: str, checkpoint: ForwardStateCheckpoint) -> dict[str, Any]:
    instance = checkpoint.instance
    return {
        "owner_id": owner_id,
        "instance_id": instance.instance_id,
        "portfolio_fingerprint": instance.portfolio_fingerprint,
        "warmup_snapshot_fingerprint": instance.warmup_snapshot_fingerprint,
        "carry_in_mode": instance.carry_in_mode.value,
        "state": instance.state.value,
        "last_event_id": instance.last_event_id,
        "last_event_sequence": instance.last_event_sequence,
        "correction_count": instance.correction_count,
        "created_at": _encode_datetime(instance.created_at),
        "updated_at": _encode_datetime(instance.updated_at),
        "processed_event_ids_json": _encode_ids(checkpoint.processed_event_ids),
        "buffered_event_ids_json": _encode_ids(checkpoint.buffered_event_ids),
        "correction_event_ids_json": _encode_ids(checkpoint.correction_event_ids),
        "duplicate_count": checkpoint.duplicate_count,
        "out_of_order_count": checkpoint.out_of_order_count,
        "instance_fingerprint": content_digest(instance),
        "checkpoint_fingerprint": checkpoint.fingerprint,
    }


def _receipt_values(owner_id: str, receipt: ForwardWarmupReceipt) -> dict[str, Any]:
    return {
        "owner_id": owner_id,
        "instance_id": receipt.instance_id,
        "warmup_snapshot_fingerprint": receipt.warmup_snapshot_fingerprint,
        "carry_in_mode": receipt.carry_in_mode.value,
        "warmup_result_fingerprint": receipt.warmup_result_fingerprint,
        "completed_at": _encode_datetime(receipt.completed_at),
        "final_event_id": receipt.final_event_id,
        "final_event_sequence": receipt.final_event_sequence,
        "final_event_fingerprint": receipt.final_event_fingerprint,
        "receipt_fingerprint": receipt.fingerprint,
    }


def _decode_checkpoint(row: Mapping[str, Any]) -> tuple[ForwardInstance, ForwardStateCheckpoint]:
    try:
        instance = ForwardInstance(
            row["instance_id"],
            row["portfolio_fingerprint"],
            row["warmup_snapshot_fingerprint"],
            _carry_in_mode(row["carry_in_mode"]),
            ForwardState(row["state"]),
            row.get("last_event_id"),
            int(row["last_event_sequence"]),
            int(row["correction_count"]),
            _decode_datetime(row["created_at"], "created_at"),
            _decode_datetime(row["updated_at"], "updated_at"),
        )
        checkpoint = ForwardStateCheckpoint(
            instance,
            _decode_ids(row["processed_event_ids_json"], "processed_event_ids_json"),
            _decode_ids(row["buffered_event_ids_json"], "buffered_event_ids_json"),
            _decode_ids(row["correction_event_ids_json"], "correction_event_ids_json"),
            int(row["duplicate_count"]),
            int(row["out_of_order_count"]),
        )
        return instance, checkpoint
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("PostgreSQL forward instance row is malformed") from error


def _decode_receipt(row: Mapping[str, Any]) -> ForwardWarmupReceipt:
    try:
        return ForwardWarmupReceipt(
            row["instance_id"],
            row["warmup_snapshot_fingerprint"],
            _carry_in_mode(row["carry_in_mode"]),
            row["warmup_result_fingerprint"],
            _decode_datetime(row["completed_at"], "completed_at"),
            row.get("final_event_id"),
            int(row["final_event_sequence"]),
            row.get("final_event_fingerprint"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL warm-up row is malformed") from error


def _decode_seen_event(row: Mapping[str, Any]) -> ForwardSeenEvent:
    try:
        return ForwardSeenEvent(
            row["event_id"], row["event_fingerprint"], int(row["sequence"])
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL seen event row is malformed") from error


def _carry_in_mode(value: Any):
    from app.strategy_lab_v2.contracts import CarryInMode

    return CarryInMode(value)


def _encode_ids(values: frozenset[str]) -> str:
    return json.dumps(sorted(values), separators=(",", ":"))


def _decode_ids(value: Any, field_name: str) -> frozenset[str]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field_name} must contain a JSON string list")
    if len(value) != len(set(value)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return frozenset(value)


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _validate_instance_id(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("instance_id must not be empty")


def _encode_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _decode_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} is malformed") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "ForwardInstanceDecision",
    "ForwardInstanceResolution",
    "ForwardStateMutationDecision",
    "ForwardStateMutationResolution",
    "PostgresForwardStateAdapter",
    "PostgresForwardStateSchema",
]
