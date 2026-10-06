"""Dedicated local process for owner-scoped search trial preparation.

This ASGI app is intended to run in its own single-worker process over a Unix
domain socket. Trial hydration and runtime materialization therefore never run
on the public FastAPI event loop. The API dispatch client and dedicated
workers' terminal-progress client use the shared local token; completion hints
are reconciled against PostgreSQL dispatch and result receipts before queue
state can change.
"""

from __future__ import annotations

import asyncio
import hmac
import importlib
import inspect
import json
import logging
import os
import stat
from collections.abc import Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from app.strategy_lab_v2.api_contracts import ApiError, ApiErrorCode
from app.strategy_lab_v2.application import (
    ApiAdapterError,
    PostgresStrategyLabV2Adapter,
)
from app.strategy_lab_v2.local_conformance_source import (
    LocalNautilusRcConformanceEvidenceSource,
)
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.search_dispatch_rpc import (
    SEARCH_DISPATCH_RPC_MAX_REQUEST_BYTES,
    SEARCH_DISPATCH_RPC_MAX_RESPONSE_BYTES,
    SEARCH_DISPATCH_RPC_PATH,
    WALK_FORWARD_PROGRESS_RPC_PATH,
    SearchDispatchRpcCommand,
    WalkForwardProgressRpcCommand,
    WalkForwardProgressRpcReceipt,
    encode_error_response,
    encode_result_response,
)
from app.strategy_lab_v2.search_preparation_composition import (
    SearchPreparationHostBindings,
    create_search_preparation_evidence_resolver,
)

_LOG = logging.getLogger("strategy_lab_v2.preparation")
_AUTH_TOKEN_ENV = "STRATEGY_LAB_V2_PREPARATION_AUTH_TOKEN"
_SOCKET_PATH_ENV = "STRATEGY_LAB_V2_PREPARATION_SOCKET_PATH"
_ARTIFACT_ROOT_ENV = "STRATEGY_LAB_V2_ARTIFACT_ROOT"
_BINDINGS_FACTORY_ENV = "STRATEGY_LAB_V2_PREPARATION_BINDINGS_FACTORY"


def create_search_preparation_app(
    adapter: PostgresStrategyLabV2Adapter,
    *,
    auth_token: str,
    socket_path: Path | None = None,
    max_request_bytes: int = SEARCH_DISPATCH_RPC_MAX_REQUEST_BYTES,
    max_response_bytes: int = SEARCH_DISPATCH_RPC_MAX_RESPONSE_BYTES,
) -> FastAPI:
    """Create the bounded internal dispatch endpoint for one preparation process."""

    if not isinstance(adapter, PostgresStrategyLabV2Adapter):
        raise TypeError("adapter must be a PostgresStrategyLabV2Adapter")
    _validate_auth_token(auth_token)
    if socket_path is not None and (
        not isinstance(socket_path, Path) or not socket_path.is_absolute()
    ):
        raise ValueError("socket_path must be an absolute Path")
    if (
        not isinstance(max_request_bytes, int)
        or isinstance(max_request_bytes, bool)
        or not 1024 <= max_request_bytes <= 1024 * 1024
    ):
        raise ValueError("max_request_bytes is outside the supported bounds")
    if (
        not isinstance(max_response_bytes, int)
        or isinstance(max_response_bytes, bool)
        or not 1024 <= max_response_bytes <= 512 * 1024 * 1024
    ):
        raise ValueError("max_response_bytes is outside the supported bounds")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if socket_path is not None:
            _set_socket_permissions(socket_path)
        yield

    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.dispatch_lock = asyncio.Lock()

    @app.post(SEARCH_DISPATCH_RPC_PATH)
    async def dispatch_search(request: Request) -> Response:
        supplied_token = _bearer_token(request.headers.get("authorization"))
        if supplied_token is None or not hmac.compare_digest(supplied_token, auth_token):
            return _error_response(
                ApiError(
                    ApiErrorCode.AUTHORIZATION_REQUIRED,
                    "local preparation authentication is required",
                    _fallback_request_id(request),
                    401,
                    False,
                )
            )
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return _error_response(
                ApiError(
                    ApiErrorCode.VALIDATION_ERROR,
                    "local preparation requests must use JSON",
                    _fallback_request_id(request),
                    415,
                    False,
                )
            )
        try:
            raw_body = await request.body()
        except Exception:
            return _error_response(
                ApiError(
                    ApiErrorCode.VALIDATION_ERROR,
                    "local preparation request body could not be read",
                    _fallback_request_id(request),
                    400,
                    False,
                )
            )
        if len(raw_body) > max_request_bytes:
            return _error_response(
                ApiError(
                    ApiErrorCode.VALIDATION_ERROR,
                    "local preparation request exceeds its byte limit",
                    _fallback_request_id(request),
                    413,
                    False,
                )
            )
        try:
            wire_value = json.loads(
                raw_body.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
            command = SearchDispatchRpcCommand.from_wire(wire_value)
            if request.headers.get("x-request-id") != command.request_id:
                raise ValueError("request ID header differs from the command")
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            return _error_response(
                ApiError(
                    ApiErrorCode.VALIDATION_ERROR,
                    "local preparation request contract is invalid",
                    _fallback_request_id(request),
                    422,
                    False,
                    {"reason": str(error)[:256]},
                )
            )

        try:
            # This process is the serial preparation boundary. Materialization
            # can be CPU- and I/O-heavy; it must not share the public API loop.
            async with app.state.dispatch_lock:
                resolution = await adapter.dispatch_search_candidate(**command.callback_arguments())
            payload = encode_result_response(resolution)
            if len(payload) > max_response_bytes:
                raise ValueError("prepared search dispatch response exceeds its byte limit")
            return Response(payload, status_code=200, media_type="application/json")
        except ApiAdapterError as error:
            return _error_response(error.error)
        except Exception:
            _LOG.exception(
                "isolated search dispatch preparation failed",
                extra={"request_id": command.request_id},
            )
            return _error_response(
                ApiError(
                    ApiErrorCode.INTERNAL_ERROR,
                    "isolated search dispatch preparation failed",
                    command.request_id,
                    500,
                    False,
                )
            )

    @app.post(WALK_FORWARD_PROGRESS_RPC_PATH)
    async def reconcile_walk_forward_progress(request: Request) -> Response:
        supplied_token = _bearer_token(request.headers.get("authorization"))
        if supplied_token is None or not hmac.compare_digest(supplied_token, auth_token):
            return _error_response(
                ApiError(
                    ApiErrorCode.AUTHORIZATION_REQUIRED,
                    "local preparation authentication is required",
                    _fallback_request_id(request),
                    401,
                    False,
                )
            )
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return _error_response(
                ApiError(
                    ApiErrorCode.VALIDATION_ERROR,
                    "local preparation requests must use JSON",
                    _fallback_request_id(request),
                    415,
                    False,
                )
            )
        try:
            raw_body = await request.body()
            if len(raw_body) > max_request_bytes:
                raise ValueError("walk-forward progress command exceeds its byte limit")
            wire_value = json.loads(
                raw_body.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
            command = WalkForwardProgressRpcCommand.from_wire(wire_value)
            if request.headers.get("x-request-id") != command.request_id:
                raise ValueError("request ID header differs from the command")
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            return _error_response(
                ApiError(
                    ApiErrorCode.VALIDATION_ERROR,
                    "walk-forward progress command is invalid",
                    _fallback_request_id(request),
                    422,
                    False,
                    {"reason": str(error)[:256]},
                )
            )

        try:
            async with app.state.dispatch_lock:
                value = await adapter.reconcile_walk_forward_terminal(
                    **command.callback_arguments()
                )
            receipt = WalkForwardProgressRpcReceipt.from_wire(
                {
                    **value,
                    "schema": "strategy-lab.walk-forward-progress-result.v1",
                    "dispatched_candidate_indices": list(value["dispatched_candidate_indices"]),
                }
            )
            return JSONResponse(
                {
                    "receipt": receipt.to_wire(),
                    "schema": "strategy-lab.walk-forward-progress-result.v1",
                },
                status_code=200,
            )
        except ApiAdapterError as error:
            return _error_response(error.error)
        except Exception:
            _LOG.exception(
                "walk-forward completion reconciliation failed",
                extra={"request_id": command.request_id},
            )
            return _error_response(
                ApiError(
                    ApiErrorCode.INTERNAL_ERROR,
                    "walk-forward completion reconciliation failed",
                    command.request_id,
                    500,
                    True,
                )
            )

    return app


def create_search_preparation_app_from_environment(
    environment: Mapping[str, str] | None = None,
) -> tuple[FastAPI, Path]:
    """Load trusted local evidence composition and the PostgreSQL adapters."""

    environment = os.environ if environment is None else environment
    auth_token = environment.get(_AUTH_TOKEN_ENV, "").strip()
    _validate_auth_token(auth_token)
    socket_value = environment.get(_SOCKET_PATH_ENV, "").strip()
    if not socket_value:
        raise ValueError(f"{_SOCKET_PATH_ENV} must be configured")
    socket_path = Path(socket_value)
    if not socket_path.is_absolute():
        raise ValueError(f"{_SOCKET_PATH_ENV} must be an absolute path")
    _prepare_socket_path(socket_path)

    session_factory = getattr(importlib.import_module("app.database"), "AsyncSessionLocal")
    persistence = PostgresStrategyLabV2Persistence.build(session_factory)
    artifact_root_value = environment.get(_ARTIFACT_ROOT_ENV, "").strip()
    if not artifact_root_value:
        raise ValueError(f"{_ARTIFACT_ROOT_ENV} must be configured")
    artifact_root = Path(artifact_root_value).expanduser()
    if not artifact_root.is_absolute():
        raise ValueError(f"{_ARTIFACT_ROOT_ENV} must be an absolute path")

    evidence_source = LocalNautilusRcConformanceEvidenceSource.from_environment(environment)
    if evidence_source is None:
        raise ValueError("operator-pinned local Nautilus RC evidence must be configured")
    conformance_resolution = evidence_source.load()

    factory_spec = environment.get(_BINDINGS_FACTORY_ENV, "").strip()
    if not factory_spec:
        raise ValueError(f"{_BINDINGS_FACTORY_ENV} must be configured")
    factory = _load_bindings_factory(factory_spec)
    bindings = factory(persistence, artifact_root, conformance_resolution)
    if inspect.isawaitable(bindings):
        if inspect.iscoroutine(bindings):
            bindings.close()
        raise TypeError(f"{_BINDINGS_FACTORY_ENV} must return synchronously")
    if not isinstance(bindings, SearchPreparationHostBindings):
        raise TypeError(f"{_BINDINGS_FACTORY_ENV} must return SearchPreparationHostBindings")
    resolver = create_search_preparation_evidence_resolver(
        persistence,
        artifact_root,
        host_bindings=bindings,
        conformance_resolution=conformance_resolution,
    )
    adapter = PostgresStrategyLabV2Adapter(
        session_factory,
        persistence=persistence,
        search_dispatch_evidence=resolver,
    )
    return create_search_preparation_app(
        adapter,
        auth_token=auth_token,
        socket_path=socket_path,
    ), socket_path


def main() -> None:
    """Run one serial preparation service on the configured local socket."""

    app, socket_path = create_search_preparation_app_from_environment()
    uvicorn.run(
        app,
        uds=str(socket_path),
        workers=1,
        access_log=False,
        proxy_headers=False,
        log_level=os.environ.get("LOG_LEVEL", "INFO").lower(),
    )


def _validate_auth_token(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) < 32
        or len(value) > 512
        or not value.isascii()
        or any(character.isspace() for character in value)
    ):
        raise ValueError("preparation auth token must be 32-512 non-space ASCII characters")


def _bearer_token(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.startswith("Bearer "):
        return None
    token = value.removeprefix("Bearer ")
    return token if token else None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("local preparation JSON contains duplicate fields")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"local preparation JSON contains unsupported constant {value}")


def _fallback_request_id(request: Request) -> str:
    value = request.headers.get("x-request-id", "")
    if (
        not value
        or len(value) > 128
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return "strategy-lab-preparation-rpc"
    return value


def _error_response(error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content=json.loads(encode_error_response(error)),
    )


def _prepare_socket_path(path: Path) -> None:
    if not path.parent.is_dir():
        raise ValueError("preparation socket directory must already exist")
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(metadata.st_mode):
        raise ValueError("refusing to replace a non-socket preparation path")
    path.unlink()


def _set_socket_permissions(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise RuntimeError("preparation service socket was not created") from error
    if not stat.S_ISSOCK(metadata.st_mode):
        raise RuntimeError("preparation service path is not a Unix-domain socket")
    os.chmod(path, 0o660, follow_symlinks=False)


def _load_bindings_factory(spec: str) -> Any:
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name.strip() or not attribute.strip():
        raise ValueError(f"{_BINDINGS_FACTORY_ENV} must use module:attribute syntax")
    factory = getattr(importlib.import_module(module_name.strip()), attribute.strip(), None)
    if not callable(factory):
        raise TypeError(f"{_BINDINGS_FACTORY_ENV} target must be callable")
    if inspect.iscoroutinefunction(factory):
        raise TypeError(f"{_BINDINGS_FACTORY_ENV} must be a synchronous factory")
    return factory


if __name__ == "__main__":
    main()


__all__ = [
    "create_search_preparation_app",
    "create_search_preparation_app_from_environment",
    "main",
]
