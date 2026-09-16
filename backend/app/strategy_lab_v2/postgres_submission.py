"""PostgreSQL adapter for idempotent API submission and outbox staging.

The adapter is deliberately registration-neutral: it maps the package-owned
submission/dispatch contracts to one SQLAlchemy async transaction but does not
create tables, register models, enqueue Redis messages, or start workers.  A
future application wiring layer can inject this adapter into ``api_router``
after the additive migration and authentication dependency are reconciled.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.strategy_lab_v2.api_contracts import ApiError, ApiErrorCode
from app.strategy_lab_v2.api_router import ApiAdapterError, SubmissionServiceResult
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.submission_dispatch import (
    SubmissionDispatchDecision,
    SubmissionReceiptLedger,
    resolve_submission_dispatch,
)
from app.strategy_lab_v2.submissions import (
    SubmissionDecision,
    SubmissionReceipt,
    SubmissionRequest,
    resolve_submission,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class PostgresSubmissionSchema:
    """Additive DDL contract for submission receipts and durable dispatch intents."""

    submission_table: str = "strategy_lab_v2_submissions"
    dispatch_table: str = "strategy_lab_v2_submission_dispatches"

    def __post_init__(self) -> None:
        for name, value in (
            ("submission_table", self.submission_table),
            ("dispatch_table", self.dispatch_table),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
                raise ValueError(f"{name} must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.submission_table} (
                owner_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                operation TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                accepted_at TEXT NOT NULL,
                PRIMARY KEY (owner_id, idempotency_key)
            )
            """,
            f"""
            CREATE TABLE {self.dispatch_table} (
                owner_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                queue_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (owner_id, idempotency_key)
            )
            """,
        )


class PostgresSubmissionDispatchAdapter:
    """Durably stage one owner-scoped submission and its dispatch intent."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresSubmissionSchema | None = None,
        queue_for_operation: Callable[[str], str] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        if queue_for_operation is not None and not callable(queue_for_operation):
            raise TypeError("queue_for_operation must be callable")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresSubmissionSchema()
        self._queue_for_operation = queue_for_operation or (lambda operation: operation)
        self._clock = clock

    @property
    def schema(self) -> PostgresSubmissionSchema:
        return self._schema

    async def submit(
        self,
        *,
        principal: Any,
        request_id: str = "adapter",
        request: SubmissionRequest,
        payload: Mapping[str, Any],
    ) -> SubmissionServiceResult:
        """Resolve and durably stage a submission/outbox pair atomically."""

        if not isinstance(request, SubmissionRequest):
            raise TypeError("request must be a SubmissionRequest")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        if content_digest(payload) != request.payload_digest:
            raise ApiAdapterError(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "submission payload does not match its content digest",
                    request_id=request_id,
                    status_code=422,
                )
            )
        owner_id = _principal_id(principal)
        queue_name = self._queue_for_operation(request.operation)
        if not isinstance(queue_name, str) or not queue_name.strip():
            raise ValueError("queue_for_operation must return a non-empty string")
        dispatch_request = DispatchRequest(
            idempotency_key=request.idempotency_key,
            attempt_id=request.attempt_id,
            payload_digest=request.payload_digest,
            queue_name=queue_name,
            created_at=request.submitted_at,
        )
        accepted_at = self._clock()
        if accepted_at.tzinfo is None or accepted_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                prior_receipt = await self._load_submission(session, owner_id, request.idempotency_key)
                prior_dispatch = await self._load_dispatch(session, owner_id, request.idempotency_key)
                ledger = SubmissionReceiptLedger(
                    (prior_receipt,) if prior_receipt is not None else ()
                )
                resolution = resolve_submission_dispatch(
                    ledger,
                    request,
                    dispatch_request,
                    accepted_at=accepted_at,
                    prior_dispatches=(prior_dispatch,) if prior_dispatch is not None else (),
                )
                if resolution.decision in {
                    SubmissionDispatchDecision.CONFLICT,
                    SubmissionDispatchDecision.REJECT,
                }:
                    code = (
                        ApiErrorCode.IDEMPOTENCY_CONFLICT
                        if resolution.decision is SubmissionDispatchDecision.CONFLICT
                        else ApiErrorCode.PRECONDITION_FAILED
                    )
                    raise ApiAdapterError(
                        _api_error(
                            code,
                            resolution.rejection_reason or "submission was rejected",
                            request_id=request_id,
                            status_code=409,
                        )
                    )
                receipt = resolution.receipt
                if receipt is None:  # pragma: no cover - guarded by pure resolution
                    raise ValueError("submission resolution omitted its receipt")
                if prior_receipt is None:
                    await self._insert_submission(session, owner_id, receipt)
                if prior_dispatch is None:
                    await self._insert_dispatch(session, owner_id, dispatch_request)
                submission_resolution = resolve_submission(request, ledger.receipts)
                if submission_resolution.decision is SubmissionDecision.ACCEPT:
                    # The pure dispatch resolver creates the receipt using the
                    # adapter clock, so the request fingerprint remains exact.
                    submission_resolution = resolve_submission(request, ())
                return SubmissionServiceResult(submission_resolution, receipt)

    async def _load_submission(
        self, session: AsyncSessionLike, owner_id: str, idempotency_key: str
    ) -> SubmissionReceipt | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, idempotency_key, request_fingerprint, operation,
                       attempt_id, payload_digest, submitted_at, accepted_at
                FROM {self._schema.submission_table}
                WHERE owner_id = :owner_id AND idempotency_key = :idempotency_key
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "idempotency_key": idempotency_key},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL submission query returned duplicate keys")
        row = rows[0]
        receipt = _decode_submission(row)
        if row.get("owner_id") != owner_id:
            raise ValueError("PostgreSQL submission owner identity drifted")
        return receipt

    async def _load_dispatch(
        self, session: AsyncSessionLike, owner_id: str, idempotency_key: str
    ) -> DispatchRequest | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, idempotency_key, request_fingerprint, attempt_id,
                       payload_digest, queue_name, created_at
                FROM {self._schema.dispatch_table}
                WHERE owner_id = :owner_id AND idempotency_key = :idempotency_key
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "idempotency_key": idempotency_key},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL dispatch query returned duplicate keys")
        row = rows[0]
        dispatch = _decode_dispatch(row)
        if row.get("owner_id") != owner_id:
            raise ValueError("PostgreSQL dispatch owner identity drifted")
        if row.get("request_fingerprint") != dispatch.fingerprint:
            raise ValueError("PostgreSQL dispatch fingerprint does not match bytes")
        return dispatch

    async def _insert_submission(
        self, session: AsyncSessionLike, owner_id: str, receipt: SubmissionReceipt
    ) -> None:
        request = receipt.request
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.submission_table}
                    (owner_id, idempotency_key, request_fingerprint, operation,
                     attempt_id, payload_digest, submitted_at, accepted_at)
                VALUES (:owner_id, :idempotency_key, :request_fingerprint, :operation,
                        :attempt_id, :payload_digest, :submitted_at, :accepted_at)
                ON CONFLICT (owner_id, idempotency_key) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "idempotency_key": request.idempotency_key,
                "request_fingerprint": request.fingerprint,
                "operation": request.operation,
                "attempt_id": request.attempt_id,
                "payload_digest": request.payload_digest,
                "submitted_at": _encode_datetime(request.submitted_at),
                "accepted_at": _encode_datetime(receipt.accepted_at),
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL submission insert lost an idempotency race")

    async def _insert_dispatch(
        self, session: AsyncSessionLike, owner_id: str, request: DispatchRequest
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.dispatch_table}
                    (owner_id, idempotency_key, request_fingerprint, attempt_id,
                     payload_digest, queue_name, created_at)
                VALUES (:owner_id, :idempotency_key, :request_fingerprint, :attempt_id,
                        :payload_digest, :queue_name, :created_at)
                ON CONFLICT (owner_id, idempotency_key) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "idempotency_key": request.idempotency_key,
                "request_fingerprint": request.fingerprint,
                "attempt_id": request.attempt_id,
                "payload_digest": request.payload_digest,
                "queue_name": request.queue_name,
                "created_at": _encode_datetime(request.created_at),
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL dispatch insert lost an idempotency race")


def _statement(sql: str) -> Any:
    """Keep SQLAlchemy optional at import time for contract-level tests."""

    from sqlalchemy import text

    return text(sql)


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.AUTHORIZATION_REQUIRED,
                "authenticated principal identity is required",
                request_id="adapter",
                status_code=401,
            )
        )
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


def _decode_submission(row: Mapping[str, Any]) -> SubmissionReceipt:
    try:
        request = SubmissionRequest(
            idempotency_key=row["idempotency_key"],
            operation=row["operation"],
            attempt_id=row["attempt_id"],
            payload_digest=row["payload_digest"],
            submitted_at=_decode_datetime(row["submitted_at"], "submitted_at"),
        )
        if row["request_fingerprint"] != request.fingerprint:
            raise ValueError("submission fingerprint does not match bytes")
        return SubmissionReceipt(
            request,
            accepted_at=_decode_datetime(row["accepted_at"], "accepted_at"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL submission row is malformed") from error


def _decode_dispatch(row: Mapping[str, Any]) -> DispatchRequest:
    try:
        request = DispatchRequest(
            idempotency_key=row["idempotency_key"],
            attempt_id=row["attempt_id"],
            payload_digest=row["payload_digest"],
            queue_name=row["queue_name"],
            created_at=_decode_datetime(row["created_at"], "created_at"),
        )
        if row["request_fingerprint"] != request.fingerprint:
            raise ValueError("dispatch fingerprint does not match bytes")
        return request
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL dispatch row is malformed") from error


def _api_error(
    code: ApiErrorCode,
    message: str,
    *,
    request_id: str,
    status_code: int,
) -> ApiError:
    return ApiError(
        code=code,
        message=message,
        request_id=request_id,
        status_code=status_code,
    )


__all__ = ["PostgresSubmissionDispatchAdapter", "PostgresSubmissionSchema"]
