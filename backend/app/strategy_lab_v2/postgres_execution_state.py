"""Owner-scoped PostgreSQL persistence for execution outcome/progress state.

Outcome and progress transitions remain engine-neutral in :mod:`outcomes` and
:mod:`progress_checkpoint`.  This adapter supplies the durable state boundary:
it locks both attempt rows, resolves monotonic updates through those pure
contracts, retains progress update identities for restart-safe replay, and
commits outcome/progress together.  It does not enqueue work or apply a
retry/cancellation effect.
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
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.outcomes import (
    ExecutionOutcome,
    OutcomeStatus,
    OutcomeUpdate,
    apply_outcome_update,
)
from app.strategy_lab_v2.postgres_commands import ExecutionCommandContext
from app.strategy_lab_v2.progress import (
    CancellationRequest,
    ExecutionProgressState,
    ExecutionProgressUpdate,
    ProgressPhase,
    request_cancellation,
)
from app.strategy_lab_v2.progress_checkpoint import (
    ProgressCheckpoint,
    ProgressCheckpointDecision,
    apply_progress_checkpoint,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class StateMutationDecision(StrEnum):
    APPLIED = "applied"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    NOT_FOUND = "not_found"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class StateMutationResolution:
    """Durable outcome/progress state returned by one transition."""

    decision: StateMutationDecision
    outcome: ExecutionOutcome | None
    progress: ExecutionProgressState | None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, StateMutationDecision):
            raise TypeError("decision must be a StateMutationDecision")
        if self.outcome is not None and not isinstance(self.outcome, ExecutionOutcome):
            raise TypeError("outcome must be an ExecutionOutcome")
        if self.progress is not None and not isinstance(self.progress, ExecutionProgressState):
            raise TypeError("progress must be an ExecutionProgressState")
        if self.outcome is not None and self.progress is not None:
            if self.outcome.attempt_id != self.progress.attempt_id:
                raise ValueError("outcome and progress must reference the same attempt")
        if self.decision in {
            StateMutationDecision.CONFLICT,
            StateMutationDecision.NOT_FOUND,
            StateMutationDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("failed state resolutions require a reason")
        if self.decision in {
            StateMutationDecision.APPLIED,
            StateMutationDecision.REPLAY_EXISTING,
        } and self.rejection_reason:
            raise ValueError("successful state resolutions cannot contain a reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class PostgresExecutionStateSchema:
    """Explicit additive DDL for owner-scoped outcome/progress checkpoints."""

    outcome_table: str = "strategy_lab_v2_execution_outcomes"
    progress_table: str = "strategy_lab_v2_execution_progress"

    def __post_init__(self) -> None:
        for name, value in (
            ("outcome_table", self.outcome_table),
            ("progress_table", self.progress_table),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
                raise ValueError(f"{name} must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.outcome_table} (
                owner_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                submission_id TEXT NOT NULL,
                sequence BIGINT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                result_digest TEXT NULL,
                error_json TEXT NULL,
                state_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, attempt_id)
            )
            """,
            f"""
            CREATE TABLE {self.progress_table} (
                owner_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                sequence BIGINT NOT NULL,
                phase TEXT NOT NULL,
                completed_units BIGINT NOT NULL,
                total_units BIGINT NOT NULL,
                cancellation_requested BOOLEAN NOT NULL,
                updated_at TEXT NOT NULL,
                applied_update_fingerprints_json TEXT NOT NULL,
                checkpoint_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, attempt_id)
            )
            """,
        )


class PostgresExecutionStateAdapter:
    """Persist and read owner-scoped monotonic outcome/progress checkpoints."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresExecutionStateSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresExecutionStateSchema()

    @property
    def schema(self) -> PostgresExecutionStateSchema:
        return self._schema

    async def initialize(
        self,
        *,
        principal: Any,
        outcome: ExecutionOutcome,
        progress: ExecutionProgressState,
    ) -> StateMutationResolution:
        """Create both sequence-zero checkpoints or replay an exact pair."""

        owner_id = _principal_id(principal)
        _validate_pair(outcome, progress)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_pair(session, owner_id, outcome.attempt_id)
                if current is not None:
                    current_outcome, current_progress, _ = current
                    if current_outcome == outcome and current_progress == progress:
                        return StateMutationResolution(
                            StateMutationDecision.REPLAY_EXISTING,
                            current_outcome,
                            current_progress,
                        )
                    return StateMutationResolution(
                        StateMutationDecision.CONFLICT,
                        current_outcome,
                        current_progress,
                        "execution state already exists with different content",
                    )
                await self._insert_outcome(session, owner_id, outcome)
                await self._insert_progress(session, owner_id, ProgressCheckpoint(progress))
                return StateMutationResolution(StateMutationDecision.APPLIED, outcome, progress)

    async def read_context(
        self, *, principal: Any, attempt_id: str
    ) -> ExecutionCommandContext | None:
        """Read an authenticated attempt context for ``PostgresCommandAdapter``."""

        owner_id = _principal_id(principal)
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_pair(session, owner_id, attempt_id)
                if current is None:
                    return None
                outcome, progress, _ = current
                return ExecutionCommandContext(outcome, progress)

    async def transition(
        self,
        *,
        principal: Any,
        outcome_update: OutcomeUpdate | None = None,
        progress_update: ExecutionProgressUpdate | None = None,
        cancellation: CancellationRequest | None = None,
    ) -> StateMutationResolution:
        """Apply one or more monotonic observations in one SQL transaction."""

        if outcome_update is None and progress_update is None and cancellation is None:
            raise ValueError("at least one state update is required")
        provided = (outcome_update, progress_update, cancellation)
        if outcome_update is not None and not isinstance(outcome_update, OutcomeUpdate):
            raise TypeError("outcome_update must be an OutcomeUpdate")
        if progress_update is not None and not isinstance(progress_update, ExecutionProgressUpdate):
            raise TypeError("progress_update must be an ExecutionProgressUpdate")
        if cancellation is not None and not isinstance(cancellation, CancellationRequest):
            raise TypeError("cancellation must be a CancellationRequest")
        attempt_ids = {
            item.attempt_id
            for item in provided
            if item is not None
        }
        if len(attempt_ids) != 1:
            raise ValueError("all state updates must reference one attempt")
        attempt_id = next(iter(attempt_ids))
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_pair(session, owner_id, attempt_id)
                if current is None:
                    return StateMutationResolution(
                        StateMutationDecision.NOT_FOUND,
                        None,
                        None,
                        "execution state was not found",
                    )
                outcome, progress, checkpoint = current
                next_outcome = outcome
                next_progress = progress
                next_checkpoint = checkpoint
                changed = False
                try:
                    if outcome_update is not None:
                        outcome_resolution = apply_outcome_update(outcome, outcome_update)
                        next_outcome = outcome_resolution.state
                        changed = changed or next_outcome != outcome
                    if progress_update is not None:
                        checkpoint_resolution = apply_progress_checkpoint(
                            next_checkpoint, progress_update
                        )
                        if checkpoint_resolution.decision is ProgressCheckpointDecision.GAP:
                            return _state_reject(
                                outcome,
                                progress,
                                "progress update has a sequence gap",
                                conflict=False,
                            )
                        if checkpoint_resolution.decision is ProgressCheckpointDecision.CONFLICT:
                            return _state_reject(
                                outcome,
                                progress,
                                "progress update conflicts with the existing checkpoint",
                                conflict=True,
                            )
                        next_checkpoint = checkpoint_resolution.checkpoint
                        next_progress = next_checkpoint.state
                        changed = changed or next_progress != progress
                    if cancellation is not None:
                        next_progress = request_cancellation(next_progress, cancellation)
                        changed = changed or next_progress != progress
                        next_checkpoint = ProgressCheckpoint(
                            next_progress, next_checkpoint.applied_update_fingerprints
                        )
                except (TypeError, ValueError) as error:
                    return _state_reject(outcome, progress, str(error), conflict=False)
                if not changed:
                    return StateMutationResolution(
                        StateMutationDecision.REPLAY_EXISTING, outcome, progress
                    )
                if next_outcome != outcome:
                    await self._update_outcome(session, owner_id, outcome, next_outcome)
                if next_checkpoint != checkpoint:
                    await self._update_progress(session, owner_id, checkpoint, next_checkpoint)
                return StateMutationResolution(
                    StateMutationDecision.APPLIED,
                    next_outcome,
                    next_progress,
                )

    async def _load_pair(
        self, session: AsyncSessionLike, owner_id: str, attempt_id: str
    ) -> tuple[ExecutionOutcome, ExecutionProgressState, ProgressCheckpoint] | None:
        outcome = await self._load_outcome(session, owner_id, attempt_id)
        progress = await self._load_progress(session, owner_id, attempt_id)
        if outcome is None and progress is None:
            return None
        if outcome is None or progress is None:
            raise ValueError("PostgreSQL execution state is partially persisted")
        checkpoint = progress
        _validate_pair(outcome, checkpoint.state)
        return outcome, checkpoint.state, checkpoint

    async def _load_outcome(
        self, session: AsyncSessionLike, owner_id: str, attempt_id: str
    ) -> ExecutionOutcome | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, attempt_id, submission_id, sequence, status,
                       updated_at, result_digest, error_json, state_fingerprint
                FROM {self._schema.outcome_table}
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
            raise ValueError("PostgreSQL outcome query returned duplicate keys")
        row = rows[0]
        outcome = _decode_outcome(row)
        if row.get("owner_id") != owner_id or row.get("attempt_id") != attempt_id:
            raise ValueError("PostgreSQL outcome owner/attempt identity drifted")
        if row.get("state_fingerprint") != outcome.fingerprint:
            raise ValueError("PostgreSQL outcome fingerprint does not match bytes")
        return outcome

    async def _load_progress(
        self, session: AsyncSessionLike, owner_id: str, attempt_id: str
    ) -> ProgressCheckpoint | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, attempt_id, sequence, phase, completed_units,
                       total_units, cancellation_requested, updated_at,
                       applied_update_fingerprints_json, checkpoint_fingerprint
                FROM {self._schema.progress_table}
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
            raise ValueError("PostgreSQL progress query returned duplicate keys")
        row = rows[0]
        checkpoint = _decode_progress(row)
        if row.get("owner_id") != owner_id or row.get("attempt_id") != attempt_id:
            raise ValueError("PostgreSQL progress owner/attempt identity drifted")
        if row.get("checkpoint_fingerprint") != checkpoint.fingerprint:
            raise ValueError("PostgreSQL progress fingerprint does not match bytes")
        return checkpoint

    async def _insert_outcome(
        self, session: AsyncSessionLike, owner_id: str, outcome: ExecutionOutcome
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.outcome_table}
                    (owner_id, attempt_id, submission_id, sequence, status, updated_at,
                     result_digest, error_json, state_fingerprint)
                VALUES (:owner_id, :attempt_id, :submission_id, :sequence, :status, :updated_at,
                        :result_digest, :error_json, :state_fingerprint)
                ON CONFLICT (owner_id, attempt_id) DO NOTHING
                """
            ),
            _outcome_values(owner_id, outcome),
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL outcome insert lost a uniqueness race")

    async def _insert_progress(
        self, session: AsyncSessionLike, owner_id: str, checkpoint: ProgressCheckpoint
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.progress_table}
                    (owner_id, attempt_id, sequence, phase, completed_units, total_units,
                     cancellation_requested, updated_at, applied_update_fingerprints_json,
                     checkpoint_fingerprint)
                VALUES (:owner_id, :attempt_id, :sequence, :phase, :completed_units, :total_units,
                        :cancellation_requested, :updated_at, :applied_update_fingerprints_json,
                        :checkpoint_fingerprint)
                ON CONFLICT (owner_id, attempt_id) DO NOTHING
                """
            ),
            _progress_values(owner_id, checkpoint),
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL progress insert lost a uniqueness race")

    async def _update_outcome(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        current: ExecutionOutcome,
        next_state: ExecutionOutcome,
    ) -> None:
        values = _outcome_values(owner_id, next_state)
        values.update(
            expected_state_fingerprint=current.fingerprint,
        )
        result = await session.execute(
            _statement(
                f"""
                UPDATE {self._schema.outcome_table}
                SET submission_id = :submission_id, sequence = :sequence, status = :status,
                    updated_at = :updated_at, result_digest = :result_digest,
                    error_json = :error_json, state_fingerprint = :state_fingerprint
                WHERE owner_id = :owner_id AND attempt_id = :attempt_id
                  AND state_fingerprint = :expected_state_fingerprint
                """
            ),
            values,
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL outcome compare-and-set lost a race")

    async def _update_progress(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        current: ProgressCheckpoint,
        next_checkpoint: ProgressCheckpoint,
    ) -> None:
        values = _progress_values(owner_id, next_checkpoint)
        values.update(expected_checkpoint_fingerprint=current.fingerprint)
        result = await session.execute(
            _statement(
                f"""
                UPDATE {self._schema.progress_table}
                SET sequence = :sequence, phase = :phase, completed_units = :completed_units,
                    total_units = :total_units, cancellation_requested = :cancellation_requested,
                    updated_at = :updated_at, applied_update_fingerprints_json = :applied_update_fingerprints_json,
                    checkpoint_fingerprint = :checkpoint_fingerprint
                WHERE owner_id = :owner_id AND attempt_id = :attempt_id
                  AND checkpoint_fingerprint = :expected_checkpoint_fingerprint
                """
            ),
            values,
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL progress compare-and-set lost a race")


def _validate_pair(outcome: ExecutionOutcome, progress: ExecutionProgressState) -> None:
    if not isinstance(outcome, ExecutionOutcome):
        raise TypeError("outcome must be an ExecutionOutcome")
    if not isinstance(progress, ExecutionProgressState):
        raise TypeError("progress must be an ExecutionProgressState")
    if outcome.attempt_id != progress.attempt_id:
        raise ValueError("outcome and progress must reference the same attempt")


def _state_reject(
    outcome: ExecutionOutcome,
    progress: ExecutionProgressState,
    reason: str,
    *,
    conflict: bool,
) -> StateMutationResolution:
    return StateMutationResolution(
        StateMutationDecision.CONFLICT if conflict else StateMutationDecision.REJECT,
        outcome,
        progress,
        reason,
    )


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _outcome_values(owner_id: str, outcome: ExecutionOutcome) -> dict[str, Any]:
    return {
        "owner_id": owner_id,
        "attempt_id": outcome.attempt_id,
        "submission_id": outcome.submission_id,
        "sequence": outcome.sequence,
        "status": outcome.status.value,
        "updated_at": _encode_datetime(outcome.updated_at),
        "result_digest": outcome.result_digest,
        "error_json": _encode_error(outcome.error),
        "state_fingerprint": outcome.fingerprint,
    }


def _progress_values(owner_id: str, checkpoint: ProgressCheckpoint) -> dict[str, Any]:
    state = checkpoint.state
    return {
        "owner_id": owner_id,
        "attempt_id": state.attempt_id,
        "sequence": state.sequence,
        "phase": state.phase.value,
        "completed_units": state.completed_units,
        "total_units": state.total_units,
        "cancellation_requested": state.cancellation_requested,
        "updated_at": _encode_datetime(state.updated_at),
        "applied_update_fingerprints_json": json.dumps(
            sorted(checkpoint.applied_update_fingerprints),
            separators=(",", ":"),
        ),
        "checkpoint_fingerprint": checkpoint.fingerprint,
    }


def _decode_outcome(row: Mapping[str, Any]) -> ExecutionOutcome:
    try:
        error = _decode_error(row.get("error_json"))
        outcome = ExecutionOutcome(
            row["submission_id"],
            row["attempt_id"],
            int(row["sequence"]),
            OutcomeStatus(row["status"]),
            _decode_datetime(row["updated_at"], "updated_at"),
            row.get("result_digest"),
            error,
        )
        return outcome
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("PostgreSQL outcome row is malformed") from error


def _decode_progress(row: Mapping[str, Any]) -> ProgressCheckpoint:
    try:
        raw_fingerprints = row["applied_update_fingerprints_json"]
        if isinstance(raw_fingerprints, str):
            raw_fingerprints = json.loads(raw_fingerprints)
        if not isinstance(raw_fingerprints, list) or any(
            not isinstance(item, str) for item in raw_fingerprints
        ):
            raise ValueError("progress update identity list is malformed")
        state = ExecutionProgressState(
            row["attempt_id"],
            int(row["sequence"]),
            ProgressPhase(row["phase"]),
            int(row["completed_units"]),
            int(row["total_units"]),
            row["cancellation_requested"],
            _decode_datetime(row["updated_at"], "updated_at"),
        )
        return ProgressCheckpoint(state, frozenset(raw_fingerprints))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("PostgreSQL progress row is malformed") from error


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


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "PostgresExecutionStateAdapter",
    "PostgresExecutionStateSchema",
    "StateMutationDecision",
    "StateMutationResolution",
]
