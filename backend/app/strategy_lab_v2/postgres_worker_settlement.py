"""Owner-scoped persistence for worker terminal settlement receipts.

The lease/reservation adapter owns the compare-and-set that frees capacity;
this small adapter retains the immutable settlement receipt that makes that
operation replayable after a process crash between the two durable writes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.worker_settlement import (
    WorkerSettlementLedger,
    WorkerSettlementRecord,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class SettlementReceiptDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class SettlementReceiptResolution:
    decision: SettlementReceiptDecision
    record: WorkerSettlementRecord

    def __post_init__(self) -> None:
        if not isinstance(self.decision, SettlementReceiptDecision):
            raise TypeError("decision must be a SettlementReceiptDecision")
        if not isinstance(self.record, WorkerSettlementRecord):
            raise TypeError("record must be a WorkerSettlementRecord")


@dataclass(frozen=True, slots=True)
class PostgresWorkerSettlementSchema:
    """Explicit additive DDL for owner-scoped worker settlement receipts."""

    settlement_table: str = "strategy_lab_v2_worker_settlements"

    def __post_init__(self) -> None:
        if not isinstance(self.settlement_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.settlement_table
        ):
            raise ValueError("settlement_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.settlement_table} (
                owner_id TEXT NOT NULL,
                settlement_fingerprint TEXT NOT NULL,
                admission_fingerprint TEXT NOT NULL,
                worker_execution_fingerprint TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                reservation_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                lease_observation_fingerprint TEXT NOT NULL,
                released_at TEXT NOT NULL,
                record_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, settlement_fingerprint),
                UNIQUE (owner_id, attempt_id),
                UNIQUE (owner_id, reservation_id)
            )
            """,
        )


class PostgresWorkerSettlementAdapter:
    """Persist and authenticate one owner's immutable worker settlements."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresWorkerSettlementSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresWorkerSettlementSchema()

    @property
    def schema(self) -> PostgresWorkerSettlementSchema:
        return self._schema

    async def ensure(
        self, *, principal: Any, record: WorkerSettlementRecord
    ) -> SettlementReceiptResolution:
        if not isinstance(record, WorkerSettlementRecord):
            raise TypeError("record must be a WorkerSettlementRecord")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_one(session, owner_id, record.attempt_id)
                if current is None:
                    await self._insert(session, owner_id, record)
                    return SettlementReceiptResolution(
                        SettlementReceiptDecision.REGISTERED, record
                    )
                if current != record:
                    raise ValueError("worker settlement identity is already bound")
                return SettlementReceiptResolution(
                    SettlementReceiptDecision.REPLAY_EXISTING, current
                )

    async def load_ledger(self, *, principal: Any) -> WorkerSettlementLedger:
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, settlement_fingerprint,
                               admission_fingerprint, worker_execution_fingerprint,
                               attempt_id, reservation_id, worker_id,
                               lease_observation_fingerprint, released_at,
                               record_fingerprint
                        FROM {self._schema.settlement_table}
                        WHERE owner_id = :owner_id
                        ORDER BY settlement_fingerprint ASC
                        FOR UPDATE
                        """
                    ),
                    {"owner_id": owner_id},
                )
                records: list[WorkerSettlementRecord] = []
                for row in result.mappings():
                    if row.get("owner_id") != owner_id:
                        raise ValueError("worker settlement owner identity drifted")
                    record = _decode_record(row)
                    if row.get("settlement_fingerprint") != record.settlement_fingerprint:
                        raise ValueError("worker settlement key does not match bytes")
                    if row.get("record_fingerprint") != record.fingerprint:
                        raise ValueError("worker settlement fingerprint does not match bytes")
                    records.append(record)
                ordered = tuple(sorted(records, key=lambda item: item.settlement_fingerprint))
                if tuple(records) != ordered:
                    raise ValueError("worker settlements are not deterministically ordered")
                return WorkerSettlementLedger(ordered)

    async def _load_one(
        self, session: AsyncSessionLike, owner_id: str, attempt_id: str
    ) -> WorkerSettlementRecord | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, settlement_fingerprint,
                       admission_fingerprint, worker_execution_fingerprint,
                       attempt_id, reservation_id, worker_id,
                       lease_observation_fingerprint, released_at,
                       record_fingerprint
                FROM {self._schema.settlement_table}
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
            raise ValueError("worker settlement query returned duplicate keys")
        row = rows[0]
        record = _decode_record(row)
        if row.get("owner_id") != owner_id or row.get("attempt_id") != record.attempt_id:
            raise ValueError("worker settlement owner/attempt identity drifted")
        if row.get("settlement_fingerprint") != record.settlement_fingerprint:
            raise ValueError("worker settlement key does not match bytes")
        if row.get("record_fingerprint") != record.fingerprint:
            raise ValueError("worker settlement fingerprint does not match bytes")
        return record

    async def _insert(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        record: WorkerSettlementRecord,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.settlement_table}
                    (owner_id, settlement_fingerprint, admission_fingerprint,
                     worker_execution_fingerprint, attempt_id, reservation_id,
                     worker_id, lease_observation_fingerprint, released_at,
                     record_fingerprint)
                VALUES (:owner_id, :settlement_fingerprint, :admission_fingerprint,
                        :worker_execution_fingerprint, :attempt_id, :reservation_id,
                        :worker_id, :lease_observation_fingerprint, :released_at,
                        :record_fingerprint)
                ON CONFLICT (owner_id, attempt_id) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "settlement_fingerprint": record.settlement_fingerprint,
                "admission_fingerprint": record.admission_fingerprint,
                "worker_execution_fingerprint": record.worker_execution_fingerprint,
                "attempt_id": record.attempt_id,
                "reservation_id": record.reservation_id,
                "worker_id": record.worker_id,
                "lease_observation_fingerprint": record.lease_observation_fingerprint,
                "released_at": _encode_datetime(record.released_at),
                "record_fingerprint": record.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("worker settlement insert lost a uniqueness race")


def _decode_record(row: Mapping[str, Any]) -> WorkerSettlementRecord:
    try:
        return WorkerSettlementRecord(
            row["settlement_fingerprint"],
            row["admission_fingerprint"],
            row["worker_execution_fingerprint"],
            row["attempt_id"],
            row["reservation_id"],
            row["worker_id"],
            row["lease_observation_fingerprint"],
            _decode_datetime(row["released_at"], "released_at"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("worker settlement row is malformed") from error


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
    return parsed


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "PostgresWorkerSettlementAdapter",
    "PostgresWorkerSettlementSchema",
    "SettlementReceiptDecision",
    "SettlementReceiptResolution",
]
