"""Owner-scoped PostgreSQL persistence for execution-summary read models.

Execution summaries are immutable projections of a submission receipt, typed
outcome/progress checkpoints, and (for successful attempts) an accepted result
publication plan.  The adapter keeps those projections append-only: a state
identity can be registered once, exact retries replay, and a changed summary
for the same outcome/progress checkpoint conflicts instead of overwriting
history.  Reads return the latest authenticated projection for an attempt.

The adapter is registration-neutral.  It does not apply migrations, authorize
HTTP requests, enqueue work, or invoke a worker.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.api_contracts import ApiError, ApiErrorCode
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.execution_summary import ExecutionSummary
from app.strategy_lab_v2.outcomes import OutcomeStatus
from app.strategy_lab_v2.progress import ProgressPhase


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class ExecutionSummaryStateDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class ExecutionSummaryStateResolution:
    """Registration result for one immutable execution-summary projection."""

    decision: ExecutionSummaryStateDecision
    summary: ExecutionSummary

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ExecutionSummaryStateDecision):
            raise TypeError("decision must be an ExecutionSummaryStateDecision")
        if not isinstance(self.summary, ExecutionSummary):
            raise TypeError("summary must be an ExecutionSummary")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class PostgresExecutionSummarySchema:
    """Explicit additive DDL for immutable execution-summary projections."""

    summary_table: str = "strategy_lab_v2_execution_summaries"

    def __post_init__(self) -> None:
        if not isinstance(self.summary_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.summary_table
        ):
            raise ValueError("summary_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.summary_table} (
                owner_id TEXT NOT NULL,
                submission_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                state_key TEXT NOT NULL,
                outcome_sequence BIGINT NOT NULL,
                progress_sequence BIGINT NOT NULL,
                operation TEXT NOT NULL,
                status TEXT NOT NULL,
                progress_phase TEXT NOT NULL,
                completed_units BIGINT NOT NULL,
                total_units BIGINT NOT NULL,
                cancellation_requested BOOLEAN NOT NULL,
                updated_at TEXT NOT NULL,
                result_digest TEXT NULL,
                publication_fingerprint TEXT NULL,
                error_json TEXT NULL,
                summary_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, state_key),
                UNIQUE (owner_id, summary_fingerprint)
            )
            """,
        )


class PostgresExecutionSummaryAdapter:
    """Persist and read owner-scoped immutable execution-summary snapshots."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresExecutionSummarySchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresExecutionSummarySchema()

    @property
    def schema(self) -> PostgresExecutionSummarySchema:
        return self._schema

    async def ensure(
        self, *, principal: Any, summary: ExecutionSummary
    ) -> ExecutionSummaryStateResolution:
        """Register one immutable projection or replay its exact state identity."""

        if not isinstance(summary, ExecutionSummary):
            raise TypeError("summary must be an ExecutionSummary")
        owner_id = _principal_id(principal)
        state_key = _state_key(summary)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_one(session, owner_id, state_key)
                if current is None:
                    await self._insert(session, owner_id, state_key, summary)
                    return ExecutionSummaryStateResolution(
                        ExecutionSummaryStateDecision.REGISTERED, summary
                    )
                if current != summary:
                    raise ValueError("PostgreSQL execution summary state identity is already bound")
                return ExecutionSummaryStateResolution(
                    ExecutionSummaryStateDecision.REPLAY_EXISTING, current
                )

    async def load(
        self, *, principal: Any, submission_id: str, attempt_id: str
    ) -> ExecutionSummary | None:
        """Read the latest authenticated projection for one owner attempt."""

        require_sha256_digest(submission_id, field_name="submission_id")
        _validate_attempt(attempt_id)
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, submission_id, attempt_id, state_key,
                               outcome_sequence, progress_sequence, operation, status,
                               progress_phase, completed_units, total_units,
                               cancellation_requested, updated_at, result_digest,
                               publication_fingerprint, error_json, summary_fingerprint
                        FROM {self._schema.summary_table}
                        WHERE owner_id = :owner_id
                          AND submission_id = :submission_id
                          AND attempt_id = :attempt_id
                        ORDER BY updated_at DESC, outcome_sequence DESC,
                                 progress_sequence DESC, summary_fingerprint DESC
                        FOR UPDATE
                        """
                    ),
                    {
                        "owner_id": owner_id,
                        "submission_id": submission_id,
                        "attempt_id": attempt_id,
                    },
                )
                summaries = tuple(
                    _authenticate_row(row, owner_id)
                    for row in result.mappings()
                )
                if not summaries:
                    return None
                return summaries[0]

    async def load_history(
        self, *, principal: Any, submission_id: str, attempt_id: str
    ) -> tuple[ExecutionSummary, ...]:
        """Read every immutable projection for one attempt in state order."""

        require_sha256_digest(submission_id, field_name="submission_id")
        _validate_attempt(attempt_id)
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, submission_id, attempt_id, state_key,
                               outcome_sequence, progress_sequence, operation, status,
                               progress_phase, completed_units, total_units,
                               cancellation_requested, updated_at, result_digest,
                               publication_fingerprint, error_json, summary_fingerprint
                        FROM {self._schema.summary_table}
                        WHERE owner_id = :owner_id
                          AND submission_id = :submission_id
                          AND attempt_id = :attempt_id
                        ORDER BY outcome_sequence ASC, progress_sequence ASC,
                                 updated_at ASC, summary_fingerprint ASC
                        FOR UPDATE
                        """
                    ),
                    {
                        "owner_id": owner_id,
                        "submission_id": submission_id,
                        "attempt_id": attempt_id,
                    },
                )
                summaries = tuple(
                    _authenticate_row(row, owner_id, submission_id, attempt_id)
                    for row in result.mappings()
                )
                ordered = tuple(
                    sorted(
                        summaries,
                        key=lambda item: (
                            item.outcome_sequence,
                            item.progress_sequence,
                            item.updated_at,
                            item.fingerprint,
                        ),
                    )
                )
                if summaries != ordered:
                    raise ValueError(
                        "PostgreSQL execution summary history is not deterministically ordered"
                    )
                return summaries

    async def load_all(self, *, principal: Any) -> tuple[ExecutionSummary, ...]:
        """Read the latest projection for every visible attempt deterministically."""

        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, submission_id, attempt_id, state_key,
                               outcome_sequence, progress_sequence, operation, status,
                               progress_phase, completed_units, total_units,
                               cancellation_requested, updated_at, result_digest,
                               publication_fingerprint, error_json, summary_fingerprint
                        FROM {self._schema.summary_table}
                        WHERE owner_id = :owner_id
                        ORDER BY submission_id ASC, attempt_id ASC, updated_at DESC,
                                 outcome_sequence DESC, progress_sequence DESC,
                                 summary_fingerprint DESC
                        FOR UPDATE
                        """
                    ),
                    {"owner_id": owner_id},
                )
                rows = tuple(result.mappings())
                latest: dict[tuple[str, str], ExecutionSummary] = {}
                for row in rows:
                    summary = _authenticate_row(row, owner_id)
                    key = (summary.submission_id, summary.attempt_id)
                    if key not in latest:
                        latest[key] = summary
                summaries = tuple(latest.values())
                ordered = tuple(
                    sorted(summaries, key=lambda item: (item.submission_id, item.attempt_id))
                )
                if summaries != ordered:
                    raise ValueError(
                        "PostgreSQL execution summaries are not deterministically ordered"
                    )
                return summaries

    async def _load_one(
        self, session: AsyncSessionLike, owner_id: str, state_key: str
    ) -> ExecutionSummary | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, submission_id, attempt_id, state_key,
                       outcome_sequence, progress_sequence, operation, status,
                       progress_phase, completed_units, total_units,
                       cancellation_requested, updated_at, result_digest,
                       publication_fingerprint, error_json, summary_fingerprint
                FROM {self._schema.summary_table}
                WHERE owner_id = :owner_id AND state_key = :state_key
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "state_key": state_key},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL execution summary query returned duplicate keys")
        return _authenticate_row(rows[0], owner_id, state_key=state_key)

    async def _insert(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        state_key: str,
        summary: ExecutionSummary,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.summary_table}
                    (owner_id, submission_id, attempt_id, state_key,
                     outcome_sequence, progress_sequence, operation, status,
                     progress_phase, completed_units, total_units,
                     cancellation_requested, updated_at, result_digest,
                     publication_fingerprint, error_json, summary_fingerprint)
                VALUES (:owner_id, :submission_id, :attempt_id, :state_key,
                        :outcome_sequence, :progress_sequence, :operation, :status,
                        :progress_phase, :completed_units, :total_units,
                        :cancellation_requested, :updated_at, :result_digest,
                        :publication_fingerprint, :error_json, :summary_fingerprint)
                ON CONFLICT (owner_id, state_key) DO NOTHING
                """
            ),
            _summary_values(owner_id, state_key, summary),
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL execution summary insert lost a uniqueness race")


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _validate_attempt(attempt_id: str) -> None:
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise ValueError("attempt_id must not be empty")


def _state_key(summary: ExecutionSummary) -> str:
    return content_digest(
        {
            "attempt_id": summary.attempt_id,
            "outcome_sequence": summary.outcome_sequence,
            "progress_sequence": summary.progress_sequence,
            "submission_id": summary.submission_id,
        }
    )


def _summary_values(
    owner_id: str, state_key: str, summary: ExecutionSummary
) -> dict[str, Any]:
    return {
        "owner_id": owner_id,
        "submission_id": summary.submission_id,
        "attempt_id": summary.attempt_id,
        "state_key": state_key,
        "outcome_sequence": summary.outcome_sequence,
        "progress_sequence": summary.progress_sequence,
        "operation": summary.operation,
        "status": summary.status.value,
        "progress_phase": summary.progress_phase.value,
        "completed_units": summary.completed_units,
        "total_units": summary.total_units,
        "cancellation_requested": summary.cancellation_requested,
        "updated_at": _encode_datetime(summary.updated_at),
        "result_digest": summary.result_digest,
        "publication_fingerprint": summary.publication_fingerprint,
        "error_json": _encode_error(summary.error),
        "summary_fingerprint": summary.fingerprint,
    }


def _authenticate_row(
    row: Mapping[str, Any],
    owner_id: str,
    submission_id: str | None = None,
    attempt_id: str | None = None,
    state_key: str | None = None,
) -> ExecutionSummary:
    summary = _decode_summary(row)
    if row.get("owner_id") != owner_id:
        raise ValueError("PostgreSQL execution summary owner identity drifted")
    if row.get("summary_fingerprint") != summary.fingerprint:
        raise ValueError("PostgreSQL execution summary fingerprint does not match bytes")
    if row.get("state_key") != _state_key(summary):
        raise ValueError("PostgreSQL execution summary state identity does not match bytes")
    if submission_id is not None and summary.submission_id != submission_id:
        raise ValueError("PostgreSQL execution summary submission identity drifted")
    if attempt_id is not None and summary.attempt_id != attempt_id:
        raise ValueError("PostgreSQL execution summary attempt identity drifted")
    if state_key is not None and _state_key(summary) != state_key:
        raise ValueError("PostgreSQL execution summary state identity drifted")
    return summary


def _decode_summary(row: Mapping[str, Any]) -> ExecutionSummary:
    try:
        return ExecutionSummary(
            submission_id=row["submission_id"],
            attempt_id=row["attempt_id"],
            operation=row["operation"],
            status=OutcomeStatus(row["status"]),
            outcome_sequence=int(row["outcome_sequence"]),
            progress_phase=ProgressPhase(row["progress_phase"]),
            progress_sequence=int(row["progress_sequence"]),
            completed_units=int(row["completed_units"]),
            total_units=int(row["total_units"]),
            cancellation_requested=_decode_bool(
                row["cancellation_requested"], "cancellation_requested"
            ),
            updated_at=_decode_datetime(row["updated_at"], "updated_at"),
            result_digest=row.get("result_digest"),
            publication_fingerprint=row.get("publication_fingerprint"),
            error=_decode_error(row.get("error_json")),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("PostgreSQL execution summary row is malformed") from error


def _encode_error(error: ApiError | None) -> str | None:
    if error is None:
        return None
    return json.dumps(
        {
            "code": error.code.value,
            "message": error.message,
            "request_id": error.request_id,
            "status_code": error.status_code,
            "retryable": error.retryable,
            "details": _json_ready(error.details),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_error(value: Any) -> ApiError | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("error_json must be a JSON string")
    raw = json.loads(value)
    if not isinstance(raw, Mapping):
        raise ValueError("error_json must contain an object")
    return ApiError(
        ApiErrorCode(raw["code"]),
        raw["message"],
        raw["request_id"],
        int(raw["status_code"]),
        raw.get("retryable", False),
        raw.get("details", {}),
    )


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted((_json_ready(item) for item in value), key=str)
    if isinstance(value, StrEnum):
        return value.value
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise TypeError(f"unsupported API error detail: {type(value).__name__}")


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


def _decode_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "ExecutionSummaryStateDecision",
    "ExecutionSummaryStateResolution",
    "PostgresExecutionSummaryAdapter",
    "PostgresExecutionSummarySchema",
]
