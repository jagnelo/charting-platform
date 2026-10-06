from __future__ import annotations

import io
import json

import pytest

from app.strategy_lab_v2.nautilus_runtime_ipc import (
    NautilusRuntimeIpcClient,
    NautilusRuntimeIpcError,
    NautilusRuntimeIpcOperation,
    NautilusRuntimeIpcStatus,
    create_nautilus_runtime_ipc_frame,
    decode_nautilus_runtime_ipc_frame,
    encode_nautilus_runtime_ipc_frame,
    read_nautilus_runtime_ipc_frame,
    serve_nautilus_runtime_ipc,
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


class _Handler:
    def __init__(self, *, fail_first_execute: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.fail_first_execute = fail_first_execute

    def open(self, payload):
        self.calls.append(("open", dict(payload)))
        return {"ready": True}

    def execute(self, payload):
        self.calls.append(("execute", dict(payload)))
        if self.fail_first_execute:
            self.fail_first_execute = False

            class DiagnosticFailure(RuntimeError):
                diagnostic_fields = ("base_window_fingerprint", "context")

            raise DiagnosticFailure("private details are not sent over IPC")
        return {"accepted": payload.get("event_id")}

    def restore(self, payload):
        self.calls.append(("restore", dict(payload)))
        return {"restored": payload.get("checkpoint_fingerprint")}

    def close(self, payload):
        self.calls.append(("close", dict(payload)))
        return {"closed": True}


def _request(request_id: str, operation: NautilusRuntimeIpcOperation, payload=None):
    return create_nautilus_runtime_ipc_frame(
        request_id=request_id,
        operation=operation,
        status=NautilusRuntimeIpcStatus.REQUEST,
        payload={} if payload is None else payload,
    )


def _serve(requests: list):
    input_stream = io.BytesIO(
        b"".join(encode_nautilus_runtime_ipc_frame(item) for item in requests)
    )
    output_stream = io.BytesIO()
    handler = _Handler()
    result = serve_nautilus_runtime_ipc(input_stream, output_stream, handler)
    output_stream.seek(0)
    responses = []
    while response := read_nautilus_runtime_ipc_frame(output_stream):
        responses.append(response)
    return result, handler, responses


def test_runtime_ipc_server_persists_handler_and_caches_latest_request() -> None:
    execute = _request("execute-1", NautilusRuntimeIpcOperation.EXECUTE, {"event_id": "e-1"})
    result, handler, responses = _serve(
        [
            _request("open-1", NautilusRuntimeIpcOperation.OPEN, {"instance_id": "i-1"}),
            execute,
            execute,
            _request("close-1", NautilusRuntimeIpcOperation.CLOSE),
        ]
    )

    assert result == 0
    assert [call[0] for call in handler.calls] == ["open", "execute", "close"]
    assert len(responses) == 4
    assert responses[1].status is NautilusRuntimeIpcStatus.SUCCESS
    assert responses[1] == responses[2]


def test_runtime_ipc_server_requires_restore_after_uncertain_execution(capsys) -> None:
    requests = [
        _request("open", NautilusRuntimeIpcOperation.OPEN),
        _request("execute-fails", NautilusRuntimeIpcOperation.EXECUTE, {"event_id": "e-1"}),
        _request("blocked", NautilusRuntimeIpcOperation.EXECUTE, {"event_id": "e-2"}),
        _request(
            "restore",
            NautilusRuntimeIpcOperation.RESTORE,
            {"checkpoint_fingerprint": "sha256:" + "c" * 64},
        ),
        _request("execute-retried", NautilusRuntimeIpcOperation.EXECUTE, {"event_id": "e-1"}),
        _request("close", NautilusRuntimeIpcOperation.CLOSE),
    ]
    input_stream = io.BytesIO(
        b"".join(encode_nautilus_runtime_ipc_frame(item) for item in requests)
    )
    output_stream = io.BytesIO()
    handler = _Handler(fail_first_execute=True)

    assert serve_nautilus_runtime_ipc(input_stream, output_stream, handler) == 0
    output_stream.seek(0)
    responses = []
    while response := read_nautilus_runtime_ipc_frame(output_stream):
        responses.append(response)

    assert [response.status for response in responses] == [
        NautilusRuntimeIpcStatus.SUCCESS,
        NautilusRuntimeIpcStatus.ERROR,
        NautilusRuntimeIpcStatus.ERROR,
        NautilusRuntimeIpcStatus.SUCCESS,
        NautilusRuntimeIpcStatus.SUCCESS,
        NautilusRuntimeIpcStatus.SUCCESS,
    ]
    assert responses[1].payload == {"error_code": "operation_failed"}
    assert responses[2].payload == {"error_code": "restore_required"}
    assert [call[0] for call in handler.calls] == ["open", "execute", "restore", "execute", "close"]
    diagnostics = capsys.readouterr().err
    assert (
        "nautilus runtime execute failed: DiagnosticFailure at test_nautilus_runtime_ipc.py:"
        in diagnostics
    )
    assert "fields=base_window_fingerprint,context" in diagnostics
    assert "private details" not in diagnostics


def test_runtime_ipc_client_correlates_request_and_returns_response_payload() -> None:
    response = create_nautilus_runtime_ipc_frame(
        request_id="request-1",
        operation=NautilusRuntimeIpcOperation.EXECUTE,
        status=NautilusRuntimeIpcStatus.SUCCESS,
        payload={"result_fingerprint": "sha256:" + "d" * 64},
    )
    response_stream = io.BytesIO(encode_nautilus_runtime_ipc_frame(response))
    request_stream = io.BytesIO()
    client = NautilusRuntimeIpcClient(response_stream, request_stream)

    payload = client.request(
        NautilusRuntimeIpcOperation.EXECUTE,
        {"event_id": "e-1"},
        request_id="request-1",
    )

    assert payload == {"result_fingerprint": "sha256:" + "d" * 64}
    request_stream.seek(0)
    sent = read_nautilus_runtime_ipc_frame(request_stream)
    assert sent is not None
    assert sent.request_id == "request-1"
    assert sent.status is NautilusRuntimeIpcStatus.REQUEST


def test_runtime_ipc_client_raises_only_the_sanitized_remote_error_code() -> None:
    response = create_nautilus_runtime_ipc_frame(
        request_id="request-2",
        operation=NautilusRuntimeIpcOperation.RESTORE,
        status=NautilusRuntimeIpcStatus.ERROR,
        payload={"error_code": "checkpoint_unavailable"},
    )
    client = NautilusRuntimeIpcClient(
        io.BytesIO(encode_nautilus_runtime_ipc_frame(response)),
        io.BytesIO(),
    )

    with pytest.raises(NautilusRuntimeIpcError) as captured:
        client.request(
            NautilusRuntimeIpcOperation.RESTORE,
            {"checkpoint_fingerprint": "sha256:" + "e" * 64},
            request_id="request-2",
        )
    assert captured.value.error_code == "checkpoint_unavailable"
    assert "checkpoint_unavailable" in str(captured.value)
    with pytest.raises(ValueError, match="bounded lowercase"):
        NautilusRuntimeIpcError("private\nserver details")
