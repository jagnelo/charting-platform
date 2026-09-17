"""Owner-scoped PostgreSQL persistence for strategy runtime evidence.

The runtime contracts remain storage-neutral in :mod:`runtime_execution` and
:mod:`runtime_result_adapter`.  This adapter provides the durable boundary for
the accepted state and its immutable update receipts.  Every transition locks
the current state, resolves the pure monotonic transition, and commits the
receipt plus compare-and-set state in one transaction.  It never starts a
process, writes artifact bytes, or publishes an official result.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.engine_execution import NautilusExecutionPlan
from app.strategy_lab_v2.nautilus_runner import NautilusRunResult
from app.strategy_lab_v2.runtime_execution import (
    RuntimeExecutionDecision,
    RuntimeExecutionPhase,
    RuntimeExecutionState,
    RuntimeExecutionUpdate,
    apply_runtime_execution_update,
)
from app.strategy_lab_v2.runtime_result_adapter import (
    RuntimeResultDecision,
    materialize_nautilus_result,
    materialize_sandbox_result,
)
from app.strategy_lab_v2.sandbox import SandboxCommandPlan
from app.strategy_lab_v2.sandbox_execution import SandboxRunResult


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class RuntimeStateDecision(StrEnum):
    REGISTERED = "registered"
    APPLIED = "applied"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    NOT_FOUND = "not_found"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class RuntimeStateResolution:
    """Authenticated runtime state returned by one durable operation."""

    decision: RuntimeStateDecision
    state: RuntimeExecutionState | None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RuntimeStateDecision):
            raise TypeError("decision must be a RuntimeStateDecision")
        if self.state is not None and not isinstance(self.state, RuntimeExecutionState):
            raise TypeError("state must be a RuntimeExecutionState or None")
        failed = {
            RuntimeStateDecision.CONFLICT,
            RuntimeStateDecision.NOT_FOUND,
            RuntimeStateDecision.REJECT,
        }
        if self.decision in failed and not self.rejection_reason:
            raise ValueError("failed runtime resolutions require a reason")
        if self.decision not in failed and self.rejection_reason:
            raise ValueError("successful runtime resolutions cannot contain a reason")


@dataclass(frozen=True, slots=True)
class PostgresRuntimeExecutionSchema:
    """Explicit additive DDL for current runtime state and update receipts."""

    state_table: str = "strategy_lab_v2_runtime_execution"
    update_table: str = "strategy_lab_v2_runtime_updates"

    def __post_init__(self) -> None:
        for name, value in (("state_table", self.state_table), ("update_table", self.update_table)):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
                raise ValueError(f"{name} must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.state_table} (
                owner_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                profile_fingerprint TEXT NOT NULL,
                output_limit_bytes BIGINT NOT NULL,
                sequence BIGINT NOT NULL,
                phase TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                output_digest TEXT NULL,
                output_bytes BIGINT NULL,
                error_digest TEXT NULL,
                state_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, attempt_id)
            )
            """,
            f"""
            CREATE TABLE {self.update_table} (
                owner_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                sequence BIGINT NOT NULL,
                phase TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                output_digest TEXT NULL,
                output_bytes BIGINT NULL,
                error_digest TEXT NULL,
                update_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, attempt_id, sequence),
                UNIQUE (owner_id, attempt_id, update_fingerprint)
            )
            """,
        )


class PostgresRuntimeExecutionAdapter:
    """Persist, replay, and authenticate runtime execution evidence."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresRuntimeExecutionSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresRuntimeExecutionSchema()

    @property
    def schema(self) -> PostgresRuntimeExecutionSchema:
        return self._schema

    async def initialize(
        self, *, principal: Any, state: RuntimeExecutionState
    ) -> RuntimeStateResolution:
        """Register an accepted sequence-zero state or replay its exact identity."""

        if not isinstance(state, RuntimeExecutionState):
            raise TypeError("state must be a RuntimeExecutionState")
        if state.sequence != 0 or state.phase is not RuntimeExecutionPhase.ACCEPTED:
            raise ValueError("runtime initialization requires a sequence-zero accepted state")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_state(session, owner_id, state.attempt_id)
                if current is None:
                    await self._insert_state(session, owner_id, state)
                    return RuntimeStateResolution(RuntimeStateDecision.REGISTERED, state)
                if current != state:
                    return RuntimeStateResolution(
                        RuntimeStateDecision.CONFLICT,
                        current,
                        "runtime attempt is already bound to different state",
                    )
                return RuntimeStateResolution(RuntimeStateDecision.REPLAY_EXISTING, current)

    async def load(
        self, *, principal: Any, attempt_id: str
    ) -> RuntimeExecutionState | None:
        """Read one owner-scoped runtime state and verify its stored identity."""

        _validate_attempt(attempt_id)
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_state(session, owner_id, attempt_id)

    async def load_for_request(
        self, *, principal: Any, request_fingerprint: str
    ) -> RuntimeExecutionState | None:
        """Read one runtime state by its immutable request identity."""

        require_sha256_digest(request_fingerprint, field_name="request_fingerprint")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_state(
                    session, owner_id, request_fingerprint, by_request=True
                )

    async def load_updates(
        self, *, principal: Any, attempt_id: str
    ) -> tuple[RuntimeExecutionUpdate, ...]:
        """Read immutable update receipts in sequence order for an attempt."""

        _validate_attempt(attempt_id)
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, attempt_id, request_fingerprint, sequence, phase,
                               observed_at, output_digest, output_bytes, error_digest,
                               update_fingerprint
                        FROM {self._schema.update_table}
                        WHERE owner_id = :owner_id AND attempt_id = :attempt_id
                        ORDER BY sequence ASC
                        FOR UPDATE
                        """
                    ),
                    {"owner_id": owner_id, "attempt_id": attempt_id},
                )
                updates = tuple(
                    _authenticate_update(_decode_update(row), row, owner_id, attempt_id)
                    for row in result.mappings()
                )
                ordered = tuple(sorted(updates, key=lambda item: item.sequence))
                if updates != ordered:
                    raise ValueError("PostgreSQL runtime updates are not deterministically ordered")
                return updates

    async def apply_update(
        self, *, principal: Any, update: RuntimeExecutionUpdate
    ) -> RuntimeStateResolution:
        """Apply one monotonic update with exact replay and conflict detection."""

        if not isinstance(update, RuntimeExecutionUpdate):
            raise TypeError("update must be a RuntimeExecutionUpdate")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_state(session, owner_id, update.attempt_id)
                if current is None:
                    return RuntimeStateResolution(
                        RuntimeStateDecision.NOT_FOUND,
                        None,
                        "runtime execution state was not found",
                    )
                if update.request_fingerprint != current.request_fingerprint:
                    return RuntimeStateResolution(
                        RuntimeStateDecision.REJECT,
                        current,
                        "runtime update references a different request",
                    )
                existing = await self._load_update(
                    session, owner_id, update.attempt_id, update.sequence
                )
                if existing is not None:
                    if existing != update:
                        return RuntimeStateResolution(
                            RuntimeStateDecision.CONFLICT,
                            current,
                            "runtime update sequence is already bound to different content",
                        )
                    return RuntimeStateResolution(RuntimeStateDecision.REPLAY_EXISTING, current)
                try:
                    resolution = apply_runtime_execution_update(current, update)
                except (TypeError, ValueError) as error:
                    return RuntimeStateResolution(RuntimeStateDecision.REJECT, current, str(error))
                if resolution.decision is RuntimeExecutionDecision.REPLAY_EXISTING:
                    return RuntimeStateResolution(RuntimeStateDecision.REPLAY_EXISTING, current)
                await self._insert_update(session, owner_id, update)
                await self._update_state(session, owner_id, current, resolution.state)
                return RuntimeStateResolution(RuntimeStateDecision.APPLIED, resolution.state)

    async def materialize_sandbox_result(
        self,
        *,
        principal: Any,
        sandbox_plan: SandboxCommandPlan,
        sandbox_result: SandboxRunResult,
        observed_at: datetime,
    ) -> RuntimeStateResolution:
        """Atomically persist running and terminal evidence from one sandbox result."""

        if not isinstance(sandbox_plan, SandboxCommandPlan):
            raise TypeError("sandbox_plan must be a SandboxCommandPlan")
        if not isinstance(sandbox_result, SandboxRunResult):
            raise TypeError("sandbox_result must be a SandboxRunResult")
        _aware(observed_at, "observed_at")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_state(
                    session, owner_id, sandbox_result.request_fingerprint, by_request=True
                )
                if current is None:
                    return RuntimeStateResolution(
                        RuntimeStateDecision.NOT_FOUND,
                        None,
                        "runtime execution state was not found",
                    )
                pure = materialize_sandbox_result(
                    current, sandbox_plan, sandbox_result, observed_at=observed_at
                )
                if pure.decision is RuntimeResultDecision.REJECT:
                    return RuntimeStateResolution(
                        RuntimeStateDecision.REJECT, current, pure.rejection_reason
                    )
                if pure.decision is RuntimeResultDecision.REPLAY_EXISTING:
                    return RuntimeStateResolution(RuntimeStateDecision.REPLAY_EXISTING, current)
                updates = _materialization_updates(current, sandbox_result, observed_at)
                next_state = current
                for update in updates:
                    existing = await self._load_update(
                        session, owner_id, update.attempt_id, update.sequence
                    )
                    if existing is not None:
                        if existing != update:
                            return RuntimeStateResolution(
                                RuntimeStateDecision.CONFLICT,
                                current,
                                "runtime materialization sequence is already bound to different content",
                            )
                        next_state = apply_runtime_execution_update(next_state, update).state
                        continue
                    transition = apply_runtime_execution_update(next_state, update)
                    await self._insert_update(session, owner_id, update)
                    await self._update_state(session, owner_id, next_state, transition.state)
                    next_state = transition.state
                return RuntimeStateResolution(RuntimeStateDecision.APPLIED, next_state)

    async def materialize_nautilus_result(
        self,
        *,
        principal: Any,
        execution_plan: NautilusExecutionPlan,
        sandbox_plan: SandboxCommandPlan,
        run_result: NautilusRunResult,
        observed_at: datetime,
    ) -> RuntimeStateResolution:
        """Envelope-check and atomically persist a gated Nautilus result."""

        if not isinstance(execution_plan, NautilusExecutionPlan):
            raise TypeError("execution_plan must be a NautilusExecutionPlan")
        if not isinstance(run_result, NautilusRunResult):
            raise TypeError("run_result must be a NautilusRunResult")
        if run_result.sandbox_result is None:
            raise ValueError("executed Nautilus results require sandbox evidence")
        # The pure bridge needs the current state; resolve it before invoking it
        # so rejected pre-process envelopes never create a runtime failure.
        state = await self.load_for_request(
            principal=principal,
            request_fingerprint=run_result.sandbox_result.request_fingerprint,
        )
        if state is None:
            return RuntimeStateResolution(
                RuntimeStateDecision.NOT_FOUND, None, "runtime execution state was not found"
            )
        checked = materialize_nautilus_result(
            state, execution_plan, sandbox_plan, run_result, observed_at=observed_at
        )
        if checked.decision is RuntimeResultDecision.REJECT:
            return RuntimeStateResolution(RuntimeStateDecision.REJECT, state, checked.rejection_reason)
        if checked.decision is RuntimeResultDecision.REPLAY_EXISTING:
            return RuntimeStateResolution(RuntimeStateDecision.REPLAY_EXISTING, state)
        return await self.materialize_sandbox_result(
            principal=principal,
            sandbox_plan=sandbox_plan,
            sandbox_result=run_result.sandbox_result,
            observed_at=observed_at,
        )

    async def _load_state(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        key: str,
        *,
        by_request: bool = False,
    ) -> RuntimeExecutionState | None:
        column = "request_fingerprint" if by_request else "attempt_id"
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, attempt_id, request_fingerprint, profile_fingerprint,
                       output_limit_bytes, sequence, phase, updated_at, output_digest,
                       output_bytes, error_digest, state_fingerprint
                FROM {self._schema.state_table}
                WHERE owner_id = :owner_id AND {column} = :lookup_key
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "lookup_key": key},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL runtime state query returned duplicate keys")
        row = rows[0]
        state = _decode_state(row)
        if row.get("owner_id") != owner_id or row.get("attempt_id") != state.attempt_id:
            raise ValueError("PostgreSQL runtime state owner/attempt identity drifted")
        if by_request and state.request_fingerprint != key:
            raise ValueError("PostgreSQL runtime state request identity drifted")
        if not by_request and state.attempt_id != key:
            raise ValueError("PostgreSQL runtime state attempt identity drifted")
        if row.get("state_fingerprint") != state.fingerprint:
            raise ValueError("PostgreSQL runtime state fingerprint does not match bytes")
        return state

    async def _load_update(
        self, session: AsyncSessionLike, owner_id: str, attempt_id: str, sequence: int
    ) -> RuntimeExecutionUpdate | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, attempt_id, request_fingerprint, sequence, phase,
                       observed_at, output_digest, output_bytes, error_digest,
                       update_fingerprint
                FROM {self._schema.update_table}
                WHERE owner_id = :owner_id AND attempt_id = :attempt_id
                  AND sequence = :sequence
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "attempt_id": attempt_id, "sequence": sequence},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL runtime update query returned duplicate keys")
        row = rows[0]
        update = _decode_update(row)
        return _authenticate_update(update, row, owner_id, attempt_id)

    async def _insert_state(
        self, session: AsyncSessionLike, owner_id: str, state: RuntimeExecutionState
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.state_table}
                    (owner_id, attempt_id, request_fingerprint, profile_fingerprint,
                     output_limit_bytes, sequence, phase, updated_at, output_digest,
                     output_bytes, error_digest, state_fingerprint)
                VALUES (:owner_id, :attempt_id, :request_fingerprint, :profile_fingerprint,
                        :output_limit_bytes, :sequence, :phase, :updated_at, :output_digest,
                        :output_bytes, :error_digest, :state_fingerprint)
                ON CONFLICT (owner_id, attempt_id) DO NOTHING
                """
            ),
            _state_values(owner_id, state),
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL runtime state insert lost a uniqueness race")

    async def _insert_update(
        self, session: AsyncSessionLike, owner_id: str, update: RuntimeExecutionUpdate
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.update_table}
                    (owner_id, attempt_id, request_fingerprint, sequence, phase,
                     observed_at, output_digest, output_bytes, error_digest,
                     update_fingerprint)
                VALUES (:owner_id, :attempt_id, :request_fingerprint, :sequence, :phase,
                        :observed_at, :output_digest, :output_bytes, :error_digest,
                        :update_fingerprint)
                ON CONFLICT (owner_id, attempt_id, sequence) DO NOTHING
                """
            ),
            _update_values(owner_id, update),
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL runtime update insert lost a uniqueness race")

    async def _update_state(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        current: RuntimeExecutionState,
        next_state: RuntimeExecutionState,
    ) -> None:
        values = _state_values(owner_id, next_state)
        values["expected_state_fingerprint"] = current.fingerprint
        result = await session.execute(
            _statement(
                f"""
                UPDATE {self._schema.state_table}
                SET request_fingerprint = :request_fingerprint,
                    profile_fingerprint = :profile_fingerprint,
                    output_limit_bytes = :output_limit_bytes, sequence = :sequence,
                    phase = :phase, updated_at = :updated_at, output_digest = :output_digest,
                    output_bytes = :output_bytes, error_digest = :error_digest,
                    state_fingerprint = :state_fingerprint
                WHERE owner_id = :owner_id AND attempt_id = :attempt_id
                  AND state_fingerprint = :expected_state_fingerprint
                """
            ),
            values,
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL runtime state compare-and-set lost a race")


def _materialization_updates(
    state: RuntimeExecutionState,
    result: SandboxRunResult,
    observed_at: datetime,
) -> tuple[RuntimeExecutionUpdate, RuntimeExecutionUpdate]:
    running = RuntimeExecutionUpdate(
        state.request_fingerprint,
        state.attempt_id,
        state.sequence + 1,
        RuntimeExecutionPhase.RUNNING,
        observed_at,
    )
    if result.status.value == "succeeded":
        terminal = RuntimeExecutionUpdate(
            state.request_fingerprint,
            state.attempt_id,
            state.sequence + 2,
            RuntimeExecutionPhase.SUCCEEDED,
            observed_at,
            result.stdout_digest,
            result.stdout_bytes,
        )
    else:
        from app.strategy_lab_v2.canonical import content_digest

        terminal = RuntimeExecutionUpdate(
            state.request_fingerprint,
            state.attempt_id,
            state.sequence + 2,
            RuntimeExecutionPhase.FAILED,
            observed_at,
            error_digest=result.error_digest
            or content_digest(f"sandbox process status: {result.status.value}"),
        )
    return running, terminal


def _state_values(owner_id: str, state: RuntimeExecutionState) -> dict[str, Any]:
    return {
        "owner_id": owner_id,
        "attempt_id": state.attempt_id,
        "request_fingerprint": state.request_fingerprint,
        "profile_fingerprint": state.profile_fingerprint,
        "output_limit_bytes": state.output_limit_bytes,
        "sequence": state.sequence,
        "phase": state.phase.value,
        "updated_at": _encode_datetime(state.updated_at),
        "output_digest": state.output_digest,
        "output_bytes": state.output_bytes,
        "error_digest": state.error_digest,
        "state_fingerprint": state.fingerprint,
    }


def _update_values(owner_id: str, update: RuntimeExecutionUpdate) -> dict[str, Any]:
    return {
        "owner_id": owner_id,
        "attempt_id": update.attempt_id,
        "request_fingerprint": update.request_fingerprint,
        "sequence": update.sequence,
        "phase": update.phase.value,
        "observed_at": _encode_datetime(update.observed_at),
        "output_digest": update.output_digest,
        "output_bytes": update.output_bytes,
        "error_digest": update.error_digest,
        "update_fingerprint": update.fingerprint,
    }


def _decode_state(row: Mapping[str, Any]) -> RuntimeExecutionState:
    try:
        return RuntimeExecutionState(
            row["request_fingerprint"],
            row["attempt_id"],
            row["profile_fingerprint"],
            int(row["output_limit_bytes"]),
            int(row["sequence"]),
            RuntimeExecutionPhase(row["phase"]),
            _decode_datetime(row["updated_at"], "updated_at"),
            row.get("output_digest"),
            None if row.get("output_bytes") is None else int(row["output_bytes"]),
            row.get("error_digest"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL runtime state row is malformed") from error


def _decode_update(row: Mapping[str, Any]) -> RuntimeExecutionUpdate:
    try:
        return RuntimeExecutionUpdate(
            row["request_fingerprint"],
            row["attempt_id"],
            int(row["sequence"]),
            RuntimeExecutionPhase(row["phase"]),
            _decode_datetime(row["observed_at"], "observed_at"),
            row.get("output_digest"),
            None if row.get("output_bytes") is None else int(row["output_bytes"]),
            row.get("error_digest"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL runtime update row is malformed") from error


def _authenticate_update(
    update: RuntimeExecutionUpdate,
    row: Mapping[str, Any],
    owner_id: str,
    attempt_id: str,
) -> RuntimeExecutionUpdate:
    if row.get("owner_id") != owner_id or row.get("attempt_id") != attempt_id:
        raise ValueError("PostgreSQL runtime update owner/attempt identity drifted")
    if row.get("update_fingerprint") != update.fingerprint:
        raise ValueError("PostgreSQL runtime update fingerprint does not match bytes")
    return update


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _validate_attempt(attempt_id: str) -> None:
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise ValueError("attempt_id must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _encode_datetime(value: datetime) -> str:
    _aware(value, "datetime")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _decode_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} is malformed") from error
    _aware(parsed, field_name)
    return parsed


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "PostgresRuntimeExecutionAdapter",
    "PostgresRuntimeExecutionSchema",
    "RuntimeStateDecision",
    "RuntimeStateResolution",
]
