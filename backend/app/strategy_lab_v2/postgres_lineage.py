"""PostgreSQL persistence for owner-scoped immutable artifact lineage."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.strategy_lab_v2.lineage import (
    ArtifactLineageEntry,
    ArtifactLineageIndex,
    LineageDecision,
    LineageResolution,
    LineageRole,
    append_lineage_entry,
    build_lineage_index,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class PostgresLineageSchema:
    """Explicit additive DDL for immutable lineage edges."""

    lineage_table: str = "strategy_lab_v2_artifact_lineage"

    def __post_init__(self) -> None:
        if not isinstance(self.lineage_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.lineage_table
        ):
            raise ValueError("lineage_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.lineage_table} (
                semantic_key TEXT PRIMARY KEY,
                owner_type TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                artifact_manifest_fingerprint TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                parent_manifest_fingerprint TEXT NULL,
                entry_fingerprint TEXT NOT NULL,
                UNIQUE (owner_type, owner_id, semantic_key)
            )
            """,
        )


class PostgresLineageAdapter:
    """Persist deterministic owner-scoped lineage entries without byte I/O."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresLineageSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresLineageSchema()

    @property
    def schema(self) -> PostgresLineageSchema:
        return self._schema

    async def load_index(self, *, owner_type: str, owner_id: str) -> ArtifactLineageIndex:
        """Read and authenticate one complete owner lineage index."""

        _validate_owner(owner_type, owner_id)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_index(session, owner_type, owner_id)

    async def append(self, entry: ArtifactLineageEntry) -> LineageResolution:
        """Append or replay one semantic lineage edge atomically."""

        if not isinstance(entry, ArtifactLineageEntry):
            raise TypeError("entry must be an ArtifactLineageEntry")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                index = await self._load_index(session, entry.owner_type, entry.owner_id)
                resolution = append_lineage_entry(index, entry)
                if resolution.decision is LineageDecision.APPEND:
                    await self._insert_entry(session, entry)
                return resolution

    async def _load_index(
        self,
        session: AsyncSessionLike,
        owner_type: str,
        owner_id: str,
    ) -> ArtifactLineageIndex:
        result = await session.execute(
            _statement(
                f"""
                SELECT semantic_key, owner_type, owner_id,
                       artifact_manifest_fingerprint, role, created_at,
                       parent_manifest_fingerprint, entry_fingerprint
                FROM {self._schema.lineage_table}
                WHERE owner_type = :owner_type AND owner_id = :owner_id
                ORDER BY semantic_key ASC
                FOR UPDATE
                """
            ),
            {"owner_type": owner_type, "owner_id": owner_id},
        )
        entries: list[ArtifactLineageEntry] = []
        for row in result.mappings():
            entry = _decode_entry(row)
            if row.get("semantic_key") != entry.semantic_key:
                raise ValueError("PostgreSQL lineage semantic key does not match bytes")
            if row.get("entry_fingerprint") != entry.fingerprint:
                raise ValueError("PostgreSQL lineage entry fingerprint does not match bytes")
            if row.get("owner_type") != owner_type or row.get("owner_id") != owner_id:
                raise ValueError("PostgreSQL lineage owner identity drifted")
            entries.append(entry)
        ordered = tuple(sorted(entries, key=lambda item: item.semantic_key))
        if tuple(entries) != ordered:
            raise ValueError("PostgreSQL lineage entries are not deterministically ordered")
        return build_lineage_index(owner_type, owner_id, ordered)

    async def _insert_entry(
        self, session: AsyncSessionLike, entry: ArtifactLineageEntry
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.lineage_table}
                    (semantic_key, owner_type, owner_id,
                     artifact_manifest_fingerprint, role, created_at,
                     parent_manifest_fingerprint, entry_fingerprint)
                VALUES (:semantic_key, :owner_type, :owner_id,
                        :artifact_manifest_fingerprint, :role, :created_at,
                        :parent_manifest_fingerprint, :entry_fingerprint)
                ON CONFLICT (semantic_key) DO NOTHING
                """
            ),
            {
                "semantic_key": entry.semantic_key,
                "owner_type": entry.owner_type,
                "owner_id": entry.owner_id,
                "artifact_manifest_fingerprint": entry.artifact_manifest_fingerprint,
                "role": entry.role.value,
                "created_at": _encode_datetime(entry.created_at),
                "parent_manifest_fingerprint": entry.parent_manifest_fingerprint,
                "entry_fingerprint": entry.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL lineage insert lost a uniqueness race")


def _validate_owner(owner_type: str, owner_id: str) -> None:
    for value, field_name in ((owner_type, "owner_type"), (owner_id, "owner_id")):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must not be empty")


def _decode_entry(row: Mapping[str, Any]) -> ArtifactLineageEntry:
    try:
        return ArtifactLineageEntry(
            row["owner_type"],
            row["owner_id"],
            row["artifact_manifest_fingerprint"],
            LineageRole(row["role"]),
            _decode_datetime(row["created_at"], "created_at"),
            row.get("parent_manifest_fingerprint"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL lineage row is malformed") from error


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


__all__ = ["PostgresLineageAdapter", "PostgresLineageSchema"]
