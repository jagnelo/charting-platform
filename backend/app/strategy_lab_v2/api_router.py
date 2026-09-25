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
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
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
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.capability_summary import CapabilitySummary
from app.strategy_lab_v2.commands import (
    ExecutionCommand,
    ExecutionCommandDecision,
    ExecutionCommandKind,
    ExecutionCommandResolution,
)
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.legacy import (
    LegacyCompatibilityAssessment,
    LegacyImportDecision,
    LegacyImportRequest,
    LegacyImportResolution,
    LegacyRecordKind,
)
from app.strategy_lab_v2.resource_mutations import (
    ResourceMutationDecision,
    ResourceMutationReceipt,
    ResourceMutationRequest,
    ResourceMutationResolution,
)
from app.strategy_lab_v2.search_dispatch import (
    SearchDispatchDecision,
    SearchDispatchResolution,
)
from app.strategy_lab_v2.search_state import (
    SearchExecutionState,
    SearchStateDecision,
    SearchStateResolution,
    new_search_execution_state,
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
MAX_RESOURCE_PAYLOAD_BYTES = 1_000_000
_OPERATION_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_T = TypeVar("_T")
_MUTABLE_RESOURCE_TYPES = frozenset(
    {
        ApiResourceType.STRATEGY,
        ApiResourceType.PACKAGE,
        ApiResourceType.PORTFOLIO,
        ApiResourceType.SNAPSHOT,
        ApiResourceType.EXPERIMENT,
        ApiResourceType.TRIAL,
        ApiResourceType.ATTEMPT,
        ApiResourceType.FORWARD_INSTANCE,
    }
)


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

    def create_resource(
        self,
        *,
        principal: Any,
        request_id: str,
        request: ResourceMutationRequest,
    ) -> Awaitable[ResourceMutationServiceResult] | ResourceMutationServiceResult: ...

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

    def import_legacy(
        self,
        *,
        principal: Any,
        request_id: str,
        request: LegacyImportRequest,
        assessment: LegacyCompatibilityAssessment,
    ) -> Awaitable[LegacyImportResolution] | LegacyImportResolution: ...


class CapabilityPreflightAdapter(Protocol):
    """Optional application-owned capability calculation seam.

    Capability calculation needs provider entitlement and engine-registration
    knowledge that the engine-neutral API package must not invent.  Keeping
    this protocol optional lets the route fail closed until the application
    supplies that binding while preserving a stable, typed response contract.
    """

    def preflight_capability(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
        payload_digest: str,
    ) -> Awaitable[CapabilitySummary] | CapabilitySummary: ...


class SearchStateApiAdapter(Protocol):
    """Application-owned durable search queue operations exposed by the API."""

    def initialize_search(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        state: SearchExecutionState,
    ) -> Awaitable[SearchStateResolution] | SearchStateResolution: ...

    def cancel_search(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        experiment_fingerprint: str,
        cancellation_request_id: str,
        now: datetime,
    ) -> Awaitable[SearchStateResolution] | SearchStateResolution: ...


class SearchDispatchApiAdapter(Protocol):
    """Application-owned atomic search candidate dispatch boundary."""

    def dispatch_search_candidate(
        self,
        *,
        principal: Any,
        request_id: str,
        experiment_fingerprint: str,
        candidate_index: int,
        attempt_id: str,
        dispatch_request: DispatchRequest,
        payload: Mapping[str, Any],
    ) -> Awaitable[SearchDispatchResolution] | SearchDispatchResolution: ...

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


@dataclass(frozen=True, slots=True)
class ResourceMutationServiceResult:
    """Adapter response carrying the durable resource mutation receipt."""

    resolution: ResourceMutationResolution
    receipt: ResourceMutationReceipt | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.resolution, ResourceMutationResolution):
            raise TypeError("resolution must be a ResourceMutationResolution")
        if self.resolution.decision is ResourceMutationDecision.REJECT:
            if self.receipt is not None:
                raise ValueError("rejected resource mutations cannot carry a receipt")
            return
        if not isinstance(self.receipt, ResourceMutationReceipt):
            raise TypeError("accepted resource mutations require a receipt")
        if self.resolution.decision is ResourceMutationDecision.ACCEPT:
            if self.receipt.request.fingerprint != self.resolution.request_fingerprint:
                raise ValueError("resource mutation receipt does not match the resolved request")
        elif self.receipt != self.resolution.existing_receipt:
            raise ValueError("replayed/conflicting resource mutations require the existing receipt")


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


def serialize_resource_mutation(result: ResourceMutationServiceResult) -> dict[str, Any]:
    """Serialize an accepted or replayed resource creation as a 202 document."""

    if not isinstance(result, ResourceMutationServiceResult):
        raise TypeError("result must be a ResourceMutationServiceResult")
    if result.receipt is None:
        raise ValueError("accepted resource mutations require a receipt")
    receipt = result.receipt
    return _json_value(
        {
            "data": serialize_resource(receipt.resource),
            "meta": {
                "decision": result.resolution.decision.value,
                "mutation_id": receipt.mutation_id,
                "payload_digest": receipt.request.payload_digest,
                "accepted_at": receipt.accepted_at,
            },
        }
    )


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


def serialize_legacy_import(
    resolution: LegacyImportResolution, *, request_id: str
) -> dict[str, Any]:
    """Serialize a preserved legacy record and its compatibility report."""

    if not isinstance(resolution, LegacyImportResolution):
        raise TypeError("resolution must be a LegacyImportResolution")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id must not be empty")
    report = resolution.report
    original = report.original
    return _json_value(
        {
            "data": {
                "type": "legacy-imports",
                "id": original.legacy_id,
                "attributes": {
                    "legacy_id": original.legacy_id,
                    "kind": original.kind,
                    "source_version": original.source_version,
                    "payload_digest": original.payload_digest,
                    "observed_at": original.observed_at,
                    "decision": resolution.decision,
                    "supported": report.supported,
                    "conversion_fingerprint": report.conversion_fingerprint,
                    "compatibility_notes": report.compatibility_notes,
                    "replay_equivalent": report.replay_equivalent,
                },
                "meta": {
                    "request_id": request_id,
                    "report_fingerprint": report.fingerprint,
                    "registry_fingerprint": resolution.registry.fingerprint,
                },
            }
        }
    )


def serialize_capability_summary(
    summary: CapabilitySummary, *, request_id: str, payload_digest: str
) -> dict[str, Any]:
    """Serialize one typed capability preflight without exposing provider handles."""

    if not isinstance(summary, CapabilitySummary):
        raise TypeError("summary must be a CapabilitySummary")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id must not be empty")
    if not isinstance(payload_digest, str) or not payload_digest.strip():
        raise ValueError("payload_digest must not be empty")
    return _json_value(
        {
            "data": {
                "type": "capability-preflights",
                "id": summary.fingerprint,
                "attributes": asdict(summary),
                "meta": {
                    "request_id": request_id,
                    "payload_digest": payload_digest,
                    "report_fingerprint": summary.report_fingerprint,
                    "binding_fingerprint": summary.binding_fingerprint,
                },
            }
        }
    )


def serialize_search_state(
    resolution: SearchStateResolution, *, request_id: str
) -> dict[str, Any]:
    """Serialize one durable resumable search queue checkpoint."""

    if not isinstance(resolution, SearchStateResolution):
        raise TypeError("resolution must be a SearchStateResolution")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id must not be empty")
    state = resolution.state
    return _json_value(
        {
            "data": {
                "type": "search-experiments",
                "id": state.experiment_fingerprint,
                "attributes": asdict(state),
                "meta": {
                    "request_id": request_id,
                    "decision": resolution.decision,
                    "state_fingerprint": state.fingerprint,
                },
            }
        }
    )


def serialize_search_dispatch(
    resolution: SearchDispatchResolution,
    *,
    request_id: str,
    candidate_index: int,
    attempt_id: str,
) -> dict[str, Any]:
    """Serialize one candidate/admission/dispatch decision and its evidence."""

    if not isinstance(resolution, SearchDispatchResolution):
        raise TypeError("resolution must be a SearchDispatchResolution")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id must not be empty")
    if not isinstance(candidate_index, int) or isinstance(candidate_index, bool) or candidate_index < 0:
        raise ValueError("candidate_index must be a non-negative integer")
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise ValueError("attempt_id must not be empty")
    dispatch = resolution.dispatch_resolution
    envelope = resolution.envelope
    dispatch_id = envelope.message_id if envelope is not None else content_digest(
        {
            "experiment_fingerprint": resolution.search_state.experiment_fingerprint,
            "candidate_index": candidate_index,
            "attempt_id": attempt_id,
            "decision": resolution.decision,
        }
    )
    return _json_value(
        {
            "data": {
                "type": "search-dispatches",
                "id": dispatch_id,
                "attributes": {
                    "decision": resolution.decision,
                    "candidate_index": candidate_index,
                    "attempt_id": attempt_id,
                    "search_state": asdict(resolution.search_state),
                    "admission_ledger": asdict(resolution.admission_ledger),
                    "worker_pool": asdict(resolution.pool),
                    "dispatch": asdict(dispatch) if dispatch is not None else None,
                    "envelope": asdict(envelope) if envelope is not None else None,
                    "rejection_reason": resolution.rejection_reason,
                },
                "meta": {
                    "request_id": request_id,
                    "state_fingerprint": resolution.search_state.fingerprint,
                    "admission_fingerprint": resolution.admission_ledger.fingerprint,
                    "worker_pool_fingerprint": resolution.pool.fingerprint,
                },
            }
        }
    )


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


def _parse_resource_mutation(
    body: Mapping[str, Any],
    *,
    resource_type: ApiResourceType,
    idempotency_key: str | None,
    request_id: str,
    now: datetime,
) -> ResourceMutationRequest:
    """Parse a strict resource-creation body without constructing domain state."""

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
    if not isinstance(body, Mapping) or "attributes" not in body:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "resource body must contain attributes and may contain relationships or meta",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    allowed = {"attributes", "relationships", "meta"}
    if set(body) - allowed:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "resource body contains unknown fields",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"allowed_fields": sorted(allowed)},
            )
        )
    attributes = body["attributes"]
    if not isinstance(attributes, Mapping):
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "resource attributes must be a JSON object",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    relationships = body.get("relationships", {})
    if not isinstance(relationships, Mapping):
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "resource relationships must be a JSON object",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    for name, targets in relationships.items():
        if not isinstance(name, str) or not name.strip():
            raise ApiAdapterError(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "relationship names must be non-empty strings",
                    request_id,
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            )
        if not isinstance(targets, Sequence) or isinstance(targets, str | bytes):
            raise ApiAdapterError(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "relationship values must be arrays",
                    request_id,
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            )
        for target in targets:
            if not isinstance(target, Mapping) or set(target) != {"type", "id"}:
                raise ApiAdapterError(
                    _api_error(
                        ApiErrorCode.VALIDATION_ERROR,
                        "relationship targets must contain type and id only",
                        request_id,
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )
                )
            if not isinstance(target["type"], str) or not target["type"].strip():
                raise ApiAdapterError(
                    _api_error(
                        ApiErrorCode.VALIDATION_ERROR,
                        "relationship target type must be a non-empty string",
                        request_id,
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )
                )
            if not isinstance(target["id"], str) or not target["id"].strip():
                raise ApiAdapterError(
                    _api_error(
                        ApiErrorCode.VALIDATION_ERROR,
                        "relationship target id must be a non-empty string",
                        request_id,
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )
                )
    meta = body.get("meta", {})
    if not isinstance(meta, Mapping):
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "resource meta must be a JSON object",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    payload = {"attributes": attributes, "relationships": relationships, "meta": meta}
    try:
        request = ResourceMutationRequest(resource_type, key, payload, now)
    except (TypeError, ValueError) as error:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "resource mutation body is not canonical JSON",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"reason": str(error)},
            )
        ) from error
    if len(json.dumps(_json_value(payload), separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > MAX_RESOURCE_PAYLOAD_BYTES:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "resource mutation payload exceeds the maximum size",
                request_id,
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                details={"max_bytes": MAX_RESOURCE_PAYLOAD_BYTES},
            )
        )
    return request


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


def _parse_legacy_import(
    body: Mapping[str, Any],
    *,
    idempotency_key: str | None,
    request_id: str,
    now: datetime,
) -> tuple[LegacyImportRequest, LegacyCompatibilityAssessment]:
    """Parse a strict digest-only legacy import request."""

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
    required = {
        "legacy_id",
        "kind",
        "source_version",
        "payload_digest",
        "mapping_version",
        "supported",
    }
    optional = {"conversion_fingerprint", "notes", "preserve_original"}
    if not isinstance(body, Mapping) or not required.issubset(body) or set(body) - required - optional:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "legacy import body contains missing or unknown fields",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"required_fields": sorted(required)},
            )
        )
    notes = body.get("notes", ())
    if not isinstance(notes, Sequence) or isinstance(notes, str | bytes):
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "legacy import notes must be an array of strings",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    if any(not isinstance(note, str) or not note.strip() for note in notes):
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "legacy import notes must contain non-empty strings",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    preserve_original = body.get("preserve_original", True)
    if not isinstance(preserve_original, bool):
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "preserve_original must be a boolean",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    request_fingerprint = content_digest(
        {"request_id": request_id, "idempotency_key": key, "body": body}
    )
    try:
        import_request = LegacyImportRequest(
            request_id=request_fingerprint,
            legacy_id=body["legacy_id"],
            kind=LegacyRecordKind(body["kind"]),
            source_version=body["source_version"],
            payload_digest=body["payload_digest"],
            requested_at=now,
            preserve_original=preserve_original,
        )
        assessment = LegacyCompatibilityAssessment(
            mapping_version=body["mapping_version"],
            supported=body["supported"],
            conversion_fingerprint=body.get("conversion_fingerprint"),
            notes=tuple(notes),
        )
    except (TypeError, ValueError) as error:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "legacy import fields are invalid",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"reason": str(error)},
            )
        ) from error
    return import_request, assessment


def _parse_search_initialization(
    body: Mapping[str, Any], *, experiment_fingerprint: str, request_id: str, now: datetime
) -> SearchExecutionState:
    """Parse a strict immutable trial-fingerprint list for a search queue."""

    try:
        require_sha256_digest(experiment_fingerprint, field_name="experiment_fingerprint")
    except (TypeError, ValueError) as error:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "experiment_id must be a SHA-256 content fingerprint",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"reason": str(error)},
            )
        ) from error
    if not isinstance(body, Mapping) or set(body) != {"trial_fingerprints"}:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "search body must contain trial_fingerprints only",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    trial_fingerprints = body["trial_fingerprints"]
    if not isinstance(trial_fingerprints, Sequence) or isinstance(
        trial_fingerprints, str | bytes
    ):
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "trial_fingerprints must be an array",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    trials = tuple(trial_fingerprints)
    if not trials or any(not isinstance(item, str) for item in trials):
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "trial_fingerprints must contain at least one string",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    try:
        for fingerprint in trials:
            require_sha256_digest(fingerprint, field_name="trial_fingerprint")
        return new_search_execution_state(experiment_fingerprint, trials, now=now)
    except (TypeError, ValueError) as error:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "trial_fingerprints are invalid",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"reason": str(error)},
            )
        ) from error


def _parse_search_dispatch(
    body: Mapping[str, Any],
    *,
    experiment_fingerprint: str,
    idempotency_key: str,
    request_id: str,
) -> tuple[int, str, DispatchRequest]:
    """Parse the digest-only candidate dispatch envelope."""

    try:
        require_sha256_digest(experiment_fingerprint, field_name="experiment_fingerprint")
    except (TypeError, ValueError) as error:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "experiment_id must be a SHA-256 content fingerprint",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"reason": str(error)},
            )
        ) from error
    required = {"candidate_index", "attempt_id", "payload_digest", "queue_name", "created_at"}
    if not isinstance(body, Mapping) or set(body) != required:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "search dispatch body contains missing or unknown fields",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"required_fields": sorted(required)},
            )
        )
    candidate_index = body["candidate_index"]
    attempt_id = body["attempt_id"]
    queue_name = body["queue_name"]
    payload_digest = body["payload_digest"]
    created_at = body["created_at"]
    if (
        not isinstance(candidate_index, int)
        or isinstance(candidate_index, bool)
        or candidate_index < 0
    ):
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "candidate_index must be a non-negative integer",
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
    if not isinstance(queue_name, str) or not queue_name.strip():
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "queue_name must be a non-empty string",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    if not isinstance(payload_digest, str):
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "payload_digest must be a SHA-256 content fingerprint",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        )
    try:
        require_sha256_digest(payload_digest, field_name="payload_digest")
        timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        dispatch = DispatchRequest(
            idempotency_key=idempotency_key,
            attempt_id=attempt_id,
            payload_digest=payload_digest,
            queue_name=queue_name,
            created_at=timestamp,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise ApiAdapterError(
            _api_error(
                ApiErrorCode.VALIDATION_ERROR,
                "search dispatch fields are invalid",
                request_id,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"reason": str(error)},
            )
        ) from error
    return candidate_index, attempt_id, dispatch


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
        try:
            request_id = _request_id(request, request_id_factory)
        except (TypeError, ValueError) as error:
            return _error_response(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "strategy validation request is invalid",
                    "unknown",
                    status.HTTP_400_BAD_REQUEST,
                    details={"reason": str(error)},
                )
            )
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
            if parsed_cursor is not None and collection.snapshot_digest != parsed_cursor.snapshot_digest:
                raise ValueError("adapter returned a collection for a different cursor snapshot")
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

    @router.post("/experiments/{experiment_id}/search", status_code=status.HTTP_202_ACCEPTED)
    async def initialize_search(
        experiment_id: str,
        request: Request,
        body: Any = Body(...),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        adapter: StrategyLabApiAdapter = Depends(adapter_dependency),
        principal: Any = Depends(principal_dependency),
    ) -> JSONResponse:
        """Create or replay a durable resumable search candidate queue."""

        try:
            request_id = _request_id(request, request_id_factory)
            body = await _strict_json_body(request, request_id)
            try:
                key = _safe_header_value(idempotency_key, "Idempotency-Key", 256)
            except (TypeError, ValueError) as error:
                return _error_response(
                    _api_error(
                        ApiErrorCode.VALIDATION_ERROR,
                        "Idempotency-Key must be non-empty, at most 256 characters, and control-free",
                        request_id,
                        status.HTTP_400_BAD_REQUEST,
                        details={"reason": str(error)},
                    )
                )
            state = _parse_search_initialization(
                body,
                experiment_fingerprint=experiment_id,
                request_id=request_id,
                now=clock(),
            )
            initialize = getattr(adapter, "initialize_search", None)
            if not callable(initialize):
                return _error_response(
                    _api_error(
                        ApiErrorCode.PRECONDITION_FAILED,
                        "search state adapter is not configured",
                        request_id,
                        status.HTTP_501_NOT_IMPLEMENTED,
                        details={"reason": "the host has not supplied search persistence"},
                    )
                )
            resolution = await _resolve(
                initialize(
                    principal=principal,
                    request_id=request_id,
                    idempotency_key=key,
                    state=state,
                )
            )
            if not isinstance(resolution, SearchStateResolution):
                raise TypeError("adapter returned an invalid search state resolution")
            if resolution.decision is SearchStateDecision.REJECT:
                return _error_response(
                    _api_error(
                        ApiErrorCode.CONFLICT,
                        resolution.rejection_reason or "search experiment is already bound to different content",
                        request_id,
                        status.HTTP_409_CONFLICT,
                    )
                )
            response = JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=serialize_search_state(resolution, request_id=request_id),
            )
            response.headers["X-Request-ID"] = request_id
            return response
        except ApiAdapterError as error:
            return _error_response(error.error)
        except (TypeError, ValueError) as error:
            return _error_response(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "search initialization request is invalid",
                    locals().get("request_id", "unknown"),
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    details={"reason": str(error)},
                )
            )
        except Exception:  # pragma: no cover - defensive adapter boundary
            logger.exception("Strategy Lab v2 search initialization failed")
            return _error_response(
                _api_error(
                    ApiErrorCode.INTERNAL_ERROR,
                    "Strategy Lab v2 search initialization failed",
                    locals().get("request_id", "unknown"),
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    retryable=True,
                )
            )

    @router.post(
        "/experiments/{experiment_id}/search/cancel", status_code=status.HTTP_202_ACCEPTED
    )
    async def cancel_search(
        experiment_id: str,
        request: Request,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        adapter: StrategyLabApiAdapter = Depends(adapter_dependency),
        principal: Any = Depends(principal_dependency),
    ) -> JSONResponse:
        """Request durable cancellation of a search queue."""

        try:
            request_id = _request_id(request, request_id_factory)
            try:
                key = _safe_header_value(idempotency_key, "Idempotency-Key", 256)
                require_sha256_digest(experiment_id, field_name="experiment_fingerprint")
            except (TypeError, ValueError) as error:
                return _error_response(
                    _api_error(
                        ApiErrorCode.VALIDATION_ERROR,
                        "search cancellation identity is invalid",
                        request_id,
                        status.HTTP_400_BAD_REQUEST,
                        details={"reason": str(error)},
                    )
                )
            cancel = getattr(adapter, "cancel_search", None)
            if not callable(cancel):
                return _error_response(
                    _api_error(
                        ApiErrorCode.PRECONDITION_FAILED,
                        "search state adapter is not configured",
                        request_id,
                        status.HTTP_501_NOT_IMPLEMENTED,
                        details={"reason": "the host has not supplied search persistence"},
                    )
                )
            cancellation_request_id = content_digest(
                {
                    "experiment_fingerprint": experiment_id,
                    "idempotency_key": key,
                }
            )
            resolution = await _resolve(
                cancel(
                    principal=principal,
                    request_id=request_id,
                    idempotency_key=key,
                    experiment_fingerprint=experiment_id,
                    cancellation_request_id=cancellation_request_id,
                    now=clock(),
                )
            )
            if not isinstance(resolution, SearchStateResolution):
                raise TypeError("adapter returned an invalid search cancellation resolution")
            if resolution.decision is SearchStateDecision.REJECT:
                return _error_response(
                    _api_error(
                        ApiErrorCode.CONFLICT,
                        resolution.rejection_reason or "search cancellation was rejected",
                        request_id,
                        status.HTTP_409_CONFLICT,
                    )
                )
            response = JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=serialize_search_state(resolution, request_id=request_id),
            )
            response.headers["X-Request-ID"] = request_id
            return response
        except ApiAdapterError as error:
            return _error_response(error.error)
        except (TypeError, ValueError) as error:
            return _error_response(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "search cancellation request is invalid",
                    locals().get("request_id", "unknown"),
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    details={"reason": str(error)},
                )
            )
        except Exception:  # pragma: no cover - defensive adapter boundary
            logger.exception("Strategy Lab v2 search cancellation failed")
            return _error_response(
                _api_error(
                    ApiErrorCode.INTERNAL_ERROR,
                    "Strategy Lab v2 search cancellation failed",
                    locals().get("request_id", "unknown"),
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    retryable=True,
                )
            )

    @router.post(
        "/experiments/{experiment_id}/search/dispatch", status_code=status.HTTP_202_ACCEPTED
    )
    async def dispatch_search_candidate(
        experiment_id: str,
        request: Request,
        body: Any = Body(...),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        adapter: StrategyLabApiAdapter = Depends(adapter_dependency),
        principal: Any = Depends(principal_dependency),
    ) -> JSONResponse:
        """Stage one search candidate through the host's atomic worker boundary."""

        try:
            request_id = _request_id(request, request_id_factory)
            body = await _strict_json_body(request, request_id)
            key = _safe_header_value(idempotency_key, "Idempotency-Key", 256)
            candidate_index, attempt_id, dispatch_request = _parse_search_dispatch(
                body,
                experiment_fingerprint=experiment_id,
                idempotency_key=key,
                request_id=request_id,
            )
            dispatch = getattr(adapter, "dispatch_search_candidate", None)
            if not callable(dispatch):
                return _error_response(
                    _api_error(
                        ApiErrorCode.PRECONDITION_FAILED,
                        "search dispatch adapter is not configured",
                        request_id,
                        status.HTTP_501_NOT_IMPLEMENTED,
                        details={
                            "reason": "the host has not supplied atomic search worker persistence"
                        },
                    )
                )
            resolution = await _resolve(
                dispatch(
                    principal=principal,
                    request_id=request_id,
                    experiment_fingerprint=experiment_id,
                    candidate_index=candidate_index,
                    attempt_id=attempt_id,
                    dispatch_request=dispatch_request,
                    payload=body,
                )
            )
            if not isinstance(resolution, SearchDispatchResolution):
                raise TypeError("adapter returned an invalid search dispatch resolution")
            if resolution.decision is SearchDispatchDecision.SATURATED:
                return _error_response(
                    _api_error(
                        ApiErrorCode.RATE_LIMITED,
                        "search worker capacity is saturated",
                        request_id,
                        status.HTTP_429_TOO_MANY_REQUESTS,
                        retryable=True,
                    )
                )
            if resolution.decision in {
                SearchDispatchDecision.CONFLICT,
                SearchDispatchDecision.REJECT,
            }:
                code = (
                    ApiErrorCode.IDEMPOTENCY_CONFLICT
                    if resolution.decision is SearchDispatchDecision.CONFLICT
                    else ApiErrorCode.PRECONDITION_FAILED
                )
                return _error_response(
                    _api_error(
                        code,
                        resolution.rejection_reason or "search candidate dispatch was rejected",
                        request_id,
                        status.HTTP_409_CONFLICT,
                    )
                )
            response = JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=serialize_search_dispatch(
                    resolution,
                    request_id=request_id,
                    candidate_index=candidate_index,
                    attempt_id=attempt_id,
                ),
            )
            response.headers["X-Request-ID"] = request_id
            return response
        except ApiAdapterError as error:
            return _error_response(error.error)
        except (TypeError, ValueError) as error:
            return _error_response(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "search dispatch request is invalid",
                    locals().get("request_id", "unknown"),
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    details={"reason": str(error)},
                )
            )
        except Exception:  # pragma: no cover - defensive adapter boundary
            logger.exception("Strategy Lab v2 search dispatch failed")
            return _error_response(
                _api_error(
                    ApiErrorCode.INTERNAL_ERROR,
                    "Strategy Lab v2 search dispatch failed",
                    locals().get("request_id", "unknown"),
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    retryable=True,
                )
            )

    @router.post("/capabilities/preflight")
    async def preflight_capability(
        request: Request,
        body: Any = Body(...),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        adapter: StrategyLabApiAdapter = Depends(adapter_dependency),
        principal: Any = Depends(principal_dependency),
    ) -> JSONResponse:
        """Evaluate a capability request through an application-owned binding.

        The package deliberately does not interpret provider entitlements or
        engine registrations.  Until the host supplies the optional adapter
        method, this endpoint returns a typed fail-closed response.
        """

        try:
            request_id = _request_id(request, request_id_factory)
            body = await _strict_json_body(request, request_id)
            if not isinstance(body, Mapping):
                return _error_response(
                    _api_error(
                        ApiErrorCode.VALIDATION_ERROR,
                        "capability preflight body must be a JSON object",
                        request_id,
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )
                )
            try:
                key = _safe_header_value(idempotency_key, "Idempotency-Key", 256)
            except (TypeError, ValueError) as error:
                return _error_response(
                    _api_error(
                        ApiErrorCode.VALIDATION_ERROR,
                        "Idempotency-Key must be non-empty, at most 256 characters, and control-free",
                        request_id,
                        status.HTTP_400_BAD_REQUEST,
                        details={"reason": str(error)},
                    )
                )
            try:
                payload_digest = content_digest(body)
            except (TypeError, ValueError) as error:
                return _error_response(
                    _api_error(
                        ApiErrorCode.VALIDATION_ERROR,
                        "capability preflight body is not canonical JSON",
                        request_id,
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        details={"reason": str(error)},
                    )
                )
            preflight = getattr(adapter, "preflight_capability", None)
            if not callable(preflight):
                return _error_response(
                    _api_error(
                        ApiErrorCode.CAPABILITY_UNSUPPORTED,
                        "capability preflight is not configured",
                        request_id,
                        status.HTTP_501_NOT_IMPLEMENTED,
                        details={"reason": "the host has not supplied a capability binding"},
                    )
                )
            summary = await _resolve(
                preflight(
                    principal=principal,
                    request_id=request_id,
                    idempotency_key=key,
                    payload=body,
                    payload_digest=payload_digest,
                )
            )
            if not isinstance(summary, CapabilitySummary):
                raise TypeError("adapter returned an invalid capability summary")
            response = JSONResponse(
                status_code=status.HTTP_200_OK,
                content=serialize_capability_summary(
                    summary, request_id=request_id, payload_digest=payload_digest
                ),
            )
            response.headers["X-Request-ID"] = request_id
            return response
        except ApiAdapterError as error:
            return _error_response(error.error)
        except (TypeError, ValueError) as error:
            return _error_response(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "capability preflight request is invalid",
                    locals().get("request_id", "unknown"),
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    details={"reason": str(error)},
                )
            )
        except Exception:  # pragma: no cover - defensive adapter boundary
            logger.exception("Strategy Lab v2 capability preflight failed")
            return _error_response(
                _api_error(
                    ApiErrorCode.INTERNAL_ERROR,
                    "Strategy Lab v2 capability preflight failed",
                    locals().get("request_id", "unknown"),
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    retryable=True,
                )
            )

    @router.post("/legacy/imports", status_code=status.HTTP_202_ACCEPTED)
    async def import_legacy(
        request: Request,
        body: Any = Body(...),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        adapter: StrategyLabApiAdapter = Depends(adapter_dependency),
        principal: Any = Depends(principal_dependency),
    ) -> JSONResponse:
        """Preserve one legacy record and return an explicit compatibility report."""

        try:
            request_id = _request_id(request, request_id_factory)
            body = await _strict_json_body(request, request_id)
            import_request, assessment = _parse_legacy_import(
                body,
                idempotency_key=idempotency_key,
                request_id=request_id,
                now=clock(),
            )
            resolution = await _resolve(
                adapter.import_legacy(
                    principal=principal,
                    request_id=request_id,
                    request=import_request,
                    assessment=assessment,
                )
            )
            if not isinstance(resolution, LegacyImportResolution):
                raise TypeError("adapter returned an invalid legacy import resolution")
            if resolution.decision is LegacyImportDecision.CONFLICT:
                return _error_response(
                    _api_error(
                        ApiErrorCode.CONFLICT,
                        resolution.rejection_reason
                        or "legacy id is already bound to different import content",
                        request_id,
                        status.HTTP_409_CONFLICT,
                    )
                )
            if resolution.decision is LegacyImportDecision.REJECT:
                return _error_response(
                    _api_error(
                        ApiErrorCode.PRECONDITION_FAILED,
                        resolution.rejection_reason or "legacy import was rejected",
                        request_id,
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )
                )
            response = JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=serialize_legacy_import(resolution, request_id=request_id),
            )
            response.headers["X-Request-ID"] = request_id
            return response
        except ApiAdapterError as error:
            return _error_response(error.error)
        except (TypeError, ValueError) as error:
            return _error_response(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "legacy import request is invalid",
                    locals().get("request_id", "unknown"),
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    details={"reason": str(error)},
                )
            )
        except Exception:  # pragma: no cover - defensive adapter boundary
            logger.exception("Strategy Lab v2 legacy import failed")
            return _error_response(
                _api_error(
                    ApiErrorCode.INTERNAL_ERROR,
                    "Strategy Lab v2 legacy import failed",
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

    @router.post("/{resource}", status_code=status.HTTP_202_ACCEPTED)
    async def create_resource(
        resource: str,
        request: Request,
        body: Any = Body(...),
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
        adapter: StrategyLabApiAdapter = Depends(adapter_dependency),
        principal: Any = Depends(principal_dependency),
    ) -> JSONResponse:
        """Create one mutable resource through an application-owned adapter."""

        try:
            request_id = _request_id(request, request_id_factory)
            parsed_resource = _resource_type(resource, request_id)
            if isinstance(parsed_resource, JSONResponse):
                return parsed_resource
            if parsed_resource not in _MUTABLE_RESOURCE_TYPES:
                return _error_response(
                    _api_error(
                        ApiErrorCode.PRECONDITION_FAILED,
                        "the requested Strategy Lab v2 resource is read-only",
                        request_id,
                        status.HTTP_405_METHOD_NOT_ALLOWED,
                        details={"resource": parsed_resource.value},
                    )
                )
            body = await _strict_json_body(request, request_id)
            mutation = _parse_resource_mutation(
                body,
                resource_type=parsed_resource,
                idempotency_key=idempotency_key,
                request_id=request_id,
                now=clock(),
            )
            result = await _resolve(
                adapter.create_resource(
                    principal=principal,
                    request_id=request_id,
                    request=mutation,
                )
            )
            if not isinstance(result, ResourceMutationServiceResult):
                raise TypeError("adapter returned an invalid resource mutation result")
            if result.resolution.decision is ResourceMutationDecision.IDEMPOTENCY_CONFLICT:
                return _error_response(
                    _api_error(
                        ApiErrorCode.IDEMPOTENCY_CONFLICT,
                        "Idempotency-Key is already bound to different resource content",
                        request_id,
                        status.HTTP_409_CONFLICT,
                        details={
                            "mutation_id": (
                                result.receipt.mutation_id if result.receipt is not None else None
                            )
                        },
                    )
                )
            if result.resolution.decision is ResourceMutationDecision.REJECT:
                return _error_response(
                    _api_error(
                        ApiErrorCode.PRECONDITION_FAILED,
                        result.resolution.rejection_reason or "resource mutation was rejected",
                        request_id,
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )
                )
            response = JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=serialize_resource_mutation(result),
            )
            response.headers["X-Request-ID"] = request_id
            return response
        except ApiAdapterError as error:
            return _error_response(error.error)
        except (TypeError, ValueError) as error:
            return _error_response(
                _api_error(
                    ApiErrorCode.VALIDATION_ERROR,
                    "resource mutation request is invalid",
                    locals().get("request_id", "unknown"),
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    details={"reason": str(error)},
                )
            )
        except Exception:  # pragma: no cover - defensive adapter boundary
            logger.exception("Strategy Lab v2 resource mutation failed")
            return _error_response(
                _api_error(
                    ApiErrorCode.INTERNAL_ERROR,
                    "Strategy Lab v2 resource mutation failed",
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
    "CapabilityPreflightAdapter",
    "SearchDispatchApiAdapter",
    "SearchStateApiAdapter",
    "StrategyLabApiAdapter",
    "SubmissionServiceResult",
    "create_strategy_lab_router",
    "serialize_collection",
    "serialize_command",
    "serialize_capability_summary",
    "serialize_search_dispatch",
    "serialize_search_state",
    "serialize_resource",
    "serialize_resource_identifier",
    "serialize_submission",
]
