"""Atomic PostgreSQL persistence for result completion and artifact commits.

The pure :func:`finalize_execution_result` contract validates terminal runtime,
outcome, progress, publication, and artifact evidence without side effects.
This adapter supplies the durable transaction boundary: it locks the
owner-scoped completion ledger and the shared content-addressed artifact
commit ledger, resolves the pure decision, and inserts every new commit and
the completion receipt in one transaction.  A failed artifact plan therefore
cannot leave a partial completion behind.

Migrations, artifact bytes, authorization, and worker execution remain
application-owned concerns.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.strategy_lab_v2.artifact_commit import (
    ArtifactCommitLedger,
    ArtifactCommitRecord,
)
from app.strategy_lab_v2.artifact_publication import ArtifactPublicationPlan
from app.strategy_lab_v2.outcomes import ExecutionOutcome
from app.strategy_lab_v2.progress import ExecutionProgressState
from app.strategy_lab_v2.result_completion import (
    ResultCompletionDecision,
    ResultCompletionLedger,
    ResultCompletionRecord,
    ResultCompletionResolution,
    finalize_execution_result,
)
from app.strategy_lab_v2.result_publication import ResultPublicationPlan
from app.strategy_lab_v2.runtime_execution import RuntimeExecutionState
from app.strategy_lab_v2.submissions import SubmissionReceipt


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class PostgresResultCompletionSchema:
    """Explicit additive DDL for completion receipts and shared artifact commits."""

    completion_table: str = "strategy_lab_v2_result_completions"
    commit_table: str = "strategy_lab_v2_artifact_commits"

    def __post_init__(self) -> None:
        for name, value in (
            ("completion_table", self.completion_table),
            ("commit_table", self.commit_table),
        ):
            if not isinstance(value, str) or not re.fullmatch(
                r"[a-z_][a-z0-9_]*", value
            ):
                raise ValueError(f"{name} must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.completion_table} (
                owner_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                completion_fingerprint TEXT NOT NULL,
                result_fingerprint TEXT NOT NULL,
                runtime_state_fingerprint TEXT NOT NULL,
                outcome_fingerprint TEXT NOT NULL,
                progress_fingerprint TEXT NOT NULL,
                publication_fingerprint TEXT NOT NULL,
                artifact_commit_keys_json TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                record_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, attempt_id),
                UNIQUE (owner_id, completion_fingerprint)
            )
            """,
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


class PostgresResultCompletionAdapter:
    """Finalize a result and all artifact commits atomically in PostgreSQL."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresResultCompletionSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresResultCompletionSchema()

    @property
    def schema(self) -> PostgresResultCompletionSchema:
        return self._schema

    async def finalize(
        self,
        *,
        principal: Any,
        submission: SubmissionReceipt,
        runtime_state: RuntimeExecutionState,
        outcome: ExecutionOutcome,
        progress: ExecutionProgressState,
        publication: ResultPublicationPlan,
        artifact_plans: Sequence[ArtifactPublicationPlan],
        completed_at: datetime,
    ) -> ResultCompletionResolution:
        """Resolve and persist one terminal completion in a single transaction."""

        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                completion_ledger = await self._load_completions(session, owner_id)
                commit_ledger = await self._load_commits(session)
                resolution = finalize_execution_result(
                    completion_ledger,
                    commit_ledger,
                    submission=submission,
                    runtime_state=runtime_state,
                    outcome=outcome,
                    progress=progress,
                    publication=publication,
                    artifact_plans=artifact_plans,
                    completed_at=completed_at,
                )
                if resolution.decision is ResultCompletionDecision.COMPLETE:
                    if resolution.record is None:  # pragma: no cover - pure guard
                        raise ValueError("result completion resolution omitted its record")
                    existing_keys = {record.commit_key for record in commit_ledger.records}
                    for record in resolution.artifact_commit_ledger.records:
                        if record.commit_key not in existing_keys:
                            await self._insert_commit(session, record)
                    await self._insert_completion(session, owner_id, resolution.record)
                return resolution

    async def load_completion_ledger(
        self, *, principal: Any
    ) -> ResultCompletionLedger:
        """Read and authenticate all completion receipts for one owner."""

        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_completions(session, owner_id)

    async def load_artifact_commit_ledger(self) -> ArtifactCommitLedger:
        """Read and authenticate the shared content-addressed commit ledger."""

        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_commits(session)

    async def _load_completions(
        self, session: AsyncSessionLike, owner_id: str
    ) -> ResultCompletionLedger:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, attempt_id, completion_fingerprint,
                       result_fingerprint, runtime_state_fingerprint,
                       outcome_fingerprint, progress_fingerprint,
                       publication_fingerprint, artifact_commit_keys_json,
                       completed_at, record_fingerprint
                FROM {self._schema.completion_table}
                WHERE owner_id = :owner_id
                ORDER BY completion_fingerprint ASC
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id},
        )
        records: list[ResultCompletionRecord] = []
        for row in result.mappings():
            record = _decode_completion(row)
            if row.get("owner_id") != owner_id:
                raise ValueError("PostgreSQL result completion owner identity drifted")
            if row.get("completion_fingerprint") != record.completion_fingerprint:
                raise ValueError("PostgreSQL result completion key does not match bytes")
            if row.get("record_fingerprint") != record.fingerprint:
                raise ValueError("PostgreSQL result completion fingerprint does not match bytes")
            records.append(record)
        ordered = tuple(sorted(records, key=lambda item: item.completion_fingerprint))
        if tuple(records) != ordered:
            raise ValueError("PostgreSQL result completions are not deterministically ordered")
        return ResultCompletionLedger(ordered)

    async def _load_commits(self, session: AsyncSessionLike) -> ArtifactCommitLedger:
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
            record = _decode_commit(row)
            if row.get("commit_key") != record.commit_key:
                raise ValueError("PostgreSQL artifact commit key does not match bytes")
            if row.get("record_fingerprint") != record.fingerprint:
                raise ValueError("PostgreSQL artifact commit fingerprint does not match bytes")
            records.append(record)
        ordered = tuple(sorted(records, key=lambda item: item.commit_key))
        if tuple(records) != ordered:
            raise ValueError("PostgreSQL artifact commits are not deterministically ordered")
        return ArtifactCommitLedger(ordered)

    async def _insert_commit(
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

    async def _insert_completion(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        record: ResultCompletionRecord,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.completion_table}
                    (owner_id, attempt_id, completion_fingerprint, result_fingerprint,
                     runtime_state_fingerprint, outcome_fingerprint, progress_fingerprint,
                     publication_fingerprint, artifact_commit_keys_json, completed_at,
                     record_fingerprint)
                VALUES (:owner_id, :attempt_id, :completion_fingerprint, :result_fingerprint,
                        :runtime_state_fingerprint, :outcome_fingerprint, :progress_fingerprint,
                        :publication_fingerprint, :artifact_commit_keys_json, :completed_at,
                        :record_fingerprint)
                ON CONFLICT (owner_id, attempt_id) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "attempt_id": record.attempt_id,
                "completion_fingerprint": record.completion_fingerprint,
                "result_fingerprint": record.result_fingerprint,
                "runtime_state_fingerprint": record.runtime_state_fingerprint,
                "outcome_fingerprint": record.outcome_fingerprint,
                "progress_fingerprint": record.progress_fingerprint,
                "publication_fingerprint": record.publication_fingerprint,
                "artifact_commit_keys_json": json.dumps(
                    list(record.artifact_commit_keys), separators=(",", ":")
                ),
                "completed_at": _encode_datetime(record.completed_at),
                "record_fingerprint": record.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL result completion insert lost a uniqueness race")


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _decode_completion(row: Mapping[str, Any]) -> ResultCompletionRecord:
    try:
        raw_keys = row["artifact_commit_keys_json"]
        if isinstance(raw_keys, str):
            raw_keys = json.loads(raw_keys)
        if not isinstance(raw_keys, list) or any(not isinstance(item, str) for item in raw_keys):
            raise ValueError("artifact_commit_keys_json must contain a string list")
        return ResultCompletionRecord(
            completion_fingerprint=row["completion_fingerprint"],
            result_fingerprint=row["result_fingerprint"],
            attempt_id=row["attempt_id"],
            runtime_state_fingerprint=row["runtime_state_fingerprint"],
            outcome_fingerprint=row["outcome_fingerprint"],
            progress_fingerprint=row["progress_fingerprint"],
            publication_fingerprint=row["publication_fingerprint"],
            artifact_commit_keys=tuple(raw_keys),
            completed_at=_decode_datetime(row["completed_at"], "completed_at"),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("PostgreSQL result completion row is malformed") from error


def _decode_commit(row: Mapping[str, Any]) -> ArtifactCommitRecord:
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


__all__ = ["PostgresResultCompletionAdapter", "PostgresResultCompletionSchema"]
