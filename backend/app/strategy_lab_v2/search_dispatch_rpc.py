"""Authenticated local RPC for isolated search-trial preparation.

The API process sends only the authenticated owner and immutable dispatch
coordinates over a Unix-domain socket. A dedicated preparation process hydrates
the owner-scoped trial, materializes frozen runtime inputs, and performs the
atomic PostgreSQL dispatch before returning a typed resolution. Strategy code
and provider/network access are never exposed through this transport.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.strategy_lab_v2.api_contracts import ApiError, ApiErrorCode
from app.strategy_lab_v2.canonical import canonical_json, content_digest, require_sha256_digest
from app.strategy_lab_v2.dispatch import SearchDispatchIntent
from app.strategy_lab_v2.postgres_result_materialization import decode_canonical_contract
from app.strategy_lab_v2.search_dispatch import SearchDispatchResolution

SEARCH_DISPATCH_RPC_COMMAND_SCHEMA = "strategy-lab.search-dispatch-command.v1"
SEARCH_DISPATCH_RPC_RESULT_SCHEMA = "strategy-lab.search-dispatch-result.v1"
SEARCH_DISPATCH_RPC_ERROR_SCHEMA = "strategy-lab.search-dispatch-error.v1"
SEARCH_DISPATCH_RPC_PATH = "/internal/v1/search-dispatch"
SEARCH_DISPATCH_RPC_URL = "http://strategy-lab-v2.local"
SEARCH_DISPATCH_RPC_MAX_REQUEST_BYTES = 64 * 1024
SEARCH_DISPATCH_RPC_MAX_RESPONSE_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SearchDispatchRpcCommand:
    """Minimal owner-scoped command accepted by the local preparation service."""

    principal_id: str
    request_id: str
    experiment_fingerprint: str
    candidate_index: int
    attempt_id: str
    dispatch_intent: SearchDispatchIntent

    def __post_init__(self) -> None:
        for name, maximum in (("principal_id", 256), ("request_id", 128), ("attempt_id", 256)):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f"{name} must be non-empty and at most {maximum} characters")
            if any(ord(character) < 32 or ord(character) == 127 for character in value):
                raise ValueError(f"{name} must not contain control characters")
        require_sha256_digest(
            self.experiment_fingerprint,
            field_name="experiment_fingerprint",
        )
        if (
            not isinstance(self.candidate_index, int)
            or isinstance(self.candidate_index, bool)
            or self.candidate_index < 0
        ):
            raise ValueError("candidate_index must be a non-negative integer")
        if not isinstance(self.dispatch_intent, SearchDispatchIntent):
            raise TypeError("dispatch_intent must be a SearchDispatchIntent")
        if self.dispatch_intent.attempt_id != self.attempt_id:
            raise ValueError("dispatch intent must reference the requested attempt")

    @classmethod
    def from_call(
        cls,
        *,
        principal: Any,
        request_id: str,
        experiment_fingerprint: str,
        candidate_index: int,
        attempt_id: str,
        dispatch_intent: SearchDispatchIntent,
    ) -> SearchDispatchRpcCommand:
        owner = getattr(principal, "id", principal)
        if owner is None or isinstance(owner, bool) or not isinstance(owner, str | int):
            raise ValueError("authenticated principal identity is required")
        return cls(
            principal_id=str(owner).strip(),
            request_id=request_id,
            experiment_fingerprint=experiment_fingerprint,
            candidate_index=candidate_index,
            attempt_id=attempt_id,
            dispatch_intent=dispatch_intent,
        )

    def to_wire(self) -> dict[str, Any]:
        """Return the strict versioned JSON command and its content fingerprint."""

        body: dict[str, Any] = {
            "candidate_index": self.candidate_index,
            "dispatch_intent": {
                "attempt_id": self.dispatch_intent.attempt_id,
                "created_at": self.dispatch_intent.created_at.isoformat(
                    timespec="microseconds"
                ).replace("+00:00", "Z"),
                "idempotency_key": self.dispatch_intent.idempotency_key,
                "queue_name": self.dispatch_intent.queue_name,
            },
            "experiment_fingerprint": self.experiment_fingerprint,
            "principal_id": self.principal_id,
            "request_id": self.request_id,
            "schema": SEARCH_DISPATCH_RPC_COMMAND_SCHEMA,
            "attempt_id": self.attempt_id,
        }
        body["command_fingerprint"] = content_digest(body)
        return body

    @classmethod
    def from_wire(cls, value: Any) -> SearchDispatchRpcCommand:
        if not isinstance(value, Mapping) or set(value) != {
            "attempt_id",
            "candidate_index",
            "command_fingerprint",
            "dispatch_intent",
            "experiment_fingerprint",
            "principal_id",
            "request_id",
            "schema",
        }:
            raise ValueError("search dispatch command fields are invalid")
        if value["schema"] != SEARCH_DISPATCH_RPC_COMMAND_SCHEMA:
            raise ValueError("search dispatch command schema is unsupported")
        fingerprint = value["command_fingerprint"]
        require_sha256_digest(fingerprint, field_name="command_fingerprint")
        unsigned = {key: item for key, item in value.items() if key != "command_fingerprint"}
        if fingerprint != content_digest(unsigned):
            raise ValueError("search dispatch command fingerprint does not match its content")
        intent_value = value["dispatch_intent"]
        if not isinstance(intent_value, Mapping) or set(intent_value) != {
            "attempt_id",
            "created_at",
            "idempotency_key",
            "queue_name",
        }:
            raise ValueError("search dispatch intent fields are invalid")
        created_at = intent_value["created_at"]
        if not isinstance(created_at, str):
            raise ValueError("dispatch intent created_at must be a timestamp")
        try:
            parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("dispatch intent created_at is invalid") from error
        command = cls(
            principal_id=value["principal_id"],
            request_id=value["request_id"],
            experiment_fingerprint=value["experiment_fingerprint"],
            candidate_index=value["candidate_index"],
            attempt_id=value["attempt_id"],
            dispatch_intent=SearchDispatchIntent(
                idempotency_key=intent_value["idempotency_key"],
                attempt_id=intent_value["attempt_id"],
                queue_name=intent_value["queue_name"],
                created_at=parsed_created_at,
            ),
        )
        if command.to_wire() != dict(value):
            raise ValueError("search dispatch command is not normalized")
        return command

    def callback_arguments(self) -> dict[str, Any]:
        return {
            "principal": self.principal_id,
            "request_id": self.request_id,
            "experiment_fingerprint": self.experiment_fingerprint,
            "candidate_index": self.candidate_index,
            "attempt_id": self.attempt_id,
            "dispatch_intent": self.dispatch_intent,
        }


@dataclass(frozen=True, slots=True)
class UnixSocketSearchDispatchClient:
    """Async API-side resolver using only a configured Unix-domain socket."""

    socket_path: Path
    auth_token: str
    timeout_seconds: float = 600.0
    max_response_bytes: int = SEARCH_DISPATCH_RPC_MAX_RESPONSE_BYTES

    def __post_init__(self) -> None:
        if not isinstance(self.socket_path, Path) or not self.socket_path.is_absolute():
            raise ValueError("preparation socket path must be an absolute Path")
        if (
            not isinstance(self.auth_token, str)
            or len(self.auth_token) < 32
            or not self.auth_token.isascii()
            or any(character.isspace() for character in self.auth_token)
        ):
            raise ValueError(
                "preparation auth token must be at least 32 non-space ASCII characters"
            )
        if (
            not isinstance(self.timeout_seconds, int | float)
            or isinstance(self.timeout_seconds, bool)
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
            or self.timeout_seconds > 3600
        ):
            raise ValueError("timeout_seconds must be greater than 0 and at most 3600")
        if (
            not isinstance(self.max_response_bytes, int)
            or isinstance(self.max_response_bytes, bool)
            or self.max_response_bytes < 1024
            or self.max_response_bytes > 512 * 1024 * 1024
        ):
            raise ValueError("max_response_bytes is outside the supported bounds")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> UnixSocketSearchDispatchClient:
        values = environment if environment is not None else os.environ
        socket_value = values.get("STRATEGY_LAB_V2_PREPARATION_SOCKET_PATH", "").strip()
        token = values.get("STRATEGY_LAB_V2_PREPARATION_AUTH_TOKEN", "").strip()
        if not socket_value or not token:
            raise ValueError("preparation socket path and auth token must both be configured")
        return cls(Path(socket_value), token)

    async def __call__(self, **kwargs: Any) -> SearchDispatchResolution:
        from app.strategy_lab_v2.application import ApiAdapterError

        command = SearchDispatchRpcCommand.from_call(**kwargs)
        command_bytes = _encode_json(command.to_wire())
        if len(command_bytes) > SEARCH_DISPATCH_RPC_MAX_REQUEST_BYTES:
            raise ValueError("search dispatch command exceeds the local RPC request limit")
        transport = httpx.AsyncHTTPTransport(uds=str(self.socket_path), retries=0)
        try:
            async with httpx.AsyncClient(
                transport=transport,
                base_url=SEARCH_DISPATCH_RPC_URL,
                timeout=self.timeout_seconds,
                trust_env=False,
            ) as client:
                async with client.stream(
                    "POST",
                    SEARCH_DISPATCH_RPC_PATH,
                    content=command_bytes,
                    headers={
                        "Authorization": f"Bearer {self.auth_token}",
                        "Content-Type": "application/json",
                        "X-Request-ID": command.request_id,
                    },
                ) as response:
                    response_bytes = await _read_bounded_response(
                        response,
                        limit=(
                            64 * 1024 if response.status_code >= 400 else self.max_response_bytes
                        ),
                    )
                    if response.status_code >= 400:
                        raise ApiAdapterError(
                            _decode_api_error(
                                response_bytes,
                                response_status=response.status_code,
                                request_id=command.request_id,
                            )
                        )
                    if response.status_code != 200:
                        raise ApiAdapterError(
                            ApiError(
                                ApiErrorCode.INTERNAL_ERROR,
                                "preparation service returned an unexpected status",
                                command.request_id,
                                502,
                                True,
                            )
                        )
        except ApiAdapterError:
            raise
        except httpx.TimeoutException as error:
            raise ApiAdapterError(
                _service_unavailable_error(command.request_id, "preparation service timed out")
            ) from error
        except httpx.RequestError as error:
            raise ApiAdapterError(
                _service_unavailable_error(command.request_id, "preparation service is unavailable")
            ) from error
        except ValueError as error:
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.INTERNAL_ERROR,
                    "preparation service response was invalid",
                    command.request_id,
                    502,
                    True,
                )
            ) from error

        try:
            value = _decode_json_object(response_bytes)
            if set(value) != {
                "resolution_canonical_json",
                "resolution_fingerprint",
                "schema",
            }:
                raise ValueError("search dispatch response fields are invalid")
            if value["schema"] != SEARCH_DISPATCH_RPC_RESULT_SCHEMA:
                raise ValueError("search dispatch response schema is unsupported")
            payload = value["resolution_canonical_json"]
            if not isinstance(payload, str) or not payload:
                raise ValueError("search dispatch result contract is missing")
            resolution = decode_canonical_contract(payload, SearchDispatchResolution)
            if not isinstance(resolution, SearchDispatchResolution):
                raise ValueError("search dispatch result has an invalid type")
            if value["resolution_fingerprint"] != content_digest(resolution):
                raise ValueError("search dispatch result fingerprint does not match its content")
            return resolution
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.INTERNAL_ERROR,
                    "preparation service response was invalid",
                    command.request_id,
                    502,
                    True,
                )
            ) from error


def build_api_bindings(_session_factory: Any, _persistence: Any) -> Any:
    """Build API host bindings that delegate search preparation over the UDS."""

    from app.strategy_lab_v2.application import StrategyLabV2ApiBindings

    return StrategyLabV2ApiBindings(
        search_dispatch=UnixSocketSearchDispatchClient.from_environment()
    )


def encode_result_response(resolution: SearchDispatchResolution) -> bytes:
    if not isinstance(resolution, SearchDispatchResolution):
        raise TypeError("resolution must be a SearchDispatchResolution")
    return _encode_json(
        {
            "resolution_canonical_json": canonical_json(resolution),
            "resolution_fingerprint": content_digest(resolution),
            "schema": SEARCH_DISPATCH_RPC_RESULT_SCHEMA,
        }
    )


def encode_error_response(error: ApiError) -> bytes:
    if not isinstance(error, ApiError):
        raise TypeError("error must be an ApiError")
    return _encode_json(
        {
            "error": {
                "code": error.code.value,
                "details": _plain_json(error.details),
                "message": error.message,
                "request_id": error.request_id,
                "retryable": error.retryable,
                "status_code": error.status_code,
            },
            "schema": SEARCH_DISPATCH_RPC_ERROR_SCHEMA,
        }
    )


def _decode_api_error(
    payload: bytes,
    *,
    response_status: int,
    request_id: str,
) -> ApiError:
    try:
        value = _decode_json_object(payload)
        error = value.get("error")
        if (
            set(value) != {"error", "schema"}
            or value["schema"] != SEARCH_DISPATCH_RPC_ERROR_SCHEMA
            or not isinstance(error, Mapping)
            or set(error)
            != {"code", "details", "message", "request_id", "retryable", "status_code"}
        ):
            raise ValueError("preparation service error fields are invalid")
        if error["status_code"] != response_status or not isinstance(error["details"], Mapping):
            raise ValueError("preparation service error status or details are invalid")
        return ApiError(
            code=ApiErrorCode(error["code"]),
            message=error["message"],
            request_id=error["request_id"],
            status_code=error["status_code"],
            retryable=error["retryable"],
            details=error["details"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ApiError(
            ApiErrorCode.INTERNAL_ERROR,
            "preparation service returned an invalid error response",
            request_id,
            502,
            True,
        )


def _service_unavailable_error(request_id: str, message: str) -> ApiError:
    return ApiError(
        ApiErrorCode.PRECONDITION_FAILED,
        message,
        request_id,
        503,
        True,
        {"reason": "the isolated local preparation process must be healthy"},
    )


def _encode_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _decode_json_object(payload: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("local RPC payload is not valid JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError("local RPC payload must be a JSON object")
    return decoded


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("local RPC payload contains duplicate fields")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"local RPC payload contains unsupported constant {value}")


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain_json(item) for item in value]
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


async def _read_bounded_response(response: httpx.Response, *, limit: int) -> bytes:
    chunks: list[bytes] = []
    byte_length = 0
    async for chunk in response.aiter_bytes():
        byte_length += len(chunk)
        if byte_length > limit:
            raise ValueError("local RPC response exceeds its configured byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


__all__ = [
    "SEARCH_DISPATCH_RPC_COMMAND_SCHEMA",
    "SEARCH_DISPATCH_RPC_ERROR_SCHEMA",
    "SEARCH_DISPATCH_RPC_MAX_REQUEST_BYTES",
    "SEARCH_DISPATCH_RPC_MAX_RESPONSE_BYTES",
    "SEARCH_DISPATCH_RPC_PATH",
    "SEARCH_DISPATCH_RPC_RESULT_SCHEMA",
    "SearchDispatchRpcCommand",
    "UnixSocketSearchDispatchClient",
    "build_api_bindings",
    "encode_error_response",
    "encode_result_response",
]
