"""Owner-scoped PostgreSQL persistence for legacy import evidence.

The legacy contracts are intentionally digest-only: this adapter preserves the
original record metadata and the exact compatibility assessment, but never
reads or writes legacy payload bytes.  Import resolution remains the pure
operation in :mod:`legacy`; this module supplies a locked registry and an
idempotent insert boundary for application wiring.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.strategy_lab_v2.legacy import (
    LegacyCompatibilityAssessment,
    LegacyImportDecision,
    LegacyImportRecord,
    LegacyImportRegistry,
    LegacyImportRequest,
    LegacyImportResolution,
    LegacyRecord,
    LegacyRecordKind,
    resolve_legacy_import,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class PostgresLegacySchema:
    """Explicit additive DDL for preserved legacy import records."""

    import_table: str = "strategy_lab_v2_legacy_imports"

    def __post_init__(self) -> None:
        if not isinstance(self.import_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.import_table
        ):
            raise ValueError("import_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.import_table} (
                owner_id TEXT NOT NULL,
                legacy_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                source_version TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                mapping_version TEXT NOT NULL,
                supported BOOLEAN NOT NULL,
                conversion_fingerprint TEXT NULL,
                notes_json TEXT NOT NULL,
                record_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, legacy_id)
            )
            """,
        )


class PostgresLegacyImportAdapter:
    """Persist an authenticated, owner-scoped legacy import registry."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresLegacySchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresLegacySchema()

    @property
    def schema(self) -> PostgresLegacySchema:
        return self._schema

    async def load_registry(self, *, principal: Any) -> LegacyImportRegistry:
        """Read and authenticate every preserved record for one principal."""

        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_registry(session, owner_id)

    async def import_record(
        self,
        *,
        principal: Any,
        request: LegacyImportRequest,
        assessment: LegacyCompatibilityAssessment,
    ) -> LegacyImportResolution:
        """Resolve and durably preserve one legacy record atomically."""

        if not isinstance(request, LegacyImportRequest):
            raise TypeError("request must be a LegacyImportRequest")
        if not isinstance(assessment, LegacyCompatibilityAssessment):
            raise TypeError("assessment must be a LegacyCompatibilityAssessment")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                registry = await self._load_registry(session, owner_id)
                resolution = resolve_legacy_import(registry, request, assessment)
                if resolution.decision in {
                    LegacyImportDecision.ACCEPT,
                    LegacyImportDecision.UNSUPPORTED,
                }:
                    record = next(
                        item
                        for item in resolution.registry.records
                        if item.original.legacy_id == request.legacy_id
                    )
                    await self._insert_record(session, owner_id, record)
                return resolution

    async def _load_registry(
        self, session: AsyncSessionLike, owner_id: str
    ) -> LegacyImportRegistry:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, legacy_id, kind, source_version, payload_digest,
                       observed_at, request_fingerprint, mapping_version, supported,
                       conversion_fingerprint, notes_json, record_fingerprint
                FROM {self._schema.import_table}
                WHERE owner_id = :owner_id
                ORDER BY legacy_id ASC
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id},
        )
        records: list[LegacyImportRecord] = []
        for row in result.mappings():
            record = _decode_record(row)
            if row.get("owner_id") != owner_id:
                raise ValueError("PostgreSQL legacy import owner identity drifted")
            if row.get("legacy_id") != record.original.legacy_id:
                raise ValueError("PostgreSQL legacy import id does not match bytes")
            if row.get("record_fingerprint") != record.fingerprint:
                raise ValueError("PostgreSQL legacy import fingerprint does not match bytes")
            records.append(record)
        ordered = tuple(sorted(records, key=lambda item: item.original.legacy_id))
        if tuple(records) != ordered:
            raise ValueError("PostgreSQL legacy imports are not deterministically ordered")
        return LegacyImportRegistry(ordered)

    async def _insert_record(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        record: LegacyImportRecord,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.import_table}
                    (owner_id, legacy_id, kind, source_version, payload_digest,
                     observed_at, request_fingerprint, mapping_version, supported,
                     conversion_fingerprint, notes_json, record_fingerprint)
                VALUES (:owner_id, :legacy_id, :kind, :source_version, :payload_digest,
                        :observed_at, :request_fingerprint, :mapping_version, :supported,
                        :conversion_fingerprint, :notes_json, :record_fingerprint)
                ON CONFLICT (owner_id, legacy_id) DO NOTHING
                """
            ),
            _record_values(owner_id, record),
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL legacy import insert lost a uniqueness race")


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _record_values(owner_id: str, record: LegacyImportRecord) -> dict[str, Any]:
    original = record.original
    assessment = record.assessment
    return {
        "owner_id": owner_id,
        "legacy_id": original.legacy_id,
        "kind": original.kind.value,
        "source_version": original.source_version,
        "payload_digest": original.payload_digest,
        "observed_at": _encode_datetime(original.observed_at),
        "request_fingerprint": record.request_fingerprint,
        "mapping_version": assessment.mapping_version,
        "supported": assessment.supported,
        "conversion_fingerprint": assessment.conversion_fingerprint,
        "notes_json": json.dumps(list(assessment.notes), separators=(",", ":")),
        "record_fingerprint": record.fingerprint,
    }


def _decode_record(row: Mapping[str, Any]) -> LegacyImportRecord:
    try:
        notes = json.loads(row["notes_json"])
        if not isinstance(notes, list):
            raise ValueError("notes_json must contain a list")
        assessment = LegacyCompatibilityAssessment(
            row["mapping_version"],
            bool(row["supported"]),
            row.get("conversion_fingerprint"),
            tuple(notes),
        )
        return LegacyImportRecord(
            LegacyRecord(
                row["legacy_id"],
                LegacyRecordKind(row["kind"]),
                row["source_version"],
                row["payload_digest"],
                _decode_datetime(row["observed_at"], "observed_at"),
            ),
            row["request_fingerprint"],
            assessment,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("PostgreSQL legacy import row is malformed") from error


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


__all__ = ["PostgresLegacyImportAdapter", "PostgresLegacySchema"]
