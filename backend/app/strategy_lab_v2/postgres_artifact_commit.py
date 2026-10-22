"""PostgreSQL persistence for immutable artifact publication commit evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.strategy_lab_v2.artifact_commit import (
    ArtifactCommitDecision,
    ArtifactCommitLedger,
    ArtifactCommitRecord,
    ArtifactCommitResolution,
    finalize_artifact_commit,
)
from app.strategy_lab_v2.artifact_publication import ArtifactPublicationPlan


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class PostgresArtifactCommitSchema:
    """Explicit additive DDL for the artifact commit ledger."""

    commit_table: str = "strategy_lab_v2_artifact_commits"

    def __post_init__(self) -> None:
        if not isinstance(self.commit_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.commit_table
        ):
            raise ValueError("commit_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.commit_table} (
                commit_key TEXT PRIMARY KEY,
                manifest_fingerprint TEXT NOT NULL,
                content_digest TEXT NOT NULL,
                storage_key TEXT NOT NULL UNIQUE,
                byte_length BIGINT NOT NULL,
                committed_at TEXT NOT NULL,
                record_fingerprint TEXT NOT NULL
            )
            """,
        )


class PostgresArtifactCommitAdapter:
    """Persist content-addressed artifact commit records without writing bytes."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresArtifactCommitSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresArtifactCommitSchema()

    @property
    def schema(self) -> PostgresArtifactCommitSchema:
        return self._schema

    async def load_ledger(self) -> ArtifactCommitLedger:
        """Read and authenticate all immutable commit records in key order."""

        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_ledger(session)

    async def finalize(
        self,
        plan: ArtifactPublicationPlan,
        *,
        committed_at: datetime,
    ) -> ArtifactCommitResolution:
        """Finalize one publication plan under a locked, idempotent transaction."""

        if not isinstance(plan, ArtifactPublicationPlan):
            raise TypeError("plan must be an ArtifactPublicationPlan")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                ledger = await self._load_ledger(session)
                resolution = finalize_artifact_commit(
                    ledger,
                    plan,
                    committed_at=committed_at,
                )
                if resolution.decision is ArtifactCommitDecision.COMMIT:
                    if resolution.record is None:  # pragma: no cover - pure guard
                        raise ValueError("artifact commit resolution omitted its record")
                    await self._insert_record(session, resolution.record)
                return resolution

    async def _load_ledger(self, session: AsyncSessionLike) -> ArtifactCommitLedger:
        result = await session.execute(
            _statement(
                f"""
                SELECT commit_key, manifest_fingerprint, content_digest, storage_key,
                       byte_length, committed_at, record_fingerprint
                FROM {self._schema.commit_table}
                ORDER BY commit_key ASC
                FOR UPDATE
                """
            )
        )
        records: list[ArtifactCommitRecord] = []
        for row in result.mappings():
            record = _decode_record(row)
            if row.get("commit_key") != record.commit_key:
                raise ValueError("PostgreSQL artifact commit key does not match bytes")
            if row.get("record_fingerprint") != record.fingerprint:
                raise ValueError("PostgreSQL artifact commit fingerprint does not match bytes")
            records.append(record)
        ordered = tuple(sorted(records, key=lambda item: item.commit_key))
        if tuple(records) != ordered:
            raise ValueError("PostgreSQL artifact commits are not deterministically ordered")
        return ArtifactCommitLedger(ordered)

    async def _insert_record(
        self, session: AsyncSessionLike, record: ArtifactCommitRecord
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.commit_table}
                    (commit_key, manifest_fingerprint, content_digest, storage_key,
                     byte_length, committed_at, record_fingerprint)
                VALUES (:commit_key, :manifest_fingerprint, :content_digest, :storage_key,
                        :byte_length, :committed_at, :record_fingerprint)
                ON CONFLICT (commit_key) DO NOTHING
                """
            ),
            {
                "commit_key": record.commit_key,
                "manifest_fingerprint": record.manifest_fingerprint,
                "content_digest": record.content_digest,
                "storage_key": record.storage_key,
                "byte_length": record.byte_length,
                "committed_at": _encode_datetime(record.committed_at),
                "record_fingerprint": record.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL artifact commit insert lost a uniqueness race")


def _decode_record(row: Mapping[str, Any]) -> ArtifactCommitRecord:
    try:
        return ArtifactCommitRecord(
            row["manifest_fingerprint"],
            row["content_digest"],
            row["storage_key"],
            int(row["byte_length"]),
            _decode_datetime(row["committed_at"], "committed_at"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL artifact commit row is malformed") from error


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


__all__ = ["PostgresArtifactCommitAdapter", "PostgresArtifactCommitSchema"]
