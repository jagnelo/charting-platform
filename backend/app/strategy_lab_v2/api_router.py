"""Registration-neutral FastAPI boundary for Strategy Lab v2.

The application owns authentication, dependency construction, persistence, and
router registration.  This module supplies the versioned route shape and the
wire conversion around those concerns without importing the existing Strategy
Lab services or mutating shared application paths.  Every state-changing route
delegates to an injected adapter so compare-and-set, outbox, and execution
semantics stay outside FastAPI.
"""

from __future__ import annotations

import inspect
import json
import logging
import math
import re
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol, TypeVar, cast

from fastapi import APIRouter, Body, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse

from app.strategy_lab_v2.api_contracts import (
    ApiCursor,
    ApiError,
    ApiErrorCode,
)
from app.strategy_lab_v2.api_resources import (
    ApiResourceType,
    ResourceCollection,
    ResourceDocument,
    ResourceIdentifier,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.commands import (
    ExecutionCommand,
    ExecutionCommandDecision,
    ExecutionCommandKind,
    ExecutionCommandResolution,
)
from app.strategy_lab_v2.strategy_validation import validate_strategy_source
from app.strategy_lab_v2.submissions import (
    SubmissionDecision,
    SubmissionReceipt,
    SubmissionRequest,
    SubmissionResolution,
)

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100
MAX_REQUEST_ID_LENGTH = 128
MAX_OPERATION_LENGTH = 128
MAX_SOURCE_BYTES = 1_000_000
_OPERATION_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_T = TypeVar("_T")


class StrategyLabApiAdapter(Protocol):
    """Application-owned adapter required by :func:`create_strategy_lab_router`.

    Implementations must scope all reads and mutations to ``principal`` and
    must perform durable compare-and-set/idempotency before returning a result.
    Methods may be async or sync to keep the boundary usable by a future
    SQLAlchemy/Redis adapter and deterministic in-memory tests.
    """

    def list_resources(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        limit: int,
        cursor: Any,
        request_id: str,
    ) -> Awaitable[ResourceCollection] | ResourceCollection: ...

    def get_resource(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        resource_id: str,
    ) -> Awaitable[ResourceDocument | None] | ResourceDocument | None: ...

    def submit(
        self,
        *,
        principal: Any,
        request_id: str,
        request: SubmissionRequest,
        payload: Mapping[str, Any],
    ) -> Awaitable[SubmissionServiceResult] | SubmissionServiceResult: ...

    def command(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        command: ExecutionCommand,
    ) -> Awaitable[ExecutionCommandResolution] | ExecutionCommandResolution: ...


@dataclass(frozen=True, slots=True)
class SubmissionServiceResult:
    """Adapter response that always carries the durable receipt to serialize."""

    resolution: SubmissionResolution
    receipt: SubmissionReceipt

    def __post_init__(self) -> None:
        if not isinstance(self.resolution, SubmissionResolution):
            raise TypeError("resolution must be a SubmissionResolution")
        if not isinstance(self.receipt, SubmissionReceipt):
            raise TypeError("receipt must be a SubmissionReceipt")
        if self.resolution.decision is SubmissionDecision.IDEMPOTENCY_CONFLICT:
            if self.resolution.existing_receipt != self.receipt:
                raise ValueError("idempotency conflict must return the existing receipt")
        elif self.receipt.request.fingerprint != self.resolution.request_fingerprint:
            raise ValueError("submission receipt does not match the resolved request")
        elif self.resolution.decision is SubmissionDecision.REPLAY_EXISTING:
            if self.resolution.existing_receipt != self.receipt:
                raise ValueError("replayed submission must return its existing receipt")


class ApiAdapterError(Exception):
    """Typed adapter failure that can cross the route boundary safely."""

    def __init__(self, error: ApiError) -> None:
        if not isinstance(error, ApiError):
            raise TypeError("error must be an ApiError")
        super().__init__(error.message)
        self.error = error


def _json_value(value: Any) -> Any:
    """Convert frozen canonical values to JSON without losing Decimal precision."""

    if isinstance(value, Mapping):
        return {str(key): _json_value(value[key]) for key in sorted(value)}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("API datetimes must be timezone-aware")
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("API decimals must be finite")
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("API floats must be finite")
        return value
    if value is None or isinstance(value, bool | int | str):
        return value
    raise TypeError(f"unsupported API JSON value: {type(value).__name__}")


def serialize_resource_identifier(identifier: ResourceIdentifier) -> dict[str, Any]:
    """Serialize one JSON:API-style relationship identifier."""

    if not isinstance(identifier, ResourceIdentifier):
        raise TypeError("identifier must be a ResourceIdentifier")
    return {"type": identifier.type, "id": identifier.resource_id}


def serialize_resource(document: ResourceDocument) -> dict[str, Any]:
    """Serialize an immutable resource document deterministically."""

    if not isinstance(document, ResourceDocument):
        raise TypeError("document must be a ResourceDocument")
    meta = dict(_json_value(document.meta))
    meta["schema_version"] = document.identity.schema_version
    if document.identity.revision_digest is not None:
        meta["revision_digest"] = document.identity.revision_digest
    relationships = {
        name: {"data": [serialize_resource_identifier(target) for target in targets]}
        for name, targets in sorted(document.relationships.items())
    }
    return {
        "type": document.type,
        "id": document.id,
        "attributes": _json_value(document.attributes),
        "relationships": relationships,
        "meta": meta,
    }


def serialize_collection(collection: ResourceCollection) -> dict[str, Any]:
    """Serialize a cursor-bound collection and expose only a continuation token."""

    if not isinstance(collection, ResourceCollection):
        raise TypeError("collection must be a ResourceCollection")
    response: dict[str, Any] = {
        "data": [serialize_resource(item) for item in collection.items],
        "meta": {
            "request_id": collection.request_id,
            "resource": collection.resource,
            "snapshot_digest": collection.snapshot_digest,
        },
        "links": {},
    }
    if collection.next_cursor is not None:
        response["links"]["next"] = collection.next_cursor.token
    return response


def serialize_submission(result: SubmissionServiceResult) -> dict[str, Any]:
    """Serialize a durable accepted/replayed submission receipt."""

    if not isinstance(result, SubmissionServiceResult):
        raise TypeError("result must be a SubmissionServiceResult")
    receipt = result.receipt
    return _json_value({
        "data": {
            "type": "submissions",
            "id": receipt.submission_id,
            "attributes": {
                "operation": receipt.request.operation,
                "attempt_id": receipt.request.attempt_id,
                "idempotency_key": receipt.request.idempotency_key,
                "payload_digest": receipt.request.payload_digest,
                "submitted_at": receipt.request.submitted_at,
                "accepted_at": receipt.accepted_at,
            },
            "meta": {"decision": result.resolution.decision.value},
        }
    })


def serialize_command(resolution: ExecutionCommandResolution) -> dict[str, Any]:
    """Serialize an accepted/replayed command receipt."""

    if not isinstance(resolution, ExecutionCommandResolution):
        raise TypeError("resolution must be an ExecutionCommandResolution")
    if resolution.receipt is None:
        raise ValueError("accepted command responses require a receipt")
    receipt = resolution.receipt
    return _json_value({
        "data": {
            "type": "execution-commands",
            "id": receipt.command_id,
            "attributes": {
                "attempt_id": receipt.attempt_id,
                "kind": receipt.kind,
                "effect": receipt.effect,
                "accepted_at": receipt.accepted_at,
                "command_fingerprint": receipt.command_fingerprint,
            },
            "meta": {"decision": resolution.decision.value},
        }
    })


def _request_id(request: Request, factory: Callable[[], str]) -> str:
    supplied = request.headers.get("X-Request-ID")
    raw_value = supplied if supplied is not None else factory()
    try:
        return _safe_header_value(raw_value, "X-Request-ID", MAX_REQUEST_ID_LENGTH)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "X-Request-ID must be non-empty, at most 128 characters, and control-free"
        ) from error


def _safe_header_value(value: str | None, field_name: str, max_length: int) -> str:
    """Normalize a request header without allowing response/header injection."""

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        raise ValueError(f"{field_name} must be non-empty and within its length limit")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized):
        raise ValueError(f"{field_name} must not contain control characters")
    return normalized


def _error_response(error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "errors": [
                {
                    "code": error.code.value,
                    "type": error.type,
                    "message": error.message,
                    "status": error.status_code,
                    "retryable": error.retryable,
                    "request_id": error.request_id,
                    "details": _json_value(error.details),
                }
            ]
        },
    )


def _api_error(
    code: ApiErrorCode,
    message: str,
    request_id: str,
    status_code: int,
    *,
    retryable: bool = False,
    details: Mapping[str, Any] | None = None,
) -> ApiError:
    return ApiError(
        code=code,
        message=message,
        request_id=request_id,
        status_code=status_code,
        retryable=retryable,
        details=details or {},
    )


async def _resolve(value: Awaitable[_T] | _T) -> _T:
    if inspect.isawaitable(value):
        return await cast(Awaitable[_T], value)
    return cast(_T, value)


def _reject_duplicate_json_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous request objects before FastAPI body normalization."""

    values: dict[str, Any] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("request JSON contains duplicate object fields")
        values[key] = value
    return values


def _reject_non_finite_json(value: str) -> Any:
    """Reject JSON extensions that cannot participate in request identity."""

    raise ValueError(f"request JSON contains non-finite constant: {value}")


async def _strict_json_body(request: Request, request_id: str) -> Any:
    """Reparse the raw body so duplicate keys cannot be hidden by FastAPI."""

    try:
        return json.loads(
            (await request.body()).decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_fields,
            parse_constant=_reject_non_finite_json,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "request body is not canonical JSON",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"reason": "duplicate fields or non-finite values are not allowed"},
            )
        ) from error


def _resource_type(value: str, request_id: str) -> ApiResourceType | JSONResponse:
    try:
        return ApiResourceType(value)
    except ValueError:
        return _error_response(
            _api_error(
                ApiErrorCode.NOT_FOUND,
                "unknown Strategy Lab v2 resource",
                request_id,
                status.HTTP_404_NOT_FOUND,
                details={"resource": value},
            )
        )


def _parse_cursor(value: str | None, request_id: str, resource_type: ApiResourceType) -> Any:
    if value is None:
        return None
    try:
        cursor = ApiCursor.from_token(value)
    except (TypeError, ValueError) as error:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "cursor token is invalid",
                request_id,
                status.HTTP_400_BAD_REQUEST,
                details={"reason": str(error)},
            )
        ) from error
    if cursor.resource != resource_type.value:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "cursor resource does not match the requested collection",
                request_id,
                status.HTTP_400_BAD_REQUEST,
                details={"cursor_resource": cursor.resource, "resource": resource_type.value},
            )
        )
    return cursor


def _parse_submission(
    body: Mapping[str, Any], *, idempotency_key: str | None, request_id: str, now: datetime
) -> tuple[SubmissionRequest, Mapping[str, Any]]:
    if idempotency_key is None or not idempotency_key.strip():
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "Idempotency-Key header is required",
                request_id,
                status.HTTP_400_BAD_REQUEST,
            )
        )
    try:
        key = _safe_header_value(idempotency_key, "Idempotency-Key", 256)
    except (TypeError, ValueError) as error:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "Idempotency-Key must be non-empty, at most 256 characters, and control-free",
                request_id,
                status.HTTP_400_BAD_REQUEST,
            )
        ) from error
    if not isinstance(body, Mapping) or set(body) != {"operation", "attempt_id", "payload"}:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "submission body must contain operation, attempt_id, and payload only",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    operation = body["operation"]
    attempt_id = body["attempt_id"]
    payload = body["payload"]
    if (
        not isinstance(operation, str)
        or not operation.strip()
        or len(operation) > MAX_OPERATION_LENGTH
        or _OPERATION_PATTERN.fullmatch(operation) is None
    ):
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "operation must match the lowercase operation format",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "attempt_id must be a non-empty string",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    if not isinstance(payload, Mapping):
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "payload must be a JSON object",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    try:
        payload_digest = content_digest(payload)
        return (
            SubmissionRequest(
                idempotency_key=key,
                operation=operation,
                attempt_id=attempt_id,
                payload_digest=payload_digest,
                submitted_at=now,
            ),
            payload,
        )
    except (TypeError, ValueError) as error:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "submission payload is not canonical JSON",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"reason": str(error)},
            )
        ) from error


def _parse_command(
    body: Mapping[str, Any], *, attempt_id: str, request_id: str
) -> ExecutionCommand:
    required = {"command_id", "kind", "reason", "requested_at"}
    if not isinstance(body, Mapping) or set(body) != required:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "command body must contain command_id, kind, reason, and requested_at only",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    requested_at = body["requested_at"]
    if not isinstance(requested_at, str):
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "requested_at must be an ISO-8601 timestamp",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    try:
        timestamp = datetime.fromisoformat(requested_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        kind = ExecutionCommandKind(body["kind"])
        return ExecutionCommand(
            command_id=body["command_id"],
            attempt_id=attempt_id,
            kind=kind,
            requested_at=timestamp,
            reason=body["reason"],
        )
    except (TypeError, ValueError) as error:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "command fields are invalid",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"reason": str(error)},
            )
        ) from error


def create_strategy_lab_router(
    *,
    adapter_dependency: Callable[..., Any],
    principal_dependency: Callable[..., Any],
    request_id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> APIRouter:
    """Create the unregistered ``/strategy-lab/v2`` router.

    The caller supplies application dependencies explicitly when the shared
    router gate is opened.  Keeping registration out of this module prevents a
    package-only branch from importing the current database/auth graph.
    """

    router = APIRouter(prefix="/strategy-lab/v2", tags=["strategy-lab-v2"])

    @router.post("/strategies/validate")
    async def validate_strategy(
        request: Request,
        body: Any = Body(...),
        _: Any = Depends(principal_dependency),
    ) -> JSONResponse:
        request_id = _request_id(request, request_id_factory)
        try:
            body = await _strict_json_body(request, request_id)
        except ApiAdapterError as error:
            return _error_response(error.error)
        if not isinstance(body, Mapping) or set(body) != {"source"} or not isinstance(
            body.get("source"), str
        ):
            return _error_response(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "strategy validation body must contain source only",
                    request_id,
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            )
        source = body["source"]
        if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
            return _error_response(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "strategy source exceeds the maximum size",
                    request_id,
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    details={"max_bytes": MAX_SOURCE_BYTES},
                )
            )
        result = validate_strategy_source(source)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "data": {
                    "type": "strategy-validations",
                    "id": result.source_digest,
                    "attributes": {
                        "source_digest": result.source_digest,
                        "accepted": result.accepted,
                        "violations": list(result.violations),
                    },
                },
                "meta": {"request_id": request_id},
            },
        )

    @router.get("/{resource}")
    async def list_resource(
        resource: str,
        request: Request,
        limit: int = Query(MAX_PAGE_SIZE),
        cursor: str | None = Query(None),
        adapter: StrategyLabApiAdapter = Depends(adapter_dependency),
        principal: Any = Depends(principal_dependency),
    ) -> JSONResponse:
        try:
            request_id = _request_id(request, request_id_factory)
            parsed_resource = _resource_type(resource, request_id)
            if isinstance(parsed_resource, JSONResponse):
                return parsed_resource
            if limit < 1 or limit > MAX_PAGE_SIZE:
                return _error_response(
                    _api_error(
                        ApiErrorCode.VALIDATION_ERROR,
                        "limit must be between 1 and 100",
                        request_id,
                        status.HTTP_400_BAD_REQUEST,
                    )
                )
            parsed_cursor = _parse_cursor(cursor, request_id, parsed_resource)
            collection = await _resolve(
                adapter.list_resources(
                    principal=principal,
                    resource_type=parsed_resource,
                    limit=limit,
                    cursor=parsed_cursor,
                    request_id=request_id,
                )
            )
            if collection.resource_type is not parsed_resource:
                raise ValueError("adapter returned a collection for the wrong resource")
            if collection.request_id != request_id:
                raise ValueError("adapter returned a collection for the wrong request")
            return JSONResponse(status_code=collection.http_status, content=serialize_collection(collection))
        except ApiAdapterError as error:
            return _error_response(error.error)
        except (TypeError, ValueError) as error:
            logger.warning("Strategy Lab v2 list validation failed: %s", error)
            return _error_response(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "resource collection request is invalid",
                    locals().get("request_id", "unknown"),
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    details={"reason": str(error)},
                )
            )
        except Exception:  # pragma: no cover - defensive adapter boundary
            logger.exception("Strategy Lab v2 resource list failed")
            return _error_response(
                _api_error(
                    ApiErrorCode.INTERNAL_ERROR,
                    "Strategy Lab v2 resource list failed",
                    locals().get("request_id", "unknown"),
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    retryable=True,
                )
            )

    @router.get("/{resource}/{resource_id}")
    async def get_resource(
        resource: str,
        resource_id: str,
        request: Request,
        adapter: StrategyLabApiAdapter = Depends(adapter_dependency),
        principal: Any = Depends(principal_dependency),
    ) -> JSONResponse:
        try:
            request_id = _request_id(request, request_id_factory)
            parsed_resource = _resource_type(resource, request_id)
            if isinstance(parsed_resource, JSONResponse):
                return parsed_resource
            if not resource_id.strip():
                return _error_response(
                    _api_error(
                        ApiErrorCode.VALIDATION_ERROR,
                        "resource_id must not be empty",
                        request_id,
                        status.HTTP_400_BAD_REQUEST,
                    )
                )
            document = await _resolve(
                adapter.get_resource(
                    principal=principal,
                    resource_type=parsed_resource,
                    resource_id=resource_id,
                )
            )
            if document is None:
                return _error_response(
                    _api_error(
                        ApiErrorCode.NOT_FOUND,
                        "Strategy Lab v2 resource was not found",
                        request_id,
                        status.HTTP_404_NOT_FOUND,
                        details={"resource": parsed_resource.value, "id": resource_id},
                    )
                )
            if document.identity.resource_type is not parsed_resource:
                raise ValueError("adapter returned a resource for the wrong type")
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"data": serialize_resource(document), "meta": {"request_id": request_id}},
            )
        except ApiAdapterError as error:
            return _error_response(error.error)
        except (TypeError, ValueError) as error:
            return _error_response(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "resource request is invalid",
                    locals().get("request_id", "unknown"),
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    details={"reason": str(error)},
                )
            )
        except Exception:  # pragma: no cover - defensive adapter boundary
            logger.exception("Strategy Lab v2 resource read failed")
            return _error_response(
                _api_error(
                    ApiErrorCode.INTERNAL_ERROR,
                    "Strategy Lab v2 resource read failed",
                    locals().get("request_id", "unknown"),
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    retryable=True,
                )
            )

    @router.post("/submissions", status_code=status.HTTP_202_ACCEPTED)
    async def submit_execution(
        request: Request,
        body: Any = Body(...),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        adapter: StrategyLabApiAdapter = Depends(adapter_dependency),
        principal: Any = Depends(principal_dependency),
    ) -> JSONResponse:
        try:
            request_id = _request_id(request, request_id_factory)
            body = await _strict_json_body(request, request_id)
            submission, payload = _parse_submission(
                body, idempotency_key=idempotency_key, request_id=request_id, now=clock()
            )
            result = await _resolve(
                adapter.submit(
                    principal=principal,
                    request_id=request_id,
                    request=submission,
                    payload=payload,
                )
            )
            if not isinstance(result, SubmissionServiceResult):
                raise TypeError("adapter returned an invalid submission result")
            if result.resolution.decision is SubmissionDecision.IDEMPOTENCY_CONFLICT:
                return _error_response(
                    _api_error(
                        ApiErrorCode.IDEMPOTENCY_CONFLICT,
                        "Idempotency-Key is already bound to different content",
                        request_id,
                        status.HTTP_409_CONFLICT,
                        details={"submission_id": result.receipt.submission_id},
                    )
                )
            response = JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=serialize_submission(result))
            response.headers["X-Request-ID"] = request_id
            return response
        except ApiAdapterError as error:
            return _error_response(error.error)
        except (TypeError, ValueError) as error:
            return _error_response(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "submission request is invalid",
                    locals().get("request_id", "unknown"),
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    details={"reason": str(error)},
                )
            )
        except Exception:  # pragma: no cover - defensive adapter boundary
            logger.exception("Strategy Lab v2 submission failed")
            return _error_response(
                _api_error(
                    ApiErrorCode.INTERNAL_ERROR,
                    "Strategy Lab v2 submission failed",
                    locals().get("request_id", "unknown"),
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    retryable=True,
                )
            )

    @router.post("/attempts/{attempt_id}/commands", status_code=status.HTTP_202_ACCEPTED)
    async def issue_command(
        attempt_id: str,
        request: Request,
        body: Any = Body(...),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        adapter: StrategyLabApiAdapter = Depends(adapter_dependency),
        principal: Any = Depends(principal_dependency),
    ) -> JSONResponse:
        try:
            request_id = _request_id(request, request_id_factory)
            body = await _strict_json_body(request, request_id)
            try:
                command_idempotency_key = _safe_header_value(
                    idempotency_key, "Idempotency-Key", 256
                )
            except (TypeError, ValueError):
                return _error_response(
                    _api_error(
                        ApiErrorCode.VALIDATION_ERROR,
                        "Idempotency-Key must be non-empty, at most 256 characters, and control-free",
                        request_id,
                        status.HTTP_400_BAD_REQUEST,
                    )
                )
            if not attempt_id.strip():
                return _error_response(
                    _api_error(
                        ApiErrorCode.VALIDATION_ERROR,
                        "attempt_id must not be empty",
                        request_id,
                        status.HTTP_400_BAD_REQUEST,
                    )
                )
            command = _parse_command(body, attempt_id=attempt_id, request_id=request_id)
            resolution = await _resolve(
                adapter.command(
                    principal=principal,
                    request_id=request_id,
                    idempotency_key=command_idempotency_key,
                    command=command,
                )
            )
            if not isinstance(resolution, ExecutionCommandResolution):
                raise TypeError("adapter returned an invalid command resolution")
            if resolution.decision in {
                ExecutionCommandDecision.CONFLICT,
                ExecutionCommandDecision.REJECT,
            }:
                code = (
                    ApiErrorCode.IDEMPOTENCY_CONFLICT
                    if resolution.decision is ExecutionCommandDecision.CONFLICT
                    else ApiErrorCode.PRECONDITION_FAILED
                )
                return _error_response(
                    _api_error(
                        code,
                        resolution.rejection_reason or "execution command was rejected",
                        request_id,
                        status.HTTP_409_CONFLICT,
                    )
                )
            response = JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=serialize_command(resolution))
            response.headers["X-Request-ID"] = request_id
            return response
        except ApiAdapterError as error:
            return _error_response(error.error)
        except (TypeError, ValueError) as error:
            return _error_response(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "execution command request is invalid",
                    locals().get("request_id", "unknown"),
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    details={"reason": str(error)},
                )
            )
        except Exception:  # pragma: no cover - defensive adapter boundary
            logger.exception("Strategy Lab v2 command failed")
            return _error_response(
                _api_error(
                    ApiErrorCode.INTERNAL_ERROR,
                    "Strategy Lab v2 command failed",
                    locals().get("request_id", "unknown"),
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    retryable=True,
                )
            )

    return router


__all__ = [
    "MAX_PAGE_SIZE",
    "ApiAdapterError",
    "StrategyLabApiAdapter",
    "SubmissionServiceResult",
    "create_strategy_lab_router",
    "serialize_collection",
    "serialize_command",
    "serialize_resource",
    "serialize_resource_identifier",
    "serialize_submission",
]
