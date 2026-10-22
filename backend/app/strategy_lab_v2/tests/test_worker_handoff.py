from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.nautilus_runtime_bundle import NautilusTrialInputBinding
from app.strategy_lab_v2.tests.test_worker_process import _request
from app.strategy_lab_v2.worker_handoff import (
    WORKER_HANDOFF_SCHEMA,
    decode_worker_handoff,
    encode_worker_handoff,
    materialize_worker_handoff,
)


@pytest.mark.asyncio
async def test_worker_handoff_round_trips_typed_execution_request(tmp_path: Path) -> None:
    request = _request(tmp_path)
    request = replace(
        request,
        runtime_input_artifact=replace(
            request.runtime_input_artifact,
            trial_binding=NautilusTrialInputBinding(
                attempt_id=request.runtime_request.attempt_id,
                trial_fingerprint=content_digest("trial"),
                experiment_fingerprint=content_digest("experiment"),
                portfolio_fingerprint=content_digest("portfolio"),
                snapshot_fingerprint=content_digest("snapshot"),
                strategy_package_fingerprint=request.runtime_request.package_fingerprint,
                engine_input_fingerprint=content_digest("engine-input"),
                invocation_input_digest=content_digest("invocation-input"),
            ),
        ),
    )
    payload = DispatchPayload.from_mapping(encode_worker_handoff(request))

    assert decode_worker_handoff(payload) == request
    assert await materialize_worker_handoff(object(), payload) == request
    assert payload.payload_digest.startswith("sha256:")


def test_worker_handoff_rejects_schema_and_identity_drift(tmp_path: Path) -> None:
    request = _request(tmp_path)
    encoded = dict(encode_worker_handoff(request))
    encoded["schema"] = "strategy-lab.worker-execution-request.v0"
    with pytest.raises(ValueError, match="schema"):
        decode_worker_handoff(DispatchPayload.from_mapping(encoded))

    encoded = dict(encode_worker_handoff(request))
    encoded["request_fingerprint"] = request.orchestration_plan.fingerprint
    with pytest.raises(ValueError, match="identity"):
        decode_worker_handoff(DispatchPayload.from_mapping(encoded))


def test_worker_handoff_rejects_reordered_canonical_request_fields(tmp_path: Path) -> None:
    request = _request(tmp_path)
    encoded = dict(encode_worker_handoff(request))
    root = json.loads(encoded["request_json"])
    assert root[0] == "dataclass"
    root[2] = list(reversed(root[2]))
    encoded["request_json"] = json.dumps(root, separators=(",", ":"), sort_keys=True)
    encoded["schema"] = WORKER_HANDOFF_SCHEMA
    with pytest.raises(ValueError, match="bytes are malformed"):
        decode_worker_handoff(DispatchPayload.from_mapping(encoded))
