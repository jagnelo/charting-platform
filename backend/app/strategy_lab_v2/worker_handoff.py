"""Versioned, authenticated dispatch envelopes for dedicated workers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.strategy_lab_v2.canonical import canonical_json, require_sha256_digest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.postgres_result_materialization import decode_canonical_contract
from app.strategy_lab_v2.worker_process import WorkerExecutionRequest

WORKER_HANDOFF_SCHEMA = "strategy-lab.worker-execution-request.v2"


def encode_worker_handoff(request: WorkerExecutionRequest) -> Mapping[str, str]:
    """Encode one immutable worker request into a transport-neutral mapping."""

    if not isinstance(request, WorkerExecutionRequest):
        raise TypeError("request must be a WorkerExecutionRequest")
    return {
        "schema": WORKER_HANDOFF_SCHEMA,
        "request_fingerprint": request.request_fingerprint,
        "request_json": canonical_json(request),
    }


def decode_worker_handoff(payload: DispatchPayload) -> WorkerExecutionRequest:
    """Decode and authenticate a worker request carried by a durable payload."""

    if not isinstance(payload, DispatchPayload):
        raise TypeError("payload must be a DispatchPayload")
    value = payload.value
    if set(value) != {"request_fingerprint", "request_json", "schema"}:
        raise ValueError("worker handoff payload fields are invalid")
    schema = value["schema"]
    fingerprint = value["request_fingerprint"]
    request_json = value["request_json"]
    if schema != WORKER_HANDOFF_SCHEMA:
        raise ValueError("worker handoff payload schema is unsupported")
    if not isinstance(fingerprint, str):
        raise ValueError("worker handoff request fingerprint is malformed")
    require_sha256_digest(fingerprint, field_name="request_fingerprint")
    if not isinstance(request_json, str) or not request_json.strip():
        raise ValueError("worker handoff request bytes are malformed")
    try:
        request = decode_canonical_contract(request_json, WorkerExecutionRequest)
    except (TypeError, ValueError) as error:
        raise ValueError("worker handoff request bytes are malformed") from error
    if request.request_fingerprint != fingerprint:
        raise ValueError("worker handoff request identity drifted")
    if payload.payload_digest != _payload_digest(encode_worker_handoff(request)):
        raise ValueError("worker handoff envelope identity drifted")
    return request


async def materialize_worker_handoff(_entry: Any, payload: DispatchPayload) -> WorkerExecutionRequest:
    """Adapt the strict decoder to the worker service materializer callback."""

    return decode_worker_handoff(payload)


def _payload_digest(value: Mapping[str, Any]) -> str:
    from app.strategy_lab_v2.canonical import content_digest

    return content_digest(value)


__all__ = [
    "WORKER_HANDOFF_SCHEMA",
    "decode_worker_handoff",
    "encode_worker_handoff",
    "materialize_worker_handoff",
]
