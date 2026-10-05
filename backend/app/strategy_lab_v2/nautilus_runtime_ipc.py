"""Bounded, fingerprinted NDJSON frames for isolated Nautilus sessions.

Frames carry JSON wire values only. Large history and artifact payloads must be
passed by verified content-addressed references rather than embedded here.
"""

from __future__ import annotations

import json
import math
import re
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import BinaryIO, Protocol

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.nautilus_runtime_protocol import NAUTILUS_FORWARD_RUNTIME_IPC_SCHEMA

MAX_NAUTILUS_RUNTIME_IPC_FRAME_BYTES = 1_048_576
_FRAME_FIELDS = frozenset({"schema", "request_id", "operation", "status", "payload", "fingerprint"})


class NautilusRuntimeIpcOperation(StrEnum):
    OPEN = "open"
    EXECUTE = "execute"
    RESTORE = "restore"
    CLOSE = "close"


class NautilusRuntimeIpcStatus(StrEnum):
    REQUEST = "request"
    SUCCESS = "success"
    ERROR = "error"


class NautilusRuntimeIpcError(RuntimeError):
    """A sanitized operation failure returned by the isolated runtime."""

    def __init__(self, error_code: str) -> None:
        if (
            not isinstance(error_code, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", error_code) is None
        ):
            raise ValueError("error_code must be a bounded lowercase identifier")
        self.error_code = error_code
        super().__init__(f"isolated Nautilus runtime rejected the operation: {error_code}")


class NautilusRuntimeIpcOperationHandler(Protocol):
    """Stateful operation target hosted inside the isolated runtime process."""

    def open(self, payload: Mapping[str, object]) -> Mapping[str, object]: ...

    def execute(self, payload: Mapping[str, object]) -> Mapping[str, object]: ...

    def restore(self, payload: Mapping[str, object]) -> Mapping[str, object]: ...

    def close(self, payload: Mapping[str, object]) -> Mapping[str, object]: ...


class _FrameLineReader(Protocol):
    def readline(self, size: int = -1) -> bytes: ...


class _FrameWriter(Protocol):
    def write(self, data: bytes) -> object: ...

    def flush(self) -> None: ...


class NautilusRuntimeIpcClient:
    """Synchronous serialized request/reply client for one process stream pair."""

    def __init__(
        self,
        input_stream: _FrameLineReader,
        output_stream: _FrameWriter,
        *,
        max_frame_bytes: int = MAX_NAUTILUS_RUNTIME_IPC_FRAME_BYTES,
    ) -> None:
        if not callable(getattr(input_stream, "readline", None)):
            raise TypeError("input_stream must provide readline")
        if not callable(getattr(output_stream, "write", None)) or not callable(
            getattr(output_stream, "flush", None)
        ):
            raise TypeError("output_stream must provide write and flush")
        if (
            not isinstance(max_frame_bytes, int)
            or isinstance(max_frame_bytes, bool)
            or max_frame_bytes <= 1
        ):
            raise ValueError("max_frame_bytes must be an integer greater than one")
        self._input_stream = input_stream
        self._output_stream = output_stream
        self._max_frame_bytes = max_frame_bytes
        self._lock = threading.Lock()

    def request(
        self,
        operation: NautilusRuntimeIpcOperation,
        payload: Mapping[str, object],
        *,
        request_id: str | None = None,
    ) -> Mapping[str, object]:
        """Exchange one frame and validate its correlation and status.

        Supplying the same ``request_id`` and payload again is safe for retrying
        the latest request after a lost response; the server caches that reply.
        """

        identifier = uuid.uuid4().hex if request_id is None else request_id
        request = create_nautilus_runtime_ipc_frame(
            request_id=identifier,
            operation=operation,
            status=NautilusRuntimeIpcStatus.REQUEST,
            payload=payload,
        )
        with self._lock:
            self._output_stream.write(
                encode_nautilus_runtime_ipc_frame(
                    request,
                    max_frame_bytes=self._max_frame_bytes,
                )
            )
            self._output_stream.flush()
            response = read_nautilus_runtime_ipc_frame(
                self._input_stream,
                max_frame_bytes=self._max_frame_bytes,
            )
        if response is None:
            raise ValueError("isolated Nautilus runtime closed before replying")
        if response.request_id != request.request_id or response.operation is not operation:
            raise ValueError("isolated Nautilus runtime response correlation does not match")
        if response.status is NautilusRuntimeIpcStatus.ERROR:
            error_code = response.payload.get("error_code")
            if not isinstance(error_code, str) or not error_code:
                raise ValueError("isolated Nautilus runtime returned an invalid error response")
            raise NautilusRuntimeIpcError(error_code)
        if response.status is not NautilusRuntimeIpcStatus.SUCCESS:
            raise ValueError("isolated Nautilus runtime returned a non-response frame")
        return response.payload


@dataclass(frozen=True, slots=True)
class NautilusRuntimeIpcFrame:
    """One immutable and self-checking request or response frame."""

    request_id: str
    operation: NautilusRuntimeIpcOperation
    status: NautilusRuntimeIpcStatus
    payload: Mapping[str, object]
    fingerprint: str

    def __post_init__(self) -> None:
        _validate_request_id(self.request_id)
        if not isinstance(self.operation, NautilusRuntimeIpcOperation):
            raise TypeError("operation must be a NautilusRuntimeIpcOperation")
        if not isinstance(self.status, NautilusRuntimeIpcStatus):
            raise TypeError("status must be a NautilusRuntimeIpcStatus")
        plain_payload = _plain_json(self.payload)
        if not isinstance(plain_payload, dict):
            raise TypeError("payload must be a JSON object")
        require_sha256_digest(self.fingerprint, field_name="fingerprint")
        expected = content_digest(
            _unsigned_wire(
                self.request_id,
                self.operation,
                self.status,
                plain_payload,
            )
        )
        if self.fingerprint != expected:
            raise ValueError("runtime IPC frame fingerprint does not match its content")
        object.__setattr__(self, "payload", _freeze_wire(plain_payload))


def create_nautilus_runtime_ipc_frame(
    *,
    request_id: str,
    operation: NautilusRuntimeIpcOperation,
    status: NautilusRuntimeIpcStatus,
    payload: Mapping[str, object],
) -> NautilusRuntimeIpcFrame:
    """Create a frame after normalizing and validating its JSON payload."""

    plain_payload = _plain_json(payload)
    if not isinstance(plain_payload, dict):
        raise TypeError("payload must be a JSON object")
    fingerprint = content_digest(_unsigned_wire(request_id, operation, status, plain_payload))
    return NautilusRuntimeIpcFrame(
        request_id=request_id,
        operation=operation,
        status=status,
        payload=plain_payload,
        fingerprint=fingerprint,
    )


def encode_nautilus_runtime_ipc_frame(
    frame: NautilusRuntimeIpcFrame,
    *,
    max_frame_bytes: int = MAX_NAUTILUS_RUNTIME_IPC_FRAME_BYTES,
) -> bytes:
    """Serialize one bounded UTF-8 NDJSON frame, including its newline."""

    if not isinstance(frame, NautilusRuntimeIpcFrame):
        raise TypeError("frame must be a NautilusRuntimeIpcFrame")
    if (
        not isinstance(max_frame_bytes, int)
        or isinstance(max_frame_bytes, bool)
        or max_frame_bytes <= 1
    ):
        raise ValueError("max_frame_bytes must be an integer greater than one")
    plain_payload = _plain_json(frame.payload)
    if not isinstance(plain_payload, dict):
        raise TypeError("payload must be a JSON object")
    unsigned = _unsigned_wire(frame.request_id, frame.operation, frame.status, plain_payload)
    wire = {**unsigned, "fingerprint": frame.fingerprint}
    try:
        encoded = (
            json.dumps(
                wire,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError, UnicodeError) as error:
        raise ValueError("runtime IPC frame is not valid UTF-8 JSON") from error
    if len(encoded) > max_frame_bytes:
        raise ValueError("runtime IPC frame exceeds its byte limit")
    return encoded


def decode_nautilus_runtime_ipc_frame(
    encoded: bytes,
    *,
    max_frame_bytes: int = MAX_NAUTILUS_RUNTIME_IPC_FRAME_BYTES,
) -> NautilusRuntimeIpcFrame:
    """Parse exactly one bounded frame, rejecting duplicate keys and extensions."""

    if not isinstance(encoded, bytes):
        raise TypeError("encoded frame must be bytes")
    if (
        not isinstance(max_frame_bytes, int)
        or isinstance(max_frame_bytes, bool)
        or max_frame_bytes <= 1
    ):
        raise ValueError("max_frame_bytes must be an integer greater than one")
    if not encoded or len(encoded) > max_frame_bytes:
        raise ValueError("runtime IPC frame is empty or exceeds its byte limit")
    if not encoded.endswith(b"\n") or encoded.endswith(b"\r\n"):
        raise ValueError("runtime IPC frame must end with one LF newline")
    try:
        decoded = json.loads(
            encoded[:-1].decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("runtime IPC frame is malformed JSON") from error
    if not isinstance(decoded, dict) or set(decoded) != _FRAME_FIELDS:
        raise ValueError("runtime IPC frame fields are invalid")
    if decoded["schema"] != NAUTILUS_FORWARD_RUNTIME_IPC_SCHEMA:
        raise ValueError("runtime IPC frame schema is unsupported")
    request_id = decoded["request_id"]
    _validate_request_id(request_id)
    try:
        operation = NautilusRuntimeIpcOperation(decoded["operation"])
        status = NautilusRuntimeIpcStatus(decoded["status"])
    except (TypeError, ValueError) as error:
        raise ValueError("runtime IPC operation or status is unsupported") from error
    payload = _plain_json(decoded["payload"])
    if not isinstance(payload, dict):
        raise ValueError("runtime IPC payload must be a JSON object")
    fingerprint = decoded["fingerprint"]
    if not isinstance(fingerprint, str):
        raise ValueError("runtime IPC fingerprint must be a string")
    return NautilusRuntimeIpcFrame(
        request_id=request_id,
        operation=operation,
        status=status,
        payload=payload,
        fingerprint=fingerprint,
    )


def read_nautilus_runtime_ipc_frame(
    stream: _FrameLineReader,
    *,
    max_frame_bytes: int = MAX_NAUTILUS_RUNTIME_IPC_FRAME_BYTES,
) -> NautilusRuntimeIpcFrame | None:
    """Read one bounded line; return ``None`` only for clean stream EOF."""

    if not hasattr(stream, "readline"):
        raise TypeError("stream must provide readline")
    if (
        not isinstance(max_frame_bytes, int)
        or isinstance(max_frame_bytes, bool)
        or max_frame_bytes <= 1
    ):
        raise ValueError("max_frame_bytes must be an integer greater than one")
    line = stream.readline(max_frame_bytes + 1)
    if line == b"":
        return None
    if len(line) > max_frame_bytes or not line.endswith(b"\n"):
        raise ValueError("runtime IPC frame is unterminated or exceeds its byte limit")
    return decode_nautilus_runtime_ipc_frame(line, max_frame_bytes=max_frame_bytes)


def serve_nautilus_runtime_ipc(
    input_stream: BinaryIO,
    output_stream: BinaryIO,
    handler: NautilusRuntimeIpcOperationHandler,
    *,
    max_frame_bytes: int = MAX_NAUTILUS_RUNTIME_IPC_FRAME_BYTES,
    max_requests: int = 1_000_000,
) -> int:
    """Serve one forward session with strict lifecycle and retry semantics.

    Only the most recently completed request is cached. The host supervisor
    serializes requests per instance, so retrying the latest frame after a lost
    response is safe without unbounded server memory. An execution exception
    poisons the session until an exact-checkpoint restore succeeds.
    """

    if not callable(getattr(handler, "open", None)):
        raise TypeError("handler must implement the runtime IPC operation contract")
    if any(not callable(getattr(handler, name, None)) for name in ("execute", "restore", "close")):
        raise TypeError("handler must implement the runtime IPC operation contract")
    if not isinstance(max_requests, int) or isinstance(max_requests, bool) or max_requests < 1:
        raise ValueError("max_requests must be a positive integer")

    opened = False
    needs_restore = False
    last_request: NautilusRuntimeIpcFrame | None = None
    last_response: NautilusRuntimeIpcFrame | None = None
    request_count = 0
    try:
        while request_count < max_requests:
            request = read_nautilus_runtime_ipc_frame(
                input_stream,
                max_frame_bytes=max_frame_bytes,
            )
            if request is None:
                return 0
            if request.status is not NautilusRuntimeIpcStatus.REQUEST:
                return 2
            if last_request is not None and request.request_id == last_request.request_id:
                if request.fingerprint != last_request.fingerprint or last_response is None:
                    return 2
                _write_frame(output_stream, last_response, max_frame_bytes=max_frame_bytes)
                continue
            request_count += 1
            if not opened and request.operation is not NautilusRuntimeIpcOperation.OPEN:
                response = _response(request, NautilusRuntimeIpcStatus.ERROR, "session_not_open")
            elif opened and request.operation is NautilusRuntimeIpcOperation.OPEN:
                response = _response(
                    request, NautilusRuntimeIpcStatus.ERROR, "session_already_open"
                )
            elif needs_restore and request.operation not in {
                NautilusRuntimeIpcOperation.RESTORE,
                NautilusRuntimeIpcOperation.CLOSE,
            }:
                response = _response(request, NautilusRuntimeIpcStatus.ERROR, "restore_required")
            else:
                try:
                    result = getattr(handler, request.operation.value)(request.payload)
                    if not isinstance(result, Mapping):
                        raise TypeError("runtime operation result must be a mapping")
                    response = create_nautilus_runtime_ipc_frame(
                        request_id=request.request_id,
                        operation=request.operation,
                        status=NautilusRuntimeIpcStatus.SUCCESS,
                        payload=result,
                    )
                    if request.operation is NautilusRuntimeIpcOperation.OPEN:
                        opened = True
                    elif request.operation is NautilusRuntimeIpcOperation.RESTORE:
                        needs_restore = False
                    elif request.operation is NautilusRuntimeIpcOperation.CLOSE:
                        opened = False
                except Exception:
                    response = _response(
                        request, NautilusRuntimeIpcStatus.ERROR, "operation_failed"
                    )
                    if request.operation is NautilusRuntimeIpcOperation.EXECUTE:
                        needs_restore = True
            last_request = request
            last_response = response
            _write_frame(output_stream, response, max_frame_bytes=max_frame_bytes)
            if request.operation is NautilusRuntimeIpcOperation.CLOSE:
                return 0 if response.status is NautilusRuntimeIpcStatus.SUCCESS else 3
        return 4
    finally:
        if opened:
            try:
                handler.close({})
            except Exception:
                pass


def _response(
    request: NautilusRuntimeIpcFrame,
    status: NautilusRuntimeIpcStatus,
    error_code: str,
) -> NautilusRuntimeIpcFrame:
    return create_nautilus_runtime_ipc_frame(
        request_id=request.request_id,
        operation=request.operation,
        status=status,
        payload={"error_code": error_code},
    )


def _write_frame(
    output_stream: _FrameWriter,
    frame: NautilusRuntimeIpcFrame,
    *,
    max_frame_bytes: int,
) -> None:
    output_stream.write(encode_nautilus_runtime_ipc_frame(frame, max_frame_bytes=max_frame_bytes))
    output_stream.flush()


def _unsigned_wire(
    request_id: str,
    operation: NautilusRuntimeIpcOperation,
    status: NautilusRuntimeIpcStatus,
    payload: dict[str, object],
) -> dict[str, object]:
    _validate_request_id(request_id)
    if not isinstance(operation, NautilusRuntimeIpcOperation):
        raise TypeError("operation must be a NautilusRuntimeIpcOperation")
    if not isinstance(status, NautilusRuntimeIpcStatus):
        raise TypeError("status must be a NautilusRuntimeIpcStatus")
    return {
        "schema": NAUTILUS_FORWARD_RUNTIME_IPC_SCHEMA,
        "request_id": request_id,
        "operation": operation.value,
        "status": status.value,
        "payload": payload,
    }


def _validate_request_id(value: object) -> None:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 128:
        raise ValueError(
            "runtime IPC request_id must be a non-empty UTF-8 string of at most 128 bytes"
        )


def _plain_json(value: object) -> object:
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("runtime IPC payload contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("runtime IPC object keys must be strings")
            result[key] = _plain_json(item)
        return result
    if isinstance(value, list | tuple):
        return [_plain_json(item) for item in value]
    raise TypeError(f"runtime IPC payload contains unsupported {type(value).__name__}")


def _freeze_wire(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_wire(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_wire(item) for item in value)
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("runtime IPC frame contains duplicate object fields")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("runtime IPC frame contains a non-finite JSON number")


__all__ = [
    "MAX_NAUTILUS_RUNTIME_IPC_FRAME_BYTES",
    "NautilusRuntimeIpcFrame",
    "NautilusRuntimeIpcClient",
    "NautilusRuntimeIpcError",
    "NautilusRuntimeIpcOperation",
    "NautilusRuntimeIpcOperationHandler",
    "NautilusRuntimeIpcStatus",
    "create_nautilus_runtime_ipc_frame",
    "decode_nautilus_runtime_ipc_frame",
    "encode_nautilus_runtime_ipc_frame",
    "read_nautilus_runtime_ipc_frame",
    "serve_nautilus_runtime_ipc",
]
