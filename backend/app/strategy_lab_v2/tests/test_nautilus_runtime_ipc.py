from __future__ import annotations

import io
import json

import pytest

from app.strategy_lab_v2.nautilus_runtime_ipc import (
    NautilusRuntimeIpcOperation,
    NautilusRuntimeIpcStatus,
    create_nautilus_runtime_ipc_frame,
    decode_nautilus_runtime_ipc_frame,
    encode_nautilus_runtime_ipc_frame,
    read_nautilus_runtime_ipc_frame,
)


def _frame(payload: dict[str, object] | None = None):
    return create_nautilus_runtime_ipc_frame(
        request_id="forward-1:17",
        operation=NautilusRuntimeIpcOperation.EXECUTE,
        status=NautilusRuntimeIpcStatus.REQUEST,
        payload=payload or {"delivery_fingerprint": "sha256:" + "a" * 64},
    )


def test_runtime_ipc_frame_round_trips_as_fingerprinted_ndjson() -> None:
    frame = _frame({"sequence": 17, "event": {"bid": 100.25, "asks": [101.0]}})

    encoded = encode_nautilus_runtime_ipc_frame(frame)
    decoded = decode_nautilus_runtime_ipc_frame(encoded)

    assert encoded.endswith(b"\n")
    assert decoded == frame
    assert decoded.fingerprint == frame.fingerprint
    with pytest.raises(TypeError):
        decoded.payload["new"] = "not mutable"  # type: ignore[index]


def test_runtime_ipc_rejects_tampered_content_and_duplicate_json_fields() -> None:
    encoded = encode_nautilus_runtime_ipc_frame(_frame())
    tampered = json.loads(encoded)
    tampered["payload"]["delivery_fingerprint"] = "sha256:" + "b" * 64

    with pytest.raises(ValueError, match="fingerprint"):
        decode_nautilus_runtime_ipc_frame(
            json.dumps(tampered, separators=(",", ":")).encode() + b"\n"
        )
    with pytest.raises(ValueError, match="malformed JSON"):
        decode_nautilus_runtime_ipc_frame(b'{"schema":"one","schema":"two"}\n')


def test_runtime_ipc_enforces_exact_fields_finite_json_and_frame_limits() -> None:
    frame = _frame()
    encoded = encode_nautilus_runtime_ipc_frame(frame)

    with pytest.raises(ValueError, match="byte limit"):
        encode_nautilus_runtime_ipc_frame(frame, max_frame_bytes=len(encoded) - 1)
    with pytest.raises(ValueError, match="byte limit"):
        decode_nautilus_runtime_ipc_frame(encoded, max_frame_bytes=len(encoded) - 1)
    with pytest.raises(ValueError, match="non-finite"):
        _frame({"value": float("nan")})
    with pytest.raises(ValueError, match="fields"):
        decode_nautilus_runtime_ipc_frame(
            b'{"schema":"strategy-lab.nautilus-forward-runtime.v1",'
            b'"request_id":"x","operation":"close","status":"request",'
            b'"payload":{},"fingerprint":"sha256:' + b"a" * 64 + b'",'
            b'"extra":true}\n'
        )


def test_runtime_ipc_stream_reads_exactly_one_frame_and_detects_truncation() -> None:
    encoded = encode_nautilus_runtime_ipc_frame(_frame())
    stream = io.BytesIO(encoded + encoded)

    assert read_nautilus_runtime_ipc_frame(stream) == _frame()
    assert read_nautilus_runtime_ipc_frame(stream) == _frame()
    assert read_nautilus_runtime_ipc_frame(stream) is None
    with pytest.raises(ValueError, match="unterminated"):
        read_nautilus_runtime_ipc_frame(io.BytesIO(encoded[:-1]))
