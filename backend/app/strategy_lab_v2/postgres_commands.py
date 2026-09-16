"""PostgreSQL adapter for owner-scoped retry/cancellation command receipts.

The command state machine remains engine-neutral in :mod:`commands`.  This
module supplies the durable adapter boundary: it locks one attempt's command
ledger, reads the latest execution state through an injected state reader,
resolves idempotency and terminal preconditions, and stores an accepted receipt
in the same transaction.  It never starts a worker or applies the cancellation
or retry effect itself.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.strategy_lab_v2.api_contracts import ApiError, ApiErrorCode
from app.strategy_lab_v2.api_router import ApiAdapterError
from app.strategy_lab_v2.commands import (
    ExecutionCommand,
    ExecutionCommandDecision,
    ExecutionCommandLedger,
    ExecutionCommandReceipt,
    ExecutionCommandResolution,
    resolve_execution_command,
)
from app.strategy_lab_v2.outcomes import ExecutionOutcome
from app.strategy_lab_v2.progress import ExecutionProgressState


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class ExecutionStateReader(Protocol):
    def __call__(
        self, *, principal: Any, attempt_id: str
    ) -> Awaitable[ExecutionCommandContext | None] | ExecutionCommandContext | None: ...


@dataclass(frozen=True, slots=True)
class ExecutionCommandContext:
    """Latest outcome/progress pair used to authorize one command."""

    outcome: ExecutionOutcome
    progress: ExecutionProgressState

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ExecutionOutcome):
            raise TypeError("outcome must be an ExecutionOutcome")
        if not isinstance(self.progress, ExecutionProgressState):
            raise TypeError("progress must be an ExecutionProgressState")
        if self.outcome.attempt_id != self.progress.attempt_id:
            raise ValueError("outcome and progress must reference the same attempt")


@dataclass(frozen=True, slots=True)
class PostgresCommandSchema:
    """Additive DDL contract for durable command receipts."""

    command_table: str = "strategy_lab_v2_execution_commands"

    def __post_init__(self) -> None:
        if not isinstance(self.command_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.command_table
        ):
            raise ValueError("command_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.command_table} (
                owner_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                command_id TEXT NOT NULL,
                command_fingerprint TEXT NOT NULL,
                receipt_fingerprint TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                effect TEXT NOT NULL,
                accepted_at TEXT NOT NULL,
                PRIMARY KEY (owner_id, idempotency_key),
                UNIQUE (owner_id, command_id)
            )
            """,
        )


class PostgresCommandAdapter:
    """Persist accepted command receipts without applying their effects."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        state_reader: ExecutionStateReader,
        *,
        schema: PostgresCommandSchema | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        if not callable(state_reader):
            raise TypeError("state_reader must be callable")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._session_factory = session_factory
        self._state_reader = state_reader
        self._schema = schema or PostgresCommandSchema()
        self._clock = clock

    @property
    def schema(self) -> PostgresCommandSchema:
        return self._schema

    async def command(
        self,
        *,
        principal: Any,
        request_id: str = "adapter",
        idempotency_key: str,
        command: ExecutionCommand,
    ) -> ExecutionCommandResolution:
        """Resolve and persist one owner-scoped command receipt atomically."""

        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ApiAdapterError(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "command Idempotency-Key is required",
                    request_id=request_id,
                    status_code=400,
                )
            )
        if len(idempotency_key) > 256:
            raise ApiAdapterError(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "command Idempotency-Key must not exceed 256 characters",
                    request_id=request_id,
                    status_code=400,
                )
            )
        if not isinstance(command, ExecutionCommand):
            raise TypeError("command must be an ExecutionCommand")
        owner_id = _principal_id(principal, request_id)
        accepted_at = self._clock()
        if accepted_at.tzinfo is None or accepted_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")

        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                ledger, by_idempotency = await self._load_ledger(
                    session, owner_id, command.attempt_id
                )
                prior_for_key = by_idempotency.get(idempotency_key)
                if prior_for_key is not None and prior_for_key.command_fingerprint != command.fingerprint:
                    raise ApiAdapterError(
                        _api_error(
                            ApiErrorCode.IDEMPOTENCY_CONFLICT,
                            "command Idempotency-Key is already bound to different content",
                            request_id=request_id,
                            status_code=409,
                        )
                    )
                context = await _resolve(self._state_reader(principal=principal, attempt_id=command.attempt_id))
                if context is None:
                    raise ApiAdapterError(
                        _api_error(
                            ApiErrorCode.NOT_FOUND,
                            "execution attempt was not found",
                            request_id=request_id,
                            status_code=404,
                        )
                    )
                if not isinstance(context, ExecutionCommandContext):
                    raise TypeError("state_reader returned an invalid execution context")
                resolution = resolve_execution_command(
                    ledger,
                    command,
                    context.outcome,
                    context.progress,
                    accepted_at=accepted_at,
                )
                if resolution.decision in {
                    ExecutionCommandDecision.CONFLICT,
                    ExecutionCommandDecision.REJECT,
                }:
                    code = (
                        ApiErrorCode.IDEMPOTENCY_CONFLICT
                        if resolution.decision is ExecutionCommandDecision.CONFLICT
                        else ApiErrorCode.PRECONDITION_FAILED
                    )
                    raise ApiAdapterError(
                        _api_error(
                            code,
                            resolution.rejection_reason or "execution command was rejected",
                            request_id=request_id,
                            status_code=409,
                        )
                    )
                receipt = resolution.receipt
                if receipt is None:  # pragma: no cover - guarded by pure resolution
                    raise ValueError("command resolution omitted its receipt")
                if resolution.decision is ExecutionCommandDecision.ACCEPT:
                    await self._insert_receipt(session, owner_id, idempotency_key, receipt)
                return resolution

    async def _load_ledger(
        self, session: AsyncSessionLike, owner_id: str, attempt_id: str
    ) -> tuple[ExecutionCommandLedger, dict[str, ExecutionCommandReceipt]]:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, idempotency_key, command_id, command_fingerprint,
                       receipt_fingerprint, attempt_id, kind, effect, accepted_at
                FROM {self._schema.command_table}
                WHERE owner_id = :owner_id AND attempt_id = :attempt_id
                ORDER BY command_id ASC
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "attempt_id": attempt_id},
        )
        rows = list(result.mappings())
        receipts: list[ExecutionCommandReceipt] = []
        by_idempotency: dict[str, ExecutionCommandReceipt] = {}
        for row in rows:
            if row.get("owner_id") != owner_id:
                raise ValueError("PostgreSQL command owner identity drifted")
            if row.get("attempt_id") != attempt_id:
                raise ValueError("PostgreSQL command attempt identity drifted")
            receipt = _decode_receipt(row)
            key = row["idempotency_key"]
            if not isinstance(key, str) or not key.strip() or key in by_idempotency:
                raise ValueError("PostgreSQL command idempotency identity is malformed")
            by_idempotency[key] = receipt
            receipts.append(receipt)
        return ExecutionCommandLedger(tuple(receipts)), by_idempotency

    async def _insert_receipt(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        idempotency_key: str,
        receipt: ExecutionCommandReceipt,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.command_table}
                    (owner_id, idempotency_key, command_id, command_fingerprint,
                     receipt_fingerprint, attempt_id, kind, effect, accepted_at)
                VALUES (:owner_id, :idempotency_key, :command_id, :command_fingerprint,
                        :receipt_fingerprint, :attempt_id, :kind, :effect, :accepted_at)
                ON CONFLICT (owner_id, idempotency_key) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "idempotency_key": idempotency_key,
                "command_id": receipt.command_id,
                "command_fingerprint": receipt.command_fingerprint,
                "receipt_fingerprint": receipt.fingerprint,
                "attempt_id": receipt.attempt_id,
                "kind": receipt.kind.value,
                "effect": receipt.effect.value,
                "accepted_at": _encode_datetime(receipt.accepted_at),
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL command insert lost an idempotency race")


async def _resolve(value: Awaitable[Any] | Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


def _principal_id(principal: Any, request_id: str) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.AUTHORIZATION_REQUIRED,
                "authenticated principal identity is required",
                request_id=request_id,
                status_code=401,
            )
        )
    return value.strip()


def _encode_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _decode_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("accepted_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("accepted_at is malformed") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("accepted_at must be timezone-aware")
    return parsed


def _decode_receipt(row: Mapping[str, Any]) -> ExecutionCommandReceipt:
    from app.strategy_lab_v2.commands import CommandEffect, ExecutionCommandKind

    try:
        receipt = ExecutionCommandReceipt(
            command_id=row["command_id"],
            command_fingerprint=row["command_fingerprint"],
            attempt_id=row["attempt_id"],
            kind=ExecutionCommandKind(row["kind"]),
            effect=CommandEffect(row["effect"]),
            accepted_at=_decode_datetime(row["accepted_at"]),
        )
        if row["receipt_fingerprint"] != receipt.fingerprint:
            raise ValueError("command receipt fingerprint does not match bytes")
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL command row is malformed") from error
    return receipt


def _api_error(
    code: ApiErrorCode,
    message: str,
    *,
    request_id: str,
    status_code: int,
) -> ApiError:
    return ApiError(code=code, message=message, request_id=request_id, status_code=status_code)


__all__ = [
    "ExecutionCommandContext",
    "ExecutionStateReader",
    "PostgresCommandAdapter",
    "PostgresCommandSchema",
]
