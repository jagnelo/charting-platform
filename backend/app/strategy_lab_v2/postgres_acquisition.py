"""Owner-scoped PostgreSQL persistence for data-acquisition receipts.

Provider adapters own acquisition, repair, and snapshot creation.  This
registration-neutral bridge persists the resulting digest-only handoff so
execution can later require the exact preflight request, frozen snapshot, and
coverage resolution evidence without fetching data inside the simulator.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.data_acquisition import DataAcquisitionReceipt


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class AcquisitionStateDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class AcquisitionStateResolution:
    decision: AcquisitionStateDecision
    receipt: DataAcquisitionReceipt

    def __post_init__(self) -> None:
        if not isinstance(self.decision, AcquisitionStateDecision):
            raise TypeError("decision must be an AcquisitionStateDecision")
        if not isinstance(self.receipt, DataAcquisitionReceipt):
            raise TypeError("receipt must be a DataAcquisitionReceipt")


@dataclass(frozen=True, slots=True)
class PostgresAcquisitionSchema:
    """Explicit additive DDL for data-acquisition handoff receipts."""

    receipt_table: str = "strategy_lab_v2_acquisition_receipts"

    def __post_init__(self) -> None:
        if not isinstance(self.receipt_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.receipt_table
        ):
            raise ValueError("receipt_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.receipt_table} (
                owner_id TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                snapshot_fingerprint TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                provider_snapshot_id TEXT NOT NULL,
                coverage_resolution_fingerprint TEXT NOT NULL,
                provider_receipt_digest TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                receipt_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, request_fingerprint)
            )
            """,
        )


class PostgresAcquisitionAdapter:
    """Persist and authenticate owner-scoped acquisition handoffs."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresAcquisitionSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresAcquisitionSchema()

    @property
    def schema(self) -> PostgresAcquisitionSchema:
        return self._schema

    async def ensure(
        self, *, principal: Any, receipt: DataAcquisitionReceipt
    ) -> AcquisitionStateResolution:
        """Register one receipt or replay its exact request-bound identity."""

        if not isinstance(receipt, DataAcquisitionReceipt):
            raise TypeError("receipt must be a DataAcquisitionReceipt")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_one(session, owner_id, receipt.request_fingerprint)
                if current is None:
                    await self._insert(session, owner_id, receipt)
                    return AcquisitionStateResolution(AcquisitionStateDecision.REGISTERED, receipt)
                if current != receipt:
                    raise ValueError("PostgreSQL acquisition receipt identity is already bound")
                return AcquisitionStateResolution(AcquisitionStateDecision.REPLAY_EXISTING, current)

    async def load(
        self, *, principal: Any, request_fingerprint: str
    ) -> DataAcquisitionReceipt | None:
        """Read and authenticate one request-bound acquisition receipt."""

        require_sha256_digest(request_fingerprint, field_name="request_fingerprint")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_one(session, owner_id, request_fingerprint)

    async def load_all(self, *, principal: Any) -> tuple[DataAcquisitionReceipt, ...]:
        """Read all owner receipts in deterministic request order."""

        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, request_fingerprint, snapshot_fingerprint,
                               snapshot_id, provider_snapshot_id,
                               coverage_resolution_fingerprint, provider_receipt_digest,
                               acquired_at, receipt_fingerprint
                        FROM {self._schema.receipt_table}
                        WHERE owner_id = :owner_id
                        ORDER BY request_fingerprint ASC
                        FOR UPDATE
                        """
                    ),
                    {"owner_id": owner_id},
                )
                receipts = tuple(_authenticate_row(row, owner_id) for row in result.mappings())
                ordered = tuple(sorted(receipts, key=lambda item: item.request_fingerprint))
                if receipts != ordered:
                    raise ValueError("PostgreSQL acquisition receipts are not deterministically ordered")
                return receipts

    async def _load_one(
        self, session: AsyncSessionLike, owner_id: str, request_fingerprint: str
    ) -> DataAcquisitionReceipt | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, request_fingerprint, snapshot_fingerprint,
                       snapshot_id, provider_snapshot_id,
                       coverage_resolution_fingerprint, provider_receipt_digest,
                       acquired_at, receipt_fingerprint
                FROM {self._schema.receipt_table}
                WHERE owner_id = :owner_id AND request_fingerprint = :request_fingerprint
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "request_fingerprint": request_fingerprint},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL acquisition query returned duplicate keys")
        return _authenticate_row(rows[0], owner_id, request_fingerprint)

    async def _insert(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        receipt: DataAcquisitionReceipt,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.receipt_table}
                    (owner_id, request_fingerprint, snapshot_fingerprint, snapshot_id,
                     provider_snapshot_id, coverage_resolution_fingerprint,
                     provider_receipt_digest, acquired_at, receipt_fingerprint)
                VALUES (:owner_id, :request_fingerprint, :snapshot_fingerprint, :snapshot_id,
                        :provider_snapshot_id, :coverage_resolution_fingerprint,
                        :provider_receipt_digest, :acquired_at, :receipt_fingerprint)
                ON CONFLICT (owner_id, request_fingerprint) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "request_fingerprint": receipt.request_fingerprint,
                "snapshot_fingerprint": receipt.snapshot_fingerprint,
                "snapshot_id": receipt.snapshot_id,
                "provider_snapshot_id": receipt.provider_snapshot_id,
                "coverage_resolution_fingerprint": receipt.coverage_resolution_fingerprint,
                "provider_receipt_digest": receipt.provider_receipt_digest,
                "acquired_at": _encode_datetime(receipt.acquired_at),
                "receipt_fingerprint": receipt.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL acquisition receipt insert lost a uniqueness race")


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _authenticate_row(
    row: Mapping[str, Any], owner_id: str, request_fingerprint: str | None = None
) -> DataAcquisitionReceipt:
    receipt = _decode_receipt(row)
    if row.get("owner_id") != owner_id:
        raise ValueError("PostgreSQL acquisition receipt owner identity drifted")
    if row.get("request_fingerprint") != receipt.request_fingerprint:
        raise ValueError("PostgreSQL acquisition request identity does not match bytes")
    if request_fingerprint is not None and receipt.request_fingerprint != request_fingerprint:
        raise ValueError("PostgreSQL acquisition request identity drifted")
    if row.get("receipt_fingerprint") != receipt.fingerprint:
        raise ValueError("PostgreSQL acquisition receipt fingerprint does not match bytes")
    return receipt


def _decode_receipt(row: Mapping[str, Any]) -> DataAcquisitionReceipt:
    try:
        return DataAcquisitionReceipt(
            row["request_fingerprint"],
            row["snapshot_fingerprint"],
            row["snapshot_id"],
            row["provider_snapshot_id"],
            row["coverage_resolution_fingerprint"],
            row["provider_receipt_digest"],
            _decode_datetime(row["acquired_at"], "acquired_at"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL acquisition receipt row is malformed") from error


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
    "AcquisitionStateDecision",
    "AcquisitionStateResolution",
    "PostgresAcquisitionAdapter",
    "PostgresAcquisitionSchema",
]
