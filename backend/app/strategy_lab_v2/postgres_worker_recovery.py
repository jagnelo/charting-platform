"""Durable, replayable PostgreSQL worker recovery receipts."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.contracts import RunAttempt
from app.strategy_lab_v2.postgres_worker_state import (
    PostgresWorkerStateAdapter,
    WorkerCapacityDecision,
)
from app.strategy_lab_v2.recovery import RecoveryReason, RetryPolicy
from app.strategy_lab_v2.worker_recovery import (
    WorkerRecoveryDecision,
    WorkerRecoveryLedger,
    WorkerRecoveryRecord,
    WorkerRecoveryResolution,
    resolve_worker_recovery,
)
from app.strategy_lab_v2.workers import WorkerProfile


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class WorkerRecoveryReceiptDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class WorkerRecoveryReceiptResolution:
    decision: WorkerRecoveryReceiptDecision
    record: WorkerRecoveryRecord

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WorkerRecoveryReceiptDecision):
            raise TypeError("decision must be a WorkerRecoveryReceiptDecision")
        if not isinstance(self.record, WorkerRecoveryRecord):
            raise TypeError("record must be a WorkerRecoveryRecord")


@dataclass(frozen=True, slots=True)
class PostgresWorkerRecoverySchema:
    """Explicit additive DDL for owner-scoped infrastructure recovery receipts."""

    recovery_table: str = "strategy_lab_v2_worker_recoveries"

    def __post_init__(self) -> None:
        if not isinstance(self.recovery_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.recovery_table
        ):
            raise ValueError("recovery_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.recovery_table} (
                owner_id TEXT NOT NULL,
                recovery_fingerprint TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                reservation_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                plan_fingerprint TEXT NOT NULL,
                next_attempt_id TEXT NULL,
                lease_observation_fingerprint TEXT NOT NULL,
                lease_observation_sequence BIGINT NOT NULL,
                released_at TEXT NOT NULL,
                record_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, recovery_fingerprint),
                UNIQUE (owner_id, attempt_id),
                UNIQUE (owner_id, reservation_id)
            )
            """,
        )


class PostgresWorkerRecoveryAdapter:
    """Persist recovery intent before atomically releasing lease and capacity.

    The recovery receipt and worker-state release use separate PostgreSQL
    transactions. A restart in between is safe: ``resolve_worker_recovery``
    replays the exact receipt and reconstructs its deterministic release
    observation, which ``release_capacity`` applies idempotently.
    """

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        worker_state: PostgresWorkerStateAdapter | None = None,
        schema: PostgresWorkerRecoverySchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._worker_state = worker_state or PostgresWorkerStateAdapter(session_factory)
        self._schema = schema or PostgresWorkerRecoverySchema()

    @property
    def schema(self) -> PostgresWorkerRecoverySchema:
        return self._schema

    async def ensure(
        self, *, principal: Any, record: WorkerRecoveryRecord
    ) -> WorkerRecoveryReceiptResolution:
        if not isinstance(record, WorkerRecoveryRecord):
            raise TypeError("record must be a WorkerRecoveryRecord")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_one(session, owner_id, record.attempt_id)
                if current is None:
                    inserted = await self._insert(session, owner_id, record)
                    if inserted:
                        return WorkerRecoveryReceiptResolution(
                            WorkerRecoveryReceiptDecision.REGISTERED, record
                        )
                    current = await self._load_one(session, owner_id, record.attempt_id)
                    if current is None:
                        raise ValueError("worker recovery insert lost a uniqueness race")
                if current != record:
                    raise ValueError("worker recovery identity is already bound")
                return WorkerRecoveryReceiptResolution(
                    WorkerRecoveryReceiptDecision.REPLAY_EXISTING, current
                )

    async def load_ledger(self, *, principal: Any) -> WorkerRecoveryLedger:
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, recovery_fingerprint, attempt_id,
                               reservation_id, decision, reason, plan_fingerprint,
                               next_attempt_id, lease_observation_fingerprint,
                               lease_observation_sequence, released_at,
                               record_fingerprint
                        FROM {self._schema.recovery_table}
                        WHERE owner_id = :owner_id
                        ORDER BY recovery_fingerprint ASC
                        FOR UPDATE
                        """
                    ),
                    {"owner_id": owner_id},
                )
                records: list[WorkerRecoveryRecord] = []
                for row in result.mappings():
                    if row.get("owner_id") != owner_id:
                        raise ValueError("worker recovery owner identity drifted")
                    record = _decode_record(row)
                    if row.get("recovery_fingerprint") != record.recovery_fingerprint:
                        raise ValueError("worker recovery key does not match bytes")
                    if row.get("record_fingerprint") != record.fingerprint:
                        raise ValueError("worker recovery fingerprint does not match bytes")
                    records.append(record)
                ordered = tuple(sorted(records, key=lambda item: item.recovery_fingerprint))
                if tuple(records) != ordered:
                    raise ValueError("worker recoveries are not deterministically ordered")
                return WorkerRecoveryLedger(ordered)

    async def recover(
        self,
        *,
        principal: Any,
        prior_attempts: Sequence[RunAttempt],
        admission_ledger: ExecutionAdmissionLedger,
        profile: WorkerProfile,
        lease_id: str,
        reason: RecoveryReason,
        observed_at: datetime,
        policy: RetryPolicy = RetryPolicy(),
        next_attempt_id: str | None = None,
    ) -> WorkerRecoveryResolution:
        """Plan recovery, persist its receipt, then release capacity safely.

        If the process stops after receipt insertion, a new adapter instance
        resumes from that receipt and applies the same lease observation and
        capacity release. Attempt creation remains an application-layer action
        represented by ``resolution.next_attempt``.
        """

        owner_id = _principal_id(principal)
        if not isinstance(profile, WorkerProfile):
            raise TypeError("profile must be a WorkerProfile")
        if not isinstance(lease_id, str) or not lease_id.strip():
            raise ValueError("lease_id must not be empty")
        pool = await self._worker_state.load_pool(profile)
        lease_state = await self._worker_state.load_lease(lease_id)
        if lease_state is None:
            raise ValueError("worker recovery lease is not persisted")
        ledger = await self.load_ledger(principal=owner_id)
        attempts = tuple(prior_attempts)
        existing_record = None
        if attempts and all(isinstance(item, RunAttempt) for item in attempts):
            latest_attempt = max(attempts, key=lambda item: item.ordinal)
            existing_record = next(
                (item for item in ledger.records if item.attempt_id == latest_attempt.attempt_id),
                None,
            )
        effective_observed_at = (
            existing_record.released_at if existing_record is not None else observed_at
        )
        effective_next_attempt_id = next_attempt_id
        if existing_record is not None and next_attempt_id is None:
            effective_next_attempt_id = existing_record.next_attempt_id
        resolution = resolve_worker_recovery(
            attempts,
            admission_ledger=admission_ledger,
            lease_state=lease_state,
            pool=pool,
            ledger=ledger,
            reason=reason,
            observed_at=effective_observed_at,
            policy=policy,
            next_attempt_id=effective_next_attempt_id,
        )
        if resolution.decision not in {
            WorkerRecoveryDecision.RETRY_SCHEDULED,
            WorkerRecoveryDecision.TERMINAL,
            WorkerRecoveryDecision.NOOP,
            WorkerRecoveryDecision.REPLAY_EXISTING,
        }:
            return resolution
        if resolution.release_observation is None:
            raise ValueError("worker recovery omitted its deterministic release observation")
        record = next(
            (
                item
                for item in resolution.ledger.records
                if item.attempt_id == resolution.release_observation.attempt_id
            ),
            None,
        )
        if record is None:
            raise ValueError("worker recovery omitted its durable receipt")
        await self.ensure(principal=owner_id, record=record)
        capacity = await self._worker_state.release_capacity(
            profile=profile,
            reservation_id=record.reservation_id,
            lease_id=lease_id,
            observation=resolution.release_observation,
        )
        if capacity.decision is WorkerCapacityDecision.REJECT:
            return WorkerRecoveryResolution(
                WorkerRecoveryDecision.REJECT,
                None,
                pool,
                lease_state,
                rejection_reason=capacity.rejection_reason or "worker capacity release rejected",
                ledger=resolution.ledger,
            )
        if capacity.lease_state is None:
            raise ValueError("worker capacity release omitted its persisted lease state")
        return WorkerRecoveryResolution(
            resolution.decision,
            resolution.plan,
            capacity.pool,
            capacity.lease_state,
            resolution.next_attempt,
            record.reservation_id,
            ledger=resolution.ledger,
            release_observation=resolution.release_observation,
        )

    async def _load_one(
        self, session: AsyncSessionLike, owner_id: str, attempt_id: str
    ) -> WorkerRecoveryRecord | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, recovery_fingerprint, attempt_id,
                       reservation_id, decision, reason, plan_fingerprint,
                       next_attempt_id, lease_observation_fingerprint,
                       lease_observation_sequence, released_at,
                       record_fingerprint
                FROM {self._schema.recovery_table}
                WHERE owner_id = :owner_id AND attempt_id = :attempt_id
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "attempt_id": attempt_id},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("worker recovery query returned duplicate keys")
        row = rows[0]
        record = _decode_record(row)
        if row.get("owner_id") != owner_id or row.get("attempt_id") != record.attempt_id:
            raise ValueError("worker recovery owner/attempt identity drifted")
        if row.get("recovery_fingerprint") != record.recovery_fingerprint:
            raise ValueError("worker recovery key does not match bytes")
        if row.get("record_fingerprint") != record.fingerprint:
            raise ValueError("worker recovery fingerprint does not match bytes")
        return record

    async def _insert(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        record: WorkerRecoveryRecord,
    ) -> bool:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.recovery_table}
                    (owner_id, recovery_fingerprint, attempt_id, reservation_id,
                     decision, reason, plan_fingerprint, next_attempt_id,
                     lease_observation_fingerprint, lease_observation_sequence,
                     released_at, record_fingerprint)
                VALUES (:owner_id, :recovery_fingerprint, :attempt_id, :reservation_id,
                        :decision, :reason, :plan_fingerprint, :next_attempt_id,
                        :lease_observation_fingerprint, :lease_observation_sequence,
                        :released_at, :record_fingerprint)
                ON CONFLICT (owner_id, attempt_id) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "recovery_fingerprint": record.recovery_fingerprint,
                "attempt_id": record.attempt_id,
                "reservation_id": record.reservation_id,
                "decision": record.decision.value,
                "reason": record.reason.value,
                "plan_fingerprint": record.plan_fingerprint,
                "next_attempt_id": record.next_attempt_id,
                "lease_observation_fingerprint": record.lease_observation_fingerprint,
                "lease_observation_sequence": record.lease_observation_sequence,
                "released_at": _encode_datetime(record.released_at),
                "record_fingerprint": record.fingerprint,
            },
        )
        return getattr(result, "rowcount", 0) == 1


def _decode_record(row: Mapping[str, Any]) -> WorkerRecoveryRecord:
    try:
        return WorkerRecoveryRecord(
            row["recovery_fingerprint"],
            row["attempt_id"],
            row["reservation_id"],
            WorkerRecoveryDecision(row["decision"]),
            RecoveryReason(row["reason"]),
            row["plan_fingerprint"],
            row.get("next_attempt_id"),
            row["lease_observation_fingerprint"],
            int(row["lease_observation_sequence"]),
            _decode_datetime(row["released_at"], "released_at"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("worker recovery row is malformed") from error


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


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
    return parsed.astimezone(UTC)


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "PostgresWorkerRecoveryAdapter",
    "PostgresWorkerRecoverySchema",
    "WorkerRecoveryReceiptDecision",
    "WorkerRecoveryReceiptResolution",
]
